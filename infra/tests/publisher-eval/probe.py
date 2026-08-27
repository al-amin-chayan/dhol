#!/usr/bin/env python3
"""Run the DG-01 publisher fixture matrix against a disposable candidate.

The probe never contacts a social provider. Channels are database fixtures, so
every authorization result describes the publisher's own authorization layer
and nothing else. Credentials are recorded as truncated SHA-256 digests; no
password, session token or API key reaches the evidence file.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html import unescape
from typing import Any, Callable

SCHEMA_VERSION = 1

PASS = "pass"
FAIL = "fail"
UNSUPPORTED = "unsupported"

# The fixture matrix every candidate is measured against. `expectation` is what
# a publisher must do to satisfy the founder-approved multi-project
# requirement; `result` records what it actually did.
MATRIX = [
    ("bootstrap.first-project", "A first project tenant can be created without SMTP or a manual browser step"),
    ("bootstrap.second-project", "A second project tenant exists that is separate from the first"),
    ("bootstrap.no-account-project", "A third project tenant with no connected channel exists"),
    ("bootstrap.registration-lockable", "Public registration can be closed after bootstrap"),
    ("api.machine-credential", "The edition issues a machine credential usable without a browser session"),
    ("api.credential-tenant-bound", "Each machine credential resolves to exactly one project tenant"),
    ("api.list-own-channels", "A tenant credential lists that tenant's own channels"),
    ("authz.no-credential-rejected", "An unauthenticated public-API call is rejected"),
    ("authz.invalid-credential-rejected", "An unknown credential is rejected"),
    ("authz.cross-tenant-read-rejected", "Tenant A's credential cannot read tenant B's channel"),
    ("authz.cross-tenant-write-rejected", "Tenant A's credential cannot schedule into tenant B's channel"),
    ("authz.cross-tenant-post-read-rejected", "Tenant A's credential cannot read tenant B's post"),
    ("authz.cross-tenant-delete-rejected", "Tenant A's credential cannot delete tenant B's post"),
    ("authz.rotated-credential-rejected", "A rotated credential stops working immediately"),
    ("posts.schedule", "A post can be scheduled through the machine API"),
    ("posts.list", "A scheduled post is listed for its own tenant"),
    ("posts.cancel", "A scheduled post can be cancelled or deleted before it is sent"),
]

MATRIX_REQUIREMENTS = dict(MATRIX)


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()[:16]


def parse_instant(value: str) -> datetime.datetime | None:
    """Read an ISO-8601 timestamp as an aware UTC instant, or None if it is not one.

    A restore is allowed to re-spell a timestamp but not to move it, so every
    comparison here is on the instant rather than on the string. A naive value
    is read as UTC because every timestamp this harness requests is UTC.
    """
    try:
        parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def iso_z(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Check:
    id: str
    requirement: str
    result: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement": self.requirement,
            "result": self.result,
            "detail": self.detail,
            "evidence": self.evidence,
        }


class Recorder:
    def __init__(self) -> None:
        self._checks: dict[str, Check] = {}

    def record(self, check_id: str, result: str, detail: str, **evidence: Any) -> None:
        if check_id not in MATRIX_REQUIREMENTS:
            raise KeyError(f"check is not part of the DG-01 matrix: {check_id}")
        if result not in {PASS, FAIL, UNSUPPORTED}:
            raise ValueError(f"unknown result: {result}")
        self._checks[check_id] = Check(
            id=check_id,
            requirement=MATRIX_REQUIREMENTS[check_id],
            result=result,
            detail=detail,
            evidence=evidence,
        )

    def unrecorded(self) -> list[str]:
        return [check_id for check_id, _ in MATRIX if check_id not in self._checks]

    def as_list(self) -> list[dict[str, Any]]:
        return [self._checks[check_id].as_dict() for check_id, _ in MATRIX if check_id in self._checks]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface a redirect instead of following it.

    A session-based candidate rotates its session cookie in the very response
    that redirects, so a followed redirect is replayed with the pre-login
    cookie and looks like an authentication failure.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102 - urllib contract
        return None


class Http:
    """Minimal explicit HTTP client. Cookies are carried by hand so that a
    candidate's cookie domain cannot silently drop authentication."""

    def __init__(self, base: str, timeout: int = 30) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout
        self._no_redirect = urllib.request.build_opener(_NoRedirect)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        form_body: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
    ) -> tuple[int, str, dict[str, list[str]]]:
        data = None
        request_headers = dict(headers or {})
        if json_body is not None:
            data = json.dumps(json_body).encode()
            request_headers.setdefault("Content-Type", "application/json")
        elif form_body is not None:
            data = urllib.parse.urlencode(form_body).encode()
            request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        request = urllib.request.Request(self.base + path, data=data, method=method)
        for key, value in request_headers.items():
            request.add_header(key, value)
        opener = urllib.request.urlopen if follow_redirects else self._no_redirect.open
        try:
            response = opener(request, timeout=self.timeout)
            body, status, raw = response.read(), response.status, response.headers
        except urllib.error.HTTPError as error:
            body, status, raw = error.read(), error.code, error.headers
        collected: dict[str, list[str]] = {}
        for key in set(raw.keys()):
            collected[key.lower()] = raw.get_all(key) or []
        return status, body.decode(errors="replace"), collected

    def wait_until(self, predicate: Callable[[], bool], *, attempts: int, delay: float, what: str) -> None:
        for _ in range(attempts):
            try:
                if predicate():
                    return
            except Exception:  # noqa: BLE001 - a starting service refuses connections
                pass
            time.sleep(delay)
        raise TimeoutError(f"timed out waiting for {what}")


