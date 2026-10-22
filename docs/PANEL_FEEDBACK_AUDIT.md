# SerbiSure panel feedback implementation audit

Reviewed October 13, 2026 against the current Django/PostgreSQL backend, Expo mobile client and React admin portal. Source: `C:/Users/admin/Downloads/SERBISURE-PROPOSAL (1).docx`, minutes of the May 26, 2026 proposal defense. The recommendations are body text under each panelist's heading; the file contains no separate Word comments part. This audit treats them as recommendations to assess, not instructions that override the user's request. Only the requested WebSocket work was implemented in this pass.

**Conclusion:** Many core recommendations have code support, but the panel feedback is not fully addressed. Secure WebSocket communication is implemented in this change and prepared for Render; deployment/device acceptance remains to be done. Completion evidence, complaint/moderation workflows and research validation remain significant gaps. An approval of the proposal is not evidence that these features are complete.

“Implemented” below means current code exists, not that the manuscript, legal compliance or field validation has been approved. “Partial” identifies an actual implementation and the work still missing. “Not found” means no complete corresponding workflow was found in the reviewed source.

## Mr Dario C Minoza Jr

| Recommendation | Status | Code evidence and remaining work |
| --- | --- | --- |
| Consistent logo, palette and branding | Partial | Mobile `src/shared/theme/theme.ts` and portal use SerbiSure's orange/ink/canvas palette and logo assets. A full visual/device/accessibility audit of all screens is still needed. |
| Maintainable Django stack and structured PostgreSQL data | Implemented | Django REST, ORM models, PostgreSQL configuration, relational bookings/assignments/proposals and separate review sentiment metadata exist. No MongoDB dependency was found in the primary backend. |
| Secure password hashing | Implemented, with credential-setup gap | Django `set_password`/`create_user` use Django's configured/default password hashing, rather than storing plaintext or a raw unsalted SHA-256 digest. Barangay provisioning still uses the shared default `Lgu@12345`; unique temporary credentials/forced first-login change remain to be implemented. |
| Authentication, permissions, SQL injection and XSS protection | Partial | JWT, ORM queries, database constraints and role/ownership checks exist. Several older admin views in `accounts/views.py` still declare `AllowAny` (`AdminUserListView`, activity, monthly trend and verification statistics). Production CORS/host restrictions also need hardening. Django's presence alone does not make all endpoints secure. |
| Carefully secure WebSockets and real-time communication | Implemented in this change; deployment pending | `realtime/consumers.py`, commit-only events/signals, ASGI routing, private JWT-authenticated groups, browser-Origin allowlist, bounded frames, expiry, reconnects and client reconciliation are added. `render.yaml` uses ASGI and Redis. See `REALTIME_RENDER_SETUP.md` for live deployment acceptance. |
| Unit/backend/functionality testing and bug resolution | Partial | Automated backend/mobile/portal regressions and feature QA guides exist, including WebSocket tests. A documented bug log, formal test plan, tracked resolutions and complete manual device/UAT evidence are still needed for the manuscript/defense. |
| Bidding or budget-based hiring | Partial | `tbl_booking_proposal`, rate offers/counteroffers and bilateral chat booking offers provide negotiation with validated agreed rates. A complete homeowner minimum/maximum budget-range workflow was not found. |
| Pricing/availability filtering and sorting | Implemented | Mobile feed filters and posting/form logic include rates, service categories, setup, schedule/location and sorting. This does not establish distance matching or automatic AI wage recommendations. |
| Progress, time and completion tracking | Partial | Bookings have guarded Pending/Accepted/InProgress/Completed transitions plus `started_at`/`completed_at`. Live booking events now refresh affected clients. These timestamps are not an hours-worked timesheet or a task-by-task progress timeline. |
| Completion photos, confirmation logs and timestamped evidence | Partial / photos not found | Booking start/end timestamps exist. Chat images are not a structured proof-of-completion submission. A dedicated completion-evidence upload, counterpart confirmation/dispute flow and evidence log were not found. |
| Timeline notifications/progress indicators | Partial | In-app notifications, booking states and new real-time booking/notification events exist. A complete task timeline with milestones/proof and acknowledgment remains missing. |
| Re-evaluate whether in-app chat is essential | Requires justification in manuscript | Current chat is tied to validated booking offers and server acceptance, which provides a concrete purpose. The research team still needs to explain why retaining it supports the objectives and why external calls/Messenger cannot supply the same structured workflow. |

## Mr Kenneth C Ampolitod

