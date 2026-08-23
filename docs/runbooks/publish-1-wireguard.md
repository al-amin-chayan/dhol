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

## Key custody and rotation

The server key is generated on the host once and never overwritten, because a
second convergence must not silently invalidate peer configurations already
saved. There is deliberately no second path that could install a different key.

**Escrow it.** Over your administrator session:

```sh
ssh dholbeat-admin@10.99.0.1 'sudo cat /etc/wireguard/wg0.key'
```

Store the output in the password manager beside the peer files. Confirm the
escrowed copy is the right one by deriving its public half and comparing it with
the committed `vpn.server_public_key`; they must be identical. That comparison is
the postcondition — an escrowed key that does not match is not a backup.

Rotate when a key is exposed, a device is lost, or the peer set changes:

- **A peer:** remove it from `vpn.peers` and converge. Verification fails if the
  peer is still present on the host, so removal is proven rather than assumed.
- **The server key:** delete `/etc/wireguard/wg0.key` over the console, converge
  to regenerate, update `vpn.server_public_key`, and reissue every peer file.
  Every peer loses access until reissued, so schedule it.

If the host is rebuilt, its server key changes and every peer needs its
`PublicKey` updated. That is the accepted cost of not holding a second live copy
of the key on the controller. Restoring the escrowed key onto a rebuilt host
avoids it.

## Rollback

Set `vpn.administration` back to `public`, restore the office CIDR in
`ssh.allow_cidrs`, and converge: the reconciler re-adds the public rule and the
tunnel keeps working. Setting `vpn.mode` to `none` additionally removes the
WireGuard rule. Reach the host through the provider console if the tunnel is the
thing that broke.

## Monthly cost

`$0`. WireGuard is self-hosted on the already-purchased `publish-1`.
