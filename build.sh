#!/bin/bash
# Package the add-on: files must sit at the root of the zip.
set -e
cd "$(dirname "$0")/src"
OUT="../ai_card_filler.ankiaddon"
rm -f "$OUT"
zip -q -r -X "$OUT" . -x "*.pyc" -x "__pycache__/*" -x "user_files/*"
echo "Built $OUT"
