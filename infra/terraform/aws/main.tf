data "aws_availability_zones" "available" {
  state = "available"
}
data "aws_caller_identity" "current" {}

locals {
  name               = "argus-${var.environment}"
  azs                = slice(data.aws_availability_zones.available.names, 0, 2)
  kafka_event_topics = ["agent.run.completed.v1", "agent.run.failed.v1"]
  kafka_retry_topics = [for topic in local.kafka_event_topics : "${topic}.retry"]
  kafka_dlq_topics   = [for topic in local.kafka_event_topics : "${topic}.dlq"]
  kafka_topic_names  = concat(local.kafka_event_topics, local.kafka_retry_topics, local.kafka_dlq_topics)
  kafka_cluster_arn  = try(aws_msk_serverless_cluster.argus[0].arn, "")
  kafka_topic_arns = var.enable_kafka ? [
    for topic in local.kafka_topic_names :
    "${replace(local.kafka_cluster_arn, ":cluster/", ":topic/")}/${topic}"
  ] : []
  kafka_consumer_group_arn = var.enable_kafka ? "${replace(local.kafka_cluster_arn, ":cluster/", ":group/")}/argus-audit-metrics-v1" : ""
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.17.0"

  name                 = local.name
  cidr                 = var.vpc_cidr
  azs                  = local.azs
  private_subnets      = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets       = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 32)]
  database_subnets     = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 48)]
  enable_nat_gateway   = true
  single_nat_gateway   = var.environment != "prod"
  enable_dns_hostnames = true
  public_subnet_tags   = { "kubernetes.io/role/elb" = "1" }
  private_subnet_tags  = { "kubernetes.io/role/internal-elb" = "1" }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.31.6"

  cluster_name                             = var.cluster_name
  cluster_version                          = var.kubernetes_version
  cluster_endpoint_public_access           = true
  enable_cluster_creator_admin_permissions = true
  cluster_upgrade_policy = {
    support_type = "STANDARD"
  }
  cluster_encryption_config        = var.environment == "prod" ? { resources = ["secrets"] } : {}
  create_kms_key                   = var.environment == "prod"
  attach_cluster_encryption_policy = var.environment == "prod"
  vpc_id                           = module.vpc.vpc_id
  subnet_ids                       = module.vpc.private_subnets
  eks_managed_node_groups = {
    general = {
      instance_types = ["m7i-flex.large"]
      min_size       = 1
      max_size       = var.environment == "prod" ? 4 : 1
      desired_size   = 1
      block_device_mappings = {
        root = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 20
            volume_type           = "gp3"
            encrypted             = true
            delete_on_termination = true
          }
        }
      }
    }
  }
}

resource "random_password" "database" {
  length  = 32
  special = false
}

resource "aws_budgets_budget" "argus" {
  name         = "${local.name}-monthly-cost"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_notification_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_notification_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_notification_email]
  }
}

