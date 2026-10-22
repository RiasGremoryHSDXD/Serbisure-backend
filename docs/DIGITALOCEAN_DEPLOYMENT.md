# DigitalOcean backend deployment

This deploys **only the backend** from public repository
`RiasGremoryHSDXD/Serbisure-backend`, branch `main`, to the existing Droplet
`159.89.196.204`. It does not purchase resources, deploy either frontend, install
Tesseract, replace certificates, or change Django application code.

## What changes, and what does not

- A GitHub merge/push to `main`, or a manual workflow run **on main**, requests a
  deployment of that exact commit. Old queued commits are skipped if main moved on.
- The workflow is **disabled by default** until the repository Actions variable
  `DROPLET_DEPLOY_ENABLED` is set to the lowercase string `true`.
- An isolated Ubuntu validation job runs on pull requests to main, pushes to main
  and manual runs. Deployment requires it to pass. It anonymously fetches the exact
  public commit and receives no production secrets; no checkout/SSH action is used.
- A dedicated `serbisure-deploy` account builds a fresh release and Python venv.
  Django still runs as the existing unprivileged `serbisure` account.
- The deployment SSH key can request only a full commit SHA. It cannot open a
  shell, forward ports, or run arbitrary SSH commands. The account's only sudo
  grant is restarting `serbisure.service`. Treat trusted main and dependency code
  as having deployment-account and production-application access, not as sandboxed.
- Pip consistency, Django checks, migration status, static collection, and ASGI
  import must pass before switching the current release. These are deployment
  checks, **not a substitute for the application's unit/integration tests**.
- Pending migrations stop deployment. No automatic production migrations or test
  database creation are permitted. No data/schema rollback is attempted.
- The current symlink switches only after preparation; then the service restarts.
  Local HTTP plus public certificate-verified HTTPS must return 200. On failure,
  the previous release is restored and restarted. This is **not zero downtime**;
  active WebSockets disconnect and clients must reconnect.
- Release-local dependencies and static files do not overwrite the live release.
  Existing `/opt/serbisure-backend` remains the initial rollback target.
- No old release is deleted automatically. A deployment refuses to start with
  less than 2 GiB free disk. Monitor disk; retain the current and previous known-good
  releases and review older release directories before removing them manually.

GitHub workflow: `.github/workflows/deploy_droplet.yml`.
Server scripts and service template: `deploy/droplet/`.

## Before enabling anything

1. Rotate the production database password, Django secret, and API credentials
   previously exposed in chat/screenshots. Update every existing deployment that
   uses them. Never paste replacement secrets into chat or commit any `.env`.
2. Review and commit these deployment files with the backend changes. Push your
   feature branch and merge the reviewed pull request into **this backend
   repository's main** only after the workflow's `validate` job passes. Nothing
   deploys while the enable variable is absent; validation still runs.
3. Keep the working root SSH session and DigitalOcean Web Console available.
4. Confirm you have reviewed any migration plan and an appropriate database backup.

## One-time step 1: create a separate deployment key on Windows

