# Holds the schedule, not the export: the API builds the CSV and writes it. See DECISIONS D-032.
data "archive_file" "bordereau" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/bordereau/handler.py"
  output_path = "${path.module}/.build/bordereau.zip"
}

resource "aws_iam_role" "bordereau_lambda" {
  name = "${var.project}-bordereau"
  # Same trust as the expiry Lambda; both are plain scheduled invocations.
  assume_role_policy = data.aws_iam_policy_document.expiry_lambda_assume.json
}

# Logs only: it holds no AWS permission at all, because it touches no AWS service.
resource "aws_iam_role_policy_attachment" "bordereau_lambda_basic" {
  role       = aws_iam_role.bordereau_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Explicit, or logs default to never-expire and survive terraform destroy. Name must match the fn.
resource "aws_cloudwatch_log_group" "bordereau_lambda" {
  name              = "/aws/lambda/${var.project}-bordereau"
  retention_in_days = 14
}

# Gated on sweeper_token: without the shared secret the function could only ever get a 503.
resource "aws_lambda_function" "bordereau" {
  count = var.sweeper_token != "" ? 1 : 0

  function_name    = "${var.project}-bordereau"
  role             = aws_iam_role.bordereau_lambda.arn
  handler          = "handler.handler"
  runtime          = "python3.13"
  architectures    = ["arm64"]
  filename         = data.archive_file.bordereau.output_path
  source_code_hash = data.archive_file.bordereau.output_base64sha256
  memory_size      = 128
  # Longer than the sweeper's: a month's export is a wider query plus an S3 put on the API side.
  timeout = 120

  environment {
    variables = {
      UNDERWRITE_API_URL = "https://${var.domain}"
      SWEEPER_TOKEN      = var.sweeper_token
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.bordereau_lambda_basic,
    aws_cloudwatch_log_group.bordereau_lambda,
  ]
}