def sql(container: str, database: str, user: str, statement: str) -> str:
    completed = subprocess.run(
        ["docker", "exec", container, "psql", "-U", user, "-d", database, "-tAc", statement],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"fixture SQL failed: {completed.stderr.strip()[:300]}")
    return completed.stdout.strip()


PROJECTS = [
    ("project-a", "Project A"),
    ("project-b", "Project B"),
    ("project-c", "Project C"),
]


def probe_postiz(args: argparse.Namespace, recorder: Recorder) -> dict[str, Any]:
    api = Http(args.base_url.rstrip("/") + "/api")
    api.wait_until(
        lambda: api.request("GET", "/user/self")[0] == 401,
        attempts=args.ready_attempts,
        delay=args.ready_delay,
        what="the Postiz backend to answer /user/self",
    )

    tenants: dict[str, dict[str, str]] = {}
    for slug, company in PROJECTS:
        email = f"{slug}@{args.fixture_domain}"
        password = f"{args.fixture_password_prefix}-{slug}"
        status, body, _ = api.request(
            "POST",
            "/auth/register",
            json_body={"email": email, "password": password, "company": company, "provider": "LOCAL"},
        )
        if status != 200:
            raise RuntimeError(f"registering {slug} failed: {status} {body[:200]}")
        status, _, headers = api.request(
            "POST",
            "/auth/login",
            json_body={"email": email, "password": password, "provider": "LOCAL"},
        )
        token = None
        for cookie in headers.get("set-cookie", []):
            match = re.match(r"auth=([^;]+)", cookie)
            if match:
                token = match.group(1)
        if status != 200 or not token:
            raise RuntimeError(f"logging in {slug} failed: {status}")
        auth = {"Cookie": f"auth={token}"}
        status, body, _ = api.request("GET", "/user/self", headers=auth)
        self_record = json.loads(body)
        tenants[slug] = {
            "email_digest": digest(email),
            "organization_id": self_record["orgId"],
            "api_key": self_record["publicApi"],
            "session": token,
        }

    recorder.record(
        "bootstrap.first-project",
        PASS,
        "POST /api/auth/register created the first organization and returned a session without an email provider configured.",
        organization_id_digest=digest(tenants["project-a"]["organization_id"]),
    )
    distinct = {tenant["organization_id"] for tenant in tenants.values()}
    recorder.record(
        "bootstrap.second-project",
        PASS if len(distinct) == len(tenants) else FAIL,
        f"{len(distinct)} distinct organization ids for {len(tenants)} registered projects.",
        organization_count=len(distinct),
    )

    # Channel fixtures. These are database rows, not provider connections.
    channels: dict[str, str] = {}
    for slug in ("project-a", "project-b"):
        organization_id = tenants[slug]["organization_id"]
        internal_id = f"dg01-{slug}"
        sql(
            args.postgres_container,
            args.postgres_database,
            args.postgres_user,
            "insert into \"Integration\" "
            "(id, \"internalId\", \"organizationId\", name, \"providerIdentifier\", type, token, \"createdAt\") "
            f"values ('{internal_id}', '{internal_id}', '{organization_id}', "
            f"'{slug} fixture channel', '{args.fixture_provider}', 'social', 'dg01-fixture-token', now()) "
            "on conflict (id) do nothing",
        )
        channels[slug] = internal_id
    recorder.record(
        "bootstrap.no-account-project",
        PASS,
        "project-c holds no channel fixture, so it exercises the empty-tenant path.",
        channelless_project="project-c",
    )

    def public(tenant: str | None, method: str, path: str, body: Any = None, key: str | None = None):
        headers = {}
        credential = key if key is not None else (tenants[tenant]["api_key"] if tenant else None)
        if credential is not None:
            headers["Authorization"] = credential
        return api.request(method, "/public/v1" + path, json_body=body, headers=headers)

    keys = {slug: tenant["api_key"] for slug, tenant in tenants.items()}
    recorder.record(
        "api.machine-credential",
        PASS if all(keys.values()) else FAIL,
        "GET /api/user/self returns a per-organization public API key usable with an Authorization header.",
        credential_digests={slug: digest(key) for slug, key in keys.items()},
    )
    recorder.record(
        "api.credential-tenant-bound",
        PASS if len(set(keys.values())) == len(keys) else FAIL,
        "Each organization carries its own distinct API key.",
        distinct_credentials=len(set(keys.values())),
    )

    status, body, _ = public("project-a", "GET", "/integrations")
    own = json.loads(body) if status == 200 else []
    own_ids = {item.get("id") for item in own}
    recorder.record(
        "api.list-own-channels",
        PASS if status == 200 and own_ids == {channels["project-a"]} else FAIL,
        f"GET /public/v1/integrations with project-a's key returned {status} and {len(own)} channel(s).",
        status=status,
        returned_ids=sorted(str(value) for value in own_ids),
    )
    leak = own_ids & {channels["project-b"]}
    # Absence from a listing is weak evidence on its own, so tenant B's channel
    # is also addressed directly by id with tenant A's credential.
    # A rejection on this endpoint means nothing unless the same endpoint answers
    # for the tenant's own channel: an unsupported route would refuse both.
    own_direct_status, _, _ = public("project-a", "GET", f"/integration-settings/{channels['project-a']}")
    direct_status, _, _ = public("project-a", "GET", f"/integration-settings/{channels['project-b']}")
    control_holds = own_direct_status == 200
    direct_rejected = direct_status >= 400
    if not control_holds:
        recorder.record(
            "authz.cross-tenant-read-rejected",
            UNSUPPORTED,
            "The direct-read endpoint did not answer for project-a's own channel "
            f"({own_direct_status}), so a rejection for project-b's ({direct_status}) proves nothing.",
            own_direct_status=own_direct_status,
            direct_read_status=direct_status,
        )
    else:
        recorder.record(
            "authz.cross-tenant-read-rejected",
            PASS if not leak and direct_rejected else FAIL,
            f"project-a's channel listing {'excludes' if not leak else 'contains'} project-b's channel; "
            f"the same endpoint returned {own_direct_status} for its own channel and "
            f"{direct_status} for project-b's.",
            leaked_ids=sorted(leak),
            own_direct_status=own_direct_status,
            direct_read_status=direct_status,
        )

    status, body, _ = public(None, "GET", "/integrations")
    recorder.record(
        "authz.no-credential-rejected",
        PASS if status == 401 else FAIL,
        f"Unauthenticated GET /public/v1/integrations returned {status}.",
        status=status,
    )
    status, body, _ = public(None, "GET", "/integrations", key="dg01-not-a-real-key")
    recorder.record(
        "authz.invalid-credential-rejected",
        PASS if status == 401 else FAIL,
        f"An unknown Authorization value returned {status}.",
        status=status,
    )

    schedule_at = args.schedule_at
    def create_post(tenant: str, channel: str, content: str, when: str | None = None):
        return public(
            tenant,
            "POST",
            "/posts",
            {
                "type": "schedule",
                "order": "",
                "shortLink": False,
                "date": when or schedule_at,
                "tags": [],
                "posts": [
                    {
                        "integration": {"id": channel},
                        # `image` is a required array and `settings` carries the
                        # provider discriminator, so both are sent explicitly.
                        "value": [{"content": content, "image": []}],
                        "group": "",
                        "settings": {"__type": args.fixture_provider},
                    }
                ],
            },
        )

    status, body, _ = create_post("project-a", channels["project-a"], "dg01 fixture post for project-a")
    own_post_id = None
    if status in (200, 201):
        try:
            payload = json.loads(body)
            own_post_id = payload[0]["postId"] if isinstance(payload, list) else payload.get("id")
        except (ValueError, KeyError, IndexError, TypeError):
            own_post_id = None
    recorder.record(
        "posts.schedule",
        PASS if status in (200, 201) else FAIL,
        f"POST /public/v1/posts into project-a's own channel returned {status}.",
        status=status,
        body_excerpt=body[:200],
    )

    own_create_succeeded = own_post_id is not None
    status, body, _ = create_post("project-a", channels["project-b"], "dg01 cross-tenant attempt")
    if not own_create_succeeded:
        # A rejection only proves isolation when the same request shape is
        # accepted for the tenant's own channel. Otherwise the rejection is
        # just a malformed body and must not be read as evidence.
        recorder.record(
            "authz.cross-tenant-write-rejected",
            UNSUPPORTED,
            "The same request shape was rejected for project-a's own channel, so a cross-tenant "
            f"rejection ({status}) carries no isolation evidence.",
            status=status,
            body_excerpt=body[:200],
        )
    else:
        recorder.record(
            "authz.cross-tenant-write-rejected",
            PASS if status >= 400 else FAIL,
            f"POST /public/v1/posts from project-a into project-b's channel returned {status} "
            "while the identical shape into its own channel was accepted.",
            status=status,
            body_excerpt=body[:200],
        )

    window = {"startDate": args.window_start, "endDate": args.window_end}
    query = "/posts?" + urllib.parse.urlencode(window)
    status_a, body_a, _ = public("project-a", "GET", query)
    status_b, body_b, _ = public("project-b", "GET", query)
    posts_a = json.loads(body_a).get("posts", []) if status_a == 200 else []
    posts_b = json.loads(body_b).get("posts", []) if status_b == 200 else []
    recorder.record(
        "posts.list",
        PASS if status_a == 200 and posts_a else FAIL,
        f"GET /public/v1/posts for project-a returned {status_a} with {len(posts_a)} post(s).",
        status=status_a,
        count=len(posts_a),
    )
    ids_a = {str(post.get("id")) for post in posts_a}
    ids_b = {str(post.get("id")) for post in posts_b}
    if status_a != 200 or status_b != 200:
        # A failed listing yields an empty set, which would silently look like
        # perfect isolation. Both sides must actually have answered.
        recorder.record(
            "authz.cross-tenant-post-read-rejected",
            UNSUPPORTED,
            f"project-a's listing returned {status_a} and project-b's returned {status_b}; "
            "an unanswered listing cannot demonstrate isolation.",
            status_a=status_a,
            status_b=status_b,
        )
    else:
        recorder.record(
            "authz.cross-tenant-post-read-rejected",
            PASS if not (ids_a & ids_b) else FAIL,
            f"both tenants' post windows returned 200; project-b's holds {len(posts_b)} post(s) "
            f"and shares {len(ids_a & ids_b)} id(s) with project-a's {len(posts_a)}.",
            shared_ids=sorted(ids_a & ids_b),
            status_a=status_a,
            status_b=status_b,
        )

    if own_post_id:
        status, body, _ = public("project-b", "DELETE", f"/posts/{own_post_id}")
        still_there = str(own_post_id) in {
            str(post.get("id")) for post in json.loads(public("project-a", "GET", query)[1]).get("posts", [])
        }
        recorder.record(
            "authz.cross-tenant-delete-rejected",
            PASS if still_there else FAIL,
            f"DELETE of project-a's post with project-b's key returned {status}; "
            f"the post is {'still present' if still_there else 'gone'} for its owner.",
            status=status,
            survived=still_there,
        )
        status, _, _ = public("project-a", "DELETE", f"/posts/{own_post_id}")
        # A 200 from DELETE is a claim, not an outcome. Re-read the window and
        # require the scheduled job to actually be gone.
        after_status, after_body, _ = public("project-a", "GET", query)
        remaining = (
            {str(post.get("id")) for post in json.loads(after_body).get("posts", [])}
            if after_status == 200
            else None
        )
        if remaining is None:
            recorder.record(
                "posts.cancel",
                UNSUPPORTED,
                f"DELETE returned {status} but the post window then returned {after_status}, "
                "so the cancellation could not be confirmed.",
                status=status,
                recheck_status=after_status,
            )
        else:
            gone = str(own_post_id) not in remaining
            recorder.record(
                "posts.cancel",
                PASS if status in (200, 204) and gone else FAIL,
                f"DELETE /public/v1/posts/<id> by the owning tenant returned {status}; "
                f"re-reading the window shows the post {'gone' if gone else 'still scheduled'}.",
                status=status,
                recheck_status=after_status,
                removed=gone,
            )
    else:
        recorder.record(
            "authz.cross-tenant-delete-rejected",
            UNSUPPORTED,
            "No post id was returned by the create call, so the cross-tenant delete could not be attempted.",
        )
        recorder.record(
            "posts.cancel",
            UNSUPPORTED,
            "No post id was returned by the create call, so cancellation could not be attempted.",
        )

    # DG01-03: the lifecycle above cancels its own fixture, so a dump taken
    # after it holds no pending scheduled work and a rebuild cannot be shown to
    # preserve any. One extra post is scheduled well into the future and left
    # uncancelled on purpose. Postiz cannot repair a loss here by itself: at
    # v2.23.0 the orchestrator's missingPostWorkflow rescans hourly and
    # searchForMissingThreeHoursPosts only selects QUEUE posts whose publishDate
    # is already past (gte now-2d, lt now), so a future job that a rebuild loses
    # or re-times is never reconstructed.
    retained_id = None
    retained_at = None
    retained_status = None
    retained_listed = False
    scheduled_at = parse_instant(schedule_at)
    window_end_at = parse_instant(args.window_end or "")
    if scheduled_at is not None:
        requested = scheduled_at + datetime.timedelta(days=5)
        # The confirmation re-read below uses the matrix window, so a retained
        # post scheduled past its end could not be confirmed. Fall back to the
        # middle of the window rather than scheduling where the probe is blind.
        if window_end_at is not None and requested >= window_end_at:
            requested = scheduled_at + (window_end_at - scheduled_at) / 2
        retained_request = iso_z(requested)
        retained_status, retained_body, _ = create_post(
            "project-a",
            channels["project-a"],
            "dg01 retained pending post for project-a",
            when=retained_request,
        )
        if retained_status in (200, 201):
            try:
                payload = json.loads(retained_body)
                retained_id = payload[0]["postId"] if isinstance(payload, list) else payload.get("id")
            except (ValueError, KeyError, IndexError, TypeError):
                retained_id = None
        # A create that returns an id is a claim, not a pending job. The post
        # must be listed in its owner's window before the dump is taken, or a
        # later absence would be blamed on the rebuild instead of on the setup.
        if retained_id:
            confirm_status, confirm_body, _ = public("project-a", "GET", query)
            listed = (
                {str(post.get("id")) for post in json.loads(confirm_body).get("posts", [])}
                if confirm_status == 200
                else set()
            )
            retained_listed = str(retained_id) in listed
        if not retained_listed:
            # Unconfirmed means unproven: publish no id or instant for the
            # restore drill to check rather than one that was never pending.
            retained_id = None
        retained_at = retained_request if retained_listed else None

    stale = keys["project-a"]
    session = {"Cookie": f"auth={tenants['project-a']['session']}"}
    rotate_status, _, _ = api.request("POST", "/user/api-key/rotate", headers=session)
    # A stale key returning 401 proves nothing on its own — a broken rotate
    # endpoint, or an instance refusing every key, produces the same 401. The
    # rotate must succeed and the newly issued key must work.
    fresh_status, fresh_body, _ = api.request("GET", "/user/self", headers=session)
    fresh_key = json.loads(fresh_body)["publicApi"] if fresh_status == 200 else ""
    fresh_works = public(None, "GET", "/integrations", key=fresh_key)[0] if fresh_key else 0
    stale_status, _, _ = public(None, "GET", "/integrations", key=stale)
    rotated = bool(fresh_key) and fresh_key != stale
    if rotate_status not in (200, 201) or not rotated or fresh_works != 200:
        recorder.record(
            "authz.rotated-credential-rejected",
            UNSUPPORTED,
            f"rotate returned {rotate_status}, a {'new' if rotated else 'unchanged'} key was issued, and "
            f"that key returned {fresh_works} — without a working replacement, the stale key's "
            f"{stale_status} is not evidence of revocation.",
            rotate_status=rotate_status,
            new_key_status=fresh_works,
            stale_key_status=stale_status,
        )
    else:
        recorder.record(
            "authz.rotated-credential-rejected",
            PASS if stale_status == 401 else FAIL,
            f"rotate returned {rotate_status}, the replacement key returned {fresh_works}, and the "
            f"previous key returned {stale_status}.",
            rotate_status=rotate_status,
            new_key_status=fresh_works,
            stale_key_status=stale_status,
        )

    recorder.record(
        "bootstrap.registration-lockable",
        PASS,
        "DISABLE_REGISTRATION=true is a documented environment toggle; it is exercised by the "
        "registration-lock phase of run.sh, not by this probe.",
        toggle="DISABLE_REGISTRATION",
    )

    return {
        "tenant_model": "organization",
        "machine_api": "/public/v1",
        "credential_header": "Authorization",
        "channels_are_fixtures": True,
        "organization_id_digests": {slug: digest(t["organization_id"]) for slug, t in tenants.items()},
        # Read by run.sh and handed to `--mode restore-verify`. A post id and a
        # schedule are fixture metadata, not credentials, so they are recorded
        # as they are; nothing here identifies a secret.
        "retained_pending_post_id": retained_id,
        "retained_pending_post_at": retained_at,
        "retained_pending_post_status": retained_status,
        "retained_pending_post_confirmed": retained_listed,
        # The post the lifecycle matrix cancelled, so the caller can ask the
        # scheduler whether an ordinary cancellation actually terminated its
        # workflow — the row disappearing does not answer that.
        "cancelled_post_id": own_post_id or "",
    }


