# Serbisure API Development & Security Guidelines

This document serves as the master blueprint for building a secure, scalable, and enterprise-grade API for Serbisure. It combines deployment security, endpoint-specific rules, and architectural standards.

## Part 1: Global Security & Deployment (The Foundation)
These are mandatory rules for the production environment to protect the API from catastrophic breaches.

- **DEBUG = False (The Deadliest Mistake)**: Leaving `DEBUG = True` in production reveals passwords, database URLs, and source code on every crash. Ensure `DEBUG = False` is strictly enforced in the production `.env` file.
- **CORS Safelisting**: To prevent unauthorized websites from making requests, use `django-cors-headers` to strictly limit `CORS_ALLOWED_ORIGINS` to the exact React/Next.js frontend URL (e.g., `https://www.serbisure.com`). Every other website is blocked.
- **HTTPS (SSL Encryption)**: JWT tokens can easily be stolen over public Wi-Fi. The production server (Render, Vercel, AWS) must force HTTPS so all traffic is encrypted while traveling through the air.

## Part 2: Standard Endpoint Creation Checklist
*Before completing ANY new API endpoint (e.g., Bookings, Payments, Profile Edits), both the Developer and AI must ensure the following layers are applied:*

- [ ] **Authentication**: Is the endpoint protected by JWT checks? (Unless explicitly meant to be public, like Registration).
- [ ] **Data Ownership (Authorization)**: When fetching, updating, or deleting data, does the query strictly ensure the data belongs to the requester (e.g., `filter(user=request.user)`)?
- [ ] **Input Validation (Strict Serializers)**: Does the DRF Serializer strictly validate all inputs and reject dangerous or unexpected fields?
- [ ] **Rate Limiting (Throttling)**: Does this endpoint have a Sliding Window Throttle to prevent spam/DDoS? (Critical for endpoints that create data, send emails, or handle logins).
- [ ] **Idempotency**: If this endpoint handles transactions, state changes, or bookings, does it check for an `Idempotency-Key` header to prevent double-clicks and double-charges?
- [ ] **UUID References (IDOR Protection)**: Are we using UUIDs instead of sequential integers in the URLs to look up data? (e.g., preventing a hacker from scraping users 1 through 10,000).

## Part 3: Senior-Level Enterprise Architecture
Security protects the app from hackers, but these 6 features protect the app from scaling issues and future headaches.

1. **Pagination (Crucial for Speed)**
   *The Rule:* Never send 10,000 records at once to avoid crashing the user's browser.
   *The Standard:* Every single `GET` request that returns a list must use DRF Pagination (e.g., returning 20 items at a time with `next` and `previous` links).

2. **Standardized JSON Responses**
   *The Rule:* The frontend needs predictability, not random error structures.
   *The Standard:* Use a Custom Exception Handler to ensure every response has the exact same structure (e.g., `{"success": false, "data": null, "error": "..."}`).

3. **API Versioning**
   *The Rule:* If you launch a mobile app and later change the API, old apps will crash.
   *The Standard:* Always prefix URLs with `/v1/` (e.g., `/api/v1/accounts/login/`). When making breaking changes next year, create `/v2/` so old apps keep working smoothly.

4. **Soft Deletes**
   *The Rule:* If a user deletes an account with pending payments, running `.delete()` destroys financial records permanently.
   *The Standard:* Add a boolean column `is_deleted = False` to every model. When a user deletes something, flip the boolean to hide it instead of destroying the data.

5. **Filtering & Sorting**
   *The Rule:* Don't force the frontend to download 1,000 bookings just to filter out the "Pending" ones using Javascript.
   *The Standard:* Install `django-filter` to let the Postgres database do the heavy lifting (e.g., requesting `/api/bookings/?status=pending&sort=-date`).

6. **Audit Logging (Who did What?)**
   *The Rule:* If a booking gets cancelled, both parties might claim "I didn't cancel it!"
   *The Standard:* Use a package like `django-simple-history` to track exactly which User ID made a change to a database row and at what time.
