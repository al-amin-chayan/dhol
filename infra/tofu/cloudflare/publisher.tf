# WP-06B activation is explicit. The operator enables this profile for the
# reviewed routing plan; normal no-change plans also enable it once present in
# remote state. Access service-token secrets are provisioned outside OpenTofu.
variable "publisher_routing_enabled" {
  type    = bool
  default = false
}

variable "publisher_service_token_id" {
  type    = string
  default = ""
}

locals {
  publisher_count   = var.publisher_routing_enabled ? 1 : 0
  publisher_route   = local.routes["publisher-admin-api"]
  publisher_buckets = { for bucket in local.edge.buckets : bucket.id => bucket if var.publisher_routing_enabled }
}

resource "cloudflare_zero_trust_access_application" "publisher_ui" {
  count                      = local.publisher_count
  account_id                 = local.bootstrap.account_id
  name                       = "Dholbeat publisher administration"
  domain                     = local.publisher_route.hostname
  type                       = "self_hosted"
  session_duration           = "24h"
  allowed_idps               = [local.bootstrap.founder_identity_provider_id]
  auto_redirect_to_identity  = true
  http_only_cookie_attribute = true
  enable_binding_cookie      = true
  options_preflight_bypass   = false
  destinations               = [{ type = "public", uri = local.publisher_route.hostname }]
  policies                   = [{ id = cloudflare_zero_trust_access_policy.founder.id, precedence = 1 }]
  lifecycle { prevent_destroy = true }
}

resource "cloudflare_zero_trust_access_policy" "publisher_machine" {
  count      = local.publisher_count
  account_id = local.bootstrap.account_id
  name       = "Dholbeat n8n publisher API only"
  decision   = "non_identity"
  include    = [{ service_token = { token_id = var.publisher_service_token_id } }]
  exclude    = []
  require    = []
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = can(regex("^[0-9a-f-]{36}$", var.publisher_service_token_id))
      error_message = "A real, independently provisioned publisher service-token identity is required."
    }
  }
}

resource "cloudflare_zero_trust_access_application" "publisher_api" {
  count                      = local.publisher_count
  account_id                 = local.bootstrap.account_id
  name                       = "Dholbeat publisher API"
  domain                     = "${local.publisher_route.hostname}/api/public/*"
  type                       = "self_hosted"
  session_duration           = "1h"
  allowed_idps               = [local.bootstrap.founder_identity_provider_id]
  options_preflight_bypass   = false
  http_only_cookie_attribute = true
  destinations               = [{ type = "public", uri = "${local.publisher_route.hostname}/api/public/*" }]
  policies = [
    { id = cloudflare_zero_trust_access_policy.publisher_machine[0].id, precedence = 1 },
    { id = cloudflare_zero_trust_access_policy.founder.id, precedence = 2 }
  ]
  lifecycle { prevent_destroy = true }
}

resource "cloudflare_r2_bucket" "runtime" {
  for_each      = local.publisher_buckets
  account_id    = local.bootstrap.account_id
  name          = each.value.name
  jurisdiction  = "default"
  storage_class = "Standard"
  lifecycle { prevent_destroy = true }
}

resource "cloudflare_r2_managed_domain" "runtime" {
  for_each    = local.publisher_buckets
  account_id  = local.bootstrap.account_id
  bucket_name = cloudflare_r2_bucket.runtime[each.key].name
  enabled     = false
}

resource "cloudflare_r2_bucket_lifecycle" "publisher_media" {
  count        = local.publisher_count
  account_id   = local.bootstrap.account_id
  bucket_name  = cloudflare_r2_bucket.runtime["publisher-media"].name
  jurisdiction = "default"
  rules = [{
    id                                 = "publisher-media-seven-day-expiry"
    enabled                            = true
    conditions                         = { prefix = "" }
    delete_objects_transition          = { condition = { type = "Age", max_age = 604800 } }
    abort_multipart_uploads_transition = { condition = { type = "Age", max_age = 86400 } }
  }]
}

# Restic's references are the retention authority; an independent bucket expiry
# can silently remove still-referenced packs or deployed source bundles.
resource "cloudflare_r2_bucket_lifecycle" "private_backups" {
  for_each     = { for id, bucket in local.publisher_buckets : id => bucket if !bucket.public }
  account_id   = local.bootstrap.account_id
  bucket_name  = cloudflare_r2_bucket.runtime[each.key].name
  jurisdiction = "default"
  rules        = []
}

resource "cloudflare_r2_custom_domain" "publisher_media" {
  count        = local.publisher_count
  account_id   = local.bootstrap.account_id
  bucket_name  = cloudflare_r2_bucket.runtime["publisher-media"].name
  domain       = local.publisher_buckets["publisher-media"].public_hostname
  zone_id      = local.bootstrap.zone_id
  enabled      = true
  min_tls      = "1.2"
  jurisdiction = "default"
}