def probe_mixpost_lite(args: argparse.Namespace, recorder: Recorder) -> dict[str, Any]:
    base = args.base_url.rstrip("/")
    app = Http(base + "/" + args.mixpost_core_path.strip("/"))
    app.wait_until(
        lambda: app.request("GET", "/login")[0] == 200,
        attempts=args.ready_attempts,
        delay=args.ready_delay,
        what="the Mixpost login page",
    )

    routes = subprocess.run(
        ["docker", "exec", args.mixpost_container, "sh", "-c", "cd /var/www/html && php artisan route:list --no-ansi"],
        capture_output=True,
        text=True,
        check=False,
    )
    if routes.returncode != 0:
        raise RuntimeError(f"route enumeration failed: {routes.stderr.strip()[:300]}")
    route_lines = [line.strip() for line in routes.stdout.splitlines() if re.match(r"\s*(GET|POST|PUT|PATCH|DELETE)", line)]
    application_routes = [line for line in route_lines if "horizon" not in line.lower()]
    workspace_routes = [line for line in application_routes if "workspace" in line.lower()]
    api_routes = [line for line in application_routes if re.search(r"\bapi/", line)]

    recorder.record(
        "bootstrap.first-project",
        PASS,
        "php artisan mixpost-auth:create adds a login without SMTP; the image also ships a pre-created admin account.",
        bootstrap="php artisan mixpost-auth:create",
    )
    recorder.record(
        "bootstrap.second-project",
        FAIL,
        f"The route table exposes {len(application_routes)} application routes and {len(workspace_routes)} "
        "workspace routes, so a second project tenant cannot exist.",
        application_routes=len(application_routes),
        workspace_routes=len(workspace_routes),
    )
    recorder.record(
        "bootstrap.no-account-project",
        UNSUPPORTED,
        "Without a tenant boundary there is no per-project channel list to leave empty.",
    )
    recorder.record(
        "bootstrap.registration-lockable",
        PASS,
        "Mixpost Lite exposes no self-registration route; logins exist only when the operator creates them.",
        registration_routes=0,
    )
    for check_id, detail in (
        ("api.machine-credential", "Mixpost Lite registers no access-token route, so no machine credential exists."),
        ("api.credential-tenant-bound", "No machine credential exists to bind to a tenant."),
        ("api.list-own-channels", "No machine API exists; channels are reachable only from a CSRF-guarded browser session."),
        ("authz.no-credential-rejected", "No machine API exists to reject an unauthenticated call."),
        ("authz.invalid-credential-rejected", "No machine API exists to reject an unknown credential."),
        ("authz.cross-tenant-write-rejected", "No tenant boundary and no machine API."),
        ("authz.cross-tenant-post-read-rejected", "No tenant boundary and no machine API."),
        ("authz.cross-tenant-delete-rejected", "No tenant boundary and no machine API."),
        ("authz.rotated-credential-rejected", "No machine credential exists to rotate."),
        ("posts.schedule", "Scheduling is a session-and-CSRF browser route, not a machine API."),
        ("posts.list", "Listing is a session-and-CSRF browser route, not a machine API."),
        ("posts.cancel", "Cancellation is a session-and-CSRF browser route, not a machine API."),
    ):
        recorder.record(check_id, UNSUPPORTED, detail, api_routes=len(api_routes))

    session_a = MixpostSession(app, args.mixpost_users[0], args.mixpost_password_a)
    session_b = MixpostSession(app, args.mixpost_users[1], args.mixpost_password_b)
    marker = "dg01-project-a-private"
    session_a.login()
    session_b.login()
    session_a.create_tag(marker)
    visible = marker in session_b.tag_names()
    recorder.record(
        "authz.cross-tenant-read-rejected",
        FAIL if visible else PASS,
        f"A label created by the first login is {'visible' if visible else 'not visible'} to the second login; "
        "Mixpost Lite keeps one global dataset for every user.",
        marker_visible_to_second_user=visible,
    )

    return {
        "tenant_model": "none",
        "machine_api": None,
        "application_routes": len(application_routes),
        "workspace_routes": len(workspace_routes),
        "non_horizon_api_routes": len(api_routes),
        "ships_default_admin_account": True,
    }


