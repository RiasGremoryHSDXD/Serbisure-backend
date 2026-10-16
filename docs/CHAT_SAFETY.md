# Chat safety: masking and manual suspension

The capstone uses existing private Support/Barangay conversations for complaints and screenshots. There is no report queue, strike counter, automated penalty, evidence snapshot, or appeal case. Officials cannot browse residents' private conversations through this feature.

## Language masking

The backend masks dictionary matches before persisting chat text, image captions, booking-offer instructions, and proposal notes. The dictionary is in `chat/moderation_rules.py`; matching uses word boundaries, Unicode normalization, case-insensitive comparison and narrow punctuation handling. Examples: kill -> k*ll, fuck you -> f*ck you, gago -> g*go, yawa -> y*wa. English, Tagalog and Bisaya terms are included. This is a limited dictionary, not a contextual threat detector; it cannot recognize every threat, spelling or language. Images are not OCR-filtered. Existing messages are not rewritten.

Successful send responses include `language_warning` only for the sender when masking occurred. Normal thread/inbox and realtime responses do not include the warning. Mobile displays a Notice alert; admin shows a dismissible toast. Dictionary matches never create admin safety alerts or suspend anyone. Ordinary chat notifications still work without quoting message content.

## Manual state (accounts user model)

- `chat_suspended_until`: nullable aware timestamp. Future timestamps block outgoing messages, images, typing, booking offers and proposals to residents. Expired timestamps are treated as inactive without a scheduled task. Clearing the field lifts the pause immediately.
- `is_account_suspended`: blocks mobile/portal login, token refresh, existing JWT requests and websocket access until manually cleared. This freezes the whole account, including in-app support. Use a messaging pause when an appeal channel must remain open.
- `suspended_by`: nullable self-reference identifying the official responsible for the latest manual control change. This is current-state accountability, not a historical event ledger. Official deletion sets this reference to null.

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

## Migration and testing

Run `python manage.py migrate` when deploying the coordinated backend update. Accounts migration 0020 adds the three fields. Chat migration 0009 removes the superseded report/audit/blocked-attempt/restriction tables; migrations 0007/0008 remain as applied schema history. Retire any previously configured evidence-purge cron, because it is no longer part of this design. Review/back up any old report data before applying the removal to a hosted database. Local report test data was already reset by request.

Validation: `python manage.py test chat.test_moderation chat.test_support_access chat.test_unread_inbox chat.tests realtime.tests booking.tests --settings=Serbisure.test_settings --noinput`, admin `node --test tests/*.test.cjs` and `npm run build`, mobile `npm run typecheck` plus module/chat tests. Test settings enforce a loopback PostgreSQL host and use an isolated temporary database.

Manual check: send a matching word and verify both ends show masked text and only the sender sees Notice; send a screenshot directly to Support; pause a resident and confirm peer sends fail while own-desk and support sends succeed; confirm other-barangay controls fail; lift the pause; suspend/restore account access separately.
