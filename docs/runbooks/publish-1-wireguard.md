# Runbook — move `publish-1` administration onto WireGuard

Replace the interim IP-bound SSH allowlist with tunnel-only administration, so
nothing binds administration to a rotating office address.

Prerequisite: `publish-1` is already converged on the interim allowlist from
`docs/runbooks/publish-1-bootstrap.md`. Do not attempt this on a host that has
never converged.

## Why this takes two releases

A host cannot reach its own tunnel before the tunnel exists. At the moment you
would most like to cut over, three things are simultaneously untrue: the host
has no WireGuard key, so your peer configuration is incomplete; inbound UDP is
still refused by the default-deny firewall; and the tunnel address has no pinned
host key. Any single-release cutover that closes public SSH in the same run
would close the only working path before the replacement can carry traffic.

So the contract declares which path currently carries administration:

| `vpn.administration` | What converges | What still works |
| --- | --- | --- |
| `public` | tunnel comes up, UDP admitted, SSH allowlist gains the VPN subnet | the existing public path |
| `tunnel` | tunnel probed, SSH scoped to the VPN subnet, stale rules removed | the tunnel only |

Each phase is its own reviewed release. `scripts/check` refuses a `tunnel`
contract whose allowlist is not exactly the VPN subnet, and refuses a `public`
contract that does not already include the VPN subnet — because the next release
has to be able to connect.

## 1. Generate your peers

```sh
scripts/wireguard-peer-config \
  --peer-id founder-laptop \
  --address 10.99.0.2/32 \
  --subnet 10.99.0.0/24 \
  --output ~/publish-1-founder-laptop.conf
```

The command writes the private half **once**, outside the repository, and prints
only the public key. Move the file into the password manager and delete the local
copy. That is the same custody rule the age keys and provider recovery logins
already follow.

Generate a second peer for another device. One peer means one lost laptop is a
console recovery.

## 2. Phase one — bring the tunnel up beside the existing path

Add to `infra/inventories/production/baseline/publish-1.yml`:

```yaml
vpn:
  mode: wireguard
  administration: public
  interface: wg0
  listen_port: 51820
  subnet: 10.99.0.0/24
  host_address: 10.99.0.1/24
  peers:
    - id: founder-laptop
      public_key: <printed by the helper>
      allowed_ips: [10.99.0.2/32]
```

Add `10.99.0.0/24` to `ssh.allow_cidrs`, keeping the existing office CIDR, and
add `/etc/wireguard` to `managed_directories` with mode `0700`.

Plan and apply through the reviewed release path in
`docs/runbooks/publish-1-bootstrap.md` §5–6, connecting over the public address
as usual. Nothing closes in this phase.

The convergence prints `wireguard_server_public_key`. Record it.

## 3. Complete your peer configuration and pin the tunnel

Append to the saved peer file, using the key just reported:

```
[Peer]
PublicKey = <wireguard_server_public_key>
Endpoint = <public-address>:51820
AllowedIPs = 10.99.0.0/24
PersistentKeepalive = 25
```

Update the copy in the password manager. Bring the tunnel up locally, then:

```sh
ssh-keyscan -t ed25519 10.99.0.1 >>~/.dholbeat/publish-1.known_hosts
ssh-keygen -lf ~/.dholbeat/publish-1.known_hosts
```

The tunnel address is the **same host**, so its fingerprint must match the one
already pinned for the public address. If it does not, stop: something is
answering on the tunnel that is not `publish-1`.

Confirm `ssh dholbeat-admin@10.99.0.1` works. Phase two connects over the tunnel
and will fail without this.

## 4. Exercise break-glass

Open a VPSDime console session and confirm you can log in. Do this **before**
phase two, not after. If the tunnel breaks, the console is the only way back.

## 5. Phase two — close the public path

Change `vpn.administration` to `tunnel`, set `ssh.allow_cidrs` to exactly
`[10.99.0.0/24]`, and add the reported key:

```yaml
  server_public_key: <wireguard_server_public_key>
```

Committing the server public key makes the running identity reviewable, and
verification then asserts the host is still using that exact key. A silently
replaced key fails the run.

Plan and apply through the reviewed release path. The convergence connects over
the tunnel, proves the administrator connection over it **before** touching the
firewall, then scopes SSH to the VPN subnet and removes the obsolete office-CIDR
rule. Removal happens only after the replacement path is proven, and the run
asserts afterwards that the owned rule set is exactly what the contract declares
— no stale rule, no missing rule.

