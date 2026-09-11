variable "aws_region" {
  type    = string
  default = "us-west-2"
}
variable "environment" {
  type    = string
  default = "dev"
}
variable "cluster_name" {
  type    = string
  default = "argus-dev"
}
variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}
variable "database_instance_class" {
  type    = string
  default = "db.t4g.micro"
}
variable "database_name" {
  type    = string
  default = "argus"
}
variable "database_username" {
  type    = string
  default = "argus"
}
variable "kubernetes_version" {
  type    = string
  default = "1.35"
}
variable "monthly_budget_usd" {
  type        = number
  default     = 31
  description = "Monthly AWS cost alert threshold. This is not a hard spending cap."
}
variable "budget_notification_email" {
  type        = string
  description = "Email address for AWS Budget notifications."
}
variable "enable_kafka" {
  type        = bool
  default     = false
  description = "Provision MSK Serverless. Disabled by default because it adds material cost."
}
