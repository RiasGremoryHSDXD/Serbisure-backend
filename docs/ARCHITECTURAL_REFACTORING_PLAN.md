# Serbisure Backend — Structural Refactoring Plan

> **Revision scope:** This document is a static-analysis refactoring plan only. It does not authorize implementation changes. Its required outcome is a DRY, SOLID structure with single-responsibility functions while preserving every existing endpoint, route name, HTTP method, request payload, response body, status code, response header, authentication behavior, and observable side effect.

## Scope and contract guardrails

This is a static analysis of `backend/Serbisure-backend`. No application code, database schema, migration, route, request field, response field, or status code was changed as part of this analysis.

The current URL configuration is the contract inventory: `Serbisure/urls.py` mounts `testing_database`, `accounts`, `verifications`, `booking`, `chat`, `reviews`, and `notifications`. The existing `docs/API_REFERENCE.md` documents only a subset of those routes, so it must not be treated as the complete compatibility specification.

The refactoring target is internal layering only:

- Keep every current URL path, URL name, HTTP method, request shape, response shape, status code, authentication behavior, and externally visible error text unchanged.
- Preserve existing database table names, model field names, serialized field names, and migration history.
- Move behavior behind compatibility-preserving adapters before removing old implementations.
- Treat any permission tightening, response cleanup, error-message normalization, cache-key change, or asynchronous processing change as a separately approved behavior change unless characterization tests prove it is invisible to clients.

## 1. Vulnerability Map

### 1.1 Structural hotspots and monolithic functions

The following functions combine routing, validation, authorization, database access, business rules, formatting, external I/O, and response construction. They are the highest-value extraction points.

| Area | Location | Static finding |
|---|---|---|
| Account administration | `accounts/views.py:290-402`, `:413-542`, `:552-608` | Dashboard statistics, activity, and trend endpoints each build their own location scope, ORM queries, aggregation, avatar formatting, and response DTOs. |
| Account registration | `accounts/views.py:53-111` | Idempotency validation, cache lookup/write, serializer execution, token generation, and response construction are in one handler. |
| Booking feed | `booking/views.py:88-206` | All query filters, category normalization, numeric parsing, location search, keyword search, and sorting live in one view method. |
| Booking proposals/lifecycle | `booking/views.py:451-521`, `:559-619` | Authorization, state transitions, assignment writes, proposal fan-out updates, notifications, and serialization are mixed together. |
| Chat image send | `chat/views.py:156-286` | Multipart validation, recipient lookup, Cloudinary upload/deletion, database write, notification, idempotency, and response serialization are in one method. |
| Chat reaction/inbox | `chat/views.py:308-400`, `:487-589` | Reaction state machine and inbox aggregation are implemented directly in HTTP handlers; inbox performs per-partner queries. |
| Review analytics | `reviews/views.py:176-236`, `:285-335` | Aggregation, profile presentation, completed-job queries, and response shaping are duplicated between summary and analytics. |
| Verification queue/review | `verifications/views.py:267-383`, `:397-584` | Filtering, unsubmitted-user synthesis, package rules, state transitions, audit logging, profile status updates, notifications, and serializers are combined. |
| OCR/AI | `verifications/ocr_service.py:164-311`, `verifications/services/document_processor.py:24-128` | Legacy synchronous parsing and the newer asynchronous OCR/AI pipeline coexist, with overlapping responsibilities. |
| Cross-cutting services | `verifications/services/audit_logger.py:36-157`, `matching_service.py:38-171` | Audit and matching code is already service-shaped but remains large and couples persistence, normalization, and policy. |

### 1.2 Duplicated idempotency and cache logic

The same sequence is implemented independently in multiple endpoints:

1. Read `Idempotency-Key`.
2. Validate it with `core.utils.check_valid_uuid`.
3. Build an endpoint-specific cache key.
4. Return the cached body/status if present.
5. Execute the operation.
6. Cache the response for a fixed TTL.

Occurrences:

