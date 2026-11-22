from PIL import ImageColor
from google import genai
from google.genai import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import base64, hashlib, hmac, io, json, os, re, secrets, sqlite3
import psycopg
from psycopg.rows import dict_row
from difflib import get_close_matches
from dotenv import load_dotenv
from google import genai

import pytesseract
from pytesseract import Output
tesseract_path = os.getenv("TESSERACT_CMD")

if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
elif os.name == "nt":
    windows_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(windows_tesseract):
        pytesseract.pytesseract.tesseract_cmd = windows_tesseract
import numpy as np
try:
    import cv2
except Exception:
    cv2 = None
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Use Render persistent storage when configured; otherwise use local database.
DATA_DIR = Path(os.getenv("BRANDGUARD_DATA_DIR", str(BASE_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_NAME = DATA_DIR / "brandguard.db"
DATABASE_URL = os.getenv("DATABASE_URL")

# Use a secure environment variable in deployment.
TOKEN_SECRET = os.getenv(
    "BRANDGUARD_SECRET_KEY",
    "CHANGE-THIS-DEVELOPMENT-SECRET-BEFORE-DEPLOYMENT"
)

TOKEN_HOURS = 24 * 7


def get_connection():
    if DATABASE_URL:
        return psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row
        )

    con = sqlite3.connect(DB_NAME)
    con.row_factory = sqlite3.Row
    return con

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260000)
    return base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_s, digest_s = stored.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_s.encode())
        expected = base64.urlsafe_b64decode(digest_s.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")

def issue_token(user):
    payload = {"uid": user["id"], "email": user["email"], "role": user["role"],
               "exp": int((datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)).timestamp())}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    body = b64(raw)
    signature = b64(hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return body + "." + signature

def read_token(token):
    try:
        body, signature = token.split(".", 1)
        expected = b64(hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return payload
    except Exception:
        return None

def initialize_database():
    con = get_connection()

    if DATABASE_URL:
        # PostgreSQL tables
        con.execute("""
            CREATE TABLE IF NOT EXISTS brand_guidelines (
                id INTEGER PRIMARY KEY,
                brand_name TEXT NOT NULL,
                tone_of_voice TEXT NOT NULL,
                approved_colors TEXT NOT NULL,
                restricted_terms TEXT NOT NULL,
                approved_claims TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS brand_guideline_versions (
                id BIGSERIAL PRIMARY KEY,
                brand_name TEXT NOT NULL,
                tone_of_voice TEXT NOT NULL DEFAULT '',
                approved_colors TEXT NOT NULL DEFAULT '[]',
                restricted_terms TEXT NOT NULL DEFAULT '[]',
                approved_claims TEXT NOT NULL DEFAULT '[]',
                approved_terms TEXT NOT NULL DEFAULT '[]',
                required_terms TEXT NOT NULL DEFAULT '[]',
                brand_facts TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                logo_data BYTEA,
                logo_filename TEXT DEFAULT '',
                logo_mime_type TEXT DEFAULT ''
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS content_reviews (
                id BIGSERIAL PRIMARY KEY,
                content_type TEXT NOT NULL,
                submitted_content TEXT,
                extracted_text TEXT,
                issues_json TEXT NOT NULL,
                total_issues INTEGER NOT NULL,
                analysis_status TEXT NOT NULL,
                decision TEXT NOT NULL DEFAULT 'Pending Human Review',
                reviewer_note TEXT DEFAULT '',
                image_filename TEXT DEFAULT '',
                image_data BYTEA,
                created_at TEXT NOT NULL,
                user_id INTEGER,
                readability_json TEXT DEFAULT '{}'
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('creator','manager')),
                created_at TEXT NOT NULL
            )
        """)

        # Safely add columns if older PostgreSQL tables exist
        con.execute("""
            ALTER TABLE brand_guideline_versions
            ADD COLUMN IF NOT EXISTS approved_terms TEXT NOT NULL DEFAULT '[]'
        """)
        con.execute("""
            ALTER TABLE brand_guideline_versions
            ADD COLUMN IF NOT EXISTS required_terms TEXT NOT NULL DEFAULT '[]'
        """)
        con.execute("""
            ALTER TABLE brand_guideline_versions
            ADD COLUMN IF NOT EXISTS brand_facts TEXT NOT NULL DEFAULT '[]'
        """)
        con.execute("""
            ALTER TABLE brand_guideline_versions
            ADD COLUMN IF NOT EXISTS logo_data BYTEA
        """)
        con.execute("""
            ALTER TABLE brand_guideline_versions
            ADD COLUMN IF NOT EXISTS logo_filename TEXT DEFAULT ''
        """)
        con.execute("""
            ALTER TABLE brand_guideline_versions
            ADD COLUMN IF NOT EXISTS logo_mime_type TEXT DEFAULT ''
        """)
        con.execute("""
            ALTER TABLE content_reviews
            ADD COLUMN IF NOT EXISTS user_id INTEGER
        """)
        con.execute("""
            ALTER TABLE content_reviews
            ADD COLUMN IF NOT EXISTS readability_json TEXT DEFAULT '{}'
        """)

        first = con.execute("""
            SELECT id FROM brand_guideline_versions
            ORDER BY id LIMIT 1
        """).fetchone()

        if not first:
            old = con.execute("""
                SELECT * FROM brand_guidelines WHERE id=1
            """).fetchone()

            values = (
                old["brand_name"],
                old["tone_of_voice"],
                old["approved_colors"],
                old["restricted_terms"],
                old["approved_claims"]
            ) if old else (
                "My Brand",
                "Professional, friendly and trustworthy",
                json.dumps(["#0F766E", "#172554", "#FFFFFF"]),
                json.dumps(["guaranteed", "100% free", "best in the world"]),
                json.dumps(["Quality products", "Customer satisfaction"])
            )

            cur = con.execute("""
                INSERT INTO brand_guideline_versions
                (brand_name, tone_of_voice, approved_colors,
                 restricted_terms, approved_claims, created_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (*values, datetime.now().astimezone().isoformat(timespec="seconds")))

            guideline_id = cur.fetchone()["id"]

            con.execute("""
                INSERT INTO app_settings(setting_key, setting_value)
                VALUES (%s,%s)
                ON CONFLICT(setting_key)
                DO UPDATE SET setting_value=EXCLUDED.setting_value
            """, ("active_guideline_id", str(guideline_id)))

        elif not con.execute("""
            SELECT 1 FROM app_settings
            WHERE setting_key='active_guideline_id'
        """).fetchone():

            con.execute("""
                INSERT INTO app_settings(setting_key, setting_value)
                VALUES (%s,%s)
                ON CONFLICT(setting_key)
                DO UPDATE SET setting_value=EXCLUDED.setting_value
            """, ("active_guideline_id", str(first["id"])))

        demo_users = [
            ("Judge Creator", "creator@brandguard.demo",
             "CreatorDemo123!", "creator"),
            ("Judge Brand Manager", "manager@brandguard.demo",
             "ManagerDemo123!", "manager")
        ]

        for name, email, password, role in demo_users:
            existing = con.execute(
                "SELECT id FROM users WHERE email=%s", (email,)
            ).fetchone()

            if not existing:
                con.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES (%s,%s,%s,%s,%s)
                """, (
                    name, email, hash_password(password), role,
                    datetime.now().astimezone().isoformat(timespec="seconds")
                ))

    else:
        # SQLite tables
        con.execute("""CREATE TABLE IF NOT EXISTS brand_guidelines (
            id INTEGER PRIMARY KEY, brand_name TEXT NOT NULL,
            tone_of_voice TEXT NOT NULL, approved_colors TEXT NOT NULL,
            restricted_terms TEXT NOT NULL, approved_claims TEXT NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS brand_guideline_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_name TEXT NOT NULL,
            tone_of_voice TEXT NOT NULL DEFAULT '',
            approved_colors TEXT NOT NULL DEFAULT '[]',
            restricted_terms TEXT NOT NULL DEFAULT '[]',
            approved_claims TEXT NOT NULL DEFAULT '[]',
            approved_terms TEXT NOT NULL DEFAULT '[]',
            required_terms TEXT NOT NULL DEFAULT '[]',
            brand_facts TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS content_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL,
            submitted_content TEXT,
            extracted_text TEXT,
            issues_json TEXT NOT NULL,
            total_issues INTEGER NOT NULL,
            analysis_status TEXT NOT NULL,
            decision TEXT NOT NULL DEFAULT 'Pending Human Review',
            reviewer_note TEXT DEFAULT '',
            image_filename TEXT DEFAULT '',
            image_data BLOB,
            created_at TEXT NOT NULL
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('creator','manager')),
            created_at TEXT NOT NULL
        )""")

        guideline_columns = [
            r["name"] for r in
            con.execute("PRAGMA table_info(brand_guideline_versions)").fetchall()
        ]

        for column in ("approved_terms", "required_terms", "brand_facts"):
            if column not in guideline_columns:
                con.execute(
                    f"ALTER TABLE brand_guideline_versions ADD COLUMN "
                    f"{column} TEXT NOT NULL DEFAULT '[]'"
                )

        if "logo_data" not in guideline_columns:
            con.execute(
                "ALTER TABLE brand_guideline_versions ADD COLUMN logo_data BLOB"
            )

        if "logo_filename" not in guideline_columns:
            con.execute(
                "ALTER TABLE brand_guideline_versions ADD COLUMN logo_filename TEXT DEFAULT ''"
            )

        if "logo_mime_type" not in guideline_columns:
            con.execute(
                "ALTER TABLE brand_guideline_versions ADD COLUMN logo_mime_type TEXT DEFAULT ''"
            )

        columns = [
            r["name"] for r in
            con.execute("PRAGMA table_info(content_reviews)").fetchall()
        ]

        if "user_id" not in columns:
            con.execute(
                "ALTER TABLE content_reviews ADD COLUMN user_id INTEGER"
            )

        if "readability_json" not in columns:
            con.execute(
                "ALTER TABLE content_reviews ADD COLUMN readability_json TEXT DEFAULT '{}'"
            )

        first = con.execute("""
            SELECT id FROM brand_guideline_versions
            ORDER BY id LIMIT 1
        """).fetchone()

        if not first:
            old = con.execute(
                "SELECT * FROM brand_guidelines WHERE id=1"
            ).fetchone()

            values = (
                old["brand_name"], old["tone_of_voice"],
                old["approved_colors"], old["restricted_terms"],
                old["approved_claims"]
            ) if old else (
                "My Brand",
                "Professional, friendly and trustworthy",
                json.dumps(["#0F766E", "#172554", "#FFFFFF"]),
                json.dumps(["guaranteed", "100% free", "best in the world"]),
                json.dumps(["Quality products", "Customer satisfaction"])
            )

            cur = con.execute("""
                INSERT INTO brand_guideline_versions
                (brand_name, tone_of_voice, approved_colors,
                 restricted_terms, approved_claims, created_at)
                VALUES (?,?,?,?,?,?)
            """, (*values, datetime.now().astimezone().isoformat(timespec="seconds")))

            guideline_id = cur.lastrowid

            con.execute("""
                INSERT OR REPLACE INTO app_settings
                VALUES ('active_guideline_id',?)
            """, (str(guideline_id),))

        elif not con.execute("""
            SELECT 1 FROM app_settings
            WHERE setting_key='active_guideline_id'
        """).fetchone():

            con.execute("""
                INSERT INTO app_settings VALUES ('active_guideline_id',?)
            """, (str(first["id"]),))

        demo_users = [
            ("Judge Creator", "creator@brandguard.demo",
             "CreatorDemo123!", "creator"),
            ("Judge Brand Manager", "manager@brandguard.demo",
             "ManagerDemo123!", "manager")
        ]

        for name, email, password, role in demo_users:
            if not con.execute(
                "SELECT id FROM users WHERE email=?", (email,)
            ).fetchone():
                con.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES (?,?,?,?,?)
                """, (
                    name, email, hash_password(password), role,
                    datetime.now().astimezone().isoformat(timespec="seconds")
                ))

    con.commit()
    con.close()
def get_table_columns(con, table_name):
    if DATABASE_URL:
        rows = con.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
        """, (table_name,)).fetchall()

        return [row["column_name"] for row in rows]

    rows = con.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return [row["name"] for row in rows]

def execute_query(con, query, params=()):
    if DATABASE_URL:
        query = query.replace("?", "%s")

    return con.execute(query, params)
initialize_database()



app = FastAPI(title="BrandGuard AI")

allowed_origins = os.getenv(
    "FRONTEND_URLS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"]
)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)

