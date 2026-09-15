"""Real local restic fixtures never contact a provider or mutate a host."""

from datetime import datetime, timezone
import importlib.util
import io
import json
import os
import runpy
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time

import pytest

ROOT = Path(__file__).resolve().parents[3]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


b = module("backup_foundation", "infra/roles/restic/files/backup.py")
escrow = module("source_escrow_foundation", "scripts/lib/source_escrow.py")
operator = module("backup_operator_foundation", "scripts/lib/backup_operator.py")


@pytest.mark.parametrize("args", [
    [],
    ["/tmp/other.img", "/var/lib/dholbeat/restic/application", "-o", "nosuid,nodev,noexec"],
    ["/var/lib/dholbeat/restic/application.img", "/tmp/other", "-o", "nosuid,nodev,noexec"],
    ["/var/lib/dholbeat/restic/application.img", "/var/lib/dholbeat/restic/application", "-o", "ro"],
    ["/var/lib/dholbeat/restic/application.img", "/var/lib/dholbeat/restic/application", "-o", "suid,exec"],
])
def test_scratch_mount_helper_rejects_other_paths_and_unsafe_options(args, monkeypatch):
    helper = runpy.run_path(str(ROOT / "infra/roles/restic/files/mount.dholbeat-fuse2fs"))
    monkeypatch.setattr(os, "execv", lambda *args: pytest.fail("rejected mount executed"))
    with pytest.raises(SystemExit, match="Refusing"):
        helper["main"](args)


def test_scratch_mount_helper_enforces_container_permissions_and_disk_backing(monkeypatch):
    helper = runpy.run_path(str(ROOT / "infra/roles/restic/files/mount.dholbeat-fuse2fs"))
    executed = []
    monkeypatch.setattr(os, "execv", lambda path, args: executed.append((path, args)))
    helper["main"]([helper["IMAGE"], helper["TARGET"], "-o", "rw,nosuid,nodev,noexec"])
    assert executed == [("/usr/bin/fuse2fs", ["fuse2fs", "-o",
        "rw,allow_other,default_permissions,nosuid,nodev,noexec", helper["IMAGE"], helper["TARGET"]])]