In a new **Windows PowerShell** terminal, not CMD and not root SSH:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\serbisure_github_actions" -C "serbisure-github-actions"
```

Choose this unused filename; **do not overwrite an existing key** if prompted.
Press Enter twice for an empty passphrase: unattended Actions uses this dedicated,
restricted key, not your personal encrypted `serbisure_digitalocean_v2` key.
Keep the private key private. The `.pub` file is the public key.

Copy only the public key:

```powershell
Get-Content "$env:USERPROFILE\.ssh\serbisure_github_actions.pub" | Set-Clipboard
```

In the **Droplet root terminal**, create a file and paste that single public line:

```bash
nano /root/serbisure-actions.pub
```

Save with Ctrl+O, Enter, Ctrl+X.

## One-time step 2: install the reviewed server scripts

Only after the files are merged into GitHub main, run these in the **Droplet root
terminal**. Fetch/archive does not update the existing live checkout:

```bash
git -C /opt/serbisure-backend fetch origin main
install -d -m 700 /root/serbisure-deploy-setup
git -C /opt/serbisure-backend archive origin/main deploy/droplet | tar -x -C /root/serbisure-deploy-setup
bash /root/serbisure-deploy-setup/deploy/droplet/bootstrap.sh /root/serbisure-actions.pub
```

Bootstrap creates a deployment account, installs root-owned deployment scripts,
restricts that account's deployment key and sudo access, and initially points
`/opt/serbisure-deploy/current` at your **existing working checkout**. It backs up
the service and Nginx site, updates their application/static paths to `current`,
and briefly restarts Django. HTTPS certificates, HTTP challenge paths and proxy
settings are preserved. On a setup health failure it attempts to restore the
previous service/site configuration. Other newly created setup files/accounts
remain for inspection; setup is not a full transaction.

Production environment handling:

- Bootstrap copies the current server `.env` to `/etc/serbisure/backend.env`,
  root-owned, mode 640, readable by the `serbisure` group. Repeat bootstrap runs do
  **not** overwrite this shared file.
- The original checkout's `.env` is backed up in the protected setup backup
  directory and replaced with a symlink to that shared file. Every new release
  uses the same link, so rollback does not resurrect stale credentials.
  After bootstrap, make environment changes **only there**, then restart:

  ```bash
  nano /etc/serbisure/backend.env
  systemctl restart serbisure.service
  ```

- Do not source the environment file as shell code.
- Bootstrap replaces the dedicated account's `authorized_keys` with this one
  restricted key; it does not alter your root/personal SSH keys.

## One-time step 3: configure GitHub secrets and enable

Open the **backend repository** on GitHub. In **Settings → Secrets and variables →
Actions → Secrets**, add these repository secrets:

| Secret | Value |
| --- | --- |
| `DROPLET_HOST` | `159.89.196.204` |
| `DROPLET_SSH_KEY` | Entire private deployment key, including BEGIN/END lines |
| `DROPLET_KNOWN_HOSTS` | Verified host key line, constructed below |

Copy the private deployment key **directly to GitHub**, not chat or source files.
In Windows PowerShell:

```powershell
Get-Content -Raw "$env:USERPROFILE\.ssh\serbisure_github_actions" | Set-Clipboard
```

Paste into `DROPLET_SSH_KEY`, save, and clear the clipboard when finished:

```powershell
Set-Clipboard -Value ''
```

In your already trusted **Droplet root SSH/Web Console**, display the public SSH
host key (not a certificate private key):

```bash
cat /etc/ssh/ssh_host_ed25519_key.pub
```

For `DROPLET_KNOWN_HOSTS`, prefix its key type and key data with the IP:

```text
159.89.196.204 ssh-ed25519 <the-server-public-host-key-data>
```

The angle-bracket text is a placeholder, not a literal value. Do not use your
personal/deployment public key here. Verify this server key through the existing
trusted connection; the workflow deliberately does not trust an on-the-fly
`ssh-keyscan` or disable host-key verification.

Under **Actions → Variables**, add repository variable:

```text
DROPLET_DEPLOY_ENABLED = true
```

Then open **Actions → Deploy backend to DigitalOcean → Run workflow**, select
`main`, and run it. Future pushes/merges into main deploy automatically. No
`pull_request_target` trigger, repository write token, or third-party SSH action
is used. Other repository workflows, including the database-export workflow,
are unchanged.

## Verify a deployment

The Actions job should end with `Successfully deployed <commit>`.
In the root server terminal:

```bash
cat /opt/serbisure-deploy/current/.deployed-sha
systemctl status serbisure --no-pager -l
curl -I https://159.89.196.204/api/docs/
```

Also test login, image upload and authenticated chat/WebSocket delivery from the
mobile app and admin. Swagger returning 200 does not prove those flows work.
Deploying backend code does not change either frontend's API environment or
rebuild an APK. Set the exact deployed portal origin in `REALTIME_ALLOWED_ORIGINS`
when hosting the admin outside localhost, and restart Django.

## When deployment stops

- **Skipped job:** confirm the enable variable is exactly `true`, workflow files
  are on main, and a manual run selected main.
- **SSH failure:** verify all three secrets and the dedicated public key. Do not
  reuse a personal private key or disable host-key checking.
- **Pending migrations:** current app remains unchanged. Review the retained
  candidate's migration plan, a current backup, and compatibility with the active
  app before manually applying anything. The existing post-migrate hook generates
  `docs/MODELS_REFERENCE.md`, so perform any approved migration as
  `serbisure-deploy` in that candidate, not as the read-only runtime account.
  Afterwards rerun the workflow on main. Never blindly fake or reverse migrations.
- **Install/check failure:** candidate retained; existing release/venv remain
  untouched. Read the Actions failure before retrying.
- **Restart/health failure:** automatic code rollback is attempted; inspect
  `journalctl -u serbisure -n 80 --no-pager` and the current symlink. Redact tokens,
  credentials and personal data before sharing logs.
- **Engine changes:** `deploy.sh` and the SSH entrypoint are installed root-owned.
  A merge does not replace privileged deployment tooling; review it and rerun
  bootstrap manually to update the installed copies.
- **Disable:** set `DROPLET_DEPLOY_ENABLED` to `false`. The app keeps running;
  this does not stop an already-running deployment. Removing the dedicated
  authorized key revokes future Actions SSH access.

## Local isolated checks

From the backend repository using Bash/Git Bash:

```bash
bash deploy/droplet/test_deploy.sh
```

Tests use temporary fixtures and mock external Git/pip/service boundaries. They
check preparation failure, pending migrations, SHA restrictions, stale jobs,
duplicate deployment, lock/disk guards and restart/health rollback. No live SSH,
production database, dependency install, or real system service is used.
The fixture suite needs native filesystem symlinks. Windows Git Bash requires
Developer Mode or symlink privilege; if Windows refuses them, run the suite on
Linux instead. The GitHub Ubuntu validation job is mandatory before deployment.

References:

- [GitHub deployment controls](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)
- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [OpenSSH authorized_keys restrictions](https://man.openbsd.org/sshd.8#AUTHORIZED_KEYS_FILE_FORMAT)
- [Django migrate --check](https://docs.djangoproject.com/en/6.0/ref/django-admin/#cmdoption-migrate-check)
