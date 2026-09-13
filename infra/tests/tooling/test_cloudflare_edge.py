import copy
import importlib.util
from pathlib import Path
import sys

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "tofu/cloudflare"
sys.path.insert(0, str(PACKAGE))
import edge
import webhook_proxy


def test_current_and_future_ingress_derive_from_one_manifest():
    docs = edge.documents()
    core = edge.render(*docs, "core-1")
    assert core["ingress"] == [
        {"hostname": "team.chayan.me", "service": "http://localhost:3100"},
        {"service": "http_status:404"},
    ]
    future = edge.render(*docs, "core-1", include_planned=True)
    assert len(future["ingress"]) == 4
    assert future["ingress"][-2]["hostname"] == "hooks.chayan.me"
    assert "path" in future["ingress"][-2]
    publisher = edge.render(*docs, "publish-1")
    assert publisher["ingress"] == [
        {"hostname": "publish.chayan.me", "service": "http://127.0.0.1:5000"},
        {"service": "http_status:404"},
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d[0]["routes"][0].update(host_id="publish-1"),
        lambda d: d[0]["routes"][0].update(origin="http://198.51.100.1:3100"),
        lambda d: d[0]["routes"][0].update(origin="http://127.0.0.1:3100/../private"),
        lambda d: d[0]["routes"][0].update(access="bypass"),
        lambda d: d[0]["routes"][0].update(hostname="alternate.chayan.me"),
        lambda d: d[0]["routes"][2].update(path="/"),
        lambda d: d[0]["routes"][2].update(methods=["GET", "POST"]),
        lambda d: d[0]["routes"][2].update(application_auth="none"),
        lambda d: d[0]["routes"][3].update(machine_path="/*"),
        lambda d: d[0]["tunnels"][1].update(
            credential_ref=d[0]["tunnels"][0]["credential_ref"]
        ),
        lambda d: d[0]["tunnels"][1].update(id=d[0]["tunnels"][0]["id"]),
        lambda d: d[0]["buckets"][0].update(public=True),
        lambda d: d[0]["buckets"][0].update(object_expiry_days=7),
        lambda d: d[0]["buckets"][2].update(object_expiry_days=None),
        lambda d: d[3].update(registrar="unknown"),
        lambda d: d[3]["delegation_evidence"].update(
            expected_nameservers=["wrong.test"]
        ),
        lambda d: d[3]["delegation_evidence"].update(recursion=True),
    ],
)
def test_unsafe_route_domain_bucket_and_credential_changes_fail(mutation):
    docs = copy.deepcopy(edge.documents())
    mutation(docs)
    with pytest.raises(edge.ContractError):
        edge.render(*docs, "core-1", include_planned=True)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/webhook/",
        "/webhook/../admin",
        "/webhook/x?admin=1",
        "/webhook/%2e%2e/admin",
        "/webhook/x%2fadmin",
        "//webhook/x",
        "/webhook-test/x",
    ],
)
def test_webhook_proxy_rejects_wrong_or_ambiguous_path(path):
    assert webhook_proxy.authorize("POST", path, "secret", "secret") == 404


@pytest.mark.parametrize(
    "method", ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]
)
def test_webhook_proxy_only_accepts_post(method):
    assert (
        webhook_proxy.authorize(method, "/webhook/approval", "secret", "secret") == 405
    )


def test_webhook_proxy_checks_application_token():
    assert webhook_proxy.authorize("POST", "/webhook/approval", "valid", "valid") == 200
    assert (
        webhook_proxy.authorize("POST", "/webhook/approval", "invalid", "valid") == 401
    )
    assert webhook_proxy.authorize("POST", "/webhook/approval", None, "valid") == 401
    assert webhook_proxy.authorize("POST", "/webhook/approval", "", "") == 401


@pytest.mark.parametrize(
    "mutation",
    [
        "shared-bucket-key",
        "missing-backup",
        "broad-service-token",
        "wrong-machine-path",
    ],
)
def test_complete_separate_bucket_and_machine_credentials(mutation):
    import copy

    docs = copy.deepcopy(edge.documents())
    manifest = docs[0]
    if mutation == "shared-bucket-key":
        manifest["buckets"][0]["credential_refs"] = manifest["buckets"][1][
            "credential_refs"
        ]
    elif mutation == "missing-backup":
        manifest["buckets"].pop(0)
    elif mutation == "broad-service-token":
        manifest["routes"][3]["machine_policy"]["allow_any_service_token"] = True
    else:
        manifest["routes"][3]["machine_policy"]["application_path"] = "/*"
    with pytest.raises(ValueError):
        edge.validate(*docs)


@pytest.mark.parametrize("malformed", [True, False])
def test_renderer_cli_suppresses_yaml_source_and_missing_file_diagnostics(
    tmp_path, malformed
):
    import shutil
    import subprocess
    import sys

    tree = tmp_path / "repo"
    package = tree / "infra/tofu/cloudflare"
    package.mkdir(parents=True)
    for filename in ["edge.py", "control_plane.py"]:
        shutil.copyfile(PACKAGE / filename, package / filename)
    if malformed:
        (package / "routes.yml").write_text("routes: [DO_NOT_ECHO_SOURCE_VALUE\n")
    result = subprocess.run(
        [sys.executable, str(package / "edge.py"), "--host", "core-1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stderr == "invalid edge declaration; no ingress rendered\n"
    assert "DO_NOT_ECHO_SOURCE_VALUE" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
