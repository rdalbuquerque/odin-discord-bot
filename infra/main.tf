terraform {}

data "aws_region" "current" {}

locals {
  region = data.aws_region.current.name
  ecs_task_container_definition = templatefile("odin-bot-task-container-definition.tftpl", {
    aws_region            = local.region
    valheim_ec2_cluster   = var.valheim_ec2_cluster
    odin_bot_token        = var.odin_bot_token
    aws_access_key_id     = var.aws_access_key_id
    aws_secret_access_key = var.aws_secret_access_key
    ssh_key               = var.ssh_key
  })
}

resource "aws_iam_role" "odin_bot_task" {
  name = "odin_bot"

  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Sid" : "",
        "Effect" : "Allow",
        "Principal" : {
          "Service" : [
            "ecs-tasks.amazonaws.com"
          ]
        },
        "Action" : "sts:AssumeRole"
      }
    ]
  })
}

data "aws_iam_policy" "ecs_task" {
  name = "AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy_attachment" "ecs_task" {
  role       = aws_iam_role.odin_bot_task.name
  policy_arn = data.aws_iam_policy.ecs_task.arn
}

data "aws_iam_policy" "cloudwatch" {
  name = "CloudWatchLogsFullAccess"
}

resource "aws_iam_role_policy_attachment" "cloudwatch_ecs" {
  role       = aws_iam_role.odin_bot_task.name
  policy_arn = data.aws_iam_policy.cloudwatch.arn
}

resource "aws_ecs_task_definition" "odin_bot" {
  family                   = "odin-bot"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  network_mode             = "awsvpc"
  execution_role_arn       = aws_iam_role.odin_bot_task.arn
  container_definitions    = local.ecs_task_container_definition
}

module "ecs" {
  source = "terraform-aws-modules/ecs/aws"

  cluster_name = "discord-bot"
  cluster_settings = {
    "name"  = "containerInsights"
    "value" = "disabled"
  }

  fargate_capacity_providers = {
    FARGATE_SPOT = {
      default_capacity_provider_strategy = {
        weight = 100
      }
    }
  }

  tags = {
    Project = "discord-bot"
  }
}

resource "aws_ecs_service" "odin_bot" {
  name             = "odin-bot"
  cluster          = module.ecs.cluster_id
  task_definition  = aws_ecs_task_definition.odin_bot.arn
  desired_count    = 1
  platform_version = "1.4.0" //not specfying this version explictly will not currently work for mounting EFS to Fargate
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 100
    base              = 1
  }

  network_configuration {
    security_groups  = [module.vpc.default_security_group_id]
    subnets          = [module.vpc.public_subnets[0]]
    assign_public_ip = true
  }
}

resource "aws_s3_bucket" "backup" {
  bucket = "valheim-backup-rda"

  tags = {
    Name        = "valheim-backup"
  }
}