class LoginRequest(BaseModel):
    email: str
    password: str

class ContentRequest(BaseModel):
    content: str

class BrandGuidelinesRequest(BaseModel):
    brand_name: str
    tone_of_voice: str = ""
    approved_colors: list[str] = Field(default_factory=list)
    restricted_terms: list[str] = Field(default_factory=list)
    approved_claims: list[str] = Field(default_factory=list)
    approved_terms: list[str] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=list)
    brand_facts: list[str] = Field(default_factory=list)

class ReviewDecisionRequest(BaseModel):
    decision: str
    reviewer_note: str = ""


def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please log in to continue.")

    payload = read_token(authorization.split(" ", 1)[1].strip())

    if not payload:
        raise HTTPException(401, "Your session expired. Please log in again.")

    con = get_connection()

    user = execute_query(
        con,
        "SELECT id,name,email,role FROM users WHERE id=?",
        (payload["uid"],)
    ).fetchone()

    con.close()

    if not user:
        raise HTTPException(401, "Account not found. Please log in again.")

    return dict(user)

def manager_only(user=Depends(current_user)):
    if user["role"] != "manager":
        raise HTTPException(
            403,
            "Only a Brand Manager / Reviewer can perform this action."
        )
    return user


@app.post("/auth/register")

@app.post("/auth/register")
def register_user(request: RegisterRequest):
    email = request.email.strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "Enter a valid email address.")

    con = get_connection()

    try:
        values = (
            request.name.strip(),
            email,
            hash_password(request.password),
            "creator",
            datetime.now().astimezone().isoformat(timespec="seconds")
        )

        if DATABASE_URL:
            cur = con.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES (%s,%s,%s,%s,%s)
                RETURNING id
            """, values)

            user_id = cur.fetchone()["id"]

        else:
            cur = con.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES (?,?,?,?,?)
            """, values)

            user_id = cur.lastrowid

        con.commit()

        user = execute_query(
            con,
            "SELECT id,name,email,role FROM users WHERE id=?",
            (user_id,)
        ).fetchone()

        return {
            "token": issue_token(user),
            "user": dict(user),
            "message": "Creator account created."
        }

    except (sqlite3.IntegrityError, psycopg.IntegrityError):
        raise HTTPException(
            409,
            "An account with this email already exists."
        )

    finally:
        con.close()



@app.post("/auth/login")
def login_user(request: LoginRequest):
    con = get_connection()

    try:
        user = execute_query(
            con,
            "SELECT * FROM users WHERE email=?",
            (request.email.strip().lower(),)
        ).fetchone()
    finally:
        con.close()

    if not user or not verify_password(
        request.password,
        user["password_hash"]
    ):
        raise HTTPException(401, "Email or password is incorrect.")

    safe_user = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"]
    }

    return {
        "token": issue_token(safe_user),
        "user": safe_user
    }


@app.get("/auth/me")
def who_am_i(user=Depends(current_user)):
    return {"user": user}

def active_id(con):
    row = con.execute("SELECT setting_value FROM app_settings WHERE setting_key='active_guideline_id'").fetchone()
    return int(row["setting_value"]) if row else None

def row_to_guideline(row, selected):
    return {"id": row["id"], "brand_name": row["brand_name"], "tone_of_voice": row["tone_of_voice"],
            "approved_colors": json.loads(row["approved_colors"] or "[]"),
            "restricted_terms": json.loads(row["restricted_terms"] or "[]"),
            "approved_claims": json.loads(row["approved_claims"] or "[]"),
            "approved_terms": json.loads(row["approved_terms"] or "[]"),
            "required_terms": json.loads(row["required_terms"] or "[]"),
            "brand_facts": json.loads(row["brand_facts"] or "[]"),
            "logo_url": ("data:" + (row["logo_mime_type"] or "image/png") + ";base64," + base64.b64encode(row["logo_data"]).decode("ascii")) if row["logo_data"] else "",
            "logo_filename": row["logo_filename"] or "",
            "created_at": row["created_at"], "is_active": row["id"] == selected}


def read_brand_guidelines():
    con = get_connection()
    selected = active_id(con)

    row = execute_query(
        con,
        "SELECT * FROM brand_guideline_versions WHERE id=?",
        (selected,)
    ).fetchone() if selected is not None else None

    con.close()

    if not row:
        raise HTTPException(404, "Active brand guidelines not found.")

    return row_to_guideline(row, selected)


