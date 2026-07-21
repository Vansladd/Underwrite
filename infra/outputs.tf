output "region" {
  description = "Region every resource is created in"
  value       = var.region
}

output "domain" {
  description = "Hostname the deployed API answers on"
  value       = var.domain
}
