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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SECRET_KEY = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

ZAPIER_SECRET = os.getenv("ZAPIER_SECRET", "change_this_secret_in_production")
ROOFR_WEBHOOK_URL = os.getenv("ROOFR_WEBHOOK_URL", "")

ADMIN_EMAIL = "fred@trulineroofing.com"

db_file = "db.json"

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
    with open(db_file, 'w') as f:
        json.dump(data, f, indent=2)

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

@app.post("/zapier/webhook")
async def zapier_webhook(webhook: ZapierWebhook):
    if webhook.secret != ZAPIER_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    
    db = load_db()
    
    if webhook.job_id:
        if webhook.job_id in db["jobs"]:
            for key, value in webhook.dict().items():
                if value is not None and key not in ["secret", "data"]:
                    db["jobs"][webhook.job_id][key] = value
            if webhook.data:
                db["jobs"][webhook.job_id].update(webhook.data)
        else:
            job_data = {k: v for k, v in webhook.dict().items() if k != "secret" and v is not None}
            if webhook.data:
                job_data.update(webhook.data)
            db["jobs"][webhook.job_id] = job_data
    
    save_db(db)
    return {"status": "ok", "message": "Webhook received"}

@app.post("/roofr/update")
async def update_roofr(update: RoofrUpdate, current_user: dict = Depends(get_current_user)):
    """Send job updates to Roofr via Zapier webhook (bi-directional sync)"""
    
    if not ROOFR_WEBHOOK_URL:
        raise HTTPException(status_code=503, detail="Roofr webhook URL not configured")
    
    db = load_db()
    
    if update.job_id not in db["jobs"]:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = db["jobs"][update.job_id]
    
    if update.status:
        job["status"] = update.status
    
    if update.notes:
        if "notes" not in job:
            job["notes"] = []
        job["notes"].append({
            "note": update.notes,
            "added_by": current_user["email"],
            "added_at": datetime.now().isoformat()
        })
    
    if update.workflow_stage:
        job["workflow_stage"] = update.workflow_stage
    
    if update.data:
        job.update(update.data)
    
    save_db(db)
    
    payload = {
        "job_id": update.job_id,
        "status": job.get("status"),
        "workflow_stage": job.get("workflow_stage"),
        "client_name": job.get("client_name"),
        "address": job.get("address"),
        "updated_by": current_user["email"],
        "updated_at": datetime.now().isoformat()
    }
    
    if update.notes:
        payload["new_note"] = update.notes
    
    if update.data:
        payload.update(update.data)
    
    try:
        import requests
        response = requests.post(ROOFR_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        
        return {
            "status": "ok",
            "message": "Job updated locally and synced to Roofr",
            "job_id": update.job_id,
            "roofr_response": response.status_code
        }
    except Exception as e:
        return {
            "status": "partial",
            "message": f"Job updated locally but failed to sync to Roofr: {str(e)}",
            "job_id": update.job_id
        }

@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    description: str = Form(""),
    current_user: dict = Depends(get_current_user)
):
    os.makedirs("documents", exist_ok=True)
    
    file_content = await file.read()
    file_path = f"documents/{file.filename}"
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    db = load_db()
    doc_id = str(len(db["documents"]) + 1)
    db["documents"][doc_id] = {
        "id": doc_id,
        "filename": file.filename,
        "filepath": file_path,
        "description": description,
        "uploaded_by": current_user["email"],
        "uploaded_at": datetime.now().isoformat()
    }
    save_db(db)
    
    return {"status": "ok", "doc_id": doc_id, "filename": file.filename}

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
    
    return {"status": "error", "message": "Unknown action"}

@app.post("/chat")
async def chat(message: ChatMessage, current_user: dict = Depends(get_current_user)):
    db = load_db()
    
    user_email = current_user["email"]
    if user_email not in db["chat_history"]:
        db["chat_history"][user_email] = []
    
    db["chat_history"][user_email].append({
        "role": "user",
        "content": message.message,
        "timestamp": datetime.now().isoformat()
    })
    
    user_role = current_user.get("role", "user")
    
    if user_role == "user":
        system_prompt = f"""You are an AI assistant for Truline Roofing, a commercial roofing company. 
You help field crew and sales people with job information and administrative tasks.

Current available data:
- Jobs: {json.dumps(db['jobs'], indent=2)}
- Documents: {json.dumps(db['documents'], indent=2)}

You can help with:
- Viewing job details and status
- Updating job status (automatically syncs to Roofr CRM)
- Adding notes to jobs (automatically syncs to Roofr CRM)
- Uploading job photos
- Sending emails and text messages
- General roofing project questions

IMPORTANT RESTRICTIONS for this user role:
- You MUST NOT provide any financial information (invoices, costs, profits, expenses, purchase orders)
- If asked about financials, politely respond: "You don't have access to financial data. Please contact your manager."
- Focus on operational and customer-facing tasks only

BI-DIRECTIONAL CRM SYNC:
- When you update job status or add notes, changes automatically sync to Roofr CRM
- You can move jobs through workflow stages (Lead → Quote → Approved → In Progress → Complete)
- All updates are tracked with user email and timestamp

User: {user_email}
Role: Field Crew / Sales (Limited Access)
"""
    else:
        financials_data = "" if user_role == "user" else f"\n- Financials: {json.dumps(db.get('financials', {}), indent=2)}"
        
        system_prompt = f"""You are an AI assistant for Truline Roofing, a commercial roofing company. 
You help manage jobs, documents, financials, and CRM data from Roofr.

Current available data:
- Jobs: {json.dumps(db['jobs'], indent=2)}
- Documents: {json.dumps(db['documents'], indent=2)}{financials_data}

You can help with:
- Viewing and summarizing job details and financials
- Updating job status and workflow stages (automatically syncs to Roofr CRM)
- Adding notes to jobs (automatically syncs to Roofr CRM)
- Calculating profitability per job
- Providing information about documents
- Answering questions about roofing projects
- Creating financial reports and summaries

BI-DIRECTIONAL CRM SYNC:
- When you update job status or add notes, changes automatically sync to Roofr CRM
- You can move jobs through workflow stages (Lead → Quote → Approved → In Progress → Complete)
- All updates are tracked with user email and timestamp
- Use workflow_stage parameter to move jobs through sales pipeline

You have full access to all company data including financial information.

User: {user_email}
Role: {"Super Admin (Full Access)" if user_role == "super_admin" else "Manager (View All)"}
"""
    
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    
    for msg in db["chat_history"][user_email][-10:]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,  # type: ignore
            temperature=0.7,
            max_tokens=1000
        )
        
        assistant_message = response.choices[0].message.content
        
        db["chat_history"][user_email].append({
            "role": "assistant",
            "content": assistant_message,
            "timestamp": datetime.now().isoformat()
        })
        
        save_db(db)
        
        return {"response": assistant_message}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")

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
    uvicorn.run(app, host="0.0.0.0", port=5000)
