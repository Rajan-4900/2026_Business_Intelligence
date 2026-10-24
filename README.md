# Crowd Heatmap & Business Intelligence Platform

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-6.0+-green.svg)](https://www.djangoproject.com/)
[![Database](https://img.shields.io/badge/database-PostgreSQL%20%7C%20Supabase%20%7C%20SQLite-336791.svg)](https://supabase.com/)
[![AI](https://img.shields.io/badge/AI-Google%20Gemini-orange.svg)](https://ai.google.dev/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An end-to-end **Business Intelligence (BI)** web platform that helps entrepreneurs and business owners evaluate where to open a business in India. The system combines **real-time crowd density mapping**, **machine-learning business recommendations**, an **Extended Huff Gravity Model & multi-factor revenue forecasting engine**, enterprise-grade **2FA & Account Security**, and an **AI assistant** powered by Google Gemini.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Database Configuration & Supabase](#database-configuration--supabase)
- [Environment Variables](#environment-variables)
- [Running the Application](#running-the-application)
- [Running Tests](#running-tests)
- [API Endpoints](#api-endpoints)
- [Revenue & Feasibility Engines](#revenue--feasibility-engines)
- [Machine Learning Model](#machine-learning-model)
- [Account Security & 2FA](#account-security--2fa)
- [User Guide](#user-guide)
- [Deployment](#deployment)
- [Documentation](#documentation)
- [License](#license)

---

## Overview

The platform answers three core questions for any location in India:

1. **How crowded is this area?** — Sector-based heatmap using OpenStreetMap POI data.
2. **What business should I open here?** — Scikit-Learn decision tree + rule-based feasibility checks.
3. **How much revenue can I expect?** — Multi-factor simulation engine with time-of-day, customer quality, competition modifiers, and Huff spatial gravity modeling.

Data is sourced live from **OpenStreetMap** (Nominatim geocoding + Overpass API) within an analysis radius (2 km to 5 km).

---

## Key Features

### Real-Time Crowd Heatmap
- Search any location in India or use browser geolocation.
- Divides the area into a **3×3 sector grid** and classifies each sector as **High**, **Medium**, or **Low** intensity based on POI density.
- Thresholds: High ≥ 15 POIs/sector, Medium 5–14, Low < 5.

### AI-Powered Business Recommendations
- **Scikit-Learn DecisionTreeClassifier** trained on `business_dataset.csv` predicts the best business type from crowd intensity, shop density, and area type.
- **Google Gemini** chatbot ("Antigravity") provides conversational guidance, geocoding assistance, and triggers map actions.
- **Smart Relocation (AI Zones)**: Scans ~1.7 km offsets to rank alternative high-potential locations.

### Revenue & Feasibility Engine
- **Spatial Prediction Engine (Extended Huff Model)**: Calculates retail gravity, competitor attraction, market capture probability, and sales estimates.
- **Smart Revenue Forecast** (`calculate_smart_revenue`): Footfall × conversion × dynamic average spend, adjusted for competition, overload, and customer quality.
- **Per-POI Revenue Enrichment** (`enrich_places_with_revenue`): Estimates revenue for nearby businesses with high efficiency.
- **Feasibility Checker**: Evaluates Go/No-Go decisions using CSV intensity rules, ML prediction, and live POI density evidence.

### Enterprise Account Security & 2FA
- **Custom User Model** (`users.CustomUser`) using email authentication with roles (**Businessman** & **Customer**).
- **Two-Factor Authentication (2FA)**: Time-based One-Time Passwords (TOTP) compatible with Google Authenticator, Authy, etc.
- **Single-Use Recovery Codes**: Cryptographically hashed backup codes for account recovery.
- **Active Session & Device Management**: View active sessions with device names/IPs and revoke any session remotely.
- **Security Audit Logs**: Automated logging of logins, password resets, and 2FA events.

### Favorites & Popular Picks
- Signed-in users tap the heart on any Popular Places card to save it; `/favorites/` lists saved places and recommends new ones.
- Stored in Supabase (`public.favorite_places`) with Row Level Security; Django forwards the user's own token, so ownership is enforced by Supabase.
- Recommendations (`favorites/recommender.py`) blend time-decayed popularity across all users, the user's category taste, distance, and the revenue engine's location score.
- **Setup:** run [`supabase/favorites.sql`](supabase/favorites.sql) and [`supabase/user_history.sql`](supabase/user_history.sql) (per-user history of searches, analyses and inquiries) in the Supabase SQL Editor. Also run [`supabase/security_fixes.sql`](supabase/security_fixes.sql), which stops the public anon key from reading profile emails and activity logs.

### AI-Powered Business Intelligence Report (PDF)
- **Generate Detailed Report** on the dashboard map, or ask the chatbot (*"Generate a comprehensive PDF report for this location."*), produces a 20–25 page A4 PDF for the selected location.
- Contents: executive summary with KPI cards, location overview, the **actual heatmap screenshot** captured from the live map, ML recommendations compared with revenue-engine scores, competitors, revenue scenarios, Go/No-Go feasibility, a business-specific roadmap, a risk matrix, final recommendations and an investment checklist, plus 5 rendered flowcharts and up to 9 charts.
- All figures come from the existing engines, rerun on the server. Gemini writes only the explanations, which are schema-checked and rejected if they contain figures that are not in the data; otherwise template text is used and labelled as such.
- Every figure is tagged *Observed*, *Estimate*, *AI text*, *Your input* or *Missing*. Missing data is shown as "Data unavailable for this analysis.", never filled in.
- Reports are private (Supabase user id), expire after 24 h, and need `brew install pango` / `libpango` for WeasyPrint. See [docs/REPORT_GENERATION.md](docs/REPORT_GENERATION.md).

### Interactive Dashboard
- Analytics UI with live revenue animation, business intelligence panel, 4×4 popular places flashcard matrix, and feasibility evaluation.
- WebSocket-powered chatbot for real-time AI assistance across all pages.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (Frontend)                       │
│  Leaflet Map │ Dashboard UI │ Chatbot │ Business Form           │
└──────────────┬──────────────────────────────┬───────────────────┘
               │ HTTP/REST                    │ WebSocket
               ▼                              ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│   Django Views (REST)    │    │  Django Channels (Daphne)    │
│ tracker & business_intel │    │  tracker/consumers.py        │
└──────────────┬───────────┘    └──────────────┬───────────────┘
               │                               │
               ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│ Spatial Engine & Utils   │    │   Google Gemini API          │
│ prediction_engine/       │    │   (Generative AI Chatbot)    │
└──────────────┬───────────┘    └──────────────────────────────┘
               │
               ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│  business_model.pkl      │    │  OpenStreetMap APIs          │
│  (Scikit-Learn)          │    │  Nominatim + Overpass        │
└──────────────────────────┘    └──────────────────────────────┘
               │
               ▼
┌──────────────────────────┐
│ SQLite / Supabase (Pg)   │
│ (User, Security & Data)  │
└──────────────────────────┘
```

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Backend | Django 6.0+, Django Channels 4.1 |
| ASGI Server | Daphne 4.1 |
| Frontend | HTML5, CSS3, Vanilla JavaScript (ES6+), Leaflet.js |
| Machine Learning | Scikit-Learn, Pandas, NumPy |
| Spatial Modeling | Extended Huff Gravity Model |
| Generative AI | Google Generative AI (Gemini 2.0 / 2.5 Flash) |
| Geospatial Data | OpenStreetMap (Nominatim & Overpass API) |
| Database | SQLite (default dev) / PostgreSQL / Supabase via `dj-database-url` |
| Security & 2FA | PyOTP, QRCode, Cryptographic Hash Recovery Codes |
| Static Files | WhiteNoise 6.7 |
| Deployment | Render / Railway / Supabase (Procfile included) |

---

## Project Structure

```text
Business_Intelligence-main/
├── crowd_heatmap_project/       # Django project configuration & ML training
│   ├── settings.py              # Settings, DB config, Channels, Auth
│   ├── urls.py                  # Root URL routing
│   ├── asgi.py                  # ASGI & WebSocket routing
│   ├── wsgi.py
│   ├── train_model.py           # ML model training script
│   ├── business_dataset.csv     # Training dataset (crowd, shops, area → business)
│   └── business_model.pkl       # Trained DecisionTreeClassifier
│
├── tracker/                     # Crowd tracking & geocoding app
│   ├── views.py                 # Location search, crowd intensity, contact views
│   ├── utils.py                 # Revenue enrichment & scoring utils
│   ├── consumers.py             # WebSocket chatbot consumer (Gemini)
│   ├── routing.py               # WebSocket URL routing
│   ├── prediction_engine/       # Spatial gravity & Huff revenue model
│   ├── models.py                # ContactMessage
│   ├── forms.py                 # ContactForm
│   ├── urls.py                  # App URL patterns
│   └── tests.py                 # Prediction engine & integration unit tests
│
├── business_intelligence/       # Analytics & recommendation app
│   ├── views.py                 # Dashboard, feasibility, AI recommendations
│   ├── utils.py                 # Smart revenue & candidate generation
│   ├── prediction_engine/       # Spatial revenue engine modules
│   ├── models.py                # BusinessUser
│   ├── forms.py                 # BusinessUserForm
│   ├── urls.py                  # BI URL patterns
│   └── tests.py                 # Prediction engine test suite
│
├── users/                       # Authentication & Security app
│   ├── models.py                # CustomUser, TwoFactorRecoveryCode, SecurityEvent, UserSession
│   ├── views.py                 # Register, login, 2FA setup/verify, security center
│   ├── forms.py                 # CustomUserCreationForm, AuthenticationForm, 2FA forms
│   └── urls.py                  # Auth URL routing
│
├── report_generator/            # PDF report generator (data collection, charts, flowcharts, Gemini text, WeasyPrint)
│   ├── services.py              # Shared pipeline for dashboard + chatbot, background thread, stages
│   ├── data_collector.py        # Runs the existing analysis engines for one location
│   ├── ai_writer.py / prompts.py  # Gemini stages with schema + figure validation and fallbacks
│   ├── chart_generator.py       # Matplotlib charts from real analysis values
│   ├── flowchart_generator.py   # Inline-SVG flowcharts
│   ├── pdf_generator.py         # WeasyPrint rendering with a locked URL fetcher
│   └── tests/                   # Validators, data, AI, PDF, API/security, chatbot tests
│
├── templates/                   # HTML templates (reports/ holds the PDF templates)
│   ├── heatmap_app/             # Home, dashboard, contact pages
│   ├── users/                   # Authentication & Security Center templates
│   └── base.html                # Global base layout & floating assistant
│
├── static/                      # Static assets
│   ├── css/style.css            # Responsive styles, glassmorphism, UI components
│   └── js/                      # Frontend scripts (main.js, analytics, forms)
│
├── docs/                        # Extended documentation
│   ├── RUN_INSTRUCTIONS.md
│   ├── GEOLOCATION_GUIDE.md
│   ├── AUTH_STRUCTURE_SUMMARY.md
│   ├── CUSTOM_USER_MIGRATION_INSTRUCTIONS.md
│   ├── REVENUE_STRUCTURE_REPORT.md
│   ├── MAP_DEBUG_CHECKLIST.md
│   └── STATIC_TESTING.md
│
├── requirements.txt
├── manage.py
├── Procfile                     # Production ASGI server command
└── .env                         # Environment variables (create locally)
```

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- **pip**
- **Google AI Studio API Key** (optional, for Gemini AI Chatbot) — [Get one here](https://aistudio.google.com/apikey)
- **Supabase Account** (optional, for cloud PostgreSQL database) — [supabase.com](https://supabase.com/)

### 1. One-Command Quick Start (Recommended)

Start both frontend and backend instantly from your terminal:

```bash
# macOS / Linux
./run.sh

# Cross-platform Python CLI
python3 run.py

# Make
make dev

# npm / Node.js
npm run dev

# Windows (PowerShell / Command Prompt)
.\run.ps1
# or: run.bat
```

Open your browser at: **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

### Manual Setup & Execution

#### 1. Clone the Repository

```bash
git clone https://github.com/vuser02454/buz_intelligence.git
cd buz_intelligence
```

#### 2. Create a Virtual Environment

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

PDF reports use WeasyPrint, which needs the Pango system library:

```bash
brew install pango                                   # macOS
sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0  # Debian/Ubuntu
```

#### 4. Configure Environment Variables

Create a `.env` file in the root directory:

```env
# AI Chatbot
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL_NAME=gemini-2.5-flash

# Django Security
DEBUG=True
SECRET_KEY=your_secret_key_here

# Database (Optional - defaults to SQLite if omitted)
DATABASE_URL=postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres

# Email / SMTP Settings (Optional - console output in dev)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
DEFAULT_FROM_EMAIL=Crowd Heatmap <noreply@crowdheatmap.local>
```

#### 5. Run Database Migrations

```bash
python manage.py migrate
```

#### 6. (Optional) Create Superuser

```bash
python manage.py createsuperuser
```

---

## Database Configuration & Supabase

This project uses `dj-database-url` and supports **SQLite** (local default) and **PostgreSQL / Supabase** (cloud production).

### Option A: Automatic Setup with Supabase URI (Recommended)
1. Go to your [Supabase Project Dashboard](https://supabase.com/dashboard) ➔ **Project Settings** ➔ **Database**.
2. Copy the **Connection URI** (Connection pooling on port `6543` or `5432`).
3. Add `DATABASE_URL` to your `.env` file:
   ```env
   DATABASE_URL=postgresql://postgres.[REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
   ```
4. Run Django migrations:
   ```bash
   ./run.sh migrate
   # or
   python3 manage.py migrate
   ```

### Option B: Manual SQL Execution (Supabase SQL Editor)
If you want to create the database tables manually without using Django migrations, open **Supabase SQL Editor** and execute:

```sql
-- Custom User Table
CREATE TABLE IF NOT EXISTS users_customuser (
    id BIGSERIAL PRIMARY KEY,
    password VARCHAR(128) NOT NULL,
    last_login TIMESTAMPTZ NULL,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    first_name VARCHAR(150) NOT NULL DEFAULT '',
    last_name VARCHAR(150) NOT NULL DEFAULT '',
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    date_joined TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    email VARCHAR(254) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    user_type VARCHAR(20) NOT NULL DEFAULT 'customer',
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    recovery_email VARCHAR(254) NULL,
    two_factor_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    totp_secret VARCHAR(64) NULL,
    password_changed_at TIMESTAMPTZ NULL
);

-- 2FA Backup Recovery Codes
CREATE TABLE IF NOT EXISTS users_twofactorrecoverycode (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
    code_hash VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    used_at TIMESTAMPTZ NULL,
    is_used BOOLEAN NOT NULL DEFAULT FALSE
);

-- Security Event Logs
CREATE TABLE IF NOT EXISTS users_securityevent (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    ip_address INET NULL,
    user_agent TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Active User Sessions
CREATE TABLE IF NOT EXISTS users_usersession (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
    session_key VARCHAR(40) NOT NULL UNIQUE,
    ip_address INET NULL,
    user_agent TEXT NULL,
    device_name VARCHAR(100) NOT NULL DEFAULT 'Web Browser',
    last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Business Intelligence User Leads
CREATE TABLE IF NOT EXISTS business_intelligence_businessuser (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    business_type VARCHAR(100) NOT NULL,
    recommended_business VARCHAR(100) NULL,
    crowd_intensity VARCHAR(10) NOT NULL,
    latitude DOUBLE PRECISION NULL,
    longitude DOUBLE PRECISION NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Contact Inquiries
CREATE TABLE IF NOT EXISTS tracker_contactmessage (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL,
    subject VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Django Sessions
CREATE TABLE IF NOT EXISTS django_session (
    session_key VARCHAR(40) NOT NULL PRIMARY KEY,
    session_data TEXT NOT NULL,
    expire_date TIMESTAMPTZ NOT NULL
);
```

---

## Environment Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `DEBUG` | No | `False` | Toggle Django debug mode (`True`/`False`) |
| `SECRET_KEY` | Yes (Prod) | Insecure dev key | Django cryptographic signing secret key |
| `DATABASE_URL` | No | `sqlite:///db.sqlite3` | PostgreSQL/Supabase database connection URI |
| `GEMINI_API_KEY` | No | None | Google AI Studio API key for interactive chatbot |
| `GEMINI_MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model version for chat assistant |
| `EMAIL_BACKEND` | No | Console in Dev | `django.core.mail.backends.smtp.EmailBackend` in prod |
| `EMAIL_HOST` | No | `smtp.gmail.com` | SMTP email server hostname |
| `EMAIL_PORT` | No | `587` | SMTP server port |
| `EMAIL_USE_TLS` | No | `True` | Enable TLS encryption |
| `EMAIL_HOST_USER` | No | None | SMTP username / email address |
| `EMAIL_HOST_PASSWORD` | No | None | SMTP password / app-specific password |
| `REPORT_RETENTION_HOURS` | No | `24` | How long generated PDF reports are kept |
| `REPORT_MAX_PER_HOUR` | No | `10` | PDF reports per user per hour |
| `REPORT_MAX_CONCURRENT` | No | `2` | PDF reports generated at once |
| `REPORT_AI_ENABLED` | No | `True` | Use Gemini for report explanations (template text otherwise) |
| `REPORT_AI_TIMEOUT` | No | `25` | Seconds per Gemini report stage |

---

## Running Tests

Run the full automated test suite:

```bash
./run.sh test
# or: python3 run.py test
# or: make test
```

Frontend tests for the report generator (jsdom):

```bash
npm install
npm run test:js
```

---

## Running the Application

### Development Server (HTTP + WebSockets)

Daphne is configured as the ASGI application handler:

```bash
./run.sh
# or: python3 run.py dev --port 8000
# or: python manage.py runserver
```

Open your browser and navigate to: **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

### Production Server (ASGI)

```bash
daphne -b 0.0.0.0 -p 8000 crowd_heatmap_project.asgi:application
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Home page with hero & quick navigation |
| GET | `/dashboard/` | Interactive analytics dashboard & map |
| POST | `/search-location/` | Geocode location name via Nominatim |
| POST | `/autocomplete-location/` | Location search suggestions (India) |
| POST | `/find-popular-places/` | Ranked POIs within 2 km + per-place revenue |
| POST | `/analyze-crowd-intensity/` | 3×3 sector heatmap & ML business prediction |
| POST | `/check-feasibility/` | Go/No-Go feasibility check for a business type |
| POST | `/api/analyze-location/` | Full smart revenue forecast |
| POST | `/api/generate-best-locations/` | Ranked AI candidate zones (top 3) |
| GET | `/api/business-types/` | Dynamic list of business categories |
| POST | `/api/find-matching-locations/` | Match locations by crowd intensity + business |
| POST | `/submit-form/` | Submit business inquiry / user profile |
| POST | `/contact/` | Contact message submission |
| GET | `/accounts/security/` | Security Center (2FA, Sessions, Audit logs) |
| WS | `/ws/chat/` | WebSocket chatbot (Gemini assistant) |
| POST | `/api/reports/generate/` | Start a PDF report for the selected location (Supabase bearer token + CSRF) |
| GET | `/api/reports/<id>/status/` | Report generation stages and status (owner only) |
| GET | `/api/reports/<id>/download/` | Download the finished PDF (owner only) |

---

## Revenue & Feasibility Engines

The platform incorporates **three revenue calculation models**:

1. **Spatial Prediction Engine (Extended Huff Model)** (`tracker/prediction_engine/`):
   - Calculates site utility from square footage, accessibility, and amenity density.
   - Computes market share probability against competing POIs using distance decay exponents.
   - Outputs revenue ranges, confidence scores, and actionable recommendations.

2. **Smart Revenue Forecast** (`calculate_smart_revenue`):
   - Models footfall from live POI density, applies daypart multipliers, and computes monthly projections adjusted for Customer Quality Index (CQI) and overload risk.

3. **Per-POI Revenue Enrichment** (`enrich_places_with_revenue`):
   - Ranks and enriches local businesses with estimated monthly turnover, health metrics, and risk scores.

---

## Machine Learning Model

| Property | Value |
|----------|-------|
| Algorithm | DecisionTreeClassifier (Scikit-Learn) |
| Features | `crowd`, `shops`, `area` (one-hot encoded) |
| Target | `business` (recommended business category) |
| Training Script | `crowd_heatmap_project/train_model.py` |
| Dataset | `crowd_heatmap_project/business_dataset.csv` |
| Serialized Model | `crowd_heatmap_project/business_model.pkl` |

---

## Account Security & 2FA

The platform includes a dedicated **Security Center** accessible to logged-in users:

1. **Two-Factor Authentication**:
   - Enable TOTP via QR Code scan using Google Authenticator, Microsoft Authenticator, or Authy.
   - 8 single-use cryptographically hashed recovery codes are generated upon setup.
2. **Session & Device Management**:
   - Real-time device and IP tracking with single-click revocation of individual devices or all other sessions.
3. **Security Audit Log**:
   - Timestamped records of critical actions (logins, password changes, 2FA status modifications).

---

## User Guide

1. **Register & Log In**: Create an account at `/accounts/register/` and set up 2FA in the Security Center.
2. **Explore Map**: Search for any city or landmark in India, or click "Find My Location".
3. **Analyze Crowd Intensity**: View the 3×3 sector heatmap (High, Medium, Low intensity).
4. **Discover Popular Places**: Click "Popular Places" to generate the 4×4 business flashcard matrix and revenue estimates.
5. **Check Feasibility**: Ask the AI assistant or test a business type (e.g., `"open cafe in Indiranagar"`).
6. **Dashboard Intelligence**: Access `/dashboard/?ai=true` for full revenue projections, market breakdowns, and AI relocation zones.

---

## Deployment

The repository includes ready-to-use deployment configuration for **Render**, **Railway**, or any container/PaaS provider:

- `Procfile`: `web: daphne -b 0.0.0.0 -p $PORT crowd_heatmap_project.asgi:application`
- `whitenoise` handles static asset serving and caching.
- Configure `DATABASE_URL` for PostgreSQL / Supabase connections.
- Set `DEBUG=False` and supply `SECRET_KEY` and `GEMINI_API_KEY` in environment variables.

---

## Documentation

| Document | Description |
| :--- | :--- |
| [Run Instructions](docs/RUN_INSTRUCTIONS.md) | Step-by-step runner and setup guide |
| [Geolocation Guide](docs/GEOLOCATION_GUIDE.md) | Map & GPS integration details |
| [Auth Structure Summary](docs/AUTH_STRUCTURE_SUMMARY.md) | Authentication & user roles |
| [Custom User Migration Instructions](docs/CUSTOM_USER_MIGRATION_INSTRUCTIONS.md) | Database migration documentation |
| [Revenue Structure Report](docs/REVENUE_STRUCTURE_REPORT.md) | In-depth revenue engine mathematical equations |
| [Map Debug Checklist](docs/MAP_DEBUG_CHECKLIST.md) | Troubleshooting map & Leaflet issues |
| [Static Testing](docs/STATIC_TESTING.md) | Static file testing guide |
| [Report Generation](docs/REPORT_GENERATION.md) | PDF report architecture, data flow, API, security, troubleshooting |

---

## License

Distributed under the **MIT License**.
