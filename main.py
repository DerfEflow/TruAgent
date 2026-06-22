from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import os
import hashlib
import json
import secrets
import threading
import time
from datetime import datetime, timedelta
from jose import JWTError, jwt
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from a local .env file (if present) so the app
# can be configured without setting OS-level environment variables.
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# The OpenAI client is created lazily so the app can boot and be reviewed
# without an API key. AI features stay dormant until OPENAI_API_KEY is set.
_openai_client = None

def get_openai_client():
    """Return a cached OpenAI client, or None if no API key is configured."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    _openai_client = OpenAI(api_key=api_key)
    return _openai_client

SECRET_KEY = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

# Fail-closed door secrets (sec-01 / G11). A missing or still-default inbound door
# secret must NOT fall back to a publicly-known placeholder that any caller could
# send. Instead it resolves to an unguessable random value, so each door's
# `provided != SECRET` check rejects EVERY request until a real secret is set. The
# app still boots (the door just stays dormant) and we warn loudly so the operator
# knows which doors are disabled.
_DISABLED_DOORS: List[str] = []

def _door_secret(name: str, placeholder: str) -> str:
    val = os.getenv(name)
    if val and val != placeholder:
        return val
    _DISABLED_DOORS.append(name)
    print(f"[SECURITY] {name} is unset or still the public placeholder -> door "
          f"DISABLED (rejecting all requests). Set a strong {name} in the "
          f"environment to enable this door.")
    return "DISABLED_" + secrets.token_urlsafe(32)

ZAPIER_SECRET = _door_secret("ZAPIER_SECRET", "change_this_secret_in_production")
ROOFR_WEBHOOK_URL = os.getenv("ROOFR_WEBHOOK_URL", "")
QUICKBOOKS_SECRET = _door_secret("QUICKBOOKS_SECRET", "change_this_in_production")
EMAIL_WEBHOOK_URL = os.getenv("EMAIL_WEBHOOK_URL", "")
SMS_WEBHOOK_URL = os.getenv("SMS_WEBHOOK_URL", "")

# Inbound webhook secrets for the three sibling-app doors (F1/F2/F3) and the
# scheduler endpoint (F4). Each is validated server-side on every request.
ALPHA_SECRET = _door_secret("ALPHA_SECRET", "change_alpha_secret_in_production")
PRODUCTION_SECRET = _door_secret("PRODUCTION_SECRET", "change_production_secret_in_production")
LEADS_SECRET = _door_secret("LEADS_SECRET", "change_leads_secret_in_production")
CRON_SECRET = _door_secret("CRON_SECRET", "change_cron_secret_in_production")
ESIGN_WEBHOOK_URL = os.getenv("ESIGN_WEBHOOK_URL", "")
# Shared secret for the inbound e-sign callback (S33/O57). Separate from the
# outbound ESIGN_WEBHOOK_URL above.
ESIGN_SECRET = _door_secret("ESIGN_SECRET", "change_esign_secret_in_production")

# Shared secret for the inbound comms door (P2-10): a Zapier email-parser / Gmail
# trigger and a Twilio inbound-SMS webhook POST incoming customer messages here.
INBOX_SECRET = _door_secret("INBOX_SECRET", "change_inbox_secret_in_production")

# AI model is configurable so a bad/unavailable id never requires a code change.
# Default is a current, known-good id; a fallback (OPENAI_FALLBACK_MODEL) is used
# automatically if the primary id is rejected (see _create_completion). Override
# with the OPENAI_MODEL env var to track newer models without a code change.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")

ADMIN_EMAIL = "fred@trulineroofing.com"

# Persistent storage location. Defaults to the project dir (current behaviour) so
# local dev is unchanged. In production set DATA_DIR to a mounted persistent
# volume (e.g. DATA_DIR=/data on Railway) so db.json + uploaded documents survive
# every redeploy. Both the database file and the documents folder live here.
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
db_file = os.path.join(DATA_DIR, "db.json")
DOCUMENTS_DIR = os.path.join(DATA_DIR, "documents")
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")

# Storage backend. When SUPABASE_URL + SUPABASE_SERVICE_KEY are set, the whole-db
# document is stored as a single JSONB row in Supabase Postgres (table app_state,
# id=1) via the REST API, instead of db.json — making the data a real database
# (live dashboard, backups, concurrency) while keeping the exact dict-in/dict-out
# contract the rest of the app relies on. When they are blank, behaviour is
# unchanged (local file db.json) — which is also the instant rollback path: unset
# the vars and the app reads the file again. On first boot in Postgres mode the
# existing db.json (the live data) is imported automatically and left in place as a
# backup. Uploaded documents/photos always stay on DATA_DIR.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
PG_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)

# ─── Specs-corpus constants ───────────────────────────────────────────────────
# Volume-solids per coating chemistry — scraped from manufacturer specs.
# Dry-mil ≈ gallons_applied × 1604 × volume_solids ÷ sqft_coated.
# Silicones run 90–96%; water-based acrylics ~45–55%. Never use a single constant.
_VOLUME_SOLIDS = {
    "silicone": 0.93, "acrylic": 0.50, "urethane": 0.80,
    "elastomeric": 0.55, "butyl": 0.70, "asphaltic": 0.60, "hybrid": 0.70,
}
_DEFAULT_VS = 0.65

# Weather profiles seeded from specs corpus.
# min_cure_before_rain_hrs = first-class field; this is the spec line that voids
# acrylic/urethane warranties (where silicones are far more forgiving).
_DEFAULT_WEATHER_PROFILES = {
    "silicone": {
        "temp_min": 40, "temp_max": 120, "surface_min": 35, "surface_max": 175,
        "rh_max": 90, "surface_minus_dewpoint": 5, "rain_free_hrs_apply": 0.5,
        "min_cure_before_rain_hrs": 2, "inter_coat_window_hrs": 24,
    },
    "acrylic": {
        "temp_min": 50, "temp_max": 95, "surface_min": 50, "surface_max": 150,
        "rh_max": 85, "surface_minus_dewpoint": 5, "rain_free_hrs_apply": 2,
        "min_cure_before_rain_hrs": 24, "inter_coat_window_hrs": 4,
    },
    "urethane": {
        "temp_min": 40, "temp_max": 100, "surface_min": 40, "surface_max": 150,
        "rh_max": 85, "surface_minus_dewpoint": 5, "rain_free_hrs_apply": 1,
        "min_cure_before_rain_hrs": 8, "inter_coat_window_hrs": 8,
    },
    "elastomeric": {
        "temp_min": 45, "temp_max": 100, "surface_min": 45, "surface_max": 155,
        "rh_max": 85, "surface_minus_dewpoint": 5, "rain_free_hrs_apply": 2,
        "min_cure_before_rain_hrs": 12, "inter_coat_window_hrs": 6,
    },
    "butyl": {
        "temp_min": 35, "temp_max": 110, "surface_min": 35, "surface_max": 165,
        "rh_max": 80, "surface_minus_dewpoint": 5, "rain_free_hrs_apply": 1,
        "min_cure_before_rain_hrs": 6, "inter_coat_window_hrs": 12,
    },
}

# Substrate prep items required by substrate type (P22)
_PREP_ITEMS_BY_SUBSTRATE = {
    "metal":    ["clean", "rust_treatment", "primer", "seams_sealed", "fasteners_tight"],
    "tpo":      ["clean", "seams_sealed", "membrane_inspection"],
    "epdm":     ["clean", "seams_sealed", "primer"],
    "bur":      ["clean", "blisters_cut", "felts_dried", "flashings_checked"],
    "modified": ["clean", "blisters_cut", "seams_sealed", "flashings_checked"],
    "concrete": ["clean", "cracks_filled", "primer", "ponding_addressed"],
    "foam":     ["clean", "inspection", "bare_foam_primed"],
    "default":  ["clean", "ponding_addressed", "seams_sealed", "primer"],
}

# Rotated 2026-06-14 (sec-02): the public demo passwords (truline2024 / roof123 /
# office123) are retired. Their strong replacements live ONLY in the operator's
# local ROTATED-LOGINS-2026-06-14.txt (git-ignored) - never in code or docs. The
# values below are the sha256 hashes of those strong passwords. On load, any of
# these three seeded users still carrying the OLD public demo hash is auto-rotated
# to the new hash, so the live db.json is upgraded on next boot without a lockout.
_ROTATED_USER_HASHES = {
    "fred@trulineroofing.com": "1e9d9281902c5af80762106680d32c9363b0de82e57aa114489d80e6c00bd984",
    "office@trulineroofing.com": "40525bdf88e60aef331d7b7fd78a0da73eefe030f96c7b3f353a3701759fe827",
    "fieldcrew@trulineroofing.com": "f4d81178cc1eafa56f5f4793e75544ac18653f33b47044691aea2508a2fe0782",
}
_RETIRED_DEMO_HASHES = {
    "fred@trulineroofing.com": hashlib.sha256(b"truline2024").hexdigest(),
    "office@trulineroofing.com": hashlib.sha256(b"office123").hexdigest(),
    "fieldcrew@trulineroofing.com": hashlib.sha256(b"roof123").hexdigest(),
}


def _seed_db() -> dict:
    """A fresh database seeded with the three (rotated) logins and all collections."""
    return {
        "jobs": {},
        "documents": {},
        "chat_history": {},
        "financials": {"invoices": {}, "expenses": {}},
        "weather_profiles": {k: dict(v) for k, v in _DEFAULT_WEATHER_PROFILES.items()},
        "templates": {},
        "sds": {},
        "employees": {},
        "parties": {},
        "opportunities": {},
        "equipment": {},
        "doc_chunks": {},
        "cron_log": [],
        "pending_voice_reports": [],
        "outbox": [],
        "sms_outbox": [],
        "users": {
            "fred@trulineroofing.com": {
                "email": "fred@trulineroofing.com",
                "password_hash": _ROTATED_USER_HASHES["fred@trulineroofing.com"],
                "role": "super_admin"
            },
            "fieldcrew@trulineroofing.com": {
                "email": "fieldcrew@trulineroofing.com",
                "password_hash": _ROTATED_USER_HASHES["fieldcrew@trulineroofing.com"],
                "role": "user"
            },
            "office@trulineroofing.com": {
                "email": "office@trulineroofing.com",
                "password_hash": _ROTATED_USER_HASHES["office@trulineroofing.com"],
                "role": "manager"
            }
        }
    }


def _normalize_db(db) -> bool:
    """Idempotent in-memory upgrades applied on every load. Returns True if the
    db dict was modified (so the caller can persist it). Shared by the file and
    Postgres storage paths so the two backends never drift."""
    needs_migration = False

    for email, user_data in db.get("users", {}).items():
        if "is_admin" in user_data and "role" not in user_data:
            if user_data["is_admin"]:
                user_data["role"] = "super_admin"
            else:
                if email == "office@trulineroofing.com":
                    user_data["role"] = "manager"
                else:
                    user_data["role"] = "user"
            del user_data["is_admin"]
            needs_migration = True

    # Auto-rotate any seeded user still on a retired public demo password
    # (sec-02) to its strong replacement, so the live db is upgraded without a
    # lockout. Idempotent: only fires while the old hash is present.
    for _email, _retired_hash in _RETIRED_DEMO_HASHES.items():
        _u = db.get("users", {}).get(_email)
        if _u and _u.get("password_hash") == _retired_hash:
            _u["password_hash"] = _ROTATED_USER_HASHES[_email]
            needs_migration = True

    for _key in ("weather_profiles", "templates", "sds", "employees",
                 "parties", "opportunities", "equipment", "doc_chunks"):
        if _key not in db:
            db[_key] = {}
            needs_migration = True
    if "cron_log" not in db:
        db["cron_log"] = []
        needs_migration = True
    if "pending_voice_reports" not in db:
        db["pending_voice_reports"] = []
        needs_migration = True
    # Outbound queues (email + SMS). Backfilled as lists on older db.json files so
    # they always exist alongside the setdefault() in the dispatch helpers and the
    # GET /outbox + flush endpoints.
    for _list_key in ("outbox", "sms_outbox"):
        if _list_key not in db:
            db[_list_key] = []
            needs_migration = True
    if not db.get("weather_profiles"):
        db["weather_profiles"] = {k: dict(v) for k, v in _DEFAULT_WEATHER_PROFILES.items()}
        needs_migration = True
    if "financials" not in db:
        db["financials"] = {}
        needs_migration = True
    if "invoices" not in db.get("financials", {}):
        db.setdefault("financials", {})["invoices"] = {}
        needs_migration = True
    if "expenses" not in db.get("financials", {}):
        db.setdefault("financials", {})["expenses"] = {}
        needs_migration = True

    return needs_migration


# ─── Postgres storage backend via Supabase REST (active when PG_ENABLED) ──────
# Uses the service_role key, which bypasses RLS. The whole db lives in one JSONB
# row (app_state.id = 1). The table is created out-of-band by a Supabase migration
# (create_app_state_singleton), so there is no runtime DDL here. requests is
# imported lazily to match the rest of this module.
def _pg_headers(extra=None):
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _pg_url():
    return f"{SUPABASE_URL}/rest/v1/app_state"


def _pg_load_row():
    """Return the stored db dict, or None if the singleton row does not exist."""
    import requests
    r = requests.get(
        _pg_url(),
        params={"id": "eq.1", "select": "data", "limit": "1"},
        headers=_pg_headers(), timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0]["data"] if rows else None


def _pg_save(data):
    """Upsert the singleton row (POST + merge-duplicates acts as upsert on the PK)."""
    import requests
    r = requests.post(
        _pg_url(),
        headers=_pg_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        data=json.dumps({"id": 1, "data": data}), timeout=15,
    )
    r.raise_for_status()


def load_db():
    if PG_ENABLED:
        db = _pg_load_row()
        if db is None:
            # First boot on Postgres: import the existing db.json (the live data)
            # if present on the volume, otherwise seed. The file is left in place
            # untouched as a backup and as the rollback source (unset the SUPABASE_*
            # vars to revert to file mode).
            if os.path.exists(db_file):
                try:
                    with open(db_file, 'r') as f:
                        db = json.load(f)
                except (json.JSONDecodeError, OSError, ValueError):
                    db = _seed_db()
            else:
                db = _seed_db()
            _normalize_db(db)
            _pg_save(db)
            return _pg_load_row() or db
        if _normalize_db(db):
            _pg_save(db)
        return db

    # ── File mode (DATABASE_URL unset) — original behaviour, unchanged ──
    if os.path.exists(db_file):
        try:
            with open(db_file, 'r') as f:
                db = json.load(f)
        except (json.JSONDecodeError, OSError, ValueError):
            # Corrupt/unreadable db.json — move it aside for forensics and reseed,
            # rather than 500-ing every request (load_db runs on every route).
            try:
                os.replace(db_file, db_file + ".corrupt." + datetime.now().strftime("%Y%m%d%H%M%S"))
            except OSError:
                pass
            db = _seed_db()
            save_db(db)
            return db

        if _normalize_db(db):
            save_db(db)
        return db

    return _seed_db()

# Serialises concurrent writers to the file backend. Uvicorn runs a single async
# worker, but synchronous cron-task handlers block that loop and can interleave a
# load->modify->save with a door webhook's save. A threading.Lock keeps the
# temp-file write + os.replace atomic across writers so db.json can't be clobbered
# mid-flight. (PG mode upserts atomically and needs no lock.)
_DB_WRITE_LOCK = threading.Lock()

def save_db(data):
    if PG_ENABLED:
        _pg_save(data)
        return
    # Atomic write: dump to a temp file in the same directory, then os.replace()
    # it over the target. A crash mid-write can't leave db.json half-written and
    # invalid (which would fail to load on the next boot).
    with _DB_WRITE_LOCK:
        tmp = db_file + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, db_file)

security = HTTPBearer()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None or not isinstance(email, str):
            raise credentials_exception
        
        db = load_db()
        user = db["users"].get(email)
        if user is None:
            raise credentials_exception
        return user
    except JWTError:
        raise credentials_exception

async def get_super_admin(current_user: dict = Depends(get_current_user)):
    """Only super_admin (Fred) can access"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current_user

async def get_manager_or_above(current_user: dict = Depends(get_current_user)):
    """Manager and super_admin can access"""
    if current_user.get("role") not in ["super_admin", "manager"]:
        raise HTTPException(status_code=403, detail="Manager access required")
    return current_user