- Registration: `accounts/views.py:53-111`, using the raw UUID as the cache key for 24 hours.
- Booking post: `booking/views.py:37-70`, using the raw UUID for 24 hours.
- Review create: `reviews/views.py:61-113`, using `review_create_<uuid>` for 24 hours.
- Text chat send: `chat/views.py:79-133`, using `chat_send_<uuid>` for one hour.
- Image chat send: `chat/views.py:145-286`, using `chat_send_image_<uuid>` for one hour.
- Resume upload: `accounts/views.py:886-905`, using `resume_idemp_<user>_<uuid>` for 24 hours and making the key optional.

The validation response differs (`details` for registration/resume versus `detail` elsewhere), and the TTL differs. A shared implementation must therefore support endpoint policy descriptors rather than force one response. The current raw-key implementations also allow cross-endpoint or cross-user cache collisions if a UUID is reused; this is a security and correctness concern. A future internal key namespace can fix this without changing the client-visible contract, but it must be introduced with replay tests.

### 1.3 Repeated validation and authorization rules

| Concern | Repeated locations | Refactoring risk |
|---|---|---|
| UUID validation | `accounts/views.py`, `booking/views.py`, `chat/views.py`, `reviews/views.py`, `core/utils.py` | Different callers return different error shapes and statuses. Centralize the primitive, not the response policy. |
| Verified-user gate | `booking/views.py:37-55`, proposal creation, `reviews/views.py:61-77`, `verifications/views.py:23-44` | The same state concept is enforced in multiple views with different messages and status codes. Extract a policy service while retaining each endpoint's current error contract. |
| Participant/owner checks | Booking lifecycle views, review serializer, chat reaction/read/delete views | Authorization is implemented inline and inconsistently as `Response`, `ValidationError`, or implicit queryset filtering. |
| Self-target checks | `chat/serializers.py` text/image validation and `chat/views.py:173-181` | Recipient validation is duplicated in both the serializer and image view. Keep one domain rule and one boundary adapter for its current error shape. |
| Rate-limit messages | `accounts/views.py:113`, `:160`, `:735`, `:763`, `:787`, `:828`, `:911`; `booking/views.py:75`; `reviews/views.py:40`; `chat/views.py:67`; `verifications/views.py:69` | The time calculation is repeated, but wording varies between “attempts” and “requests”. Use a shared formatter with explicit wording configuration. |
| Required document types | `accounts/models.py:276-322`, `verifications/views.py:109-124`, `verifications/views.py:471-491`, `views_admin.py:33-52` | Required-document policy is spread across model property, views, and admin workflow. Centralize policy and preserve the derived status values. |

### 1.4 Duplicated database queries and query construction

#### Location and Barangay scoping

The following code independently discovers active Barangay accounts, normalizes names, handles `ALL`/`UNASSIGNED`/`NO_LGU`, and searches `barangay`, `city`, and `street`:

- `accounts/views.py:185-280` — admin user list.
- `accounts/views.py:290-402` — dashboard statistics.
- `accounts/views.py:413-542` — dashboard activity.
- `accounts/views.py:552-608` — monthly trend.
- `accounts/views.py:679-719` — active Barangay endpoint.
- `verifications/views.py:202-265` and `:267-383` — verification queue and unsubmitted users.
- `booking/views.py:88-206` — booking feed filters.

This creates drift risk: different endpoints use exact, case-insensitive, or substring matches and do not all apply the same scope rules. Introduce a read-only location-scope component that returns the exact queryset predicate and normalized display values, with endpoint-specific options where the current behavior differs.

#### Booking list status filters

`MyBookingsView.get_queryset` and `MyAssignedBookingsView.get_queryset` in `booking/views.py:393-443` contain the same `active`, `completed`, `cancelled`, and arbitrary-status mapping. Extract `BookingQueryService.filter_by_requested_status` and retain both existing base querysets.

#### Review aggregation

`ReviewSummaryView.get` and `ReviewAnalyticsView.get` both calculate average rating, sentiment counts, and rating counts using nearly identical loops (`reviews/views.py:176-236` and `:285-335`). Extract one aggregation result object; let each controller keep its current envelope and additional analytics fields.

#### Admin verification package rules

The legacy review endpoint (`verifications/views.py:397-584`) and the newer admin action endpoint (`verifications/views_admin.py:95-192`) both update document status, assign the reviewer, write an audit log, update profile verification, and create notifications. Their request fields, supported actions, permission classes, response shapes, and companion-document behavior differ. They require one domain state-transition service with two compatibility adapters, not two independent implementations.

