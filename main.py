from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import hashlib
import json
import secrets
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

ZAPIER_SECRET = os.getenv("ZAPIER_SECRET", "change_this_secret_in_production")
ROOFR_WEBHOOK_URL = os.getenv("ROOFR_WEBHOOK_URL", "")
QUICKBOOKS_SECRET = os.getenv("QUICKBOOKS_SECRET", "change_this_in_production")
EMAIL_WEBHOOK_URL = os.getenv("EMAIL_WEBHOOK_URL", "")
SMS_WEBHOOK_URL = os.getenv("SMS_WEBHOOK_URL", "")

# AI model is configurable so a bad/unavailable id never requires a code change.
# Default is the id confirmed working on this account; a known-good fallback is
# used automatically if the primary id is rejected (see _create_completion).
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
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

def load_db():
    if os.path.exists(db_file):
        with open(db_file, 'r') as f:
            db = json.load(f)
        
        needs_migration = False
        
        if "financials" not in db:
            db["financials"] = {}
            needs_migration = True
        
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
        
        if needs_migration:
            save_db(db)
        
        return db
    
    return {
        "jobs": {},
        "documents": {},
        "chat_history": {},
        "financials": {},
        "users": {
            "fred@trulineroofing.com": {
                "email": "fred@trulineroofing.com",
                "password_hash": hashlib.sha256(b"truline2024").hexdigest(),
                "role": "super_admin"
            },
            "fieldcrew@trulineroofing.com": {
                "email": "fieldcrew@trulineroofing.com",
                "password_hash": hashlib.sha256(b"roof123").hexdigest(),
                "role": "user"
            },
            "office@trulineroofing.com": {
                "email": "office@trulineroofing.com",
                "password_hash": hashlib.sha256(b"office123").hexdigest(),
                "role": "manager"
            }
        }
    }

def save_db(data):
    # Atomic write: dump to a temp file in the same directory, then os.replace()
    # it over the target. A crash mid-write can't leave db.json half-written and
    # invalid (which would fail to load on the next boot).
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
        "job_id": job_id,
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
        "job_id": job_id,
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


