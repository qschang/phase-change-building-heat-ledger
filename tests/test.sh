#!/usr/bin/env bash
set -Eeuo pipefail

REWARD_PATH="/logs/verifier/reward.txt"
REPORT_DIR="/logs/verifier"
REWARD_TMP="${REWARD_PATH}.tmp.$$"
write_reward() {
  mkdir -p "$REPORT_DIR"
  printf '%s\n' "$1" > "$REWARD_TMP"
  mv -f "$REWARD_TMP" "$REWARD_PATH"
}
write_zero() {
  mkdir -p "$REPORT_DIR"
  printf '0.00\n' > /logs/verifier/reward.txt
  rm -f "$REWARD_TMP"
}
trap 'write_zero; exit 1' ERR INT TERM HUP
write_zero
cd /tests
export PYTHONDONTWRITEBYTECODE=1
python3 -B -I -m pip install --disable-pip-version-check --no-index --find-links=/tests/wheels --require-hashes -r /tests/requirements.txt >/logs/verifier/pytest-install.log 2>&1
python3 -B -I -c 'import pytest; assert pytest.__version__ == "8.4.2"'

earned=0
# The structured scorer is part of the verifier contract; its report is fail-closed.
# score.py consumes --junit and writes --report-out/--reward-out scoring-report.json.
groups=(dynamics heat_pump state_accounting invalid_input)
weights=(35 30 20 15)
for i in "${!groups[@]}"; do
  group="${groups[$i]}"
  report="$REPORT_DIR/pytest-${group}.xml"
  check="$REPORT_DIR/pytest-${group}-verification.json"
  console="$REPORT_DIR/pytest-${group}.log"
  rm -f "$report" "$check" "$console"

  if python3 -B -I -m pytest -q -p no:cacheprovider -c /tests/pytest.ini --strict-markers --junitxml="$report" \
      -m "$group" /tests/test_outputs.py >"$console" 2>&1; then
    pytest_rc=0
  else
    pytest_rc=$?
  fi

  if python3 -B -I /tests/verify_junit.py "$report" "$group" "$pytest_rc" >"$check" 2>&1; then
    check_rc=0
  else
    check_rc=$?
  fi
  if [ "$check_rc" -eq 0 ]; then
    earned=$((earned + weights[$i]))
  fi
done

python3 -B -I /tests/merge_junit.py "$REPORT_DIR/pytest-all.xml" "$REPORT_DIR"/pytest-*.xml
python3 -B -I /tests/score.py \
  --config /tests/scoring.json \
  --junit "$REPORT_DIR/pytest-all.xml" \
  --report-out "$REPORT_DIR/scoring-report.json" \
  --reward-out "$REWARD_TMP"
mv -f "$REWARD_TMP" "$REWARD_PATH"
rm -f "$REWARD_TMP"
trap - ERR INT TERM HUP
