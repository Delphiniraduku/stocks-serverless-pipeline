variable "aws_region" {
  default = "us-east-1"
}

variable "project_name" {
  default = "stocks-pipeline"
}

variable "alert_email" {
  description = "Email address to receive pipeline failure alerts"
  default     = "delphiniradukunda11@gmail.com"
}