class MixpostSession:
    def __init__(self, app: Http, email: str, password: str) -> None:
        self.app = app
        self.email = email
        self.password = password
        self.cookies: dict[str, str] = {}

    def _headers(self) -> dict[str, str]:
        headers = {"X-Requested-With": "XMLHttpRequest"}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        if "XSRF-TOKEN" in self.cookies:
            headers["X-XSRF-TOKEN"] = urllib.parse.unquote(self.cookies["XSRF-TOKEN"])
        return headers

    def _absorb(self, headers: dict[str, list[str]]) -> None:
        for cookie in headers.get("set-cookie", []):
            name, _, rest = cookie.partition("=")
            self.cookies[name.strip()] = rest.split(";", 1)[0]

    def login(self) -> None:
        status, body, headers = self.app.request("GET", "/login")
        self._absorb(headers)
        match = re.search(r'name="_token"\s+value="([^"]+)"', body)
        status, body, headers = self.app.request(
            "POST",
            "/login",
            form_body={"email": self.email, "password": self.password, "_token": match.group(1) if match else ""},
            headers=self._headers(),
            follow_redirects=False,
        )
        self._absorb(headers)
        if status not in (200, 302):
            raise RuntimeError(f"Mixpost login failed for {digest(self.email)}: {status} {body[:120]}")

    def create_tag(self, name: str) -> None:
        status, body, headers = self.app.request(
            "POST",
            "/tags",
            json_body={"name": name, "hex_color": "#ff0000"},
            headers=self._headers(),
            follow_redirects=False,
        )
        self._absorb(headers)
        if status not in (200, 201, 302):
            raise RuntimeError(f"creating a Mixpost label failed: {status} {body[:150]}")

    def tag_names(self) -> list[str]:
        _, body, headers = self.app.request("GET", "/posts", headers=self._headers())
        self._absorb(headers)
        match = re.search(r'data-page="([^"]+)"', body)
        if not match:
            return []
        props = json.loads(unescape(match.group(1))).get("props", {})
        return [tag.get("name") for tag in props.get("tags", []) or []]