### 1.5 Repeated presentation and integration logic

#### Cloudinary and avatar URL generation

`cloudinary.utils.cloudinary_url` appears across accounts serializers/views, booking serializers, review serializers, chat serializers/views, and verification serializers/views. The code repeats authenticated signing, fallback avatars, URL passthrough checks, PDF/raw-resource handling, image transformations, and broad exception swallowing.

Create a media gateway with named operations such as profile image, document image, chat image, and resume URL. Each operation must encode the current resource type and transformation options so centralization does not accidentally change signed URL behavior.

#### User identity and display formatting

Name construction (`first_name + last_name` or username fallback), role normalization, default city/address, Barangay inference, and fallback avatar URLs are repeated in account admin, verification queue, booking serializers, review serializers, chat inbox, and admin login. Extract presentation helpers or boundary mappers; do not expose model objects directly from services.

#### Notifications

Booking, review, and chat views use `notifications.services.send_in_app_notification`, but verification code and the document processor call `tbl_notification.objects.create` directly (`verifications/views.py:59`, `:496`, `:539`; `verifications/views_admin.py:47`, `:146`, `:178`; `verifications/services/document_processor.py:120`). This bypasses one error-handling path and makes sender/default-state behavior inconsistent. The notification service should be the only write gateway after characterization tests confirm that notification failures remain non-blocking.

#### Token claims

`UserRegistrationSerializer.get_token` and `CustomLoginSerializer.get_token` (`accounts/serializers.py:227-265` and `:280-315`) manually populate largely overlapping JWT claims. A shared token-claims builder should be used by both while preserving the exact existing claim names, defaults, and signed profile URL behavior.

### 1.6 Serializer and model layer leakage

Serializers are not limited to input/output mapping:

- `DocumentUploadSerializer.create` (`verifications/serializers.py:33-126`) performs OCR, Cloudinary upload, rejected-document replacement, database persistence, transaction callback registration, and user-status updates.
- `BookingDetailSerializer` queries reviews, assignments, and proposal counts for each object (`booking/serializers.py:181-266`).
- `CreateReviewSerializer.validate` performs booking state lookup, assignment lookup, participant authorization, reviewee derivation, and duplicate detection (`reviews/serializers.py:21-70`).
- `ChatMessageSerializer` and `ChatInboxSerializer` generate signed media URLs and reaction summaries (`chat/serializers.py:170-281`).
- `tbl_user_profile.verification_status` queries related documents from a model property (`accounts/models.py:276-322`), while views also try to assign and save that property.

This violates single responsibility and makes query count, transaction boundaries, and error behavior hard to reason about. Keep serializers as contract adapters; move orchestration to services/selectors, but preserve serializer validation errors and serialized fields through adapter tests.

### 1.7 N+1 query and performance hotspots

These are static N+1 risks, independent of whether the current dataset exposes them in production:

- `accounts/views.py:413-542`: one assignment lookup and additional short-term count per booking.
- `booking/serializers.py:214-266`: rating aggregate, assignment lookup, review existence, and proposal count per serialized booking.
- `booking/views.py:630-733`: one review aggregate per worker recommendation and repeated avatar generation.
- `chat/views.py:487-589`: one user lookup, last-message query, unread count, sent count, and media signing per partner.
- `verifications/serializers.py:152-580`: many `SerializerMethodField` lookups and signed URL operations across queue items.
- `tbl_user_profile.verification_status`: related-document evaluation can be repeated for every access.

Selectors should provide `select_related`/`prefetch_related` querysets and precomputed aggregates. Any optimization must be validated against response ordering, null handling, and exact field values.

### 1.8 Error-handling inconsistencies

- Broad `except Exception: pass` blocks suppress Cloudinary, notification, OCR, and serializer-processing failures. This makes incident diagnosis difficult and can leave partially completed workflows.
- Missing resources are not represented consistently: for example, `MarkMessageReadView.get_object` raises `ValidationError` for a missing message (`chat/views.py:609-625`), while other endpoints return 404 responses.
- Some domain failures are raised from serializers, some are manually returned from views, and some are silently converted into fallback data.
- `verifications/services/document_processor.py` catches fetch/processing failures and may only log them, while the upload path has already returned a successful response.

