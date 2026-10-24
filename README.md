# Crowd Heatmap & Business Intelligence Platform

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-6.0+-green.svg)](https://www.djangoproject.com/)
[![Database](https://img.shields.io/badge/database-PostgreSQL%20%7C%20Supabase%20%7C%20SQLite-336791.svg)](https://supabase.com/)
[![AI](https://img.shields.io/badge/AI-Gemini%202.0%20%7C%20Grok%20xAI-orange.svg)](https://ai.google.dev/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An enterprise-grade **Business Intelligence (BI) and Spatial Intelligence** web platform that helps entrepreneurs, retail chains, and startups identify the most viable, profitable locations to launch businesses across India. 

The platform combines **real-time crowd density heatmap analytics**, a **Machine Learning recommendation engine (Scikit-Learn)**, an **Extended Huff Gravity Model & multi-factor revenue forecasting engine**, **Dual-AI Intelligence (Google Gemini 2.0 + Grok xAI)**, a **conversational AI Assistant with instant site search & navigation**, **investment-grade PDF report generation (WeasyPrint + ReportLab fallback)**, and enterprise **2FA & Account Security** with Supabase Cloud integration.

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
- [AI Assistant & Dual-AI Engine](#ai-assistant--dual-ai-engine)
- [Account Security & 2FA](#account-security--2fa)
- [User Guide](#user-guide)
- [Deployment](#deployment)
- [Documentation](#documentation)
- [License](#license)

---

## Overview

The platform answers four critical commercial questions for any area in India:

1. **How crowded is this area?** — Real-time sector-based heatmap using OpenStreetMap POI data and calibrated footfall density circles.
2. **What business should I open here?** — Scikit-Learn decision tree classification + rule-based category feasibility engine.
3. **How much revenue can I expect?** — Multi-factor simulation engine modeling daypart distribution, customer ticket size, competitor attraction, Customer Quality Index (CQI), and spatial gravity decay (Extended Huff Model).
4. **Is this location viable and risk-resistant?** — Independent Dual-AI review (Gemini spatial synthesis + Grok critical risk stress-testing).

Data is fetched live from **OpenStreetMap** (Nominatim geocoding + Overpass API) across configurable analysis radii (2 km to 5 km).

---

## Key Features

### 🗺️ Real-Time Crowd Heatmap & POI Radar
- **Calibrated Footfall Circles**: Color-coded crowd density overlays accurately calibrated for spatial density:
  - 🔴 **High Density (~420m radius)**: Heavy pedestrian footfall, prime commercial hub.
  - 🟡 **Medium Density (~300m radius)**: Moderate, steady consumer traffic with balanced competition.
  - 🟢 **Low Density (~200m radius)**: Quieter developing or residential zones.
- **Dynamic 3×3 Sector Grid**: Classifies area sectors into High (≥15 POIs), Medium (5–14 POIs), and Low (<5 POIs).
- **Seamless Zero-Gap Header**: Dynamic map control bar attached flush to the navigation bar.
- **Front-of-Map POI Markers**: Feasible business markers and candidate pins elevated to the front of map layers for unobstructed visibility.
- **Nearby Popular Places Radar**: Scans nearby commercial establishments (cafes, pharmacies, gyms, retail stores, restaurants) with one-click bookmarking.

### 🤖 Conversational AI Assistant & Instant Feature Router
- **Friendly Conversational Mode**: Natural, warm conversation just like **ChatGPT and Google Gemini**. Responds instantly (<70ms) to greetings, friendly chit-chat, name inquiries (*"what is your name"*), humor (*"tell me a joke"*), and advice.
- **Zero-Lag Website Knowledge Base (`SITE_FEATURES_KNOWLEDGE`)**: Answers questions about any platform tool (Heatmap, Business Analytics, Startup Form, Favorites, Reports, Revenue, GPS) in milliseconds without network waiting.
- **Instant Redirection & Action Buttons**: Each answered query renders an interactive action button (e.g. `[ 🚀 Open Live Heatmap ]`, `[ 📊 Go to Business Analytics ]`, `[ 📄 Open Reports Hub ]`). Direct navigation commands automatically redirect within 350ms.
- **Live Search-As-You-Type Preview**: Typing in the chatbot input bar (e.g. `"rep"`, `"ana"`, `"map"`) displays a glassmorphic quick-jump preview popup with one-click **Go →** buttons.
- **Dual-Action Input Handling**: Supports both <kbd>Enter</kbd> keypress and the **Send** button seamlessly.

### 🧠 Dual-AI Intelligence Architecture (Gemini 2.0 + Grok)
- **Primary Spatial Intelligence (Google Gemini 2.0 / 2.5 Flash)**: Analyzes spatial POI distributions, demographic context, competitive advantages, and market trends.
- **Critical Risk Review (xAI Grok)**: Independently stress-tests business viability, identifying commercial risks, footfall bottlenecks, saturation hazards, and operational pitfalls.

### 📊 Interactive Dashboard & Launchpad UI
- **Single-Scroll Architecture**: Removed nested inner scrollbars in favor of a clean, single-page viewport with a full-width responsive feature grid.
- **Seamless View Switching**: Instant transition between **Dashboard Launchpad**, **Live Heatmap (Full Window)**, **Business Analytics (`?ai=true`)**, and **Startup Planning Form** without page reload.
- **Live Revenue Animations & Flashcards**: Interactive 4×4 business category cards with projected monthly turnover and break-even metrics.

### 📋 Startup Planning Form & Feasibility Engine
- Interactive startup venture calculator allowing entrepreneurs to specify business category, target capital budget, minimum required footfall, and operating hours to receive algorithmic suitability scores.

### ⭐ Favorites Hub & Candidate Ranking
- Bookmark candidate locations and discovered businesses with one tap on the heart icon.
- Backed by **Supabase Cloud PostgreSQL** (`public.favorite_places`) with Row Level Security (RLS) and token authentication.
- Candidate scoring blends user category tastes, time-decayed popularity across users, and proximity.

### 📄 Investment-Grade Business Intelligence Reports (PDF)
- Generates comprehensive 20–25 page executive PDF reports for any location.
- **Dual PDF Engine**: Renders high-fidelity reports via **WeasyPrint** with an automated zero-dependency fallback to **ReportLab**, guaranteeing reliable PDF export on Windows, macOS, and Linux without GObject/Pango DLL failures.
- Includes executive summary, KPI scorecard, real map screenshot, SWOT analysis, competitor mapping, footfall breakdown, and investment roadmap.
- Stored permanently in the user's **Favorites Hub** for instant one-click download.

### 🔒 Enterprise Account Security & 2FA
- **Custom User Model** (`users.CustomUser`) using email authentication with role separation (**Businessman** & **Customer**).
- **Two-Factor Authentication (2FA)**: TOTP compatible with Google Authenticator, Microsoft Authenticator, and Authy.
- **Single-Use Cryptographic Recovery Codes**: Hashed backup codes for emergency access.
- **Active Session & Device Manager**: Real-time IP, browser, and device tracking with remote revocation.
- **Audit Logging**: Comprehensive security event tracking.

---

## Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          Browser (Frontend)                            │
│  Leaflet Map │ Dashboard UI │ Conversational AI Assistant │ Form Modal  │
└──────────────────┬───────────────────────────────┬─────────────────────┘
                   │ HTTP/REST                     │ WebSocket (ws/chat/)
                   ▼                               ▼
┌──────────────────────────────┐    ┌────────────────────────────────────┐
│     Django Views (REST)      │    │     Django Channels (Daphne)       │
│   tracker & business_intel   │    │     tracker/consumers.py           │
└──────────────┬───────────────┘    └──────────────┬─────────────────────┘
               │                                   │
               ▼                                   ▼
┌──────────────────────────────┐    ┌────────────────────────────────────┐
│   Spatial Gravity Engine     │    │       Dual-AI Orchestrator         │
│   (Extended Huff Model)      │    │  Gemini 2.0 Flash + Grok xAI       │
└──────────────┬───────────────┘    └────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐    ┌────────────────────────────────────┐
│    Scikit-Learn ML Model     │    │       PDF Generation Pipeline      │
│    (business_model.pkl)      │    │  WeasyPrint + ReportLab Fallback   │
└──────────────┬───────────────┘    └────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐    ┌────────────────────────────────────┐
│    OpenStreetMap APIs        │    │    SQLite / Supabase PostgreSQL    │
│    Nominatim + Overpass      │    │    (Auth, Favorites, History, RLS) │
└──────────────────────────────┘    └────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Details |
|-------|------------|---------|
| **Backend Framework** | Django 6.0+, Django Channels 4.1 | Asynchronous ASGI-powered web framework |
| **ASGI Server** | Daphne 4.1 | WebSocket & HTTP multiplexer |
| **Frontend Core** | HTML5, CSS3 (Vanilla), JavaScript (ES6+) | Modern dark glassmorphic design, zero-gap layout |
| **Mapping & GIS** | Leaflet.js, OpenStreetMap, Nominatim, Overpass API | Real-time geospatial rendering & POI queries |
| **Machine Learning** | Scikit-Learn, Pandas, NumPy | DecisionTreeClassifier trained on business datasets |
| **Spatial Gravity Model** | Extended Huff Gravity Model | Retail attraction, distance decay, and market share |
| **Dual Generative AI** | Google Gemini 2.0 / 2.5 Flash + xAI Grok | Spatial synthesis & critical risk stress-testing |
| **PDF Generation** | WeasyPrint + ReportLab Fallback | 20–25 page investment reports with zero-dependency fallback |
| **Database** | SQLite (dev) / PostgreSQL / Supabase | Cloud PostgreSQL via `dj-database-url` with RLS |
| **Security & Auth** | PyOTP, QRCode, Cryptographic Hash Codes | Two-Factor Authentication, Session Manager, Audit Log |
| **Static Serving** | WhiteNoise 6.7 | Compressed static asset caching & delivery |
| **Production Ready** | Render / Railway / Docker / Supabase | Complete `Procfile`, `run.sh`, `run.py`, and `run.ps1` |

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
│   ├── consumers.py             # WebSocket Dual-AI chatbot consumer
│   ├── routing.py               # WebSocket URL routing (/ws/chat/)
│   ├── ai/                      # Dual-AI Intelligence engine
│   │   ├── orchestrator.py      # Dual-AI dispatcher (Gemini + Grok + friendly chat)
│   │   ├── gemini_service.py    # Google Gemini spatial intelligence
│   │   ├── grok_service.py      # xAI Grok critical risk reviewer
│   │   └── validators.py        # Input sanitation & scope validation
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
├── report_generator/            # PDF report generator (data collection, charts, flowcharts, Gemini text)
│   ├── services.py              # Shared pipeline for dashboard + chatbot, background thread, stages
│   ├── data_collector.py        # Runs the existing analysis engines for one location
│   ├── ai_writer.py / prompts.py  # Gemini stages with schema + figure validation and fallbacks
│   ├── chart_generator.py       # Matplotlib charts from real analysis values
│   ├── flowchart_generator.py   # Inline-SVG flowcharts
│   ├── pdf_generator.py         # Dual PDF engine: WeasyPrint + ReportLab fallback
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
# Django Security
DEBUG=True
SECRET_KEY=your_secret_key_here
SITE_URL=http://127.0.0.1:8000

# Database (Supabase Cloud PostgreSQL or local SQLite)
DATABASE_URL=postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?pgbouncer=true

# Supabase Auth & Cloud Integration (Optional)
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_jwt_token
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# Dual Generative AI Engines
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL_NAME=gemini-2.5-flash
GROK_API_KEY=your_xai_grok_api_key
GROK_MODEL_NAME=grok-2-latest

# Email / SMTP Settings (Optional - console output in dev)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
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
| `SITE_URL` | No | `http://127.0.0.1:8000` | Base public URL for redirects and absolute links |
| `DATABASE_URL` | No | `sqlite:///db.sqlite3` | PostgreSQL / Supabase connection URI |
| `SUPABASE_URL` | No | None | Supabase project URL (e.g. `https://[ref].supabase.co`) |
| `SUPABASE_ANON_KEY` | No | None | Supabase client anon JWT key |
| `SUPABASE_SERVICE_ROLE_KEY` | No | None | Supabase service-role administrative key (backend only) |
| `GEMINI_API_KEY` | No | None | Google AI Studio API key for Gemini spatial intelligence |
| `GEMINI_MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model version for chat assistant & report writer |
| `GROK_API_KEY` | No | None | xAI API key for Grok critical risk review |
| `GROK_MODEL_NAME` | No | `grok-2-latest` | Grok model name for independent risk evaluation |
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
| GET | `/` | Home page with full-window interactive map & search |
| GET | `/dashboard/` | Interactive BI dashboard, live heatmap & analytics launchpad |
| GET | `/favorites/` | Saved candidate places, bookmarks & generated PDF reports hub |
| POST | `/search-location/` | Geocode location name via OpenStreetMap Nominatim |
| POST | `/autocomplete-location/` | Autocomplete search suggestions across India |
| POST | `/find-popular-places/` | Ranked POIs within 2 km + per-place revenue estimates |
| POST | `/analyze-crowd-intensity/` | 3×3 sector heatmap & ML business category prediction |
| POST | `/check-feasibility/` | Go/No-Go commercial feasibility check for a business type |
| POST | `/api/analyze-location/` | Full smart revenue forecast (Huff spatial model) |
| POST | `/api/generate-best-locations/` | Ranked AI candidate relocation zones (top 3) |
| GET | `/api/business-types/` | Dynamic list of business categories |
| POST | `/api/find-matching-locations/` | Match locations by crowd intensity + business type |
| POST | `/submit-form/` | Submit business inquiry & startup profile |
| POST | `/contact/` | Contact message submission |
| GET | `/accounts/security/` | Security Center (2FA, active sessions, audit logs) |
| POST | `/chat/` | HTTP fallback endpoint for AI Assistant conversational responses |
| WS | `/ws/chat/` | Real-time WebSocket Dual-AI assistant (Gemini + Grok) |
| POST | `/api/reports/generate/` | Start a PDF report generation pipeline for selected location |
| GET | `/api/reports/<id>/status/` | Report generation stage telemetry and progress status |
| GET | `/api/reports/<id>/download/` | Download finished 20–25 page investment report PDF |

---

## AI Assistant & Dual-AI Engine

The platform features an intelligent, conversational **AI Assistant** accessible from any page:

### 1. Conversational Chat Mode (Gemini & ChatGPT Experience)
- Chat naturally with the AI like a business partner and friend.
- Instant, sub-70ms friendly responses for casual conversation (*"what is your name"*, *"how are you"*, *"tell me a joke"*, *"can we be friends"*, *"thank you"*).
- Eliminates unnecessary network and geocoding latency for non-geographic chat.

### 2. Zero-Lag Site Feature Knowledge Base & Fast Router
- Client-side feature registry (`SITE_FEATURES_KNOWLEDGE`) matching user queries against all platform capabilities:
  - **Live Crowd Heatmap**: Explains footfall density circles (Red=420m, Yellow=300m, Green=200m) and satellite layers.
  - **Business Analytics**: Details market demand index, category breakdown, and competition metrics.
  - **Startup Planning Form**: Outlines budget criteria, target footfall, and suitability scoring.
  - **Favorites & Reports**: Guides users to saved bookmarks and generated PDF intelligence reports.
  - **Popular Places & GPS Locate**: Explains POI scanning and browser geolocation.
- Every matched answer includes a rich description and a high-contrast action button (e.g. `[ 🚀 Open Live Heatmap ]`, `[ 📊 Go to Business Analytics ]`, `[ 📄 Open Reports Hub ]`).
- Direct navigation queries (e.g., *"go to map"*, *"open analytics"*, *"take me to reports"*) auto-redirect immediately in 350ms.

### 3. Live Search-As-You-Type Preview
- Displays an interactive glassmorphic popup above the input bar as you type, showing matched features and one-click **Go →** buttons.

### 4. Dual-AI Backend Architecture
- **Google Gemini 2.0 / 2.5 Flash**: Acts as the primary spatial intelligence engine, synthesizing geographic crowd distribution, demographic demand, and competitive clustering.
- **xAI Grok**: Acts as the critical risk review engine, stress-testing commercial assumptions and identifying market saturation risks, overhead threats, and footfall bottlenecks.

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
2. **Explore Map**: Search for any city or landmark in India, or click "Find My Location" to center the map using GPS.
3. **Analyze Crowd Intensity**: View the 3×3 sector heatmap and calibrated crowd circles (Red 420m, Yellow 300m, Green 200m).
4. **Discover Popular Places**: Click "Nearby Popular Places Radar" to generate the business card matrix, footfall scores, and revenue estimates.
5. **Chat with AI Assistant**:
   - Chat casually like a friend: *"What is your name?"*, *"How are you?"*
   - Check commercial feasibility: *"Open cafe in Indiranagar"*, *"Is pharmacy feasible in Koramangala?"*
   - Jump to any page: *"Take me to map"*, *"Show business analytics"*, *"Where are my reports?"*
6. **Save to Favorites**: Tap the heart icon on any place card to save it to your Favorites hub.
7. **Download PDF Intelligence Reports**: Generate a full 20–25 page investment report and download it anytime from the Favorites hub.

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