def _op_send_email(db: dict, to: Optional[str], subject: str, body: str,
                   html: Optional[str], document_ids, user_email: str) -> dict:
    if not EMAIL_WEBHOOK_URL:
        return {"status": "error", "message": "Email service not configured"}
    if not to:
        return {"status": "error", "message": "A recipient ('to') is required"}
    attachments = _gather_attachments(db, document_ids)
    payload = {
        "to": to, "subject": subject, "body": body, "html": html,
        "attachments": attachments or None,
        "sent_by": user_email, "sent_at": datetime.now().isoformat(),
    }
    try:
        import requests
        resp = requests.post(EMAIL_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return {"status": "ok", "message": f"Email sent to {to}"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to send email: {e}"}


def _op_send_sms(to: Optional[str], message: str, user_email: str) -> dict:
    if not SMS_WEBHOOK_URL:
        return {"status": "error", "message": "SMS service not configured"}
    if not to:
        return {"status": "error", "message": "A recipient ('to') is required"}
    payload = {"to": to, "message": message, "sent_by": user_email,
               "sent_at": datetime.now().isoformat()}
    try:
        import requests
        resp = requests.post(SMS_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return {"status": "ok", "message": f"SMS sent to {to}"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to send SMS: {e}"}


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
}

_COMMON_TOOLS = ["list_jobs", "get_job", "update_job_status", "add_job_note",
                 "list_documents", "send_email", "send_sms"]
_FINANCIAL_TOOLS = ["get_job_financials", "company_financials_summary"]


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
        if role == "user":  # hide financial id-lists from field crew
            job = {k: v for k, v in job.items() if k not in ("invoices", "expenses")}
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
        return _op_send_sms(args.get("to"), args.get("message", ""), email)
    if name == "get_job_financials":
        return _job_financials(db, args.get("job_id"))
    if name == "company_financials_summary":
        return _company_financials_summary(db)
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

@app.post("/login")
async def login(data: Login):
    db = load_db()
    user = db["users"].get(data.email)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    if user["password_hash"] != hashed:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
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
    return job

@app.get("/jobs")
async def get_all_jobs(current_user: dict = Depends(get_current_user)):
    db = load_db()
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

    # Accept whatever fields Roofr/Zapier sends so new fields (job value, customer
    # phone/email, assignee, etc.) can be mapped in Zapier without a code change.
    # Drop the secret, ignore blanks, and flatten a nested "data" object if present.
    fields = {k: v for k, v in payload.items()
              if k not in ("secret", "data") and v not in (None, "")}
    nested = payload.get("data")
    if isinstance(nested, dict):
        fields.update({k: v for k, v in nested.items() if v not in (None, "")})

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
        
        if webhook.job_id and webhook.job_id in db["jobs"]:
            if "invoices" not in db["jobs"][webhook.job_id]:
                db["jobs"][webhook.job_id]["invoices"] = []
            if webhook.transaction_id not in db["jobs"][webhook.job_id]["invoices"]:
                db["jobs"][webhook.job_id]["invoices"].append(webhook.transaction_id)
    
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
        
        if webhook.job_id and webhook.job_id in db["jobs"]:
            if "expenses" not in db["jobs"][webhook.job_id]:
                db["jobs"][webhook.job_id]["expenses"] = []
            if webhook.transaction_id not in db["jobs"][webhook.job_id]["expenses"]:
                db["jobs"][webhook.job_id]["expenses"].append(webhook.transaction_id)
    
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
    """Send email via Zapier webhook integration (supports Gmail, SendGrid, etc.)"""
    
    if not EMAIL_WEBHOOK_URL:
        raise HTTPException(status_code=503, detail="Email service not configured")
    
    db = load_db()
    
    attachments = []
    if email.document_ids:
        for doc_id in email.document_ids:
            if doc_id in db["documents"]:
                doc = db["documents"][doc_id]
                try:
                    import base64
                    with open(doc["filepath"], "rb") as f:
                        file_content = f.read()
                        base64_content = base64.b64encode(file_content).decode()
                        attachments.append({
                            "filename": doc["filename"],
                            "content": base64_content,
                            "contentType": "application/octet-stream"
                        })
                except Exception as e:
                    pass
    
    payload = {
        "to": email.to,
        "subject": email.subject,
        "body": email.body,
        "html": email.html,
        "attachments": attachments if attachments else None,
        "sent_by": current_user["email"],
        "sent_at": datetime.now().isoformat()
    }
    
    try:
        import requests
        response = requests.post(EMAIL_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        
        return {
            "status": "ok",
            "message": f"Email sent to {email.to}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.post("/send-sms")
async def send_sms(sms: SMSMessage, current_user: dict = Depends(get_current_user)):
    """Send SMS via Zapier webhook integration (supports Twilio, etc.)"""
    
    if not SMS_WEBHOOK_URL:
        raise HTTPException(status_code=503, detail="SMS service not configured")
    
    payload = {
        "to": sms.to,
        "message": sms.message,
        "sent_by": current_user["email"],
        "sent_at": datetime.now().isoformat()
    }
    
    try:
        import requests
        response = requests.post(SMS_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        
        return {
            "status": "ok",
            "message": f"SMS sent to {sms.to}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send SMS: {str(e)}")

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
        return {"status": "ok", "jobs": db["jobs"]}
    
    elif action.action == "get_job_details":
        job_id = action.parameters.get("job_id")
        if job_id in db["jobs"]:
            return {"status": "ok", "job": db["jobs"][job_id]}
        return {"status": "error", "message": "Job not found"}
    
    elif action.action == "list_documents":
        return {"status": "ok", "documents": db["documents"]}
    
    elif action.action == "send_email":
        to = action.parameters.get("to")
        subject = action.parameters.get("subject")
        body = action.parameters.get("body")
        html = action.parameters.get("html")
        doc_ids = action.parameters.get("document_ids", [])
        
        if not EMAIL_WEBHOOK_URL:
            return {"status": "error", "message": "Email service not configured"}
        
        attachments = []
        if doc_ids:
            for doc_id in doc_ids:
                if doc_id in db["documents"]:
                    doc = db["documents"][doc_id]
                    try:
                        import base64
                        with open(doc["filepath"], "rb") as f:
                            file_content = f.read()
                            base64_content = base64.b64encode(file_content).decode()
                            attachments.append({
                                "filename": doc["filename"],
                                "content": base64_content,
                                "contentType": "application/octet-stream"
                            })
                    except:
                        pass
        
        payload = {
            "to": to,
            "subject": subject,
            "body": body,
            "html": html,
            "attachments": attachments if attachments else None,
            "sent_by": current_user["email"],
            "sent_at": datetime.now().isoformat()
        }
        
        try:
            import requests
            response = requests.post(EMAIL_WEBHOOK_URL, json=payload, timeout=10)
            response.raise_for_status()
            return {"status": "ok", "message": f"Email sent to {to}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send email: {str(e)}"}
    
    elif action.action == "send_sms":
        to = action.parameters.get("to")
        message = action.parameters.get("message")
        
        if not SMS_WEBHOOK_URL:
            return {"status": "error", "message": "SMS service not configured"}
        
        payload = {
            "to": to,
            "message": message,
            "sent_by": current_user["email"],
            "sent_at": datetime.now().isoformat()
        }
        
        try:
            import requests
            response = requests.post(SMS_WEBHOOK_URL, json=payload, timeout=10)
            response.raise_for_status()
            return {"status": "ok", "message": f"SMS sent to {to}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send SMS: {str(e)}"}
    
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
    return {
        "webhook_url": "/zapier/webhook",
        "secret": ZAPIER_SECRET,
        "instructions": "Include the 'secret' field in your Zapier webhook payload"
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "5000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