Introduce typed domain exceptions and an exception-to-response adapter only after capturing each endpoint's current status and body. Do not normalize the public error contract as part of the structural refactor.

### 1.9 Authentication and access-control inconsistencies

The newer verification admin endpoints use `IsAuthenticated, IsAdminOrBarangay` (`verifications/views_admin.py:55-239`), but legacy/admin-facing endpoints use `AllowAny`:

- `accounts/views.py:179`, `:283`, `:405`, `:545`, `:611`, `:679`.
- `verifications/views.py:191-584`.
- `verifications/views_admin.py:222-239` for audit logs.

This exposes administrative data or actions unless an upstream control exists outside this repository. It is a significant security finding, but tightening it would be an external behavior change. First characterize current frontend access and preserve it during mechanical layering; then handle authorization hardening as a separately approved security change.

Authentication is also duplicated between `CustomLoginSerializer.validate` and `AdminLoginView.post` (`accounts/serializers.py:318-364`, `accounts/views.py:619-676`): identifier resolution, password verification, active-account checks, role checks, JWT creation, and avatar generation are independently implemented. Centralize credential resolution and token creation while retaining the separate mobile/admin role policies and current generic error messages.

### 1.10 Duplicate OCR/AI pipelines

There are two OCR implementations:

- Legacy synchronous pipeline: `verifications/ocr_service.py`, imported by `DocumentUploadSerializer`.
- Newer service pipeline: `verifications/services/ocr_service.py`, `groq_service.py`, `matching_service.py`, and `document_processor.py`.

`DocumentUploadSerializer.create` first calls `process_document_ocr` synchronously and writes its result, then registers `process_document_async` after commit. The asynchronous pipeline can subsequently overwrite OCR fields with a different extraction/matching result. This is the largest functional duplication and a major source of race/timing ambiguity.

The target is one `DocumentProcessingService` facade with provider adapters for Google Vision, Tesseract, Groq text, and Groq vision. The old pipeline must not be deleted until response-field equivalence and persisted-field equivalence are verified for all supported document types and fallback conditions.

### 1.11 State-model inconsistency requiring special care

`tbl_user_profile.verification_status` is a Python property derived from related documents (`accounts/models.py:276-322`), not a declared model field. Several workflows assign it and call `save(update_fields=['verification_status'])` (`verifications/views.py` and `verifications/views_admin.py`). This is a contract-sensitive defect/risk: it may not persist and may raise a Django field error depending on execution path. Do not “fix” it opportunistically during layering. First add characterization tests, decide whether document-derived status or a persisted field is authoritative, then make that a separately reviewed domain-state change.

## 2. Target Architecture

### 2.0 Required responsibility boundaries

The target structure is intentionally separated into the four layers required for a safe, contract-preserving refactor.

| Layer | Responsibility | Must not contain |
|---|---|---|
| Routing | Stable URL paths, URL names, and mapping to compatibility controllers. | Business rules, ORM logic, response shaping, or permission decisions. |
| Controllers | HTTP concerns only: request extraction, current permission/throttle/parser configuration, service/selector invocation, and exact current `Response` construction. | Domain state transitions, provider calls, repeated validation, or query assembly. |
| Services | Business rules, transactions, idempotency orchestration, authorization policy evaluation, state transitions, and side-effect commands. | DRF `Response` objects, route details, or serializer-specific output envelopes. |
| Middleware and shared platform | Truly cross-cutting transport concerns: CORS, request/correlation context, exception adaptation, throttling helpers, cache/idempotency support, media gateways, and audit context. | Domain-specific booking, review, chat, or document policy. |

Read-only selectors/repositories support the service/controller layers by owning ORM query construction, prefetch plans, filters, ordering, and aggregates. They are not a second business-logic layer.

### 2.0.1 Contract-preservation rules for every extraction

An implementation phase may move code only when all of the following remain unchanged for the affected endpoint:

1. URL path, route name, HTTP method, parser, permission result, and throttle result.
2. Request field names, optionality, accepted content type, and validation order where it affects the response.
3. Success payload keys, nesting, value types, null/empty handling, ordering, HTTP status, and headers.
4. Error payload keys and wording, including existing distinctions such as `detail` versus `details`.
5. Idempotency-key validation, replay body/status, cache lifetime, and observable side effects.
6. Database table/column names, migrations, and externally observed state transitions.

