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
| `CRON_SECRET` | Password the scheduler endpoint (`POST /cron/tick`) must include so only your Railway cron / Zapier Schedule can fire scheduled tasks | You choose it; paste into the cron/schedule caller | Cron endpoint uses a default placeholder (insecure — set before exposing) |
| `ROOFR_WEBHOOK_URL` | Where to push job updates out to Roofr | Zapier "Catch Hook" URL | Sending updates to Roofr returns "not configured" |
| `EMAIL_WEBHOOK_URL` | Where to send emails (Gmail/SendGrid via Zapier) | Zapier webhook URL | Email feature returns "not configured" |
| `SMS_WEBHOOK_URL` | Where to send texts (Twilio via Zapier) | Zapier webhook URL | SMS feature returns "not configured" |
| `ESIGN_WEBHOOK_URL` | Where to route documents for e-signature (DocuSign / a Zapier e-sign step) | Zapier "Catch Hook" or DocuSign Zap URL | E-sign send records the request locally but reports the webhook is "not configured" |
| `PORT` | Local server port | Optional | Defaults to `5000` |
| `OPENAI_MODEL` | Which OpenAI chat model the AI agent uses | Optional | Defaults to `gpt-5.5`; falls back to `OPENAI_FALLBACK_MODEL` if rejected |
| `OPENAI_FALLBACK_MODEL` | Known-good model used if `OPENAI_MODEL` is unavailable | Optional | Defaults to `gpt-4o-mini` |
| `DATA_DIR` | Folder holding `db.json` + uploaded `documents/` | **Production: set to a mounted persistent volume** (e.g. `/data` on Railway) so data survives redeploys | Defaults to the project folder (fine for local dev; **ephemeral on Railway if left unset**) |

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
