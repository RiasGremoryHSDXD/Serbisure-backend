# Urgent fixes: local QA and rollout

Changes are uncommitted. The backend, mobile app and admin must be updated together: booking responses now expose `rate_amount` and `rate_period`, replacing the misleading `daily_rate` field. Short-term uses `day`; long-term uses `month`. No automatic multiplication or division converts an agreed amount.

## Local setup

The migrations were applied only to `localhost / serbisure_test_empty`. Restart Django, reload the mobile development app and reload the admin portal. No Neon deployment or remote migration was performed.

Existing long-term amounts are preserved but marked for review. For an unassigned pending post, open **Manage Post → Confirm Monthly Amount**, enter the actual monthly amount and save. This invalidates old pending proposals so participants must agree again. Expired posts require a new schedule. Existing accepted legacy terms are flagged as uncertain; do not treat their stored amount as a confirmed monthly agreement.

Migration `accounts.0018` preserves compatible restriction columns already present in legacy installations and adds them on fresh databases. Incompatible definitions stop migration without replacing values. `booking.0012` stops for duplicate assignments; investigate duplicates rather than deleting or faking the migration. Restriction-column rollback preserves those columns intentionally.

## Manual checks

Booking work setup is now stored in `tbl_booking.work_setup` (`stay_in` / `stay_out`). New posts must include it. Registration's profile preference remains in `user_tags` and the bio; it does not overwrite a booking's agreed setup. Duration and setup are independent: Long-term + Stay-out and Short-term + Stay-in are both supported. Test the separate Work Setup and Booking Type filters and check the setup in booking history, public posts and contract summaries. Legacy descriptions are backfilled only when the opening paragraph unambiguously states a setup; other rows remain null and display “Not specified.” No profile preferences or engagement types are used to guess missing values.

1. **Verification evidence:** Upload both required documents. Review them separately in admin. Approving one must leave the other pending; the user must remain unverified until the required documents are approved. OCR confidence must be a percentage from 0–100. Missing confidence stays unavailable. Facial-liveness/face-match scores must remain unavailable, not be derived from OCR; manual visual comparison is labeled explicitly.
2. **Compensation:** Try below-floor and wrong-period amounts when posting, proposing and accepting. All must fail on the server. Region X long-term minimum is PHP 6,500/month; NCR is PHP 7,800/month. Short-term PHP 600/day is a configurable SerbiSure platform minimum, not a declaration of statutory exemption. Unsupported long-term regions fail closed. Confirm the latest applicable wage order before a future production rollout.
3. **Pair cap:** Use the same verified homeowner–worker pair for three accepted short-term engagements with start dates in one Philippine calendar month. A fourth acceptance must fail, including through a proposal and when booked in advance. Reversing poster roles or cancelling an accepted engagement must not free a slot. Different pairs/months remain independent. Concurrent fourth acceptances cannot exceed three.
4. **Eligibility and proposals:** Try accepting as the poster, the same account type, a restricted/inactive user, or a user with pending/expired documents. All fail. Accept one proposal, then try a competing, rejected, cancelled or expired proposal. It cannot reopen the post or replace the assigned partner.
5. **Work state:** Completion before start fails. Starting before the scheduled time fails. At or after that time, start the engagement, then complete it. Both timestamps must be recorded. A migrated in-progress record without a start timestamp needs an explicit start action before completion.
6. **Long-term contract:** Accept a future long-term engagement. Both participants must see categories, the agreed monthly amount, start date and location plus **Download DOLE Standard Kasambahay Contract (PDF)**. The PDF is the official blank two-page form; users complete it, print it, both sign it and submit the physical copy to their Barangay Kasambahay Desk. Employer registration obligations remain external to the app; downloading does not signify signing or registration. No digital signature system was added.
7. **Units and admin:** Browse, saved posts, proposals, profiles and booking history must label daily/monthly amounts correctly. Budget filtering and price sorting compare a single selected rate period. Admin must show actual agreed amounts and pair counts, without a fabricated daily-to-monthly estimate.

## Automated checks

Run Django tests from the backend using `manage.py test --settings=Serbisure.test_settings`. These settings refuse remote hosts and create/drop a separate local PostgreSQL test database; they do not flush the application database. Run mobile `test:modules` and `typecheck`, and admin TypeScript checking and Vite build.

The contract is bundled under `booking/assets/`, served at `/api/v1/booking/contract-template/`, and included in the Vercel Python build configuration. The download is public because the template contains no participant data; booking terms remain authenticated and participant-scoped.