def test_readonly_first_install_plan_needs_no_download_directory_or_timer_units(tmp_path):
    """Exercise real Ansible check mode against an absent installation."""
    import yaml

    tasks = yaml.safe_load((ROOT / "infra/roles/restic/tasks/main.yml").read_text())
    install = next(t for t in tasks if "block" in t)
    inspect = next(t for t in tasks if t["name"] == "Inspect timer units before planning their first installation")
    timers = next(t for t in tasks if t["name"] == "Start only the founder-approved verified backup timers")
    # A named disposable directory guarantees absent units even on developers'
    # machines. No task installs a package, starts a service, or contacts R2.
    inspect["ansible.builtin.stat"]["path"] = str(tmp_path / "absent") + "/{{ item }}"
    playbook = tmp_path / "readonly-install.yml"
    playbook.write_text(yaml.safe_dump([{
        "name": "Check absent backup foundation without mutation", "hosts": "all",
        "gather_facts": False,
        "vars": {"ansible_remote_tmp": str(tmp_path / "ansible-remote"),
                 "restic_current_version": {"rc": 1, "stdout": ""},
                 "restic_timer_enabled": False},
        "tasks": [install, inspect, timers],
    }]))
    result = subprocess.run([
        "ansible-playbook", "--check", "--diff", "--inventory", "localhost,",
        "--connection", "local", str(playbook),
    ], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "failed=0" in result.stdout
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("worktree", [False, True])
def test_backup_identity_accepts_home_ssh_from_primary_and_worktree(tmp_path, monkeypatch, worktree):
    home = tmp_path / "home"
    checkout = home / "Projects/dholbeat"
    root = checkout / ".worktrees/publish-routing-backups" if worktree else checkout
    root.mkdir(parents=True)
    key = home / ".ssh/publish-1"
    key.parent.mkdir()
    key.write_text("credential-free-key-fixture")
    key.chmod(0o600)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(operator, "ROOT", root)
    assert operator.private_identity("~/.ssh/publish-1") == key


@pytest.mark.parametrize("kind", ["checkout", "other-git", "linked-worktree", "bare-git", "app", "symlink", "mode"])
def test_backup_identity_rejects_checkout_app_symlink_and_insecure_keys(tmp_path, monkeypatch, kind):
    checkout = tmp_path / "repo"
    checkout.mkdir()
    monkeypatch.setattr(operator, "ROOT", checkout)
    directory = checkout if kind == "checkout" else tmp_path / ("github-agent-apps" if kind == "app" else "keys")
    directory.mkdir(exist_ok=True)
    key = directory / "fixture-key"
    key.write_text("credential-free-key-fixture")
    key.chmod(0o644 if kind == "mode" else 0o600)
    if kind == "other-git":
        (directory / ".git").mkdir()
    if kind == "linked-worktree":
        (directory / ".git").write_text("gitdir: /outside/shared/repo\n")
    if kind == "bare-git":
        (directory / "HEAD").write_text("ref: refs/heads/develop\n")
        (directory / "config").write_text("[core]\n bare = true\n")
        (directory / "objects").mkdir()
    if kind == "symlink":
        link = directory / "link"
        link.symlink_to(key)
        key = link
    with pytest.raises(ValueError):
        operator.private_identity(str(key))


@pytest.fixture
def document(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    return {"schema_version": 1, "host_id": "publish-1", "account_id": "7512591000a1e57593bc784dad59bfc0",
        "repository": "s3:https://7512591000a1e57593bc784dad59bfc0.r2.cloudflarestorage.com/dholbeat-publisher-backups/state",
        "repository_id_file": str(tmp_path / "repository-id"), "staging": str(stage),
        "restore_root": str(tmp_path / "restores"), "status": str(tmp_path / "status.json"),
        "lock": str(tmp_path / "backup.lock"), "retained_paths": ["/etc/dholbeat-release"],
        "publisher_staging": str(tmp_path / 'application'), "publisher_enabled": False}


@pytest.fixture
def restic(document, tmp_path, monkeypatch):
    # Keep fixture disk tiny; production always checks the actual eight-GB headroom.
    monkeypatch.setattr(b, "capacity", lambda *args: None)
    value = b.Restic(document)
    value.env.update({"RESTIC_REPOSITORY": str(tmp_path / "local-restic"),
        "RESTIC_PASSWORD": "credential-free-fixture-backup-root"})
    return value


def test_real_restic_encrypted_dump_restore_and_retention(document, restic, tmp_path, monkeypatch):
    database = sqlite3.connect(":memory:")
    database.executescript("create table fixture(id integer primary key, value text); insert into fixture values(1,'retained');")
    dump = tmp_path / "fixture.sql"
    dump.write_text("\n".join(database.iterdump()))
    document["retained_paths"] = [str(dump)]
    restic.initialize()
    first = b.backup(document, restic)
    assert len(first["snapshot_id"]) == 64
    assert not list(Path(document["staging"]).iterdir())
    assert b.status(document)["healthy"]
    original_extract = b.extract

    def prove(path, destination):
        original_extract(path, destination)
        recovered = sqlite3.connect(":memory:")
        recovered.executescript((destination / "retained/0").read_text())
        assert recovered.execute("select value from fixture").fetchall() == [("retained",)]
        assert not any(destination.rglob("*.sqlite"))
        assert not any(destination.rglob("cache*"))

    monkeypatch.setattr(b, "extract", prove)
    result = b.restore(document, restic, first["snapshot_id"], "dholbeat-restore-fixture", 5200)
    assert result["cleanup"]
    assert not list(Path(document["restore_root"]).iterdir())
    second = b.backup(document, restic)
    snapshots = json.loads(restic.command("snapshots", "--json"))
    assert 1 <= len(snapshots) <= 2
    assert second["snapshot_id"] in {v["id"] for v in snapshots}
    assert {tuple(v['paths']) for v in snapshots} == {('/state.tar',)}


def test_repository_identity_and_wrong_password_fail(document, restic):
    restic.initialize()
    Path(document["repository_id_file"]).write_text("a" * 64)
    with pytest.raises(b.BackupError):
        restic.verify()
    restic.env["RESTIC_PASSWORD"] = "wrong-fixture-root"
    with pytest.raises(b.BackupError):
        restic.identity()


def test_unpinned_existing_repository_is_not_adopted(document, restic):
    restic.initialize()
    Path(document["repository_id_file"]).unlink()
    with pytest.raises(b.BackupError, match="absent"):
        restic.initialize()


@pytest.mark.parametrize("mutation", [
    {"host_id": "core-1"}, {"account_id": "f" * 32},
    {"repository": "s3:https://7512591000a1e57593bc784dad59bfc0.r2.cloudflarestorage.com/dholbeat-publisher-media/state"},
    {"retained_paths": ["/var/lib/docker/volumes/live-postgres"]}, {"unexpected": True},
])
def test_production_config_rejects_wrong_host_media_and_live_db(document, tmp_path, mutation):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**document, **mutation}))
    with pytest.raises(b.BackupError):
        b.config(path)


