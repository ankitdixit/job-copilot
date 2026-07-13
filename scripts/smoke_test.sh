#!/usr/bin/env bash
# smoke_test.sh — verify a fresh clone is working end-to-end
# Does NOT require LM Studio or Gmail credentials.
# Exit 0 = all checks passed. Exit 1 = one or more failed.

set -euo pipefail

PASS=0
FAIL=0
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ok()   { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

# Detect python3 — prefer venv if active
PYTHON="${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python3}"
PYTHON="${PYTHON:-python3}"

echo ""
echo "=== Job Copilot smoke test ==="
echo "    repo: $REPO_ROOT"
echo "    python: $($PYTHON --version 2>&1)"
echo ""

# ── 1. Python version ────────────────────────────────────────────────────────
echo "[ Environment ]"
PY_VER=$($PYTHON -c "import sys; print(sys.version_info.major * 10 + sys.version_info.minor)")
if [ "$PY_VER" -ge 310 ]; then
  ok "python3 >= 3.10 ($($PYTHON --version 2>&1))"
else
  fail "python3 >= 3.10 required; got $($PYTHON --version 2>&1)"
fi

# ── 2. pyyaml installed ──────────────────────────────────────────────────────
if $PYTHON -c "import yaml" 2>/dev/null; then
  ok "pyyaml installed"
else
  fail "pyyaml not installed — run: pip install pyyaml"
fi

# ── 3. playwright installed ──────────────────────────────────────────────────
if command -v playwright &>/dev/null || $PYTHON -m playwright --version &>/dev/null 2>&1; then
  ok "playwright installed"
else
  fail "playwright not installed — run: pip install playwright && playwright install chromium"
fi

# ── 4. Config files exist (not just examples) ────────────────────────────────
echo ""
echo "[ Config ]"
for cfg in profile standard_answers targets; do
  if [ -f "$REPO_ROOT/config/${cfg}.yml" ]; then
    ok "config/${cfg}.yml exists"
  else
    fail "config/${cfg}.yml missing — run: make config"
  fi
done

# ── 5. Standalone tools respond to --help ────────────────────────────────────
echo ""
echo "[ Tools ]"
for tool in generate_dashboard email_triage; do
  if $PYTHON "$REPO_ROOT/tools/${tool}.py" --help &>/dev/null 2>&1; then
    ok "tools/${tool}.py --help exits 0"
  else
    fail "tools/${tool}.py --help failed"
  fi
done

# ── 6. Orchestrator --list runs without crashing ─────────────────────────────
echo ""
echo "[ Orchestrator ]"
if $PYTHON "$REPO_ROOT/run_applications.py" --list &>/dev/null 2>&1; then
  ok "run_applications.py --list exits 0"
else
  fail "run_applications.py --list failed"
fi

# ── 7. No personal data in tracked files ────────────────────────────────────
echo ""
echo "[ Secret check ]"
LEAK_PATTERNS=(
  "[a-zA-Z0-9._%+\\-]+@(gmail|outlook|hotmail|yahoo)\\.com"
  "\\+44[0-9 ]{9,12}"
  "linkedin\\.com/in/[a-z\\-]+"
)
LEAK_FOUND=0
for pattern in "${LEAK_PATTERNS[@]}"; do
  # Only check tracked files; skip gitignored and .git
  if git -C "$REPO_ROOT" grep -Il -P "$pattern" -- \
      ':!config/profile.yml' \
      ':!config/standard_answers.yml' \
      ':!config/targets.yml' \
      ':!config/companies/*.yml' \
      ':!*.log' \
      ':!.git' 2>/dev/null | grep -q .; then
    fail "potential personal data found (pattern: $pattern)"
    LEAK_FOUND=1
  fi
done
if [ "$LEAK_FOUND" -eq 0 ]; then
  ok "no personal data patterns in tracked files"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
echo ""
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL — fix the issues above then re-run: make smoke"
  exit 1
else
  echo "PASS — ready to run. Next step: set up Gmail (see README § Gmail setup)"
  exit 0
fi
