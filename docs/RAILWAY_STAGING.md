# Railway staging deployment

Deploy `RiasGremoryHSDXD/Serbisure-backend`, branch
`chore/railway-deployment`, with Railway's Railpack builder. No Dockerfile,
server installation, SSH workflow, or custom domain is needed.

## Isolation and rollback

The staging database is `staging-environment` on Neon. It was copied from a
consistent `serbisure-production-db` snapshot before connecting Railway.
Production is not a fallback. The startup command refuses any other database
name, missing Redis, debug mode, or absent secrets/origin configuration.

The original backend remains at commit
`6d2a105b1565b3932f49a42aedd84828b359de86`, preserved by `main` and
`backup/pre-railway-staging-20261024`. Droplet deployment files are removed only
on this staging branch. The running production service and production repository
branch are not changed. To abandon the trial, stop the staging Railway service
and return each local repository to `main`; no production database restore is needed.

## Dashboard setup

1. Add the backend from GitHub. Select the staging branch before deploying.
2. Add a Redis service in the same Railway project. Keep it private.
3. In backend Variables, supply:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | Existing private Neon URL, database `staging-environment` |
   | `SECRET_KEY` | Existing private application secret |
   | `DJANGO_DEBUG` | `false` |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` if the service is named Redis |
   | `REALTIME_ALLOWED_ORIGINS` | Exact staging admin origin(s), comma-separated; localhost:3000 may be included for QA |
   | `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Existing Cloudinary settings |
   | `GOOGLE_VISION_API_KEY`, `GROQ_API_KEY`, `HUGGINGFACE_API_TOKEN` | Existing keys for enabled integrations |

   Preserve the supplied staging connection credentials. Never commit real `.env`
   values. Cloudinary assets are referenced by the copied database; no media
   deletion is part of this migration.
4. Use one replica in Singapore and leave Serverless/app sleeping disabled.
5. Generate a public Railway HTTPS domain.
6. Enable GitHub autodeploys for this staging branch only.
7. Set Build Command to `python manage.py collectstatic --noinput`, Start Command
   to `python -m scripts.start_railway`, and Healthcheck Path to `/api/health/`.

Railway's dashboard stores those service settings; new services no longer accept
the deprecated `railway.json` configuration mechanism. The `Procfile` also declares
the ASGI entrypoint for Railpack. The Python module
uses Railway's `PORT`, preserves the WebSocket limits, and checks pending
migrations without applying them. `railpack.json` installs Tesseract and English
OCR data. `.python-version` selects Python 3.14.

No automatic schema migrations or database test suite runs against staging or
production during deployment. If a migration check fails, investigate the copied
schema and selected commit before changing data.

## Clients and verification

Set `VITE_API_URL` in the admin **Preview** environment to the generated Railway
URL, then deploy the admin staging branch. Do not replace the production domain's
environment. Add its exact preview hostname to `REALTIME_ALLOWED_ORIGINS` and
redeploy the backend. The mobile staging build uses `EXPO_PUBLIC_API_URL` with
the same Railway URL; rebuild the APK after changing this build-time setting.

HTTP and WebSockets derive from the same selected API URL. Neither client may
silently fall back to a production backend. Log out/in when moving between the
isolated datasets. Keep both staging clients on Railway for cross-client QA.

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
