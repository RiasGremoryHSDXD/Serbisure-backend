# Automatically generated Kasambahay CV

Registration Step 2 uses four short pages: work preferences, experience and family, availability, and optional extras/sharing. Civil status remains a required choice. Children are recorded as an exact integer from 0 to 99; counts above five are allowed. Neither field changes eligibility, feed ordering, verification, or trust scores. Workers choose whether family details and phone numbers appear on the shared CV; both sharing settings default to off.

Structured preferences are saved in `tbl_worker_profile`, linked one-to-one to `tbl_user_profile`. Registration creates both records atomically. Fields include service categories, work setup, engagement preference, separate PHP monthly/daily expectations, experience level/duration/summary, practical skills, civil status, child count, available date/days/shifts, preferred work areas, optional education and training, references-on-request, and sharing choices. Languages remain on the user profile. Profile preferences are not agreed booking or contract terms; wage enforcement on actual offers is unchanged.

## Endpoints

- `GET/PATCH /api/v1/accounts/worker-profile/`: authenticated Kasambahay's own structured details. Updates cannot target another account. Category and setup edits synchronize profile tags; editing tags also synchronizes the corresponding CV preferences.
- `GET /api/v1/accounts/worker-cv/<user_id>/`: authenticated, privacy-filtered preview for an active Kasambahay. Shows current verification and actual completed jobs/reviews. New workers show no reviews rather than invented ratings or percentages.
- `GET /api/v1/accounts/worker-cv/<user_id>/export/?file_format=pdf`: generates a fresh PDF from saved data, with the same privacy rules as the preview.
- The same export endpoint accepts `file_format=csv` for the worker's own CSV only. CSV is UTF-8 with a BOM, quotes values correctly, and escapes spreadsheet formula prefixes. This is a single-worker export; it does not add a bulk admin workforce export.
- The old `/resume/` endpoint is read-only for owners retrieving legacy files. Manual uploads return 405. Shared profiles no longer issue links to legacy files that may contain outdated personal information. Existing uploaded files are not deleted.

Full addresses, exact birth dates, email, clearance images/numbers and religious information are excluded from CV exports. Family and contact values are omitted unless the worker opts in. Experience, skills, training and family details are marked self-reported. Previously downloaded copies cannot be recalled when sharing settings change.

## Mobile behavior

The profile card is **Your SerbiSure CV**, with **Preview my CV**. Preview offers **Edit Details** on its own row, then **View PDF** and **Download PDF** side by side; the CSV button is removed. Other people's profiles offer **View CV**, with both PDF actions inside and no editing action. Edit uses the same guided form as registration. Loading, save, and export errors retain entered details. Requests send authentication headers; tokens are never appended to URLs.

Android **View PDF** fetches the PDF into private app cache, obtains a FileProvider content URI and launches `ACTION_VIEW` with MIME type `application/pdf` and temporary read permission. It opens an installed PDF viewer without a folder picker or manual save. An older APK missing `ExpoIntentLauncher` shows an installation message before downloading; it does not import a missing native module. No installed PDF viewer produces an actionable alert and cleans the failed temporary file. iOS uses its native document share/preview sheet (direct Quick Look is not implemented). Web opens an authenticated PDF Blob in a new tab; popup blocking produces an actionable error. Successfully opened native files remain in app cache for the receiving app and are purged after 24 hours on a later view. Failed and stale views remove their temporary files. The owner-only CSV API remains for compatibility but has no mobile button.

**Download PDF** explicitly saves a copy. Android reuses the tested folder-picker save flow: choose a writable folder and grant access; the **PDF saved** alert appears only after writing succeeds. Cancellation is quiet and partial files are cleaned on error. iOS offers its native save/share sheet. Web starts a standard PDF file download. All actions are disabled while preparing or saving a CV, preventing concurrent requests. Adding this button requires only reloading the current debug app; it adds no native dependency. TypeScript and all 52 mobile tests pass; check the two-row footer and real folder save on the device.

Old accounts can preview a basic CV immediately and add details with **Edit Details**. Existing category/setup tags are reused where recognized. Salary, child count, civil status, experience and training are not guessed from the biography or assigned invented defaults. Unrecognized legacy roles remain existing tags until the worker edits them; they are not reclassified as different services.

## Setup and validation

