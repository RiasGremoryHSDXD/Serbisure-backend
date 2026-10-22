#!/bin/bash
# A forced authorized_keys command: accept a SHA, never arbitrary shell commands.
set -euo pipefail
if [[ ! ${SSH_ORIGINAL_COMMAND:-} =~ ^[0-9a-f]{40}$ ]]; then
    printf 'Only deployment of a full main commit SHA is permitted.\n' >&2
    exit 1
fi
exec /usr/bin/env -i \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/home/serbisure-deploy USER=serbisure-deploy LOGNAME=serbisure-deploy \
    LANG=C.UTF-8 \
    /usr/local/lib/serbisure/deploy.sh "$SSH_ORIGINAL_COMMAND"
