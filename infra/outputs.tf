output "api_endpoint" {
  value = "https://${aws_api_gateway_rest_api.rest_api.id}.execute-api.${var.aws_region}.amazonaws.com/prod/movers"
}

output "frontend_url" {
  value = aws_s3_bucket_website_configuration.frontend.website_endpoint
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.movers.name
}