resource "aws_security_group" "data" {
  name_prefix = "${local.name}-data-"
  vpc_id      = module.vpc.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "kafka" {
  count       = var.enable_kafka ? 1 : 0
  name_prefix = "${local.name}-kafka-"
  vpc_id      = module.vpc.vpc_id
  ingress {
    from_port       = 9098
    to_port         = 9098
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_msk_serverless_cluster" "argus" {
  count        = var.enable_kafka ? 1 : 0
  cluster_name = local.name
  vpc_config {
    subnet_ids         = module.vpc.private_subnets
    security_group_ids = [aws_security_group.kafka[0].id]
  }
  client_authentication {
    sasl {
      iam {
        enabled = true
      }
    }
  }
}

data "aws_msk_bootstrap_brokers" "argus" {
  count       = var.enable_kafka ? 1 : 0
  cluster_arn = aws_msk_serverless_cluster.argus[0].arn
}

resource "aws_db_instance" "argus" {
  identifier                = local.name
  engine                    = "postgres"
  engine_version            = "16.14"
  instance_class            = var.database_instance_class
  allocated_storage         = 20
  max_allocated_storage     = var.environment == "prod" ? 100 : 0
  storage_type              = "gp3"
  db_name                   = var.database_name
  username                  = var.database_username
  password                  = random_password.database.result
  db_subnet_group_name      = module.vpc.database_subnet_group_name
  vpc_security_group_ids    = [aws_security_group.data.id]
  storage_encrypted         = true
  backup_retention_period   = var.environment == "prod" ? 7 : 1
  deletion_protection       = var.environment == "prod"
  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${local.name}-final" : null
  multi_az                  = var.environment == "prod"
}

resource "aws_elasticache_subnet_group" "argus" {
  name       = local.name
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "argus" {
  replication_group_id       = local.name
  description                = "Argus cache and job queue"
  node_type                  = "cache.t4g.micro"
  port                       = 6379
  parameter_group_name       = "default.redis7"
  subnet_group_name          = aws_elasticache_subnet_group.argus.name
  security_group_ids         = [aws_security_group.data.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  num_cache_clusters         = var.environment == "prod" ? 2 : 1
  automatic_failover_enabled = var.environment == "prod"
}

resource "aws_s3_bucket" "artifacts" {
  bucket_prefix = "${local.name}-artifacts-"
  force_destroy = var.environment != "prod"
}
resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_ecr_repository" "backend" {
  name         = "${local.name}/backend"
  force_delete = var.environment != "prod"
  image_scanning_configuration {
    scan_on_push = true
  }
}
resource "aws_ecr_repository" "frontend" {
  name         = "${local.name}/frontend"
  force_delete = var.environment != "prod"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_secretsmanager_secret" "runtime" {
  name                    = "${local.name}/runtime"
  recovery_window_in_days = var.environment == "prod" ? 30 : 0
}
resource "aws_secretsmanager_secret_version" "runtime" {
  secret_id = aws_secretsmanager_secret.runtime.id
  secret_string = jsonencode({
    ARGUS_DATABASE_URL            = "postgresql+psycopg://${var.database_username}:${random_password.database.result}@${aws_db_instance.argus.address}:5432/${var.database_name}"
    ARGUS_REDIS_URL               = "rediss://${aws_elasticache_replication_group.argus.primary_endpoint_address}:6379/0"
    ARGUS_S3_BUCKET               = aws_s3_bucket.artifacts.id
    ARGUS_KAFKA_BOOTSTRAP_SERVERS = try(data.aws_msk_bootstrap_brokers.argus[0].bootstrap_brokers_sasl_iam, "")
    ARGUS_KAFKA_SECURITY_PROTOCOL = var.enable_kafka ? "SASL_SSL" : "PLAINTEXT"
    ARGUS_KAFKA_SASL_MECHANISM    = var.enable_kafka ? "OAUTHBEARER" : ""
  })
}

resource "aws_iam_role" "argus" {
  name = "${local.name}-workload"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = module.eks.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = { StringEquals = {
        "${replace(module.eks.cluster_oidc_issuer_url, "https://", "")}:sub" = "system:serviceaccount:argus:argus",
        "${replace(module.eks.cluster_oidc_issuer_url, "https://", "")}:aud" = "sts.amazonaws.com"
      } }
    }]
  })
}

resource "aws_iam_role_policy" "argus" {
  role = aws_iam_role.argus.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.artifacts.arn}/*" },
        { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.runtime.arn }
      ],
      var.enable_kafka ? [
        {
          Sid      = "KafkaClusterAccess"
          Effect   = "Allow"
          Action   = ["kafka-cluster:Connect", "kafka-cluster:DescribeCluster", "kafka-cluster:WriteDataIdempotently"]
          Resource = [local.kafka_cluster_arn]
        },
        {
          Sid    = "KafkaTopicBootstrapAndData"
          Effect = "Allow"
          Action = [
            "kafka-cluster:CreateTopic",
            "kafka-cluster:DescribeTopic",
            "kafka-cluster:DescribeTopicDynamicConfiguration",
            "kafka-cluster:ReadData",
            "kafka-cluster:WriteData"
          ]
          Resource = local.kafka_topic_arns
        },
        {
          Sid      = "KafkaConsumerGroup"
          Effect   = "Allow"
          Action   = ["kafka-cluster:AlterGroup", "kafka-cluster:DescribeGroup"]
          Resource = [local.kafka_consumer_group_arn]
        }
      ] : []
    )
  })
}
