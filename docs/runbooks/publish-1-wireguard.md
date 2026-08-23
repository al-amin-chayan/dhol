# Runbook — move `publish-1` administration onto WireGuard

Replace the interim IP-bound SSH allowlist with tunnel-only administration, so
nothing binds administration to a rotating office address.

Prerequisite: `publish-1` is already converged on the interim allowlist from
`docs/runbooks/publish-1-bootstrap.md`. Do not attempt this on a host that has
never converged.

## What this changes

Before, SSH was reachable from a declared public CIDR. After, the only public
entry point is the WireGuard UDP listener, and SSH answers only inside the
tunnel. The provider console remains the break-glass path, and it must be
exercised before public SSH is scoped away.

## 1. Generate your peer

The host has no WireGuard key until it first converges, so generate your peer
first and complete its configuration afterwards.

```sh
scripts/wireguard-peer-config \
  --peer-id founder-laptop \
  --address 10.99.0.2/32 \
  --subnet 10.99.0.0/24 \
  --output ~/publish-1-founder-laptop.conf
```

The command writes the private half **once**, outside the repository, and prints
only the public key. Move the file into the password manager and delete the
local copy. That is the whole key-custody story: the same place the age keys and
provider recovery logins already live.

Generate a second peer as a recovery path — a phone or another machine. One peer
means one lost device is a console recovery.

## 2. Declare the tunnel

Add to `infra/inventories/production/baseline/publish-1.yml`:

```yaml
vpn:
  mode: wireguard
  interface: wg0
  listen_port: 51820
  subnet: 10.99.0.0/24
  host_address: 10.99.0.1/24
  peers:
    - id: founder-laptop
      public_key: <printed by the helper>
      allowed_ips: [10.99.0.2/32]
```

Then set `ssh.allow_cidrs` to exactly `[10.99.0.0/24]` and add `/etc/wireguard`
to `managed_directories` with mode `0700`. `scripts/check` rejects the contract
if the allowlist is anything other than the VPN subnet, because any other value
leaves a second administrative path bound to a rotating address.

## 3. Exercise break-glass first

Open a VPSDime console session and confirm you can log in. Do this **before**
converging, not after. If the tunnel fails to come up, the console is the only
way back.

## 4. Converge

```sh
scripts/infra-plan --limit publish-1 --stage converged --address <address> \
  --identity-file ~/.dholbeat/publish-1-admin \
  --known-hosts-file ~/.dholbeat/publish-1.known_hosts
```

Review the plan, then apply it through the reviewed release path in
`docs/runbooks/publish-1-bootstrap.md` §5–6.

The convergence order is the safety property. WireGuard comes up **before** the
first connection probe, so the probe proves the path that will survive rather
than the one about to be taken away. The firewall then admits the WireGuard
listener and asserts it is present before SSH is scoped to the VPN subnet:
closing SSH without an admitted tunnel would leave no administrative path at
all. A failed probe aborts with the previous firewall state intact.

## 5. Complete your peer configuration

The convergence reports `wireguard_server_public_key`. Append the block the
helper printed to the saved file, filling in that key and the host's public
endpoint:

```
[Peer]
PublicKey = <wireguard_server_public_key>
Endpoint = <host>:51820
AllowedIPs = 10.99.0.0/24
PersistentKeepalive = 25
```

Update the copy in the password manager. Bring the tunnel up locally and confirm
`ssh dholbeat-admin@10.99.0.1` works before closing the console session.

## 6. Verify

```sh
scripts/infra-verify --limit publish-1 --address <address> \
  --identity-file ~/.dholbeat/publish-1-admin \
  --known-hosts-file ~/.dholbeat/publish-1.known_hosts
```

Verification asserts the interface carries the declared address inside the
declared subnet, the listen port matches, the peer set matches the contract
exactly with no undeclared peer, every peer is allowed a single address rather
than a range, and the only public listener is the WireGuard port plus SSH —
which the firewall scopes to the tunnel.

## Key custody and rotation

The server key is generated on the host once and never overwritten, because a
second convergence must not silently invalidate peer configurations already
saved. Escrow it the same way as any other private key: the password manager.

Rotate when a key is exposed, a device is lost, or the peer set changes. Rotation
is: remove the peer from the contract, converge, and confirm the peer is gone
from `wg show`. A removed peer loses access at the next convergence, not at the
next reboot.

If the host is rebuilt, its server key changes and every peer configuration needs
its `PublicKey` updated. That is the accepted cost of not holding a second copy
of the key off-host. Supply `wireguard_server_private_key` from escrow instead if
you want a rebuild to be transparent to peers.

## Rollback

Re-converge the preceding annotated release, which restores the interim
allowlist. Reach the host through the provider console if the tunnel is the
thing that broke.

## Monthly cost

`$0`. WireGuard is self-hosted on the already-purchased `publish-1`.