The refactor must use compatibility controllers and serializers until parity tests demonstrate these invariants. Security hardening, API cleanup, permission changes, and schema redesign are intentionally outside this structural plan unless separately approved.

### 2.1 Layering rules

```text
URL configuration
        |
Thin DRF controllers / compatibility views
        |
Serializers and request/response DTO adapters
        |
Domain services (writes, policies, state transitions)
        |
Selectors / repositories (read queries and prefetch plans)
        |
Models and external gateways (Cloudinary, OCR, cache, notifications)
```

Rules for the target state:

1. URL modules contain routing only and continue importing the existing public view class names during migration.
2. Controllers authenticate, parse the request, invoke one service/selector, and return the exact existing response.
3. Serializers validate and render the existing API contract. They do not start threads, upload files, send notifications, or run cross-domain queries.
4. Services own business rules, transactions, idempotency orchestration, state transitions, and domain side effects.
5. Selectors own read-only ORM queries, filters, ordering, and prefetch/annotation plans.
6. Integrations hide Cloudinary, OCR providers, cache, JWT construction, and notification persistence behind small interfaces.
7. Domain modules may depend on shared primitives and their own models; cross-domain reads go through an explicit selector/service boundary.
8. Migrations and database table/column names remain unchanged unless a later, separately approved schema project is opened.

### 2.2 Proposed package structure

The following is a target shape, not an instruction to create all files at once:

```text
Serbisure-backend/
├── core/
│   ├── api/
│   │   ├── exceptions.py          # Internal exception -> current response adapters
│   │   └── contract.py            # Response/status compatibility helpers
│   ├── auth/
│   │   ├── credential_service.py  # Identifier resolution and password checks
│   │   ├── token_service.py       # Shared JWT claims, exact current claim names
│   │   └── permissions.py         # Shared role/verification policies
│   ├── platform/
│   │   ├── cache.py               # Idempotency and TTL policy
│   │   ├── throttling.py          # Shared wait-time calculation/formatting
│   │   ├── media.py               # Cloudinary URL/upload gateway
│   │   ├── identity.py            # Names, roles, fallback avatars
│   │   └── location.py             # Barangay/LGU scope and address predicates
│   ├── middleware.py
│   └── utils.py                   # Compatibility shim for existing imports
├── accounts/
│   ├── api/urls.py
│   ├── controllers/
│   │   ├── auth.py
│   │   ├── profile.py
│   │   └── admin.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── profile_service.py
│   │   └── admin_dashboard_service.py
│   ├── selectors.py
│   ├── serializers/               # Contract-specific serializers, split from one large module
│   ├── permissions.py
│   └── models.py
├── booking/
│   ├── api/urls.py
│   ├── controllers/
│   │   ├── booking.py
│   │   ├── lifecycle.py
│   │   └── proposals.py
│   ├── services/
│   │   ├── booking_service.py
│   │   ├── lifecycle_service.py
│   │   ├── proposal_service.py
│   │   └── recommendation_service.py
│   ├── selectors.py
│   ├── serializers.py
│   └── wage_policy.py
├── reviews/
│   ├── controllers.py
│   ├── services/review_service.py
│   ├── selectors.py
│   └── serializers.py
├── chat/
│   ├── controllers.py
│   ├── services/chat_service.py
│   ├── selectors.py
│   └── serializers.py
├── verifications/
│   ├── api/urls.py
│   ├── controllers/
│   │   ├── user.py
│   │   └── admin.py
│   ├── services/
│   │   ├── document_service.py
│   │   ├── review_service.py
│   │   ├── processing_service.py
│   │   ├── audit_service.py
│   │   └── providers/
│   │       ├── google_vision.py
│   │       ├── tesseract.py
│   │       └── groq.py
│   ├── selectors.py
│   ├── serializers.py
│   └── serializers_admin.py
└── notifications/
    ├── controllers.py
    ├── services.py
    ├── selectors.py
    └── serializers.py
```

For a low-risk migration, retain the current flat modules as compatibility shims. For example, `accounts/views.py` can re-export controller classes while routes and existing test patch targets are migrated. This avoids breaking imports that are not visible in the URL configuration.

