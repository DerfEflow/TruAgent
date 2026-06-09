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
| `ROOFR_WEBHOOK_URL` | Where to push job updates out to Roofr | Zapier "Catch Hook" URL | Sending updates to Roofr returns "not configured" |
| `EMAIL_WEBHOOK_URL` | Where to send emails (Gmail/SendGrid via Zapier) | Zapier webhook URL | Email feature returns "not configured" |
| `SMS_WEBHOOK_URL` | Where to send texts (Twilio via Zapier) | Zapier webhook URL | SMS feature returns "not configured" |
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
