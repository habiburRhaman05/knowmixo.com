#!/usr/bin/env bash
# scripts/verify_launch.sh — one-command proof of Day-N readiness.
# Prints a PASS/FAIL table. Non-zero exit on any FAIL.
set -u -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RED=$'\033[31m'; GRN=$'\033[32m'; DIM=$'\033[2m'; RST=$'\033[0m'
PASS=0; FAIL=0
STATUS_TABLE=()

run() {
  local label="$1"; shift
  local out
  if out="$(eval "$@" 2>&1)"; then
    STATUS_TABLE+=("${GRN}PASS${RST}	$label")
    PASS=$((PASS+1))
  else
    STATUS_TABLE+=("${RED}FAIL${RST}	$label	${DIM}$(echo "$out" | tail -2 | tr '\n' ' ')${RST}")
    FAIL=$((FAIL+1))
  fi
}

cd "$ROOT"

echo "--- Build health ---"
run "backend compile"     "cd backend && ./.venv/Scripts/python -m compileall -q app worker scripts"
run "backend unit tests"  "cd backend && ./.venv/Scripts/python -m pytest -q -p no:cacheprovider -W ignore"
run "frontend typecheck"  "cd frontend && npx tsc --noEmit"
run "frontend tests"      "cd frontend && npx vitest run --silent"
run "openapi drift"       "cd backend && ./.venv/Scripts/python scripts/export_openapi.py --check"

echo "--- Phase 0 providers (real) ---"
run "phase 0 smoke"       "cd backend && ./.venv/Scripts/python scripts/smoke_phase0.py"

echo "--- DB-bound ---"
if [ -n "${TEST_DATABASE_URL:-}" ]; then
  run "alembic head"      "cd backend && ./.venv/Scripts/alembic upgrade head"
  run "DB-backed pytest"  "cd backend && ./.venv/Scripts/python -m pytest -q -p no:cacheprovider -W ignore --timeout=30"
fi

echo "--- Security scans ---"
command -v gitleaks >/dev/null && run "gitleaks secrets scan" "gitleaks detect --redact --no-banner -s $ROOT"
command -v pip-audit >/dev/null && run "pip-audit"            "cd backend && ./.venv/Scripts/pip-audit --strict"
command -v npm      >/dev/null && run "npm audit (high)"      "cd frontend && npm audit --omit=dev --audit-level=high"

echo "--- Eval (if golden set exists) ---"
[ -d backend/eval/golden ] && run "RAG eval ship-gate" "cd backend && ./.venv/Scripts/python -m eval.harness --config v2 --ship-gate"

echo
echo "--- Verify-launch result ---"
printf '%s\n' "${STATUS_TABLE[@]}"
echo
echo "PASS: $PASS   FAIL: $FAIL"
[ $FAIL -eq 0 ]