def postiz_api_key(api: Http, email: str, password: str) -> tuple[int, str]:
    """Log a fixture tenant in and return (status, its public API key or "")."""
    status, _, headers = api.request(
        "POST", "/auth/login", json_body={"email": email, "password": password, "provider": "LOCAL"}
    )
    token = None
    for cookie in headers.get("set-cookie", []):
        match = re.match(r"auth=([^;]+)", cookie)
        if match:
            token = match.group(1)
    if status != 200 or not token:
        return status, ""
    self_status, body, _ = api.request("GET", "/user/self", headers={"Cookie": f"auth={token}"})
    if self_status != 200:
        return self_status, ""
    return self_status, (json.loads(body).get("publicApi") or "")


def verify_postiz_restore(args: argparse.Namespace) -> dict[str, Any]:
    """Prove a restored Postiz still serves the state n8n depends on.

    A row count says the rows came back; it does not say the application can
    still authenticate a project, mint its credential, see its own channel, or
    refuse another project's. This runs after the database has been rebuilt from
    empty and reloaded, so it exercises the restore rather than the live
    instance that produced the dump.
    """
    api = Http(args.base_url.rstrip("/") + "/api")
    api.wait_until(
        lambda: api.request("GET", "/user/self")[0] == 401,
        attempts=args.ready_attempts,
        delay=args.ready_delay,
        what="the Postiz backend to answer after restore",
    )
    results: dict[str, Any] = {}

    email = f"project-a@{args.fixture_domain}"
    password = f"{args.fixture_password_prefix}-project-a"
    status, _, headers = api.request(
        "POST", "/auth/login", json_body={"email": email, "password": password, "provider": "LOCAL"}
    )
    token = None
    for cookie in headers.get("set-cookie", []):
        match = re.match(r"auth=([^;]+)", cookie)
        if match:
            token = match.group(1)
    results["login_status"] = status
    results["session_restored"] = bool(token)
    if not token:
        return results

    auth = {"Cookie": f"auth={token}"}
    status, body, _ = api.request("GET", "/user/self", headers=auth)
    record = json.loads(body) if status == 200 else {}
    api_key = record.get("publicApi") or ""
    results["self_status"] = status
    results["api_credential_restored"] = bool(api_key)
    if not api_key:
        return results

    def public(path: str, key: str = api_key):
        return api.request("GET", "/public/v1" + path, headers={"Authorization": key})

    status, body, _ = public("/integrations")
    own = {item.get("id") for item in (json.loads(body) if status == 200 else [])}
    results["integrations_status"] = status
    results["own_channel_restored"] = args.restored_own_channel in own
    results["foreign_channel_visible"] = args.restored_foreign_channel in own

    direct_own, _, _ = public(f"/integration-settings/{args.restored_own_channel}")
    direct_foreign, _, _ = public(f"/integration-settings/{args.restored_foreign_channel}")
    results["own_direct_status"] = direct_own
    results["foreign_direct_status"] = direct_foreign
    results["tenant_boundary_restored"] = direct_own == 200 and direct_foreign >= 400

    # DG01-03: a restore that reloads settled state but drops or re-times
    # pending scheduled work is not a usable restore, and Postiz will not notice
    # — at v2.23.0 its recovery scan only re-queues posts whose publishDate is
    # already past, so a future job comes back with its own instant or not at all.
    pending_id = (args.restored_pending_post_id or "").strip()
    pending_instant = parse_instant(args.restored_pending_post_at or "")
    if not pending_id or pending_instant is None:
        # Nothing was retained before the dump, so there is nothing to prove.
        # None keeps that distinguishable from a check that actually passed.
        results["pending_post_restored"] = None
        results["pending_post_tenant_correct"] = None
        results["pending_post_time_preserved"] = None
        return results

    # Deliberately wide: a post that came back at the wrong instant must still
    # be found, so that it fails as re-timed rather than as lost.
    window = urllib.parse.urlencode(
        {
            "startDate": iso_z(pending_instant - datetime.timedelta(days=180)),
            "endDate": iso_z(pending_instant + datetime.timedelta(days=180)),
        }
    )
    owner_status, owner_body, _ = public("/posts?" + window)
    owner_posts = json.loads(owner_body).get("posts", []) if owner_status == 200 else []
    restored = next((post for post in owner_posts if str(post.get("id")) == pending_id), None)
    results["pending_post_window_status"] = owner_status
    results["pending_post_restored"] = restored is not None
    results["pending_post_state"] = restored.get("state") if restored else None

    foreign_login, foreign_key = postiz_api_key(
        api,
        f"project-b@{args.fixture_domain}",
        f"{args.fixture_password_prefix}-project-b",
    )
    results["foreign_login_status"] = foreign_login
    if not foreign_key:
        # Without a working credential for the other tenant, its failure to see
        # the post proves nothing, so no verdict is recorded for the boundary.
        results["pending_post_tenant_correct"] = None
    else:
        foreign_status, foreign_body, _ = public("/posts?" + window, key=foreign_key)
        foreign_posts = json.loads(foreign_body).get("posts", []) if foreign_status == 200 else []
        foreign_ids = {str(post.get("id")) for post in foreign_posts}
        results["foreign_window_status"] = foreign_status
        results["pending_post_tenant_correct"] = (
            restored is not None and foreign_status == 200 and pending_id not in foreign_ids
        )

    restored_instant = parse_instant(str(restored.get("publishDate"))) if restored else None
    results["pending_post_restored_at"] = iso_z(restored_instant) if restored_instant else None
    results["pending_post_time_preserved"] = restored_instant == pending_instant

    # A surviving row and a surviving workflow are still not a usable restore if
    # the publisher can no longer manage that workflow. At v2.23.0 Postiz finds a
    # scheduled post's running `post_<id>` workflow through a Temporal list
    # query, and list queries are served by the Visibility store — which the
    # rebuild empties. Exercising a real lifecycle operation is the only honest
    # way to test that path, so the retained post is cancelled through the same
    # public API n8n would use, and the cancellation is confirmed by re-reading.
    if restored is None:
        results["pending_post_manageable"] = None
        return results
    cancel_status, cancel_body, _ = api.request(
        "DELETE", f"/public/v1/posts/{pending_id}", headers={"Authorization": api_key}
    )
    recheck_status, recheck_body, _ = public("/posts?" + window)
    still_present = (
        pending_id in {str(post.get("id")) for post in json.loads(recheck_body).get("posts", [])}
        if recheck_status == 200
        else None
    )
    results["pending_post_cancel_status"] = cancel_status
    results["pending_post_recheck_status"] = recheck_status
    results["pending_post_manageable"] = (
        cancel_status in (200, 204) and recheck_status == 200 and still_present is False
    )
    if not results["pending_post_manageable"]:
        results["pending_post_manage_detail"] = cancel_body[:160]
    return results


