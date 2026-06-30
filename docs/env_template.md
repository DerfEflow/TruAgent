# TruAgent — Environment Variables

Settings are read from a local `.env` file (loaded automatically at startup).
Copy `.env.example` to `.env` and fill in what you need. The real `.env` is
gitignored and must never be committed.

Every integration is **optional**. Leave a value blank and that feature stays
dormant — the app runs and is fully reviewable without any of them.

| Variable | What it's for | Where the value comes from | Blank =? |
|----------|---------------|----------------------------|----------|
| `OPENAI_API_KEY` | Powers the AI chat assistant | platform.openai.com → API keys | AI chat says "not configured" |
| `SESSION_SECRET` | Signs login tokens (JWT) | Generate a strong random string | A random one is generated each restart (logs everyone out on restart) |
| `ZAPIER_SECRET` | Password Zapier must include when sending Roofr data in | You choose it; paste the same value into Zapier | Incoming Roofr webhook uses the default placeholder |
| `QUICKBOOKS_SECRET` | Password Zapier must include when sending QuickBooks data in | You choose it; paste into Zapier | Incoming QuickBooks webhook uses the default placeholder |
| `ALPHA_SECRET` | Password the Alpha Estimator door (`POST /alpha/webhook`) must include to import an estimate baseline | You choose it; paste into the Alpha → TruAgent Zap | Inbound Alpha webhook uses a default placeholder (insecure — set a real value before connecting) |
| `PRODUCTION_SECRET` | Password the Delta production-log door (`POST /production/webhook`) must include to ingest a daily log | You choose it; paste into the Delta → TruAgent Zap | Inbound production webhook uses a default placeholder (insecure — set before connecting) |
| `LEADS_SECRET` | Password the Dominate lead door (`POST /leads/webhook`) must include to create an opportunity | You choose it; paste into the lead-source → TruAgent Zap | Inbound leads webhook uses a default placeholder (insecure — set before connecting) |
| `CRON_SECRET` | Password the scheduler endpoint (`POST /cron/tick`) must include, sent in the `X-Cron-Secret` request header (never a `?secret=` query param, which would leak into access logs), so only your Railway cron / Zapier Schedule can fire scheduled tasks | You choose it; set it as the `X-Cron-Secret` header in the cron/schedule caller | Door rejects all calls (fail-closed) until set |
| `ROOFR_WEBHOOK_URL` | Where to push job updates out to Roofr | Zapier "Catch Hook" URL | Sending updates to Roofr returns "not configured" |
| `EMAIL_WEBHOOK_URL` | Fallback email path (Gmail/SendGrid via Zapier) — used only if SMTP isn't set | Zapier webhook URL | Falls back; email queues if neither this nor SMTP is set |
| `SMTP_USER` | **Preferred email backend.** SMTP login — for Google Workspace, the mailbox the app authenticates as (e.g. `admin@trulineroofing.com`) | Workspace account | Email stays dormant/queues until set (with `SMTP_PASSWORD`) |
| `SMTP_PASSWORD` | App password for `SMTP_USER` (Google account → Security → App passwords; needs 2-Step Verification on) | Google app password | — |
| `EMAIL_FROM` | Address shown as the sender | Optional | Defaults to `SMTP_USER` |
| `SMTP_HOST` / `SMTP_PORT` | SMTP server/port | Optional | Default `smtp.gmail.com` / `587` (STARTTLS; `465` = SSL) |
| `SMS_WEBHOOK_URL` | Where to send texts (Twilio via Zapier) | Zapier webhook URL | SMS feature returns "not configured" |
| `ESIGN_WEBHOOK_URL` | Where to route documents for e-signature (DocuSign / a Zapier e-sign step) | Zapier "Catch Hook" or DocuSign Zap URL | E-sign send records the request locally but reports the webhook is "not configured" |
| `PORT` | Local server port | Optional | Defaults to `5000` |
| `OPENAI_MODEL` | Which OpenAI chat model the AI agent uses | Optional | Defaults to `gpt-4o`; falls back to `OPENAI_FALLBACK_MODEL` if rejected |
| `OPENAI_FALLBACK_MODEL` | Known-good model used if `OPENAI_MODEL` is unavailable | Optional | Defaults to `gpt-4o-mini` |
| `DATA_DIR` | Folder holding `db.json` + uploaded `documents/` | **Production: set to a mounted persistent volume** (e.g. `/data` on Railway) so data survives redeploys | Defaults to the project folder (fine for local dev; **ephemeral on Railway if left unset**) |
| `OVERPASS_API_URL` | Roof-measure (P3-14) building-footprint source (OSM Overpass). Keyless. | Optional override | Defaults to the public Overpass endpoint; the estimator also fails over to known mirrors automatically |
| `GOOGLE_SOLAR_API_KEY` | Roof-measure (P3-14) **optional** roof-area cross-check via Google Solar buildingInsights | console.cloud.google.com → Solar API | Solar cross-check is skipped (estimate stands on open footprints + geometry) |
| `MS_FOOTPRINTS_URL` | Roof-measure (P3-14) **optional** Microsoft Building Footprints point-query service (there is no keyless point API for the raw MS dataset) | a service you host exposing `?lat&lon&radius_m`→GeoJSON | MS source is skipped; OSM/Overpass is the keyless primary |
| `SCHEDULER_ENABLED` | Built-in in-process scheduler that runs the db-only scans on a timer (compliance + anomaly scans daily, hub heartbeat hourly) — no external cron needed; last-run stamps persist in `db.json` so it's restart-safe | Optional | Defaults to **on**; set to `0` to disable (e.g. if you switch to an external cron driving `/cron/tick`) |

## Generating strong secret values

```
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The local `.env` already has strong values for `SESSION_SECRET`, `ZAPIER_SECRET`,
and `QUICKBOOKS_SECRET`. `OPENAI_API_KEY` and the webhook URLs are intentionally
left blank so those features stay off until Fred turns them on.

The four inbound-door secrets — `ALPHA_SECRET`, `PRODUCTION_SECRET`,
`LEADS_SECRET`, and `CRON_SECRET` — each fall back to an insecure default
placeholder if left blank, so the app still boots for local review. **Generate a
strong value for each (same command as above) and set them in Railway Variables
+ local `.env` before connecting the corresponding Alpha / Delta / lead / cron
Zap.** `ESIGN_WEBHOOK_URL` stays blank until the e-sign integration is wired up.
