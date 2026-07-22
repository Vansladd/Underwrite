# Account-suffixed name, force_destroy behind a var. See DECISIONS D-014.
resource "aws_s3_bucket" "documents" {
  bucket        = "${var.project}-documents-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.allow_destroy
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  # On a versioned bucket a current-version expiration only writes a delete marker, so the
  # retention and cleanup rules below act on noncurrent versions too. See DECISIONS D-014.
  depends_on = [aws_s3_bucket_versioning.documents]

  rule {
    id     = "expire-bordereaux"
    status = "Enabled"

    filter {
      prefix = "bordereaux/"
    }

    expiration {
      days = 365
    }

    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }

  rule {
    id     = "expire-superseded-generated-pdfs"
    status = "Enabled"

    filter {
      prefix = "generated/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