def test_failed_dump_does_not_capture_partial_state(document, restic, monkeypatch):
    restic.initialize()
    document["publisher_enabled"] = True
    document["retained_paths"] = []

    application = Path(document['publisher_staging'])
    application.mkdir()
    monkeypatch.setattr(b, 'publisher_area', lambda doc: application)
    original_run = b.run
    calls = []

    def fail(argv, **kwargs):
        if argv[0] == '/usr/local/sbin/dholbeat-publisher-state':
            calls.append(argv)
            partial = application / argv[-1]
            partial.mkdir()
            (partial / 'incomplete.sql').write_text('partial')
            raise b.BackupError("failed consistent dump")
        return original_run(argv, **kwargs)

    monkeypatch.setattr(b, "run", fail)
    with pytest.raises(b.BackupError):
        b.backup(document, restic)
    assert not list(Path(document["staging"]).iterdir())
    assert not Path(document["status"]).exists()
    assert len(calls) == 1
    assert not list(application.iterdir())
    assert json.loads(restic.command('snapshots', '--json')) == []


def test_publisher_dump_stream_and_disposable_staging_are_separate(document, restic, monkeypatch):
    restic.initialize()
    application = Path(document['publisher_staging'])
    application.mkdir()
    document.update(publisher_enabled=True, retained_paths=[])
    monkeypatch.setattr(b, 'publisher_area', lambda doc: application)
    original_run = b.run
    calls = []

    def adapter(argv, **kwargs):
        if argv[0] != '/usr/local/sbin/dholbeat-publisher-state':
            return original_run(argv, **kwargs)
        calls.append(argv)
        if 'backup' in argv:
            dump = application / argv[-1]
            dump.mkdir()
            (dump / 'fixture.sql').write_text('consistent-dump')
        else:
            restored = Path(argv[2]) / argv[argv.index('--backup-id') + 1]
            assert (restored / 'fixture.sql').read_text() == 'consistent-dump'
            assert kwargs['env']['PUBLISHER_BACKUP_STAGING'] == argv[2]
            assert Path(argv[2]) != application
        return b'{}'

    monkeypatch.setattr(b, 'run', adapter)
    monkeypatch.setattr(b.os, 'chown', lambda *args: None)
    result = b.backup(document, restic)
    assert not list(application.iterdir())
    assert b.restore(document, restic, result['snapshot_id'], 'dholbeat-restore-adapter', 5200)['application_restore_verified']
    assert len(calls) == 2
    assert not list(Path(document['restore_root']).iterdir())


def test_lock_contention_covers_publisher_and_backup(tmp_path):
    with b.lock(tmp_path / "lock"):
        with pytest.raises(b.BackupError, match="running"):
            with b.lock(tmp_path / "lock"):
                pass


def test_full_disk_and_size_quota_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(100, 99, 1))
    with pytest.raises(b.BackupError):
        b.capacity(tmp_path)
    with pytest.raises(b.BackupError):
        b.capacity(tmp_path, 2 * b.MAX_ARCHIVE + 1)


@pytest.mark.parametrize("kind", ["traversal", "symlink", "duplicate", "size"])
def test_archive_corruption_cannot_escape_disposable_target(tmp_path, kind):
    path = tmp_path / "bad.tar"
    with tarfile.open(path, "w") as archive:
        member = tarfile.TarInfo("../production" if kind == "traversal" else "file")
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/shadow"
        if kind == "size":
            member.size = b.MAX_ARCHIVE + 1
            # Header-only malformed huge member is enough to fail safely.
            archive.fileobj.write(member.tobuf())
        else:
            archive.addfile(member)
            if kind == "duplicate":
                archive.addfile(member)
    destination = tmp_path / "restore"
    destination.mkdir()
    with pytest.raises((b.BackupError, tarfile.ReadError)):
        b.extract(path, destination)
    assert not (tmp_path / "production").exists()