## 6. Verify

```sh
scripts/infra-verify --limit publish-1 --address <public-address> \
  --identity-file ~/.dholbeat/publish-1-admin \
  --known-hosts-file ~/.dholbeat/publish-1.known_hosts
```

Verification asserts the interface carries the declared address inside the
declared subnet, the listen port matches, the running key matches the reviewed
one, the peer set matches the contract exactly with no undeclared peer, every
peer is allowed a single address rather than a range, and the only public
listeners are the WireGuard port and SSH — which the firewall now scopes to the
tunnel.

## Key custody, escrow, and rotation

The server key is generated on the host once and never overwritten, because a
second convergence must not silently invalidate peer configurations already
saved.

### Escrow, with a confirmation you can act on

Over your administrator session:

```sh
ssh dholbeat-admin@10.99.0.1 'sudo cat /etc/wireguard/wg0.key' >~/publish-1-wg0.key
chmod 600 ~/publish-1-wg0.key
scripts/controller exec python3 scripts/lib/wireguard_keys.py --public-of - <~/publish-1-wg0.key
```

The last command prints the public half and never echoes the private key. **It
must equal the committed `vpn.server_public_key`.** That equality is the
postcondition: an escrowed key that does not derive to the committed value is not
a backup of this host.

Store `~/publish-1-wg0.key` in the password manager beside the peer files, then
delete the local copy. Record the printed public key as the receipt; it is
non-secret and already in Git.

### Restore onto a rebuilt host

Export the key from the password manager to a path outside the repository, then:

```sh
scripts/infra-apply --limit publish-1 --release <tag> --address <address> \
  --identity-file ~/.dholbeat/publish-1-admin \
  --known-hosts-file ~/.dholbeat/publish-1.known_hosts \
  --approved-plan .artifacts/<plan>/plan.yml \
  --wireguard-key-file ~/publish-1-wg0.key
```

The key is copied into the run's bounded inputs directory, never logged, and
removed with that directory when the command exits. The interface is restarted
deliberately so disk and runtime cannot diverge, convergence then asserts the
running identity equals `vpn.server_public_key`, and the evidence directory keeps
only `wireguard-restore-receipt.yml` containing the public half. Delete the
exported file afterwards.

Because the identity is preserved, every peer configuration keeps working.

### Rotation

- **A peer:** remove it from `vpn.peers` and converge. Verification fails if the
  peer is still present on the host, so removal is proven rather than assumed.
- **The server key:** generate a new one, escrow it, update
  `vpn.server_public_key`, and converge with `--wireguard-key-file` pointing at
  the new key. This runs entirely through the reviewed plan and apply path — no
  console session and no hand-deleted host file. Every peer needs its `PublicKey`
  updated afterwards, so schedule it.

```sh
scripts/controller exec python3 -c 'import sys; sys.path.insert(0, "scripts/lib"); \
  import wireguard_keys as k; p = k.generate_private_key(); \
  print(k.encode(p)); print(k.encode(k.public_key(p)), file=sys.stderr)' \
  >~/publish-1-wg0.key.new
```

The private half goes to the file, the public half to the terminal for the
contract.

## Rollback

Rollback is a reverse cutover, and it has the same ordering problem forwards had:
at the moment you want the public path back, only the tunnel is reachable. So the
transport is stated explicitly rather than derived from the document you are
moving towards.

1. Set `vpn.administration` back to `public` and restore the office CIDR in
   `ssh.allow_cidrs`, keeping the VPN subnet.
2. Plan and apply with `--transport tunnel`:

```sh
scripts/infra-plan --limit publish-1 --stage converged --transport tunnel \
  --address <public-address> \
  --identity-file ~/.dholbeat/publish-1-admin \
  --known-hosts-file ~/.dholbeat/publish-1.known_hosts
```

The run connects over the still-live tunnel while the reconciler re-adds the
public rule. Confirm public SSH works before going further.

3. Only then, if you want WireGuard gone entirely, set `vpn.mode` to `none` and
   converge normally over the public path. The reconciler removes the WireGuard
   rule.

Doing step 3 first would try to reach a host over a path the same release is
removing. Reach the host through the provider console only if the tunnel itself
is what broke; that is break-glass, not the reproducible rollback.

## Monthly cost

`$0`. WireGuard is self-hosted on the already-purchased `publish-1`.
