# User-initiated support chat

Mobile homeowners and kasambahays can open Messages → Need help? and contact an active Superadmin or their own active barangay desk without receiving a message first. Contacts come from saved accounts through `GET /api/v1/chat/support-contacts/`; opening a contact does not create a message.

## Access rules

- The backend uses the authenticated account's saved barangay. Query parameters and street addresses cannot grant access to another barangay.
- Barangay matching ignores letter case, whitespace, and the `Brgy.`/`Barangay` prefix. Empty barangays and conflicting city/province values cannot match.
- Inactive or missing desks show an unavailable notice directing the user to SerbiSure Support. No account is fabricated when none exists.
- Barangay officers can send to and read chats with their own residents and Superadmins. Other Barangay accounts are blocked.
- Superadmins see only conversations addressed to their own account, as requested. They cannot read Barangay–resident or another Superadmin's conversations through their inbox.
- The same policy applies to text, images, typing, thread reads, read acknowledgements, reactions, deletions, inbox lists, and the portal user directory. Old messages do not grant access after a resident changes barangay.
- Support conversations hide booking offers and resident-profile navigation. Existing messages, notifications, and WebSocket delivery use the normal chat flow.

## Manual acceptance checks

1. Use existing test accounts in two barangays, with an active desk for each, plus a Superadmin. Restart Django and Metro after updating. Native rebuilds and migrations are not required.
2. Sign in as a homeowner who has never chatted with an administrator. In Messages, use Contact Superadmin, send a message, and verify it appears in that Superadmin's portal inbox with an unread badge.
3. Open the conversation in the portal and reply. Verify the mobile conversation updates and the portal unread badge clears. Repeat as a kasambahay.
4. Contact the user's own barangay desk and repeat the message/reply check. Verify support conversations do not offer booking actions.
5. Confirm the other barangay's desk is absent. A direct send, image upload, typing request, or thread read using that desk's ID must return HTTP 403.
6. Sign in to each barangay portal. Confirm its inbox and resident directory contain only its own residents, even with a different `barangay` query parameter.
7. Test a user in a barangay with no active desk. Confirm the unavailable notice appears and Contact Superadmin still works. Pull to refresh after an account is activated or deactivated.
8. Verify the Superadmin cannot see conversations sent only to the barangay desk or another Superadmin.

## Automated checks

Run from the backend checkout using its virtual environment:

```powershell
venv\Scripts\python.exe manage.py test chat.test_support_access chat.test_unread_inbox chat.tests realtime.tests --settings=Serbisure.test_settings --noinput
```

The test settings require a local PostgreSQL host and create an isolated temporary test database.
