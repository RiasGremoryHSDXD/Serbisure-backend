#!/bin/bash
# Run ONCE manually as root, after reviewing this file. It briefly restarts Django.
set -euo pipefail
umask 022
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
APP=/opt/serbisure-backend
ROOT=/opt/serbisure-deploy
NGINX=/etc/nginx/sites-available/serbisure
changed=0
backup=

restore_on_failure() {
    local result=$?
    trap - EXIT
    if (( result != 0 && changed == 1 )); then
        printf 'Setup failed; restoring the previous service and Nginx configuration.\n' >&2
        cp -a -- "$backup/serbisure.service" /etc/systemd/system/serbisure.service
        cp -a -- "$backup/nginx-serbisure" "$NGINX"
        cp -a --remove-destination -- "$backup/backend.env" "$APP/.env"
        systemctl daemon-reload
        systemctl restart serbisure.service || true
        nginx -t && systemctl reload nginx || true
    fi
    exit "$result"
}

[[ $EUID == 0 ]] || { echo 'Run bootstrap as root.' >&2; exit 1; }
[[ $# == 1 && -f "$1" ]] || { echo 'Usage: bash bootstrap.sh /root/serbisure-actions.pub' >&2; exit 1; }
mapfile -t key_lines < "$1"
[[ ${#key_lines[@]} == 1 ]] || { echo 'Provide exactly one public key line.' >&2; exit 1; }
read -r key_type key_data key_comment <<< "${key_lines[0]}"
[[ "$key_type" == ssh-ed25519 && "$key_data" =~ ^[A-Za-z0-9+/]+={0,3}$ ]] || {
    echo 'An Ed25519 PUBLIC key is required, not a private key.' >&2; exit 1;
}
ssh-keygen -lf "$1" >/dev/null
[[ -f "$APP/.env" && -x "$APP/.venv/bin/python" && -f "$NGINX" ]]
[[ -f /etc/systemd/system/serbisure.service ]]
for binary in git python3 curl flock sudo visudo nginx; do command -v "$binary" >/dev/null; done
id serbisure >/dev/null
nginx -t
curl --fail --silent --show-error --max-time 10 https://159.89.196.204/api/docs/ >/dev/null
grep -Eq 'alias /opt/(serbisure-backend|serbisure-deploy/current)/staticfiles_build/static/;' "$NGINX" || {
    echo 'Unexpected Nginx static alias; inspect it before running setup.' >&2; exit 1;
}
if ! id serbisure-deploy >/dev/null 2>&1; then
    useradd --create-home --user-group --shell /bin/bash serbisure-deploy
fi
[[ $(getent passwd serbisure-deploy | cut -d: -f6) == /home/serbisure-deploy ]]
[[ $(id -u serbisure-deploy) != 0 ]]
usermod -a -G serbisure serbisure-deploy
install -d -o root -g serbisure -m 750 /etc/serbisure
# Keep an existing shared environment on repeat runs. Never print its contents.
if [[ ! -e /etc/serbisure/backend.env ]]; then
    install -o root -g serbisure -m 640 "$APP/.env" /etc/serbisure/backend.env
fi
install -d -o serbisure-deploy -g serbisure -m 755 "$ROOT" "$ROOT/releases"
if [[ ! -e "$ROOT/current" && ! -L "$ROOT/current" ]]; then
    runuser -u serbisure-deploy -- ln -s "$APP" "$ROOT/current"
fi
[[ -L "$ROOT/current" && -d "$ROOT/current" ]]
runuser -u serbisure-deploy -- test -r /etc/serbisure/backend.env
install -d -o root -g root -m 755 /usr/local/lib/serbisure
install -o root -g root -m 755 "$SOURCE/deploy.sh" /usr/local/lib/serbisure/deploy.sh
install -o root -g root -m 755 "$SOURCE/ssh-entrypoint.sh" /usr/local/lib/serbisure/ssh-entrypoint.sh
install -d -o serbisure-deploy -g serbisure-deploy -m 700 /home/serbisure-deploy/.ssh
# Dedicated key, no port/agent forwarding, no PTY, no arbitrary SSH command.
printf 'restrict,command="/usr/local/lib/serbisure/ssh-entrypoint.sh" %s %s serbisure-github-actions\n' \
    "$key_type" "$key_data" > /home/serbisure-deploy/.ssh/authorized_keys
chown serbisure-deploy:serbisure-deploy /home/serbisure-deploy/.ssh/authorized_keys
chmod 600 /home/serbisure-deploy/.ssh/authorized_keys
sudo_file=$(mktemp /etc/sudoers.d/serbisure-deploy.XXXXXX)
printf 'serbisure-deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart serbisure.service\n' > "$sudo_file"
chmod 440 "$sudo_file"
if ! visudo -cf "$sudo_file"; then rm -f -- "$sudo_file"; exit 1; fi
mv -f -- "$sudo_file" /etc/sudoers.d/serbisure-deploy
backup=$(mktemp -d /var/backups/serbisure-deploy.XXXXXX)
cp -a /etc/systemd/system/serbisure.service "$backup/serbisure.service"
cp -a "$NGINX" "$backup/nginx-serbisure"
cp -a "$APP/.env" "$backup/backend.env"
trap restore_on_failure EXIT
changed=1
# The initial rollback checkout and all future releases read the same protected env.
env_stage=$(mktemp -d "$APP/.env-setup.XXXXXX")
ln -s /etc/serbisure/backend.env "$env_stage/env"
mv -Tf -- "$env_stage/env" "$APP/.env"
rmdir -- "$env_stage"
install -o root -g root -m 644 "$SOURCE/serbisure.service" /etc/systemd/system/serbisure.service
# Preserve TLS, WebSocket headers, challenge paths, and every other Nginx setting.
sed -i 's@alias /opt/serbisure-backend/staticfiles_build/static/;@alias /opt/serbisure-deploy/current/staticfiles_build/static/;@' "$NGINX"
nginx -t
systemctl daemon-reload
systemctl restart serbisure.service
systemctl reload nginx
ready=0
for attempt in {1..20}; do
    if curl --fail --silent --max-time 3 https://159.89.196.204/api/docs/ >/dev/null; then
        ready=1; break
    fi
    sleep 2
done
[[ $ready == 1 ]] || { echo 'HTTPS did not become healthy after setup.' >&2; exit 1; }
changed=0
printf 'Setup complete. Existing app remains deployed; backups: %s\n' "$backup"
printf 'Configure GitHub secrets, then enable DROPLET_DEPLOY_ENABLED and run the workflow on main.\n'