@app.get("/brand-guidelines")
def get_brand_guidelines(user=Depends(manager_only)):
    return read_brand_guidelines()

@app.get("/brand-guidelines/history")
def get_brand_guideline_history(user=Depends(manager_only)):
    con = get_connection()
    selected = active_id(con)
    rows = con.execute("SELECT * FROM brand_guideline_versions ORDER BY id DESC").fetchall()
    con.close()
    return {"guidelines": [row_to_guideline(r, selected) for r in rows]}

@app.post("/brand-guidelines")

@app.post("/brand-guidelines")
def create_brand_guidelines(g: BrandGuidelinesRequest, user=Depends(manager_only)):
    if not g.brand_name.strip():
        raise HTTPException(400, "Brand name cannot be empty.")

    con = get_connection()

    values = (
        g.brand_name.strip(),
        g.tone_of_voice.strip(),
        json.dumps(g.approved_colors),
        json.dumps(g.restricted_terms),
        json.dumps(g.approved_claims),
        json.dumps(g.approved_terms),
        json.dumps(g.required_terms),
        json.dumps(g.brand_facts),
        datetime.now().astimezone().isoformat(timespec="seconds")
    )

    if DATABASE_URL:
        cur = con.execute("""
            INSERT INTO brand_guideline_versions
            (brand_name,tone_of_voice,approved_colors,restricted_terms,
             approved_claims,approved_terms,required_terms,brand_facts,created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, values)

        new_id = cur.fetchone()["id"]

        con.execute("""
            INSERT INTO app_settings(setting_key,setting_value)
            VALUES (%s,%s)
            ON CONFLICT(setting_key)
            DO UPDATE SET setting_value=EXCLUDED.setting_value
        """, ("active_guideline_id", str(new_id)))

    else:
        cur = con.execute("""
            INSERT INTO brand_guideline_versions
            (brand_name,tone_of_voice,approved_colors,restricted_terms,
             approved_claims,approved_terms,required_terms,brand_facts,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, values)

        new_id = cur.lastrowid

        con.execute("""
            INSERT OR REPLACE INTO app_settings
            VALUES ('active_guideline_id',?)
        """, (str(new_id),))

    con.commit()
    con.close()

    return {
        "message": "New brand guideline saved and activated.",
        "id": new_id
    }



@app.put("/brand-guidelines")
def update_brand_guidelines(g: BrandGuidelinesRequest, user=Depends(manager_only)):
    if not g.brand_name.strip():
        raise HTTPException(400, "Brand name cannot be empty.")

    con = get_connection()
    selected = active_id(con)

    if selected is None:
        con.close()
        raise HTTPException(404, "No active guideline found.")

    execute_query(
        con,
        """UPDATE brand_guideline_versions
        SET brand_name=?, tone_of_voice=?, approved_colors=?,
        restricted_terms=?, approved_claims=?, approved_terms=?,
        required_terms=?, brand_facts=?
        WHERE id=?""",
        (
            g.brand_name.strip(),
            g.tone_of_voice.strip(),
            json.dumps(g.approved_colors),
            json.dumps(g.restricted_terms),
            json.dumps(g.approved_claims),
            json.dumps(g.approved_terms),
            json.dumps(g.required_terms),
            json.dumps(g.brand_facts),
            selected
        )
    )

    con.commit()
    con.close()

    return {
        "message": "Active brand guidelines updated.",
        "id": selected
    }


@app.post("/brand-guidelines/logo")
async def upload_brand_logo(file: UploadFile = File(...), user=Depends(manager_only)):
    allowed = {"image/png", "image/jpeg", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, "Logo must be PNG, JPG or WebP.")
    data = await file.read()
    if not data or len(data) > 2 * 1024 * 1024:
        raise HTTPException(400, "Logo must be a non-empty image smaller than 2 MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
    except Exception:
        raise HTTPException(400, "The uploaded logo image is invalid.")
    con = get_connection(); selected = active_id(con)
    if selected is None:
        con.close(); raise HTTPException(404, "No active brand profile found. Save a profile first.")
    execute_query(
        con,
        "UPDATE brand_guideline_versions SET logo_data=?,logo_filename=?,logo_mime_type=? WHERE id=?",
        (data, file.filename or "brand-logo", file.content_type, selected)
    )
    con.commit(); con.close()
    return {"message":"Brand logo uploaded successfully.", "filename":file.filename or "brand-logo"}

@app.delete("/brand-guidelines/logo")
def delete_brand_logo(user=Depends(manager_only)):
    con = get_connection()
    selected = active_id(con)

    if selected is None:
        con.close()
        raise HTTPException(404, "No active brand profile found.")

    execute_query(
        con,
        """UPDATE brand_guideline_versions
        SET logo_data=NULL, logo_filename='', logo_mime_type=''
        WHERE id=?""",
        (selected,)
    )

    con.commit()
    con.close()

    return {"message": "Brand logo removed from the active profile."}


@app.post("/brand-guidelines/{guideline_id}/activate")
def activate_guideline(guideline_id: int, user=Depends(manager_only)):
    con = get_connection()

    guideline = execute_query(
        con,
        "SELECT id FROM brand_guideline_versions WHERE id=?",
        (guideline_id,)
    ).fetchone()

    if not guideline:
        con.close()
        raise HTTPException(404, "Guideline version not found.")

    if DATABASE_URL:
        con.execute("""
            INSERT INTO app_settings(setting_key,setting_value)
            VALUES (%s,%s)
            ON CONFLICT(setting_key)
            DO UPDATE SET setting_value=EXCLUDED.setting_value
        """, ("active_guideline_id", str(guideline_id)))
    else:
        con.execute("""
            INSERT OR REPLACE INTO app_settings
            VALUES ('active_guideline_id',?)
        """, (str(guideline_id),))

    con.commit()
    con.close()

    return {
        "message": "Guideline activated.",
        "id": guideline_id
    }


def _normalise_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9% ]", " ", str(value).lower())).strip()

def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None

def check_brand_compliance(text):
    """Rule-based first-pass checker. Findings are suggestions for human review, not verdicts."""
    guidelines = read_brand_guidelines()
    clean = _normalise_phrase(text)
    words = clean.split()
    issues = []
    seen = set()

    def add_issue(detected, rule, message, suggestion, severity="medium"):
        key = (str(detected).lower(), rule)
        if key in seen:
            return
        seen.add(key)
        issues.append({"word": detected, "rule": rule, "message": message,
                       "suggestion": suggestion, "severity": severity})

    # 1) Restricted wording: exact phrase first, then cautious fuzzy matching for single words.
    restricted = ["guaranteed", "100% free", "best in the world"] + guidelines.get("restricted_terms", [])
    for raw in restricted:
        term = str(raw).strip()
        normalized = _normalise_phrase(term)
        if not normalized:
            continue
        matched = _contains_phrase(clean, normalized)
        if not matched and len(normalized.split()) == 1 and len(normalized) >= 5:
            matched = any(get_close_matches(word, [normalized], n=1, cutoff=0.88) for word in words)
        if matched:
            add_issue(term, "Restricted brand wording",
                f"The content uses '{term}', which is listed as restricted in the active brand rules.",
                "Remove this wording or replace it with a phrase approved by the Brand Manager.", "high")

    # 2) Preferred terminology. Add entries as: old term -> preferred term.
    for entry in guidelines.get("approved_terms", []):
        raw = str(entry).strip()
        if "->" not in raw:
            continue
        old, preferred = [part.strip() for part in raw.split("->", 1)]
        old_n, preferred_n = _normalise_phrase(old), _normalise_phrase(preferred)
        if old_n and preferred_n and _contains_phrase(clean, old_n):
            add_issue(old, "Preferred brand terminology",
                f"'{old}' is not the preferred brand term. The guideline specifies '{preferred}'.",
                f"Replace '{old}' with '{preferred}'.")

    # 3) Required phrases/terminology.
    for raw in guidelines.get("required_terms", []):
        term = str(raw).strip()
        normalized = _normalise_phrase(term)
        if normalized and not _contains_phrase(clean, normalized):
            add_issue(term, "Required brand terminology",
                f"The active guideline expects the phrase '{term}', but it was not found.",
                f"Include '{term}' where it fits naturally. Do not force it into content where it is irrelevant.")

    # 4) Claims that need evidence. The checker only flags common high-risk claim patterns;
    # approved claims/facts are treated as supporting context, not as a complete legal verification.
    claim_patterns = [
        (r"\b(?:#\s?1|number one|no\.?\s?1|world'?s best|best in the world)\b", "ranking / superiority claim"),
        (r"\b(?:clinically proven|scientifically proven|proven to)\b", "proof / efficacy claim"),
        (r"\b(?:certified|accredited|officially approved)\b", "certification / approval claim"),
        (r"\b(?:guarantee[sd]?|risk[- ]free|zero risk)\b", "guarantee / risk claim"),
        (r"\b\d+(?:\.\d+)?\s?%\s?(?:off|more|less|increase|improvement|success|satisfaction)?\b", "quantified performance claim"),
    ]
    approved_context = " ".join(_normalise_phrase(x) for x in
        (guidelines.get("approved_claims", []) + guidelines.get("brand_facts", [])))
    for pattern, label in claim_patterns:
        for match in re.finditer(pattern, clean, flags=re.IGNORECASE):
            phrase = match.group(0).strip()
            # A phrase is considered documented only when the exact claim wording is listed.
            already_flagged = any(_normalise_phrase(item.get("word", "")) == _normalise_phrase(phrase) for item in issues)
            if not _contains_phrase(approved_context, _normalise_phrase(phrase)) and not already_flagged:
                add_issue(phrase, "Claim needs verification",
                    f"This may be a {label}. The automated checker cannot confirm that it is supported by approved brand evidence.",
                    "Verify the claim against approved brand facts or evidence. If it cannot be verified, soften or remove it.", "high")

    # 5) Numeric / dated company facts should be supported by the manager's fact list.
    fact_markers = r"\b(?:since|founded|established|serves|trusted by|over|more than|up to|at least|award[- ]winning)\b"
    fact_sentences = [part.strip() for part in re.split(r"[.!?\n]+", text) if part.strip()]
    approved_facts = [_normalise_phrase(x) for x in guidelines.get("brand_facts", []) if _normalise_phrase(x)]
    for sentence in fact_sentences:
        sentence_n = _normalise_phrase(sentence)
        has_numeric = bool(re.search(r"\b\d{2,}(?:[,.]\d+)?\b|\b\d+(?:\.\d+)?\s?%", sentence_n))
        looks_factual = bool(re.search(fact_markers, sentence_n)) or has_numeric
        if not looks_factual:
            continue
        supported = any(fact and (fact in sentence_n or sentence_n in fact) for fact in approved_facts)
        if not supported:
            add_issue(sentence[:90], "Brand fact needs verification",
                "This sentence appears to contain a number, date, achievement or company fact that was not matched to the approved brand facts list.",
                "Verify this statement with an authoritative company source and add the confirmed wording to Brand Guidelines if it is approved.", "medium")

    # 6) Tone indicators are intentionally conservative and only check clear mismatches.
    tone = (guidelines.get("tone_of_voice") or "").lower()
    tone_checks = []
    if any(k in tone for k in ["professional", "formal", "corporate"]):
        tone_checks.append((r"\b(omg|lol|gonna|wanna|bro|yo|ain't|u guys)\b", "Professional tone"))
    if any(k in tone for k in ["friendly", "warm", "approachable", "respectful"]):
        tone_checks.append((r"\b(shut up|stupid|idiot|hate you|you are wrong)\b", "Friendly / respectful tone"))
    if any(k in tone for k in ["trustworthy", "honest", "balanced", "reliable"]):
        tone_checks.append((r"\b(always|never fail|100% guaranteed|zero risk|perfect for everyone)\b", "Trustworthy tone"))
    for pattern, label in tone_checks:
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match:
            phrase = match.group(0)
            add_issue(phrase, "Possible tone mismatch",
                f"'{phrase}' may conflict with the configured {label.lower()}.",
                "Rewrite this sentence to match the brand's stated tone. Review the full sentence in context.")

    return issues


def save_review(kind, submitted, extracted, issues, user_id, filename="", image_data=None, readability=None):
    con = get_connection()

    values = (
        kind,
        submitted,
        extracted,
        json.dumps(issues),
        len(issues),
        "Needs Review" if issues else "Passed Basic Checks",
        filename,
        image_data,
        datetime.now().astimezone().isoformat(timespec="seconds"),
        user_id,
        json.dumps(readability or {})
    )
    if DATABASE_URL:
        cur = con.execute("""
            INSERT INTO content_reviews(content_type,submitted_content,extracted_text,issues_json,total_issues,analysis_status,image_filename,image_data,created_at,user_id,readability_json)VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)RETURNING id""", values)
        rid = cur.fetchone()["id"]
    else:
        cur = con.execute("""
            INSERT INTO content_reviews (content_type,submitted_content,extracted_text,issues_json,total_issues,analysis_status,image_filename,image_data,created_at,user_id,readability_json)VALUES (?,?,?,?,?,?,?,?,?,?,?)""", values)
        rid = cur.lastrowid

    con.commit()
    con.close()

    return rid

@app.get("/reviews")
def get_reviews(user=Depends(current_user)):
    con = get_connection()

    if user["role"] == "manager":
        rows = execute_query(con, """
            SELECT id,content_type,submitted_content,extracted_text,
            issues_json,total_issues,analysis_status,decision,
            reviewer_note,image_filename,created_at,readability_json
            FROM content_reviews
            ORDER BY id DESC
        """).fetchall()
    else:
        rows = execute_query(con, """
            SELECT id,content_type,submitted_content,extracted_text,
            issues_json,total_issues,analysis_status,decision,
            reviewer_note,image_filename,created_at,readability_json
            FROM content_reviews
            WHERE user_id=?
            ORDER BY id DESC
        """, (user["id"],)).fetchall()

    con.close()

    return {
        "reviews": [
            {
                "id": r["id"],
                "type": r["content_type"],
                "submitted_content": r["submitted_content"] or "",
                "extracted_text": r["extracted_text"] or "",
                "issues": json.loads(r["issues_json"] or "[]"),
                "total_issues": r["total_issues"],
                "status": r["analysis_status"],
                "decision": r["decision"] or "Pending Review",
                "reviewer_note": r["reviewer_note"] or "",
                "image_filename": r["image_filename"] or "",
                "date": r["created_at"],
                "readability": json.loads(r["readability_json"] or "{}")
            }
            for r in rows
        ]
    }



@app.delete("/reviews/{review_id}")
def delete_review(review_id: int, user=Depends(current_user)):
    con = get_connection()

    if user["role"] == "manager":
        cur = execute_query(
            con,
            "DELETE FROM content_reviews WHERE id=?",
            (review_id,)
        )
    else:
        cur = execute_query(
            con,
            "DELETE FROM content_reviews WHERE id=? AND user_id=?",
            (review_id, user["id"])
        )

    if cur.rowcount == 0:
        con.close()
        raise HTTPException(
            404,
            "Review not found or you do not have permission to delete it."
        )

    con.commit()
    con.close()

    return {
        "message": "Review deleted successfully.",
        "review_id": review_id
    }



@app.delete("/reviews")
def clear_reviews(user=Depends(manager_only)):
    con = get_connection(); con.execute("DELETE FROM content_reviews"); con.commit(); con.close()
    return {"message": "Review history cleared. Brand guidelines were not changed."}




@app.patch("/reviews/{review_id}/decision")
def update_review_decision(
    review_id: int,
    request: ReviewDecisionRequest,
    user=Depends(manager_only)
):
    if request.decision not in ["Approved", "Revision Requested", "Rejected"]:
        raise HTTPException(400, "Invalid review decision.")

    con = get_connection()

    cur = execute_query(
        con,
        "UPDATE content_reviews SET decision=?, reviewer_note=? WHERE id=?",
        (request.decision, request.reviewer_note, review_id)
    )

    if cur.rowcount == 0:
        con.close()
        raise HTTPException(404, "Review not found.")

    con.commit()
    con.close()

    return {
        "message": "Review decision saved.",
        "review_id": review_id,
        "decision": request.decision
    }


@app.get("/analytics")
def get_analytics(user=Depends(current_user)):
    con = get_connection()

    if user["role"] == "manager":
        rows = execute_query(
            con,
            "SELECT decision, content_type, total_issues, issues_json, created_at FROM content_reviews"
        ).fetchall()
    else:
        rows = execute_query(
            con,
            "SELECT decision, content_type, total_issues, issues_json, created_at FROM content_reviews WHERE user_id=?",
            (user["id"],)
        ).fetchall()

    con.close()

    decisions = {"Pending": 0, "Approved": 0, "Revision Requested": 0, "Rejected": 0}
    types = {"Text": 0, "Image": 0}
    severity = {"high": 0, "medium": 0, "low": 0}
    daily = {}

    for row in rows:
        decision = row["decision"] or "Pending Human Review"

        if decision in ("Pending", "Pending Review", "Pending Human Review"):
            decisions["Pending"] += 1
        elif decision in decisions:
            decisions[decision] += 1

        kind = row["content_type"] or "Other"
        types[kind] = types.get(kind, 0) + 1

        try:
            issues = json.loads(row["issues_json"] or "[]")
        except Exception:
            issues = []

        for issue in issues:
            level = str(issue.get("severity", "medium")).lower()
            severity[level] = severity.get(level, 0) + 1

        day = (row["created_at"] or "")[:10]
        if day:
            daily[day] = daily.get(day, 0) + 1

    return {
        "total_reviews": len(rows),
        "decisions": decisions,
        "content_types": types,
        "severity": severity,
        "total_issues": sum(severity.values()),
        "daily_reviews": [
            {"date": k, "count": v}
            for k, v in sorted(daily.items())[-7:]
        ]
    }


@app.get("/")
def home():
    return {"message":"Welcome to BrandGuard AI!","status":"Running"}

@app.get("/health")
def health():
    return {"status":"Backend is running"}




def analyze_brand_colors(image, approved_colors):

    # Convert user-entered colour formats into HEX
    def normalize_color(value):
        if not isinstance(value, str):
            return None

        color = value.strip().lower()

        if not color:
            return None

        # Support common colour names
        aliases = {
            "navy blue": "navy",
            "off white": "#FAF9F6",
            "off-white": "#FAF9F6",
            "grey": "gray"
        }

        color = aliases.get(color, color)

        try:
            # Support HEX, CSS colour names and RGB formats
            if re.fullmatch(r"[0-9a-f]{6}", color):
                color = "#" + color

            rgb = ImageColor.getrgb(color)

            return "#{:02X}{:02X}{:02X}".format(
                rgb[0], rgb[1], rgb[2]
            )

        except (ValueError, TypeError):
            return None

    # Accept a list or a single colour string
    if isinstance(approved_colors, str):
        if not approved_colors.strip().lower().startswith("rgb"):
            approved_colors = re.split(r"[,;]", approved_colors)
        else:
            approved_colors = [approved_colors]

    approved = []
    invalid_colors = []

    for color in approved_colors or []:
        normalized = normalize_color(color)

        if normalized:
            if normalized not in approved:
                approved.append(normalized)
        else:
            invalid_colors.append(color)

    # Stop safely if no valid colours are available
    if not approved:
        return {
            "status": "No valid brand colours configured",
            "approved_colors": [],
            "detected_colors": [],
            "matches": [],
            "matched_count": 0,
            "total_detected": 0,
            "invalid_colors": invalid_colors,
            "message": "Please enter valid colour names or HEX values."
        }

    # Resize image for faster processing
    resized = cv2.resize(image, (150, 150))

    pixels = resized.reshape((-1, 3)).astype(np.float32)

    # Detect dominant colours using K-means
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        20,
        1.0
    )

    _, labels, centers = cv2.kmeans(
        pixels,
        5,
        None,
        criteria,
        3,
        cv2.KMEANS_PP_CENTERS
    )

    detected_colors = []

    for center in centers:
        rgb = [int(value) for value in center]

        hex_color = "#{:02X}{:02X}{:02X}".format(*rgb)

        detected_colors.append(hex_color)

    # Compare detected and approved colours
    def color_distance(color1, color2):
        rgb1 = np.array([
            int(color1[i:i+2], 16)
            for i in (1, 3, 5)
        ])

        rgb2 = np.array([
            int(color2[i:i+2], 16)
            for i in (1, 3, 5)
        ])

        return float(np.linalg.norm(rgb1 - rgb2))

    matches = []

    for detected in detected_colors:
        closest = min(
            approved,
            key=lambda color: color_distance(detected, color)
        )

        distance = color_distance(detected, closest)

        matches.append({
            "detected": detected,
            "closest_approved": closest,
            "distance": round(distance, 2),
            "match": distance <= 60
        })

    matched_count = sum(item["match"] for item in matches)

    status = (
        "Good match"
        if matched_count == len(matches)
        else "Possible colour mismatch"
    )

    return {
        "status": status,
        "approved_colors": approved,
        "detected_colors": detected_colors,
        "matches": matches,
        "matched_count": matched_count,
        "total_detected": len(matches),
        "invalid_colors": invalid_colors
    }
    # Compare detected and approved colours
    def color_distance(color1, color2):
        rgb1 = np.array([
            int(color1[i:i+2], 16)
            for i in (1, 3, 5)
        ])

        rgb2 = np.array([
            int(color2[i:i+2], 16)
            for i in (1, 3, 5)
        ])

        return float(np.linalg.norm(rgb1 - rgb2))

    matches = []

    for detected in detected_colors:
        closest = min(
            approved,
            key=lambda color: color_distance(detected, color)
        )

        distance = color_distance(detected, closest)

        matches.append({
            "detected": detected,
            "closest_approved": closest,
            "distance": round(distance, 2),
            "match": distance <= 60
        })

    matched_count = sum(item["match"] for item in matches)

    status = (
        "Good match"
        if matched_count == len(matches)
        else "Possible colour mismatch"
    )

    return {
        "status": status,
        "approved_colors": approved,
        "detected_colors": detected_colors,
        "matches": matches,
        "matched_count": matched_count,
        "total_detected": len(matches)
    }


