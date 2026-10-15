# Database-only admin statistics and barangay directory

The previous UI imported a demo dataset (373 workers; Canitoan 110 employed/88 available; Pagatpat 70 employed/105 available). It seeded context from demo/localStorage rows, merged those rows back after requests, and ignored successful empty responses. Settings also mixed resident counts with individual document counts. These were browser-side numbers, not LGU accounts created in PostgreSQL.

The unused mock data file and predefined offline administrator accounts are removed. Login must succeed against Django with a real access token. Session restoration requires a stored real user ID, role and token. Cached barangay/statistic arrays are discarded and never read as a fallback. The user's local API-target configuration is preserved.

The authenticated dashboard endpoint supplies one snapshot for the cards and directory. Only an active `account_type=Barangay` record enables **Active LGU / Configured**. Resident addresses create directory rows with **No Account / Setup LGU**, including accurate counts even without an LGU account. Active LGUs with no residents have genuine zero counts; absent entries do not become demo rows. Creating a barangay account waits for a successful database response and refreshes the canonical snapshot instead of adding fabricated local counts.

Workers/citizens include active Kasambahay/Homeowner accounts. Employment counts each worker once, using their `is_on_job` flag or an Accepted/InProgress engagement, including workers who initiated the service post and workers who accepted an employer post. Available workers equal total minus employed. This represents hired/on-job status; it is not a separate legal employment registry. Verification columns count each citizen once with the existing bilateral required-document rules. The metrics field `pendingVerifications` remains a document queue count, while each directory row's `pending` is a citizen count.

Barangay matching uses the explicit barangay field, trims the Barangay/Brgy prefix and ignores case. It does not guess a barangay from street/city substrings or silently combine different spellings such as Canitoan and Canito-An. With no active LGUs, the **No LGU Coverage** scope correctly includes all residents. LGU accounts are restricted to their own jurisdiction; creating LGU accounts requires a superadmin. Statistics and coverage endpoints require authenticated portal roles.

The first render shows **Loading…** and a loading directory row. Failed or malformed requests clear statistics and show **Unavailable / Retry**, with no mock or zero fallback. Successful empty responses are authoritative. Request guards discard late responses after a different request, jurisdiction change or logout. Four-second polling skips overlapping requests in the same scope. Charts no longer inject Pagatpat/Canitoan options or a fabricated calendar series; options derive from actual registered locations.

Read-only verification of the local database found 3 workers, 2 homeowners, and no LGU accounts. The corrected endpoint returned 3 workers, 1 employed and 2 available. The actual directory contained Agusan (2 workers), Canito-An (1 worker) and Pagatpat (2 homeowners, 0 workers); all three had no LGU account. No live accounts were created, edited or deleted during this repair.

## Validation

- Eight backend regression cases cover real versus nonexistent/inactive LGUs, zero residents, one-person verification totals, bilateral booking initiators, duplicate employment, empty coverage, exact barangay matching, authentication and officer jurisdiction restrictions.
- Seven admin regression tests cover empty/malformed snapshots, stale request guards, poisoned browser cache, rejected offline logins, dashboard first paint and directory loading/error/account-status rendering.
- All 302 backend tests and seven admin regression tests pass, along with TypeScript and the final Vite production build. Vite reports a large-chunk advisory; no unrelated bundle restructuring was performed.
- The UI tests render the actual pages with controlled API/context inputs; live browser interaction has not been verified on the user's session.
- Refresh/restart Django to load the endpoint changes, then reload the portal. Old offline-only sessions lacking a real token will need to sign in against Django again.
- No commit or deployment was performed.

## Manual checks

- [ ] Reload the dashboard with network throttling: it should show Loading followed by the real worker count, never 373.
- [ ] Open Settings: existing resident locations show No Account unless an active LGU record exists.
- [ ] Simulate an API failure: verify Unavailable/error and Retry, without old demo rows.
- [ ] On an empty database, verify zero metrics and an empty directory.
- [ ] Create an LGU using the normal form: confirm a persisted Barangay account and its Active LGU state after a fresh request.
- [ ] Log in as an LGU officer and verify the assigned jurisdiction stays enforced.
