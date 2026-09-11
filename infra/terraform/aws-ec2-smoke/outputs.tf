output "instance_id" {
  description = "Temporary EC2 instance ID used by SSM commands."
  value       = aws_instance.smoke.id
}

output "backend_repository_name" {
  description = "ECR repository name. The account-specific registry URL is intentionally not printed."
  value       = aws_ecr_repository.backend.name
}

output "frontend_repository_name" {
  description = "ECR repository name. The account-specific registry URL is intentionally not printed."
  value       = aws_ecr_repository.frontend.name
}

output "budget_name" {
  description = "Account-level AWS Budget created for the learning window."
  value       = aws_budgets_budget.monthly.name
}

output "safety_summary" {
  description = "Human-readable boundaries of this intentionally limited stack."
  value = {
    inbound_rules       = 0
    ssh_key_configured  = false
    managed_kubernetes  = false
    managed_kafka       = false
    managed_database    = false
    root_disk_encrypted = true
    imdsv2_required     = true
  }
}