### 2.3 Domain boundaries

#### Accounts/authentication

Own registration, mobile login, admin login, profile mutation, resume/profile media, account deletion/export, and admin dashboard read models. Use shared credential and token services, but retain separate mobile/admin role policies and exact error responses.

#### Booking

Own booking creation, feed filtering, lifecycle state transitions, proposals, recommendations, and wage policy. Booking services should be the only writers for assignment/status changes. Notifications should be emitted after successful transactions through the notification gateway.

#### Reviews

Own participant-derived reviewee logic, duplicate protection, review creation, and aggregate reputation read models. Controllers should select the current response envelope; the service should return domain data, not `Response` objects.

#### Chat

Own message/reaction lifecycle, conversation queries, unread/read transitions, typing presence, media upload, and chat-specific idempotency. The inbox selector should return all data needed for one serialization pass instead of issuing queries per partner.

#### Verifications

Own document upload/replacement, OCR processing, package rules, admin review actions, profile verification policy, audit events, and user notifications. The legacy review and newer admin action endpoints should be compatibility adapters over one state-transition service.

#### Notifications

Own notification creation and list/read operations. Domain services emit notification commands/events; only the notifications service writes `tbl_notification`.

### 2.4 Contract-preservation mechanism

Before moving each endpoint, define a small contract record containing:

- route, method, permission classes, parsers, throttle scope/rate;
- accepted request fields and content type;
- success body and status;
- each known validation/auth/not-found/conflict/error body and status;
- cache/idempotency behavior and TTL;
- side effects such as notifications and persisted state.

The old view and new controller should be compared against the same request fixtures. Compatibility tests should assert JSON keys, value types, null/empty behavior, ordering where observable, status codes, headers, and signed media URL presence—not just 2xx success.

## 3. Execution Roadmap

The order below minimizes simultaneous behavior changes. Each phase should be completed and contract-tested before the next phase begins.

### Phase 0 — Freeze the observable contract

1. Inventory every route from all `urls.py` files, including the currently undocumented profile, chat, notifications, admin, analytics, and testing routes.
2. Treat the existing tests, frontend call sites, `docs/API_REFERENCE.md`, serializers, and current URL patterns as separate evidence sources. Resolve conflicts in favor of the running route behavior and add a compatibility fixture for the observed result.
3. Record current response/status fixtures for success, validation, authentication, authorization, not-found, conflict, throttling, duplicate idempotency, empty-list, and external-service-failure cases.
4. Record current cache key prefixes/TTLs and notification side effects. This is necessary before extracting idempotency or notification helpers.
5. Add static checks for import cycles, unresolved route imports, dead aliases, and serializers with ORM/external side effects. Do not change implementation code in this phase.

### Phase 1 — Establish shared primitives without changing callers

1. Add internal platform modules for idempotency, throttle-message formatting, media signing/upload, user identity formatting, and location/LGU scope.
2. Keep `core/utils.py` as a compatibility facade. Existing imports of `check_valid_uuid`, `convert_title`, `check_input_letters`, and `normalize_ph_phone_number` must continue to work.
3. Implement idempotency as a policy-driven helper that preserves each endpoint's current field name (`detail` versus `details`), status, prefix, TTL, and response replay behavior. Add user/endpoint namespacing only after replay/collision tests confirm no client-visible change.
4. Implement throttle formatting with endpoint-specific wording. Migrate one endpoint at a time; do not globally replace “attempts” with “requests”.
5. Implement media helpers with explicit modes for profile, resume, document, and chat assets. Preserve existing URL passthrough and Cloudinary resource type behavior.
6. Add identity and location helpers, but initially call them from adapters that retain the current response keys and default values.

### Phase 2 — Refactor accounts and authentication

