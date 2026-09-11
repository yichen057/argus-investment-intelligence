variable "aws_region" {
  type        = string
  default     = "us-west-2"
  description = "AWS Region for the temporary learning stack."

  validation {
    condition     = var.aws_region == "us-west-2"
    error_message = "This reviewed learning stack is intentionally restricted to us-west-2."
  }
}

variable "environment" {
  type        = string
  default     = "learning"
  description = "Short-lived environment label used in names and tags."

  validation {
    condition     = var.environment == "learning"
    error_message = "This stack is only approved for the learning environment."
  }
}

variable "instance_type" {
  type        = string
  default     = "m7i-flex.large"
  description = "Single x86 EC2 instance used for the Docker Compose smoke."

  validation {
    condition     = var.instance_type == "m7i-flex.large"
    error_message = "Changing the reviewed instance type requires a new cost review."
  }
}

variable "root_volume_gib" {
  type        = number
  default     = 20
  description = "Encrypted gp3 root disk size. It is deleted with the instance."

  validation {
    condition     = var.root_volume_gib >= 16 && var.root_volume_gib <= 30
    error_message = "The learning smoke root disk must stay between 16 and 30 GiB."
  }
}

variable "monthly_budget_usd" {
  type        = number
  default     = 10
  description = "Account-level monthly AWS Budget threshold. It is an alert, not a hard spending cap."

  validation {
    condition     = var.monthly_budget_usd >= 1 && var.monthly_budget_usd <= 20
    error_message = "The reviewed learning budget must stay between USD 1 and USD 20."
  }
}

variable "budget_notification_email" {
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
  description = "Optional private email for AWS Budget alerts. Supply interactively; never commit it."

  validation {
    condition = (
      var.budget_notification_email == null ||
      can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.budget_notification_email))
    )
    error_message = "Use a valid email address or leave the value null for a draft plan."
  }
}

variable "docker_compose_version" {
  type        = string
  default     = "v5.3.1"
  description = "Pinned Docker Compose CLI plugin version installed during EC2 bootstrap."
}

variable "docker_compose_sha256" {
  type        = string
  default     = "f9ebc6ebdb19d769b793c245a736caaeb198c62587f13b25c660c13b4987f959"
  description = "Official SHA-256 for the pinned linux-x86_64 Docker Compose binary."

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.docker_compose_sha256))
    error_message = "Docker Compose checksum must be a lowercase SHA-256 value."
  }
}