| Recommendation | Status | Code evidence and remaining work |
| --- | --- | --- |
| Explain verification actors and submission-to-approval workflow | Partial | Document submission, OCR checks, independent document decisions, admin/barangay review and account verification rules exist in `verifications` and account models. A plain-language workflow diagram and user-facing explanation of human versus automated responsibilities still need complete documentation. |
| Handle unclear, mismatched, invalid or manipulated documents | Partial | OCR validation, retries, document matching/expiry and manual review provide checks. This is not proof of official ID authenticity or a validated face-liveness/identity match. Fake/manipulated credential detection and the limitations must be demonstrated honestly. |
| Chat harassment moderation, offensive-language detection, warnings and repeated-violation penalties | Not found as a complete workflow | Chat has authentication, participant checks, message validation and rate limits. No complete reporting, moderation queue, harassment detection, warning/escalation or repeated-violation suspension workflow was found. Review sentiment must not be presented as chat safety moderation. |
| Complaints, reports, accountability and legal concerns | Partial / complaint workflow not found | Ownership checks and some audit records exist. A complete user report/complaint intake, evidence review, resolution/appeal and accountability workflow was not found. |
| Explain ML's role | Partly implemented; explanation still required | Reviews call the configured Cebuano/Taglish Hugging Face sentiment model through private backend credentials. Booking matching uses rule-based scores; salary validation uses regional policy. Do not describe those latter features as trained ML without evidence. |
| Wage recommendations and employment law alignment | Partial | `booking/wage_policy.py`, explicit daily/monthly compensation, PSGC region/address, work setup and contract summary/download logic exist. Policy figures, source dates and legal review still need current verification; code cannot certify legal compliance. |
| Worker protection, privacy, data security and ethics | Partial | CV contact/family sharing choices, authenticated exports, server-owned contract terms and protected inference tokens are implemented. The public admin-endpoint gap above, shared initial LGU password, data retention, harassment/complaint handling and legal documentation remain important unresolved items. |
| User manual and application usage guidelines | Partial | Developer feature QA documents and in-app privacy/terms exist. A complete end-user manual covering both roles, barangay reviewers and admins was not found. QA instructions are not a substitute for an end-user manual. |
| Onboarding and first-time usability guidance | Partial | Guided registration, posting and chat-offer steps with validation/helper text exist. A full first-login tutorial/help workflow and documented usability evaluation were not found. |

## Dr Ma Esther B Chio

| Recommendation | Status | Code evidence and remaining work |
| --- | --- | --- |
| Support Cebuano/Bisaya and mixed Tagalog-English review language | Integration implemented; model-quality validation pending | Backend settings select `Rhoii/cebuano-taglish-sentiment` through the corresponding Space. `reviews/sentiment.py` validates label/confidence/probabilities. The integration itself does not establish accuracy across dialects or all mixed-language cases. |
| Localize the NLP/model and use appropriate multilingual tokenization/data | External model integration; provenance needs documentation | The deployed provider owns tokenization/model inference; the local repository integrates the API. Training datasets, preprocessing, tokenizer settings, model revision and the proponents' training/contribution must be documented with evidence from the model repository/research work. They cannot be inferred from the API name alone. |
| Explain conflicting words, negative context, ambiguity and mixed sentiment | Partial | Sentence-level model predictions and three probability scores exist, with no keyword/Neutral fallback. Dedicated labeled challenge cases and analysis of contextual errors are still needed. Case or text differences can affect predictions. |
| Explain token/word weights and positive/neutral/negative scoring | Partial | Provider probability/confidence validation exists. No per-token explanation method was found. Transformer inference must not be described as summing predefined positive/negative word weights; an explanation method would need to be selected, implemented and evaluated if required. |
| Validate machine interpretation against humans | Not evidenced as a completed study | Regression tests verify API parsing, security, saved-label integrity and failure behavior. They do not substitute for an independently human-labeled dataset, accuracy/F1/confusion matrix, annotator agreement, language subgroup evaluation and documented error analysis. No complete validation study was found in the reviewed repository. |
| Explain whether NLP is developed, reused or integrated from a third party | Integration is identifiable; manuscript work pending | This code integrates an existing Hugging Face Space/model via mobile → Django → provider → PostgreSQL. The proponents must distinguish their actual training work, integration work and original contributions, and credit external tools/data. |
| Improve technical explanation and manuscript style/formatting | Cannot assess from this attachment | The attached file is feedback/minutes, not the current thesis manuscript or presentation. Those documents must be reviewed separately before claiming the writing/formatting comments were addressed. |

## Suggested next order

1. Apply the prepared Render configuration and run the real device/portal WebSocket acceptance checklist.
2. Close the remaining admin authorization gap and replace shared barangay initial passwords with an accountable setup flow.
3. Implement a minimal, real complaint/report/moderation workflow and structured completion evidence/confirmation.
4. Complete the human-labeled NLP evaluation and honest model/contribution documentation.
5. Produce the end-user manual, final UAT/bug-resolution evidence and manuscript updates.

This audit does not silently expand the requested WebSocket implementation into those additional features. It records them as unfinished recommendations for a later authorized change.
