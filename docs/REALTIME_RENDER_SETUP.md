# SerbiSure WebSocket deployment and verification

## What changed

The same Django ASGI process serves the REST API and `/ws/events/`. Each mobile or portal session establishes one WebSocket and authenticates in its first JSON frame with its existing access JWT. The server subscribes it to that account's private group. Tokens never appear in connection URLs. Browser Origins are checked against an exact allowlist. Connections may also use the exact endpoint HTTP(S) origin, which React Native Android automatically sends (e.g. `http://192.168.1.8:8000` for a local WS endpoint, or the HTTPS API origin for WSS). Native clients may omit Origin. All of these paths still require JWT authentication; unrelated origins, duplicate origins and URL tokens are rejected. Behind a TLS proxy, use the documented ASGI proxy settings so the scope scheme reflects WSS. Invalid/expired tokens and inactive accounts are rejected. An authenticated socket expires with its JWT, receives active-account checks and accepts only heartbeat commands. Database writes continue through the validated REST endpoints.

After a database transaction commits, private events notify affected accounts about messages, image messages, reactions, read receipts, typing, notifications and booking/proposal changes. Clients refresh the corresponding authoritative REST data. A disconnected socket cannot lose a saved message or formalize an unsaved booking. On reconnect, clients reconcile inbox/thread/notification state through REST. Exponential backoff, heartbeat checks and background suspension are included. Regular 3/5/6-second chat polling has been removed; a 30-second REST recovery check runs only while live updates are disconnected and the client is foregrounded. This is live in-app communication, not a mobile OS push-notification service.

## Render resources and cost scope

`render.yaml` prepares one Python web service on `0.5c-512mb` (the current name of the former Starter plan) and one **Free Key Value** service. Verify the plan prices in your Render account before applying the Blueprint. The planned web-service budget is approximately USD 7/month, or USD 14 for two full months, before any taxes, extra usage or other services. PostgreSQL, paid Key Value, background workers and cron jobs are not bundled into that amount. Keep your existing hosted PostgreSQL `DATABASE_URL` if it meets your needs; this Blueprint does not create a second database or paid worker.

Free Key Value currently has 25 MB RAM, 50 server connections and no persistence. It carries only temporary channel events, so losing it does not erase PostgreSQL messages. Fifty Redis connections is a broker-connection limit, not fifty connected app users. It is appropriate to evaluate for the capstone demonstration; monitor memory, connections and event loss before claiming production capacity. Use the internal Redis URL and the same Render region as the API. The Blueprint disables external Redis access. Redis is required on Render so multiple processes/deployments share events correctly. The in-memory layer is used only for local single-process development and automated tests.

Official references checked October 13, 2026:

