# The API container reads/writes generated PDFs; scoped to generated/*, not the whole bucket.
data "aws_iam_policy_document" "instance_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "instance_s3" {
  statement {
    sid       = "GeneratedDocuments"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.documents.arn}/generated/*"]
  }
}

resource "aws_iam_role" "instance" {
  name               = "${var.project}-instance"
  assume_role_policy = data.aws_iam_policy_document.instance_assume.json
}

resource "aws_iam_role_policy" "instance_s3" {
  name   = "generated-documents"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.instance_s3.json
}

# Invoke only the PDF render Lambda (UW-052). Gated on image_tag, like the Lambda itself, so a
# box-only apply (no image) plans clean.
data "aws_iam_policy_document" "instance_lambda" {
  count = var.image_tag != "" ? 1 : 0

  statement {
    sid       = "InvokePdfRender"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.pdf_render[0].arn]
  }
}

resource "aws_iam_role_policy" "instance_lambda" {
  count  = var.image_tag != "" ? 1 : 0
  name   = "invoke-pdf-render"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.instance_lambda[0].json
}

# Pull the API image. GetAuthorizationToken has no resource scope; the pull verbs do.
data "aws_iam_policy_document" "instance_ecr" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "PullApiImage"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = [aws_ecr_repository.api.arn]
  }
}

resource "aws_iam_role_policy" "instance_ecr" {
  name   = "pull-api-image"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.instance_ecr.json
}

# Session Manager, so there is no SSH key and no port 22.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.project}-instance"
  role = aws_iam_role.instance.name
}
