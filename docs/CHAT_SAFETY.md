# Chat safety: masking and manual suspension

The capstone uses existing private Support/Barangay conversations for complaints and screenshots. There is no report queue, strike counter, automated penalty, evidence snapshot, or appeal case. Officials cannot browse residents' private conversations through this feature.

## Language masking

The backend masks dictionary matches before persisting chat text, image captions, booking-offer instructions, and proposal notes. The dictionary is in `chat/moderation_rules.py`; matching uses word boundaries, Unicode normalization, case-insensitive comparison and narrow punctuation handling. Examples: kill -> k*ll, fuck you -> f*ck you, gago -> g*go, yawa -> y*wa. English, Tagalog and Bisaya terms are included. This is a limited dictionary, not a contextual threat detector; it cannot recognize every threat, spelling or language. Images are not OCR-filtered. Existing messages are not rewritten.

Successful send responses include `language_warning` only for the sender when masking occurred. Normal thread/inbox and realtime responses do not include the warning. Mobile displays a Notice alert; admin shows a dismissible toast. Dictionary matches never create admin safety alerts or suspend anyone. Ordinary chat notifications still work without quoting message content.

## Manual state (accounts user model)

- `chat_suspended_until`: nullable aware timestamp. Future timestamps block outgoing messages, images, typing, booking offers and proposals to residents. Expired timestamps are treated as inactive without a scheduled task. Clearing the field lifts the pause immediately.
- `is_account_suspended`: blocks mobile/portal login, token refresh, existing JWT requests and websocket access until manually cleared. This freezes the whole account, including in-app support. Use a messaging pause when an appeal channel must remain open.
- `suspended_by`: nullable self-reference identifying the official responsible for the latest manual control change. Official deletion sets this current-state reference to null; the independent access history preserves the original identity snapshot.

Messaging-paused residents can still exchange text/images with their own eligible Barangay desk and any active SerbiSure Support account. An unavailable desk falls back to the existing Support contact. Original chats and screenshots remain subject to normal chat participant permissions; no official gains access to another pair's conversation.

Barangay controls require a current active unsuspended officer and a resident with matching normalized, nonempty barangay, city and province. Officers cannot act on themselves, staff, superusers or other jurisdictions. Superadmins can manage other residents and staff platform-wide, but cannot suspend themselves. The server rechecks profiles under ordered row locks; client roles and barangay filters confer no authority. Suspended residents remain in the officer directory so their access can be restored.

## API and UI

- GET `/api/v1/accounts/admin/users/?access_management=1`: resident roster with current suspension state, constrained by the same server authority as mutations. Includes suspended/deactivated residents so they can be restored. Barangay accounts cannot widen scope through query parameters; Superadmins can filter by registered barangay. The response is private, no-store.
- GET `/api/v1/chat/safety/status/`: current user's effective messaging pause.
- GET `/api/v1/chat/safety/users/<uuid>/`: authorized official reads current access state.
- POST the same user URL: `action` is `pause_chat`, `resume_chat`, `suspend_account` or `restore_account`.
- `pause_chat` requires an ISO timestamp `until` strictly in the future and within 30 days; other actions reject an expiry. The portal offers 1 hour, 24 hours, 7 days and 30 days.
- The sidebar exposes **Account Access** immediately below **Users**. This separate page lists eligible Homeowners and Kasambahays in a table with name/barangay search, role and effective-access filters, and 10 users per page. Every row has one **Manage access** button; resident suspension controls no longer appear in the chat directory. Authorized staff-account controls remain in staff profiles, outside this resident-only table. Each action opens a keyboard-accessible native modal with state, action, duration, and a confirmation before the save. Controls are disabled during loading/saving and errors remain visible. Action requests do not automatically retry.
- Restoring account access does not implicitly clear a separate chat pause; lifting a chat pause does not restore a fully suspended account.
- Booking cancellation strikes and booking restrictions are unchanged.

## Read-only account access history

