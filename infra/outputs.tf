output "documents_bucket" {
  description = "Documents bucket name; the instance profile scopes s3 access to its /generated/*"
  value       = aws_s3_bucket.documents.bucket
}

output "documents_bucket_arn" {
  description = "Bucket ARN the instance profile scopes s3 access to (#15)"
  value       = aws_s3_bucket.documents.arn
}

output "ecr_repository_url" {
  description = "Push target for make push-pdf-lambda (#21)"
  value       = aws_ecr_repository.pdf_render.repository_url
}

output "instance_id" {
  description = "The app instance; ssm start-session target and budget stop-action subject"
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "Elastic IP — put this in the Cloudflare A record for underwrite.* (#17)"
  value       = aws_eip.app.public_ip
}
