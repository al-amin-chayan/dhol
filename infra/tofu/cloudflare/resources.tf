locals {
  bootstrap = yamldecode(file("${path.module}/bootstrap.yml"))
  edge      = yamldecode(file("${path.module}/routes.yml"))
  tunnels   = { for tunnel in local.edge.tunnels : tunnel.host_id => tunnel }
  routes    = { for route in local.edge.routes : route.id => route }
}

resource "cloudflare_dns_record" "team" {
  zone_id = local.bootstrap.zone_id
  name    = local.routes["paperclip-admin"].hostname
  type    = "CNAME"
  content = "${local.tunnels["core-1"].id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
  lifecycle { prevent_destroy = true }
}

resource "cloudflare_dns_record" "publish" {
  zone_id = local.bootstrap.zone_id
  name    = local.routes["publisher-admin-api"].hostname
  type    = "CNAME"
  content = "${local.tunnels["publish-1"].id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
  lifecycle { prevent_destroy = true }
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "core" {
  account_id = local.bootstrap.account_id
  name       = local.tunnels["core-1"].name
  config_src = local.tunnels["core-1"].config_source
  lifecycle { prevent_destroy = true }
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "publisher" {
  account_id = local.bootstrap.account_id
  name       = local.tunnels["publish-1"].name
  config_src = local.tunnels["publish-1"].config_source
  lifecycle { prevent_destroy = true }
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "core" {
  account_id = local.bootstrap.account_id
  tunnel_id  = local.tunnels["core-1"].id
  source     = "cloudflare"
  # The operator renders this file from the validated manifest into tmpfs.
  config = { ingress = jsondecode(file("${path.module}/core-ingress.json")) }
  lifecycle { prevent_destroy = true }
}

resource "cloudflare_zero_trust_access_policy" "founder" {
  account_id = local.bootstrap.account_id
  name       = "Only me"
  decision   = "allow"
  include    = [{ email = { email = local.bootstrap.founder_email } }]
  # The provider normalizes empty API rule sets to null on import.
  connection_rules = { rdp = {} }
  lifecycle { prevent_destroy = true }
}

resource "cloudflare_zero_trust_access_application" "team" {
  account_id                 = local.bootstrap.account_id
  name                       = "Paperclip"
  domain                     = local.routes["paperclip-admin"].hostname
  type                       = "self_hosted"
  session_duration           = "24h"
  http_only_cookie_attribute = false
  enable_binding_cookie      = false
  options_preflight_bypass   = false
  app_launcher_visible       = true
  auto_redirect_to_identity  = true
  allowed_idps               = [local.bootstrap.founder_identity_provider_id]
  destinations               = [{ type = "public", uri = local.routes["paperclip-admin"].hostname }]
  policies                   = [{ id = cloudflare_zero_trust_access_policy.founder.id, precedence = 1 }]
  lifecycle { prevent_destroy = true }
}