def test_missing_snapshot_and_production_name_are_rejected(document, restic):
    restic.initialize()
    with pytest.raises(b.BackupError):
        b.restore(document, restic, "a" * 64, "dholbeat-restore-missing", 5200)
    for name, port in (("production", 5200), ("dholbeat-restore-fixture", 5000)):
        with pytest.raises(b.BackupError):
            b.restore(document, restic, "a" * 64, name, port)


def test_stale_failed_future_and_oversized_status(document):
    good = {"host_id": "publish-1", "success_epoch": time.time(), "staging_bytes": 1, "last_attempt_failed": False}
    for bad in ({"success_epoch": 0}, {"success_epoch": time.time() + 100},
                {"staging_bytes": b.MAX_ARCHIVE + 1}, {"last_attempt_failed": True}, {"host_id": "core-1"}):
        b.atomic_json(document["status"], {**good, **bad})
        with pytest.raises(b.BackupError):
            b.status(document)


def snapshot(number, release):
    return {"id": format(number, "064x"), "time": f"2026-09-{number:02d}T00:00:00Z",
            "hostname": "dholbeat-source-escrow", "tags": ["source-escrow", "release:" + release]}


def test_source_escrow_retains_every_deployed_plus_two_superseded():
    values = [snapshot(i, f"infra-prod-20260913-{i}") for i in range(1, 7)]
    keep = escrow.retained_snapshots(values, {"core-1": "infra-prod-20260913-1", "publish-1": "infra-prod-20260913-2"})
    assert keep == {format(i, "064x") for i in (1, 2, 5, 6)}


def test_missing_deployed_root_prevents_source_pruning():
    with pytest.raises(ValueError):
        escrow.retained_snapshots([snapshot(1, "infra-prod-20260913-1")],
            {"core-1": None, "publish-1": "infra-prod-20260913-2"})
    with pytest.raises(ValueError):
        escrow.retained_snapshots([], {"publish-1": None})


def test_new_bundle_can_cover_an_older_deployed_tag():
    current = snapshot(3, 'infra-prod-20260913-3')
    current['tags'].append('contains-release:infra-prod-20260913-2')
    assert escrow.retained_snapshots([current], {'core-1': None, 'publish-1': 'infra-prod-20260913-2'}) == {current['id']}


def test_source_roots_cannot_be_public_media_or_sops_dependency(tmp_path):
    path = tmp_path / "roots"
    path.write_text("RESTIC_REPOSITORY=s3:https://" + "a" * 32 + ".r2.cloudflarestorage.com/dholbeat-publisher-media/source\n"
        "RESTIC_PASSWORD=fixture\nAWS_ACCESS_KEY_ID=fixture\nAWS_SECRET_ACCESS_KEY=fixture\nSOURCE_ESCROW_REPOSITORY_ID=" + "a" * 64 + "\n")
    with pytest.raises(ValueError):
        escrow.roots(path)


def test_source_roots_require_dedicated_controller_bucket(tmp_path):
    path = tmp_path / "roots"
    def write(bucket):
        path.write_text("RESTIC_REPOSITORY=s3:https://7512591000a1e57593bc784dad59bfc0.r2.cloudflarestorage.com/" + bucket + "/source\n"
            "RESTIC_PASSWORD=fixture\nAWS_ACCESS_KEY_ID=fixture\nAWS_SECRET_ACCESS_KEY=fixture\nSOURCE_ESCROW_REPOSITORY_ID=" + "a" * 64 + "\n")
    write("dholbeat-source-escrow")
    assert escrow.roots(path)["RESTIC_REPOSITORY"].endswith("/dholbeat-source-escrow/source")
    write("dholbeat-publisher-backups")
    with pytest.raises(ValueError, match="dedicated"):
        escrow.roots(path)


def test_installation_is_opt_in_and_core_backup_untouched():
    text = (ROOT / "infra/playbooks/publisher-boundaries.yml").read_text()
    assert "dholbeat_host_role == 'publisher'" in text
    assert "restic_enabled | default(false)" in text
    role = (ROOT / "infra/roles/restic/tasks/main.yml").read_text()
    assert "dholbeat_host_id == 'publish-1'" in role
    assert "wp07-publish1.yml" in role
    assert "core-1" not in role
