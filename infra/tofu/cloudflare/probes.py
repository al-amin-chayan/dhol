"""Value-free route probe contracts; live requests never follow redirects."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
import errno
import ipaddress
import socket
import urllib.error
import urllib.request

from backend import NoRedirect
from control_plane import ContractError, require


@dataclass(frozen=True)
class Response:
    status: int
    location: str = ""
    body: bytes = b""


def access_denied(response: Response) -> bool:
    if response.status in {401, 403}:
        return True
    destination = urlsplit(response.location)
    return (
        response.status in {302, 303, 307}
        and destination.scheme == "https"
        and bool(destination.hostname)
        and destination.hostname.endswith(".cloudflareaccess.com")
        and destination.path.startswith("/cdn-cgi/access/login")
    )


def check(kind: str, response: Response):
    if kind in {
        "unauthenticated",
        "wrong-founder",
        "wrong-service-token",
        "alternate-dns",
        "direct-ip",
    }:
        require(
            access_denied(response) or (kind == "direct-ip" and response.status == 0),
            "route exposed or denial was not proven",
        )
    elif kind in {"founder", "service-token"}:
        # Access accepted the caller; the independent application may still require its own session/key.
        require(
            not access_denied(response)
            and (
                200 <= response.status < 300
                or (response.status in {302, 303} and response.location.startswith("/"))
            ),
            "authorized route probe failed",
        )
    elif kind == "method":
        require(response.status in {403, 405}, "machine route accepts forbidden method")
    elif kind == "path":
        require(
            access_denied(response) or response.status == 404,
            "machine exception escapes its path",
        )
    elif kind == "webhook-token":
        require(
            response.status == 401,
            "webhook accepted missing or invalid application token",
        )
    else:
        raise ContractError("unknown route probe kind")


def request(hostname: str, path: str = "/", headers=None) -> Response:
    require(
        path.startswith("/") and not path.startswith("//") and "?" not in path,
        "invalid probe path",
    )
    require(
        urlsplit("https://" + hostname).hostname == hostname and "/" not in hostname,
        "invalid probe hostname",
    )
    http = urllib.request.Request(
        "https://" + hostname + path,
        headers={"User-Agent": "Dholbeat-production-boundary-verifier/1.0", **(headers or {})},
        method="GET",
    )
    try:
        result = urllib.request.build_opener(NoRedirect).open(http, timeout=15)
    except urllib.error.HTTPError as error:
        result = error
    with result:
        # R2's unsigned S3 request reports its missing Authorization as 400.
        # Retain only a bounded error body so callers can distinguish that
        # exact denial from an unrelated bad request.
        body = result.read(4097) if result.status == 400 else b""
        return Response(result.status, result.headers.get("Location", ""), body)


def private_s3_denied(response: Response) -> bool:
    if response.status == 403:
        return True
    if response.status != 400 or len(response.body) > 4096 or b"<!DOCTYPE" in response.body.upper():
        return False
    import xml.etree.ElementTree as ET
    try:
        error = ET.fromstring(response.body)
        return (error.tag == "Error" and error.findtext("Code") == "InvalidArgument"
                and error.findtext("Message") == "Authorization")
    except ET.ParseError:
        return False


def verify_founder_policy(application, policy, hostname: str, founder_email: str):
    require(
        application.get("domain") == hostname
        and application.get("type") == "self_hosted",
        "Access app route differs",
    )
    require(
        application.get("options_preflight_bypass") is False,
        "Access preflight bypass is enabled",
    )
    attached = application.get("policies", [])
    require(
        len(attached) == 1 and attached[0].get("id") == policy.get("id"),
        "unexpected or missing Access policy",
    )
    require(
        policy.get("decision") == "allow"
        and policy.get("include") == [{"email": {"email": founder_email}}]
        and not policy.get("exclude")
        and not policy.get("require"),
        "founder Access is not default-deny",
    )


def matrix(manifest):
    """All routes need these contracts before their later promotion; fixtures exercise them now."""
    result = {}
    for route in manifest["routes"]:
        kinds = ["unauthenticated", "direct-ip", "alternate-dns", "path"]
        if route["caller"] == "human":
            kinds += ["founder", "wrong-founder"]
        else:
            kinds += ["method", "webhook-token"]
        if route.get("machine_path"):
            kinds += ["service-token", "wrong-service-token"]
        result[route["id"]] = kinds
    return result


def run_live(manifest, credentials):
    """Read-only edge probes. Missing deployments/identities are explicit, never passing probes.

    GET is the only live method, including the forbidden-method webhook probe. A positive
    POST is tested against the disposable loopback relay fixture to avoid invoking a workflow.
    """
    results = {}
    for route in manifest["routes"]:
        if route["status"] != "adopted":
            results[route["id"]] = {
                "status": "promotion-required",
                "admission": route["status"],
            }
            continue
        hostname = route["hostname"]
        outcomes = {}
        anonymous = request(hostname)
        check("unauthenticated", anonymous)
        outcomes["unauthenticated"] = "denied"
        wrong = request(
            hostname, headers={"Cookie": "CF_Authorization=invalid-disposable-probe"}
        )
        check("wrong-founder", wrong)
        outcomes["wrong-founder"] = "denied"
        alternate = request(hostname, headers={"Host": "undeclared-probe." + hostname})
        require(
            access_denied(alternate) or alternate.status == 404,
            "alternate DNS exposes an origin",
        )
        outcomes["alternate-dns"] = "denied"
        identity_key = "FOUNDER_ACCESS_JWT_" + route["id"].replace("-", "_").upper()
        if credentials.get(identity_key):
            founder = request(
                hostname,
                headers={"Cookie": "CF_Authorization=" + credentials[identity_key]},
            )
            check("founder", founder)
            outcomes["founder"] = "accepted"
        else:
            outcomes["founder"] = "scoped-session-required"
        if route.get("machine_path"):
            path = "/api/public/v1/integrations"
            wrong = request(
                hostname,
                path,
                headers={
                    "CF-Access-Client-Id": "invalid-disposable-probe",
                    "CF-Access-Client-Secret": "invalid-disposable-probe",
                },
            )
            check("wrong-service-token", wrong)
            outcomes["wrong-service-token"] = "denied"
            if all(
                credentials.get(key)
                for key in (
                    "N8N_ACCESS_CLIENT_ID",
                    "N8N_ACCESS_CLIENT_SECRET",
                    "PUBLISHER_API_KEY",
                )
            ):
                machine = request(
                    hostname,
                    path,
                    headers={
                        "CF-Access-Client-Id": credentials["N8N_ACCESS_CLIENT_ID"],
                        "CF-Access-Client-Secret": credentials[
                            "N8N_ACCESS_CLIENT_SECRET"
                        ],
                        "Authorization": credentials["PUBLISHER_API_KEY"],
                    },
                )
                check("service-token", machine)
                outcomes["service-token"] = "accepted"
            else:
                outcomes["service-token"] = (
                    "scoped-service-and-application-credentials-required"
                )
        ip_key = "PROBE_" + route["host_id"].replace("-", "_").upper() + "_IP"
        if credentials.get(ip_key):
            check(
                "direct-ip",
                direct_ip(
                    credentials[ip_key], urlsplit(route["origin"]).port, hostname
                ),
            )
            outcomes["direct-ip"] = "denied"
        else:
            outcomes["direct-ip"] = "explicit-public-host-ip-required"
        check("path", request(hostname, "/__disposable-invalid-path-probe"))
        outcomes["path"] = "denied"
        results[route["id"]] = outcomes
    return results


def direct_ip(address, port, hostname):
    require(
        ipaddress.ip_address(address).is_global and 0 < port < 65536,
        "probe needs an explicit public host IP",
    )
    target = "[" + address + "]" if ":" in address else address
    http = urllib.request.Request(
        f"http://{target}:{port}/", headers={"Host": hostname}, method="GET"
    )
    try:
        result = urllib.request.build_opener(NoRedirect).open(http, timeout=5)
    except urllib.error.HTTPError as error:
        result = error
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, (TimeoutError, socket.timeout)) or (
            isinstance(reason, OSError)
            and reason.errno
            in {
                errno.ECONNREFUSED,
                errno.EHOSTUNREACH,
                errno.ENETUNREACH,
                errno.ETIMEDOUT,
                errno.ECONNRESET,
            }
        ):
            return Response(0)
        raise ContractError("direct-IP transport could not be verified") from None
    with result:
        return Response(result.status, result.headers.get("Location", ""))