@app.post("/analyze")
def analyze_content(request: ContentRequest, user=Depends(current_user)):
    content = request.content.strip()

    if not content:
        raise HTTPException(400, "Please enter content to analyze.")

    # Existing rule-based analysis
    issues = check_brand_compliance(content)

    for issue in issues:
        issue["source"] = "Rule-based"

    # Gemini AI analysis
    ai_issues = analyze_with_gemini(content)

    existing_messages = {
        issue.get("message", "").strip().lower()
        for issue in issues
    }

    for issue in ai_issues:
        message = issue["message"].strip().lower()

        if message not in existing_messages:
            issue["source"] = "Gemini AI"
            issues.append(issue)
            existing_messages.add(message)
    if len(content) < 10:
        issues.append({
            "word": "Short content",
            "rule": "Minimum content length",
            "message": "Your content is too short to review properly.",
            "suggestion": "Provide more information."
        })

    rid = save_review("Text", content, "", issues, user["id"])

    return {
        "review_id": rid,
        "status": "Needs Review" if issues else "Passed Basic Checks",
        "total_issues": len(issues),
        "issues": issues
    }
def analyze_text_contrast(image_array, ocr_results):
    height, width = image_array.shape[:2]
    results = []

    def luminance(rgb):
        rgb = np.array(rgb, dtype=np.float64) / 255.0
        linear = np.where(
            rgb <= 0.04045,
            rgb / 12.92,
            ((rgb + 0.055) / 1.055) ** 2.4
        )
        return float(
            0.2126 * linear[0] +
            0.7152 * linear[1] +
            0.0722 * linear[2]
        )

    for item in ocr_results:
        try:
            points = item[0]

            xs = [int(point[0]) for point in points]
            ys = [int(point[1]) for point in points]

            x1 = max(0, min(xs))
            y1 = max(0, min(ys))
            x2 = min(width, max(xs))
            y2 = min(height, max(ys))

            if x2 - x1 < 5 or y2 - y1 < 5:
                continue

            # Text region
            crop = image_array[y1:y2, x1:x2]

            # Surrounding area used to estimate background
            pad = max(3, int(min(x2 - x1, y2 - y1) * 0.15))

            outer = image_array[
                max(0, y1 - pad):min(height, y2 + pad),
                max(0, x1 - pad):min(width, x2 + pad)
            ]

            if crop.size == 0 or outer.size == 0:
                continue

            # Estimate background from the outer region
            background_rgb = np.median(
                outer.reshape(-1, 3), axis=0
            )

            background_lum = luminance(background_rgb)

            # Estimate text from pixels most different from background
            pixels = crop.reshape(-1, 3).astype(np.float64)

            pixel_luminance = (
                0.2126 * pixels[:, 0] +
                0.7152 * pixels[:, 1] +
                0.0722 * pixels[:, 2]
            )

            pixel_luminance = pixel_luminance / 255.0

            difference = np.abs(pixel_luminance - background_lum)

            selected_count = max(1, int(len(pixels) * 0.20))
            selected_indices = np.argsort(difference)[-selected_count:]

            foreground_rgb = np.median(
                pixels[selected_indices], axis=0
            )

            foreground_lum = luminance(foreground_rgb)

            lighter = max(background_lum, foreground_lum)
            darker = min(background_lum, foreground_lum)

            ratio = (lighter + 0.05) / (darker + 0.05)

            results.append({
                "text": str(item[1]),
                "contrast_ratio": round(ratio, 2),
                "wcag_aa_normal": ratio >= 4.5,
                "wcag_aa_large": ratio >= 3.0,
                "estimated": True
            })

        except Exception:
            continue

    low_contrast = [
        result for result in results
        if not result["wcag_aa_large"]
    ]

    normal_text_pass = sum(
        result["wcag_aa_normal"] for result in results
    )

    large_text_pass = sum(
        result["wcag_aa_large"] for result in results
    )

    return {
        "status": (
            "No text regions available"
            if not results
            else "Review recommended"
            if low_contrast
            else "No low-contrast regions detected"
        ),
        "regions_checked": len(results),
        "normal_text_pass": normal_text_pass,
        "large_text_pass": large_text_pass,
        "low_contrast_count": len(low_contrast),
        "results": results,
        "note": (
            "Contrast values are approximate estimates from OCR regions. "
            "They are not certified WCAG measurements."
        )
    }
