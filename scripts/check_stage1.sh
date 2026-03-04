#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

required_files=(
  ".env.example"
  "config.py"
  "requirements.txt"
  "README.md"
  "FABRIC_RUNBOOK.md"
  "EXECUTE_INSTRUCTIONS.md"
  "LICENSE"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "[FAIL] missing required file: $file"
    exit 1
  fi
done

python3 -m py_compile config.py web_app.py detect.py anchor_to_fabric.py verify_evidence.py

if rg -n -- "asset-transfer-basic|ReadAsset|projects/cv-simple|GeminiAntigravity" \
  README.md FABRIC_RUNBOOK.md EXECUTE_INSTRUCTIONS.md >/dev/null; then
  echo "[FAIL] old flow keywords still found in docs"
  exit 1
fi

echo "[OK] stage-1 baseline checks passed"
