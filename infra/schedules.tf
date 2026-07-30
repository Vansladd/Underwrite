# EventBridge Scheduler, not Rules: AWS documents scheduled rules as a legacy feature (R4). The
# whole permission model inverts — Scheduler assumes an execution role, so there is deliberately
# NO aws_lambda_permission here. Adding one is the Rules habit and grants nothing. See D-033.

# Both conditions, or the schedules point at a hostname the destroy took away and fail nightly.
locals {
  schedules_on = var.enable_schedules && var.sweeper_token != "" ? 1 : 0
}

# Our own group, not `default`. Scheduler only ever presents the GROUP as aws:SourceArn, so the
# group is the finest grain the trust policy can name — in `default`, any schedule in the account
# could assume this role. Verified by attack: a foreign-named schedule in `default` was accepted
# before this existed. See D-033.
resource "aws_scheduler_schedule_group" "underwrite" {
  count = local.schedules_on
  name  = var.project
}

data "aws_iam_policy_document" "scheduler_assume" {
  count = local.schedules_on

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    # Confused deputy: without this, any account's schedule could assume this role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    # The GROUP arn, not the schedule's. Scheduler presents the group as aws:SourceArn both when
    # validating the role at CreateSchedule and when invoking, so a `schedule/<group>/<name>`
    # pattern matches the resource but nothing ever checked, and 400s. See D-033.
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [one(aws_scheduler_schedule_group.underwrite[*].arn)]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  count              = local.schedules_on
  name               = "${var.project}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume[0].json
}

# count, not a bare data source: with the Lambdas ungated `one()` is null, and a resources list
# containing null fails at plan time even when no schedule is being created.
data "aws_iam_policy_document" "scheduler_invoke" {
  count = local.schedules_on

  statement {
    sid     = "InvokeScheduledLambdas"
    actions = ["lambda:InvokeFunction"]
    resources = [
      one(aws_lambda_function.quote_expiry[*].arn),
      one(aws_lambda_function.bordereau[*].arn),
    ]
  }
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  count  = local.schedules_on
  name   = "invoke-scheduled-lambdas"
  role   = aws_iam_role.scheduler[0].id
  policy = data.aws_iam_policy_document.scheduler_invoke[0].json
}

# Six fields (minutes hours day-of-month month day-of-week year), and day-of-week is 1-7 = SUN-SAT,
# not Unix cron's 0-6. `?` is the no-value marker the unused day field requires. R4.
resource "aws_scheduler_schedule" "quote_expiry" {
  count = local.schedules_on

  name                         = "${var.project}-quote-expiry"
  group_name                   = aws_scheduler_schedule_group.underwrite[0].name
  description                  = "Daily: expire quotes past valid_until (UW-053)"
  schedule_expression          = "cron(0 2 * * ? *)"
  schedule_expression_timezone = "Europe/London"

  # Required by the API; a window would let a 02:00 run drift into the day it is reporting on.
  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = one(aws_lambda_function.quote_expiry[*].arn)
    role_arn = aws_iam_role.scheduler[0].arn
    # Explicit, so the handler's event is always a dict even if the target payload changes shape.
    input = jsonencode({})

    # Cheap retries: the sweep is idempotent and runs again tomorrow, so a bad night self-repairs.
    # The 185-attempt / 24-hour default would hammer a dead box until the next run started.
    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}

resource "aws_scheduler_schedule" "bordereau" {
  count = local.schedules_on

  name                         = "${var.project}-bordereau"
  group_name                   = aws_scheduler_schedule_group.underwrite[0].name
  description                  = "1st of the month: export the closed month's bordereau (UW-054)"
  schedule_expression          = "cron(0 3 1 * ? *)"
  schedule_expression_timezone = "Europe/London"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = one(aws_lambda_function.bordereau[*].arn)
    role_arn = aws_iam_role.scheduler[0].arn
    # No period: the API picks the closed month in its own reporting zone. See D-032.
    input = jsonencode({})

    # More generous than the sweep's: a missed month is a month, not a day. The real repair is
    # still the manual backfill (`POST /api/internal/bordereaux/YYYY-MM`), not more retries.
    retry_policy {
      maximum_retry_attempts       = 5
      maximum_event_age_in_seconds = 21600
    }
  }
}