def assess_poster_readability(image_array, ocr_results):
    """Automated poster readability and accessibility estimates."""

    height, width = image_array.shape[:2]

    confidences = [
        max(0.0, min(1.0, float(item[2])))
        for item in ocr_results
        if len(item) > 2
    ]

    box_heights = []

    for item in ocr_results:
        try:
            ys = [float(point[1]) for point in item[0]]
            box_heights.append(max(ys) - min(ys))
        except Exception:
            pass

    avg_conf = (
        round((sum(confidences) / len(confidences)) * 100, 1)
        if confidences else 0.0
    )

    smallest_pct = (
        round((min(box_heights) / max(height, 1)) * 100, 2)
        if box_heights else None
    )

    text = " ".join(item[1] for item in ocr_results)
    char_count = len(text.strip())
    block_count = len(ocr_results)

    gray = np.mean(image_array, axis=2)
    contrast_spread = float(np.std(gray))

    findings = []
    suggestions = []

    if not block_count:
        findings.append("No readable text was detected by OCR.")
        suggestions.append(
            "Use a sharper, higher-resolution image and ensure text is visible."
        )

    elif avg_conf < 65:
        findings.append(
            "OCR confidence is low, so some poster wording may be difficult to read."
        )
        suggestions.append(
            "Use clearer typography, sharper text edges and less decorative lettering."
        )

    if smallest_pct is not None and smallest_pct < 1.2:
        findings.append(
            "Some detected text appears small relative to the poster height."
        )
        suggestions.append(
            "Increase the size of small captions, dates and contact details."
        )

    if char_count > 650 or block_count > 28:
        findings.append(
            "The poster may contain too much text or too many separate text blocks."
        )
        suggestions.append(
            "Shorten supporting copy and keep one clear main message."
        )

    if contrast_spread < 35:
        findings.append(
            "The image has low overall brightness variation; check text contrast manually."
        )
        suggestions.append(
            "Use stronger foreground and background contrast."
        )

    contrast_analysis = analyze_text_contrast(
        image_array,
        ocr_results
    )

    if contrast_analysis["low_contrast_count"] > 0:
        findings.append(
            "Some detected text regions may have insufficient foreground/background contrast."
        )
        suggestions.append(
            "Increase contrast between text and background."
        )

    if not findings:
        findings.append(
            "No major readability warning was detected by these automated estimates."
        )
        suggestions.append(
            "Inspect the poster at phone-screen size and verify every word manually."
        )

    return {
        "ocr_confidence": avg_conf,
        "text_blocks": block_count,
        "character_count": char_count,
        "smallest_text_height_percent": smallest_pct,
        "contrast_spread_estimate": round(contrast_spread, 1),
        "contrast_analysis": contrast_analysis,
        "findings": findings,
        "suggestions": suggestions,
        "note": (
            "These are automated estimates, not a guarantee of accessibility "
            "or exact font-size measurement."
        )
    }

