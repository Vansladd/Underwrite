# IMMUTABLE: #21 tags images by git SHA, and an overwritable SHA defeats pinning a deploy.
resource "aws_ecr_repository" "pdf_render" {
  name                 = "${var.project}/pdf-render"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.allow_destroy

  image_scanning_configuration {
    scan_on_push = true
  }
}

# The 500MB free allowance is 12-month-only, so untagged layers must not accumulate.
resource "aws_ecr_lifecycle_policy" "pdf_render" {
  repository = aws_ecr_repository.pdf_render.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "expire untagged after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "keep last 5 tagged"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = 5
        }
        action = { type = "expire" }
      }
    ]
  })
}
