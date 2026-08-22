# Reproducible repository controller

`scripts/check` is the only local and CI validation entry point. It builds the
same checksum-locked controller on native `linux/amd64` and `linux/arm64`, then
runs every check with the repository mounted read-only, no network, no added
capabilities and a bounded temporary filesystem.

The default `exec` path remains network-isolated. A founder-approved disposable
SSH target uses the explicit `exec-ssh` path, which still mounts the repository
read-only, drops every capability, runs as the invoking user, copies only the
declared `.artifacts/` known-hosts file into an ephemeral home, and requires the
literal `--confirm disposable-host` guard. It never mounts an SSH agent or a
provider credential.

## Clean-checkout workflow

Prerequisites are Docker Engine with the buildx plugin and enough temporary
space for one controller image. No global Python, Ansible, SOPS, OpenTofu,
Compose, ShellCheck or secret-scanner installation is used.

```bash
scripts/controller versions
scripts/check
scripts/controller digest
scripts/controller cache size
```

For an approved disposable host, keep its inventory, identity, and known-hosts
inputs under ignored `.artifacts/`, then invoke the locked controller with:

```bash
scripts/controller exec-ssh \
  --known-hosts .artifacts/<known-hosts-file> \
  --confirm disposable-host \
  ansible-playbook --inventory /workspace/.artifacts/<inventory> \
  /workspace/infra/playbooks/baseline.yml
```

The first command builds from `infra/controller/Containerfile` if the exact
source-lock tag is absent. GHCR and laptop caches are not required: the build
starts from the digest-pinned base, installs exact-version system packages, and
downloads standalone artifacts only when their URLs and SHA-256 checksums are
committed in `toolchain.lock.yml`. A future published controller is a
convenience only and must be addressed by OCI digest.

The build uses a dedicated, uniquely named BuildKit builder backed by the
digest-pinned BuildKit image. That builder and its task cache are removed after
every build, including failed builds. The remaining Dholbeat-labelled
controller images have a 2 GiB aggregate gate. Inspect and remove them with:

```bash
scripts/controller cache size
scripts/controller cache cleanup --confirm dholbeat-controller
```

Cleanup resolves image IDs from the exact Dholbeat cache label and detects
dedicated builders through Docker's buildx label. It refuses images referenced
by a container or builders that are still running, and never invokes a global
Docker prune. Unrelated images, volumes, containers and shared builder caches
are outside its target.

## Updating the lock

1. Select stable upstream releases for both supported architectures and record
   each version, source URL, license and vendor-published or independently
   verified SHA-256 in `toolchain.lock.yml`.
2. Keep Ansible collections exact in both the lock and `requirements.yml`,
   including transitive collection dependencies.
3. Update direct Python pins in `requirements.in`, then regenerate all
   transitive hashes from the repository root:

   ```bash
   uv pip compile infra/controller/requirements.in \
     --output-file infra/controller/requirements.txt \
     --generate-hashes --universal --python-version 3.13 --no-strip-extras
   ```

   `uv` is only a lockfile generator here; it is not a runtime dependency.
4. Update action version metadata and full commit SHAs together. Never use an
   action tag in a workflow.
5. Run `scripts/controller versions`, `scripts/check`, `scripts/controller
   digest`, and the guarded cache cleanup test before review.

Generated plans, evidence and decrypted output belong under ignored
`.artifacts/` or a fresh temporary directory. CI and normal controller commands
never connect to a host or provider and perform no apply. The guarded
`exec-ssh` command is operator-invoked only for a founder-approved disposable
target. Software and standard repository CI add **$0/month**; any paid
registry, runner or storage proposal requires a founder decision and a complete
wallet table.