def analyze_with_gemini(content):
    """Use Gemini to provide additional brand-content analysis."""

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    if not api_key:
        return []

    try:
        guidelines = read_brand_guidelines()

        if not guidelines:
            return []

        brand_context = {
            "brand_name": guidelines.get("brand_name"),
            "tone_of_voice": guidelines.get("tone_of_voice"),
            "restricted_terms": guidelines.get("restricted_terms", []),
            "approved_terms": guidelines.get("approved_terms", []),
            "required_terms": guidelines.get("required_terms", []),
            "approved_claims": guidelines.get("approved_claims", []),
            "brand_facts": guidelines.get("brand_facts", [])
        }

        client = genai.Client(api_key=api_key)

        prompt = f"""
You are a professional brand governance assistant.

Analyze the following marketing content using ONLY the supplied
brand guidelines.

Brand guidelines:
{json.dumps(brand_context)}

Content:
{content}

Identify additional issues such as:
- Brand tone inconsistencies
- Misleading or unsupported claims
- Inappropriate marketing language
- Brand messaging inconsistencies

Do not invent brand rules or claim that facts have been externally verified.
Do not repeat obvious issues already covered by the supplied rules.

Return valid JSON in this exact format:
{{
  "issues": [
    {{
      "word": "Relevant word or phrase",
      "rule": "Issue category",
      "message": "Explain the problem",
      "suggestion": "Give a practical improvement",
      "severity": "High"
    }}
  ]
}}

Use only High, Medium, or Low for severity.
Return an empty issues array if no additional problems are found.
Return no more than 8 issues.
"""

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )

        result = json.loads(response.text)
        ai_issues = result.get("issues", [])

        if not isinstance(ai_issues, list):
            return []

        valid_issues = []

        for issue in ai_issues[:8]:
            if not isinstance(issue, dict):
                continue

            required_fields = ["word", "rule", "message", "suggestion"]

            if not all(
                isinstance(issue.get(field), str) and issue[field].strip()
                for field in required_fields
            ):
                continue

            severity = issue.get("severity", "Medium")
            if severity not in ["High", "Medium", "Low"]:
                severity = "Medium"

            valid_issues.append({
                "word": issue["word"].strip(),
                "rule": issue["rule"].strip(),
                "message": issue["message"].strip(),
                "suggestion": issue["suggestion"].strip(),
                "severity": severity
            })

        return valid_issues
    except Exception as error:
        print("Gemini analysis unavailable:", error)
        return []
def extract_text_with_gemini(image_bytes, mime_type):
    """Extract visible poster text using Gemini image understanding."""

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    if not api_key:
        print("Gemini OCR unavailable: API key missing.")
        return ""

    try:
        client = genai.Client(api_key=api_key)

        prompt = """
        Read all visible text in this poster or image.

        Instructions:
        - Extract the actual visible words.
        - Preserve the original spelling.
        - Include headings, small text and contact details.
        - Keep the reading order as naturally as possible.
        - Do not summarize or analyze the image.
        - Return only the extracted text.
        - If no text is visible, return an empty response.
        """

        response = client.models.generate_content(
            model=model,
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type
                )
            ]
        )

        return (response.text or "").strip()

    except Exception as error:
        print("Gemini OCR error:", error)
        return ""


    except Exception as error:
        print("Gemini analysis unavailable:", error)
        return []

