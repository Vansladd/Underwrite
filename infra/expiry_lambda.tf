# Holds the schedule, not the sweep: Postgres is unreachable from Lambda. See DECISIONS D-031.
data "archive_file" "quote_expiry" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/quote_expiry/handler.py"
  output_path = "${path.module}/.build/quote-expiry.zip"
}

data "aws_iam_policy_document" "expiry_lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "expiry_lambda" {
  name               = "${var.project}-quote-expiry"
  assume_role_policy = data.aws_iam_policy_document.expiry_lambda_assume.json
}

# Logs. Its only other permission is reading one SSM parameter, in sweeper_token.tf.
resource "aws_iam_role_policy_attachment" "expiry_lambda_basic" {
  role       = aws_iam_role.expiry_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Explicit, or logs default to never-expire and survive terraform destroy. Name must match the fn.
resource "aws_cloudwatch_log_group" "expiry_lambda" {
  name              = "/aws/lambda/${var.project}-quote-expiry"
  retention_in_days = 14
}

# Gated like the PDF Lambda is on image_tag: with no parameter to read the function could only
# ever get a 503, so a box-only apply does not create it.
resource "aws_lambda_function" "quote_expiry" {
  count = local.token_from_ssm

  function_name    = "${var.project}-quote-expiry"
  role             = aws_iam_role.expiry_lambda.arn
  handler          = "handler.handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]
  filename         = data.archive_file.quote_expiry.output_path
  source_code_hash = data.archive_file.quote_expiry.output_base64sha256
  memory_size      = 128
  timeout          = 30

  environment {
    variables = {
      UNDERWRITE_API_URL  = "https://${var.domain}"
      SWEEPER_TOKEN_PARAM = var.sweeper_token_param
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.expiry_lambda_basic,
    aws_iam_role_policy.expiry_lambda_token,
    aws_cloudwatch_log_group.expiry_lambda,
  ]
}
