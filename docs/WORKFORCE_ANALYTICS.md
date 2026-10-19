# Kasambahay Workforce dashboard

Run `python manage.py migrate` when deploying backend changes. Migration
`accounts.0023_worker_status_history` creates the history table and seeds one
current-state record per existing Kasambahay. It does not modify user rows or
invent earlier status changes. No scheduler or cron job is needed.

## Current metrics

- Only active Kasambahays with the latest NBI and Police clearance submissions
  both Verified count toward the workforce. Expired clearances are excluded.
- Occupied uses `is_on_job=True`; Available uses `False`. Bookings are not queried.
- Homeowner verification requires both front and back of the National ID.
- Skills use `tbl_worker_profile.service_categories` and the same verified-worker
  denominator. A worker counts once per category. All-around is its own category;
  percentages across categories may total more than 100%.

## History

User saves and document saves record a new snapshot only when status, eligibility,
clearance validity or barangay changes. Document removal and account deactivation
also end eligibility. The mobile status API locks the worker, saves their toggle,
and writes history within one transaction. Failed history writes roll back the
toggle. No-op/repeated requests do not create duplicate transitions.

History includes `is_verified`, `clearance_valid_until`, and `worker_id_snapshot`
in addition to the requested status fields. These preserve past verification,
expiry and identity when a worker later loses verification, moves, or is deleted.
Deleted accounts leave history intact through a nullable FK and an ineligible
final snapshot. Required document changes never rewrite earlier snapshots.

The six-month chart uses each worker's latest event strictly before the next
month starts in Asia/Manila. The current month uses live verified-worker counts.
Months before the baseline show **No history**, rather than fabricated zeroes.

Use the normal model/API paths for changes. Raw SQL, `QuerySet.update()` and
bulk writes bypass Django model hooks and will not generate these events.
