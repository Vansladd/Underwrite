#!/bin/bash
# Build the arm64 image and prove it renders a real-font PDF via the Lambda RIE. No AWS. See D-019.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE=underwrite/pdf-render:rie-test
PORT=9001
OUT="$(mktemp -d)"
chmod 777 "$OUT"

echo "==> building linux/arm64 image"
docker buildx build --platform linux/arm64 --provenance=false -t "$IMAGE" --load "$DIR"

echo "==> starting Lambda RIE"
CID="$(docker run -d --rm -e PDF_OUTPUT_DIR=/tmp/out -v "$OUT:/tmp/out" -p "$PORT:8080" "$IMAGE")"
trap 'docker stop "$CID" >/dev/null 2>&1 || true' EXIT

URL="http://localhost:$PORT/2015-03-31/functions/function/invocations"
for _ in $(seq 1 30); do
  curl -s "$URL" -d '{}' >/dev/null 2>&1 && break || sleep 1
done

echo "==> invoking with test HTML"
EVENT="$(python3 -c "import json; print(json.dumps({'quote_id':'rie-test','html':'<html><body style=\"font-family: DejaVu Sans\"><h1>Underwrite</h1><p>Real fonts, not tofu boxes.</p></body></html>'}))")"
RESP="$(curl -s "$URL" -d "$EVENT")"
echo "response: $RESP"

PDF="$OUT/rie-test.pdf"
[ -f "$PDF" ] || { echo "FAIL: no PDF written"; exit 1; }
head -c4 "$PDF" | grep -q '%PDF' || { echo "FAIL: output is not a PDF"; exit 1; }
echo "PDF size: $(wc -c < "$PDF") bytes"

# PDF streams are compressed, so inspect embedded fonts structurally with pdffonts, not grep.
echo "==> embedded fonts (pdffonts)"
FONTS="$(docker run --rm -v "$OUT:/w" alpine sh -c 'apk add -q poppler-utils && pdffonts /w/rie-test.pdf')"
echo "$FONTS"
DEJAVU="$(echo "$FONTS" | grep -i 'DejaVu' || true)"
[ -n "$DEJAVU" ] || { echo "FAIL: no DejaVu font in the PDF (fallback/tofu)"; exit 1; }
echo "$DEJAVU" | grep -qi 'yes' || { echo "FAIL: DejaVu present but not embedded"; exit 1; }
echo "PASS: DejaVu embedded (real fonts, not tofu)"
