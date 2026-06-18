# TruAgent — Architecture

TruAgent ("Truline Roofing AI Agent") is a small, self-contained web app: one
Python backend file, a vanilla-JavaScript front end, and a single JSON file for
storage. There is **no separate database server**.

## The pieces

- **Backend — `main.py` (FastAPI + Uvicorn).**
  Serves the web app, handles login (JWT tokens), and exposes all the API
  routes below. Runs locally with `python main.py` on `http://localhost:5000`
  (the port can be changed with the `PORT` environment variable).

- **Storage — `db.json`.**
  A plain JSON file in the project folder. It is created automatically the
  first time data is written, and seeded with three demo logins. See
  [data_model.md](data_model.md) for its shape. This file is gitignored
  (it holds live data) and is **not** committed.

- **Front end — `static/`.**
  A single-page app made of `index.html`, `app.js`, and `style.css`, plus PWA
  files (`manifest.json`, `service-worker.js`) and the logo. The browser talks
  to the backend over the API routes using a saved login token.

- **Integrations (all optional / dormant by default).**
  Roofr CRM, QuickBooks, email, and SMS all work through **Zapier webhooks**,
  not direct APIs. Each is turned on only when its environment variable is set
  (see [env_template.md](env_template.md)). With them blank, the app runs fine
  and shows a "not configured" state instead of crashing.

- **AI assistant (OpenAI, dormant by default).**
  The chat is a **tool-calling agent**: it can answer questions *and* take
  actions (update job status / add notes → sync to Roofr, send email/SMS, look
  up jobs & financials), with financial tools gated to manager+ roles. The model
  is set by the `OPENAI_MODEL` env var (default `gpt-4o`); if that id is
  rejected it falls back automatically to `OPENAI_FALLBACK_MODEL` (default
  `gpt-4o-mini`) so a bad id can't take chat down. The client is created lazily —
  with no `OPENAI_API_KEY` set, the app still boots and the chat politely says
  it isn't configured yet.

## Roles

Three role levels, enforced on the backend and reflected in the UI:

- **Super Admin** (Fred) — full access: user management, document delete, Zapier
  webhook config, financials, everything.
- **Manager** (office) — sees everything including financials, but cannot delete
  documents or manage users.
- **User** (field crew) — operational access only; the AI is instructed to hide
  all financial data from this role.

## Main API routes

| Area | Route | Notes |
|------|-------|-------|
| Auth | `POST /login` | Returns a JWT token + role |
| Jobs | `GET /jobs`, `GET /job/{id}`, `POST /job` | Requires login |
| Jobs (money) | `GET /job/{id}/financials` | Manager+ only |
| CRM in | `POST /zapier/webhook` | From Roofr via Zapier; needs `ZAPIER_SECRET` |
| CRM out | `POST /roofr/update` | To Roofr; needs `ROOFR_WEBHOOK_URL` |
| Finance in | `POST /quickbooks/webhook` | From QuickBooks; needs `QUICKBOOKS_SECRET` |
| Documents | `POST /documents/upload`, `GET /documents`, `GET /documents/{id}/download`, `DELETE /documents/{id}` | Delete is Super Admin only |
| Comms | `POST /send-email`, `POST /send-sms` | Need the matching webhook URL |
| AI | `POST /chat`, `GET /chat/history`, `POST /ai/action` | Chat needs `OPENAI_API_KEY` |
| Admin | `GET /admin/webhook-info` | Super Admin only |
| Users | `GET /users`, `POST /users`, `PUT /users/{email}/role`, `DELETE /users/{email}` | Super Admin only |
