variable "aws_access_key_id" {
  sensitive = true
  type      = string
}

variable "aws_secret_access_key" {
  sensitive = true
  type      = string
}

variable "odin_bot_token" {
  sensitive = true
  type      = string
}

variable "valheim_ec2_cluster" {
  type = string
}