def compare_poster_logo(poster_image, logo_bytes):
    """Conservative logo comparison using ORB and geometric verification."""

    if not logo_bytes:
        return {
            "status": "Not configured",
            "score": 0,
            "matched_features": 0,
            "note": "No official logo is saved."
        }

    if cv2 is None:
        return {
            "status": "Unavailable",
            "score": 0,
            "matched_features": 0,
            "note": "OpenCV is not installed."
        }

    try:
        # Prepare poster
        poster = np.array(poster_image.convert("RGB"))
        poster_gray = cv2.cvtColor(poster, cv2.COLOR_RGB2GRAY)

        # Prepare official logo
        logo_pil = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
        bbox = logo_pil.getchannel("A").getbbox()

        if bbox:
            logo_pil = logo_pil.crop(bbox)

        white = Image.new("RGBA", logo_pil.size, (255, 255, 255, 255))
        white.alpha_composite(logo_pil)

        logo_rgb = np.array(white.convert("RGB"))
        logo_gray = cv2.cvtColor(logo_rgb, cv2.COLOR_RGB2GRAY)

        # Detect distinctive features
        orb = cv2.ORB_create(
            nfeatures=2500,
            scaleFactor=1.2,
            nlevels=8
        )

        kp_logo, des_logo = orb.detectAndCompute(logo_gray, None)
        kp_poster, des_poster = orb.detectAndCompute(poster_gray, None)

        if des_logo is None or des_poster is None:
            return {
                "status": "Not detected",
                "score": 0,
                "matched_features": 0,
                "note": "Not enough distinctive logo features were detected."
            }

        if len(kp_logo) < 6 or len(kp_poster) < 6:
            return {
                "status": "Not detected",
                "score": 0,
                "matched_features": 0,
                "note": "Insufficient visual features for reliable logo comparison."
            }

        # Match distinctive features
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

        pairs = matcher.knnMatch(des_logo, des_poster, k=2)

        good = [
            m for pair in pairs
            if len(pair) == 2
            for m, n in [pair]
            if m.distance < 0.70 * n.distance
        ]

        if len(good) < 6:
            return {
                "status": "Not detected",
                "score": 0,
                "matched_features": len(good),
                "note": "The official logo was not confidently detected."
            }

        # Verify that matched features form the same geometric shape
        src = np.float32([
            kp_logo[m.queryIdx].pt for m in good
        ]).reshape(-1, 1, 2)

        dst = np.float32([
            kp_poster[m.trainIdx].pt for m in good
        ]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(
            src, dst, cv2.RANSAC, 4.0
        )

        if H is None or mask is None:
            return {
                "status": "Not detected",
                "score": 0,
                "matched_features": 0,
                "note": "No reliable geometric logo match was found."
            }

        inlier_mask = mask.ravel().astype(bool)
        inliers = int(np.sum(inlier_mask))
        inlier_ratio = inliers / len(good)

        # Check how much of the official logo is represented
        logo_points = src[inlier_mask].reshape(-1, 2)

        if len(logo_points) < 6:
            return {
                "status": "Not detected",
                "score": 0,
                "matched_features": inliers,
                "note": "Too few reliable logo features were found."
            }

        hull = cv2.convexHull(
            logo_points.astype(np.float32)
        )

        logo_area = max(
            1, logo_gray.shape[0] * logo_gray.shape[1]
        )

        coverage = cv2.contourArea(hull) / logo_area

        # Validate projected logo position and shape
        lh, lw = logo_gray.shape[:2]
        ph, pw = poster_gray.shape[:2]

        corners = np.float32([
            [0, 0],
            [lw - 1, 0],
            [lw - 1, lh - 1],
            [0, lh - 1]
        ]).reshape(-1, 1, 2)

        projected = cv2.perspectiveTransform(corners, H)

        center = np.mean(projected.reshape(-1, 2), axis=0)

        center_valid = (
            0 <= center[0] < pw and
            0 <= center[1] < ph
        )

        polygon_area = abs(
            cv2.contourArea(projected.astype(np.float32))
        )

        area_ratio = polygon_area / max(1, pw * ph)

        geometry_valid = (
            center_valid and
            0.0001 < area_ratio < 0.60
        )

        # Conservative score: this is not a probability
        score = round(
            100 *
            min(1, inliers / 20) *
            min(1, inlier_ratio / 0.70) *
            min(1, coverage / 0.15)
        )

        # Never present an uncertain match as 100%
        score = min(95, score)

        if (
            inliers >= 12 and
            inlier_ratio >= 0.50 and
            coverage >= 0.08 and
            geometry_valid
        ):
            status = "Likely match"
            note = "Strong visual feature and geometric agreement found. Human verification is still required."

        elif (
            inliers >= 7 and
            inlier_ratio >= 0.35 and
            coverage >= 0.03 and
            geometry_valid
        ):
            status = "Possible match"
            note = "Some logo similarities were found, but the match is uncertain. Manager review is required."

        else:
            status = "Not detected"
            note = "The official logo could not be reliably matched. Check whether the correct logo is present."

        return {
            "status": status,
            "score": score,
            "matched_features": inliers,
            "note": note,
            "method": "ORB with RANSAC geometric verification"
        }

    except Exception as exc:
        return {
            "status": "Unable to compare",
            "score": 0,
            "matched_features": 0,
            "note": f"Logo comparison failed: {str(exc)[:180]}"
        }


def _brand_ocr_normalise(value: str) -> str:
    """Normalise OCR text without losing the order of meaningful characters."""
    value = str(value or "").casefold()
    # Common OCR substitutions relevant to the supplied GreenBite example.
    value = value.translate(str.maketrans({"0": "o"}))
    return re.sub(r"[^a-z0-9]+", "", value)


def check_poster_brand_name(expected_brand_name, ocr_results, image_size=None):
    """Verify a brand name from local OCR evidence, conservatively.

    It checks individual detections and nearby pairs (including stacked logo
    lines), uses OCR confidence and box prominence, and never treats a low-
    confidence/unclear result as proof of a different brand.
    """
    expected_display = str(expected_brand_name or "").strip()
    expected = _brand_ocr_normalise(expected_display)
    if not expected:
        return {"status": "Not configured", "expected_brand": "", "detected_text": "",
                "note": "Add the official brand name in Brand Guidelines to verify poster identity."}

    detections = []
    for item in (ocr_results or []):
        try:
            box, raw_text, confidence = item
            raw_text = str(raw_text).strip()
            normalised = _brand_ocr_normalise(raw_text)
            if not raw_text or not normalised:
                continue
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            left, right = min(xs), max(xs)
            top, bottom = min(ys), max(ys)
            detections.append({
                "text": raw_text, "normalised": normalised,
                "confidence": max(0.0, min(1.0, float(confidence))),
                "left": left, "right": right, "top": top, "bottom": bottom,
                "width": max(1.0, right-left), "height": max(1.0, bottom-top),
                "area": max(1.0, (right-left)*(bottom-top)),
                "cy": (top+bottom)/2.0,
            })
        except Exception:
            continue

    # Build candidates from one OCR box and from spatially adjacent boxes.
    # Pair candidates cover logos where the brand name is split over two lines
    # (for example, "GreenBite" above "FOODS").
    candidates = []
    for d in detections:
        candidates.append((d["normalised"], d["text"], d["confidence"], d["area"], d["height"], d["cy"]))
    for i, first in enumerate(detections):
        for second in detections[i+1:]:
            horizontal_gap = max(0.0, max(first["left"], second["left"]) - min(first["right"], second["right"]))
            vertical_gap = max(0.0, max(first["top"], second["top"]) - min(first["bottom"], second["bottom"]))
            scale = max(first["height"], second["height"], 1.0)
            # Adjacent on the same row or close stacked lines only.
            if horizontal_gap > 3.0*scale or vertical_gap > 2.5*scale:
                continue
            pair = sorted((first, second), key=lambda d: (round(d["cy"] / max(scale, 1)), d["left"]))
            joined = "".join(d["normalised"] for d in pair)
            display = " / ".join(d["text"] for d in pair)
            candidates.append((joined, display, min(d["confidence"] for d in pair),
                               sum(d["area"] for d in pair), max(d["height"] for d in pair),
                               min(d["cy"] for d in pair)))

    # Exact OCR match after O/0 correction. Require a minimally credible OCR
    # confidence; low-confidence text is not enough to assert a match.
    matches = [c for c in candidates if expected in c[0] and c[2] >= 0.30]
    if matches:
        best = max(matches, key=lambda c: (c[2], c[3], len(c[0])))
        return {"status": "Match", "expected_brand": expected_display,
                "detected_text": best[1],
                "note": "The official brand name was found in OCR after accounting for spacing and common O/0 confusion. Confirm its appearance on the original poster."}

    # A mismatch requires a clear, sufficiently confident, prominent alternative.
    # Generic slogans and descriptive food/marketing words are not brand names.
    generic_terms = {
        "eat", "fresh", "live", "better", "choose", "healthy", "today",
        "delicious", "nutritious", "natural", "nutrition", "quality",
        "products", "tomorrow", "free", "sale", "offer", "new", "best",
        "taste", "good", "food", "foods", "organic", "premium"
    }
    heights = sorted(d["height"] for d in detections)
    median_height = heights[len(heights)//2] if heights else 0
    image_height = float(image_size[1]) if image_size and len(image_size) > 1 else 0.0
    alternatives = []
    for d in detections:
        words = re.findall(r"[A-Za-z][A-Za-z0-9&'-]*", d["text"])
        compact = d["normalised"]
        if len(compact) < 5 or len(words) > 3 or d["confidence"] < 0.55:
            continue
        if expected in compact or compact in expected:
            continue
        meaningful = [w.casefold() for w in words if len(w) >= 3]
        if not meaningful or all(w in generic_terms for w in meaningful):
            continue
        prominent = (d["height"] >= max(1.0, median_height*1.35) or
                     (image_height and d["cy"] <= image_height*0.38))
        if not prominent:
            continue
        alternatives.append(d)

    if alternatives:
        best = max(alternatives, key=lambda d: (d["confidence"], d["height"], d["area"]))
        return {"status": "Possible mismatch", "expected_brand": expected_display,
                "detected_text": best["text"],
                "note": f'The official name "{expected_display}" was not found. Prominent text "{best["text"]}" may identify a different brand; this is a warning for human review, not a definitive identity decision.'}

    return {"status": "Unable to verify", "expected_brand": expected_display, "detected_text": "",
            "note": f'The official name "{expected_display}" was not found clearly enough in OCR. This is not proof of a mismatch; verify the poster manually.'}


def run_improved_ocr(image):
    """Run lightweight Tesseract OCR on original and enhanced images."""
    original = image.convert("RGB")
    w, h = original.size

    enhanced = ImageOps.autocontrast(original.convert("L")).convert("RGB")
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.6)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.25)

    scale = min(1.8, 2400 / max(w, h, 1))

    if scale > 1.02:
        enhanced = enhanced.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            getattr(Image, "Resampling", Image).LANCZOS
        )

    candidates = [
        (np.array(original), 1.0),
        (np.array(enhanced), scale if scale > 1.02 else 1.0)
    ]

    merged = {}

    for arr_img, factor in candidates:
        try:
            data = pytesseract.image_to_data(
                arr_img,
                output_type=Output.DICT,
                config="--psm 11"
            )
        except Exception as e:
            print("OCR error:", e)
            continue

        for i, txt in enumerate(data["text"]):
            text_value = str(txt).strip()

            if not text_value:
                continue

            try:
                confidence = float(data["conf"][i]) / 100
            except (ValueError, TypeError):
                continue

            if confidence < 0:
                continue

            x = float(data["left"][i]) / factor
            y = float(data["top"][i]) / factor
            width = float(data["width"][i]) / factor
            height = float(data["height"][i]) / factor

            box = [
                [x, y],
                [x + width, y],
                [x + width, y + height],
                [x, y + height]
            ]

            key = re.sub(r"\W+", "", text_value.casefold())

            if not key:
                continue

            candidate = (box, text_value, confidence)

            if key not in merged or confidence > merged[key][2]:
                merged[key] = candidate

    results = list(merged.values())

    results.sort(
        key=lambda item: (
            min(p[1] for p in item[0]),
            min(p[0] for p in item[0])
        )
    )

    return results

