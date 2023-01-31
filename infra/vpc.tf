module "vpc" {
  source = "terraform-aws-modules/vpc/aws"

  name = "discord-bot"
  cidr = "10.0.0.0/16"

  azs            = ["${local.region}a", "${local.region}b", "${local.region}c"]
  public_subnets = ["10.0.110.0/24"]

  manage_default_security_group = true
  default_security_group_ingress = [
    {
      protocol    = "-1"
      from_port   = 0
      to_port     = 0
      cidr_blocks = "0.0.0.0/0"
    }
  ]
  default_security_group_egress = [
    {
      protocol    = "-1"
      from_port   = 0
      to_port     = 0
      cidr_blocks = "0.0.0.0/0"
    }
  ]

  tags = {
    Terraform = "true"
  }
}