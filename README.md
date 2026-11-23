BrandGuard AI

Intelligent Brand Governance Platform

Team: Bicoders\
Hackathon:CodeZen India -- Inkloom AI Challenge\
Team Leader: Rachel INGABIRE\
Team Member: Issac Shiloah Herbert V

BrandGuard AI helps organizations review content against their brand
guidelines before publication. It combines configurable compliance
rules, AI-assisted analysis, OCR-supported image checks, and a human
review workflow.

 Live links

-   **Application:** https://brand-guard-ai-iota.vercel.app
-   **Backend API:** https://brandguardai-backend.onrender.com
- API documentation:
    https://brandguardai-backend.onrender.com/docs
- Source repository: https://github.com/rachel831/BrandGuardAI

Main capabilities

-   Creator and Manager roles with authenticated access.
-   Organization-specific users, brand guidelines, and review records.
-   Brand guideline configuration, including restricted terms, preferred
    terms, required phrases, approved claims, brand facts, colours, and
    logo information.
-   Text compliance checks for terminology, required phrases, restricted
    terms, tone, claims requiring evidence, and facts requiring
    verification.
-   Image/poster submission with OCR-assisted text extraction and brand
    compliance checks.
-   Logo comparison and brand-colour analysis.
-   Readability and contrast indicators.
-   Suggested corrections and issue explanations.
-   Manager review actions: approve, request changes, or reject, with
    reviewer notes.
-   Review history and analytics.

Analysis is decision support. A human Manager remains responsible for
the final review decision.

Technology

  -----------------------------------------------------------------------
  Layer                               Technology
  ----------------------------------- -----------------------------------
  Frontend                            React.js and Vite

  Backend                             Python and FastAPI

  Database                            PostgreSQL

  AI-assisted analysis                Gemini API

  Image processing                    OpenCV, Pillow, Tesseract OCR /
                                      pytesseract

  Authentication                      PBKDF2-HMAC-SHA256 password hashing
                                      and HMAC-signed tokens

  Frontend hosting                    Vercel

  Backend hosting                     Render

  Source control                      Git and GitHub
  -----------------------------------------------------------------------

## Project structure

``` text
BrandGuardAI/
├── backend/
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   └── src/
├── .gitignore
└── README.md
```

The exact contents may include additional configuration and source
files.

Run locally

 1. Clone the repository

``` bash
git clone https://github.com/rachel831/BrandGuardAI.git
cd BrandGuardAI
```

If you need the Round 3 development branch, switch to it:

``` bash
git checkout round3-development
```

### 2. Set up the backend

Open a terminal in the `backend` folder:

``` bash
cd backend
python -m venv .venv
```

Activate the environment on Windows PowerShell:

``` powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

``` bash
pip install -r requirements.txt
```

Create a local `.env` file in `backend/` and configure the environment
variables required by the backend:

``` env
DATABASE_URL=your_postgresql_connection_string
GEMINI_API_KEY=your_gemini_api_key
BRANDGUARD_SECRET_KEY=replace_with_a_long_random_secret
```

Use your own PostgreSQL database and API credentials. Never commit
`.env` files or publish secrets. Confirm the variable names against the
current backend configuration before running.

Start the API:

``` bash
uvicorn main:app --reload
```

The local API is normally available at `http://127.0.0.1:8000`;
interactive API documentation is at `http://127.0.0.1:8000/docs`.

### 3. Set up the frontend

Open a second terminal:

``` bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite. If the frontend needs a backend base
URL setting, configure it using the variable name already used by the
frontend source; do not expose private credentials in frontend
environment variables.

### 4. Production deployment

The current deployment uses: - Vercel for the React/Vite frontend. -
Render for the FastAPI backend. - PostgreSQL for persistent application
data.

Production environment variables and secrets must be configured in the
hosting providers' environment settings, not committed to Git.

## Organization and access model

Public registration creates a Creator account associated with a new
organization. Application records such as guidelines and review history
are scoped to the authenticated user's organization. Manager access is
intended for review and guideline-management responsibilities. The
Manager account creation interface is not exposed in the current
frontend; use only the supported controlled account-provisioning
process.

## Round 3 improvements

1.  **Persistent data and organization support --- implemented in the
    current backend:** PostgreSQL-backed organization records and
    organization-scoped users, guidelines, and reviews. Database
    backup/restore procedures should be tested operationally before
    describing them as verified.
2.  **Semantic analysis and evidence-grounded suggestions --- partially
    implemented:** Gemini-assisted contextual analysis is used with
    submitted text and OCR-extracted image text. Explicit evidence
    citations and uncertainty explanations are not yet comprehensive;
    outputs should be checked by a human.
3.  **Visual and accessibility governance --- partially implemented:**
    OCR, logo comparison, brand-colour checks, and basic
    readability/contrast indicators are available. Approved logo-variant
    validation and full layout-consistency analysis are not complete.
    Contrast indicators are not a certified WCAG audit.

## Testing checklist

Before a release or evaluation, test: - Creator login and Manager
login. - New organization registration. - Text submission and compliance
results. - Image upload, OCR extraction, and image compliance results. -
Brand guideline creation and update. - Manager approve / request changes
/ reject actions. - Review history after refresh. - Organization
isolation: one organization's users must not see another organization's
guidelines or reviews. - Empty history, invalid input, repeated
submissions, and refresh behavior.

Record the date, test account role, test data, expected result, and
actual result for each test. Do not publish passwords, tokens, or
private database connection strings in the repository or report.

## Known limitations

-   AI suggestions are advisory and may require human verification.
-   Image text is analyzed using OCR; this is not equivalent to complete
    visual understanding of an image.
-   Basic contrast/readability checks do not certify WCAG compliance.
-   Approved logo variants and comprehensive layout consistency checks
    are future work.
-   Automated database backup restoration has not been confirmed as
    tested.

## Roadmap

-   Add explicit evidence references and uncertainty explanations to AI
    findings.
-   Expand logo-variant and layout-consistency validation.
-   Improve accessibility analysis with more complete WCAG-oriented
    checks.
-   Add automated backup scheduling and tested restore procedures.
-   Add automated API and end-to-end tests for organization isolation
    and core workflows.
-   Improve onboarding and controlled Manager account provisioning.
-   Extend supported file formats and integrations.

## Security and contribution notes

-   Keep API keys, database URLs, signing secrets, and user credentials
    private.
-   Do not commit `.env`, database exports, backup JSON files, local
    virtual environments, or temporary backup folders.
-   Use organization-scoped authorization checks for every endpoint that
    reads or modifies customer data.
-   Review changes and run tests before deploying.

------------------------------------------------------------------------

Prepared for CodeZen India Round 3.