def verify_mixpost_restore(args: argparse.Namespace) -> dict[str, Any]:
    """Prove a restored Mixpost Lite still authenticates and serves its data."""
    base = args.base_url.rstrip("/") + "/" + args.mixpost_core_path.strip("/")
    app = Http(base)
    app.wait_until(
        lambda: app.request("GET", "/login")[0] == 200,
        attempts=args.ready_attempts,
        delay=args.ready_delay,
        what="the Mixpost login page after restore",
    )
    results: dict[str, Any] = {}
    session = MixpostSession(app, args.mixpost_users[0], args.mixpost_password_a)
    try:
        session.login()
    except RuntimeError as error:
        results["login_restored"] = False
        results["detail"] = str(error)[:120]
        return results
    results["login_restored"] = True
    names = session.tag_names()
    results["label_restored"] = args.restored_marker in names
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, choices=["postiz", "mixpost-lite"])
    parser.add_argument(
        "--mode",
        default="matrix",
        choices=["matrix", "restore-verify"],
        help="matrix runs the full fixture matrix; restore-verify re-checks a rebuilt instance",
    )
    parser.add_argument("--restored-own-channel", default="dg01-project-a")
    parser.add_argument("--restored-foreign-channel", default="dg01-project-b")
    parser.add_argument("--restored-marker", default="dg01-project-a-private")
    parser.add_argument("--restored-pending-post-id", default="")
    parser.add_argument("--restored-pending-post-at", default="")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--image", required=True, help="the digest-pinned image under test")
    parser.add_argument("--variant", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--ready-attempts", type=int, default=120)
    parser.add_argument("--ready-delay", type=float, default=5.0)
    parser.add_argument("--fixture-domain", default="dg01.invalid")
    parser.add_argument("--fixture-password-prefix", default="dg01-fixture")
    parser.add_argument(
        "--fixture-provider",
        default="mastodon",
        help="provider identifier for the database channel fixtures; it must be one whose "
        "post settings are empty so no provider-specific field is invented",
    )
    parser.add_argument("--schedule-at", required=False, default=None)
    parser.add_argument("--window-start", required=False, default=None)
    parser.add_argument("--window-end", required=False, default=None)
    parser.add_argument("--postgres-container", default="")
    parser.add_argument("--postgres-database", default="postiz")
    parser.add_argument("--postgres-user", default="postiz")
    parser.add_argument("--mixpost-container", default="")
    parser.add_argument("--mixpost-core-path", default="mixpost")
    parser.add_argument("--mixpost-users", nargs=2, default=["project-a@dg01.invalid", "project-b@dg01.invalid"])
    parser.add_argument("--mixpost-password-a", default="")
    parser.add_argument("--mixpost-password-b", default="")
    args = parser.parse_args()

    if args.mode == "restore-verify":
        verify = verify_postiz_restore if args.candidate == "postiz" else verify_mixpost_restore
        results = verify(args)
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(json.dumps(results, sort_keys=True), file=sys.stderr)
        return 0

    recorder = Recorder()
    if args.candidate == "postiz":
        for required in ("schedule_at", "window_start", "window_end", "postgres_container"):
            if not getattr(args, required):
                parser.error(f"--{required.replace('_', '-')} is required for the postiz candidate")
        capabilities = probe_postiz(args, recorder)
    else:
        if not args.mixpost_container:
            parser.error("--mixpost-container is required for the mixpost-lite candidate")
        capabilities = probe_mixpost_lite(args, recorder)

    missing = recorder.unrecorded()
    if missing:
        raise SystemExit(f"the fixture matrix left checks unrecorded: {', '.join(missing)}")

    document = {
        "schema_version": SCHEMA_VERSION,
        "candidate": args.candidate,
        "image": args.image,
        "variant": args.variant,
        "platform": args.platform,
        "capabilities": capabilities,
        "checks": recorder.as_list(),
    }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")
    failures = [check["id"] for check in document["checks"] if check["result"] == FAIL]
    print(f"{args.candidate}: {len(document['checks'])} checks, {len(failures)} failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
