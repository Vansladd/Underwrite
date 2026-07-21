#!/usr/bin/env bash
# Creates Terraform's own state bucket, idempotently. See docs/DECISIONS.md D-013.
set -euo pipefail

BUCKET="${TF_STATE_BUCKET:-underwrite-tfstate}"
REGION="${AWS_REGION:-eu-west-2}"

if aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
    echo "bucket $BUCKET already exists"
else
    aws s3api create-bucket \
        --bucket "$BUCKET" \
        --region "$REGION" \
        --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
    echo "created $BUCKET in $REGION"
fi

# Versioning is the only rollback for corrupted state; terraform state has no undo.
aws s3api put-bucket-versioning \
    --bucket "$BUCKET" \
    --versioning-configuration Status=Enabled

aws s3api put-public-access-block \
    --bucket "$BUCKET" \
    --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption \
    --bucket "$BUCKET" \
    --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'

aws s3api put-bucket-lifecycle-configuration \
    --bucket "$BUCKET" \
    --lifecycle-configuration \
    '{"Rules":[{"ID":"expire-old-state-versions","Status":"Enabled","Filter":{},
      "NoncurrentVersionExpiration":{"NoncurrentDays":90},
      "AbortIncompleteMultipartUpload":{"DaysAfterInitiation":7}}]}' >/dev/null

echo "versioning, public-access block, encryption and lifecycle applied to $BUCKET"