- Apply `accounts.0019_tbl_worker_profile` before running the updated backend. The local development database has been migrated; no family details were invented for existing users.
- `reportlab>=4.4,<5` is in backend requirements and installed locally. Nunito regular/bold fonts and their license are bundled under `accounts/assets`, included in the Vercel build configuration with the existing booking assets. No cloud deployment was performed.
- Expo SDK 51 compatible `expo-file-system`, `expo-sharing`, and `expo-intent-launcher` dependencies are installed. Android PDF viewing needs an APK containing `ExpoIntentLauncher`. The updated development APK was built successfully at `front_end_2/SerbiSure-Frontend/android/app/build/outputs/apk/debug/app-debug.apk`; install it over the existing development build and reload Metro. No device installation was performed. iOS native sharing requires a build containing `ExpoSharing`. Device PDF viewer/share-sheet verification is still required; automated tests simulate the native adapters.
- Tests cover atomic registration, category grouping, zero/multiple children, preserving unrelated details, private/shared family fields, contact redaction, unsupported values, role authorization, current PDF/CSV content, legacy behavior, spreadsheet injection and mobile payload/date validation.
- The illustrative sample PDF is visually checked and contains fictional data, not an existing worker's personal details. Long optional summaries/training may extend a CV to additional pages.
- Dependency installation reported 75 npm audit findings across the dependency tree. No broad dependency upgrades or `audit fix --force` were applied as part of the CV change.
- Download regression checks cover Android PDF/CSV authenticated requests and exact Base64 bytes without loading sharing, cancellation, expired sessions, partial-file cleanup, stale downloads, and iOS missing-module/success behavior. All 48 mobile module tests and TypeScript checking pass after the fix.

## CV layout redesign QA

The design guide was adapted to the actual backend ReportLab renderer, rather than introducing on-device HTML generation or `expo-print`. PDF generation stays in Django and uses the existing embedded Nunito fonts. It keeps A4 with 56pt horizontal and 48pt vertical margins. All text is at least 9pt, with a larger name, readable service headline, a compact facts strip, skills, availability, experience, background and a quiet trust/disclaimer area. The photo is cropped without stretching and clipped to a true circle. Missing or failed photos do not leave a blank slot. ReportLab supports reliable page numbers, so real page numbers are retained.

Pure formatting in `accounts/cv_presentation.py` is shared between the mobile preview JSON and PDF. Working days are ordered and grouped, shifts are ordered/capitalized, rates retain explicit daily/monthly units and omit unnecessary decimals, and dates use Philippine calendar time. Empty optional fields and zero activity are omitted. First-time workers keep their actual experience label without an invented duration. Pending/unverified status moves to the trust area; only genuinely verified users receive a header label. Shared zero children remains visible because it is an actual value; the guide's suggestion to hide zero was not adopted. Family/contact sharing preferences remain effective for every display and export. CSV content and its owner-only API are unchanged.

Validated: 294 backend tests, 52 mobile module tests, TypeScript compilation, and a successful Android development APK build. The one-page fictional sample and a two-page long-name/long-summary fixture were rendered and visually inspected; neither clips or overlaps text, and the photo is circular. No device/emulator testing or release APK build was performed. The sample uses a fictional geometric avatar, not a real worker's photo.

- [x] Typical first-time profile fits on one A4 page.
- [x] Long name and long escaped summary paginate without clipping or orphan headings.
- [x] No-photo layout uses the full header width.
- [x] Text is at least 9pt; rates and labels remain readable.
- [x] CSV button is absent; **View PDF** replaces **Download PDF**.
- [x] Authorization remains in headers, never in the viewer URL.
- [ ] Android: install the new development APK, open a worker CV, tap **View PDF**, verify it opens without a folder picker, and return to the app.
- [ ] Android: test offline, expired session and no installed PDF viewer; verify clear errors and retry.
- [ ] Android: edit profile details and sharing choices, then verify a new preview/PDF reflects them.
- [ ] iOS: test its document share/preview sheet on a build containing `ExpoSharing`.
- [ ] Web: allow popups and verify the PDF opens in a new tab.

Dependency installation for the viewer reported 85 npm audit findings across the dependency tree (2 low, 31 moderate, 50 high, 2 critical). No broad dependency updates or force fixes were applied. Profile expectation rates are rendered as entered; actual offer/booking wage enforcement is unchanged.
