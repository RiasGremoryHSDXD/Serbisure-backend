#!/bin/bash
# Installed root-owned; executed as serbisure-deploy, NEVER as root.
set -euo pipefail
umask 022

DEPLOY_ROOT=${SERBISURE_DEPLOY_ROOT:-/opt/serbisure-deploy}
ENV_FILE=${SERBISURE_ENV_FILE:-/etc/serbisure/backend.env}
REPOSITORY=https://github.com/SerbiSure-Tagupa-et-al/Serbisure-backend.git
PUBLIC_URL=https://159.89.196.204/api/docs/
SERVICE=serbisure.service
switched=0
previous=
release=

log() { printf '[deploy] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; return 1; }

atomic_link() {
    local target=$1 temporary="$DEPLOY_ROOT/.current.$$.next"
    ln -s -- "$target" "$temporary" &&
        mv -Tf -- "$temporary" "$DEPLOY_ROOT/current"
}

restart_service() { sudo -n /usr/bin/systemctl restart "$SERVICE"; }

healthy() {
    local attempt status
    for attempt in {1..20}; do
        status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
            --connect-timeout 1 --max-time 2 http://127.0.0.1:8000/api/docs/ || true)
        if [[ "$status" == 200 ]] && /usr/bin/systemctl is-active --quiet "$SERVICE"; then
            status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
                --connect-timeout 2 --max-time 5 "$PUBLIC_URL" || true)
            [[ "$status" == 200 ]] && return 0
        fi
        sleep 2
    done
    return 1
}

finish() {
    local result=$1
    trap - EXIT
    if (( result != 0 && switched == 1 )); then
        log 'Deployment failed after switching. Restoring the previous release.'
        if atomic_link "$previous" && restart_service && healthy; then
            log "Previous release restored: $previous"
        else
            log 'ERROR: rollback did not become healthy; check journalctl -u serbisure.' >&2
        fi
    fi
    if (( result != 0 )) && [[ -n "$release" ]]; then
        log "Candidate retained for inspection: $release"
    fi
    exit "$result"
}

check_space() {
    local available
    available=$(df -Pk "$DEPLOY_ROOT/releases" | awk 'NR == 2 {print $4}')
    [[ "$available" =~ ^[0-9]+$ ]] && (( available >= 2097152 )) ||
        fail 'At least 2 GiB free disk is required. Old releases are not deleted automatically.'
}

main() {
    [[ $# == 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || {
        fail 'Expected exactly one full, lowercase commit SHA.'; return 1;
    }
    [[ $(id -un) == serbisure-deploy ]] || {
        fail 'Run as the dedicated serbisure-deploy account, not root.'; return 1;
    }
    local requested=$1 git_dir="$DEPLOY_ROOT/repository.git" target
    export HOME=/home/serbisure-deploy
    export DJANGO_DEBUG=false PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
    export PIP_DISABLE_PIP_VERSION_CHECK=1 GIT_TERMINAL_PROMPT=0
    [[ -r "$ENV_FILE" && -L "$DEPLOY_ROOT/current" ]] || {
        fail 'Run the one-time bootstrap first.'; return 1;
    }
    # Serialize manual runs as well as GitHub Actions jobs.
    exec 9> "$DEPLOY_ROOT/deploy.lock"
    flock -n 9 || { fail 'Another deployment is running.'; return 1; }
    check_space
    if [[ ! -d "$git_dir" ]]; then
        git init --bare "$git_dir"
    fi
    git --git-dir="$git_dir" fetch --no-tags "$REPOSITORY" \
        '+refs/heads/main:refs/remotes/origin/main'
    target=$(git --git-dir="$git_dir" rev-parse refs/remotes/origin/main)
    if [[ "$requested" != "$target" ]]; then
        log 'Skipped: this workflow commit is no longer the tip of main.'
        return 0
    fi
    if [[ -f "$DEPLOY_ROOT/current/.deployed-sha" ]] &&
        [[ $(< "$DEPLOY_ROOT/current/.deployed-sha") == "$target" ]]; then
        log 'This commit is already deployed.'
        return 0
    fi
    previous=$(readlink -f "$DEPLOY_ROOT/current")
    [[ -d "$previous" ]] || { fail 'Current release is missing.'; return 1; }
    release=$(mktemp -d "$DEPLOY_ROOT/releases/$target.XXXXXX")
    chmod 755 "$release"
    trap 'finish $?' EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    log "Preparing commit $target in $release"
    git --git-dir="$git_dir" archive "$target" | tar -x --no-same-owner -C "$release"
    [[ ! -e "$release/.env" && ! -L "$release/.env" ]] || {
        fail 'A committed .env is forbidden.'; return 1;
    }
    ln -s -- "$ENV_FILE" "$release/.env"
    cd "$release"
    python3 -m venv .venv
    .venv/bin/python -m pip install --no-cache-dir --no-compile -r requirements.txt
    .venv/bin/python -m pip check
    .venv/bin/python manage.py check
    # Read-only DB check. NEVER run migrate or tests against production automatically.
    if ! .venv/bin/python manage.py migrate --check --noinput; then
        fail 'Migration check failed. Review the plan and database backup before migrating manually.'
        return 1
    fi
    .venv/bin/python manage.py collectstatic --noinput
    .venv/bin/python -c 'from Serbisure.asgi import application; print("ASGI import OK")'
    printf '%s\n' "$target" > .deployed-sha
    # All preparation completes while the previous release is still serving requests.
    switched=1
    atomic_link "$release"
    restart_service
    healthy || { fail 'HTTP/HTTPS health check failed.'; return 1; }
    switched=0
    log "Successfully deployed $target"
    log 'Previous releases remain available for rollback; no database schema was changed.'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