The Account Access page has **Accounts** and **Access history** views for both Superadmin and Barangay accounts. History has name/official/barangay search, an action filter, ten entries per page, and expandable previous/new values. It has no create, edit or delete controls. Successful access changes create records automatically; officials cannot submit arbitrary log entries.

`chat.AccountAccessAudit` (`tbl_account_access_audit`) stores one immutable event for each actual manual state transition: messaging pause, messaging resumption, account suspension, or account restoration. Each event snapshots actor and target UUIDs, names, roles and barangays; normalized target jurisdiction and staff eligibility; previous/new account-suspension and pause-expiry values; and the event timestamp. No private conversation content is recorded. UUID snapshots are intentionally not foreign keys, so deleting or renaming a profile cannot cascade into history. The target's jurisdiction at the time of the action determines local visibility even if the target subsequently moves.

The access update and its audit insert run in the same transaction under the existing ordered account row locks. Audit insertion failure rolls back the access update; realtime events publish only after commit. Failed/unauthorized requests, reads, and unchanged duplicate actions do not create successful-change entries. Natural pause expiry needs no background mutation: the original event already records its expiry. Historical changes before migration 0010 are not reconstructed or backfilled.

GET `/api/v1/chat/safety/history/` returns `{count, next, previous, results}` in newest-first order, ten results per page. Supported query parameters are `page`, `search` (up to 200 characters), `action`, resident `role`, `user_id`, and Superadmin-only `barangay`. Active, unsuspended Superadmins can read all access history, including staff actions. Barangay officers can read only nonstaff resident events with a complete, matching normalized barangay/city/province snapshot. Client parameters cannot widen this scope. Responses use `Cache-Control: private, no-store`. Only GET/HEAD/OPTIONS are enabled; POST/PUT/PATCH/DELETE are rejected. This history grants no access to residents' chats.

Model and queryset operations reject edits/deletion. PostgreSQL triggers independently reject UPDATE, DELETE and TRUNCATE, including direct SQL; SQLite has corresponding UPDATE/DELETE triggers. Django admin exposes only jurisdiction-scoped read access. This protects ordinary application/database operations; a database owner can still deliberately alter the schema or disable triggers and should be restricted operationally. The isolated realtime test fixture briefly disables the trigger only during test-table cleanup, after checking the disposable database name and loopback host. It remains enabled during tests and application execution.

## Migration and testing

Run `python manage.py migrate` when deploying the coordinated backend update. Accounts migration 0020 adds the three fields. Chat migration 0009 removes the superseded report/audit/blocked-attempt/restriction tables; migrations 0007/0008 remain as applied schema history. Retire any previously configured evidence-purge cron, because it is no longer part of this design. Review/back up any old report data before applying the removal to a hosted database. Local report test data was already reset by request.

Chat migration **0010_account_access_audit** adds only the new access-history table, indexes, constraints and append-only database triggers. Apply it before deploying the matching portal/backend code. It does not change existing suspension state or document-verification audit records. A deliberate migration reversal removes its protection and drops this table, so do not reverse it as a routine rollback after records exist.

Validation: `python manage.py test chat.test_moderation chat.test_support_access chat.test_unread_inbox chat.tests realtime.tests booking.tests --settings=Serbisure.test_settings --noinput`, admin `node --test tests/*.test.cjs` and `npm run build`, mobile `npm run typecheck` plus module/chat tests. Test settings enforce a loopback PostgreSQL host and use an isolated temporary database.

Manual check: send a matching word and verify both ends show masked text and only the sender sees Notice; send a screenshot directly to Support; pause a resident and confirm peer sends fail while own-desk and support sends succeed; confirm other-barangay controls fail; lift the pause; suspend/restore account access separately.

Access history checks: `python manage.py test chat.test_access_audit chat.test_moderation chat.test_support_access chat.test_unread_inbox realtime.tests --settings=Serbisure.test_settings --noinput`; portal `node --test tests/access-history.test.cjs tests/account-access.test.cjs` and `npm run build`. Check that each successful access change appears in Access history, authorized scopes remain isolated, and failed logging never leaves an unaudited suspension.
