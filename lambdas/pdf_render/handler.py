import os

import boto3
import weasyprint  # module scope: the ~2-5s init cost lands in cold start, not per invoke (R2)


def render_pdf(html: str) -> bytes:
    return weasyprint.HTML(string=html).write_pdf()


def handler(event, context):
    quote_id = event["quote_id"]
    pdf = render_pdf(event["html"])
    key = f"generated/{quote_id}.pdf"

    # PDF_OUTPUT_DIR is the no-AWS path for the local RIE test; prod puts to S3.
    output_dir = os.environ.get("PDF_OUTPUT_DIR")
    if output_dir:
        path = os.path.join(output_dir, f"{quote_id}.pdf")
        with open(path, "wb") as handle:
            handle.write(pdf)
        return {"s3_key": key, "local_path": path}

    boto3.client("s3").put_object(
        Bucket=os.environ["DOCUMENTS_BUCKET"], Key=key, Body=pdf, ContentType="application/pdf"
    )
    return {"s3_key": key}
