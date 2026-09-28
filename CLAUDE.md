# SerbiSure Backend — CLAUDE.md

> AI Coding Guide for the **SerbiSure Backend RESTful API**
> USTP Capstone Research Project · Django 6 + DRF 3.17 + PostgreSQL (Neon)

---

## 🗂️ Project Overview

SerbiSure is a Philippine domestic-worker platform that enforces **RA 10361 (Batas Kasambahay)** compliance. The backend is a Django REST Framework API that connects four actor types:

| Role | Description |
|---|---|
| `Kasambahay` | Domestic worker — uploads clearances, gets hired |
| `Homeowner` | Employer — uploads National ID, books workers |
| `Barangay` | LGU account — scoped admin for their barangay |
| `Admin` / `SUPERADMIN` | Platform-wide administrator |

---

## 🏗️ Architecture

```
Serbisure-backend/
├── Serbisure/            # Django project config (settings, root urls, wsgi)
├── accounts/             # Custom user model, JWT auth, admin dashboard views
├── verifications/        # Document upload, OCR, admin verification queue
├── booking/              # Booking lifecycle & RA 10361 wage compliance
├── reviews/              # Star ratings and review system
├── chat/                 # Direct messaging with image support
├── notifications/        # Push/in-app notification system
├── core/                 # Shared utils, CORS middleware, helpers
├── testing_database/     # Seed/testing database endpoints
└── docs/                 # Internal documentation
```

**API Base URL:** `/api/v1/`
**Swagger UI:** `/api/docs/`
**API Schema (JSON):** `/api/schema/`

---

## 🛠️ Tech Stack

| Tool | Version | Purpose |
|---|---|---|
| Django | 6.0.7 | Core framework |
| Django REST Framework | 3.17.1 | API layer |
| SimpleJWT | 5.5.1 | JWT authentication |
| PostgreSQL (Neon) | via psycopg2 2.9.12 | Production database |
| Cloudinary | 1.45.0 | Media storage (images, PDFs) |
| Pillow | 12.3.0 | Image validation |
| pytesseract | >=0.3.13 | OCR for document text extraction |
| Groq | >=1.7.0 | AI-assisted OCR verification |
| drf-spectacular | 0.30.0 | OpenAPI schema auto-generation |
| Whitenoise | 6.12.0 | Static file serving |
| Gunicorn | >=22.0.0 | Production WSGI server |
| Coverage / PyTest | 7.15.2 | Test framework |

---

## 🔐 Authentication & Auth Model

- **Custom user model:** `accounts.tbl_user_profile` (extends `AbstractUser`)
- **Login field:** `email` (not `username`)
- **JWT:** Access token = 30 days, Refresh token = 90 days (rotate + blacklist)
- **Admin login endpoint:** `POST /api/v1/accounts/admin/login/` — returns `role: SUPERADMIN | ADMIN`
- **Regular login endpoint:** `POST /api/v1/accounts/login/`

### Key model fields on `tbl_user_profile`
- `id` — UUIDv4 primary key (prevents enumeration attacks)
- `account_type` — `Kasambahay | Homeowner | Barangay | Admin`
- `verification_status` — **computed property** from `tbl_documents`, NOT a stored DB field
- `contact_number` — E.164 format (`+639XXXXXXXXX`), unique
- `barangay`, `city`, `province`, `region` — address fields (Philippine-specific)
- `is_on_job` — Kasambahay employment status
- `user_tags` — JSONField (list, max 10 tags, max 15 chars each)
- `social_links` — JSONField (list, max 5 links with `platform` + `url`)

> **IMPORTANT:** `verification_status` is a computed `@property` — never try to store it directly in the DB. It derives its value from related `tbl_documents` records.

---

## 📡 API Endpoints Reference

### Accounts (`/api/v1/accounts/`)
| Method | Path | Description |
|---|---|---|
| POST | `register/` | New user registration |
| POST | `login/` | User JWT login |
| POST | `admin/login/` | Admin-only JWT login |
| PATCH | `profile-image/` | Upload profile picture to Cloudinary |
| PATCH | `user-about/` | Update bio (throttled: 3/h) |
| PATCH | `user-tags/` | Update skill tags (throttled: 3/h) |
| PATCH | `contact-privacy/` | Toggle contact number visibility |
| PATCH | `social-links/` | Update social media links |
| PATCH | `job-status/` | Kasambahay availability toggle |
| GET | `public-profile/<uuid:id>/` | Public user profile |
| GET | `search/` | Search users |
| DELETE | `delete-account/` | Delete own account |
| GET | `export-data/` | Export personal data (GDPR-style) |
| POST/GET | `resume/` | Kasambahay resume upload (throttled: 5/d) |
| POST | `change-password/` | Authenticated password change |
| POST | `token/refresh/` | JWT token refresh |

### Admin Dashboard (`/api/v1/accounts/admin/`)
| Method | Path | Description |
|---|---|---|
| GET | `users/` | List all users (filterable: `role`, `barangay`) |
| GET | `dashboard-stats/` | Metrics: worker counts, employment ratio |
| GET | `dashboard-activity/` | Recent bookings for RA 10361 compliance table |
| GET | `monthly-trend/` | Monthly employment trend data for charts |
| GET | `active-barangays/` | List of LGU and user barangays |
| GET | `verification-status-stats/` | Verified/Pending/Rejected/Unverified counts |

