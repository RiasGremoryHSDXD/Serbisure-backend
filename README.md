<div align="center">
  <img src="https://raw.githubusercontent.com/SerbiSure-Tagupa-et-al/Serbisure-backend/main/assets/serbisure-logo.png" alt="SerbiSure Logo" width="85" />
  <h1>SerbiSure Backend API</h1>
  <p><b>The Secure, Scalable Engine Powering the SerbiSure Ecosystem</b></p>

  <p>
    <a href="https://www.djangoproject.com/"><img src="https://img.shields.io/badge/Django-6.0-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django" /></a>
    <a href="https://www.django-rest-framework.org/"><img src="https://img.shields.io/badge/DRF-3.17-red?style=for-the-badge&logo=django&logoColor=white" alt="Django REST Framework" /></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.14-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" /></a>
    <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-Neon-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" /></a>
    <a href="https://cloudinary.com/"><img src="https://img.shields.io/badge/Cloudinary-Cloud_Storage-3448C5?style=for-the-badge&logo=cloudinary&logoColor=white" alt="Cloudinary" /></a>
    <a href="https://jwt.io/"><img src="https://img.shields.io/badge/JWT-Secure_Auth-000000?style=for-the-badge&logo=jsonwebtokens&logoColor=white" alt="JWT" /></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License" /></a>
  </p>

  <p><i>"Robust backend infrastructure enforcing RA 10361 (Batas Kasambahay) compliance through strict role-based access, automated throttling, and secure document verification."</i></p>
</div>

---

> [!IMPORTANT]
> This repository contains the **Backend RESTful API** for SerbiSure, an IT Capstone Research Project from the **University of Science and Technology of Southern Philippines (USTP)**. It is responsible for orchestrating secure data transactions, enforcing business logic, and maintaining the integrity of the bilateral verification gateway between Homeowners, Kasambahays, and Barangay LGUs.

---

## 📋 Table of Contents
- [📖 Architecture Overview](#-architecture-overview)
- [🛠️ Tech Stack & Dependencies](#️-tech-stack--dependencies)
- [✨ Core Backend Modules](#-core-backend-modules)
- [🛡️ Security & Compliance](#️-security--compliance)
- [🚀 Getting Started & Local Setup](#-getting-started--local-setup)
- [🧪 Testing (100% Coverage)](#-testing-100-coverage)
- [📄 License](#-license)

---

## 📖 Architecture Overview

The SerbiSure backend is engineered using a **Django Application-Based Architecture** to ensure strict separation of concerns, scalability, and maintainability. It completely isolates domain logic into modular apps:

1. **`accounts` App**: Manages custom user profiles (`tbl_user_profile`), Role-Based Access Control (Kasambahay, Homeowner, Admin, Barangay), and secure JWT authentication.
2. **`verifications` App**: Manages the `tbl_documents` database, handling secure biometric and clearance uploads to Cloudinary with strict idempotency and payload size restrictions.

The API exclusively uses **Django REST Framework (DRF)** for routing and serialization, ensuring all client communications are strictly typed, validated, and normalized before hitting the PostgreSQL database.

---

## 🛠️ Tech Stack & Dependencies

| Component | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Core Framework** | Django | `6.0.7` | High-level MVC/MVT framework. |
| **API Layer** | Django REST Framework | `3.17.1` | RESTful routing, serialization, and viewsets. |
| **Database** | PostgreSQL (Neon DB) | `2.9.12` | ACID-compliant relational database. |
| **Authentication** | SimpleJWT | `5.5.1` | Stateless, cryptographically secure token auth. |
| **Media Storage** | Cloudinary | `1.45.0` | Cloud-hosted CDN for ID & Clearance storage. |
| **Image Processing** | Pillow | `12.3.0` | In-memory image validation and processing. |
| **Testing** | Coverage / PyTest | `7.15.2` | Comprehensive automated test suites. |

---

## ✨ Core Backend Modules

### 1. 🔐 Role-Based Access Control (RBAC)
- Enforces strict account types globally: `Kasambahay`, `Homeowner`, `Admin`, `Barangay`.
- Utilizes custom JWT payload claims to pass user roles efficiently to the frontend without requiring secondary database queries.

### 2. 🛂 Secure Document Verification API
- **Endpoint**: `/api/verifications/upload/`
- Validates that Kasambahays upload only NBI/Police Clearances, and Homeowners upload only National IDs.
- Synchronously streams valid image data to Cloudinary via a secure API pipeline, saving only the returned `secure_url` to the database.

### 3. 📈 Data Integrity & ORM Constraints
- Implements PostgreSQL `CheckConstraint` rules directly at the ORM level to prevent invalid data insertion (e.g., locking `verification_status` to only Pending, Verified, or Rejected).
- Uses standard UUIDv4 primary keys across all models to prevent enumeration attacks.

---

## 🛡️ Security & Compliance

SerbiSure enforces military-grade API security protocols:
- **Strict Idempotency**: The API blocks exact duplicate uploads to prevent database clutter and double-processing.
- **Algorithmic Rate Limiting (Throttling)**: Endpoints utilize DRF's `UserRateThrottle` (hard-capped at 5 requests/day for sensitive endpoints) to prevent DDoS attacks and spam.
- **Malicious Payload Rejection**: Enforces a strict 10MB file size limit and uses Pillow to deeply inspect binary headers, blocking malicious PDFs or executables disguised as image files.
- **Environment Isolation**: Zero hardcoded secrets. All database URIs, JWT signing keys, and Cloudinary credentials are injected dynamically via `.env`.

---

## 🚀 Getting Started & Local Setup

### Prerequisites
- **Python**: `3.14+`
- **PostgreSQL** (Or an active Neon DB connection string)
- **Git**

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/SerbiSure-Tagupa-et-al/Serbisure-backend.git
   cd Serbisure-backend
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate
   
   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Create a `.env` file in the root directory and configure the following keys:
   ```env
   DEBUG=True
   SECRET_KEY=your_secure_django_secret_key
   DATABASE_URL=postgres://user:password@neon.tech/dbname
   
   CLOUDINARY_CLOUD_NAME=your_cloud_name
   CLOUDINARY_API_KEY=your_api_key
   CLOUDINARY_API_SECRET=your_api_secret
   ```

5. **Apply Database Migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Start the Development Server**:
   ```bash
   python manage.py runserver
   ```
   *The API will be available at `http://127.0.0.1:8000/api/`*

---

## 🧪 Testing (100% Coverage)

The backend is backed by an extensive `APITestCase` suite covering edge cases, permission escalations, idiot inputs, and mocked API calls to Cloudinary.

**Run the full test suite and view coverage:**
```bash
coverage run manage.py test
coverage report -m
```

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">
  <p>Made with ❤️ by the <b>USTP SerbiSure Capstone Research Team</b></p>
  <p>Department of Information Technology • USTP Cagayan de Oro City • 2026</p>
</div>