async def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Legacy: Alias for super_admin"""
    return await get_super_admin(current_user)

class Login(BaseModel):
    email: str
    password: str

class Job(BaseModel):
    job_id: str
    client_name: str
    address: str
    status: str = "Pending"
    images: List[str] = []
    notes: List[str] = []

class ChatMessage(BaseModel):
    message: str
    
class ZapierWebhook(BaseModel):
    secret: str
    job_id: Optional[str] = None
    client_name: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
    data: Optional[dict] = None

class AIAction(BaseModel):
    action: str
    parameters: dict

class NewUser(BaseModel):
    email: str
    password: str
    role: str

class UpdateRole(BaseModel):
    role: str

class RoofrUpdate(BaseModel):
    job_id: str
    status: Optional[str] = None
    notes: Optional[str] = None
    workflow_stage: Optional[str] = None
    data: Optional[dict] = None

class QuickBooksWebhook(BaseModel):
    secret: str
    transaction_type: str  # "invoice" or "expense"
    transaction_id: str
    job_id: Optional[str] = None
    amount: float
    date: str
    description: Optional[str] = None
    customer_name: Optional[str] = None
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    data: Optional[dict] = None

class EmailMessage(BaseModel):
    to: str
    subject: str
    body: str
    html: Optional[str] = None
    document_ids: Optional[List[str]] = []

class SMSMessage(BaseModel):
    to: str
    message: str

# ─── New models (F1–I63) ─────────────────────────────────────────────────────

class AlphaWebhook(BaseModel):
    secret: str
    job_id: str
    client_name: Optional[str] = None
    address: Optional[str] = None
    contract_value: Optional[float] = None
    coating_system: Optional[str] = None
    substrate: Optional[str] = None
    sqft: Optional[float] = None
    dry_mil_target: Optional[float] = None
    quoted_margin: Optional[float] = None
    loaded_labor_rate: Optional[float] = None
    est_gallons: Optional[Dict[str, float]] = None       # {"product_name": gallons}
    material_cost_per_gal: Optional[Dict[str, float]] = None
    labor_hours_by_method: Optional[Dict[str, float]] = None
    data: Optional[dict] = None

class ProductionLogWebhook(BaseModel):
    secret: str
    job_id: str
    date: str
    crew: Optional[str] = None
    product: Optional[str] = None
    gallons_applied: Optional[float] = None
    gallons_by_product: Optional[Dict[str, float]] = None
    sqft_coated: Optional[float] = None
    wet_mil: Optional[List[float]] = None
    hours_by_type: Optional[Dict[str, float]] = None    # {"spray": h, "prep": h, "roller": h}
    weather: Optional[dict] = None
    photo_refs: Optional[List[str]] = None
    notes: Optional[str] = None
    coat_seq: Optional[int] = None
    # ── Delta field-data wire contract (step 6 receiver) — all optional. ────────
    # Log-level field readings/warnings/punch/photo metadata, stored verbatim on
    # the appended log_entry. The lists carry whatever shape Delta sends; we never
    # interpret or recompute them.
    dft_readings: Optional[List[dict]] = None   # [{reading, is_thin, sample_number}]
    wft_readings: Optional[List[dict]] = None   # [{reading, is_thin}]
    ai_warnings: Optional[List[dict]] = None    # [{warning_type, severity, message, dismissed}]
    punch_list: Optional[List[dict]] = None     # [{repair_needed, is_completed}]
    photo_meta: Optional[List[dict]] = None     # [{phase, photo_type, description, latitude, longitude}]
    # Job-level objects (latest non-empty wins). spec_baseline values are warranty
    # thresholds — passed through verbatim, never computed or guessed here.
    inspection: Optional[dict] = None           # {inspection_date, inspector_name, manufacturer_name, warranty_required}
    spec_baseline: Optional[dict] = None         # {required_wft_mils, required_dft_mils, coverage_rate, expected_coating_gallons, min_temp_f, max_temp_f, max_humidity_pct, min_dewpoint_spread_f}

class LeadWebhook(BaseModel):
    secret: str
    source: Optional[str] = None
    client_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    rep: Optional[str] = None
    territory: Optional[str] = None
    data: Optional[dict] = None

class ChangeOrderRequest(BaseModel):
    reason: str
    added_gallons: Optional[float] = 0
    added_hours: Optional[float] = 0
    price: Optional[float] = 0
    approved_by: Optional[str] = None

class DrawRequest(BaseModel):
    description: str
    amount: float
    milestone: Optional[str] = None
    retainage_pct: Optional[float] = 10.0

class WeatherCheckRequest(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    coating_system: Optional[str] = None

class PrepSignoffRequest(BaseModel):
    substrate: Optional[str] = "default"
    area: Optional[str] = None
    items: Dict[str, bool]   # {"clean": True, "primer": True, ...}
    notes: Optional[str] = None

class QAReadingRequest(BaseModel):
    product: str
    coat_seq: Optional[int] = 1
    area: Optional[str] = None
    wet_mil: Optional[List[float]] = None
    notes: Optional[str] = None

class WeatherApplicationCheckRequest(BaseModel):
    temp: Optional[float] = None            # ambient air temp (°F)
    surface_temp: Optional[float] = None    # substrate/surface temp (°F)
    rh: Optional[float] = None              # relative humidity (%)
    dewpoint: Optional[float] = None        # dewpoint (°F)
    wind: Optional[float] = None            # wind speed (mph)
    rain_free_hrs_actual: Optional[float] = None   # POST-application rain-free hours achieved
    coat_seq: Optional[int] = None
    notes: Optional[str] = None

class CoatLogRequest(BaseModel):
    product: str
    coat_seq: int
    wet_mil: Optional[float] = None
    sqft_coated: Optional[float] = None
    notes: Optional[str] = None

class PunchItemRequest(BaseModel):
    description: str
    area: Optional[str] = None
    assignee: Optional[str] = None
    photo_ref: Optional[str] = None

class PunchItemUpdate(BaseModel):
    status: str   # open | in_progress | done
    notes: Optional[str] = None

class WarrantyRequest(BaseModel):
    manufacturer: Optional[str] = None
    warranty_type: Optional[str] = None
    term_years: Optional[int] = None
    required_mil: Optional[float] = None
    install_date: Optional[str] = None
    registration_deadline: Optional[str] = None
    cert_number: Optional[str] = None
    registered: Optional[bool] = False
    renewal_recoat_due: Optional[str] = None

class PipelineStageUpdate(BaseModel):
    stage: str
    notes: Optional[str] = None

class ConvertToJobRequest(BaseModel):
    # Link to an existing job instead of creating one (optional). When omitted, a
    # TruAgent-native job `opp-<opportunity_id>` is created from the opportunity.
    link_job_id: Optional[str] = None
    workflow_stage: Optional[str] = None   # initial stage for a newly created job

class WinLossRequest(BaseModel):
    outcome: str    # "won" | "lost"
    loss_reason: Optional[str] = None   # price | tear_off | competitor | saturated | warranty_short | weather
    notes: Optional[str] = None
    contract_value: Optional[float] = None

class ESignRequest(BaseModel):
    document_id: Optional[str] = None
    recipient_email: str
    recipient_name: Optional[str] = None
    document_type: str = "proposal"
    message: Optional[str] = None

class ESignWebhook(BaseModel):
    secret: str
    document_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    job_id: Optional[str] = None
    status: str = "signed"   # signed | viewed | declined
    signed_pdf_url: Optional[str] = None
    signed_pdf_document_id: Optional[str] = None
    data: Optional[dict] = None

class TimelogRequest(BaseModel):
    employee: str
    arrive: str
    depart: Optional[str] = None
    geo: Optional[dict] = None
    hours_type: Optional[str] = "general"   # spray | prep | roller | general

class PartyRequest(BaseModel):
    name: str
    party_type: str = "sub"   # sub | vendor
    trade: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

class PartyUpdate(BaseModel):
    w9: Optional[bool] = None
    subcontract: Optional[bool] = None
    trade: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

class COIRequest(BaseModel):
    party_id: str
    carrier: str
    policy_number: Optional[str] = None
    expiry: str   # ISO date string
    gl_limit: Optional[float] = None
    wc_limit: Optional[float] = None
    document_id: Optional[str] = None

class TemplateRequest(BaseModel):
    name: str
    kind: str   # subcontract | proposal | warranty | lien_waiver | jha | dispatch
    body: str   # may contain {{merge_tokens}}

class SDSRequest(BaseModel):
    product: str
    manufacturer: Optional[str] = None
    document_id: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None

class EmployeeRequest(BaseModel):
    name: str
    email: Optional[str] = None
    role: Optional[str] = "crew"

class CertRequest(BaseModel):
    cert_type: str   # osha10 | osha30 | fall_protection | respirator_fit | lift | applicator | other
    expiry: Optional[str] = None
    notes: Optional[str] = None

class LienWaiverRequest(BaseModel):
    waiver_type: str   # conditional_progress | unconditional_progress | conditional_final | unconditional_final
    through_date: Optional[str] = None
    payment_amount: Optional[float] = None
    claimant_name: Optional[str] = None

class ContactLogRequest(BaseModel):
    contact_type: str   # email | sms | call | visit | note
    summary: str
    contact_with: Optional[str] = None
    direction: Optional[str] = "outbound"
    due_at: Optional[str] = None        # P1-3: when the NEXT follow-up is due (ISO). Default +3 days.

class ReferralRequest(BaseModel):
    referrer_name: Optional[str] = None     # the happy customer making the referral
    referred_name: str                       # the new prospect
    referred_contact: Optional[str] = None   # phone/email of the prospect
    notes: Optional[str] = None

class InboxWebhook(BaseModel):
    secret: str
    channel: str = "email"              # email | sms
    contact: Optional[str] = None       # the customer's email/phone (the sender)
    name: Optional[str] = None          # sender display name, if known
    to: Optional[str] = None            # which inbox/number it came in on
    subject: Optional[str] = None
    body: str = ""
    data: Optional[dict] = None

class InboxSend(BaseModel):
    channel: str = "email"              # email | sms
    to: str
    subject: Optional[str] = None
    body: str
    job_id: Optional[str] = None

class PermitRequest(BaseModel):
    permit_type: Optional[str] = "roofing"
    permit_number: Optional[str] = None
    status: str = "pending"   # pending | applied | issued | not_required
    jurisdiction: Optional[str] = None
    issued_date: Optional[str] = None

class JHARequest(BaseModel):
    coating_system: Optional[str] = None
    hazards: Optional[List[str]] = None
    controls: Optional[List[str]] = None
    ppe_required: Optional[List[str]] = None

class AssignmentRequest(BaseModel):
    job_id: str
    crew: str
    date: str   # YYYY-MM-DD
    phase: Optional[str] = None
    equipment_id: Optional[str] = None   # specific rig/lift from the equipment registry
    notes: Optional[str] = None

class EquipmentRequest(BaseModel):
    name: str
    equipment_type: str   # sprayer | lift | truck | trailer | other
    day_rate: Optional[float] = None
    notes: Optional[str] = None

class DispatchRequest(BaseModel):
    date: str
    crew: Optional[str] = None
    job_ids: Optional[List[str]] = None

class VoiceReportRequest(BaseModel):
    transcript: str
    job_id: Optional[str] = None

class ReviewRequest(BaseModel):
    platform: Optional[str] = "google"
    message: Optional[str] = None

# ─────────────────────────────────────────────────────────────────────────────
# Agent operations — shared by the /chat AI agent (tool-calling) and the explicit
# /ai/action endpoint, so both go through one code path and stay consistent.
# These are plain functions (no FastAPI deps); they mutate and persist `db`.
# ─────────────────────────────────────────────────────────────────────────────

def _sync_to_roofr(payload: dict) -> str:
    """POST a job update out to Roofr via the Zapier outbound webhook, if set.
    Returns a short status string: 'synced', 'not configured', or an error."""
    if not ROOFR_WEBHOOK_URL:
        return "not configured"
    try:
        import requests
        resp = requests.post(ROOFR_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return "synced"
    except Exception as e:
        return f"sync failed: {e}"


def _outbound_roofr_id(job: dict, internal_job_id: Optional[str]) -> Optional[str]:
    """The id Roofr knows this job by. Prefer a stored roofr_job_id cross-reference
    (set when a Roofr/Zapier job is linked to a suite job); fall back to the
    internal id so Roofr-originated jobs (already keyed by their Roofr id) keep
    working. Without this, outbound status/note pushes for suite jobs go out under
    the internal 'alpha-<uuid>' id Roofr never saw, so they match no Roofr record."""
    if isinstance(job, dict):
        data = job.get("data") or {}
        xref = job.get("roofr_job_id") or data.get("roofr_job_id")
        if xref:
            return str(xref)
    return internal_job_id


def _resolve_job_id(db: dict, external_id) -> Optional[str]:
    """Map an id from an external system (QuickBooks/Roofr) to the internal job
    key. Returns the id directly if it already IS a job key; otherwise finds a job
    whose stored cross-ref (roofr_job_id / qb_job_id, at job root or under data)
    equals it. Returns None if nothing matches, so a real invoice is stored
    unlinked rather than mis-attached to the wrong job."""
    if not external_id:
        return None
    if external_id in db.get("jobs", {}):
        return external_id
    ext = str(external_id)
    for jid, job in db.get("jobs", {}).items():
        if not isinstance(job, dict):
            continue
        data = job.get("data") or {}
        for key in ("roofr_job_id", "qb_job_id"):
            if str(job.get(key) or data.get(key) or "") == ext:
                return jid
    return None


def _op_update_job_status(db: dict, job_id: Optional[str], status: Optional[str],
                          workflow_stage: Optional[str], user_email: str) -> dict:
    job = db["jobs"].get(job_id) if job_id else None
    if not job:
        return {"status": "error", "message": f"Job {job_id!r} not found"}
    if status:
        job["status"] = status
    if workflow_stage:
        job["workflow_stage"] = workflow_stage
    save_db(db)
    sync = _sync_to_roofr({
        "job_id": _outbound_roofr_id(job, job_id),
        "truagent_job_id": job_id,
        "status": job.get("status"),
        "workflow_stage": job.get("workflow_stage"),
        "client_name": job.get("client_name"),
        "address": job.get("address"),
        "updated_by": user_email,
        "updated_at": datetime.now().isoformat(),
    })
    return {"status": "ok", "job_id": job_id, "new_status": job.get("status"),
            "workflow_stage": job.get("workflow_stage"), "roofr_sync": sync}


def _op_add_job_note(db: dict, job_id: Optional[str], note: Optional[str],
                     user_email: str) -> dict:
    job = db["jobs"].get(job_id) if job_id else None
    if not job:
        return {"status": "error", "message": f"Job {job_id!r} not found"}
    if not note:
        return {"status": "error", "message": "Note text is required"}
    notes = job.get("notes")
    if not isinstance(notes, list):
        notes = []
    notes.append({"note": note, "added_by": user_email,
                  "added_at": datetime.now().isoformat()})
    job["notes"] = notes
    save_db(db)
    sync = _sync_to_roofr({
        "job_id": _outbound_roofr_id(job, job_id),
        "truagent_job_id": job_id,
        "new_note": note,
        "client_name": job.get("client_name"),
        "address": job.get("address"),
        "updated_by": user_email,
        "updated_at": datetime.now().isoformat(),
    })
    return {"status": "ok", "job_id": job_id, "roofr_sync": sync}


def _gather_attachments(db: dict, document_ids) -> list:
    attachments = []
    for doc_id in (document_ids or []):
        doc = db["documents"].get(str(doc_id))
        if not doc:
            continue
        try:
            import base64
            with open(doc["filepath"], "rb") as f:
                attachments.append({
                    "filename": doc["filename"],
                    "content": base64.b64encode(f.read()).decode(),
                    "contentType": "application/octet-stream",
                })
        except Exception:
            pass
    return attachments


def _queue_email(db: dict, payload: dict, reason: str) -> dict:
    """Park an email in the outbox so it is never lost. Flushed by the
    flush_outbox cron task (or POST /outbox/flush) once EMAIL_WEBHOOK_URL is
    configured. Persists immediately."""
    outbox = db.setdefault("outbox", [])
    entry = {
        "id": f"out_{int(datetime.now().timestamp() * 1000)}_{len(outbox)}",
        "payload": payload,
        "status": "queued",
        "queued_reason": reason,
        "attempts": 0,
        "queued_at": datetime.now().isoformat(),
        "last_error": None,
    }
    outbox.append(entry)
    save_db(db)
    return entry


def _email_dispatch(db: dict, payload: dict) -> dict:
    """Single choke point for outbound email. Sends through the Zapier
    EMAIL_WEBHOOK_URL when configured; otherwise (or on failure) queues the
    email in the outbox instead of dropping it."""
    to = payload.get("to")
    if not EMAIL_WEBHOOK_URL:
        entry = _queue_email(db, payload, "email webhook not configured")
        return {"status": "queued",
                "message": (f"Email to {to} saved to the outbox ({entry['id']}). "
                            "It will send automatically once the email Zap "
                            "(EMAIL_WEBHOOK_URL) is configured.")}
    try:
        import requests
        resp = requests.post(EMAIL_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return {"status": "ok", "message": f"Email sent to {to}"}
    except Exception as e:
        entry = _queue_email(db, payload, f"send failed: {e}")
        entry["attempts"] = 1
        entry["last_error"] = str(e)
        save_db(db)
        return {"status": "queued",
                "message": f"Send to {to} failed ({e}); email queued for retry ({entry['id']})."}


def _op_send_email(db: dict, to: Optional[str], subject: str, body: str,
                   html: Optional[str], document_ids, user_email: str) -> dict:
    if not to:
        return {"status": "error", "message": "A recipient ('to') is required"}
    attachments = _gather_attachments(db, document_ids)
    payload = {
        "to": to, "subject": subject, "body": body, "html": html,
        "attachments": attachments or None,
        "sent_by": user_email, "sent_at": datetime.now().isoformat(),
    }
    return _email_dispatch(db, payload)


def _queue_sms(db: dict, payload: dict, reason: str) -> dict:
    """Park an SMS in the sms_outbox so it is never lost. Flushed by the
    flush_sms cron task (or POST /sms-outbox/flush) once SMS_WEBHOOK_URL is
    configured. Persists immediately. Mirrors _queue_email."""
    outbox = db.setdefault("sms_outbox", [])
    entry = {
        "id": f"sms_{int(datetime.now().timestamp() * 1000)}_{len(outbox)}",
        "payload": payload,
        "status": "queued",
        "queued_reason": reason,
        "attempts": 0,
        "queued_at": datetime.now().isoformat(),
        "last_error": None,
    }
    outbox.append(entry)
    save_db(db)
    return entry


def _sms_dispatch(db: dict, payload: dict) -> dict:
    """Single choke point for outbound SMS. Sends through the Zapier
    SMS_WEBHOOK_URL when configured; otherwise (or on failure) queues the text
    in the sms_outbox instead of dropping it. Mirrors _email_dispatch."""
    to = payload.get("to")
    if not SMS_WEBHOOK_URL:
        entry = _queue_sms(db, payload, "sms webhook not configured")
        return {"status": "queued",
                "message": (f"SMS to {to} saved to the outbox ({entry['id']}). "
                            "It will send automatically once the SMS Zap "
                            "(SMS_WEBHOOK_URL) is configured.")}
    try:
        import requests
        resp = requests.post(SMS_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return {"status": "ok", "message": f"SMS sent to {to}"}
    except Exception as e:
        entry = _queue_sms(db, payload, f"send failed: {e}")
        entry["attempts"] = 1
        entry["last_error"] = str(e)
        save_db(db)
        return {"status": "queued",
                "message": f"Send to {to} failed ({e}); SMS queued for retry ({entry['id']})."}


def _op_send_sms(db: dict, to: Optional[str], message: str, user_email: str) -> dict:
    if not to:
        return {"status": "error", "message": "A recipient ('to') is required"}
    payload = {"to": to, "message": message, "sent_by": user_email,
               "sent_at": datetime.now().isoformat()}
    return _sms_dispatch(db, payload)


def _job_financials(db: dict, job_id: Optional[str]) -> dict:
    job = db["jobs"].get(job_id) if job_id else None
    if not job:
        return {"status": "error", "message": f"Job {job_id!r} not found"}
    financials = db.get("financials") or {}
    inv_map = financials.get("invoices", {})
    exp_map = financials.get("expenses", {})
    invoices = [inv_map[i] for i in job.get("invoices", []) if i in inv_map]
    expenses = [exp_map[e] for e in job.get("expenses", []) if e in exp_map]
    revenue = sum(float(inv.get("amount", 0) or 0) for inv in invoices
                  if inv.get("status") != "cancelled")
    costs = sum(float(exp.get("amount", 0) or 0) for exp in expenses)
    profit = revenue - costs
    margin = (profit / revenue * 100) if revenue > 0 else 0
    return {"status": "ok", "job_id": job_id, "client_name": job.get("client_name"),
            "invoice_count": len(invoices), "expense_count": len(expenses),
            "total_revenue": round(revenue, 2), "total_costs": round(costs, 2),
            "profit": round(profit, 2), "margin_percent": round(margin, 2)}


def _company_financials_summary(db: dict) -> dict:
    financials = db.get("financials") or {}
    inv = list((financials.get("invoices") or {}).values())
    exp = list((financials.get("expenses") or {}).values())
    revenue = sum(float(i.get("amount", 0) or 0) for i in inv
                  if i.get("status") != "cancelled")
    costs = sum(float(e.get("amount", 0) or 0) for e in exp)
    profit = revenue - costs
    margin = (profit / revenue * 100) if revenue > 0 else 0
    return {"status": "ok", "job_count": len(db.get("jobs", {})),
            "invoice_count": len(inv), "expense_count": len(exp),
            "total_revenue": round(revenue, 2), "total_costs": round(costs, 2),
            "profit": round(profit, 2), "margin_percent": round(margin, 2)}


def _compact_job(job: dict) -> dict:
    """A small, prompt-friendly view of a job (no financial id lists, no blobs)."""
    return {k: job.get(k) for k in (
        "job_id", "job_name", "client_name", "status", "workflow_stage",
        "address", "assigned_to") if job.get(k) not in (None, "")}


# Financial fields the field-crew ('user') role must never see on a job object.
# Top-level money keys are dropped entirely; the budget block keeps operational
# fields (sqft, system, substrate, est_gallons, dry_mil_target, labor hours) but
# loses every dollar value.
_JOB_MONEY_TOP_KEYS = ("invoices", "expenses", "billing", "change_orders",
                       "draws", "job_value", "estimate")
_JOB_MONEY_BUDGET_KEYS = ("contract_value", "quoted_margin", "loaded_labor_rate",
                          "material_cost_per_gal")


def _strip_job_financials(job: dict) -> dict:
    """Return a copy of a job with all financial data removed, for the field-crew
    ('user') role. Operational/production fields are preserved so the crew can
    still work the job; only money is stripped. Enforced at the data layer so a
    field token can never read financials even by calling the API directly."""
    safe = {k: v for k, v in job.items() if k not in _JOB_MONEY_TOP_KEYS}
    budget = safe.get("budget")
    if isinstance(budget, dict):
        safe["budget"] = {k: v for k, v in budget.items()
                          if k not in _JOB_MONEY_BUDGET_KEYS}
    return safe


# ─── Coating / production helpers ────────────────────────────────────────────

def _get_volume_solids(system: str) -> float:
    if not system:
        return _DEFAULT_VS
    return _VOLUME_SOLIDS.get(system.lower().strip(), _DEFAULT_VS)


def _calc_achieved_dry_mil(gallons_applied: float, sqft: float, volume_solids: float) -> float:
    if sqft <= 0 or gallons_applied <= 0:
        return 0.0
    return round(gallons_applied * 1604.0 * volume_solids / sqft, 2)


def _production_pct_complete(job: dict) -> float:
    """Estimate % complete from sqft_coated vs. sqft in budget."""
    sqft_target = (job.get("budget") or {}).get("sqft", 0) or 0
    if sqft_target <= 0:
        return 0.0
    sqft_done = sum(
        float(log.get("sqft_coated") or 0)
        for log in job.get("production_logs") or []
    )
    return round(min(sqft_done / sqft_target * 100, 100), 1)


def _applied_gallons_by_product(job: dict) -> dict:
    """Aggregate applied gallons per product across all production logs."""
    totals: Dict[str, float] = {}
    for log in job.get("production_logs") or []:
        gbp = log.get("gallons_by_product") or {}
        if gbp:
            for prod, gals in gbp.items():
                totals[prod] = totals.get(prod, 0.0) + float(gals or 0)
        elif log.get("product") and log.get("gallons_applied"):
            prod = log["product"]
            totals[prod] = totals.get(prod, 0.0) + float(log["gallons_applied"])
    return totals


def _job_margin_live(db: dict, job: dict) -> Optional[float]:
    """Current live margin % for a job (requires financials)."""
    financials = db.get("financials") or {}
    inv_map = financials.get("invoices", {})
    exp_map = financials.get("expenses", {})
    invoices = [inv_map[i] for i in job.get("invoices", []) if i in inv_map]
    expenses = [exp_map[e] for e in job.get("expenses", []) if e in exp_map]
    revenue = sum(float(inv.get("amount", 0) or 0) for inv in invoices
                  if inv.get("status") != "cancelled")
    costs = sum(float(exp.get("amount", 0) or 0) for exp in expenses)
    if revenue > 0:
        return round((revenue - costs) / revenue * 100, 2)
    return None


def _log_thin_flags(log: dict) -> int:
    """Count thin-flagged readings on a single production log. Per the Delta
    field-data wire contract, a log may carry dft_readings / wft_readings, each
    a list of {reading, is_thin, ...}. A 'thin flag' is any reading whose
    is_thin is truthy. Both lists are optional; missing/None means zero."""
    n = 0
    for key in ("dft_readings", "wft_readings"):
        for r in (log.get(key) or []):
            if isinstance(r, dict) and r.get("is_thin"):
                n += 1
    return n


def _dashboard_summary(db: dict, role: str) -> dict:
    """Build the cross-app dashboard summary (step 9), role-gated.

    Role rules (enforced here, never just in the UI):
      - 'user' (field crew): NO leads key, financials = null.
      - manager / super_admin: leads (scope != 'public' only) + financials.

    O(n) over jobs: a single pass collects job counts/by-stage, recent jobs,
    recent field logs, and the company-wide thin-flag total."""
    jobs = db.get("jobs", {})
    is_manager = role in ("manager", "super_admin")

    by_stage: Dict[str, int] = {}
    recent_jobs = []
    recent_logs = []
    thin_flag_total = 0

    for jid, job in jobs.items():
        stage = job.get("workflow_stage") or "Unstaged"
        by_stage[stage] = by_stage.get(stage, 0) + 1
        recent_jobs.append({
            "job_id": job.get("job_id") or jid,
            "client_name": job.get("client_name"),
            "address": job.get("address"),
            "status": job.get("status"),
            "workflow_stage": job.get("workflow_stage"),
            "pct_complete": job.get("pct_complete"),
            "alert_count": len(job.get("alerts") or []),
        })
        for log in (job.get("production_logs") or []):
            flags = _log_thin_flags(log)
            thin_flag_total += flags
            recent_logs.append({
                "job_id": job.get("job_id") or jid,
                "date": log.get("date"),
                "crew": log.get("crew"),
                "sqft_coated": log.get("sqft_coated"),
                "thin_flags": flags,
                # private sort key (stripped before return)
                "_logged_at": log.get("logged_at") or log.get("date") or "",
            })

    # Recent jobs: most-recently-touched first where a hint exists, else stable.
    recent_jobs = recent_jobs[-10:][::-1]
    # Recent logs: newest first by logged_at/date, cap at 10.
    recent_logs.sort(key=lambda r: r.get("_logged_at") or "", reverse=True)
    recent_logs = recent_logs[:10]
    for r in recent_logs:
        r.pop("_logged_at", None)

    summary = {
        "role": role,
        "generated_at": datetime.now().isoformat(),
        "jobs": {
            "total": len(jobs),
            "by_stage": by_stage,
            "recent": recent_jobs,
        },
        "field": {
            "recent_logs": recent_logs,
            "thin_flag_total": thin_flag_total,
        },
        # financials/leads filled in below per role
        "financials": None,
    }

    if is_manager:
        fin = _company_financials_summary(db)
        summary["financials"] = {
            "total_revenue": fin.get("total_revenue"),
            "total_costs": fin.get("total_costs"),
            "profit": fin.get("profit"),
            "margin_percent": fin.get("margin_percent"),
        }
        opps = db.get("opportunities", {})
        # Truline-only view: exclude public-Dominate clients (scope == 'public').
        visible = [o for o in opps.values() if o.get("scope") != "public"]
        # 'open' = not yet won/closed. Opportunities track a 'stage'; treat the
        # terminal stages as closed, everything else as open.
        closed_stages = {"Won", "Closed", "Lost", "closed", "won", "lost"}
        open_count = sum(1 for o in visible if o.get("stage") not in closed_stages)
        recent_leads = sorted(
            visible,
            key=lambda o: o.get("last_seen") or o.get("first_touch_at") or "",
            reverse=True,
        )[:10]
        summary["leads"] = {
            "open": open_count,
            "recent": [{
                "id": o.get("id"),
                "client_name": o.get("client_name"),
                "source": o.get("source"),
                "last_seen": o.get("last_seen") or o.get("first_touch_at"),
            } for o in recent_leads],
        }
    # For role 'user', the 'leads' key is intentionally absent and financials is
    # null — money and pipeline never leak to field crew.
    return summary


def _cost_breakdown(db: dict, job: dict) -> dict:
    """Per-job cost bucketed into categories. A7+A8."""
    budget = job.get("budget") or {}
    loaded_rate = float(budget.get("loaded_labor_rate") or 0)
    burden = 1.45

    labor_cost = 0.0
    for log in job.get("production_logs") or []:
        for htype, hrs in (log.get("hours_by_type") or {}).items():
            labor_cost += float(hrs or 0) * loaded_rate * burden

    financials = db.get("financials") or {}
    exp_map = financials.get("expenses", {})
    material_cost = 0.0
    equipment_cost = 0.0
    sub_cost = 0.0
    other_cost = 0.0
    for eid in job.get("expenses", []):
        exp = exp_map.get(eid, {})
        cat = (exp.get("category") or "other").lower()
        amt = float(exp.get("amount") or 0)
        if "material" in cat or "coating" in cat or "product" in cat:
            material_cost += amt
        elif "equipment" in cat or "spray" in cat or "rig" in cat:
            equipment_cost += amt
        elif "sub" in cat or "contractor" in cat:
            sub_cost += amt
        else:
            other_cost += amt

    co_added = sum(
        float(co.get("price") or 0)
        for co in job.get("change_orders") or []
        if co.get("approved_at")
    )
    contract = float(budget.get("contract_value") or 0) + co_added
    total_cost = labor_cost + material_cost + equipment_cost + sub_cost + other_cost
    profit = contract - total_cost
    margin = round(profit / contract * 100, 2) if contract > 0 else 0.0

    return {
        "burdened_labor": round(labor_cost, 2),
        "material": round(material_cost, 2),
        "equipment": round(equipment_cost, 2),
        "subcontractor": round(sub_cost, 2),
        "other": round(other_cost, 2),
        "total_cost": round(total_cost, 2),
        "contract_value": round(contract, 2),
        "profit": round(profit, 2),
        "margin_pct": margin,
    }


def _weather_verdict_from_forecast(forecast: dict, profile: dict) -> dict:
    """Analyze a 12-hour forecast window against a weather profile."""
    hourly = forecast.get("hourly", {})
    temps = hourly.get("temperature_2m", [])[:12]
    rh = hourly.get("relativehumidity_2m", [])[:12]
    precip = hourly.get("precipitation_probability", [])[:12]

    flags = []
    if temps:
        if min(temps) < profile.get("temp_min", 40):
            flags.append(f"Temp too low ({min(temps):.0f}°F < {profile['temp_min']}°F min)")
        if max(temps) > profile.get("temp_max", 120):
            flags.append(f"Temp too high ({max(temps):.0f}°F > {profile['temp_max']}°F max)")
    if rh and max(rh) > profile.get("rh_max", 85):
        flags.append(f"Humidity too high ({max(rh):.0f}% > {profile['rh_max']}%)")
    cure_hrs = int(profile.get("min_cure_before_rain_hrs", 4))
    if precip and cure_hrs > 0:
        window = precip[:cure_hrs]  # never empty here (precip truthy, cure_hrs > 0)
        if window and max(window) > 40:
            flags.append(f"Rain risk within {cure_hrs}h cure window — warranty may be voided")

    verdict = "GREEN" if not flags else (
        "RED" if any(kw in f for f in flags for kw in ("too low", "too high", "warranty"))
        else "YELLOW"
    )
    return {"verdict": verdict, "reason": "; ".join(flags) if flags else "All conditions within spec",
            "flags": flags, "checked_at": datetime.now().isoformat()}


def _fetch_weather(lat: float, lon: float) -> dict:
    """Fetch 24h forecast from Open-Meteo (free, no key required)."""
    import requests
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m,relativehumidity_2m,precipitation_probability",
        "temperature_unit": "fahrenheit", "timezone": "auto", "forecast_days": 2,
    }
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def _geocode(address: str) -> tuple:
    """Return (lat, lon) for an address using Nominatim (free)."""
    import requests
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": address, "format": "json", "limit": 1},
                     headers={"User-Agent": "TruAgent/1.0"},
                     timeout=10)
    r.raise_for_status()
    data = r.json()
    if data:
        return float(data[0]["lat"]), float(data[0]["lon"])
    return None, None


def _merge_template(body: str, job: dict) -> str:
    """Replace {{token}} placeholders with job/budget data."""
    budget = job.get("budget") or {}
    warranty = job.get("warranty") or {}
    replacements = {
        "client_name": job.get("client_name", ""),
        "address": job.get("address", ""),
        "job_id": job.get("job_id", ""),
        "coating_system": budget.get("system", job.get("coating_system", "")),
        "substrate": budget.get("substrate", job.get("substrate", "")),
        "sqft": str(budget.get("sqft", "")),
        "dry_mil_spec": str(budget.get("dry_mil_target", "")),
        "contract_value": str(budget.get("contract_value", "")),
        "warranty_years": str(warranty.get("term_years", "")),
        "warranty_type": warranty.get("warranty_type", ""),
        "manufacturer": warranty.get("manufacturer", ""),
        "today": datetime.now().strftime("%Y-%m-%d"),
    }
    result = body
    for token, value in replacements.items():
        result = result.replace("{{" + token + "}}", str(value))
    return result


def _ar_aging_buckets(db: dict) -> dict:
    """Bucket unpaid invoices into 0-30/31-60/61-90/90+ days past due."""
    buckets = {"0_30": [], "31_60": [], "61_90": [], "over_90": [], "current": []}
    now = datetime.now()
    for inv_id, inv in (db.get("financials", {}).get("invoices", {})).items():
        if inv.get("status") in ("paid", "cancelled"):
            continue
        try:
            due = datetime.fromisoformat(inv.get("due_date") or inv.get("date") or now.isoformat())
        except Exception:
            continue
        days = (now - due).days
        inv_summary = {"id": inv_id, "amount": inv.get("amount"), "job_id": inv.get("job_id"),
                       "customer": inv.get("customer_name"), "days_past_due": days}
        if days <= 0:
            buckets["current"].append(inv_summary)
        elif days <= 30:
            buckets["0_30"].append(inv_summary)
        elif days <= 60:
            buckets["31_60"].append(inv_summary)
        elif days <= 90:
            buckets["61_90"].append(inv_summary)
        else:
            buckets["over_90"].append(inv_summary)
    return buckets


def _recompute_cleared(party: dict) -> bool:
    """O47: a party is 'cleared to work' when it has at least one unexpired COI,
    a W-9 on file, and (for subcontractors) a signed subcontract."""
    has_valid_coi = False
    for c in party.get("cois", []):
        try:
            if datetime.fromisoformat(c.get("expiry") or "") > datetime.now():
                has_valid_coi = True
                break
        except Exception:
            pass
    needs_subcontract = party.get("party_type") == "sub"
    party["cleared"] = bool(has_valid_coi and party.get("w9")
                            and (not needs_subcontract or party.get("subcontract")))
    return party["cleared"]


def _sds_gaps(db: dict) -> list:
    """Coating products referenced on jobs that have no SDS on file (OSHA HazCom
    gap — O50/O52). Matched case-insensitively by product name."""
    on_file = set()
    for s in (db.get("sds") or {}).values():
        prod = (s.get("product") or "").strip().lower()
        if prod:
            on_file.add(prod)
    referenced = set()
    for job in (db.get("jobs") or {}).values():
        for prod in ((job.get("budget") or {}).get("est_gallons") or {}):
            if prod:
                referenced.add(str(prod).strip().lower())
        for log in job.get("production_logs") or []:
            for prod in (log.get("gallons_by_product") or {}):
                if prod:
                    referenced.add(str(prod).strip().lower())
            if log.get("product"):
                referenced.add(str(log["product"]).strip().lower())
    return sorted(p for p in referenced if p and p not in on_file)


def _compliance_summary(db: dict) -> dict:
    """Roll up expiring/missing COIs, certs, uncleared parties, and SDS gaps.
    Each entry carries both a `party`/`employee` and a `name` alias plus the raw
    `expiry` date, so the dashboard and the AI tool can render it directly."""
    now = datetime.now()
    warn_days = 30
    expiring_cois = []
    for pid, party in (db.get("parties") or {}).items():
        for coi in party.get("cois", []):
            try:
                exp = datetime.fromisoformat(coi.get("expiry") or "")
                days = (exp - now).days
                if days <= warn_days:
                    expiring_cois.append({"party": party.get("name"), "name": party.get("name"),
                                          "party_id": pid, "carrier": coi.get("carrier"),
                                          "expiry": coi.get("expiry"), "days_until_expiry": days})
            except Exception:
                pass
    expiring_certs = []
    for eid, emp in (db.get("employees") or {}).items():
        for cert in emp.get("certs", []):
            if not cert.get("expiry"):
                continue
            try:
                exp = datetime.fromisoformat(cert["expiry"])
                days = (exp - now).days
                if days <= warn_days:
                    expiring_certs.append({"employee": emp.get("name"), "name": emp.get("name"),
                                           "employee_id": eid, "cert_type": cert.get("cert_type"),
                                           "expiry": cert.get("expiry"), "days_until_expiry": days})
            except Exception:
                pass
    uncleared = [
        {"party": p.get("name"), "name": p.get("name"), "id": pid, "type": p.get("party_type")}
        for pid, p in (db.get("parties") or {}).items()
        if not p.get("cleared")
    ]
    return {"expiring_cois": expiring_cois, "expiring_certs": expiring_certs,
            "uncleared_parties": uncleared, "sds_gaps": _sds_gaps(db),
            "checked_at": datetime.now().isoformat()}


def _send_email_or_log(db: dict, to: str, subject: str, body: str, sent_by: str) -> str:
    """Best-effort email send; returns 'sent' or a 'queued: …' explanation.
    Unsendable emails are parked in the outbox, never dropped."""
    result = _email_dispatch(db, {"to": to, "subject": subject, "body": body,
                                  "sent_by": sent_by, "sent_at": datetime.now().isoformat()})
    if result["status"] == "ok":
        return "sent"
    return f"queued: {result['message']}"


# OpenAI tool/function specs. Financial tools are exposed only to manager+.
_TOOL_DEFS = {
    "list_jobs": {"type": "function", "function": {
        "name": "list_jobs",
        "description": "List all jobs and leads with id, name, customer, status and workflow stage. Use to answer 'what jobs do we have' or to find a job_id.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    "get_job": {"type": "function", "function": {
        "name": "get_job",
        "description": "Get the full detail of one job (all fields and notes) by its job_id.",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string", "description": "The job's id"}},
            "required": ["job_id"], "additionalProperties": False}}},
    "update_job_status": {"type": "function", "function": {
        "name": "update_job_status",
        "description": "Update a job's status and/or workflow stage. This automatically syncs the change back to the Roofr CRM when configured.",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string"},
            "status": {"type": "string", "description": "New status, e.g. Pending, In Progress, Complete"},
            "workflow_stage": {"type": "string", "description": "Optional pipeline stage: Lead, Quote, Approved, In Progress, Complete"}},
            "required": ["job_id"], "additionalProperties": False}}},
    "add_job_note": {"type": "function", "function": {
        "name": "add_job_note",
        "description": "Add a note to a job. Automatically syncs to Roofr when configured.",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string"},
            "note": {"type": "string"}},
            "required": ["job_id", "note"], "additionalProperties": False}}},
    "list_documents": {"type": "function", "function": {
        "name": "list_documents",
        "description": "List documents on file (id, filename, description).",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    "send_email": {"type": "function", "function": {
        "name": "send_email",
        "description": "Send an email (via the configured email integration), optionally attaching documents by id.",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "document_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional document ids to attach"}},
            "required": ["to", "subject", "body"], "additionalProperties": False}}},
    "send_sms": {"type": "function", "function": {
        "name": "send_sms",
        "description": "Send a text message (via the configured SMS integration). Phone in E.164 format, e.g. +15551234567.",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string"},
            "message": {"type": "string"}},
            "required": ["to", "message"], "additionalProperties": False}}},
    "get_job_financials": {"type": "function", "function": {
        "name": "get_job_financials",
        "description": "Get revenue, costs, profit and margin for one job (manager/admin only).",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string"}},
            "required": ["job_id"], "additionalProperties": False}}},
    "company_financials_summary": {"type": "function", "function": {
        "name": "company_financials_summary",
        "description": "Get company-wide totals: revenue, costs, profit and margin across all jobs (manager/admin only).",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    "get_production_data": {"type": "function", "function": {
        "name": "get_production_data",
        "description": "Get production summary for a job: gallons applied vs estimated, % complete, QA flags, coat status, punch items.",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string"}},
            "required": ["job_id"], "additionalProperties": False}}},
    "get_overbudget_jobs": {"type": "function", "function": {
        "name": "get_overbudget_jobs",
        "description": "List jobs where applied gallons exceed estimated, or hours exceed budget, or margin has fallen.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    "get_compliance_summary": {"type": "function", "function": {
        "name": "get_compliance_summary",
        "description": "Get a summary of expiring COIs, lapsing employee certs, and uncleared subcontractors (manager/admin only).",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    "get_pipeline_summary": {"type": "function", "function": {
        "name": "get_pipeline_summary",
        "description": "Get the sales pipeline: open opportunities by stage, with values and rep assignment (manager/admin only).",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    "get_job_report": {"type": "function", "function": {
        "name": "get_job_report",
        "description": "Generate a natural-language summary report for one job: stage, gallons vs est, mil compliance, open issues, next action. Financial details shown to manager+ only.",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string"}},
            "required": ["job_id"], "additionalProperties": False}}},
    "advance_pipeline_stage": {"type": "function", "function": {
        "name": "advance_pipeline_stage",
        "description": "Advance an opportunity or job to the next pipeline stage. Syncs to Roofr when configured.",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string"},
            "stage": {"type": "string", "description": "Target stage: New Lead, Site Survey, Measured/Cores, Estimating, Proposal, Negotiation, Won, Lost"}},
            "required": ["job_id", "stage"], "additionalProperties": False}}},
    "search_docs": {"type": "function", "function": {
        "name": "search_docs",
        "description": "Search uploaded documents (specs, SDS, warranties, contracts) by keyword and return relevant excerpts with citations.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query, e.g. 'inter-coat window silicone' or 'volume solids Gaco'"}},
            "required": ["query"], "additionalProperties": False}}},
    "get_weather_verdict": {"type": "function", "function": {
        "name": "get_weather_verdict",
        "description": "Check today's weather for a job address vs the coating system's application limits. Returns GREEN/YELLOW/RED.",
        "parameters": {"type": "object", "properties": {
            "job_id": {"type": "string"}},
            "required": ["job_id"], "additionalProperties": False}}},
    "get_anomalies": {"type": "function", "function": {
        "name": "get_anomalies",
        "description": "Detect jobs with budget overruns, stalled production, past-due invoices, or approved jobs not yet started.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
}

_COMMON_TOOLS = ["list_jobs", "get_job", "update_job_status", "add_job_note",
                 "list_documents", "send_email", "send_sms",
                 "get_production_data", "get_overbudget_jobs", "get_job_report",
                 "search_docs", "get_weather_verdict", "get_anomalies"]
_FINANCIAL_TOOLS = ["get_job_financials", "company_financials_summary",
                    "get_compliance_summary", "get_pipeline_summary",
                    "advance_pipeline_stage"]


def tools_for_role(role: str) -> list:
    names = list(_COMMON_TOOLS)
    if role in ("manager", "super_admin"):
        names += _FINANCIAL_TOOLS
    return [_TOOL_DEFS[n] for n in names]


def execute_agent_tool(name: str, args: dict, current_user: dict, db: dict) -> dict:
    """Dispatch one tool call. Enforces role gating server-side (never trust the
    model alone): field crew can never reach financial data."""
    role = current_user.get("role", "user")
    email = current_user["email"]
    args = args or {}

    if name in _FINANCIAL_TOOLS and role not in ("manager", "super_admin"):
        return {"status": "error", "message": "Financial data is restricted to managers and admins."}

    if name == "list_jobs":
        return {"status": "ok", "jobs": [_compact_job(j) for j in db["jobs"].values()]}
    if name == "get_job":
        job = db["jobs"].get(args.get("job_id"))
        if not job:
            return {"status": "error", "message": "Job not found"}
        if role == "user":  # strip all financials (budget money, invoices, expenses…) for field crew
            job = _strip_job_financials(job)
        return {"status": "ok", "job": job}
    if name == "update_job_status":
        return _op_update_job_status(db, args.get("job_id"), args.get("status"),
                                     args.get("workflow_stage"), email)
    if name == "add_job_note":
        return _op_add_job_note(db, args.get("job_id"), args.get("note"), email)
    if name == "list_documents":
        return {"status": "ok", "documents": [
            {"id": d.get("id"), "filename": d.get("filename"), "description": d.get("description")}
            for d in db["documents"].values()]}
    if name == "send_email":
        return _op_send_email(db, args.get("to"), args.get("subject", ""),
                              args.get("body", ""), args.get("html"),
                              args.get("document_ids"), email)
    if name == "send_sms":
        return _op_send_sms(db, args.get("to"), args.get("message", ""), email)
    if name == "get_job_financials":
        return _job_financials(db, args.get("job_id"))
    if name == "company_financials_summary":
        return _company_financials_summary(db)

    # ── New tools ──────────────────────────────────────────────────────────────
    if name == "get_production_data":
        job = db["jobs"].get(args.get("job_id"))
        if not job:
            return {"status": "error", "message": "Job not found"}
        applied = _applied_gallons_by_product(job)
        est = (job.get("budget") or {}).get("est_gallons") or {}
        pct = _production_pct_complete(job)
        qa_flags = [r for r in job.get("qa_readings", []) if r.get("flag")]
        punch_open = [p for p in job.get("punch_items", []) if p.get("status") != "done"]
        return {"status": "ok", "job_id": args.get("job_id"),
                "pct_complete": pct, "applied_gallons": applied,
                "est_gallons": est, "qa_flags": qa_flags[:5], "open_punch_items": len(punch_open),
                "log_count": len(job.get("production_logs", []))}

    if name == "get_overbudget_jobs":
        results = []
        for jid, job in db["jobs"].items():
            budget = job.get("budget") or {}
            est = budget.get("est_gallons") or {}
            applied = _applied_gallons_by_product(job)
            for prod, est_gals in est.items():
                app_gals = applied.get(prod, 0)
                if app_gals > float(est_gals or 0) * 1.0 and float(est_gals or 0) > 0:
                    results.append({"job_id": jid, "client": job.get("client_name"),
                                    "product": prod, "applied": app_gals,
                                    "estimated": est_gals, "overrun_pct": round((app_gals - float(est_gals)) / float(est_gals) * 100, 1)})
        return {"status": "ok", "overbudget_jobs": results}

    if name == "get_compliance_summary":
        if role not in ("manager", "super_admin"):
            return {"status": "error", "message": "Manager access required"}
        return {"status": "ok", **_compliance_summary(db)}

    if name == "get_pipeline_summary":
        if role not in ("manager", "super_admin"):
            return {"status": "error", "message": "Manager access required"}
        stages: Dict[str, list] = {}
        for oid, opp in db.get("opportunities", {}).items():
            s = opp.get("stage", "New Lead")
            stages.setdefault(s, []).append({
                "id": oid, "client": opp.get("client_name"),
                "address": opp.get("address"), "value": opp.get("contract_value"),
                "rep": opp.get("rep"),
            })
        return {"status": "ok", "pipeline": stages,
                "total_opportunities": len(db.get("opportunities", {}))}

    if name == "get_job_report":
        job = db["jobs"].get(args.get("job_id"))
        if not job:
            return {"status": "error", "message": "Job not found"}
        budget = job.get("budget") or {}
        applied = _applied_gallons_by_product(job)
        pct = _production_pct_complete(job)
        qa_flags = [r for r in job.get("qa_readings", []) if r.get("flag")]
        punch_open = [p for p in job.get("punch_items", []) if p.get("status") != "done"]
        report = {
            "job_id": args.get("job_id"), "client": job.get("client_name"),
            "address": job.get("address"), "stage": job.get("workflow_stage"),
            "status": job.get("status"), "pct_complete": pct,
            "applied_gallons": applied, "est_gallons": budget.get("est_gallons"),
            "system": budget.get("system"), "substrate": budget.get("substrate"),
            "open_punch_items": len(punch_open), "qa_flags": len(qa_flags),
            "warranty_status": (job.get("warranty") or {}).get("registered"),
        }
        if role in ("manager", "super_admin"):
            cb = _cost_breakdown(db, job)
            report["financials"] = cb
        return {"status": "ok", "report": report}

    if name == "advance_pipeline_stage":
        if role not in ("manager", "super_admin"):
            return {"status": "error", "message": "Manager access required"}
        jid = args.get("job_id")
        stage = args.get("stage")
        job = db["jobs"].get(jid)
        opp = db.get("opportunities", {}).get(jid)
        if job:
            job["workflow_stage"] = stage
            timeline = job.setdefault("timeline", [])
            timeline.append({"event": "stage_changed", "stage": stage,
                             "by": email, "at": datetime.now().isoformat()})
            save_db(db)
            sync = _sync_to_roofr({"job_id": jid, "workflow_stage": stage, "updated_by": email,
                                    "updated_at": datetime.now().isoformat()})
            return {"status": "ok", "job_id": jid, "new_stage": stage, "roofr_sync": sync}
        if opp:
            opp["stage"] = stage
            opp.setdefault("timeline", []).append({"event": "stage_changed", "stage": stage,
                                                   "by": email, "at": datetime.now().isoformat()})
            save_db(db)
            return {"status": "ok", "opportunity_id": jid, "new_stage": stage}
        return {"status": "error", "message": f"No job or opportunity found for id {jid!r}"}

    if name == "search_docs":
        query = (args.get("query") or "").lower()
        results = []
        for doc_id, chunks in db.get("doc_chunks", {}).items():
            doc = db["documents"].get(doc_id, {})
            for chunk in chunks:
                text = chunk.get("text", "")
                if any(word in text.lower() for word in query.split()):
                    results.append({"doc_id": doc_id, "filename": doc.get("filename"),
                                    "excerpt": text[:400], "page": chunk.get("page")})
                    if len(results) >= 5:
                        break
            if len(results) >= 5:
                break
        return {"status": "ok", "results": results, "query": query,
                "note": "Upload documents and use /documents/{id}/index to enable search"}

    if name == "get_weather_verdict":
        job = db["jobs"].get(args.get("job_id"))
        if not job:
            return {"status": "error", "message": "Job not found"}
        weather_status = job.get("weather_status") or {}
        return {"status": "ok", "job_id": args.get("job_id"),
                "address": job.get("address"),
                "system": (job.get("budget") or {}).get("system"),
                "verdict": weather_status.get("verdict", "UNKNOWN"),
                "reason": weather_status.get("reason", "No weather check run yet"),
                "checked_at": weather_status.get("checked_at"),
                "tip": "POST /job/{job_id}/weather-check to refresh"}

    if name == "get_anomalies":
        flags = []
        now = datetime.now()
        for jid, job in db["jobs"].items():
            budget = job.get("budget") or {}
            applied = _applied_gallons_by_product(job)
            est = budget.get("est_gallons") or {}
            # Gallons overrun
            for prod, est_gals in est.items():
                app = applied.get(prod, 0)
                if app > float(est_gals or 0) * 1.05:
                    flags.append({"type": "gallons_overrun", "job_id": jid,
                                  "client": job.get("client_name"), "product": prod})
            # Stalled (no log in 5 days, if approved/in-progress)
            logs = job.get("production_logs") or []
            if logs and job.get("status") in ("In Progress", "Approved"):
                last_log = max(logs, key=lambda l: l.get("date", ""), default=None)
                if last_log:
                    try:
                        d = datetime.fromisoformat(last_log["date"])
                        if (now - d).days > 5:
                            flags.append({"type": "stalled", "job_id": jid,
                                          "client": job.get("client_name"),
                                          "days_since_log": (now - d).days})
                    except Exception:
                        pass
            # Approved but no production start
            if job.get("workflow_stage") == "Approved" and not logs:
                flags.append({"type": "approved_no_start", "job_id": jid,
                               "client": job.get("client_name")})
        return {"status": "ok", "anomaly_flags": flags, "count": len(flags)}

    return {"status": "error", "message": f"Unknown tool: {name}"}


def _build_chat_system_prompt(db: dict, user_email: str, user_role: str) -> str:
    """Lean, step-scoped system prompt: a compact job summary inline (not the
    whole DB) plus tools for details and actions. Keeps token use bounded."""
    jobs = list(db.get("jobs", {}).values())
    compact = [_compact_job(j) for j in jobs[:40]]
    job_summary = json.dumps(compact, indent=2) if compact else "(no jobs synced yet)"
    more = (f"\n(Showing 40 of {len(jobs)} jobs — call list_jobs for the rest.)"
            if len(jobs) > 40 else "")
    doc_count = len(db.get("documents", {}))

    base = f"""You are TruAgent, the AI operations assistant for Truline Roofing, a commercial roof coating contractor.
