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
