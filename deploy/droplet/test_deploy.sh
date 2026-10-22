#!/bin/bash
# Isolated integration tests: no SSH, pip installs, PostgreSQL, sudo, or live service.
set -euo pipefail
# Git Bash otherwise copies files for ln -s, which would not test Linux semantics.
if [[ ${OSTYPE:-} == msys* ]]; then
    export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
fi
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for script in "$SOURCE"/*.sh; do bash -n "$script"; done
if [[ ${1:-} == --syntax-only ]]; then
    printf 'All deployment Bash scripts parsed successfully.\n'
    exit 0
fi
TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/serbisure-deploy-tests.XXXXXX")
# Tests deliberately retain their small fixture directory for failure inspection.
SHA=0123456789abcdef0123456789abcdef01234567
OTHER_SHA=abcdef0123456789abcdef0123456789abcdef01
passed=0
printf 'Deployment test fixtures: %s\n' "$TEST_ROOT"

assert() { if ! "$@"; then printf 'FAIL: %s\n' "$*" >&2; exit 1; fi; }

run_case() {
    local name=$1 expected=$2 mode=${3:-ok} requested=${4:-$SHA}
    local case_dir="$TEST_ROOT/$name"
    mkdir -p "$case_dir/root/releases" "$case_dir/original" "$case_dir/archive"
    printf 'original dependency environment\n' > "$case_dir/original/venv-marker"
    printf 'fixture environment, NOT credentials\n' > "$case_dir/backend.env"
    printf 'fixture requirements\n' > "$case_dir/archive/requirements.txt"
    ln -s "$case_dir/original" "$case_dir/root/current"
    : > "$case_dir/events"
    if [[ "$mode" == tracked-env ]]; then
        printf 'forbidden fixture\n' > "$case_dir/archive/.env"
    fi
    if [[ "$mode" == already ]]; then
        printf '%s\n' "$SHA" > "$case_dir/original/.deployed-sha"
    fi
    set +e
    (
        source "$SOURCE/deploy.sh"
        DEPLOY_ROOT="$case_dir/root"
        ENV_FILE="$case_dir/backend.env"
        export TEST_LOG="$case_dir/events" TEST_MODE="$mode"
        # Only external boundaries are mocked. The release, switch and rollback code runs.
        id() { printf 'serbisure-deploy\n'; }
        flock() { [[ "$TEST_MODE" != locked ]]; }
        check_space() { [[ "$TEST_MODE" != disk-full ]]; }
        git() {
            if [[ "$1" == init ]]; then mkdir -p "$3"; return; fi
            case "$2" in
                fetch) printf 'fetch\n' >> "$TEST_LOG" ;;
                rev-parse) if [[ "$TEST_MODE" == stale ]]; then
                    printf '%s\n' "$OTHER_SHA"
                else printf '%s\n' "$SHA"; fi ;;
                archive) tar -cf - -C "$case_dir/archive" . ;;
                *) return 90 ;;
            esac
        }
        python3() {
            [[ "$1 $2 $3" == '-m venv .venv' ]]
            mkdir -p .venv/bin
            cat > .venv/bin/python <<'PYTHON_FIXTURE'
#!/usr/bin/env bash
set -eu
printf 'python:%s\n' "$*" >> "$TEST_LOG"
if [[ "$TEST_MODE" == pip-fail && "$*" == '-m pip install '* ]]; then exit 41; fi
if [[ "$TEST_MODE" == pending && "$*" == 'manage.py migrate --check --noinput' ]]; then exit 1; fi
if [[ "$TEST_MODE" == asgi-fail && "$1" == '-c' ]]; then exit 42; fi
if [[ "$*" == 'manage.py collectstatic --noinput' ]]; then mkdir -p staticfiles_build/static; fi
PYTHON_FIXTURE
            chmod 755 .venv/bin/python
        }
        restart_service() {
            printf 'restart:%s\n' "$(readlink "$DEPLOY_ROOT/current")" >> "$TEST_LOG"
            if [[ "$TEST_MODE" == restart-fail && $(readlink "$DEPLOY_ROOT/current") != "$case_dir/original" ]]; then
                return 43
            fi
        }
        healthy() {
            printf 'health\n' >> "$TEST_LOG"
            [[ "$TEST_MODE" != health-fail || $(readlink "$DEPLOY_ROOT/current") == "$case_dir/original" ]]
        }
        main "$requested"
    ) > "$case_dir/output" 2>&1
    local result=$?
    set -e
    if [[ "$expected" == success && "$result" != 0 ]]; then
        cat "$case_dir/output" >&2
    fi
    if [[ "$expected" == success ]]; then
        assert test "$result" -eq 0
    else
        assert test "$result" -ne 0
    fi
    if [[ "$name" == success ]]; then
        assert test "$(cat "$case_dir/root/current/.deployed-sha")" = "$SHA"
        assert test -L "$case_dir/root/current/.env"
        assert grep -q '^python:manage.py migrate --check --noinput$' "$case_dir/events"
        assert grep -q '^python:manage.py collectstatic --noinput$' "$case_dir/events"
        assert grep -q '^restart:' "$case_dir/events"
    else
        assert test "$(readlink "$case_dir/root/current")" = "$case_dir/original"
    fi
    if [[ "$name" == restart-failure || "$name" == health-failure ]]; then
        assert test "$(grep -c '^restart:' "$case_dir/events")" -eq 2
        assert grep -q 'Previous release restored' "$case_dir/output"
    elif [[ "$name" != success ]]; then
        assert test "$(grep -c '^restart:' "$case_dir/events" || true)" -eq 0
    fi
    # No test can mutate the existing runtime, environment, or run a schema migration.
    assert test "$(cat "$case_dir/original/venv-marker")" = 'original dependency environment'
    assert test "$(cat "$case_dir/backend.env")" = 'fixture environment, NOT credentials'
    if grep '^python:manage.py migrate ' "$case_dir/events" | grep -v -- '--check' >/dev/null; then
        echo 'FAIL: attempted a production migration' >&2; exit 1
    fi
    printf 'PASS: %s\n' "$name"
    passed=$((passed + 1))
}

run_case success success
run_case stale-job success stale
run_case already-deployed success already
run_case invalid-sha failure ok 'main; touch /tmp/not-allowed'
run_case pending-migrations failure pending
run_case dependency-failure failure pip-fail
run_case asgi-failure failure asgi-fail
run_case tracked-env failure tracked-env
run_case locked failure locked
run_case disk-full failure disk-full
run_case restart-failure failure restart-fail
run_case health-failure failure health-fail

for command in '' 'main' 'id' "$SHA; id"; do
    if SSH_ORIGINAL_COMMAND="$command" bash "$SOURCE/ssh-entrypoint.sh" > /dev/null 2>&1; then
        echo 'FAIL: forced SSH command accepted non-SHA input' >&2; exit 1
    fi
done
printf 'PASS: forced SSH entrypoint rejects arbitrary commands\n'
printf '%s deployment scenarios plus SSH rejection checks passed. Fixtures: %s\n' "$passed" "$TEST_ROOT"
