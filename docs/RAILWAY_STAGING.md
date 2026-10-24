# Railway deployment

Deploy `RiasGremoryHSDXD/Serbisure-backend`, branch
`chore/railway-deployment`, with Railway's Railpack builder. No Dockerfile,
server installation, SSH workflow, or custom domain is needed.

## Database selection and rollback

`DATABASE_URL` selects the database. Use the Neon URL ending in
`/serbisure-production-db` for production, or `/staging-environment` for staging,
preserving the connection string's SSL query parameters. The startup command
accepts either name (or another explicitly named PostgreSQL database); it does
not rewrite the URL, copy records, or fall back to a different database.
It still rejects an empty database name, a non-PostgreSQL URL, a local database
host, missing Redis, debug mode, or absent secrets/origin configuration.

After deploying this code yourself, update `DATABASE_URL` in Railway Variables
and apply the change. Your local `.env` controls local Django commands; editing
it does not update Railway's environment. The Railway environment label and
service name do not select the PostgreSQL database.

The original backend remains at commit
`6d2a105b1565b3932f49a42aedd84828b359de86`, preserved by `main` and
`backup/pre-railway-staging-20261024`. Droplet deployment files are removed only
on this staging branch. The running production service and production repository
branch are not changed by local edits. A code rollback does not undo records
written to the selected database. The earlier staging-only startup script will
reject a production connection string if that older code is redeployed.

## Dashboard setup

1. Add the backend from GitHub. Select the branch you intend to deploy.
2. Add a Redis service in the same Railway project. Keep it private.
3. In backend Variables, supply:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | Existing private Neon URL for the intended database, e.g. `serbisure-production-db` |
   | `SECRET_KEY` | Existing private application secret |
   | `DJANGO_DEBUG` | `false` |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` if the service is named Redis |
   | `REALTIME_ALLOWED_ORIGINS` | Exact admin origin(s), comma-separated, including `https://serbisure-admin-one.vercel.app` for production |
   | `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Existing Cloudinary settings |
   | `GOOGLE_VISION_API_KEY`, `GROQ_API_KEY`, `HUGGINGFACE_API_TOKEN` | Existing keys for enabled integrations |

   Preserve the supplied connection credentials. Never commit real `.env`
   values. Cloudinary assets are referenced by the copied database; no media
   deletion is part of this migration.
4. Use one replica in Singapore and leave Serverless/app sleeping disabled.
5. Generate a public Railway HTTPS domain.
6. Enable GitHub autodeploys for the intended deployment branch.
7. Set Build Command to `python manage.py collectstatic --noinput`, Start Command
   to `python -m scripts.start_railway`, and Healthcheck Path to `/api/health/`.

Railway's dashboard stores those service settings; new services no longer accept
the deprecated `railway.json` configuration mechanism. The `Procfile` also declares
the ASGI entrypoint for Railpack. The Python module
uses Railway's `PORT`, preserves the WebSocket limits, and checks pending
migrations without applying them. `railpack.json` installs Tesseract and English
OCR data. `.python-version` selects Python 3.14.

No automatic schema migrations or database test suite runs against staging or
production during deployment. If a migration check fails, investigate the selected
schema and selected commit before changing data.

## Clients and verification

The updated admin code uses the Railway URL in `src/api/apiClient.ts` for hosted
builds and ignores legacy `VITE_API_URL` overrides. Add the production admin's
exact origin and any required Preview origins to `REALTIME_ALLOWED_ORIGINS` and
redeploy the backend. The mobile build uses `EXPO_PUBLIC_API_URL` with
the same Railway URL; rebuild the APK after changing this build-time setting.

HTTP and WebSockets derive from the same selected API URL. Neither client may
silently fall back to another backend. Log out/in when moving between datasets.
Clients sharing this Railway URL use whichever database its backend selects.

Verify readiness (database + Redis), login, uploads/OCR, message delivery in both
directions, stable online presence, bookings, and PDF exports. HTTP readiness alone
does not prove authenticated user flows. Redis's 15-second channel read timeout
must remain longer than Channels' 5-second blocking receive.

## Local checks

With a loopback-only local PostgreSQL URL, run:

```text
venv\Scripts\python.exe manage.py test core.test_railway realtime --settings=Serbisure.test_settings --noinput
```

References: https://docs.railway.com/builds and
https://docs.railway.com/deployments/start-command.
