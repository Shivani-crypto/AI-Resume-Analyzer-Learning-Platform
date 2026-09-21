# Unified AI Resume Analyzer & Micro-Learning Platform
## System Architecture, Module Connections, API Key Flows & Setup Instructions

---

> 🌐 **Live Application:** [https://ai-resume-analyzer-learning-platform.onrender.com/](https://ai-resume-analyzer-learning-platform.onrender.com/)

## 1. Executive Summary & High-Level System Architecture

The **Unified AI Resume Analyzer & Micro-Learning Platform** is an enterprise-grade AI-powered web application built with **FastAPI**, **Jinja2 Templates**, **SQLAlchemy ORM**, **Scikit-Learn (TF-IDF & Cosine Similarity)**, **LangChain / RAG FAISS**, **ReportLab PDF Generation**, and **Supabase / Local Storage**.

The application bridges resume scoring, automated skill gap detection, dynamic AI micro-course generation, interactive quiz assessments, PDF certificate generation, tiered subscription management, and executive administration.

```mermaid
graph TD
    User["👤 Student / Jobseeker"] -->|HTTP Request| FastAPI["⚡ FastAPI Core App (main.py)"]
    Admin["🛡️ System Admin"] -->|HTTP / Admin Token| FastAPI

    subgraph Core Modules
        FastAPI --> Auth["🔐 Auth & JWT Engine (app/api/auth.py)"]
        FastAPI --> ResumeEngine["📄 Resume Analyzer (utils/analyzer.py & extractor.py)"]
        FastAPI --> CourseEngine["🎓 Course & Player Engine (app/api/courses.py)"]
        FastAPI --> QuizEngine["✍️ Quiz & Cert Engine (app/api/quizzes.py)"]
        FastAPI --> PaymentEngine["💳 Payment Gateway & Quotas (app/services/payment_service.py)"]
        FastAPI --> AdminEngine["⚙️ Admin Control Panel (main.py / admin.html)"]
    end

    subgraph Data & Storage Layers
        ResumeEngine --> ML["🧠 Scikit-Learn TF-IDF & Cosine Match"]
        CourseEngine --> RAG["🔍 FAISS Vector Store / LLM RAG"]
        CourseEngine & ResumeEngine --> Storage["📦 Supabase Storage / Local Uploads"]
        FastAPI --> DB[("🗄️ SQLite / Supabase PostgreSQL")]
    end

    subgraph External Cloud & AI Services
        CourseEngine --> Gemini["✨ Google Gemini API"]
        CourseEngine --> Groq["⚡ Groq LLM API"]
        CourseEngine --> Cohere["🌌 Cohere Embeddings API"]
        PaymentEngine --> Razorpay["💳 Razorpay Payment API"]
        PaymentEngine --> UPI["📱 Merchant Direct UPI QR"]
    end
```

---

## 2. Comprehensive Inter-Module Connection Flowcharts

### 2.1. Resume Analysis & Skill Extraction Flowchart

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Candidate
    participant Web as Web UI (analysis.html)
    participant API as FastAPI Router (main.py)
    participant Extractor as Text Extractor (utils/extractor.py)
    participant Normalizer as Skill Normalizer (utils/skill_normalizer.py)
    participant ML as ML Matcher (utils/analyzer.py)
    participant DB as Database (local_dev.db)

    User->>Web: Upload Resume (PDF / DOCX / Image) + Job Description
    Web->>API: POST /analyze-resume (UploadFile)
    API->>Extractor: extract_text_from_file(filepath)
    Note over Extractor: Uses pdfplumber -> pypdf -> pytesseract (OCR) fallback
    Extractor-->>API: Clean Formatted Text
    API->>Normalizer: extract_skills(clean_text)
    Normalizer-->>API: Extracted Skill Set [Python, FastAPI, SQL, ...]
    API->>ML: calculate_ml_match(resume_text, jd_text)
    Note over ML: Runs TF-IDF Vectorizer + Cosine Similarity scoring
    ML-->>API: Match Percentage (0-100%) + Missing Skills List
    API->>DB: save_resume(email, filename, score, missing_skills)
    API-->>Web: Render Analysis Page with Course Recommendations
```

### 2.2. Dynamic Micro-Course & Interactive AI Player Flowchart

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Learner
    participant Player as Learning Player (player.html)
    participant CourseAPI as Course Router (app/api/courses.py)
    participant AIService as AI Generator (app/services/ai_course_service.py)
    participant Storage as Storage Service (utils/supabase_storage.py)

    User->>Player: Open Course (e.g., "Python Masterclass")
    Player->>CourseAPI: GET /api/learning/courses/{course_id}
    CourseAPI->>AIService: Fetch / Generate Course Curriculum
    Note over AIService: Queries Gemini/Groq/Ollama LLM for 5-slide masterclass & 1-min video script
    AIService-->>CourseAPI: Structured Course JSON & Slides
    CourseAPI->>Storage: Store Generated Video / PDF Notes
    CourseAPI-->>Player: Return Lessons, Slides, Video & Interactive AI Tutor
```

### 2.3. Quiz Assessment & PDF Certificate Generation Flowchart

```mermaid
sequenceDiagram
    autonumber
    actor User as Candidate
    participant QuizUI as Quiz Component (player.html / course.html)
    participant QuizAPI as Quiz Router (app/api/quizzes.py)
    participant CertService as Certificate Service (app/services/certificate_service.py)
    participant Storage as Supabase Storage
    participant DB as Database

    User->>QuizUI: Submit Quiz Answers (5 Questions)
    QuizUI->>QuizAPI: POST /api/quizzes/submit
    QuizAPI->>DB: save_quiz_result(email, topic, score, passed)
    alt Score >= 25% (Passed)
        QuizAPI->>CertService: generate_certificate_pdf(user_name, topic, score)
        Note over CertService: Uses ReportLab to generate official PDF with UUID QR Code
        CertService->>Storage: upload_certificate_to_supabase(pdf_bytes)
        CertService->>DB: save_certificate(email, name, title, score, cert_url, cert_uuid)
        QuizAPI-->>QuizUI: Pass Status + View/Download Certificate PDF Link
    else Score < 25% (Failed)
        QuizAPI-->>QuizUI: Fail Notice (Minimum 25% passing score required)
    end
```

### 2.4. Payment Gateway & Tiered Subscription Flowchart

```mermaid
sequenceDiagram
    autonumber
    actor User as Subscriber
    participant Modal as Payment Gateway Modal (analysis.html)
    participant PayAPI as Subscriptions Router (app/api/subscriptions.py)
    participant PayService as Payment Service (app/services/payment_service.py)
    participant DB as Database

    User->>Modal: Select Plan (Basic ₹99 / Pro ₹999 / VIP ₹4,999) or enter Coupon (FREE99)
    alt Coupon Validation
        Modal->>PayAPI: POST /api/subscriptions/coupons/validate
        PayAPI->>PayService: validate_coupon(code, original_amount)
        PayService-->>Modal: Discount Amount & Final Payable Total
    end
    alt Direct UPI QR Payment
        User->>Modal: Scan Merchant UPI QR & Enter 12-Digit UTR Ref Number
        Modal->>PayAPI: POST /api/subscriptions/verify-upi-payment
        PayAPI->>PayService: verify_upi_utr_payment(utr_number, plan, amount)
        PayService->>DB: Record Subscription (payment_status="SUCCESS", is_active=True)
        PayService-->>Modal: Instant Plan Activation + Course Unlock
    else Razorpay Checkout
        Modal->>PayAPI: POST /api/subscriptions/razorpay/verify-payment
        PayAPI->>PayService: verify_razorpay_signature(...)
        PayService->>DB: Record Subscription (is_active=True)
        PayService-->>Modal: Payment Approved + Full Access Granted
    end
```

---

## 3. Software & Hardware Requirements

### 3.1. System & Runtime Requirements
- **Operating System**: Windows 10/11, Ubuntu 20.04+, or macOS 12+
- **Python Runtime**: Python `3.10` or Python `3.11` (64-bit required)
- **Node.js Runtime** *(Optional, for front-end tooling)*: Node.js `v18+` & `npm`

### 3.2. Hardware Specifications
| Specification | Minimum Required | Recommended Production |
| :--- | :--- | :--- |
| **CPU** | 4-Core x86_64 / ARM64 | 8-Core Intel Core i7 / AMD Ryzen 7 / Apple M-Series |
| **RAM** | 8 GB RAM | 16 GB or 32 GB RAM |
| **Disk Space** | 10 GB Free Storage | 50 GB SSD / NVMe Storage |
| **Network** | 5 Mbps Broadband | 50+ Mbps High-Speed Fiber |

### 3.3. Dependencies & Libraries (`requirements.txt`)
- **Web Framework**: `fastapi>=0.110.0`, `uvicorn[standard]>=0.28.0`, `jinja2>=3.1.3`, `python-multipart>=0.0.9`
- **ORM & Data**: `sqlalchemy>=2.0.0`, `pydantic[email]>=2.6.0`, `email-validator>=2.0.0`, `python-dotenv>=1.0.1`
- **Machine Learning & NLP**: `scikit-learn>=1.4.0`, `sentence-transformers>=2.5.0`, `faiss-cpu>=1.7.4`, `langchain>=0.1.0`
- **Document & Image Processing**: `pdfplumber>=0.10.3`, `pypdf>=4.0.0`, `python-docx>=1.1.0`, `pytesseract>=0.3.10`
- **PDF Generation**: `reportlab>=4.1.0`
- **Security & Authentication**: `python-jose[cryptography]>=3.3.0`, `bcrypt>=4.1.2`
- **HTTP & Storage Integrations**: `requests>=2.31.0`, `boto3>=1.34.0`, `httpx>=0.27.0`

---

## 4. Step-by-Step API Key Creation & Configuration Flows

### 4.1. Google Gemini API Key Setup
1. Visit the [Google AI Studio Console](https://aistudio.google.com/).
2. Log in with your Google account.
3. Click **Get API key** -> **Create API key in new project**.
4. Copy your generated API Key (starts with `AIzaSy...`).
5. Open your `.env` file and set:
   ```env
   GEMINI_API_KEY="your_gemini_api_key_here"
   ```

### 4.2. Groq Cloud API Key Setup
1. Navigate to [Groq Cloud Console](https://console.groq.com/).
2. Create an account and navigate to **API Keys**.
3. Click **Create API Key**, enter a label (e.g., `CareerPro-App`), and copy the key (starts with `gsk_...`).
4. In `.env`:
   ```env
   GROQ_API_KEY="gsk_your_groq_api_key_here"
   ```

### 4.3. Cohere API Key Setup
1. Go to [Cohere Dashboard](https://dashboard.cohere.com/).
2. Register and open **API Keys**.
3. Copy your **Trial** or **Production** API Key.
4. In `.env`:
   ```env
   COHERE_API_KEY="cohere_your_key_here"
   ```

### 4.4. Supabase Cloud Storage & Database Setup
1. Sign up at [Supabase.com](https://supabase.com/).
2. Create a new project named `career-pro-app`.
3. In **Project Settings** -> **Database**, copy your Connection String (PostgreSQL URL).
4. In **Project Settings** -> **API**, copy your **Project URL** and **`service_role` secret key**.
5. Go to **Storage** -> **New Bucket**, create public buckets: `images`, `videos`, `files`, `certificates`.
6. Update `.env`:
   ```env
   DATABASE_URL="postgresql://postgres:your_password@db.your_project.supabase.co:5432/postgres"
   STORAGE_PROVIDER=supabase
   SUPABASE_URL="https://your_project.supabase.co"
   SUPABASE_KEY="your_supabase_service_role_key"
   SUPABASE_BUCKET_NAME=files
   ```

### 4.5. Razorpay Merchant Gateway Setup
1. Sign in to [Razorpay Dashboard](https://dashboard.razorpay.com/).
2. Go to **Account & Settings** -> **API Keys** under Developer Controls.
3. Click **Generate Test Key** (or Live Key).
4. Copy the **Key ID** (`rzp_test_...`) and **Key Secret**.
5. Update `.env`:
   ```env
   RAZORPAY_KEY_ID="rzp_test_your_key_id"
   RAZORPAY_KEY_SECRET="your_key_secret"
   ```

### 4.6. Gmail SMTP App Password Setup (for Email Verification & Receipts)
1. Log in to your Google Account and go to [Security Settings](https://myaccount.google.com/security).
2. Enable **2-Step Verification**.
3. Search for **App Passwords** in the Google search bar.
4. Create an App Password named `CareerPro Mailer`.
5. Copy the 16-character generated code (e.g., `qfifnugkvgsukrhi`).
6. Update `.env`:
   ```env
   SMTP_HOST="smtp.gmail.com"
   SMTP_PORT=587
   SMTP_USER="your_email@gmail.com"
   SMTP_PASSWORD="your_16_char_app_password"
   SMTP_FROM_EMAIL="your_email@gmail.com"
   SMTP_FROM_NAME="Career Pro Platform"
   SMTP_TLS=True
   ```

---

## 5. Module-by-Module Methodology & Setup Instructions

```
c:\Users\TruProjects\Documents\test
├── app/
│   ├── api/             # FastAPI Endpoint Routers (auth, courses, quizzes, subscriptions, admin)
│   ├── core/            # Core DB setup & config (database.py, security.py)
│   ├── models/          # SQLAlchemy Database Models (user, course, progress, subscription, analysis)
│   ├── schemas/         # Pydantic Request/Response Schemas
│   └── services/        # Business Logic Services (payment, certificate, AI, email, progress)
├── templates/
│   ├── admin/           # Admin Dashboard & User Provisioning (admin.html, admin_login.html)
│   ├── common/          # Public Auth Pages (login.html, signup.html)
│   ├── learning/        # Micro-Learning UI & Interactive Video Player (player.html, course.html)
│   └── user/            # Candidate Resume Analysis & Dashboard (analysis.html, dashboard.html, history.html)
├── utils/
│   ├── analyzer.py      # TF-IDF, Cosine Similarity & Machine Learning Match Engine
│   ├── extractor.py     # PDF, DOCX, TXT & Tesseract OCR Text Extractor
│   ├── skill_normalizer.py # Skill Taxonomies, Canonical Aliases & Keyword Extractor
│   └── supabase_storage.py # Unified Cloud File Uploader (Images, Videos, PDFs)
├── db.py                # Database Core Utility & CRUD Operations
├── main.py              # Main FastAPI Application Dispatcher & Server Entrypoint
└── requirements.txt     # Python Dependencies Manifest
```

### Module 1: Main Application Dispatcher (`main.py`)
- **Methodology**: Operates as the central routing hub using FastAPI. Handles middleware (CORS, Static Mounting, Cookie Session extraction), template rendering, and API endpoint integration.
- **Key Files**: [`main.py`](file:///c:/Users/TruProjects/Documents/test/main.py)
- **Connections**: Connects all API routers under `/api/v1` and renders Jinja2 views from `templates/`.

### Module 2: Persistence Layer & Schemas (`app/core/database.py`, `db.py`, `app/models/`)
- **Methodology**: Operates via SQLAlchemy ORM (`create_engine`, `sessionmaker`, `declarative_base`).
  - Reads `DATABASE_URL` environment variable. By default, initializes a local thread-safe **SQLite database** (`sqlite:///./local_dev.db`).
  - If `DATABASE_URL` is set to PostgreSQL (e.g. Supabase Postgres `postgresql://...`), it connects with connection pooling (`pool_pre_ping=True`).
  - Implements automatic exception handling: if remote connection fails, it catches the error and falls back to `sqlite:///./local_dev.db`.
  - Manages relational ORM models: `User`, `Resume`, `Course`, `GeneratedCourse`, `QuizResult`, `Certificate`, `Subscription`, `SystemLog`, `UserView`.
- **Key Files**: [`app/core/database.py`](file:///c:/Users/TruProjects/Documents/test/app/core/database.py), [`db.py`](file:///c:/Users/TruProjects/Documents/test/db.py), [`app/models/user.py`](file:///c:/Users/TruProjects/Documents/test/app/models/user.py), [`app/models/subscription.py`](file:///c:/Users/TruProjects/Documents/test/app/models/subscription.py)
- **Connections**: Supplies session dependency `get_db` to all endpoints and services.

### Module 3: Document Parsing & Text Extractor (`utils/extractor.py`)
- **Methodology**: Multi-stage document parser:
  1. `pdfplumber` for structured text extraction.
  2. `pypdf` fallback for unformatted PDFs.
  3. `pytesseract` OCR for scanned images/PDFs.
  4. `python-docx` for `.docx` paragraphs & tables.
- **Key Files**: [`utils/extractor.py`](file:///c:/Users/TruProjects/Documents/test/utils/extractor.py)

### Module 4: Skill Normalizer & AI Match Engine (`utils/analyzer.py`, `utils/skill_normalizer.py`)
- **Methodology**: Maintains canonical skill mappings (`SKILL_ALIASES`) and uses Scikit-Learn TF-IDF vectorization with Cosine Similarity to score resume match against job descriptions.
- **Key Files**: [`utils/skill_normalizer.py`](file:///c:/Users/TruProjects/Documents/test/utils/skill_normalizer.py), [`utils/analyzer.py`](file:///c:/Users/TruProjects/Documents/test/utils/analyzer.py)

### Module 5: Micro-Learning Platform & Interactive Player (`app/api/courses.py`, `templates/learning/player.html`)
- **Methodology**: Renders dynamic 5-slide masterclasses, 1-minute AI video scripts, PDF lecture notes, and a 24/7 AI tutor chatbot interface.
- **Key Files**: [`app/api/courses.py`](file:///c:/Users/TruProjects/Documents/test/app/api/courses.py), [`templates/learning/player.html`](file:///c:/Users/TruProjects/Documents/test/templates/learning/player.html)

### Module 6: Quiz Assessment & Certificate Engine (`app/api/quizzes.py`, `app/services/certificate_service.py`)
- **Methodology**: Generates 5-question skill quizzes. Upon passing (>= 25%), uses **ReportLab** to build printable PDF certificates embedded with unique verification UUIDs.
- **Key Files**: [`app/api/quizzes.py`](file:///c:/Users/TruProjects/Documents/test/app/api/quizzes.py), [`app/services/certificate_service.py`](file:///c:/Users/TruProjects/Documents/test/app/services/certificate_service.py)

### Module 7: Tiered Subscription & Unified Payment Gateway (`app/services/payment_service.py`, `app/api/subscriptions.py`)
- **Methodology**: Supports 3 tier plans (`Basic Pack ₹99`, `Pro Unlimited ₹999`, `VIP Lifetime ₹4,999`) and promo coupons (e.g. `FREE99`, `DISCOUNT1500`). Offers dual checkout: Direct Merchant UPI QR Code with UTR verification + Official Razorpay gateway.
- **Key Files**: [`app/services/payment_service.py`](file:///c:/Users/TruProjects/Documents/test/app/services/payment_service.py), [`app/api/subscriptions.py`](file:///c:/Users/TruProjects/Documents/test/app/api/subscriptions.py)

### Module 8: Unified Cloud Storage Service (`utils/supabase_storage.py`, `app/services/storage_service.py`)
- **Methodology**: Rest API file uploader for Supabase Storage buckets (`images`, `videos`, `files`, `certificates`) with automatic local fallback.
- **Key Files**: [`utils/supabase_storage.py`](file:///c:/Users/TruProjects/Documents/test/utils/supabase_storage.py)

### Module 9: Executive Admin Control Panel (`templates/admin/admin.html`, `main.py`)
- **Methodology**: Admin dashboard for user role management, subscription granting/revocation, exact package details audit, certificate ledger inspection, and audit logs.
- **Key Files**: [`templates/admin/admin.html`](file:///c:/Users/TruProjects/Documents/test/templates/admin/admin.html)

---

## 6. Local Setup & Execution Guide

### 6.1. Environment Initialization
1. Open PowerShell or Terminal in the project directory:
   ```powershell
   cd c:\Users\TruProjects\Documents\test
   ```
2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. Install required packages:
   ```powershell
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### 6.2. Local Development Server Execution
Launch the application using Uvicorn:
```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Once launched, open your web browser to:
- **Application Homepage**: `http://localhost:8000`
- **Interactive Swagger API Docs**: `http://localhost:8000/docs`
- **ReDoc API Documentation**: `http://localhost:8000/redoc`
- **Admin Management Portal**: `http://localhost:8000/learning/admin`

### 6.3. Docker Container Deployment Guide
Build and run using Docker Compose:
```powershell
docker-compose up --build -d
```
The application will run inside an isolated container listening on port `8000`.
