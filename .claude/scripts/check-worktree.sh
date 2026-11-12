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
# Exit:  0 all checks passed, 1 a check failed, 2 usage or environment error.
set -uo pipefail

fail() { echo "Error: $*" >&2; exit 2; }
usage() { echo "Usage: $0 <worktree-path> [auto|backend|frontend|all]" >&2; exit 2; }

[ $# -ge 1 ] || usage
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
trap 'rmdir "$lock"' EXIT

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
(cd "$main" && docker compose ps --quiet >/dev/null 2>&1) \
  || fail "Docker or Compose is not reachable from $main"

echo "Worktree: $wt ($(git -C "$wt" rev-parse --abbrev-ref HEAD) @ $(git -C "$wt" rev-parse --short HEAD))"
result=0

if $check_backend; then
  (cd "$main" && docker compose ps --status running --services 2>/dev/null | grep -qx db) \
    || fail "the dev database is not running. Start the stack in $main: docker compose up --build"
  # The api image has the main checkout's dependencies; only the worktree's source is
  # mounted. With other dependencies the result would mislead, so leave it to CI.
  cmp -s "$wt/backend/uv.lock" "$main/backend/uv.lock" \
    || fail "backend/uv.lock in $wt differs from the main checkout's, whose dependencies the api image has; CI checks this branch"
  echo "== backend =="
  # Fresh test databases for every run, as in CI. The tests migrate their database to
  # the branch's head and leave it there, so a database shared between branches ends
  # at a revision other branches don't know. These two belong to this script only;
  # the developer's tourneyhub_test databases stay untouched.
  for d in tourneyhub_check tourneyhub_check_migrations; do
    (cd "$main" && docker compose exec -T db sh -c \
      "dropdb -U postgres --if-exists --force $d && createdb -U postgres $d") \
      || fail "could not recreate the test database $d"
  done
  # A one-off api container with the worktree's backend mounted over /src;
  # the running api container keeps serving the main checkout.
  if (cd "$main" && docker compose run --rm --no-deps -T -v "$wt/backend:/src" api sh -c '
        db=${TOURNEYHUB_DATABASE_URL%/*}
        export TOURNEYHUB_TEST_DATABASE_URL=$db/tourneyhub_check
        export TOURNEYHUB_TEST_MIGRATIONS_DATABASE_URL=$db/tourneyhub_check_migrations
        ruff format --check && ruff check && mypy && lint-imports &&
        coverage run -m pytest && coverage report &&
        coverage report --include="*/tourneyhub/engine/*" --fail-under=100 &&
        python -W error -m tourneyhub.openapi | diff -u openapi.json -'); then
    echo "backend: PASS"
  else
    echo "backend: FAIL"
    result=1
  fi
fi

if $check_frontend; then
  echo "== frontend =="
  # A one-off frontend container (it has the Node and pnpm versions the project pins;
  # the host may not). node_modules is an anonymous volume, so the main stack's
  # frontend-node-modules volume stays untouched; it is removed with the container.
  if (cd "$main" && docker compose run --rm --no-deps -T \
        -v "$wt/frontend:/src/frontend" \
        -v /src/frontend/node_modules \
        -v "$wt/backend/openapi.json:/src/backend/openapi.json:ro" \
        frontend sh -c 'pnpm install --frozen-lockfile && pnpm lint && pnpm format:check &&
          pnpm typecheck && pnpm test && pnpm build'); then
    echo "frontend: PASS"
  else
    echo "frontend: FAIL"
    result=1
  fi
fi

exit $result