@app.post("/analyze-image")
async def analyze_image(file: UploadFile = File(...), user=Depends(current_user)):
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(400, "Only JPG, PNG and WebP images are allowed.")

    data = await file.read()

    if not data:
        raise HTTPException(400, "The uploaded image is empty.")

    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image must be smaller than 5 MB.")

    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        image_array = np.array(image)

        # Step 1: Extract text using Tesseract OCR
        results = run_improved_ocr(image)
        extracted = " ".join(item[1] for item in results)

        # Step 1B: Use Gemini if Tesseract cannot extract text
        if not extracted.strip():
            print("Tesseract found no text. Trying Gemini image OCR...")
            extracted = extract_text_with_gemini(data, file.content_type)

            if extracted:
                print("Gemini successfully extracted poster text.")
            else:
                print("Gemini could not extract poster text.")

        # Identify the OCR method
        if extracted and not results:
            ocr_method = "Gemini image OCR fallback"
        elif results:
            ocr_method = "Original + enhanced Tesseract OCR with duplicate merging"
        else:
            ocr_method = "No text detected"

        # Step 2: Existing rule-based analysis
        issues = check_brand_compliance(extracted)

        for issue in issues:
            issue["source"] = "Rule-based"

        # Step 3: Gemini AI analysis
        if extracted.strip():
            ai_issues = analyze_with_gemini(extracted)

            existing_messages = {
                issue.get("message", "").strip().lower()
                for issue in issues
            }

            for issue in ai_issues:
                message = issue.get("message", "").strip().lower()

                if message and message not in existing_messages:
                    issue["source"] = "Gemini AI"
                    issues.append(issue)
                    existing_messages.add(message)

        # Step 4: Check poster readability and brand colours
        readability = assess_poster_readability(image_array, results)
        guidelines = read_brand_guidelines()

        color_analysis = analyze_brand_colors(
            image_array,
            guidelines["approved_colors"]
        )

        readability["color_analysis"] = color_analysis

        # Add warning when brand colours do not match
        if color_analysis["status"] == "Possible colour mismatch":
            issues.append({
                "word": "Brand colours",
                "rule": "Visual identity / brand colour consistency",
                "severity": "medium",
                "source": "Brand colour analysis",
                "message": "Some dominant poster colours differ from the approved brand palette.",
                "suggestion": "Review the poster colours and use the approved brand colours where appropriate."
            })

        # Step 5: Load active brand logo and guidelines
        con = get_connection()
        try:
            selected = active_id(con)

            logo_row = execute_query(
                con,
                "SELECT brand_name, logo_data, logo_filename "
                "FROM brand_guideline_versions WHERE id=?",
                (selected,)
            ).fetchone() if selected is not None else None

        finally:
            con.close()

        # Step 6: Compare official logo
        logo_match = compare_poster_logo(
            image,
            logo_row["logo_data"] if logo_row else None
        )

        logo_match["official_logo_filename"] = (
            logo_row["logo_filename"] or ""
        ) if logo_row else ""

        brand_name_match = check_poster_brand_name(
            logo_row["brand_name"] if logo_row else "",
            results,
            image.size
        )

        logo_match["brand_name_check"] = brand_name_match
        readability["logo_match"] = logo_match

        # Step 7: Check brand name mismatch
        if brand_name_match["status"] == "Possible mismatch":
            issues.append({
                "word": brand_name_match["detected_text"],
                "rule": "Brand identity / brand-name consistency",
                "severity": "high",
                "source": "Logo and brand identity check",
                "message": brand_name_match["note"],
                "suggestion": (
                    "Confirm that the poster belongs to the active brand. "
                    "Replace the other brand name with the approved brand name "
                    "if this is an accidental mix-up."
                )
            })

        # Step 8: Check logo detection
        if logo_match["status"] == "Not detected":
            issues.append({
                "word": "Official brand logo",
                "rule": "Visual identity / logo consistency",
                "severity": "medium",
                "source": "Logo verification",
                "message": (
                    "The saved official logo was not confidently detected "
                    "in this poster."
                ),
                "suggestion": (
                    "Check whether the correct official logo is present "
                    "and clearly visible. If it is present but altered, "
                    "ask the Brand Manager to verify it."
                )
            })

        elif logo_match["status"] == "Possible match":
            issues.append({
                "word": "Official brand logo",
                "rule": "Visual identity / logo consistency",
                "severity": "low",
                "source": "Logo verification",
                "message": (
                    "A possible version of the official logo was found, "
                    "but the visual match is uncertain."
                ),
                "suggestion": (
                    "Ask the Brand Manager to compare the poster logo "
                    "with the saved official logo."
                )
            })

        # Step 9: Save analysis report
        rid = save_review(
            "Image",
            file.filename or "Uploaded image",
            extracted,
            issues,
            user["id"],
            file.filename or "uploaded-image",
            data,
            readability
        )

        return {
            "review_id": rid,
            "message": "Image analyzed successfully!",
            "filename": file.filename,
            "extracted_text": extracted,
            "total_issues": len(issues),
            "readability": readability,
            "color_analysis": color_analysis,
            "ocr_method": ocr_method,
            "status": "Needs Review" if issues else "Passed Basic Checks",
            "issues": issues
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            400,
            f"Image analysis failed: {str(exc)}"
        )