1. Split `accounts/views.py` conceptually into auth, profile, and admin controllers. Keep the current classes (`UserRegistrationView`, `CustomLoginView`, `AdminLoginView`, and all profile/admin view names) available through `accounts/views.py` during migration.
2. Move registration and login orchestration into `accounts/services/auth_service.py`; use `core/auth/credential_service.py` for identifier resolution/password checks and `core/auth/token_service.py` for shared JWT claims.
3. Consolidate the duplicate token claim builders in `accounts/serializers.py:227-315` while preserving exact claim names, defaults, and profile-link signing.
4. Split `accounts/serializers.py` into auth, profile/media, social-links, resume, and public-profile serializers. Initially re-export every serializer from the old module so route imports and test patch paths remain valid.
5. Extract profile update/media/resume operations from views/serializers into `profile_service.py`. Preserve the POST-as-PATCH resume alias and its optional idempotency behavior.
6. Extract admin user list, dashboard stats/activity/trend, and active-Barangay reads into `admin_dashboard_service.py` and selectors. Reuse location/media/identity helpers while preserving current dashboard JSON shapes.
7. Explicitly characterize the current `AllowAny` behavior of admin endpoints before any permission refactor. Do not silently change it under the structural task.
8. Delete only duplicated implementation bodies after all imports use the new services. Retain `accounts/views.py` and `accounts/serializers.py` as compatibility shims until repository-wide imports and frontend tests show they are no longer needed.

### Phase 3 — Refactor booking

1. Extract read selectors from `booking/views.py`: feed filters, user-posted bookings, assigned bookings, proposals, and recommendation inputs.
2. Extract the repeated status filter in `MyBookingsView` and `MyAssignedBookingsView` into a shared selector function, retaining each base queryset and ordering.
3. Move booking creation, idempotency, verification gating, and response DTO assembly into `booking/services/booking_service.py`.
4. Move accept/start/complete/cancel transitions into `lifecycle_service.py`. Centralize booking lookup, participant determination, allowed transitions, assignment handling, and notification dispatch; retain each endpoint's current error text and response envelope.
5. Move proposal create/respond operations into `proposal_service.py`, including the long-term wage rule and rejection of competing proposals. Use transaction boundaries around status, assignment, and proposal writes.
6. Move recommendation scoring into `recommendation_service.py`, with selectors that prefetch/annotate ratings where possible. Preserve score formulas, top-15 limit, and output keys.
7. Keep `booking/wage_policy.py` as the single wage-policy module. Both serializer validation and proposal service should call it rather than reproduce thresholds.
8. Reduce `booking/views.py` to compatibility controllers; delete the old inline lifecycle/query/scoring bodies only after endpoint fixtures and query-result comparisons pass.

### Phase 4 — Refactor reviews and notifications

1. Move review creation validation and participant/reviewee derivation from `CreateReviewSerializer.validate` into `reviews/services/review_service.py`, with a serializer adapter that returns the current field-level errors.
2. Move the shared average/sentiment/rating aggregation from `ReviewSummaryView` and `ReviewAnalyticsView` into one selector/service result. Keep the two current response envelopes unchanged.
3. Add explicit review selectors for received, given, target-user, summary, and analytics reads, including the current 404 behavior for a nonexistent target user.
4. Route review notification creation through `notifications/services.py` while preserving the current non-blocking failure behavior and message text.
5. Move notification list/read operations from `notifications/views.py` into thin controllers plus selectors/services. Do not change the list cap, unread count, or response keys.
6. Replace direct `tbl_notification.objects.create` calls in verification code only after notification contract tests prove sender, state, and failure behavior match.

### Phase 5 — Refactor chat

1. Extract `chat/selectors.py` for message threads, inbox aggregates, unread messages, and participant lookups. Use `select_related`/`prefetch_related` and annotations to remove the per-partner query pattern without changing ordering or output.
2. Move text/image message creation, Cloudinary upload, idempotency replay, and notification dispatch into `chat/services/chat_service.py`.
3. Move reaction toggling and its race-condition handling into a transaction-scoped reaction service. Preserve `added`, `removed`, and `changed` actions and exact reaction-count keys.
4. Move read/delete/typing operations into service methods. Preserve the current legacy behavior for invalid temporary message IDs and the current status/body behavior for missing or unauthorized messages until separately approved.
5. Keep chat serializers focused on rendering. The service/selector should provide reaction summaries, signed media values, and partner metadata needed by serializers.
6. Reduce `chat/views.py` to controllers and compatibility imports. Remove duplicated inline logic only after pagination, headers, inbox ordering, idempotency replay, upload-failure, and race-condition tests pass.

