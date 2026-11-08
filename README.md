# HealthTrack AI — Backend API

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-VectorStore-orange)](https://www.trychroma.com/)
[![Gemini](https://img.shields.io/badge/Google_Gemini-2.5--flash-8E75B2?logo=google&logoColor=white)](https://ai.google.dev/)

Backend API service for **HealthTrack AI**, an intelligent medical report extraction, validation, and longitudinal health tracking platform.

It processes multi-page PDF diagnostic reports, normalizes lab metrics into canonical forms, detects urgent medical anomalies deterministically, stores semantic chunks in ChromaDB for Retrieval-Augmented Generation (RAG), and serves data through a clean FastAPI REST API.

---

## 🌟 Key Capabilities

- **Multi-Page Document Processing:** Extracts text page-by-page with layout fidelity using PyMuPDF (`fitz`).
- **Cryptographic Deduplication:** Uses SHA-256 file hashing to prevent redundant report ingestion.
- **AI-Powered Structured Extraction:** Leverages Google Gemini (`gemini-2.5-flash`) to parse patient metadata, clinical dates, and complete test observation tables into typed schemas.
- **Deterministic Validation & Normalization:**
  - Standardizes hundreds of erratic lab naming conventions to canonical tests (e.g., *SGPT*, *ALT (SGPT)*, *Alanine Transaminase* ➔ **`ALT`**).
  - Validates numeric results against biological plausibility ranges.
  - Classifies status deterministically (`within_range`, `attention`, `significant`, `potentially_urgent`).
- **Urgent Clinical Alert Engine:** Rule-based triggers for critical lab emergencies (e.g., ALT/AST > 3x upper limit, severe thrombocytopenia, critical glucose deviation).
- **Personalized Health Guidance:** Generates non-prescriptive lifestyle/dietary Do's & Don'ts and physician discussion questions.
- **RAG Medical Assistant:** Hybrid retrieval combining structured SQLite observations and ChromaDB vector embeddings for contextual Q&A with document source citations.
- **Security & Multi-Tenant Isolation:** JWT-based bearer authentication, Bcrypt password hashing, and server-side encryption for user Gemini API keys.

---

## 🏗️ Architecture & Directory Layout

```
backend/
├── app/
│   ├── api/                  # FastAPI REST route controllers
│   │   ├── auth.py           # JWT generation, Bcrypt hashing, OAuth2 scheme
│   │   ├── auth_routes.py    # Login, registration, profile endpoints
│   │   ├── chat.py           # RAG Q&A endpoints (report-specific & history-wide)
│   │   ├── dashboard.py      # Aggregated metrics, attention items, priority trends
│   │   ├── guidance.py       # Personalized guidance and urgent alerts
│   │   ├── patients.py       # Patient & family profile management
│   │   ├── reports.py        # PDF upload, listing, details, background processor
│   │   ├── settings.py       # Gemini API key storage and testing
│   │   └── trends.py         # Longitudinal biomarker time-series data
│   ├── database/             # SQLAlchemy ORM models & data access layer
│   │   ├── models.py         # User, Patient, Report, Observation entities
│   │   ├── repositories.py   # Database query abstractions
│   │   └── session.py        # Engine and session lifecycle management
│   ├── extraction/           # LLM extraction & validation logic
│   │   ├── extractor.py      # Gemini structured JSON extraction prompts
│   │   └── validator.py      # Deterministic range and biological checks
│   ├── guidance/             # Health advisory engine
│   │   └── health_advisor.py # Urgent alert triggers & lifestyle guidance
│   ├── ingestion/            # Document parsing pipeline
│   │   ├── pdf_parser.py     # PyMuPDF page extractor
│   │   └── report_processor.py # End-to-end background processing pipeline
│   ├── normalization/        # Clinical standardization
│   │   └── test_normalizer.py# Canonical mapping for lab biomarker variations
│   ├── rag/                  # Retrieval-Augmented Generation
│   │   ├── chains.py         # Gemini prompt chains & context builders
│   │   └── chroma.py         # ChromaDB client & vector indexing service
│   ├── schemas/              # Pydantic v2 validation models
│   ├── config.py             # Settings management via pydantic-settings
│   └── main.py               # FastAPI application entrypoint & middleware
├── tests/                    # Pytest test suite
├── uploads/                  # Uploaded PDF document storage
├── chroma_data/              # Persistent ChromaDB vector database files
├── requirements.txt          # Python package dependencies
├── .env.example              # Environment variables template
└── .gitignore                # Git ignore configuration
```

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.10+** (Tested on Python 3.11 & 3.14)
- **pip** package manager

### 1. Clone & Navigate
```bash
git clone https://github.com/<YOUR_GITHUB_USERNAME>/healthtrack-ai-backend.git
cd healthtrack-ai-backend
```

### 2. Set Up Virtual Environment
```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the example environment file:
```bash
cp .env.example .env
```

Review or update `.env` as needed:
```ini
# Database
DATABASE_URL=sqlite:///./healthtrack.db

# Authentication
SECRET_KEY=change-this-to-a-secure-random-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# File Storage & Vector DB
UPLOAD_DIR=./uploads
CHROMA_PERSIST_DIR=./chroma_data

# Google Gemini (Optional in .env — users can also configure via UI)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

---

## ▶️ Running the Server

Start the backend using Uvicorn:
```bash
python -m uvicorn app.main:app --reload --port 8000
```

Once running:
- **API Base:** `http://localhost:8000`
- **Interactive Swagger UI:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`
- **Health Check:** `http://localhost:8000/api/health`

---

## 🧪 Running Tests

Run the test suite to verify extraction, normalization, and deterministic status classification:
```bash
python -m pytest tests
```

---

## 📡 API Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/register` | Register a new user account |
| `POST` | `/api/auth/login` | Authenticate and obtain JWT access token |
| `GET` | `/api/auth/me` | Fetch authenticated user profile |
| `GET` | `/api/patients` | List patient profiles for current user |
| `POST` | `/api/patients` | Create a new family patient profile |
| `POST` | `/api/reports/upload` | Upload PDF report (runs background extraction) |
| `GET` | `/api/reports` | List all processed reports for a patient |
| `GET` | `/api/reports/{id}` | Get report metadata and extracted observations |
| `DELETE` | `/api/reports/{id}` | Permanently delete a report and its vector chunks |
| `GET` | `/api/dashboard` | Aggregated metrics, attention items, priority trends |
| `GET` | `/api/trends/available-tests` | List all tests available for time-series charting |
| `GET` | `/api/trends/{test_name}` | Fetch longitudinal trend points for a specific biomarker |
| `GET` | `/api/guidance/latest` | Get health guidance & urgent alerts for latest report |
| `GET` | `/api/guidance/report/{id}` | Get health guidance & urgent alerts for a specific report |
| `POST` | `/api/chat/report` | RAG chat scoped to a single report |
| `POST` | `/api/chat/history` | RAG chat across entire multi-year patient history |
| `POST` | `/api/settings/gemini` | Store encrypted Gemini API key |

---

## 🛡️ Medical Safety & Ethical AI Notice

This software is designed strictly for educational and longitudinal tracking purposes. 
- It does **not** provide formal medical diagnoses.
- It does **not** prescribe drugs, suggest dosages, or modify existing treatment plans.
- All urgent alerts advise consultation with licensed medical professionals.
- All clinical interpretations should be evaluated by qualified healthcare providers.

