# TruAgent — Session Handoff
_Last updated: 2026-06-08_

---

## Current State: LIVE on Railway

**Production URL:** https://truagent-production.up.railway.app  
**GitHub repo:** https://github.com/DerfEflow/TruAgent  
**Local dev:** http://localhost:5050 (run `.\.venv\Scripts\python.exe main.py`)

**Auto-deploy:** Every `git push origin main` triggers a Railway redeploy automatically.

---

## What's Done

### Design
- Full dark steel theme (carbon black + Truline green)
- Franchise-quality design across all 6 screens
- Mobile responsive: 768px + 480px breakpoints
- Header email hidden on mobile, tabs scroll horizontally
- Clipped-corner buttons, green status dot, industrial typography

### AI Chat
- Model: `gpt-5.5` (confirmed working on Railway)
- Parameters: `max_completion_tokens=1000` only (gpt-5.5 rejects `temperature` and `max_tokens`)
- Voice input: mic button using OpenAI Whisper (`/transcribe` endpoint)
  - MediaRecorder API in browser → POST audio → Whisper → text into input field
  - Tap to record (turns red), tap again to stop → text appears in chat box

### Deployment
- `railway.toml` and `requirements.txt` added
- All 4 env vars set in Railway: `OPENAI_API_KEY`, `SESSION_SECRET`, `ZAPIER_SECRET`, `QUICKBOOKS_SECRET`
- `PORT` is set automatically by Railway — do not set manually

### Webhook fixes
- `GET /zapier/webhook` added for Zapier URL verification (returns `{"status":"ok"}`)
- `POST /zapier/webhook` handles actual job data from Roofr

---

## In Progress: Zapier / Roofr Setup

Fred is mid-setup in Zapier. He got through URL verification and is now on the **data mapping step** for the action (Webhooks by Zapier → POST).

**Roofr Zapier trigger chosen:** Job Workflow Stage Changed

**Field mapping to use:**

| TruAgent field | Roofr Zapier field |
|---------------|-------------------|
| `secret` | Fixed value — ZAPIER_SECRET from Admin tab |
| `job_id` | External Id |
| `client_name` | Primary Customer Name |
| `address` | Job Address |
| `status` | New Stage |

**Next step:** Fred needs to complete the data mapping, click Test action, and confirm a job appears in the Jobs tab on the live app.

**After Roofr Zap is working, remaining Zaps to build:**
1. **Roofr Lead Created** — second Roofr trigger for new estimator leads (same mapping)
2. **QuickBooks → TruAgent** — two Zaps (invoices + expenses) to `/quickbooks/webhook`
3. **Gmail outbound** — Zapier Catch Hook → Gmail, URL goes in `EMAIL_WEBHOOK_URL` env var on Railway

---

## Remaining To-Do (in priority order)

1. **Finish Roofr Zap** (mid-setup)
2. **Add second Roofr Zap** (Lead Created trigger)
3. **QuickBooks Zaps** (invoices + expenses)
4. **Gmail outbound Zap**
5. **Change demo passwords** before sharing with real staff
   - office@trulineroofing.com / office123 → manager
   - fieldcrew@trulineroofing.com / roof123 → field crew
6. **Test voice input** on mobile (tap mic, speak, check transcription accuracy)
7. **Persistent document storage** — currently Railway filesystem is ephemeral; uploaded documents disappear on redeploy. Future fix: Railway volume or S3.

---

## Demo Logins (do not change until real staff are set up)
- `fred@trulineroofing.com` / `truline2024` → Super Admin
- `office@trulineroofing.com` / `office123` → Manager
- `fieldcrew@trulineroofing.com` / `roof123` → Field Crew

---

## Key Technical Notes

- **gpt-5.5 quirks:** Does not accept `temperature` or `max_tokens` — use `max_completion_tokens` only
- **Zapier webhook secret:** Available in Admin tab of live app (Copy button), also in `.env` as `ZAPIER_SECRET`
- **QuickBooks secret:** In `.env` as `QUICKBOOKS_SECRET` — will need to be entered in Zapier QB zap
- **PORT:** Railway sets this automatically from its environment — never hardcode or override
- **db.json:** JSON flat-file database, gitignored, lives on Railway's filesystem (ephemeral — see To-Do #7)
- **documents/ folder:** Also ephemeral on Railway — uploads survive until next deploy only

---

## Architecture Summary
- FastAPI + Uvicorn backend (`main.py`)
- Vanilla JS SPA frontend (`static/index.html`, `app.js`, `style.css`)
- JSON flat-file storage (`db.json`)
- All integrations via Zapier webhooks (no direct API calls to Roofr/QuickBooks)
- OpenAI used for chat (`/chat`) and voice transcription (`/transcribe`)
