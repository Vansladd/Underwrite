# The parameter is created by hand, outside Terraform, and only its NAME is passed in. Holding the
# value here — as a var, an aws_ssm_parameter or a data source — writes it to the state bucket in
# plaintext, which is the thing this replaces rather than a detail of how. See D-034.
locals {
  token_from_ssm = var.sweeper_token_param != "" ? 1 : 0
}

data "aws_kms_alias" "ssm" {
  count = local.token_from_ssm
  name  = "alias/aws/ssm"
}

data "aws_iam_policy_document" "sweeper_token_read" {
  count = local.token_from_ssm

  statement {
    actions = ["ssm:GetParameter"]
    resources = [
      "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.sweeper_token_param}"
    ]
  }

  statement {
    actions   = ["kms:Decrypt"]
    resources = [one(data.aws_kms_alias.ssm[*].target_key_arn)]

    # Through Parameter Store only: the AWS-managed SSM key encrypts other things in the account.
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "expiry_lambda_token" {
  count  = local.token_from_ssm
  name   = "read-sweeper-token"
  role   = aws_iam_role.expiry_lambda.id
  policy = one(data.aws_iam_policy_document.sweeper_token_read[*].json)
}

resource "aws_iam_role_policy" "bordereau_lambda_token" {
  count  = local.token_from_ssm
  name   = "read-sweeper-token"
  role   = aws_iam_role.bordereau_lambda.id
  policy = one(data.aws_iam_policy_document.sweeper_token_read[*].json)
}
