data "aws_iam_policy_document" "pdf_lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "pdf_lambda" {
  name               = "${var.project}-pdf-render"
  assume_role_policy = data.aws_iam_policy_document.pdf_lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "pdf_lambda_basic" {
  role       = aws_iam_role.pdf_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Writes rendered PDFs; scoped to generated/*. No ECR permission — Lambda pulls the image itself.
data "aws_iam_policy_document" "pdf_lambda_s3" {
  statement {
    sid       = "PutGeneratedPdfs"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.documents.arn}/generated/*"]
  }
}

resource "aws_iam_role_policy" "pdf_lambda_s3" {
  name   = "put-generated-pdfs"
  role   = aws_iam_role.pdf_lambda.id
  policy = data.aws_iam_policy_document.pdf_lambda_s3.json
}

# Explicit, or logs default to never-expire and survive terraform destroy. Name must match the fn.
resource "aws_cloudwatch_log_group" "pdf_lambda" {
  name              = "/aws/lambda/${var.project}-pdf-render"
  retention_in_days = 14
}

# Gated on image_tag: a box-only apply needs no pushed image. Deploy with -var image_tag=<sha>.
resource "aws_lambda_function" "pdf_render" {
  count = var.image_tag != "" ? 1 : 0

  function_name = "${var.project}-pdf-render"
  role          = aws_iam_role.pdf_lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.pdf_render.repository_url}:${var.image_tag}"
  architectures = ["arm64"]
  memory_size   = 2048
  timeout       = 60

  environment {
    variables = {
      DOCUMENTS_BUCKET = aws_s3_bucket.documents.bucket
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.pdf_lambda_basic,
    aws_cloudwatch_log_group.pdf_lambda,
  ]
}
