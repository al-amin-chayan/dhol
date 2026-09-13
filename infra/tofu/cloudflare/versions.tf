terraform {
  required_version = "= 1.12.5"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "= 5.24.0"
    }
  }
  backend "s3" {}
  encryption {
    key_provider "pbkdf2" "dholbeat" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "dholbeat" {
      keys = key_provider.pbkdf2.dholbeat
    }
    state {
      method   = method.aes_gcm.dholbeat
      enforced = true
    }
    plan {
      method   = method.aes_gcm.dholbeat
      enforced = true
    }
  }
}

variable "state_passphrase" {
  type      = string
  sensitive = true
}

provider "cloudflare" {}