### Phase 6 — Consolidate verification workflows and OCR

1. First document the behavioral differences between:
   - `verifications/views.py` legacy queue/review endpoints;
   - `verifications/views_admin.py` authenticated document/action endpoints;
   - `AdminVerificationQueueSerializer` in `verifications/serializers.py`;
   - `AdminDocumentDetailSerializer` and `AdminDocumentActionSerializer` in `serializers_admin.py`.
2. Extract selectors for user documents, queue packages, unsubmitted users, admin filters, audit logs, and Barangay scoping.
3. Extract `document_service.py` for upload/rejected replacement, allowed document types, profile status transition, and audit/notification commands. Preserve the current 409 duplicate behavior and multipart response.
4. Extract `review_service.py` for approve/reject/reset, companion-document rules, reviewer attribution, profile-status recalculation, audit logs, and notifications. Expose two adapters so the legacy `action` payload and the newer `verification_status` payload continue to behave exactly as they do now.
5. Make `IsAdminOrBarangay` a shared permission policy for the already-protected admin API. Preserve the legacy `AllowAny` routes until the separate access-control decision is approved.
6. Define one `processing_service.py` facade around the newer provider modules: `services/ocr_service.py`, `groq_service.py`, `matching_service.py`, and `document_processor.py`.
7. Decide the upload timing contract explicitly. The current serializer performs synchronous legacy OCR and then schedules asynchronous processing. To preserve the current response, initially expose the same fields while delegating processing through an adapter; do not remove synchronous fields or change when the response returns without replay/performance evidence.
8. After equivalence tests pass for Google Vision, Tesseract, Groq text, Groq vision, no-text, invalid-date, retry, and Cloudinary-failure paths, remove the import of `verifications/ocr_service.py` from `DocumentUploadSerializer`.
9. Only then delete the obsolete `verifications/ocr_service.py` implementation. Retain a compatibility module or re-export temporarily if tests or external management commands import it.
10. Merge the old queue/review implementation and `views_admin.py` into the new controllers. Keep the old modules as re-export shims for one compatibility cycle, then delete them only after repository-wide import checks pass.
11. Resolve the `verification_status` model-property/update-fields inconsistency as a separate reviewed state-model change. The structural refactor must not silently change whether status is derived from documents or persisted.

### Phase 7 — Contract verification and cleanup

1. Run all existing app tests and add endpoint contract tests for every route in `Serbisure/urls.py`, including currently undocumented routes.
2. Compare old/new controllers on a fixture matrix covering valid requests, malformed payloads, missing/invalid UUIDs, unauthenticated users, wrong roles, unverified users, missing objects, duplicate requests, throttling, empty collections, and external-service failures.
3. Compare exact JSON keys, nested envelopes, status codes, error key names (`detail` versus `details`), message text, null/empty behavior, list ordering, pagination metadata, response headers, and signed URL presence.
4. Verify idempotency replay returns the same body/status and does not duplicate database writes, uploads, assignments, reviews, notifications, or audit logs.
5. Verify transaction boundaries for booking lifecycle, proposals, reviews, document actions, and chat reactions under concurrent requests.
6. Measure query counts for booking feeds/details, recommendations, chat inbox/threads, verification queue, and admin dashboards before and after extraction. Optimize only when result equivalence is demonstrated.
7. Remove dead imports, duplicate helper bodies, unreachable aliases, and obsolete service modules. Do not delete migrations, model compatibility properties, URL names, or old import shims until external import usage is proven absent.
8. Update `docs/API_REFERENCE.md` from the verified route inventory without changing any endpoint behavior. Mark it as generated or contract-reviewed so future feature iterations do not create another documentation split.

## Recommended end state

The final implementation should have thin, stable route controllers; contract-specific serializers; domain services responsible for writes and policy; selectors responsible for optimized reads; and shared platform gateways for cache/idempotency, throttling, media, identity, locations, authentication, notifications, and audit logging.

The safest deletion candidates after migration are the legacy OCR implementation (`verifications/ocr_service.py`) and duplicate inline admin verification workflow bodies. The current view/serializer modules should be deleted only after compatibility shims, imports, test patch targets, and frontend behavior have been migrated and verified. No endpoint or database migration should be removed as part of this refactoring.