Today's date: {datetime.now().strftime('%Y-%m-%d')}.

You ANSWER questions and TAKE ACTIONS using the tools provided. Do not merely describe what you would do — call the matching tool, then confirm the outcome in plain language. Updating a job status or adding a note automatically syncs to the Roofr CRM when configured; report the sync result to the user.

Current jobs (summary):
{job_summary}{more}

Documents on file: {doc_count} (call list_documents for details).

Guidelines:
- Be concise and practical; your users are busy office staff and field crews.
- Call get_job for full detail (notes, all fields) before answering specifics about one job.
- Confirm the job_id you are acting on. If it is ambiguous which job is meant, ask first.
"""
    if user_role == "user":
        base += """
ROLE: Field Crew / Sales (limited access). You MUST NOT reveal or discuss financial information (invoices, costs, profit, margins, expenses). You have no financial tools. If asked about money, reply: "Financial data is restricted — please ask a manager." Focus on job status, notes, scheduling, and customer communication.
"""
    else:
        role_name = ("Super Admin (full access)" if user_role == "super_admin"
                     else "Manager (full access incl. financials)")
        base += f"""
ROLE: {role_name}. You have financial tools (get_job_financials, company_financials_summary). Profit = revenue − costs; margin = profit / revenue × 100.
"""
    return base + f"\nCurrent user: {user_email}\n"


def _create_completion(client, messages: list, tools: Optional[list] = None,
                       max_completion_tokens: int = 2000):
    """Call chat.completions with the configured model, falling back once to a
    known-good model if the primary id is rejected (unknown/unavailable). This
    keeps the AI from 500-ing on every message just because OPENAI_MODEL is bad."""
    kwargs: Dict[str, Any] = {"messages": messages,
                              "max_completion_tokens": max_completion_tokens}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    try:
        return client.chat.completions.create(model=OPENAI_MODEL, **kwargs)
    except Exception as e:
        msg = str(e).lower()
        model_problem = any(s in msg for s in
                            ("model", "404", "not found", "does not exist", "unsupported"))
        if (OPENAI_FALLBACK_MODEL and OPENAI_FALLBACK_MODEL != OPENAI_MODEL
                and model_problem):
            return client.chat.completions.create(model=OPENAI_FALLBACK_MODEL, **kwargs)
        raise


def _run_agent_loop(client, messages: list, tools: list, current_user: dict,
                    db: dict, max_hops: int = 5) -> str:
    """Run the chat-completions tool-calling loop until the model returns a
    final text answer or we hit the hop cap (then force a text answer)."""
    for _ in range(max_hops):
        resp = _create_completion(client, messages, tools=tools,
                                  max_completion_tokens=2000)
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return msg.content or ""
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name,
                                         "arguments": tc.function.arguments}}
                           for tc in tool_calls],
        })
        for tc in tool_calls:
            try:
                call_args = json.loads(tc.function.arguments or "{}")
            except Exception:
                call_args = {}
            result = execute_agent_tool(tc.function.name, call_args, current_user, db)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, default=str)})
    # Hop cap reached — force a final natural-language answer with tools off.
    resp = _create_completion(client, messages, tools=None,
                              max_completion_tokens=1000)
    return (resp.choices[0].message.content
            or "I ran into trouble completing that — please try rephrasing.")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("static/index.html")


@app.get("/dashboard/summary")
async def dashboard_summary(current_user: dict = Depends(get_current_user)):
    """Cross-app dashboard (step 9): one role-gated rollup of jobs, field
    activity, leads, and financials for the standalone /static/dashboard.html
    card view. Role 'user' (field crew) gets no leads key and financials=null;
    manager+ get leads (Truline-only: scope != 'public') and financials."""
    db = load_db()
    role = current_user.get("role") or "user"
    return _dashboard_summary(db, role)


# In-process brute-force throttle for /login. Keyed by client IP, counts failed
# attempts in a rolling window and returns 429 past the threshold. In-memory
# (resets on restart) and per-process, which is sufficient for this single-worker
# internal app; a shared store (e.g. Redis) would be the cross-process upgrade.
_LOGIN_ATTEMPTS: Dict[str, List[float]] = {}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECS = 60

def _client_ip(request: Request) -> str:
    # Behind Railway's proxy the socket peer is the proxy, so prefer the first
    # X-Forwarded-For hop (the real caller) for per-client throttling instead of
    # lumping every user under one proxy IP and risking a global lockout. XFF is
    # client-settable, so this is a brute-force speed-bump, not an authz control.
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _login_rate_limit_check(ip: str):
    now = time.time()
    recent = [t for t in _LOGIN_ATTEMPTS.get(ip, []) if now - t < _LOGIN_WINDOW_SECS]
    _LOGIN_ATTEMPTS[ip] = recent
    if len(recent) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Wait a minute and try again.",
        )

def _login_record_failure(ip: str):
    _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.time())

def _login_clear(ip: str):
    _LOGIN_ATTEMPTS.pop(ip, None)


@app.post("/login")
async def login(data: Login, request: Request):
    ip = _client_ip(request)
    _login_rate_limit_check(ip)
    db = load_db()
    user = db["users"].get(data.email)
    
    if not user:
        _login_record_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    if user["password_hash"] != hashed:
        _login_record_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    _login_clear(ip)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"], "role": user.get("role", "user")},
        expires_delta=access_token_expires
    )
    
    return {
        "status": "ok",
        "token": access_token,
        "role": user.get("role", "user"),
        "is_admin": user.get("role") == "super_admin"
    }

@app.post("/job")
async def add_job(job: Job, current_user: dict = Depends(get_current_user)):
    db = load_db()
    db["jobs"][job.job_id] = job.dict()
    save_db(db)
    return {"msg": f"Job {job.job_id} saved"}

@app.get("/job/{job_id}")
async def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if current_user.get("role") == "user":
        return _strip_job_financials(job)
    return job

@app.get("/jobs")
async def get_all_jobs(current_user: dict = Depends(get_current_user)):
    db = load_db()
    if current_user.get("role") == "user":
        return {"jobs": {jid: _strip_job_financials(j) for jid, j in db["jobs"].items()}}
    return {"jobs": db["jobs"]}

@app.get("/zapier/webhook")
async def zapier_webhook_verify():
    """Zapier GET verification check"""
    return {"status": "ok", "message": "TruAgent webhook ready"}

@app.post("/zapier/webhook")
async def zapier_webhook(request: Request):
    # Zapier/Roofr can deliver the payload in several shapes depending on how the
    # Zap is configured: a plain JSON object (ideal), a JSON array wrapping one
    # object ("Wrap Request In Array"), a double-encoded JSON string, or
    # form-encoded fields. Normalize all of them to one dict so the webhook never
    # hard-fails on benign wrapping.
    try:
        payload = await request.json()
    except Exception:
        try:
            payload = dict(await request.form())
        except Exception:
            payload = {}

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    if isinstance(payload, list):
        payload = next((p for p in payload if isinstance(p, dict)), {})
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Webhook body must be a JSON object")

    if payload.get("secret") != ZAPIER_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    # Drop the secret, ignore blanks, and flatten a nested "data" object if present.
    fields = {k: v for k, v in payload.items()
              if k not in ("secret", "data") and v not in (None, "")}
    nested = payload.get("data")
    if isinstance(nested, dict):
        fields.update({k: v for k, v in nested.items() if v not in (None, "")})

    # Whitelist (step 7b): this is the broadest-write, weakest door, so it may
    # only set a fixed set of safe operational fields. Anything financial
    # (budget / contract_value / financials / invoices / expenses / margin / cost)
    # must NEVER come in through here — those belong to the QuickBooks / Alpha
    # doors. Apply the whitelist AFTER the nested-data flatten so a hostile or
    # mis-mapped Zap cannot smuggle a money field in via `data`.
    _ZAPIER_ALLOWED = {
        "job_id", "client_name", "address", "status", "workflow_stage",
        "phone", "email", "customer_phone", "customer_email", "assignee",
        "job_value", "lead_source", "notes", "roofr_job_id",
    }
    fields = {k: v for k, v in fields.items() if k in _ZAPIER_ALLOWED}

    job_id = fields.get("job_id")
    if not job_id:
        # No id to key the job on (e.g. an empty test record). Accept the request
        # so Zapier reports success, but store nothing.
        return {"status": "ok", "message": "Webhook received (no job_id, nothing stored)"}

    db = load_db()
    if job_id in db["jobs"]:
        db["jobs"][job_id].update(fields)
    else:
        db["jobs"][job_id] = fields
    save_db(db)
    return {"status": "ok", "message": "Webhook received"}

@app.post("/roofr/update")
async def update_roofr(update: RoofrUpdate, current_user: dict = Depends(get_current_user)):
    """Update a job from the UI/agent: always save locally, then push to Roofr
    best-effort. Uses the same helpers as the AI agent so behaviour is identical.
    Does NOT 503 when the outbound Roofr webhook is unconfigured — the local save
    is the source of truth and must never be lost; the sync is reported as
    'not configured' instead."""
    db = load_db()

    if update.job_id not in db["jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")

    sync = "not configured"
    changed = False

    if update.status or update.workflow_stage:
        r = _op_update_job_status(db, update.job_id, update.status,
                                  update.workflow_stage, current_user["email"])
        sync = r.get("roofr_sync", sync)
        changed = True

    if update.notes:
        r = _op_add_job_note(db, update.job_id, update.notes, current_user["email"])
        sync = r.get("roofr_sync", sync)
        changed = True

    if update.data:
        db["jobs"][update.job_id].update(update.data)
        save_db(db)
        changed = True

    if not changed:
        return {"status": "ok", "job_id": update.job_id,
                "message": "Nothing to update", "roofr_sync": sync}

    status = "ok" if sync in ("synced", "not configured") else "partial"
    return {"status": status, "job_id": update.job_id, "roofr_sync": sync,
            "message": f"Job {update.job_id} updated (Roofr sync: {sync})"}

@app.post("/quickbooks/webhook")
async def quickbooks_webhook(webhook: QuickBooksWebhook):
    """Receive financial data (invoices/expenses) from QuickBooks via Zapier"""
    
    if webhook.secret != QUICKBOOKS_SECRET:
        raise HTTPException(status_code=403, detail="Invalid QuickBooks webhook secret")
    
    db = load_db()
    
    if "financials" not in db:
        db["financials"] = {"invoices": {}, "expenses": {}}
    
    if webhook.transaction_type == "invoice":
        if "invoices" not in db["financials"]:
            db["financials"]["invoices"] = {}
        
        invoice_data = {
            "transaction_id": webhook.transaction_id,
            "job_id": webhook.job_id,
            "amount": webhook.amount,
            "date": webhook.date,
            "description": webhook.description,
            "customer_name": webhook.customer_name,
            "status": webhook.status or "pending",
            "created_at": datetime.now().isoformat()
        }
        
        if webhook.data:
            invoice_data.update(webhook.data)
        
        db["financials"]["invoices"][webhook.transaction_id] = invoice_data

        # Resolve the QB-provided job id against internal keys AND any stored
        # roofr_job_id/qb_job_id cross-ref, so a real invoice attaches to the suite
        # job ('alpha-<uuid>') instead of landing unlinked (QB sends Roofr's/QB's
        # own job number, which never equals the internal key).
        linked_id = _resolve_job_id(db, webhook.job_id)
        if linked_id:
            invoice_data["job_id"] = linked_id
            linked_job = db["jobs"][linked_id]
            linked_job.setdefault("invoices", [])
            if webhook.transaction_id not in linked_job["invoices"]:
                linked_job["invoices"].append(webhook.transaction_id)
    
    elif webhook.transaction_type == "expense":
        if "expenses" not in db["financials"]:
            db["financials"]["expenses"] = {}
        
        expense_data = {
            "transaction_id": webhook.transaction_id,
            "job_id": webhook.job_id,
            "amount": webhook.amount,
            "date": webhook.date,
            "description": webhook.description,
            "vendor_name": webhook.vendor_name,
            "category": webhook.category,
            "created_at": datetime.now().isoformat()
        }
        
        if webhook.data:
            expense_data.update(webhook.data)
        
        db["financials"]["expenses"][webhook.transaction_id] = expense_data

        # Same cross-ref resolution as invoices: attach real expenses to the suite
        # job even though QB sends a job number that isn't the internal key.
        linked_id = _resolve_job_id(db, webhook.job_id)
        if linked_id:
            expense_data["job_id"] = linked_id
            linked_job = db["jobs"][linked_id]
            linked_job.setdefault("expenses", [])
            if webhook.transaction_id not in linked_job["expenses"]:
                linked_job["expenses"].append(webhook.transaction_id)
    
    else:
        raise HTTPException(status_code=400, detail="Invalid transaction_type. Must be 'invoice' or 'expense'")
    
    save_db(db)
    
    return {
        "status": "ok",
        "message": f"{webhook.transaction_type.capitalize()} {webhook.transaction_id} received and linked to job {webhook.job_id}" if webhook.job_id else f"{webhook.transaction_type.capitalize()} {webhook.transaction_id} received"
    }

@app.get("/job/{job_id}/financials")
async def get_job_financials(job_id: str, current_user: dict = Depends(get_manager_or_above)):
    """Get financial data (invoices and expenses) for a specific job - Manager/Admin only"""
    
    db = load_db()
    
    if job_id not in db["jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = db["jobs"][job_id]
    financials = db.get("financials", {"invoices": {}, "expenses": {}})
    
    job_invoices = []
    for invoice_id in job.get("invoices", []):
        if invoice_id in financials.get("invoices", {}):
            job_invoices.append(financials["invoices"][invoice_id])
    
    job_expenses = []
    for expense_id in job.get("expenses", []):
        if expense_id in financials.get("expenses", {}):
            job_expenses.append(financials["expenses"][expense_id])
    
    total_revenue = sum(inv["amount"] for inv in job_invoices if inv.get("status") != "cancelled")
    total_costs = sum(exp["amount"] for exp in job_expenses)
    profit = total_revenue - total_costs
    margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
    
    return {
        "job_id": job_id,
        "client_name": job.get("client_name"),
        "invoices": job_invoices,
        "expenses": job_expenses,
        "summary": {
            "total_revenue": total_revenue,
            "total_costs": total_costs,
            "profit": profit,
            "margin_percent": round(margin, 2)
        }
    }

@app.post("/send-email")
async def send_email(email: EmailMessage, current_user: dict = Depends(get_current_user)):
    """Send email via Zapier webhook integration (supports Gmail, SendGrid, etc.).
    When the webhook is not configured (or the send fails), the email is queued
    in the outbox instead of being dropped."""
    db = load_db()
    result = _op_send_email(db, email.to, email.subject, email.body,
                            email.html, email.document_ids, current_user["email"])
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return {**result, "timestamp": datetime.now().isoformat()}

@app.post("/send-sms")
async def send_sms(sms: SMSMessage, current_user: dict = Depends(get_current_user)):
    """Send SMS via Zapier webhook integration (supports Twilio, etc.).
    When the webhook is not configured (or the send fails), the text is queued
    in the sms_outbox instead of being dropped."""
    db = load_db()
    result = _op_send_sms(db, sms.to, sms.message, current_user["email"])
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return {**result, "timestamp": datetime.now().isoformat()}

@app.get("/outbox")
async def get_outbox(current_user: dict = Depends(get_manager_or_above)):
    """Queued/sent outbound emails (parked when the email Zap is missing)."""
    db = load_db()
    entries = []
    for e in db.get("outbox", []):
        p = e.get("payload", {})
        entries.append({
            "id": e.get("id"), "status": e.get("status"),
            "to": p.get("to"), "subject": p.get("subject"),
            "queued_at": e.get("queued_at"), "queued_reason": e.get("queued_reason"),
            "attempts": e.get("attempts", 0), "last_error": e.get("last_error"),
            "sent_at": e.get("sent_at"),
        })
    return {"status": "ok", "outbox": entries,
            "email_webhook_configured": bool(EMAIL_WEBHOOK_URL)}


@app.post("/outbox/flush")
async def flush_outbox(current_user: dict = Depends(get_manager_or_above)):
    """Attempt delivery of every queued outbox email now."""
    return {"status": "ok", "result": _flush_outbox_once()}


def _flush_outbox_once() -> str:
    if not EMAIL_WEBHOOK_URL:
        return "email webhook not configured — outbox left untouched"
    db = load_db()
    sent = failed = 0
    import requests
    for entry in db.get("outbox", []):
        if entry.get("status") != "queued":
            continue
        try:
            requests.post(EMAIL_WEBHOOK_URL, json=entry["payload"], timeout=10).raise_for_status()
            entry["status"] = "sent"
            entry["sent_at"] = datetime.now().isoformat()
            sent += 1
        except Exception as e:
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["last_error"] = str(e)
            if entry["attempts"] >= 20:
                entry["status"] = "dead"
            failed += 1
    save_db(db)
    return f"outbox flush: {sent} sent, {failed} failed"


@app.get("/sms-outbox")
async def get_sms_outbox(current_user: dict = Depends(get_manager_or_above)):
    """Queued/sent outbound texts (parked when the SMS Zap is missing or a send
    fails). Mirrors GET /outbox."""
    db = load_db()
    entries = []
    for e in db.get("sms_outbox", []):
        p = e.get("payload", {})
        entries.append({
            "id": e.get("id"), "status": e.get("status"),
            "to": p.get("to"), "message": p.get("message"),
            "queued_at": e.get("queued_at"), "queued_reason": e.get("queued_reason"),
            "attempts": e.get("attempts", 0), "last_error": e.get("last_error"),
            "sent_at": e.get("sent_at"),
        })
    return {"status": "ok", "sms_outbox": entries,
            "sms_webhook_configured": bool(SMS_WEBHOOK_URL)}


@app.post("/sms-outbox/flush")
async def flush_sms_outbox(current_user: dict = Depends(get_manager_or_above)):
    """Attempt delivery of every queued SMS now."""
    return {"status": "ok", "result": _flush_sms_once()}


def _flush_sms_once() -> str:
    if not SMS_WEBHOOK_URL:
        return "sms webhook not configured — sms outbox left untouched"
    db = load_db()
    sent = failed = 0
    import requests
    for entry in db.get("sms_outbox", []):
        if entry.get("status") != "queued":
            continue
        try:
            requests.post(SMS_WEBHOOK_URL, json=entry["payload"], timeout=10).raise_for_status()
            entry["status"] = "sent"
            entry["sent_at"] = datetime.now().isoformat()
            sent += 1
        except Exception as e:
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["last_error"] = str(e)
            if entry["attempts"] >= 20:
                entry["status"] = "dead"
            failed += 1
    save_db(db)
    return f"sms outbox flush: {sent} sent, {failed} failed"


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    description: str = Form(""),
    current_user: dict = Depends(get_current_user)
):
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)

    db = load_db()
    # Monotonic id based on the highest existing numeric id, so deleting a
    # document never causes the next upload to collide with / overwrite another.
    existing_ids = [int(k) for k in db["documents"].keys() if str(k).isdigit()]
    doc_id = str((max(existing_ids) + 1) if existing_ids else 1)

    # Sanitize the filename: strip any path components (block path traversal),
    # fall back to a default, and prefix with the doc_id so same-named uploads
    # don't overwrite each other on disk.
    safe_name = os.path.basename(file.filename or "").strip() or "upload"
    file_content = await file.read()
    file_path = os.path.join(DOCUMENTS_DIR, f"{doc_id}_{safe_name}")

    with open(file_path, "wb") as f:
        f.write(file_content)

    db["documents"][doc_id] = {
        "id": doc_id,
        "filename": safe_name,
        "filepath": file_path,
        "description": description,
        "uploaded_by": current_user["email"],
        "uploaded_at": datetime.now().isoformat()
    }
    save_db(db)
    
    return {"status": "ok", "doc_id": doc_id, "filename": safe_name}

@app.get("/documents")
async def get_documents(current_user: dict = Depends(get_current_user)):
    db = load_db()
    return {"documents": db["documents"]}

@app.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    db = load_db()
    doc = db["documents"].get(doc_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return FileResponse(doc["filepath"], filename=doc["filename"])

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, current_user: dict = Depends(get_admin_user)):
    db = load_db()
    doc = db["documents"].get(doc_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if os.path.exists(doc["filepath"]):
        os.remove(doc["filepath"])
    
    del db["documents"][doc_id]
    save_db(db)
    
    return {"status": "ok", "message": "Document deleted"}

@app.post("/ai/action")
async def execute_ai_action(action: AIAction, current_user: dict = Depends(get_current_user)):
    db = load_db()
    
    if action.action == "update_job_status":
        job_id = action.parameters.get("job_id")
        new_status = action.parameters.get("status")
        workflow_stage = action.parameters.get("workflow_stage")
        
        if job_id in db["jobs"]:
            db["jobs"][job_id]["status"] = new_status
            if workflow_stage:
                db["jobs"][job_id]["workflow_stage"] = workflow_stage
            save_db(db)
            
            sync_status = "not configured"
            if ROOFR_WEBHOOK_URL:
                try:
                    import requests
                    payload = {
                        "job_id": job_id,
                        "status": new_status,
                        "workflow_stage": workflow_stage,
                        "client_name": db["jobs"][job_id].get("client_name"),
                        "address": db["jobs"][job_id].get("address"),
                        "updated_by": current_user["email"],
                        "updated_at": datetime.now().isoformat()
                    }
                    response = requests.post(ROOFR_WEBHOOK_URL, json=payload, timeout=10)
                    response.raise_for_status()
                    sync_status = "synced"
                except Exception as e:
                    sync_status = f"sync failed: {str(e)}"
            
            if sync_status == "synced":
                return {"status": "ok", "message": f"Job {job_id} status updated to {new_status} and synced to Roofr"}
            elif sync_status == "not configured":
                return {"status": "ok", "message": f"Job {job_id} status updated to {new_status} (Roofr sync not configured)"}
            else:
                return {"status": "partial", "message": f"Job {job_id} status updated locally but Roofr {sync_status}"}
        return {"status": "error", "message": "Job not found"}
    
    elif action.action == "add_job_note":
        job_id = action.parameters.get("job_id")
        note = action.parameters.get("note")
        if job_id in db["jobs"]:
            if "notes" not in db["jobs"][job_id]:
                db["jobs"][job_id]["notes"] = []
            db["jobs"][job_id]["notes"].append({
                "note": note,
                "added_by": current_user["email"],
                "added_at": datetime.now().isoformat()
            })
            save_db(db)
            
            sync_status = "not configured"
            if ROOFR_WEBHOOK_URL:
                try:
                    import requests
                    payload = {
                        "job_id": job_id,
                        "new_note": note,
                        "client_name": db["jobs"][job_id].get("client_name"),
                        "address": db["jobs"][job_id].get("address"),
                        "updated_by": current_user["email"],
                        "updated_at": datetime.now().isoformat()
                    }
                    response = requests.post(ROOFR_WEBHOOK_URL, json=payload, timeout=10)
                    response.raise_for_status()
                    sync_status = "synced"
                except Exception as e:
                    sync_status = f"sync failed: {str(e)}"
            
            if sync_status == "synced":
                return {"status": "ok", "message": f"Note added to job {job_id} and synced to Roofr"}
            elif sync_status == "not configured":
                return {"status": "ok", "message": f"Note added to job {job_id} (Roofr sync not configured)"}
            else:
                return {"status": "partial", "message": f"Note added to job {job_id} locally but Roofr {sync_status}"}
        return {"status": "error", "message": "Job not found"}
    
    elif action.action == "list_jobs":
        jobs = db["jobs"]
        if current_user.get("role") == "user":
            jobs = {jid: _strip_job_financials(j) for jid, j in jobs.items()}
        return {"status": "ok", "jobs": jobs}

    elif action.action == "get_job_details":
        job_id = action.parameters.get("job_id")
        if job_id in db["jobs"]:
            job = db["jobs"][job_id]
            if current_user.get("role") == "user":
                job = _strip_job_financials(job)
            return {"status": "ok", "job": job}
        return {"status": "error", "message": "Job not found"}
    
    elif action.action == "list_documents":
        return {"status": "ok", "documents": db["documents"]}
    
    elif action.action == "send_email":
        return _op_send_email(db, action.parameters.get("to"),
                              action.parameters.get("subject", ""),
                              action.parameters.get("body", ""),
                              action.parameters.get("html"),
                              action.parameters.get("document_ids", []),
                              current_user["email"])
    
    elif action.action == "send_sms":
        # Route through the SMS choke point so a failed/unconfigured text is
        # parked in the sms_outbox instead of being silently lost.
        return _op_send_sms(db, action.parameters.get("to"),
                            action.parameters.get("message", ""),
                            current_user["email"])

    return {"status": "error", "message": "Unknown action"}

@app.post("/chat")
async def chat(message: ChatMessage, current_user: dict = Depends(get_current_user)):
    db = load_db()

    client = get_openai_client()
    if client is None:
        return {
            "response": "The AI assistant isn't configured yet. An administrator "
                        "needs to add an OpenAI API key before I can answer. "
                        "Everything else in the app works normally in the meantime."
        }

    user_email = current_user["email"]
    user_role = current_user.get("role", "user")
    if user_email not in db["chat_history"]:
        db["chat_history"][user_email] = []

    db["chat_history"][user_email].append({
        "role": "user",
        "content": message.message,
        "timestamp": datetime.now().isoformat()
    })

    # Lean, role-scoped system prompt (compact job summary, not the whole DB) +
    # tools for details and actions. The agent can now actually DO things —
    # update job status, add notes (both sync to Roofr), send email/SMS, and
    # (manager+ only) read financials — not just talk about them.
    system_prompt = _build_chat_system_prompt(db, user_email, user_role)
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for msg in db["chat_history"][user_email][-8:]:
        if msg.get("role") in ("user", "assistant") and msg.get("content"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    tools = tools_for_role(user_role)

    try:
        assistant_message = _run_agent_loop(client, messages, tools, current_user, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")

    db["chat_history"][user_email].append({
        "role": "assistant",
        "content": assistant_message,
        "timestamp": datetime.now().isoformat()
    })
    save_db(db)

    return {"response": assistant_message}

@app.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Transcribe voice recording using OpenAI Whisper"""
    client = get_openai_client()
    if client is None:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    try:
        from io import BytesIO
        audio_bytes = await audio.read()
        audio_file = BytesIO(audio_bytes)
        audio_file.name = audio.filename or "recording.webm"
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en"
        )
        return {"text": transcript.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@app.get("/chat/history")
async def get_chat_history(current_user: dict = Depends(get_current_user)):
    db = load_db()
    history = db["chat_history"].get(current_user["email"], [])
    return {"history": history}

@app.delete("/users/{email}")
async def delete_user_access(email: str, current_user: dict = Depends(get_admin_user)):
    if email == ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Cannot delete admin account")
    
    db = load_db()
    if email in db["users"]:
        del db["users"][email]
        save_db(db)
        return {"status": "ok", "message": f"User {email} access deleted"}
    
    raise HTTPException(status_code=404, detail="User not found")

@app.get("/admin/webhook-info")
async def get_webhook_info(current_user: dict = Depends(get_admin_user)):
    # Never return the live secret in the response body: it would land in proxy
    # logs, browser history, and dev-tools. Surface only a short masked hint plus
    # a configured/disabled flag so the operator can confirm which value is set
    # without exposing it. The real value is set via the ZAPIER_SECRET env var.
    _configured = bool(ZAPIER_SECRET) and not ZAPIER_SECRET.startswith("DISABLED_")
    # Suffix-only hint (like card/last-4): confirms the right value is set without
    # exposing a brute-force-helpful prefix.
    _hint = ("****" + ZAPIER_SECRET[-4:]) if _configured else None
    return {
        "webhook_url": "/zapier/webhook",
        "secret_configured": _configured,
        "secret_hint": _hint,
        "instructions": "Include the 'secret' field (the value of the ZAPIER_SECRET env var) in your Zapier webhook payload"
    }

@app.post("/users")
async def create_user(user_data: NewUser, current_user: dict = Depends(get_super_admin)):
    """Create a new user - Super Admin only"""
    db = load_db()
    
    if user_data.email in db["users"]:
        raise HTTPException(status_code=400, detail="User already exists")
    
    if user_data.role not in ["super_admin", "manager", "user"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be: super_admin, manager, or user")
    
    db["users"][user_data.email] = {
        "email": user_data.email,
        "password_hash": hashlib.sha256(user_data.password.encode()).hexdigest(),
        "role": user_data.role
    }
    save_db(db)
    
    return {"status": "ok", "message": f"User {user_data.email} created with role {user_data.role}"}

@app.get("/users")
async def list_users(current_user: dict = Depends(get_super_admin)):
    """List all users - Super Admin only"""
    db = load_db()
    users_list = []
    for email, user_data in db["users"].items():
        users_list.append({
            "email": email,
            "role": user_data.get("role", "user")
        })
    return {"users": users_list}

@app.put("/users/{email}/role")
async def update_user_role(email: str, role_data: UpdateRole, current_user: dict = Depends(get_super_admin)):
    """Update user role - Super Admin only"""
    if email == ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Cannot change super admin role")
    
    if role_data.role not in ["super_admin", "manager", "user"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be: super_admin, manager, or user")
    
    db = load_db()
    if email not in db["users"]:
        raise HTTPException(status_code=404, detail="User not found")
    
    db["users"][email]["role"] = role_data.role
    save_db(db)
    
    return {"status": "ok", "message": f"User {email} role updated to {role_data.role}"}

# ═══════════════════════════════════════════════════════════════════════════════
# F1 — Alpha Estimator inbound door (estimate baseline import)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/alpha/webhook")
async def alpha_webhook(payload: AlphaWebhook):
    if payload.secret != ALPHA_SECRET:
        raise HTTPException(status_code=403, detail="Invalid Alpha webhook secret")
    db = load_db()
    job_id = payload.job_id
    job = db["jobs"].setdefault(job_id, {"job_id": job_id})
    # Update basic job fields if provided
    for field in ("client_name", "address"):
        val = getattr(payload, field, None)
        if val:
            job[field] = val
    extra = payload.data or {}
    if extra:
        job.update({k: v for k, v in extra.items() if v not in (None, "")})
    budget = job.setdefault("budget", {})
    if payload.contract_value is not None:
        budget["contract_value"] = payload.contract_value
    if payload.coating_system:
        budget["system"] = payload.coating_system
        job["coating_system"] = payload.coating_system
    if payload.substrate:
        budget["substrate"] = payload.substrate
    if payload.sqft is not None:
        budget["sqft"] = payload.sqft
    if payload.dry_mil_target is not None:
        budget["dry_mil_target"] = payload.dry_mil_target
    if payload.quoted_margin is not None:
        budget["quoted_margin"] = payload.quoted_margin
    if payload.loaded_labor_rate is not None:
        budget["loaded_labor_rate"] = payload.loaded_labor_rate
    if payload.est_gallons:
        budget["est_gallons"] = payload.est_gallons
    if payload.material_cost_per_gal:
        budget["material_cost_per_gal"] = payload.material_cost_per_gal
    if payload.labor_hours_by_method:
        budget["labor_hours_by_method"] = payload.labor_hours_by_method
    budget["imported_at"] = datetime.now().isoformat()
    save_db(db)
    return {"status": "ok", "job_id": job_id, "message": "Estimate baseline imported",
            "budget_fields": list(budget.keys())}


# ═══════════════════════════════════════════════════════════════════════════════
# F2 — Delta Coating Logistics inbound door (production log)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/production/webhook")
async def production_webhook(payload: ProductionLogWebhook):
    if payload.secret != PRODUCTION_SECRET:
        raise HTTPException(status_code=403, detail="Invalid production webhook secret")
    db = load_db()
    job = db["jobs"].get(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {payload.job_id!r} not found")
    # Idempotency (dash-02): TruHub stamps each Delta daily log with a
    # [delta_log:<uuid>] marker in notes. If a log carrying this exact marker is
    # already present, this is a retry / re-fire being replayed - skip the append
    # so a day's log is not doubled. TruHub dedupes on its side too; this makes the
    # door self-protecting against any caller that re-posts the same log.
    import re
    _marker_match = re.search(r"\[delta_log:[0-9a-fA-F-]+\]", payload.notes or "")
    if _marker_match:
        _marker = _marker_match.group(0)
        for _existing in job.get("production_logs", []):
            if _marker in (_existing.get("notes") or ""):
                return {"status": "ok", "job_id": payload.job_id,
                        "pct_complete": job.get("pct_complete"),
                        "applied_gallons": _applied_gallons_by_product(job),
                        "duplicate": True,
                        "message": "Production log already recorded (idempotent skip)"}
    log_entry = {
        "date": payload.date,
        "crew": payload.crew,
        "product": payload.product,
        "gallons_applied": payload.gallons_applied,
        "gallons_by_product": payload.gallons_by_product or (
            {payload.product: payload.gallons_applied} if payload.product and payload.gallons_applied else {}),
        "sqft_coated": payload.sqft_coated,
        "wet_mil": payload.wet_mil or [],
        "hours_by_type": payload.hours_by_type or {},
        "weather": payload.weather or {},
        "photo_refs": payload.photo_refs or [],
        "notes": payload.notes,
        "coat_seq": payload.coat_seq,
        "logged_at": datetime.now().isoformat(),
    }
    # Delta field-data wire contract (step 6 receiver): attach the optional
    # log-level readings/warnings/punch/photo metadata verbatim. Only include a
    # field when the sender actually sent it, so old logs stay clean.
    if payload.dft_readings is not None:
        log_entry["dft_readings"] = payload.dft_readings
    if payload.wft_readings is not None:
        log_entry["wft_readings"] = payload.wft_readings
    if payload.ai_warnings is not None:
        log_entry["ai_warnings"] = payload.ai_warnings
    if payload.punch_list is not None:
        log_entry["punch_list"] = payload.punch_list
    if payload.photo_meta is not None:
        log_entry["photo_meta"] = payload.photo_meta
    job.setdefault("production_logs", []).append(log_entry)
    # Job-level objects: inspection + spec_baseline (warranty thresholds). Latest
    # non-empty wins; pass through verbatim — never compute or guess a spec value.
    if payload.inspection:
        job["inspection"] = payload.inspection
    if payload.spec_baseline:
        job["spec_baseline"] = payload.spec_baseline
    pct = _production_pct_complete(job)
    job["pct_complete"] = pct
    # Auto-check margin alert (A11)
    budget = job.get("budget") or {}
    est_gallons = budget.get("est_gallons") or {}
    applied = _applied_gallons_by_product(job)
    for prod, est_gals in est_gallons.items():
        if applied.get(prod, 0) > float(est_gals or 0) * 1.05:
            job.setdefault("alerts", []).append({
                "type": "gallons_overrun", "product": prod,
                "at": datetime.now().isoformat(),
            })
    save_db(db)
    return {"status": "ok", "job_id": payload.job_id, "pct_complete": pct,
            "applied_gallons": applied, "message": "Production log appended"}


# ═══════════════════════════════════════════════════════════════════════════════
# F3 — Dominate lead inbound door
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/leads/webhook")
async def leads_webhook(payload: LeadWebhook):
    if payload.secret != LEADS_SECRET:
        raise HTTPException(status_code=403, detail="Invalid leads webhook secret")
    db = load_db()
    opportunities = db.get("opportunities", {})

    # Dedupe pass 1: stable cross-system key. Sources like Dominate send
    # data.dominate_brand_id (their Brand row id) and carry no address, so the
    # name+address check below never catches their repeats — re-running a
    # backfill would duplicate every client. Match on the source id first.
    # str() both sides so an int id and a stringified id still compare equal.
    # Scope marker (step 7a): public-Dominate clients carry data.scope so the
    # dashboard can exclude them from Truline-only views. May be None. Set on
    # every create/update path below so a re-seen lead keeps its scope current.
    scope = (payload.data or {}).get("scope")

    brand_id = (payload.data or {}).get("dominate_brand_id")
    if brand_id is not None:
        for oid, opp in opportunities.items():
            if opp.get("dominate_brand_id") is not None and \
                    str(opp.get("dominate_brand_id")) == str(brand_id):
                opp["last_seen"] = datetime.now().isoformat()
                opp["scope"] = scope
                save_db(db)
                return {"status": "ok",
                        "message": "Duplicate lead — opportunity updated",
                        "opportunity_id": oid, "duplicate": True}

    # Dedupe pass 2: by address+name. Stored records may hold None for either
    # field (a None address once poisoned this loop and 500'd every later lead),
    # so guard both sides with `or ""`.
    address = (payload.address or "").strip().lower()
    client = (payload.client_name or "").strip().lower()
    for oid, opp in opportunities.items():
        if ((opp.get("address") or "").lower() == address and
                (opp.get("client_name") or "").lower() == client and address):
            opp["last_seen"] = datetime.now().isoformat()
            opp["scope"] = scope
            save_db(db)
            return {"status": "ok", "message": "Duplicate lead — opportunity updated",
                    "opportunity_id": oid, "duplicate": True}
    opp_id = f"opp_{int(datetime.now().timestamp() * 1000)}"
    sla_hours = 24
    opp = {
        "id": opp_id,
        "client_name": payload.client_name,
        "address": payload.address,
        "phone": payload.phone,
        "email": payload.email,
        "notes": payload.notes,
        "rep": payload.rep,
        "territory": payload.territory,
        "source": payload.source or "unknown",
        "stage": "New Lead",
        "first_touch_at": datetime.now().isoformat(),
        "sla_due": (datetime.now() + timedelta(hours=sla_hours)).isoformat(),
        "timeline": [{"event": "lead_created", "source": payload.source,
                      "at": datetime.now().isoformat()}],
    }
    if payload.data:
        opp.update({k: v for k, v in payload.data.items() if v not in (None, "")})
    # Always record scope explicitly (may be None) so the dashboard can filter
    # public-Dominate clients out of Truline views regardless of the data merge.
    opp["scope"] = scope
    db.setdefault("opportunities", {})[opp_id] = opp
    save_db(db)
    return {"status": "ok", "opportunity_id": opp_id, "stage": "New Lead",
            "sla_due": opp["sla_due"], "message": "Lead created"}


# ═══════════════════════════════════════════════════════════════════════════════
# F4 — Scheduler primitive
# ═══════════════════════════════════════════════════════════════════════════════

_CRON_TASKS: Dict[str, Any] = {}  # registered task handlers (set in later sections)

@app.post("/cron/tick")
async def cron_tick(request: Request, task: str = "noop"):
    # Secret is accepted ONLY via the X-Cron-Secret header, never a ?secret=
    # query param (which would land in proxy/access logs). The query fallback was
    # removed after prod logs confirmed no caller used it, so this closes G12 for
    # good: a secret placed in the URL simply won't authenticate.
    provided = request.headers.get("X-Cron-Secret")
    if provided != CRON_SECRET:
        raise HTTPException(status_code=403, detail="Invalid cron secret")
    log_entry = {"task": task, "fired_at": datetime.now().isoformat(), "result": None}
    handler = _CRON_TASKS.get(task)
    if handler:
        try:
            result = handler()
            log_entry["result"] = result
        except Exception as e:
            log_entry["result"] = f"error: {e}"
    else:
        log_entry["result"] = "noop — task not registered"
    db = load_db()
    db.setdefault("cron_log", []).append(log_entry)
    if len(db["cron_log"]) > 500:
        db["cron_log"] = db["cron_log"][-500:]
    save_db(db)
    return {"status": "ok", "task": task, "result": log_entry["result"]}


# ═══════════════════════════════════════════════════════════════════════════════
# F5 — QB expense enrichment (extended from existing /quickbooks/webhook)
# GET endpoint exposes purchased-gallon rollup per job
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/job/{job_id}/material-costs")
async def get_material_costs(job_id: str, current_user: dict = Depends(get_manager_or_above)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    financials = db.get("financials", {})
    exp_map = financials.get("expenses", {})
    material_expenses = []
    purchased_gallons: Dict[str, float] = {}
    for eid in job.get("expenses", []):
        exp = exp_map.get(eid, {})
        if not exp:
            continue
        cat = (exp.get("category") or "").lower()
        if "material" in cat or "coating" in cat or "product" in cat or exp.get("product"):
            material_expenses.append(exp)
            prod = exp.get("product") or exp.get("description") or "unknown"
            gals = float(exp.get("gallons_purchased") or 0)
            if gals:
                purchased_gallons[prod] = purchased_gallons.get(prod, 0) + gals
    budget = job.get("budget") or {}
    est_gallons = budget.get("est_gallons") or {}
    applied = _applied_gallons_by_product(job)
    comparison = {}
    for prod in set(list(est_gallons.keys()) + list(purchased_gallons.keys()) + list(applied.keys())):
        comparison[prod] = {
            "estimated": est_gallons.get(prod, 0),
            "purchased": purchased_gallons.get(prod, 0),
            "applied": applied.get(prod, 0),
        }
    return {"status": "ok", "job_id": job_id, "material_expenses": material_expenses,
            "purchased_gallons": purchased_gallons, "gallon_comparison": comparison}


# ═══════════════════════════════════════════════════════════════════════════════
# F6 — Weather profiles admin + per-job weather check
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/weather-profiles")
async def get_weather_profiles(current_user: dict = Depends(get_manager_or_above)):
    db = load_db()
    return {"status": "ok", "weather_profiles": db.get("weather_profiles", {})}

@app.put("/admin/weather-profiles")
async def update_weather_profiles(profiles: dict, current_user: dict = Depends(get_super_admin)):
    db = load_db()
    db["weather_profiles"].update(profiles)
    save_db(db)
    return {"status": "ok", "message": "Weather profiles updated", "systems": list(profiles.keys())}

@app.post("/job/{job_id}/weather-check")
async def job_weather_check(job_id: str, req: WeatherCheckRequest,
                            current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    system = req.coating_system or (job.get("budget") or {}).get("system") or job.get("coating_system") or "default"
    profile = db.get("weather_profiles", {}).get(system.lower()) or list(db.get("weather_profiles", _DEFAULT_WEATHER_PROFILES).values())[0]
    lat, lon = req.lat, req.lon
    if lat is None or lon is None:
        address = job.get("address")
        if address:
            try:
                lat, lon = _geocode(address)
            except Exception:
                pass
    if lat is None or lon is None:
        return {"status": "ok", "verdict": "UNKNOWN",
                "reason": "Provide lat/lon or ensure job has an address for geocoding"}
    try:
        forecast = _fetch_weather(lat, lon)
        verdict_data = _weather_verdict_from_forecast(forecast, profile)
    except Exception as e:
        return {"status": "error", "message": f"Weather fetch failed: {e}"}
    job["weather_status"] = verdict_data
    save_db(db)
    return {"status": "ok", "job_id": job_id, **verdict_data}


# ═══════════════════════════════════════════════════════════════════════════════
# A-phase — Accounting, Job Costing & Finance
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/job/{job_id}/cost-breakdown")
async def job_cost_breakdown(job_id: str, current_user: dict = Depends(get_manager_or_above)):
    """A7 + A8: Per-job cost categories with 45% burden on labor."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "job_id": job_id, **_cost_breakdown(db, job)}

@app.get("/job/{job_id}/gallons-tracker")
async def gallons_tracker(job_id: str, current_user: dict = Depends(get_current_user)):
    """A9: Applied vs. estimated gallons per product (three-bucket model)."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    budget = job.get("budget") or {}
    est = budget.get("est_gallons") or {}
    applied = _applied_gallons_by_product(job)
    result = {}
    for prod in set(list(est.keys()) + list(applied.keys())):
        e = float(est.get(prod) or 0)
        a = applied.get(prod, 0)
        pct = round(a / e * 100, 1) if e > 0 else None
        result[prod] = {"estimated": e, "applied": a, "pct_consumed": pct,
                        "overrun": a > e * 1.0 if e > 0 else False}
    return {"status": "ok", "job_id": job_id, "gallons": result,
            "pct_complete": _production_pct_complete(job)}

@app.get("/job/{job_id}/coverage")
async def coverage_reconciliation(job_id: str, current_user: dict = Depends(get_manager_or_above)):
    """A10: Achieved dry-mil from gallons+sqft+volume-solids vs. estimate AND spec min."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    budget = job.get("budget") or {}
    system = budget.get("system") or job.get("coating_system") or ""
    vs = _get_volume_solids(system)
    sqft = float(budget.get("sqft") or 0)
    dry_mil_target = float(budget.get("dry_mil_target") or 0)
    applied = _applied_gallons_by_product(job)
    total_applied = sum(applied.values())
    achieved = _calc_achieved_dry_mil(total_applied, sqft, vs)
    warranty_min = float((job.get("warranty") or {}).get("required_mil") or dry_mil_target or 0)
    wet_mil_readings = [r for log in job.get("production_logs", []) for r in (log.get("wet_mil") or [])]
    avg_wet_mil = round(sum(wet_mil_readings) / len(wet_mil_readings), 2) if wet_mil_readings else None
    flag = None
    if achieved > 0 and warranty_min > 0:
        if achieved < warranty_min * 0.95:
            flag = "TOO_THIN — warranty risk"
        elif achieved > dry_mil_target * 1.20:
            flag = "TOO_THICK — margin loss"
    return {
        "status": "ok", "job_id": job_id, "system": system, "volume_solids_pct": round(vs * 100, 1),
        "sqft": sqft, "total_applied_gallons": round(total_applied, 2),
        "achieved_dry_mil": achieved, "target_dry_mil": dry_mil_target,
        "warranty_min_mil": warranty_min, "avg_wet_mil_reading": avg_wet_mil,
        "flag": flag,
    }

@app.get("/job/{job_id}/margin-alert")
async def margin_alert(job_id: str, current_user: dict = Depends(get_manager_or_above)):
    """A11: Fire when live margin drops >5 pts below quote."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    budget = job.get("budget") or {}
    quoted = float(budget.get("quoted_margin") or 0)
    live = _job_margin_live(db, job)
    cb = _cost_breakdown(db, job)
    projected_margin = cb.get("margin_pct", 0)
    alerts = []
    if quoted > 0 and projected_margin < quoted - 5:
        alerts.append(f"Projected margin {projected_margin:.1f}% is {quoted - projected_margin:.1f} pts below quoted {quoted:.1f}%")
    if live is not None and quoted > 0 and live < quoted - 5:
        alerts.append(f"Billed margin {live:.1f}% is {quoted - live:.1f} pts below quote")
    applied = _applied_gallons_by_product(job)
    for prod, est_gals in (budget.get("est_gallons") or {}).items():
        if applied.get(prod, 0) > float(est_gals or 0) * 1.0:
            alerts.append(f"Gallons overrun on {prod}")
    return {"status": "ok", "job_id": job_id, "quoted_margin": quoted,
            "live_billed_margin": live, "projected_margin": projected_margin,
            "alerts": alerts, "alert_count": len(alerts)}

@app.get("/financials/dashboard")
async def company_dashboard(current_user: dict = Depends(get_manager_or_above)):
    """A12: Company-wide profitability dashboard."""
    db = load_db()
    jobs = list(db.get("jobs", {}).values())
    financials = db.get("financials", {})
    inv_map = financials.get("invoices", {})
    exp_map = financials.get("expenses", {})
    total_revenue = total_cost = 0.0
    by_system: Dict[str, dict] = {}
    active_jobs = 0
    for job in jobs:
        revenue = sum(float(inv_map.get(i, {}).get("amount", 0) or 0)
                      for i in job.get("invoices", [])
                      if inv_map.get(i, {}).get("status") != "cancelled")
        cost = sum(float(exp_map.get(e, {}).get("amount", 0) or 0)
                   for e in job.get("expenses", []))
        total_revenue += revenue
        total_cost += cost
        system = (job.get("budget") or {}).get("system") or "unknown"
        sys_data = by_system.setdefault(system, {"revenue": 0, "cost": 0, "jobs": 0})
        sys_data["revenue"] += revenue
        sys_data["cost"] += cost
        sys_data["jobs"] += 1
        if job.get("status") in ("In Progress", "Approved"):
            active_jobs += 1
    profit = total_revenue - total_cost
    margin = round(profit / total_revenue * 100, 2) if total_revenue > 0 else 0
    for sys_data in by_system.values():
        r = sys_data["revenue"]
        c = sys_data["cost"]
        sys_data["margin_pct"] = round((r - c) / r * 100, 2) if r > 0 else 0
    backlog = sum(float((j.get("budget") or {}).get("contract_value") or 0)
                  for j in jobs if j.get("workflow_stage") in ("Won", "Approved"))
    return {"status": "ok", "total_jobs": len(jobs), "active_jobs": active_jobs,
            "total_revenue": round(total_revenue, 2), "total_cost": round(total_cost, 2),
            "profit": round(profit, 2), "margin_pct": margin,
            "backlog": round(backlog, 2), "by_system": by_system}

@app.get("/financials/wip")
async def wip_report(current_user: dict = Depends(get_manager_or_above)):
    """A13: WIP report — earned vs billed per job."""
    db = load_db()
    financials = db.get("financials", {})
    inv_map = financials.get("invoices", {})
    rows = []
    for jid, job in db.get("jobs", {}).items():
        budget = job.get("budget") or {}
        contract = float(budget.get("contract_value") or 0)
        if contract <= 0:
            continue
        pct = _production_pct_complete(job) / 100.0
        earned = round(contract * pct, 2)
        billed = sum(float(inv_map.get(i, {}).get("amount", 0) or 0)
                     for i in job.get("invoices", [])
                     if inv_map.get(i, {}).get("status") != "cancelled")
        position = earned - billed
        rows.append({"job_id": jid, "client": job.get("client_name"),
                     "contract": contract, "pct_complete": pct * 100,
                     "earned": earned, "billed": round(billed, 2),
                     "wip_position": round(position, 2),
                     "status": "over_billed" if position < 0 else "under_billed" if position > 0 else "on_track"})
    return {"status": "ok", "wip": rows}

@app.get("/job/{job_id}/draws")
async def get_draws(job_id: str, current_user: dict = Depends(get_manager_or_above)):
    """A14: Draw schedule for a job."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "job_id": job_id, "draws": job.get("billing", {}).get("draws", [])}

@app.post("/job/{job_id}/draws")
async def add_draw(job_id: str, req: DrawRequest,
                   current_user: dict = Depends(get_manager_or_above)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # retainage_pct may arrive as an explicit null (Pydantic only fills the 10.0
    # default for a MISSING key), so coerce None back to the documented default.
    pct = req.retainage_pct if req.retainage_pct is not None else 10.0
    billing = job.setdefault("billing", {"draws": [], "retainage_pct": pct})
    retainage = round(req.amount * (pct / 100), 2)
    net = round(req.amount - retainage, 2)
    draw = {"id": f"draw_{len(billing.get('draws', [])) + 1}",
            "description": req.description, "milestone": req.milestone,
            "gross_amount": req.amount, "retainage_pct": pct,
            "retainage_held": retainage, "net_invoice": net,
            "created_at": datetime.now().isoformat(), "status": "pending"}
    billing.setdefault("draws", []).append(draw)
    billing["retainage_pct"] = pct
    save_db(db)
    return {"status": "ok", "draw": draw, "message": f"Draw created — net invoice: ${net}"}

@app.get("/job/{job_id}/change-orders")
async def get_change_orders(job_id: str, current_user: dict = Depends(get_manager_or_above)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "job_id": job_id, "change_orders": job.get("change_orders", [])}

@app.post("/job/{job_id}/change-orders")
async def add_change_order(job_id: str, req: ChangeOrderRequest,
                           current_user: dict = Depends(get_manager_or_above)):
    """A15: Add a change order; approved ones revise the baseline."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    co_id = f"co_{len(job.get('change_orders', [])) + 1}"
    co = {"id": co_id, "reason": req.reason, "added_gallons": req.added_gallons,
          "added_hours": req.added_hours, "price": req.price,
          "approved_by": req.approved_by,
          "approved_at": datetime.now().isoformat() if req.approved_by else None,
          "created_at": datetime.now().isoformat()}
    job.setdefault("change_orders", []).append(co)
    if req.approved_by:
        budget = job.setdefault("budget", {})
        budget["contract_value"] = float(budget.get("contract_value") or 0) + (req.price or 0)
    save_db(db)
    return {"status": "ok", "change_order": co}

@app.get("/financials/ar-aging")
async def ar_aging(current_user: dict = Depends(get_manager_or_above)):
    """A16: AR aging buckets."""
    db = load_db()
    buckets = _ar_aging_buckets(db)
    totals = {k: sum(i.get("amount") or 0 for i in v) for k, v in buckets.items()}
    return {"status": "ok", "buckets": buckets, "totals": totals}

@app.post("/financials/ar-aging/{invoice_id}/remind")
async def ar_send_reminder(invoice_id: str, current_user: dict = Depends(get_manager_or_above)):
    """A16: one-click payment reminder for an overdue invoice via the comms webhooks."""
    db = load_db()
    inv = db.get("financials", {}).get("invoices", {}).get(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.get("status") in ("paid", "cancelled"):
        return {"status": "error", "message": f"Invoice is {inv.get('status')} — no reminder needed"}
    job = db["jobs"].get(inv.get("job_id")) or {}
    to_email = job.get("customer_email") or job.get("contact_email")
    to_phone = job.get("customer_phone") or job.get("contact_phone")
    if not to_email and not to_phone:
        return {"status": "error", "message": "No customer contact on file for the linked job"}
    now = datetime.now()
    try:
        due = datetime.fromisoformat(inv.get("due_date") or inv.get("date") or now.isoformat())
        days_past_due = (now - due).days
    except Exception:
        days_past_due = None
    subject = f"Payment reminder — invoice {invoice_id}"
    body = (f"Hello {inv.get('customer_name') or 'there'},\n\n"
            f"A friendly reminder that invoice {invoice_id} for ${inv.get('amount')} is past due"
            + (f" by {days_past_due} days" if days_past_due else "") + ".\n\n"
            f"Please reach out with any questions. Thank you,\nTruline Roofing")
    email_status = sms_status = None
    if to_email:
        email_status = _send_email_or_log(db, to_email, subject, body, current_user["email"])
    if to_phone:
        # Route through the SMS choke point: an unconfigured Zap or a failed send
        # parks the reminder in the sms_outbox instead of dropping it silently.
        _r = _sms_dispatch(db, {"to": to_phone, "message": body,
                                "sent_by": current_user["email"],
                                "sent_at": now.isoformat()})
        sms_status = _r.get("status")
    inv.setdefault("reminders", []).append({"sent_by": current_user["email"],
        "sent_at": now.isoformat(), "email_status": email_status, "sms_status": sms_status})
    save_db(db)
    return {"status": "ok", "invoice_id": invoice_id, "days_past_due": days_past_due,
            "email_status": email_status, "sms_status": sms_status}

@app.get("/financials/ap-aging")
async def ap_aging(current_user: dict = Depends(get_manager_or_above)):
    """A17: AP / vendor bill aging."""
    db = load_db()
    now = datetime.now()
    rows = []
    by_vendor: Dict[str, float] = {}
    for eid, exp in (db.get("financials", {}).get("expenses", {})).items():
        if exp.get("status") == "paid":
            continue
        vendor = exp.get("vendor_name") or "Unknown"
        amt = float(exp.get("amount") or 0)
        by_vendor[vendor] = by_vendor.get(vendor, 0) + amt
        try:
            due = datetime.fromisoformat(exp.get("due_date") or exp.get("date") or now.isoformat())
            days_due = (now - due).days
        except Exception:
            days_due = 0
        rows.append({"expense_id": eid, "vendor": vendor, "amount": amt,
                     "date": exp.get("date"), "days_due": days_due,
                     "po_number": exp.get("po_number"),
                     "po_matched": bool(exp.get("po_matched"))})
    return {"status": "ok", "vendor_totals": by_vendor, "unpaid_bills": rows}

@app.get("/payroll/export")
async def payroll_export(period_start: str, period_end: str,
                         current_user: dict = Depends(get_manager_or_above)):
    """A18: Aggregate Delta hours per employee for a pay period."""
    db = load_db()
    rows: Dict[str, dict] = {}
    try:
        start = datetime.fromisoformat(period_start)
        end = datetime.fromisoformat(period_end)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format (use YYYY-MM-DD)")
    for jid, job in db.get("jobs", {}).items():
        for log in job.get("production_logs", []):
            try:
                log_date = datetime.fromisoformat(log.get("date") or "")
            except Exception:
                continue
            if not (start <= log_date <= end):
                continue
            crew = log.get("crew") or "unknown"
            emp = rows.setdefault(crew, {"employee": crew, "spray_hrs": 0, "prep_hrs": 0, "total_hrs": 0, "jobs": []})
            hours = log.get("hours_by_type") or {}
            emp["spray_hrs"] += float(hours.get("spray", 0))
            emp["prep_hrs"] += float(hours.get("prep", 0) + hours.get("roller", 0))
            emp["total_hrs"] += sum(float(v) for v in hours.values())
            if jid not in emp["jobs"]:
                emp["jobs"].append(jid)
        for tl in job.get("timelogs", []):
            try:
                tl_date = datetime.fromisoformat(tl.get("arrive") or "")
            except Exception:
                continue
            if not (start <= tl_date <= end):
                continue
            emp_name = tl.get("employee") or "unknown"
            emp = rows.setdefault(emp_name, {"employee": emp_name, "spray_hrs": 0, "prep_hrs": 0, "total_hrs": 0, "jobs": []})
            hrs = float(tl.get("hours") or 0)
            emp["total_hrs"] += hrs
            if tl.get("hours_type") == "spray":
                emp["spray_hrs"] += hrs
            elif tl.get("hours_type") == "prep":
                emp["prep_hrs"] += hrs
    return {"status": "ok", "period": {"start": period_start, "end": period_end},
            "employees": list(rows.values())}

@app.get("/job/{job_id}/retainage-release")
async def retainage_release_status(job_id: str, current_user: dict = Depends(get_manager_or_above)):
    """A20: Gate final retainage release on warranty + inspection + punch list."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    warranty = job.get("warranty") or {}
    punch_open = [p for p in job.get("punch_items", []) if p.get("status") != "done"]
    gates = {
        "warranty_registered": bool(warranty.get("registered")),
        "punch_list_clear": len(punch_open) == 0,
        "permit_closed": (job.get("permit") or {}).get("status") in ("issued", "closed", "not_required"),
    }
    can_release = all(gates.values())
    billing = job.get("billing") or {}
    total_retainage = sum(float(d.get("retainage_held") or 0) for d in billing.get("draws", []))
    return {"status": "ok", "job_id": job_id, "gates": gates, "can_release": can_release,
            "total_retainage_held": round(total_retainage, 2),
            "blocking_issues": [k for k, v in gates.items() if not v]}


# ═══════════════════════════════════════════════════════════════════════════════
# P-phase — Production & QA
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/job/{job_id}/qa-reading")
async def add_qa_reading(job_id: str, req: QAReadingRequest,
                         current_user: dict = Depends(get_current_user)):
    """P21: Wet-mil reading → expected dry-mil, auto-flag below warranty min."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    budget = job.get("budget") or {}
    system = budget.get("system") or job.get("coating_system") or ""
    vs = _get_volume_solids(req.product or system)
    avg_wet = sum(req.wet_mil or []) / max(len(req.wet_mil or []), 1) if req.wet_mil else None
    expected_dry = round(avg_wet * vs, 2) if avg_wet else None
    warranty_min = float((job.get("warranty") or {}).get("required_mil") or budget.get("dry_mil_target") or 0)
    flag = expected_dry is not None and warranty_min > 0 and expected_dry < warranty_min * 0.95
    reading = {
        "product": req.product, "coat_seq": req.coat_seq, "area": req.area,
        "wet_mil": req.wet_mil, "avg_wet_mil": avg_wet,
        "expected_dry_mil": expected_dry, "volume_solids_pct": round(vs * 100, 1),
        "warranty_min_mil": warranty_min, "flag": flag,
        "notes": req.notes, "taken_by": current_user["email"],
        "taken_at": datetime.now().isoformat(),
    }
    job.setdefault("qa_readings", []).append(reading)
    if flag:
        job.setdefault("alerts", []).append({"type": "mil_below_min", "coat_seq": req.coat_seq,
                                              "expected_dry_mil": expected_dry, "at": datetime.now().isoformat()})
    if flag:
        job.setdefault("punch_items", []).append({
            "id": f"punch_{len(job.get('punch_items', [])) + 1}",
            "description": f"Thin mil on coat {req.coat_seq} area {req.area or 'unknown'} — re-coat required",
            "area": req.area, "source": "qa_auto", "status": "open",
            "created_at": datetime.now().isoformat(),
        })
    save_db(db)
    return {"status": "ok", "reading": reading, "flag": flag,
            "message": "Low mil flagged — punch item auto-created" if flag else "QA reading recorded"}

@app.get("/job/{job_id}/prep-signoff")
async def get_prep_signoff(job_id: str, current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    substrate = (job.get("budget") or {}).get("substrate") or "default"
    required = _PREP_ITEMS_BY_SUBSTRATE.get(substrate.lower(), _PREP_ITEMS_BY_SUBSTRATE["default"])
    return {"status": "ok", "job_id": job_id, "substrate": substrate,
            "required_items": required, "signoff": job.get("prep_signoff")}

@app.post("/job/{job_id}/prep-signoff")
async def submit_prep_signoff(job_id: str, req: PrepSignoffRequest,
                              current_user: dict = Depends(get_current_user)):
    """P22: Substrate prep sign-off — gates production start."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    substrate = req.substrate or (job.get("budget") or {}).get("substrate") or "default"
    required = _PREP_ITEMS_BY_SUBSTRATE.get(substrate.lower(), _PREP_ITEMS_BY_SUBSTRATE["default"])
    missing = [item for item in required if not req.items.get(item)]
    job["prep_signoff"] = {
        "substrate": substrate, "area": req.area, "items": req.items,
        "required": required, "missing": missing,
        "complete": len(missing) == 0, "notes": req.notes,
        "signed_by": current_user["email"], "signed_at": datetime.now().isoformat(),
    }
    save_db(db)
    return {"status": "ok", "complete": len(missing) == 0, "missing_items": missing,
            "message": "Prep sign-off complete — ready to coat" if not missing else f"Blocked: {', '.join(missing)}"}

@app.post("/job/{job_id}/weather-application-check")
async def weather_application_check(job_id: str, req: WeatherApplicationCheckRequest,
                                     current_user: dict = Depends(get_current_user)):
    """P23: Record actual weather conditions at the time of application vs. the
    per-system spec window — temp / surface / RH / dewpoint / wind at apply time,
    plus POST-application rain-free hours achieved vs. min-cure-before-rain."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    actual = {"temp": req.temp, "surface_temp": req.surface_temp, "rh": req.rh,
              "dewpoint": req.dewpoint, "wind": req.wind,
              "rain_free_hrs_actual": req.rain_free_hrs_actual}
    system = (job.get("budget") or {}).get("system") or job.get("coating_system") or "default"
    profile = db.get("weather_profiles", _DEFAULT_WEATHER_PROFILES).get(system.lower(), {})
    flags = []
    if req.temp is not None and req.temp < float(profile.get("temp_min", 40)):
        flags.append("temp_below_min")
    if req.surface_temp is not None and profile.get("surface_min") is not None \
            and req.surface_temp < float(profile["surface_min"]):
        flags.append("surface_below_min")
    if req.rh is not None and req.rh > float(profile.get("rh_max", 85)):
        flags.append("humidity_above_max")
    # Surface within the spec margin of dewpoint risks condensation under the film.
    if req.surface_temp is not None and req.dewpoint is not None \
            and (req.surface_temp - req.dewpoint) < float(profile.get("surface_minus_dewpoint", 5)):
        flags.append("surface_within_dewpoint_margin")
    # Post-application rain-free hours achieved vs. the min cure-before-rain window
    # (the warranty-critical field — NOT the pre-application apply window).
    if req.rain_free_hrs_actual is not None \
            and req.rain_free_hrs_actual < float(profile.get("min_cure_before_rain_hrs", 4)):
        flags.append("min_cure_before_rain_not_met")
    record = {
        "actual_conditions": actual, "system": system, "profile_used": profile,
        "out_of_window": len(flags) > 0, "flags": flags, "notes": req.notes,
        "coat_seq": req.coat_seq,
        "recorded_by": current_user["email"], "recorded_at": datetime.now().isoformat(),
    }
    job.setdefault("weather_application_checks", []).append(record)
    save_db(db)
    return {"status": "ok", "out_of_window": len(flags) > 0, "flags": flags, "record": record}

@app.get("/job/{job_id}/production-dashboard")
async def production_dashboard(job_id: str, current_user: dict = Depends(get_current_user)):
    """P24: Full job production dashboard."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    budget = job.get("budget") or {}
    applied = _applied_gallons_by_product(job)
    pct = _production_pct_complete(job)
    qa_flags = [r for r in job.get("qa_readings", []) if r.get("flag")]
    open_punch = [p for p in job.get("punch_items", []) if p.get("status") != "done"]
    latest_log = max(job.get("production_logs", []), key=lambda l: l.get("date", ""), default=None)
    total_sqft = sum(float(l.get("sqft_coated") or 0) for l in job.get("production_logs", []))
    total_hrs = sum(sum(float(v) for v in (l.get("hours_by_type") or {}).values())
                    for l in job.get("production_logs", []))
    achieved_mil = None
    vs = _get_volume_solids((budget.get("system") or ""))
    sqft = float(budget.get("sqft") or 0)
    if sqft > 0:
        achieved_mil = _calc_achieved_dry_mil(sum(applied.values()), sqft, vs)
    health = "good"
    if qa_flags:
        health = "warning"
    if any(v for v in job.get("alerts", []) if v.get("type") == "gallons_overrun"):
        health = "alert"
    return {
        "status": "ok", "job_id": job_id, "client": job.get("client_name"),
        "pct_complete": pct, "total_sqft_coated": round(total_sqft, 0),
        "sqft_target": sqft, "applied_gallons": applied,
        "est_gallons": budget.get("est_gallons"), "total_hours": round(total_hrs, 1),
        "crew_days": len(job.get("production_logs", [])), "weather_status": job.get("weather_status"),
        "achieved_dry_mil": achieved_mil, "target_dry_mil": budget.get("dry_mil_target"),
        "qa_flag_count": len(qa_flags), "open_punch_items": len(open_punch),
        "health_badge": health, "last_log_date": (latest_log or {}).get("date"),
        "prep_signoff": job.get("prep_signoff", {}).get("complete"),
        "warranty": job.get("warranty"),
    }

@app.get("/job/{job_id}/coat-windows")
async def coat_windows(job_id: str, current_user: dict = Depends(get_current_user)):
    """P25: Inter-coat recoat windows — warn on too-soon / lapsed."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    system = (job.get("budget") or {}).get("system") or ""
    profile = db.get("weather_profiles", {}).get(system.lower(), {})
    window_hrs = float(profile.get("inter_coat_window_hrs") or 4)
    # Coats are derived from the F2 production logs (the actual writer of coat-level
    # data) — grouped by coat_seq, using the earliest log per coat as applied_at.
    by_seq: Dict[Any, dict] = {}
    for log in job.get("production_logs", []):
        seq = log.get("coat_seq")
        if seq is None:
            continue
        applied_at = log.get("logged_at") or log.get("date")
        cur = by_seq.get(seq)
        if cur is None or (applied_at and applied_at < (cur.get("applied_at") or "")):
            by_seq[seq] = {"seq": seq, "product": log.get("product"), "applied_at": applied_at}
    coats = sorted(by_seq.values(), key=lambda c: c.get("seq") or 0)
    now = datetime.now()
    result = []
    for i, coat in enumerate(coats):
        applied_at = coat.get("applied_at")
        status = {"coat_seq": coat.get("seq"), "product": coat.get("product"),
                  "applied_at": applied_at}
        if applied_at:
            try:
                applied_dt = datetime.fromisoformat(applied_at)
                hours_elapsed = (now - applied_dt).total_seconds() / 3600
                earliest_next = applied_dt + timedelta(hours=window_hrs)
                status["hours_elapsed"] = round(hours_elapsed, 1)
                status["earliest_next_coat"] = earliest_next.isoformat()
                status["ready_for_next_coat"] = hours_elapsed >= window_hrs
                status["window_lapsed"] = hours_elapsed > window_hrs * 3
                if status["window_lapsed"]:
                    status["warning"] = "Inter-coat window may have lapsed — re-prep/scuff may be required"
            except Exception:
                pass
        result.append(status)
    return {"status": "ok", "job_id": job_id, "system": system,
            "inter_coat_window_hrs": window_hrs, "coats": result}

@app.post("/job/{job_id}/photos")
async def upload_job_photo(job_id: str, stage: str = Form("general"),
                            area: str = Form(""),
                            file: UploadFile = File(...),
                            current_user: dict = Depends(get_current_user)):
    """P26: Photo upload tied to job/area/stage."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    photo_id = f"photo_{job_id}_{int(datetime.now().timestamp() * 1000)}"
    safe_name = os.path.basename(file.filename or "photo.jpg")
    file_path = os.path.join(PHOTOS_DIR, f"{photo_id}_{safe_name}")
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    photo = {"id": photo_id, "filename": safe_name, "filepath": file_path,
             "stage": stage, "area": area, "taken_by": current_user["email"],
             "taken_at": datetime.now().isoformat(), "size_bytes": len(content)}
    job.setdefault("photos", []).append(photo)
    save_db(db)
    return {"status": "ok", "photo_id": photo_id, "stage": stage, "area": area}

@app.get("/job/{job_id}/photos")
async def get_job_photos(job_id: str, stage: Optional[str] = None,
                          current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    photos = job.get("photos", [])
    if stage:
        photos = [p for p in photos if p.get("stage") == stage]
    return {"status": "ok", "job_id": job_id, "photos": photos}

@app.get("/job/{job_id}/punch-items")
async def get_punch_items(job_id: str, current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "punch_items": job.get("punch_items", [])}

@app.post("/job/{job_id}/punch-items")
async def add_punch_item(job_id: str, req: PunchItemRequest,
                          current_user: dict = Depends(get_current_user)):
    """P27: Add a punch list item."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    item = {"id": f"punch_{len(job.get('punch_items', [])) + 1}",
            "description": req.description, "area": req.area,
            "assignee": req.assignee, "photo_ref": req.photo_ref,
            "status": "open", "source": "manual",
            "created_by": current_user["email"], "created_at": datetime.now().isoformat()}
    job.setdefault("punch_items", []).append(item)
    save_db(db)
    return {"status": "ok", "punch_item": item}

@app.put("/job/{job_id}/punch-items/{item_id}")
async def update_punch_item(job_id: str, item_id: str, req: PunchItemUpdate,
                             current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for item in job.get("punch_items", []):
        if item.get("id") == item_id:
            item["status"] = req.status
            if req.notes:
                item["notes"] = req.notes
            item["updated_by"] = current_user["email"]
            item["updated_at"] = datetime.now().isoformat()
            save_db(db)
            return {"status": "ok", "punch_item": item}
    raise HTTPException(status_code=404, detail="Punch item not found")

@app.get("/job/{job_id}/warranty")
async def get_warranty(job_id: str, current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "job_id": job_id, "warranty": job.get("warranty")}

@app.post("/job/{job_id}/warranty")
async def set_warranty(job_id: str, req: WarrantyRequest,
                        current_user: dict = Depends(get_manager_or_above)):
    """P29 / O49: Manufacturer warranty registration."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    w = job.setdefault("warranty", {})
    for field in ("manufacturer", "warranty_type", "term_years", "required_mil",
                  "install_date", "registration_deadline", "cert_number",
                  "registered", "renewal_recoat_due"):
        val = getattr(req, field, None)
        if val is not None:
            w[field] = val
    w["updated_at"] = datetime.now().isoformat()
    if req.install_date and req.term_years and not req.renewal_recoat_due:
        try:
            install = datetime.fromisoformat(req.install_date)
            target_year = install.year + int(req.term_years)
            try:
                renewal = install.replace(year=target_year)
            except ValueError:
                # Feb-29 install landing on a non-leap anniversary — clamp to Feb 28.
                renewal = install.replace(year=target_year, day=28)
            w["renewal_recoat_due"] = renewal.strftime("%Y-%m-%d")
        except Exception:
            pass
    save_db(db)
    return {"status": "ok", "warranty": w}


# ═══════════════════════════════════════════════════════════════════════════════
# S-phase — Sales, Estimating Pipeline & CRM
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/pipeline")
async def get_pipeline(current_user: dict = Depends(get_current_user)):
    """S30: Sales pipeline — all opportunities by stage."""
    db = load_db()
    by_stage: Dict[str, list] = {}
    for oid, opp in db.get("opportunities", {}).items():
        s = opp.get("stage", "New Lead")
        entry = {k: opp.get(k) for k in ("id", "client_name", "address", "rep", "source",
                                          "first_touch_at", "sla_due", "stage", "job_id")}
        if isManagerOrAbove := current_user.get("role") in ("manager", "super_admin"):
            entry["contract_value"] = opp.get("contract_value")
        by_stage.setdefault(s, []).append(entry)
    return {"status": "ok", "pipeline": by_stage,
            "stages": ["New Lead", "Site Survey", "Measured/Cores", "Estimating",
                       "Proposal", "Negotiation", "Won", "Lost"]}

@app.put("/pipeline/{opportunity_id}/stage")
async def advance_opp_stage(opportunity_id: str, req: PipelineStageUpdate,
                             current_user: dict = Depends(get_current_user)):
    db = load_db()
    opp = db.get("opportunities", {}).get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    old_stage = opp.get("stage")
    opp["stage"] = req.stage
    opp.setdefault("timeline", []).append({
        "event": "stage_changed", "from": old_stage, "to": req.stage,
        "notes": req.notes, "by": current_user["email"], "at": datetime.now().isoformat()
    })
    if req.stage == "Won" and opp.get("job_id"):
        job = db["jobs"].get(opp["job_id"])
        if job:
            job["workflow_stage"] = "Won"
            _sync_to_roofr({"job_id": opp["job_id"], "workflow_stage": "Won",
                             "updated_by": current_user["email"],
                             "updated_at": datetime.now().isoformat()})
    save_db(db)
    return {"status": "ok", "opportunity_id": opportunity_id, "stage": req.stage}

@app.post("/pipeline/{opportunity_id}/convert")
async def convert_opportunity_to_job(opportunity_id: str, req: ConvertToJobRequest,
                                     current_user: dict = Depends(get_manager_or_above)):
    """P1-1: Convert/link an opportunity to a job — the keystone link between the
    sales pipeline and production. Sets opp.job_id <-> job.origin_opportunity_id so
    the Won-stage sync and e-sign auto-Won handoff (which both require opp.job_id)
    actually fire. Idempotent: re-running returns the already-linked job."""
    db = load_db()
    opp = db.get("opportunities", {}).get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    jobs = db.setdefault("jobs", {})

    # Already linked → no-op (idempotent).
    existing = opp.get("job_id")
    if existing and existing in jobs:
        return {"status": "ok", "job_id": existing, "created": False,
                "message": "Opportunity already linked to a job"}

    created = False
    if req.link_job_id:
        if req.link_job_id not in jobs:
            raise HTTPException(status_code=404, detail="link_job_id not found")
        job_id = req.link_job_id
    else:
        job_id = f"opp-{opportunity_id}"
        if job_id not in jobs:
            jobs[job_id] = {
                "job_id": job_id,
                "client_name": opp.get("client_name"),
                "address": opp.get("address"),
                "customer_phone": opp.get("phone") or opp.get("customer_phone"),
                "customer_email": opp.get("email") or opp.get("customer_email"),
                "status": "Pending",
                "workflow_stage": req.workflow_stage or opp.get("stage") or "Won",
                "source": opp.get("source"),
                "rep": opp.get("rep"),
                "contract_value": opp.get("contract_value"),
                "images": [],
                "notes": [],
                "created_by": current_user["email"],
                "created_at": datetime.now().isoformat(),
            }
            created = True

    # Establish the bidirectional link.
    opp["job_id"] = job_id
    jobs[job_id]["origin_opportunity_id"] = opportunity_id
    now = datetime.now().isoformat()
    opp.setdefault("timeline", []).append({
        "event": "converted_to_job", "job_id": job_id, "created": created,
        "by": current_user["email"], "at": now})
    jobs[job_id].setdefault("notes", []).append({
        "note": f"Linked from opportunity {opportunity_id}",
        "added_by": current_user["email"], "added_at": now})
    save_db(db)
    return {"status": "ok", "job_id": job_id, "created": created,
            "opportunity_id": opportunity_id,
            "message": ("Job created and linked" if created else "Linked to existing job")}

@app.delete("/pipeline/{opportunity_id}")
async def delete_opportunity(opportunity_id: str,
                             current_user: dict = Depends(get_super_admin)):
    """Delete an opportunity. Super-admin only — used to clear test/duplicate
    leads that the lead door cannot otherwise remove."""
    db = load_db()
    opp = db.get("opportunities", {}).get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    del db["opportunities"][opportunity_id]
    save_db(db)
    return {"status": "ok", "message": "Opportunity deleted",
            "opportunity_id": opportunity_id}

@app.post("/pipeline/{opportunity_id}/cadence")
async def set_cadence(opportunity_id: str, req: ContactLogRequest,
                      current_user: dict = Depends(get_current_user)):
    """S31 (P1-3): Log a cadence step and set when the NEXT follow-up is due.
    `next_followup_due` is what the pipeline-alerts scan watches for overdue
    follow-ups, so this is a real cadence engine, not just a log."""
    db = load_db()
    opp = db.get("opportunities", {}).get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    due_at = req.due_at or (datetime.now() + timedelta(days=3)).isoformat()
    step = {"contact_type": req.contact_type, "summary": req.summary,
            "due_at": due_at, "by": current_user["email"], "at": datetime.now().isoformat()}
    opp.setdefault("cadence_log", []).append(step)
    opp["next_followup_due"] = due_at
    opp.setdefault("timeline", []).append({"event": "cadence_step", **step})
    save_db(db)
    return {"status": "ok", "cadence_step": step, "next_followup_due": due_at}

@app.post("/pipeline/{opportunity_id}/win-loss")
async def log_win_loss(opportunity_id: str, req: WinLossRequest,
                        current_user: dict = Depends(get_manager_or_above)):
    """S32: Record win/loss with coating-specific loss reason."""
    db = load_db()
    opp = db.get("opportunities", {}).get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opp["stage"] = "Won" if req.outcome == "won" else "Lost"
    opp["outcome"] = req.outcome
    opp["loss_reason"] = req.loss_reason
    opp["outcome_notes"] = req.notes
    opp["closed_at"] = datetime.now().isoformat()
    if req.contract_value:
        opp["contract_value"] = req.contract_value
    opp.setdefault("timeline", []).append({
        "event": f"marked_{req.outcome}", "loss_reason": req.loss_reason,
        "by": current_user["email"], "at": datetime.now().isoformat()
    })
    save_db(db)
    return {"status": "ok", "outcome": req.outcome, "stage": opp["stage"]}

@app.get("/sales/win-loss")
async def win_loss_report(current_user: dict = Depends(get_manager_or_above)):
    """S32: Win-rate rollups by source/rep/loss reason."""
    db = load_db()
    wins = losses = 0
    by_reason: Dict[str, int] = {}
    by_rep: Dict[str, dict] = {}
    for opp in db.get("opportunities", {}).values():
        outcome = opp.get("outcome")
        if not outcome:
            continue
        rep = opp.get("rep") or "unassigned"
        rep_data = by_rep.setdefault(rep, {"won": 0, "lost": 0, "total_value": 0})
        if outcome == "won":
            wins += 1
            rep_data["won"] += 1
            rep_data["total_value"] += float(opp.get("contract_value") or 0)
        elif outcome == "lost":
            losses += 1
            rep_data["lost"] += 1
            reason = opp.get("loss_reason") or "unknown"
            by_reason[reason] = by_reason.get(reason, 0) + 1
    total = wins + losses
    return {"status": "ok", "wins": wins, "losses": losses, "total_closed": total,
            "win_rate_pct": round(wins / total * 100, 1) if total else 0,
            "by_loss_reason": by_reason, "by_rep": by_rep}

@app.post("/pipeline/{opportunity_id}/esign-send")
async def esign_send(opportunity_id: str, req: ESignRequest,
                      current_user: dict = Depends(get_manager_or_above)):
    """S33 / O57: Route a document for e-signature."""
    db = load_db()
    opp = db.get("opportunities", {}).get(opportunity_id) or db["jobs"].get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity or job not found")
    esign_record = {
        "document_id": req.document_id, "document_type": req.document_type,
        "recipient_email": req.recipient_email, "recipient_name": req.recipient_name,
        "status": "sent", "sent_by": current_user["email"],
        "sent_at": datetime.now().isoformat(),
    }
    if ESIGN_WEBHOOK_URL:
        try:
            import requests
            payload = {**esign_record, "opportunity_id": opportunity_id,
                       "message": req.message or f"Please sign the {req.document_type}"}
            r = requests.post(ESIGN_WEBHOOK_URL, json=payload, timeout=10)
            r.raise_for_status()
            esign_record["status"] = "sent_via_webhook"
        except Exception as e:
            esign_record["note"] = f"webhook error: {e}"
    opp.setdefault("esign_records", []).append(esign_record)
    opp.setdefault("timeline", []).append({"event": "esign_sent", **esign_record})
    save_db(db)
    return {"status": "ok", "esign_record": esign_record,
            "note": "Configure ESIGN_WEBHOOK_URL to route via DocuSign/Zapier" if not ESIGN_WEBHOOK_URL else ""}


def _apply_won_handoff(db: dict, opp: dict, actor: str) -> None:
    """Mark an opportunity Won and sync its linked job to Roofr (S33/O57 handoff)."""
    opp["stage"] = "Won"
    opp["outcome"] = "won"
    opp.setdefault("timeline", []).append({"event": "marked_won", "by": actor,
                                           "at": datetime.now().isoformat()})
    job_id = opp.get("job_id")
    if job_id and job_id in db["jobs"]:
        db["jobs"][job_id]["workflow_stage"] = "Won"
        _sync_to_roofr({"job_id": job_id, "workflow_stage": "Won", "updated_by": actor,
                        "updated_at": datetime.now().isoformat()})


@app.post("/esign/webhook")
async def esign_webhook(payload: ESignWebhook):
    """S33/O57: inbound e-sign callback. On a 'signed' event, mark the matching
    esign record signed, attach the executed PDF reference, and (for an
    opportunity) flip the stage to Won and fire the production handoff."""
    if payload.secret != ESIGN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid e-sign webhook secret")
    db = load_db()
    # Resolve the target by explicit id, else by scanning esign_records for the document.
    target, target_kind = None, None
    if payload.opportunity_id:
        target = db.get("opportunities", {}).get(payload.opportunity_id)
        target_kind = "opportunity"
    if target is None and payload.job_id:
        target = db["jobs"].get(payload.job_id)
        target_kind = "job"
    if target is None and payload.document_id:
        for opp in db.get("opportunities", {}).values():
            if any(r.get("document_id") == payload.document_id for r in opp.get("esign_records", [])):
                target, target_kind = opp, "opportunity"
                break
        if target is None:
            for job in db["jobs"].values():
                if any(r.get("document_id") == payload.document_id for r in job.get("esign_records", [])):
                    target, target_kind = job, "job"
                    break
    if target is None:
        raise HTTPException(status_code=404, detail="No matching opportunity/job for this e-sign event")
    # Update (or append) the matching esign record.
    matched = next((r for r in target.get("esign_records", [])
                    if payload.document_id and r.get("document_id") == payload.document_id), None)
    if matched is None:
        matched = {"document_id": payload.document_id}
        target.setdefault("esign_records", []).append(matched)
    matched["status"] = payload.status
    matched["signed_at"] = datetime.now().isoformat()
    if payload.signed_pdf_document_id:
        matched["signed_pdf_document_id"] = payload.signed_pdf_document_id
    if payload.signed_pdf_url:
        matched["signed_pdf_url"] = payload.signed_pdf_url
    target.setdefault("timeline", []).append({"event": f"esign_{payload.status}",
        "document_id": payload.document_id, "at": datetime.now().isoformat()})
    advanced_to_won = False
    if payload.status == "signed" and target_kind == "opportunity":
        _apply_won_handoff(db, target, "esign_webhook")
        advanced_to_won = True
    save_db(db)
    return {"status": "ok", "matched_kind": target_kind,
            "esign_status": payload.status, "advanced_to_won": advanced_to_won}

@app.post("/job/{job_id}/review-request")
async def schedule_review_request(job_id: str, req: ReviewRequest,
                                   current_user: dict = Depends(get_manager_or_above)):
    """S34: Queue a post-cure review-ask."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    warranty = job.get("warranty") or {}
    install_date = warranty.get("install_date") or datetime.now().strftime("%Y-%m-%d")
    try:
        install_dt = datetime.fromisoformat(install_date)
        send_after = (install_dt + timedelta(days=14)).isoformat()
    except Exception:
        send_after = datetime.now().isoformat()
    record = {"platform": req.platform, "message": req.message,
              "send_after": send_after, "status": "queued",
              "queued_by": current_user["email"], "queued_at": datetime.now().isoformat()}
    job.setdefault("review_requests", []).append(record)
    save_db(db)
    return {"status": "ok", "review_request": record}

@app.get("/renewals")
async def renewals_list(current_user: dict = Depends(get_manager_or_above)):
    """S35: List jobs due for renewal re-coat."""
    db = load_db()
    now = datetime.now()
    results = []
    for jid, job in db.get("jobs", {}).items():
        warranty = job.get("warranty") or {}
        due_str = warranty.get("renewal_recoat_due")
        if not due_str:
            continue
        try:
            due = datetime.fromisoformat(due_str)
            days_until = (due - now).days
            results.append({
                "job_id": jid, "client": job.get("client_name"),
                "address": job.get("address"), "system": (job.get("budget") or {}).get("system"),
                "renewal_due": due_str, "days_until_due": days_until,
                "warranty_type": warranty.get("warranty_type"),
                "original_scope": {
                    "system": (job.get("budget") or {}).get("system"),
                    "sqft": (job.get("budget") or {}).get("sqft"),
                    "dry_mil_target": (job.get("budget") or {}).get("dry_mil_target"),
                }
            })
        except Exception:
            pass
    results.sort(key=lambda r: r.get("days_until_due", 9999))
    return {"status": "ok", "renewals": results, "total": len(results)}

@app.get("/sales/performance")
async def rep_performance(current_user: dict = Depends(get_manager_or_above)):
    """S36 (P1-6): Territory & rep performance dashboard."""
    db = load_db()
    by_rep: Dict[str, dict] = {}
    by_territory: Dict[str, dict] = {}

    def _tally(bucket: dict, key: str, opp: dict):
        d = bucket.setdefault(key, {"leads": 0, "won": 0, "lost": 0, "open": 0,
                                    "total_value": 0, "won_value": 0})
        d["leads"] += 1
        outcome = opp.get("outcome")
        if outcome == "won":
            d["won"] += 1
            d["won_value"] += float(opp.get("contract_value") or 0)
            d["total_value"] += float(opp.get("contract_value") or 0)
        elif outcome == "lost":
            d["lost"] += 1
        else:
            d["open"] += 1

    for opp in db.get("opportunities", {}).values():
        _tally(by_rep, opp.get("rep") or "unassigned", opp)
        _tally(by_territory, opp.get("territory") or "unassigned", opp)
    for bucket in (by_rep, by_territory):
        for d in bucket.values():
            total_closed = d["won"] + d["lost"]
            d["win_rate_pct"] = round(d["won"] / total_closed * 100, 1) if total_closed else 0
    return {"status": "ok", "by_rep": by_rep, "by_territory": by_territory}


@app.get("/sales/alerts")
async def sales_alerts(current_user: dict = Depends(get_manager_or_above)):
    """P1-3/P1-5: read the latest pipeline-alerts snapshot (overdue follow-ups +
    SLA breaches) that the pipeline_alerts cron task computes."""
    db = load_db()
    return {"status": "ok", **db.get("pipeline_alerts",
            {"sla_breaches": [], "overdue_followups": [], "scanned_at": None})}


@app.post("/job/{job_id}/referral")
async def add_referral(job_id: str, req: ReferralRequest,
                       current_user: dict = Depends(get_manager_or_above)):
    """S34 (P1-4): capture a referral from a customer/job."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    referral = {"referrer_name": req.referrer_name or job.get("client_name"),
                "referred_name": req.referred_name, "referred_contact": req.referred_contact,
                "notes": req.notes, "captured_by": current_user["email"],
                "captured_at": datetime.now().isoformat()}
    job.setdefault("referrals", []).append(referral)
    save_db(db)
    return {"status": "ok", "referral": referral}

@app.get("/pipeline/{opportunity_id}/timeline")
async def opp_timeline(opportunity_id: str, current_user: dict = Depends(get_current_user)):
    """S38: Opportunity timeline & comm log."""
    db = load_db()
    opp = db.get("opportunities", {}).get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return {"status": "ok", "opportunity_id": opportunity_id,
            "timeline": opp.get("timeline", []),
            "cadence_log": opp.get("cadence_log", [])}


# ═══════════════════════════════════════════════════════════════════════════════
# P2-10 — Unified communications inbox (email + SMS, threaded per contact/job)
# ═══════════════════════════════════════════════════════════════════════════════
# Messages live in db["messages"] keyed by id. A "thread" is all messages sharing
# a normalized contact (email lowercased / phone last-10-digits), channel-prefixed
# so an email and a phone never collide. Inbound arrives via the secret-checked
# /inbox/webhook (Zapier email-parser / Twilio inbound SMS). Outbound goes through
# the existing email/SMS dispatch (dormant-safe: queues until the webhook is set).

def _thread_key(channel: str, contact: str) -> str:
    c = (contact or "").strip().lower()
    if channel == "sms":
        digits = "".join(ch for ch in c if ch.isdigit())
        return "sms:" + (digits[-10:] if digits else "unknown")
    return "email:" + (c if c else "unknown")


def _match_contact(db: dict, channel: str, contact: str):
    """Best-effort link of a contact to an existing job and/or opportunity."""
    key = _thread_key(channel, contact)
    jf = "customer_phone" if channel == "sms" else "customer_email"
    of = "phone" if channel == "sms" else "email"
    job_id = next((jid for jid, j in db.get("jobs", {}).items()
                   if j.get(jf) and _thread_key(channel, j[jf]) == key), None)
    opp_id = next((oid for oid, o in db.get("opportunities", {}).items()
                   if o.get(of) and _thread_key(channel, o[of]) == key), None)
    return job_id, opp_id


def _record_message(db: dict, *, channel, direction, contact, body,
                    subject=None, name=None, by=None, status):
    job_id, opp_id = _match_contact(db, channel, contact or "")
    mid = f"msg_{int(datetime.now().timestamp() * 1000)}_{len(db.get('messages', {}))}"
    msg = {"id": mid, "channel": channel, "direction": direction,
           "contact": contact, "name": name, "subject": subject, "body": body,
           "thread_key": _thread_key(channel, contact or ""),
           "job_id": job_id, "opportunity_id": opp_id,
           "status": status, "at": datetime.now().isoformat(), "by": by}
    db.setdefault("messages", {})[mid] = msg
    return msg


@app.post("/inbox/webhook")
async def inbox_webhook(payload: InboxWebhook):
    """P2-10 inbound door: record an incoming customer email/SMS into the inbox."""
    if payload.secret != INBOX_SECRET:
        raise HTTPException(status_code=403, detail="Invalid inbox webhook secret")
    db = load_db()
    contact = payload.contact or (payload.data or {}).get("from")
    msg = _record_message(db, channel=payload.channel, direction="inbound",
                          contact=contact, body=payload.body, subject=payload.subject,
                          name=payload.name, status="unread")
    save_db(db)
    return {"status": "ok", "message_id": msg["id"], "thread_key": msg["thread_key"],
            "linked_job": msg["job_id"], "linked_opportunity": msg["opportunity_id"]}


@app.post("/inbox/send")
async def inbox_send(req: InboxSend, current_user: dict = Depends(get_manager_or_above)):
    """P2-10 outbound: send an email/SMS and record it in the thread. Sending is
    dormant-safe — it queues in the outbox until EMAIL_/SMS_WEBHOOK_URL is set."""
    db = load_db()
    if req.channel == "sms":
        result = _sms_dispatch(db, {"to": req.to, "message": req.body,
                                    "sent_by": current_user["email"],
                                    "sent_at": datetime.now().isoformat()})
    else:
        result = _email_dispatch(db, {"to": req.to, "subject": req.subject or "(no subject)",
                                      "body": req.body, "sent_by": current_user["email"],
                                      "sent_at": datetime.now().isoformat()})
    status = "sent" if result.get("status") == "ok" else "queued"
    msg = _record_message(db, channel=req.channel, direction="outbound",
                          contact=req.to, body=req.body, subject=req.subject,
                          by=current_user["email"], status=status)
    save_db(db)
    return {"status": "ok", "dispatch": result, "message_id": msg["id"],
            "thread_key": msg["thread_key"]}


@app.get("/inbox")
async def inbox_threads(current_user: dict = Depends(get_manager_or_above)):
    """P2-10: list threads (grouped by contact), newest first, with unread counts."""
    db = load_db()
    threads: Dict[str, dict] = {}
    for m in db.get("messages", {}).values():
        tk = m["thread_key"]
        t = threads.setdefault(tk, {"thread_key": tk, "channel": m["channel"],
            "contact": m.get("contact"), "name": m.get("name"), "job_id": m.get("job_id"),
            "opportunity_id": m.get("opportunity_id"), "count": 0, "unread": 0,
            "last_at": "", "last_snippet": "", "last_direction": ""})
        t["count"] += 1
        if m["direction"] == "inbound" and m.get("status") == "unread":
            t["unread"] += 1
        if (m.get("at") or "") >= t["last_at"]:
            t["last_at"] = m.get("at") or ""
            t["last_snippet"] = (m.get("body") or "")[:90]
            t["last_direction"] = m["direction"]
            t["name"] = m.get("name") or t["name"]
        t["job_id"] = t["job_id"] or m.get("job_id")
        t["opportunity_id"] = t["opportunity_id"] or m.get("opportunity_id")
    for t in threads.values():
        if t["job_id"] and t["job_id"] in db.get("jobs", {}):
            t["client_name"] = db["jobs"][t["job_id"]].get("client_name")
        elif t["opportunity_id"] and t["opportunity_id"] in db.get("opportunities", {}):
            t["client_name"] = db["opportunities"][t["opportunity_id"]].get("client_name")
        else:
            t["client_name"] = t.get("name")
    ordered = sorted(threads.values(), key=lambda x: x["last_at"], reverse=True)
    return {"status": "ok", "threads": ordered,
            "total_unread": sum(t["unread"] for t in ordered)}


@app.get("/inbox/thread")
async def inbox_thread(key: str, current_user: dict = Depends(get_manager_or_above)):
    """P2-10: all messages in one thread (oldest first)."""
    db = load_db()
    msgs = sorted([m for m in db.get("messages", {}).values() if m["thread_key"] == key],
                  key=lambda m: m.get("at") or "")
    if not msgs:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"status": "ok", "thread_key": key, "messages": msgs,
            "job_id": next((m["job_id"] for m in msgs if m.get("job_id")), None),
            "opportunity_id": next((m["opportunity_id"] for m in msgs if m.get("opportunity_id")), None)}


@app.post("/inbox/thread/read")
async def inbox_mark_read(key: str, current_user: dict = Depends(get_manager_or_above)):
    """P2-10: mark every unread inbound message in a thread as read."""
    db = load_db()
    n = 0
    for m in db.get("messages", {}).values():
        if m["thread_key"] == key and m["direction"] == "inbound" and m.get("status") == "unread":
            m["status"] = "read"
            n += 1
    if n:
        save_db(db)
    return {"status": "ok", "marked_read": n}


# ═══════════════════════════════════════════════════════════════════════════════
# C-phase — Scheduling, Dispatch & Crew
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/schedule/assignments")
async def get_assignments(week_start: Optional[str] = None,
                           current_user: dict = Depends(get_current_user)):
    """C39: Crew calendar — all assignments, optionally filtered by week."""
    db = load_db()
    assignments = []
    for jid, job in db.get("jobs", {}).items():
        for asgn in job.get("schedule_assignments", []):
            a = {**asgn, "job_id": jid, "client": job.get("client_name"),
                 "address": job.get("address"),
                 "system": (job.get("budget") or {}).get("system"),
                 "weather_status": job.get("weather_status")}
            if current_user.get("role") not in ("manager", "super_admin"):
                a.pop("contract_value", None)
            if week_start:
                if a.get("date", "") >= week_start:
                    assignments.append(a)
            else:
                assignments.append(a)
    assignments.sort(key=lambda a: a.get("date", ""))
    return {"status": "ok", "assignments": assignments}

@app.post("/schedule/assignments")
async def add_assignment(req: AssignmentRequest,
                          current_user: dict = Depends(get_manager_or_above)):
    db = load_db()
    job = db["jobs"].get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Hard-block double-booking a SPECIFIC rig (C42) when an equipment_id is given;
    # otherwise fall back to the looser same-day spray-phase heuristic (C39) — and
    # only against other un-rigged assignments so two crews each with their own rig
    # are no longer falsely rejected.
    if req.equipment_id:
        if req.equipment_id not in db.get("equipment", {}):
            raise HTTPException(status_code=404, detail="Equipment not found")
        for jid, j in db["jobs"].items():
            for a in j.get("schedule_assignments", []):
                if a.get("date") == req.date and a.get("equipment_id") == req.equipment_id:
                    rig = db["equipment"][req.equipment_id].get("name", req.equipment_id)
                    return {"status": "conflict",
                            "message": f"{rig} already booked on {req.date} (job {jid})"}
    elif req.phase and "spray" in req.phase.lower():
        for jid, j in db["jobs"].items():
            for a in j.get("schedule_assignments", []):
                if (a.get("date") == req.date and "spray" in (a.get("phase") or "").lower()
                        and jid != req.job_id and not a.get("equipment_id")):
                    return {"status": "conflict", "message": f"Sprayer already assigned to job {jid} on {req.date}"}
    asgn = {"id": f"asgn_{int(datetime.now().timestamp() * 1000)}",
            "crew": req.crew, "date": req.date, "phase": req.phase,
            "equipment_id": req.equipment_id,
            "notes": req.notes, "created_by": current_user["email"],
            "created_at": datetime.now().isoformat()}
    job.setdefault("schedule_assignments", []).append(asgn)
    save_db(db)
    return {"status": "ok", "assignment": asgn}

@app.get("/schedule/weather-verdicts")
async def schedule_weather_verdicts(current_user: dict = Depends(get_current_user)):
    """C40: Today's weather verdict for all scheduled jobs."""
    db = load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    results = []
    for jid, job in db.get("jobs", {}).items():
        today_assignments = [a for a in job.get("schedule_assignments", [])
                             if a.get("date") == today]
        if not today_assignments:
            continue
        results.append({
            "job_id": jid, "client": job.get("client_name"),
            "address": job.get("address"),
            "system": (job.get("budget") or {}).get("system"),
            "verdict": (job.get("weather_status") or {}).get("verdict", "UNKNOWN"),
            "reason": (job.get("weather_status") or {}).get("reason"),
            "checked_at": (job.get("weather_status") or {}).get("checked_at"),
            "assignments": today_assignments,
        })
    return {"status": "ok", "date": today, "scheduled_jobs": results}

@app.get("/equipment")
async def list_equipment(current_user: dict = Depends(get_manager_or_above)):
    # day_rate is cost data — keep the registry manager+ only (no field-crew UI uses it).
    db = load_db()
    return {"status": "ok", "equipment": db.get("equipment", {})}

@app.post("/equipment")
async def add_equipment(req: EquipmentRequest,
                         current_user: dict = Depends(get_manager_or_above)):
    """C42: Equipment/sprayer registry."""
    db = load_db()
    eid = f"eq_{int(datetime.now().timestamp() * 1000)}"
    item = {"id": eid, "name": req.name, "type": req.equipment_type,
            "day_rate": req.day_rate, "notes": req.notes,
            "added_by": current_user["email"], "added_at": datetime.now().isoformat()}
    db.setdefault("equipment", {})[eid] = item
    save_db(db)
    return {"status": "ok", "equipment": item}

@app.get("/schedule/material-staging")
async def material_staging(days_out: int = 3,
                            current_user: dict = Depends(get_manager_or_above)):
    """C43: Flag un-staged jobs within N days of first coat."""
    db = load_db()
    cutoff = (datetime.now() + timedelta(days=days_out)).strftime("%Y-%m-%d")
    flags = []
    for jid, job in db.get("jobs", {}).items():
        assignments = sorted(job.get("schedule_assignments", []), key=lambda a: a.get("date", ""))
        if not assignments:
            continue
        first_date = assignments[0].get("date", "")
        if not (datetime.now().strftime("%Y-%m-%d") <= first_date <= cutoff):
            continue
        budget = job.get("budget") or {}
        est = budget.get("est_gallons") or {}
        has_material = any(
            exp for exp in [
                (db.get("financials", {}).get("expenses", {})).get(eid, {})
                for eid in job.get("expenses", [])
            ] if "material" in (exp.get("category") or "").lower()
        )
        if not has_material and est:
            flags.append({"job_id": jid, "client": job.get("client_name"),
                          "first_date": first_date, "est_gallons": est,
                          "flag": "material_not_staged"})
    return {"status": "ok", "days_out": days_out, "unstaged_jobs": flags}

@app.post("/dispatch/send")
async def send_dispatch_sheet(req: DispatchRequest,
                               current_user: dict = Depends(get_manager_or_above)):
    """C44: Send daily dispatch sheet to crew."""
    db = load_db()
    job_ids = req.job_ids or [
        jid for jid, j in db["jobs"].items()
        if any(a.get("date") == req.date and (not req.crew or a.get("crew") == req.crew)
               for a in j.get("schedule_assignments", []))
    ]
    lines = []
    for jid in job_ids:
        job = db["jobs"].get(jid)
        if not job:
            continue
        budget = job.get("budget") or {}
        weather = job.get("weather_status") or {}
        lines.append(
            f"Job {jid}: {job.get('client_name')} — {job.get('address')}\n"
            f"  System: {budget.get('system')} | Target mil: {budget.get('dry_mil_target')}\n"
            f"  Weather: {weather.get('verdict', 'UNKNOWN')} — {weather.get('reason', '')}"
        )
    body = f"Dispatch Sheet — {req.date}" + ("\n" + f"Crew: {req.crew}" if req.crew else "") + "\n\n" + "\n\n".join(lines)
    sent = _send_email_or_log(db, "crew@trulineroofing.com", f"Dispatch {req.date}", body, current_user["email"])
    return {"status": "ok", "dispatch_body": body, "email_status": sent,
            "note": "No financial data included (field-safe)"}

@app.get("/job/{job_id}/timelogs")
async def get_timelogs(job_id: str, current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "timelogs": job.get("timelogs", [])}

@app.post("/job/{job_id}/timelogs")
async def add_timelog(job_id: str, req: TimelogRequest,
                       current_user: dict = Depends(get_current_user)):
    """C45: Crew time check-in; feeds A8 labor costing."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    hours = 0.0
    if req.depart:
        try:
            arrive = datetime.fromisoformat(req.arrive)
            depart = datetime.fromisoformat(req.depart)
            hours = round((depart - arrive).total_seconds() / 3600, 2)
        except Exception:
            pass
    tl = {"employee": req.employee, "arrive": req.arrive, "depart": req.depart,
          "hours": hours, "hours_type": req.hours_type, "geo": req.geo,
          "logged_by": current_user["email"], "logged_at": datetime.now().isoformat()}
    job.setdefault("timelogs", []).append(tl)
    save_db(db)
    return {"status": "ok", "timelog": tl}


# ═══════════════════════════════════════════════════════════════════════════════
# O-phase — Office Admin, Compliance & Safety
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/parties")
async def list_parties(current_user: dict = Depends(get_manager_or_above)):
    db = load_db()
    return {"status": "ok", "parties": db.get("parties", {})}

@app.post("/parties")
async def create_party(req: PartyRequest,
                        current_user: dict = Depends(get_manager_or_above)):
    """O47: Create a sub/vendor compliance profile."""
    db = load_db()
    pid = f"party_{int(datetime.now().timestamp() * 1000)}"
    party = {"id": pid, "name": req.name, "party_type": req.party_type,
             "trade": req.trade, "contact_email": req.contact_email,
             "contact_phone": req.contact_phone, "cois": [], "certs": [],
             "w9": False, "subcontract": False, "cleared": False,
             "created_by": current_user["email"], "created_at": datetime.now().isoformat()}
    db.setdefault("parties", {})[pid] = party
    save_db(db)
    return {"status": "ok", "party": party}

@app.post("/parties/{party_id}/coi")
async def add_coi(party_id: str, req: COIRequest,
                   current_user: dict = Depends(get_manager_or_above)):
    """O46: Add a COI for a sub/vendor."""
    db = load_db()
    party = db.get("parties", {}).get(party_id)
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    coi = {"carrier": req.carrier, "policy_number": req.policy_number,
           "expiry": req.expiry, "gl_limit": req.gl_limit, "wc_limit": req.wc_limit,
           "document_id": req.document_id, "added_at": datetime.now().isoformat()}
    party.setdefault("cois", []).append(coi)
    _recompute_cleared(party)
    save_db(db)
    return {"status": "ok", "coi": coi, "cleared": party.get("cleared")}

@app.put("/parties/{party_id}")
async def update_party(party_id: str, req: PartyUpdate,
                       current_user: dict = Depends(get_manager_or_above)):
    """O47: record W-9 / signed subcontract / contact updates and recompute the
    party's 'cleared to work' status from its documents."""
    db = load_db()
    party = db.get("parties", {}).get(party_id)
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    for field in ("w9", "subcontract", "trade", "contact_email", "contact_phone"):
        val = getattr(req, field, None)
        if val is not None:
            party[field] = val
    _recompute_cleared(party)
    save_db(db)
    return {"status": "ok", "party": party}

@app.get("/compliance/dashboard")
async def compliance_dashboard_route(current_user: dict = Depends(get_manager_or_above)):
    """O52: Rolling compliance dashboard."""
    db = load_db()
    return {"status": "ok", **_compliance_summary(db)}

@app.get("/templates")
async def list_templates(current_user: dict = Depends(get_current_user)):
    db = load_db()
    return {"status": "ok", "templates": db.get("templates", {})}

@app.post("/templates")
async def create_template(req: TemplateRequest,
                           current_user: dict = Depends(get_manager_or_above)):
    """O48: Document template library."""
    db = load_db()
    tid = f"tmpl_{int(datetime.now().timestamp() * 1000)}"
    tmpl = {"id": tid, "name": req.name, "kind": req.kind, "body": req.body,
            "created_by": current_user["email"], "created_at": datetime.now().isoformat()}
    db.setdefault("templates", {})[tid] = tmpl
    save_db(db)
    return {"status": "ok", "template": tmpl}

@app.post("/templates/{template_id}/merge")
async def merge_template_route(template_id: str, job_id: str,
                                 current_user: dict = Depends(get_manager_or_above)):
    """O48: Merge template with job data."""
    db = load_db()
    tmpl = db.get("templates", {}).get(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    merged = _merge_template(tmpl["body"], job)
    return {"status": "ok", "template_id": template_id, "job_id": job_id,
            "merged_output": merged, "kind": tmpl["kind"]}

@app.get("/sds")
async def list_sds(current_user: dict = Depends(get_current_user)):
    """O50: SDS library."""
    db = load_db()
    return {"status": "ok", "sds": db.get("sds", {})}

@app.post("/sds")
async def add_sds(req: SDSRequest, current_user: dict = Depends(get_manager_or_above)):
    db = load_db()
    sid = f"sds_{int(datetime.now().timestamp() * 1000)}"
    sds_entry = {"id": sid, "product": req.product, "manufacturer": req.manufacturer,
                 "document_id": req.document_id, "url": req.url,
                 "notes": req.notes, "added_by": current_user["email"],
                 "added_at": datetime.now().isoformat()}
    db.setdefault("sds", {})[sid] = sds_entry
    save_db(db)
    return {"status": "ok", "sds": sds_entry}

@app.get("/employees")
async def list_employees(current_user: dict = Depends(get_current_user)):
    db = load_db()
    return {"status": "ok", "employees": db.get("employees", {})}

@app.post("/employees")
async def create_employee(req: EmployeeRequest,
                           current_user: dict = Depends(get_manager_or_above)):
    """O51: Employee record."""
    db = load_db()
    eid = f"emp_{int(datetime.now().timestamp() * 1000)}"
    emp = {"id": eid, "name": req.name, "email": req.email, "role": req.role,
           "certs": [], "created_by": current_user["email"],
           "created_at": datetime.now().isoformat()}
    db.setdefault("employees", {})[eid] = emp
    save_db(db)
    return {"status": "ok", "employee": emp}

@app.post("/employees/{employee_id}/certs")
async def add_cert(employee_id: str, req: CertRequest,
                    current_user: dict = Depends(get_manager_or_above)):
    db = load_db()
    emp = db.get("employees", {}).get(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    cert = {"cert_type": req.cert_type, "expiry": req.expiry, "notes": req.notes,
            "added_by": current_user["email"], "added_at": datetime.now().isoformat()}
    emp.setdefault("certs", []).append(cert)
    save_db(db)
    return {"status": "ok", "cert": cert}

@app.post("/job/{job_id}/lien-waiver")
async def create_lien_waiver(job_id: str, req: LienWaiverRequest,
                              current_user: dict = Depends(get_manager_or_above)):
    """O53: Lien waiver generation and tracking."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    waiver_id = f"lw_{int(datetime.now().timestamp() * 1000)}"
    waiver = {
        "id": waiver_id, "waiver_type": req.waiver_type,
        "through_date": req.through_date, "payment_amount": req.payment_amount,
        "claimant_name": req.claimant_name or job.get("client_name"),
        "property_address": job.get("address"),
        "status": "generated", "generated_at": datetime.now().isoformat(),
        "generated_by": current_user["email"],
    }
    job.setdefault("lien_waivers", []).append(waiver)
    save_db(db)
    return {"status": "ok", "waiver": waiver}

@app.get("/job/{job_id}/comm-log")
async def get_comm_log(job_id: str, current_user: dict = Depends(get_current_user)):
    """O54: Customer communication log."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "job_id": job_id, "comm_log": job.get("comm_log", [])}

@app.post("/job/{job_id}/comm-log")
async def add_comm_log(job_id: str, req: ContactLogRequest,
                        current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    entry = {"contact_type": req.contact_type, "summary": req.summary,
             "contact_with": req.contact_with, "direction": req.direction,
             "logged_by": current_user["email"], "logged_at": datetime.now().isoformat()}
    job.setdefault("comm_log", []).append(entry)
    save_db(db)
    return {"status": "ok", "entry": entry}

@app.get("/job/{job_id}/permit")
async def get_permit(job_id: str, current_user: dict = Depends(get_current_user)):
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "permit": job.get("permit")}

@app.post("/job/{job_id}/permit")
async def set_permit(job_id: str, req: PermitRequest,
                      current_user: dict = Depends(get_manager_or_above)):
    """O55: Permit tracker."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job["permit"] = {"permit_type": req.permit_type, "permit_number": req.permit_number,
                     "status": req.status, "jurisdiction": req.jurisdiction,
                     "issued_date": req.issued_date, "updated_at": datetime.now().isoformat()}
    save_db(db)
    return {"status": "ok", "permit": job["permit"]}

@app.post("/job/{job_id}/jha")
async def create_jha(job_id: str, req: JHARequest,
                      current_user: dict = Depends(get_current_user)):
    """O56: Job Hazard Analysis pre-task plan, auto-filled from coating system."""
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    system = req.coating_system or (job.get("budget") or {}).get("system") or "general"
    # Default hazards/controls/PPE by system
    defaults = {
        "silicone": {
            "hazards": ["fall", "solvent_vapors", "overspray", "uv_exposure"],
            "controls": ["anchor_lanyards", "ppe_respirator_half_face", "wind_check_overspray", "sunscreen"],
            "ppe": ["fall_harness", "half_face_respirator_organic_vapor", "safety_glasses", "gloves"],
        },
        "acrylic": {
            "hazards": ["fall", "skin_irritation", "overspray"],
            "controls": ["anchor_lanyards", "barrier_cream", "wind_check_overspray"],
            "ppe": ["fall_harness", "safety_glasses", "gloves", "tyvek_if_windy"],
        },
        "default": {
            "hazards": ["fall", "chemical_exposure", "heat_stress", "overspray"],
            "controls": ["anchor_lanyards", "ppe_appropriate_for_product", "wind_check", "hydration"],
            "ppe": ["fall_harness", "respirator", "safety_glasses", "gloves"],
        }
    }
    defs = defaults.get(system.lower(), defaults["default"])
    jha = {
        "coating_system": system,
        "hazards": req.hazards or defs["hazards"],
        "controls": req.controls or defs["controls"],
        "ppe_required": req.ppe_required or defs["ppe"],
        "created_by": current_user["email"], "created_at": datetime.now().isoformat(),
        "signed_by": [], "status": "active",
    }
    job.setdefault("jhas", []).append(jha)
    save_db(db)
    return {"status": "ok", "jha": jha}

@app.post("/documents/{doc_id}/index")
async def index_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    """I60: Parse and chunk a document for RAG search."""
    db = load_db()
    doc = db["documents"].get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    filepath = doc.get("filepath", "")
    chunks = []
    try:
        if filepath.lower().endswith((".txt", ".md", ".csv")):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif filepath.lower().endswith(".pdf"):
            try:
                import pypdf
                reader = pypdf.PdfReader(filepath)
                text = "\n".join(p.extract_text() or "" for p in reader.pages)
            except ImportError:
                with open(filepath, "rb") as f:
                    raw = f.read()
                text = raw.decode("utf-8", errors="ignore")
        else:
            with open(filepath, "rb") as f:
                raw = f.read()
            text = raw.decode("utf-8", errors="ignore")
        # Split into ~500-char chunks with overlap
        chunk_size = 500
        overlap = 50
        for i in range(0, max(len(text), 1), chunk_size - overlap):
            chunk = text[i:i + chunk_size].strip()
            if chunk:
                chunks.append({"text": chunk, "page": i // chunk_size + 1,
                                "doc_id": doc_id, "filename": doc.get("filename")})
    except Exception as e:
        return {"status": "error", "message": f"Failed to index document: {e}"}
    db.setdefault("doc_chunks", {})[doc_id] = chunks
    save_db(db)
    return {"status": "ok", "doc_id": doc_id, "chunks_indexed": len(chunks)}


# ═══════════════════════════════════════════════════════════════════════════════
# I-phase — AI, Voice & Mobile-First Field UX
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/ai/voice-report")
async def voice_report(req: VoiceReportRequest,
                        current_user: dict = Depends(get_current_user)):
    """I58: Extract structured production log from a voice transcript."""
    client = get_openai_client()
    if client is None:
        raise HTTPException(status_code=503, detail="OpenAI not configured")
    db = load_db()
    job_hint = ""
    if req.job_id:
        job = db["jobs"].get(req.job_id, {})
        job_hint = f"Job {req.job_id} — {job.get('client_name')} at {job.get('address')}."

    extraction_prompt = f"""Extract a structured production log from this field report transcript.
{job_hint}
Today's date: {datetime.now().strftime('%Y-%m-%d')}.

Transcript:
{req.transcript}

Return JSON with these fields (omit fields not mentioned):
{{
  "job_id": "{req.job_id or 'UNKNOWN'}",
  "date": "YYYY-MM-DD",
  "crew": "crew member name(s)",
  "product": "coating product name",
  "gallons_applied": number,
  "sqft_coated": number,
  "wet_mil": [list of wet-mil readings as numbers],
  "hours_by_type": {{"spray": h, "prep": h, "roller": h}},
  "weather": {{"temp": F, "rh": percent, "conditions": "string"}},
  "notes": "any other notes",
  "coat_seq": coat number (1, 2, etc.)
}}"""
    try:
        resp = _create_completion(client, [{"role": "user", "content": extraction_prompt}],
                                   max_completion_tokens=800)
        raw = resp.choices[0].message.content or "{}"
        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        extracted = json.loads(json_match.group(0)) if json_match else {}
    except Exception as e:
        return {"status": "error", "message": f"Extraction failed: {e}", "transcript": req.transcript}

    if not extracted.get("job_id") and req.job_id:
        extracted["job_id"] = req.job_id
    extracted["source"] = "voice_report"
    extracted["needs_confirmation"] = True
    extracted["transcript"] = req.transcript
    extracted["extracted_by"] = current_user["email"]
    extracted["extracted_at"] = datetime.now().isoformat()

    db.setdefault("pending_voice_reports", []).append(extracted)
    save_db(db)
    return {"status": "ok", "extracted": extracted,
            "message": "Review and confirm — POST /production/webhook with PRODUCTION_SECRET to save"}

@app.post("/cron/digest")
async def send_digest(request: Request):
    """I59: Morning ops digest. Two auth modes: a logged-in user's JWT (digest
    goes to that user, scoped to their role), or the CRON_SECRET via the
    X-Cron-Secret header (scheduled callers like a Railway cron / Zapier
    Schedule — digest goes to the super admin). The secret is header-only; it is
    never read from a ?secret= query param, so it can't leak into access logs."""
    current_user = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.decode(auth[7:], SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
            if isinstance(email, str):
                current_user = load_db()["users"].get(email)
        except JWTError:
            current_user = None
    if current_user is None:
        provided_secret = request.headers.get("X-Cron-Secret")
        if provided_secret and provided_secret == CRON_SECRET:
            db_users = load_db().get("users", {})
            admin_email = next((e for e, u in db_users.items()
                                if u.get("role") == "super_admin"), "fred@trulineroofing.com")
            current_user = {"email": admin_email, "role": "super_admin"}
        else:
            raise HTTPException(status_code=401, detail="Not authenticated")
    db = load_db()
    role = current_user.get("role", "user")
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    lines = [f"TruAgent Morning Digest — {today}"]
    def _last_log_age_days(j):
        logs = j.get("production_logs", [])[-1:]
        if not logs:
            return None
        try:
            return (now - datetime.fromisoformat(logs[0].get("date") or today)).days
        except Exception:
            return None  # unparseable/empty date — don't crash, don't flag as stalled

    if role in ("manager", "super_admin"):
        # Stalled jobs (guarded against malformed log dates)
        stalled = [j for j in db["jobs"].values()
                   if j.get("status") in ("In Progress", "In Production", "Approved")
                   and j.get("production_logs")
                   and (_last_log_age_days(j) or 0) > 3]
        if stalled:
            lines.append(f"\n⚠️ Stalled Jobs ({len(stalled)}):")
            for j in stalled[:5]:
                lines.append(f"  - {j.get('client_name')} ({j.get('job_id')})")
        # Gallons over estimate
        over = []
        for j in db["jobs"].values():
            applied = _applied_gallons_by_product(j)
            for prod, est in ((j.get("budget") or {}).get("est_gallons") or {}).items():
                if applied.get(prod, 0) > float(est or 0) * 1.0:
                    over.append(j.get("client_name"))
        if over:
            lines.append(f"\n🚨 Over-gallons ({len(over)}): {', '.join(over[:5])}")
        # Past-due invoices
        buckets = _ar_aging_buckets(db)
        past_due = len(buckets["31_60"]) + len(buckets["61_90"]) + len(buckets["over_90"])
        if past_due:
            lines.append(f"\n💰 Past-due invoices: {past_due}")
        # Unscheduled approved jobs
        unscheduled = [j for j in db["jobs"].values()
                       if j.get("workflow_stage") == "Won" and not j.get("schedule_assignments")]
        if unscheduled:
            lines.append(f"\n📅 Won but unscheduled: {len(unscheduled)} jobs")
    else:
        # Field crew view — today's jobs
        today_jobs = [j for j in db["jobs"].values()
                      if any(a.get("date") == today for a in j.get("schedule_assignments", []))]
        if today_jobs:
            lines.append(f"\nToday's Jobs ({len(today_jobs)}):")
            for j in today_jobs:
                budget = j.get("budget") or {}
                weather = j.get("weather_status") or {}
                lines.append(f"  - {j.get('address')} | {budget.get('system')} | "
                              f"Target mil: {budget.get('dry_mil_target')} | "
                              f"Weather: {weather.get('verdict', '?')}")
    body = "\n".join(lines)
    sent = _send_email_or_log(db, current_user["email"], f"TruAgent Digest {today}", body, "system")
    return {"status": "ok", "digest": body, "email_status": sent}

def _detect_anomalies(db: dict) -> list:
    """I62: over-budget / stalled / past-due / approved-no-start / margin-drop flags."""
    now = datetime.now()
    flags = []
    financials = db.get("financials", {})
    inv_map = financials.get("invoices", {})
    for jid, job in db.get("jobs", {}).items():
        budget = job.get("budget") or {}
        applied = _applied_gallons_by_product(job)
        for prod, est in (budget.get("est_gallons") or {}).items():
            if applied.get(prod, 0) > float(est or 0) * 1.05:
                flags.append({"type": "gallons_overrun", "job_id": jid,
                               "client": job.get("client_name"), "severity": "high"})
        logs = job.get("production_logs") or []
        if logs and job.get("status") in ("In Progress", "In Production"):
            last = logs[-1]
            try:
                last_dt = datetime.fromisoformat(last.get("date") or "")
                if (now - last_dt).days > 5:
                    flags.append({"type": "stalled", "job_id": jid,
                                  "client": job.get("client_name"),
                                  "days_stalled": (now - last_dt).days, "severity": "medium"})
            except Exception:
                pass
        if job.get("workflow_stage") == "Won" and not logs:
            flags.append({"type": "approved_no_start", "job_id": jid,
                          "client": job.get("client_name"), "severity": "low"})
        for inv_id in job.get("invoices", []):
            inv = inv_map.get(inv_id, {})
            if inv.get("status") not in ("paid", "cancelled"):
                try:
                    due = datetime.fromisoformat(inv.get("due_date") or inv.get("date") or "")
                    if (now - due).days > 30:
                        flags.append({"type": "past_due_invoice", "job_id": jid,
                                      "invoice_id": inv_id, "days_past_due": (now - due).days,
                                      "severity": "high"})
                except Exception:
                    pass
        # Margin drop
        live = _job_margin_live(db, job)
        quoted = float(budget.get("quoted_margin") or 0)
        if live is not None and quoted > 0 and live < quoted - 5:
            flags.append({"type": "margin_drop", "job_id": jid,
                          "client": job.get("client_name"),
                          "quoted": quoted, "live": live, "severity": "high"})
    return flags


@app.get("/jobs/anomalies")
async def jobs_anomalies(current_user: dict = Depends(get_manager_or_above)):
    """I62: Anomaly scan — over-budget, stalled, past-due, approved-no-start."""
    db = load_db()
    flags = _detect_anomalies(db)
    return {"status": "ok", "anomaly_flags": flags, "count": len(flags)}


# ─── Scheduler task registry (F4) ────────────────────────────────────────────
# Register the scan tasks the /cron/tick endpoint dispatches. Each persists its
# result so the scan durably "surfaces" (O46/O51 COI/cert scans; I62 anomalies),
# rather than only being computed on-demand by the dashboards.
def _cron_compliance_scan():
    db = load_db()
    summary = _compliance_summary(db)
    db["compliance_alerts"] = {**summary, "scanned_at": summary.get("checked_at")}
    save_db(db)
    return {"cois_flagged": len(summary.get("expiring_cois", [])),
            "certs_flagged": len(summary.get("expiring_certs", [])),
            "sds_gaps": len(summary.get("sds_gaps", []))}


def _cron_anomaly_scan():
    db = load_db()
    flags = _detect_anomalies(db)
    db["anomaly_snapshot"] = {"flags": flags, "scanned_at": datetime.now().isoformat()}
    save_db(db)
    return {"anomalies_flagged": len(flags)}


def _cron_suite_sync_heartbeat():
    """Step 8a: in-hub heartbeat for the suite sync. The real cross-app sync runs
    in the separate truhub-bridge service; this just stamps a last_tick the hub
    dashboard can show so an operator can see the scheduler is alive."""
    db = load_db()
    now = datetime.now().isoformat()
    db["sync_heartbeat"] = {"last_tick": now}
    save_db(db)
    return f"suite sync heartbeat recorded at {now}"


def _cron_pipeline_alerts():
    """P1-3/P1-5: surface overdue follow-ups (cadence next_followup_due in the past)
    and lead-SLA breaches (past sla_due, still 'New Lead', never contacted) into
    db['pipeline_alerts'] so the pipeline view can flag them. db-only; no external send."""
    db = load_db()
    now = datetime.now()
    sla_breaches, overdue_followups = [], []
    for oid, opp in db.get("opportunities", {}).items():
        if opp.get("outcome") in ("won", "lost"):
            continue
        card = {"id": oid, "client_name": opp.get("client_name"),
                "address": opp.get("address"), "rep": opp.get("rep"), "stage": opp.get("stage")}
        sla_due = opp.get("sla_due")
        if sla_due and opp.get("stage") == "New Lead" and not opp.get("cadence_log"):
            try:
                if datetime.fromisoformat(sla_due) < now:
                    sla_breaches.append({**card, "sla_due": sla_due})
            except (ValueError, TypeError):
                pass
        nfd = opp.get("next_followup_due")
        if nfd:
            try:
                if datetime.fromisoformat(nfd) < now:
                    overdue_followups.append({**card, "next_followup_due": nfd})
            except (ValueError, TypeError):
                pass
    db["pipeline_alerts"] = {"sla_breaches": sla_breaches,
                             "overdue_followups": overdue_followups,
                             "scanned_at": now.isoformat()}
    save_db(db)
    return {"sla_breaches": len(sla_breaches), "overdue_followups": len(overdue_followups)}


def _cron_review_flush():
    """P1-4: drain queued post-cure review-asks whose send_after has passed, routing
    them through the email outbox (which itself stays dormant-safe until EMAIL_WEBHOOK_URL
    is set). Marks each request sent/queued_no_contact so it is never re-sent."""
    db = load_db()
    now = datetime.now()
    flushed = no_contact = 0
    for jid, job in db.get("jobs", {}).items():
        for r in job.get("review_requests", []):
            if r.get("status") != "queued":
                continue
            try:
                due = datetime.fromisoformat(r.get("send_after"))
            except (ValueError, TypeError):
                due = now
            if due > now:
                continue
            to = job.get("customer_email")
            if to:
                _email_dispatch(db, {
                    "to": to, "subject": "How did we do? — Truline Roofing",
                    "body": r.get("message") or "Thanks for choosing Truline Roofing! "
                            "If you have a moment, we'd appreciate a quick review.",
                    "sent_by": "review-flush", "sent_at": now.isoformat()})
                r["status"] = "sent"
                flushed += 1
            else:
                r["status"] = "queued_no_contact"
                no_contact += 1
    save_db(db)
    return {"flushed": flushed, "no_contact": no_contact}


_CRON_TASKS["compliance_scan"] = _cron_compliance_scan   # O52 rollup
_CRON_TASKS["coi_scan"] = _cron_compliance_scan          # O46
_CRON_TASKS["cert_scan"] = _cron_compliance_scan         # O51
_CRON_TASKS["anomaly_scan"] = _cron_anomaly_scan         # I62
_CRON_TASKS["flush_outbox"] = _flush_outbox_once         # outbox email retry
_CRON_TASKS["flush_sms"] = _flush_sms_once               # sms outbox retry (7c)
_CRON_TASKS["suite_sync_heartbeat"] = _cron_suite_sync_heartbeat  # in-hub heartbeat (8a)
_CRON_TASKS["pipeline_alerts"] = _cron_pipeline_alerts   # P1-3/P1-5 follow-up + SLA alerts
_CRON_TASKS["review_flush"] = _cron_review_flush          # P1-4 drain review-ask queue


# ─── In-process scheduler (built-in scheduled scans) ─────────────────────────
# TruAgent runs as a single always-on uvicorn worker, so a lightweight asyncio
# loop is enough to fire the db-only scans on a timer — no external cron service
# is needed. Last-run stamps are persisted in db.json (scheduler_runs) so a
# restart never double-fires and a daily job still fires about once per day even
# across restarts. The email-dependent tasks (flush_outbox / flush_sms and the
# /cron/digest) are intentionally NOT scheduled here — they stay dormant until an
# EMAIL_/SMS_WEBHOOK_URL is set; add them to _SCHEDULE once those are live. The
# /cron/tick endpoint stays available for manual/external triggering (header-
# authed). Disable this loop entirely with SCHEDULER_ENABLED=0.
_SCHEDULE = [
    # (task_name registered in _CRON_TASKS, interval_seconds)
    ("compliance_scan", 24 * 3600),   # COI/cert/SDS expiry rollup -> compliance_alerts
    ("anomaly_scan", 24 * 3600),      # margin/gallon anomaly flags -> anomaly_snapshot
    ("suite_sync_heartbeat", 3600),   # hub liveness marker -> sync_heartbeat
    ("pipeline_alerts", 6 * 3600),    # P1-3/P1-5 overdue follow-ups + SLA breaches
    ("review_flush", 24 * 3600),      # P1-4 drain post-cure review-ask queue (dormant-safe)
]
_SCHEDULER_TICK_SECS = 300  # re-check for due jobs every 5 minutes


def _run_due_scheduled_tasks():
    """Run any scheduled task whose interval has elapsed; persist last-run stamps
    in db.json so it is restart-safe. Synchronous (runs in a worker thread).
    Returns a list of (task_name, result) for whatever fired this tick."""
    snapshot = load_db()
    stamps = dict(snapshot.get("scheduler_runs", {}))
    now = datetime.now()
    ran = []
    for task_name, interval in _SCHEDULE:
        last = stamps.get(task_name)
        if last:
            try:
                if (now - datetime.fromisoformat(last)).total_seconds() < interval:
                    continue
            except (ValueError, TypeError):
                pass  # unparseable stamp -> treat as due
        handler = _CRON_TASKS.get(task_name)
        if not handler:
            continue
        try:
            result = handler()  # each handler does its own load_db()/save_db()
        except Exception as e:
            result = f"error: {e}"
        # Re-read AFTER the handler saved so we don't clobber its write, then
        # stamp this run.
        db = load_db()
        db.setdefault("scheduler_runs", {})[task_name] = now.isoformat()
        save_db(db)
        ran.append((task_name, result))
    return ran


async def _scheduler_loop():
    await asyncio.sleep(10)  # let the app finish booting before the first tick
    while True:
        try:
            for task_name, result in await asyncio.to_thread(_run_due_scheduled_tasks):
                print(f"[scheduler] ran {task_name}: {result}", flush=True)
        except Exception as e:
            print(f"[scheduler] tick error: {e}", flush=True)
        await asyncio.sleep(_SCHEDULER_TICK_SECS)


@app.on_event("startup")
async def _start_scheduler():
    if os.getenv("SCHEDULER_ENABLED", "1") == "0":
        print("[scheduler] disabled (SCHEDULER_ENABLED=0)", flush=True)
        return
    asyncio.create_task(_scheduler_loop())
    print("[scheduler] started — compliance_scan/anomaly_scan daily, "
          "suite_sync_heartbeat hourly", flush=True)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "5000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
