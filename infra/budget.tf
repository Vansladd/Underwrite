# Stop-action budget lives with the instance, so destroy takes it too. The $20 account-wide
# alert budget is separate and permanent, so a teardown never removes cost protection. D-015.
data "aws_iam_policy_document" "budget_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "budget_stop" {
  statement {
    actions   = ["ec2:StopInstances"]
    resources = ["arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/${aws_instance.app.id}"]
  }
}

resource "aws_iam_role" "budget_action" {
  name               = "${var.project}-budget-stop"
  assume_role_policy = data.aws_iam_policy_document.budget_assume.json
}

resource "aws_iam_role_policy" "budget_stop" {
  name   = "stop-app-instance"
  role   = aws_iam_role.budget_action.id
  policy = data.aws_iam_policy_document.budget_stop.json
}

resource "aws_budgets_budget" "stop" {
  name         = "${var.project}-stop-action"
  budget_type  = "COST"
  limit_amount = "30"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
}

resource "aws_budgets_budget_action" "stop_instance" {
  budget_name        = aws_budgets_budget.stop.name
  action_type        = "RUN_SSM_DOCUMENTS"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = aws_iam_role.budget_action.arn

  action_threshold {
    action_threshold_type  = "ABSOLUTE_VALUE"
    action_threshold_value = 30
  }

  definition {
    ssm_action_definition {
      action_sub_type = "STOP_EC2_INSTANCES"
      region          = var.region
      instance_ids    = [aws_instance.app.id]
    }
  }

  subscriber {
    address           = "taiwoajoms@gmail.com"
    subscription_type = "EMAIL"
  }
}