- [Render WebSockets](https://render.com/docs/websocket): ASGI support, WSS, shared public port, reconnects and heartbeats.
- [Render pricing](https://render.com/pricing) and [Blueprint plan IDs](https://render.com/docs/blueprint-spec).
- [Render Key Value](https://render.com/docs/key-value) and [free-tier limitations](https://render.com/docs/free).
- [Django Channels channel layers](https://channels.readthedocs.io/en/stable/topics/channel_layers.html): Redis for shared production groups.

## Deploy the prepared code

No hosting account has been changed, purchased or deployed by this implementation.

1. Push the reviewed backend changes yourself, then create/update the web service and Free Key Value in Render. The supplied Blueprint is optional: for an existing web service you can instead update its build/start commands and add the Key Value instance manually. Do not change an existing service's region unintentionally; both resources must be in the same region.
2. Keep `SECRET_KEY`, `DATABASE_URL`, Cloudinary, Groq and Hugging Face credentials in the backend environment. The Blueprint's `sync: false` settings require real values; existing private API credentials must be retained. Set `DJANGO_DEBUG=false`.
3. Set `REDIS_URL` to the Key Value **internal** connection string. Do not put Redis credentials in either frontend.
4. Set `REALTIME_ALLOWED_ORIGINS` to the exact portal origin(s), comma separated, e.g. `https://your-portal.vercel.app`. Include the mobile web origin if you deploy Expo web. No wildcard origin is accepted. Native Android/iOS does not need a separate Origin entry when using the endpoint's own origin or omitting Origin. Add `http://localhost:3000` only when intentionally allowing local portal development against this backend.
5. Set the Render start command:

   ```sh
   uvicorn Serbisure.asgi:application --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --ws-max-size 4096 --ws-ping-interval 25 --ws-ping-timeout 25
   ```

   Keep a single worker on the small demo plan initially. Uvicorn handles HTTP and WebSockets; the previous WSGI-only Gunicorn command does not. The build command installs dependencies, collects static assets and applies existing migrations. No new database migration is needed for this feature.
6. Set the portal's `VITE_API_URL=https://your-api.onrender.com` and mobile's `EXPO_PUBLIC_API_URL=https://your-api.onrender.com`. Rebuild the portal and restart Metro with a cleared cache so Expo embeds the new URL. Both REST and WebSockets derive from the same configured backend: `https` becomes `wss`. The old Vercel backend URL is still available for explicitly selected legacy deployments, but it must not be used as the Render WebSocket target. There is no automatic switch between databases or servers.
7. Deploy the backend before the updated clients, then perform the acceptance checks below. These TypeScript changes use the built-in WebSocket API and do not add a native Expo module; your existing debug build can load them through Metro.

## Local development

Install `requirements.txt` in the backend venv. `python manage.py runserver 0.0.0.0:8000` now uses Daphne and serves both protocols. Alternatively:

```powershell
.\venv\Scripts\python.exe -m uvicorn Serbisure.asgi:application --host 0.0.0.0 --port 8000 --reload
```

Keep the mobile and portal pointing to the same reachable backend address. A physical phone needs the PC's LAN address or the existing ADB reverse setup. Only local connections use `ws://`; Render clients use `wss://`. A local multi-process setup also requires Redis.

## Acceptance and failure checks

1. Sign in as a real Homeowner and Kasambahay on two clients; separately sign in as Superadmin/Barangay in the portal. The portal message menu should show **Live updates** after authentication.
2. Send a text and image. The counterpart's message preview and unread badge should update without waiting for a periodic poll. Open the thread: only its incoming messages become read and badges reconcile after the server response.
3. Send an offer from each role, accept it on the counterpart and verify the structured booking/assignment in PostgreSQL and updated cards on both clients. Rejection, reactions and deletion should also refresh the existing conversation.
4. Type on mobile and confirm the counterpart's typing indicator updates and clears. Typing is transient and is never a contract term.
5. Restart the backend or briefly disable networking. Verify the reconnect label, bounded retries, retained saved messages and REST reconciliation when the connection returns. Hidden browser tabs and background mobile apps intentionally suspend their sockets.
6. Log out and sign in as another user. Previous private counts, events and previews must not appear. Try an expired token, another browser Origin or a URL containing a token: the server must reject it.
7. Confirm an authenticated user cannot subscribe to another UUID or write a chat message through the socket. REST authorization, validation and idempotency remain authoritative.
8. Monitor the Render web-service RAM/CPU and Key Value connections during the demonstration. A deployment restart can interrupt sockets; reconnection is expected.

### Mobile connection diagnosis

The Messages screen displays **Live updates** only after the socket receives authenticated `ready`. Connecting/reconnecting and expired-session states are visible there as well as inside an open thread. In a debug build, Metro logs `[Realtime] Connection: connected` and `[Realtime] Received chat.changed` (no tokens or message text). An incoming event refreshes the inbox and the matching open thread through REST immediately; it does not wait for the disconnected recovery timer. Events during a request queue a trailing refresh, and events during an offer response are reconciled once the response finishes. The server subscribes each authenticated account to its private group; opening a conversation does not require a separate room-join command.

If Django logs `WebSocket handshake rejected: untrusted Origin`, check the portal origin allowlist and the proxy's scheme/Host forwarding. The installed React Native Android source adds an endpoint Origin automatically; treating every native connection as origin-less previously rejected these sockets. Restart the backend after updating this validation and reload the mobile JS bundle. No new native module or APK rebuild is required.

Daphne's local `runserver` omits the optional ASGI WebSocket scheme field. Origin validation uses the ASGI default `ws` in that case; tests deliberately omit this field for Android-style local connections. Explicit `wss` scopes still require the matching HTTPS endpoint origin.

Automated checks include actual ASGI WebSocket communicators with an isolated PostgreSQL test database, transaction rollback, REST message/read delivery, private groups, authentication, Origins, frame-size limits, notifications, typing and Redis-outage persistence. Client tests cover auth frames, reconnect reconciliation, heartbeat timeout, background/foreground behavior, logout and shared mobile/web protocol parity. The automated transport tests use the in-memory channel layer; a live Render/Redis acceptance run remains necessary after deployment.
