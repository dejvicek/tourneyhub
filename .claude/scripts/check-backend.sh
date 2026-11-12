#!/bin/sh
# The backend checks of check-worktree.sh. Runs inside a one-off api container, in the
# worktree's backend/ (mounted on /src), with this directory mounted on /check.
#
# Usage: check-backend.sh <shards> <database-prefix>
#   The tests run as <shards> pytest processes side by side. Shard i has the databases
#   <database-prefix>_<i> and <database-prefix>_migrations_<i>, which must exist and be
#   empty. The static checks run beside the tests.
# Exit: 0 all checks passed, 1 a check failed.
set -u

shards=$1
prefix=$2
db=${TOURNEYHUB_DATABASE_URL%/*}
out=$(mktemp -d)

# Logs, shard reports and coverage data go to $out, not /src, where only .coverage
# and the tools' caches are git-ignored.
(ruff format --check && ruff check && mypy && lint-imports &&
  python -W error -m tourneyhub.openapi | diff -u openapi.json -) >"$out/static.log" 2>&1 &
static=$!

pids=
i=0
while [ "$i" -lt "$shards" ]; do
  TOURNEYHUB_TEST_DATABASE_URL=$db/${prefix}_$i \
    TOURNEYHUB_TEST_MIGRATIONS_DATABASE_URL=$db/${prefix}_migrations_$i \
    COVERAGE_FILE=$out/.coverage.$i PYTHONPATH=/check \
    coverage run -m pytest -p check_shard --shard "$i/$shards" \
    --shard-report "$out/shard.$i" >"$out/pytest.$i.log" 2>&1 &
  pids="$pids $!"
  i=$((i + 1))
done

# The static checks are quick: when one fails, the tests are not worth waiting for.
wait "$static"
static_rc=$?
cat "$out/static.log"
# The container ends with this script, and the pytest processes with the container.
[ "$static_rc" -eq 0 ] || exit 1

failed=false
i=0
for pid in $pids; do
  if wait "$pid"; then
    # A passed shard: only what -ra reported (skips, xfails) and the totals line.
    sed -n '/short test summary info/,$p' "$out/pytest.$i.log" | grep . || tail -n 1 "$out/pytest.$i.log"
  else
    failed=true
    echo "--- pytest shard $i of $shards FAILED ---"
    cat "$out/pytest.$i.log"
  fi
  i=$((i + 1))
done
$failed && exit 1

# Every shard must have collected the same tests (same count and same node ids), so
# that the split by node id gives each test to exactly one shard; together they must
# have run all of them.
if ! awk -v shards="$shards" '
      { kept += $1; if (NR == 1) { total = $2; ids = $3 } else if ($2 != total || $3 != ids) differ = 1 }
      END {
        if (NR != shards || differ || kept != total) {
          printf "Error: %d shards ran %d of %d collected tests\n", NR, kept, total
          exit 1
        }
        printf "pytest: %d tests ran in %d shards", total, shards
        print " (a shard counts the tests of the other shards as deselected)"
      }' "$out"/shard.*; then
  exit 1
fi

export COVERAGE_FILE="$out/.coverage"
coverage combine --quiet "$out" && coverage report &&
  coverage report --include="*/tourneyhub/engine/*" --fail-under=100
