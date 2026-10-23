# Administrative penalty points

The portal's **Penalty Points** page lists Homeowners and Kasambahays, shows their current monthly score, and opens a review with this month's cancellations and their original assessed points. Existing automatic cancellation rules and the Manila calendar-month reset are unchanged. At 3 points, booking/posting are restricted; deductions below 3 clear the points restriction. Account suspension, messaging restrictions, verification and availability are unchanged.

Officials review safety complaints through existing Support/Barangay conversations or barangay records. There is no new incident-ticket system or automatic verification. The adjustment form requires notes; selecting **I verified the safety / incident report** also requires a report/blotter reference. An optional cancellation link must belong to that resident and the current month. Original booking cancellation records are never rewritten to reflect waivers.

## Authority and API

Only active, unsuspended Admin/Superadmin accounts and Barangay officers with complete saved jurisdiction fields may use these endpoints. Barangay officers can read/adjust only nonstaff Homeowners/Kasambahays with matching normalized barangay, city and province. Their request parameters cannot broaden scope. Superadmins can read residents across all barangays and filter the scope. Staff targets are excluded. A resident's deactivation or account suspension does not erase their penalty history or prevent an authorized review.

Under `/api/v1/accounts/admin/penalties/`:

- `GET users/`: paginated residents and effective current-month scores.
- `GET users/<uuid>/`: current score, paginated current-month cancellations, five recent manual adjustments.
- `POST users/<uuid>/`: signed `points_delta` (-3..-1 or 1..3), required `reason` (10..2000 characters), `expected_points`, `expected_month`, unique UUID `request_id`, optional `booking_id`, `report_verified`, `incident_reference`.
- `GET history/`: paginated immutable adjustment records.
- `GET export/`: all matching history as a printable landscape A4 PDF table with User, Change, Score, Reason / incident notes, Report / cancellation, Adjusted by and Date / period columns. Includes full IDs, jurisdiction, active history filters, exporting official and page numbers. Column headers repeat on each page; long notes wrap and split across pages without being truncated. Uses the existing ReportLab dependency and bundled Nunito fonts. The portal downloads `penalty-adjustments.pdf` through the authenticated API.

The portal history uses the same seven-column structure, with horizontal scrolling on narrow screens. Long notes can be expanded in their own cell; full notes always appear in the PDF. The review dialog's recent adjustments use this table too.

Lists/history/export accept `search`, resident `role` and Superadmin `barangay`; history/export also accept `user_id`. Lists/review/history paginate 10 records per page. Historical audit visibility follows the resident's jurisdiction snapshot when the adjustment was recorded. Later profile edits/deletion do not rewrite past records. All responses are private/no-store.

The user list also accepts `points=with_penalties` for any current penalty, or `points=0`, `1`, `2`, `3` for an exact current-month score. Omit it for all scores. Filtering happens before pagination and combines with role, search and authorized barangay scope. Previous-month points count as zero. The score filter is shown only on **User points**; historical records retain their original snapshots.

The adjustment transaction locks current official/resident profiles, rechecks jurisdiction, refreshes monthly points, rejects stale scores/periods with HTTP 409, enforces 0..3 without clamping, and inserts the audit record in the same transaction. Logging failure rolls back the score. Identical request-ID retries return the original record without adding/deducting again; changed reuse is rejected. Existing `booking.changed` events refresh the mobile jobs/penalty display after commit. The portal does not automatically retry writes.

## Migration and audit storage

The staging admin and mobile clients target the Railway backend through `VITE_API_URL` and `EXPO_PUBLIC_API_URL`. Local API URLs supplied with Windows CMD `set` are temporary overrides for that terminal and its child processes; they are not source changes or Git content. The admin's `.env.local` and any mobile `.env` overrides are ignored by Git. Do not hardcode a developer's LAN address for a PR.

To return to the hosted backend, stop Vite / Expo and clear the override in the **same CMD terminal** before restarting:

```bat
set "VITE_API_URL="
set "EXPO_PUBLIC_API_URL="
```

For local testing, set `VITE_API_URL=http://127.0.0.1:8000` in the admin terminal, or `EXPO_PUBLIC_API_URL=http://192.168.1.14:8000` in the mobile terminal (replace the address if the PC's LAN IP changes). Shell values take precedence over `.env` files. PowerShell uses `$env:NAME='value'` and `Remove-Item Env:NAME` instead of CMD `set`. Do not include escaped colons or a trailing backslash in the URL.

For hosted releases, check the hosting / EAS environment also uses the hosted HTTPS URL, then rebuild the admin or mobile bundle. Merging code does not clear a previously configured deployment variable or change a URL embedded in an installed APK.

Deploy the backend migration before using the new page:

```powershell
python manage.py migrate
```

`accounts.0024_penalty_adjustment` adds `tbl_penalty_adjustment`. It contains immutable user/admin identity snapshots, jurisdiction, signed delta, before/after score, penalty month, reason, verified-report/reference, optional booking snapshot, timestamp and retry key. It has no foreign keys that could cascade/rewrite audit data during profile deletion. ORM writes are insert-only; PostgreSQL triggers reject UPDATE, DELETE and TRUNCATE (SQLite rejects UPDATE/DELETE). Django admin offers scoped read access only. No historical adjustments are fabricated or backfilled. Existing automatic penalties remain recorded on bookings; this table records every new manual adjustment.

Test cleanup disables the triggers only inside explicitly guarded disposable loopback test databases, after test execution. Production operations never disable these protections. Reversing the migration drops the audit table and must not be used as a routine rollback once records exist.

## Validation

```powershell
python manage.py test accounts.test_penalty_management booking.test_penalties chat.test_access_audit realtime.tests --settings=Serbisure.test_settings --noinput
```

Portal: `node --test tests/penalties.test.cjs`, `npm run build`. Regression checks cover scope tampering, staff/resident exclusions, stale/double submissions, month rollover, score bounds, verified-report references, audit-failure rollback, ORM/SQL immutability, PDF scope, long notes, empty exports, binary downloads and late client responses after a scope change.
