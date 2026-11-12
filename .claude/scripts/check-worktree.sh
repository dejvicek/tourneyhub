#!/usr/bin/env bash
# Runs the backend and frontend CI checks (not e2e and not the dependency audits)
# against the code in a git worktree of this repository, without replacing the
# running dev stack.
#
# Usage: .claude/scripts/check-worktree.sh <worktree-path> [auto|backend|frontend|all]
#   auto (default): check backend and/or frontend, whichever changed against origin/main
#                   (committed or not); as in CI, a change to backend/openapi.json also
#                   checks the frontend.
# Needs: the dev stack running from the main checkout (`docker compose up`); both
#        areas run in one-off containers, so the host needs no Node or Python.
# Speed: the two areas run side by side, and the backend tests run as several pytest
#        processes (check-backend.sh, check_shard.py). Both files are mounted from this
#        script's directory, so the checked worktree needs no copy of them.
# Exit:  0 all checks passed, 1 a check failed, 2 usage or environment error.
set -uo pipefail

fail() { echo "Error: $*" >&2; exit 2; }
usage() { echo "Usage: $0 <worktree-path> [auto|backend|frontend|all]" >&2; exit 2; }

[ $# -ge 1 ] || usage
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
wt=$(cd "$1" 2>/dev/null && pwd -P) || fail "worktree path not found: $1"
mode=${2:-auto}
case $mode in auto|backend|frontend|all) ;; *) usage ;; esac

# The main checkout holds .env and the Compose project; all worktrees share its .git.
common=$(git -C "$wt" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) \
  || fail "$wt is not inside a git repository"
main=$(dirname "$common")
[ -f "$main/compose.yaml" ] || fail "$wt is not a worktree of the TourneyHub repository"

# Test runs share the tourneyhub_check databases, so only one may run at a time.
lock="$common/check-worktree.lock"
mkdir "$lock" 2>/dev/null \
  || fail "another check is running (lock $lock). Wait for it. Remove the lock only if no check runs."
# The one-off containers get names of this run. Killing `docker compose run` (Ctrl-C,
# a timeout) does not stop its container, so the cleanup removes them: an interrupted
# run must not keep testing against the databases or the worktree of the next run.
run_id="check-worktree-$$"
frontend_log=
frontend_pid=
cleanup() {
  docker rm -f "$run_id-api" "$run_id-frontend" >/dev/null 2>&1
  [ -z "$frontend_log" ] || rm -f "$frontend_log"
  rmdir "$lock"
}
trap cleanup EXIT

check_backend=false
check_frontend=false
case $mode in
  backend) check_backend=true ;;
  frontend) check_frontend=true ;;
  all) check_backend=true; check_frontend=true ;;
  auto)
    git -C "$wt" fetch --quiet origin main 2>/dev/null \
      || echo "Warning: could not fetch origin/main; comparing with the local copy." >&2
    committed=$(git -C "$wt" diff --name-only origin/main...HEAD) \
      || fail "could not compare $wt with origin/main"
    uncommitted=$(git -C "$wt" status --porcelain | cut -c4-) \
      || fail "could not read the git status of $wt"
    changed=$committed$'\n'$uncommitted
    grep -q '^backend/' <<<"$changed" && check_backend=true
    grep -qE '^(frontend/|backend/openapi\.json$)' <<<"$changed" && check_frontend=true
    if ! $check_backend && ! $check_frontend; then
      echo "No changes in backend/ or frontend/ against origin/main: nothing to check."
      exit 0
    fi
    ;;
esac

# Without Docker or Compose no check can run; that is an environment error, not a failed check.
cd "$main" || fail "could not enter $main"
docker compose ps --quiet >/dev/null 2>&1 || fail "Docker or Compose is not reachable from $main"

echo "Worktree: $wt ($(git -C "$wt" rev-parse --abbrev-ref HEAD) @ $(git -C "$wt" rev-parse --short HEAD))"

# Every environment check and the databases come before the first check starts, so
# that `fail` never leaves a check running in the background.
if $check_backend; then
  docker compose ps --status running --services 2>/dev/null | grep -qx db \
    || fail "the dev database is not running. Start the stack in $main: docker compose up --build"
  # The api image has the main checkout's dependencies; only the worktree's source is
  # mounted. With other dependencies the result would mislead, so leave it to CI.
  cmp -s "$wt/backend/uv.lock" "$main/backend/uv.lock" \
    || fail "backend/uv.lock in $wt differs from the main checkout's, whose dependencies the api image has; CI checks this branch"
  # One pytest process for every two of Docker's CPUs: the database works as hard as
  # the tests, and the frontend checks may run beside them.
  cpus=$(docker info --format '{{.NCPU}}' 2>/dev/null) || fail "could not read Docker's CPU count"
  shards=$((cpus / 2))
  [ "$shards" -ge 1 ] || shards=1
  # Fresh test databases for every run, as in CI, one pair per pytest process. The
  # tests migrate their database to the branch's head and leave it there, so a
  # database shared between branches ends at a revision other branches don't know.
  # The tourneyhub_check* databases belong to this script only; the developer's
  # tourneyhub_test databases stay untouched.
  docker compose exec -T db psql -U postgres -q -v ON_ERROR_STOP=1 -v shards="$shards" >/dev/null <<'SQL' \
    || fail "could not recreate the tourneyhub_check test databases"
SELECT format('DROP DATABASE %I WITH (FORCE)', datname) FROM pg_database
  WHERE datname ~ '^tourneyhub_check(_migrations)?(_[0-9]+)?$' \gexec
SELECT format('CREATE DATABASE %I', 'tourneyhub_check' || kind || '_' || shard)
  FROM generate_series(0, :shards - 1) AS shard, (VALUES (''), ('_migrations')) AS kinds (kind) \gexec
SQL
fi

# A one-off api container with the worktree's backend mounted over /src; the running
# api container keeps serving the main checkout.
run_backend() {
  docker compose run --rm --no-deps -T --name "$run_id-api" \
    -v "$wt/backend:/src" -v "$here:/check:ro" \
    api sh /check/check-backend.sh "$shards" tourneyhub_check
}

# A one-off frontend container (it has the Node and pnpm versions the project pins;
# the host may not). node_modules is an anonymous volume, so the main stack's
# frontend-node-modules volume stays untouched; it is removed with the container.
run_frontend() {
  docker compose run --rm --no-deps -T --name "$run_id-frontend" \
    -v "$wt/frontend:/src/frontend" \
    -v /src/frontend/node_modules \
    -v "$wt/backend/openapi.json:/src/backend/openapi.json:ro" \
    frontend sh -c 'pnpm install --frozen-lockfile && pnpm lint && pnpm format:check &&
      pnpm typecheck && pnpm test && pnpm build'
}

result=0

# With both areas to check, the frontend runs in the background while the backend
# reports; its output is kept and printed afterwards.
if $check_backend && $check_frontend; then
  frontend_log=$(mktemp) || fail "could not create a temporary file"
  run_frontend >"$frontend_log" 2>&1 &
  frontend_pid=$!
fi

if $check_backend; then
  echo "== backend =="
  if run_backend; then
    echo "backend: PASS"
  else
    echo "backend: FAIL"
    result=1
  fi
fi

if $check_frontend; then
  echo "== frontend =="
  if [ -n "$frontend_pid" ]; then
    wait "$frontend_pid"
    frontend_rc=$?
    cat "$frontend_log"
  else
    run_frontend
    frontend_rc=$?
  fi
  if [ "$frontend_rc" -eq 0 ]; then
    echo "frontend: PASS"
  else
    echo "frontend: FAIL"
    result=1
  fi
fi

exit $result
