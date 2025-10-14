from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import hashlib
import json
import base64
from datetime import datetime
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

ADMIN_EMAIL = "fred@trulineroofing.com"

USERS = {
    "fred@trulineroofing.com": hashlib.sha256(b"truline2024").hexdigest(),
    "fieldcrew@trulineroofing.com": hashlib.sha256(b"roof123").hexdigest(),
    "office@trulineroofing.com": hashlib.sha256(b"office123").hexdigest()
}

db_file = "db.json"

def load_db():
    if os.path.exists(db_file):
        with open(db_file, 'r') as f:
            return json.load(f)
    return {"jobs": {}, "documents": {}, "chat_history": {}}

def save_db(data):
    with open(db_file, 'w') as f:
        json.dump(data, f, indent=2)

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
    job_id: Optional[str] = None
    client_name: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
    data: Optional[dict] = None

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("static/index.html")

@app.post("/login")
async def login(data: Login):
    hashed = hashlib.sha256(data.password.encode()).hexdigest()
    if USERS.get(data.email) == hashed:
        is_admin = data.email == ADMIN_EMAIL
        return {"status": "ok", "token": data.email, "is_admin": is_admin}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/job")
async def add_job(job: Job, request: Request):
    token = request.headers.get("Authorization")
    if token not in USERS:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    db = load_db()
    db["jobs"][job.job_id] = job.dict()
    save_db(db)
    return {"msg": f"Job {job.job_id} saved"}

@app.get("/job/{job_id}")
async def get_job(job_id: str, request: Request):
    token = request.headers.get("Authorization")
    if token not in USERS:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    db = load_db()
    job = db["jobs"].get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/jobs")
async def get_all_jobs(request: Request):
    token = request.headers.get("Authorization")
    if token not in USERS:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    db = load_db()
    return {"jobs": db["jobs"]}

@app.post("/zapier/webhook")
async def zapier_webhook(webhook: ZapierWebhook):
    db = load_db()
    
    if webhook.job_id:
        if webhook.job_id in db["jobs"]:
            for key, value in webhook.dict().items():
                if value is not None and key != "data":
                    db["jobs"][webhook.job_id][key] = value
        else:
            db["jobs"][webhook.job_id] = webhook.dict()
    
    save_db(db)
    return {"status": "ok", "message": "Webhook received"}

@app.post("/documents/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    description: str = Form("")
):
    token = request.headers.get("Authorization")
    if token not in USERS:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
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
        "uploaded_by": token,
        "uploaded_at": datetime.now().isoformat()
    }
    save_db(db)
    
    return {"status": "ok", "doc_id": doc_id, "filename": file.filename}

@app.get("/documents")
async def get_documents(request: Request):
    token = request.headers.get("Authorization")
    if token not in USERS:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    db = load_db()
    return {"documents": db["documents"]}

@app.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, request: Request):
    token = request.headers.get("Authorization")
    if token not in USERS:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    db = load_db()
    doc = db["documents"].get(doc_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return FileResponse(doc["filepath"], filename=doc["filename"])

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request):
    token = request.headers.get("Authorization")
    if token != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Only admin can delete documents")
    
    db = load_db()
    doc = db["documents"].get(doc_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if os.path.exists(doc["filepath"]):
        os.remove(doc["filepath"])
    
    del db["documents"][doc_id]
    save_db(db)
    
    return {"status": "ok", "message": "Document deleted"}

@app.post("/chat")
async def chat(message: ChatMessage, request: Request):
    token = request.headers.get("Authorization")
    if token not in USERS:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    db = load_db()
    
    if token not in db["chat_history"]:
        db["chat_history"][token] = []
    
    db["chat_history"][token].append({
        "role": "user",
        "content": message.message,
        "timestamp": datetime.now().isoformat()
    })
    
    system_prompt = f"""You are an AI assistant for Truline Roofing, a commercial roofing company. 
You help users manage jobs, documents, and CRM data from Roofr.

Current available data:
- Jobs: {json.dumps(db['jobs'], indent=2)}
- Documents: {json.dumps(db['documents'], indent=2)}

You can help with:
- Viewing and editing job details
- Managing documents
- Answering questions about roofing projects
- Providing summaries and reports

User: {token}
Is Admin: {token == ADMIN_EMAIL}
"""
    
    from typing import List, Dict, Any
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    
    for msg in db["chat_history"][token][-10:]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        assistant_message = response.choices[0].message.content
        
        db["chat_history"][token].append({
            "role": "assistant",
            "content": assistant_message,
            "timestamp": datetime.now().isoformat()
        })
        
        save_db(db)
        
        return {"response": assistant_message}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")

@app.get("/chat/history")
async def get_chat_history(request: Request):
    token = request.headers.get("Authorization")
    if token not in USERS:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    db = load_db()
    history = db["chat_history"].get(token, [])
    
    return {"history": history}

@app.delete("/users/{email}")
async def delete_user_access(email: str, request: Request):
    token = request.headers.get("Authorization")
    if token != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Only admin can delete user access")
    
    if email == ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Cannot delete admin account")
    
    if email in USERS:
        del USERS[email]
        return {"status": "ok", "message": f"User {email} access deleted"}
    
    raise HTTPException(status_code=404, detail="User not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