### Verifications (`/api/v1/verifications/`)
| Method | Path | Description |
|---|---|---|
| POST | `upload/` | Upload document to Cloudinary (throttled: 5/d) |
| GET | `status/` | Get own verification status |
| DELETE | `documents/<uuid:document_id>/` | Delete a rejected document |
| GET | `admin/queue/` | Admin: pending verification queue |
| POST | `admin/review/<uuid:document_id>/` | Admin: approve / reject / reset a document |
| GET | `admin/documents/` | Admin: list all documents |
| GET | `admin/documents/<uuid>/` | Admin: single document detail |
| POST | `admin/documents/<uuid>/action/` | Admin: take action on document |
| POST | `admin/documents/<uuid>/reprocess/` | Admin: re-run OCR on a document |
| GET | `admin/audit-logs/` | Admin: full verification action audit trail |

### Other Apps
- **Booking:** `/api/v1/booking/` — booking lifecycle, wage validation
- **Chat:** `/api/v1/chat/` — messages, inbox, image uploads (throttled)
- **Reviews:** `/api/v1/reviews/` — star ratings (throttled: 30/d create)
- **Notifications:** `/api/v1/notifications/`

---

## 🗃️ Key Models

### `verifications.tbl_documents`
- Linked 1-to-many to `tbl_user_profile` via `user_profile` FK
- `document_type`: `national_id_front`, `national_id_back`, `nbi_clearance`, `police_clearance`
- `verification_status`: `Pending | Verified | Rejected` (DB-level CheckConstraint)
- `document_url`: Cloudinary `secure_url`
- OCR data stored per document (extracted by Groq + pytesseract pipeline)

### Verification Logic
- **Homeowner** is `Verified` when **both** `national_id_front` AND `national_id_back` are `Verified`
- **Kasambahay** is `Verified` when **both** `nbi_clearance` AND `police_clearance` are `Verified`
- `Admin` and `Barangay` accounts are auto-`Verified`

---

## ⚙️ Environment Variables (`.env`)

```env
SECRET_KEY=your_django_secret_key
DEBUG=True
DATABASE_URL=postgres://user:password@neon.tech/dbname

CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

---

## 🛡️ Security Patterns

- **Rate Throttling** — DRF `UserRateThrottle` with named scopes per endpoint (see `settings.py → DEFAULT_THROTTLE_RATES`)
- **File validation** — Pillow inspects binary headers; rejects PDFs/executables disguised as images; hard 10 MB limit
- **Idempotency** — Duplicate document uploads are blocked at the API level
- **UUID PKs** — All primary keys are UUIDv4 to prevent enumeration attacks
- **DB CheckConstraints** — ORM-level constraints lock ENUM fields (account_type, gender, document statuses)
- **Zero hardcoded secrets** — All credentials via `.env`

---

## 🧪 Testing

- Framework: **pytest-django** + **coverage**
- Target: **100% coverage** across all apps
- Run all tests:
  ```bash
  coverage run manage.py test
  coverage report -m
  ```
- Or with pytest:
  ```bash
  pytest
  ```
- Config file: `pytest.ini`

---

## 🚀 Local Development Setup

```bash
# 1. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate          # Windows
source venv/bin/activate         # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up .env (copy from .env.example)
cp .env.example .env

# 4. Run migrations
python manage.py migrate

# 5. Start dev server
python manage.py runserver
# API: http://127.0.0.1:8000/api/v1/
# Swagger: http://127.0.0.1:8000/api/docs/
```

---

## 🧠 Important Coding Conventions

1. **App naming:** Use `tbl_` prefix for database models (e.g., `tbl_user_profile`, `tbl_documents`)
2. **Role guards:** Always check `request.user.account_type` in views — never trust the frontend role claim
3. **Admin views:** Admin-specific views are in `views_admin.py` (separate file from user-facing `views.py`)
4. **Serializer split:** Admin serializers live in `serializers_admin.py`
5. **Verification status:** Never store verification_status as a DB column — always derive from documents
6. **Phone numbers:** Always normalize to E.164 (`+639XXXXXXXXX`) using `core.utils.normalize_ph_phone_number`
7. **Media:** Upload to Cloudinary, store only the `secure_url` string in DB
8. **CORS:** Handled by `core.middleware.SimpleCorsMiddleware` — not django-cors-headers
9. **Barangay filtering:** Both `SUPERADMIN` and `Barangay` roles use `?barangay=` query param for scoped data

---

## 📂 Adding a New App

1. Create app: `python manage.py startapp <appname>`
2. Add to `INSTALLED_APPS` in `Serbisure/settings.py`
3. Add URL include in `Serbisure/urls.py` under `/api/v1/<appname>/`
4. Create `<appname>/urls.py` with `urlpatterns`
5. Add migrations: `python manage.py makemigrations <appname>`
6. Write tests in `<appname>/tests.py` targeting 100% coverage

---

## 📄 Deployment

- **Platform:** Render (configured in `render.yaml`)
- **Static files:** Whitenoise + `build_files.sh`
- **Vercel config:** `vercel.json` (alternative deploy)
- **Production server:** Gunicorn
