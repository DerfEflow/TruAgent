# TruAgent MVP Gap Assessment

*Honest, prioritized read of where the live app stands against its stated MVP: **(1) pull Roofr data in, (2) update Roofr, (3) answer job/accounting/production/scheduling questions any employee might ask — and run without errors.***

---

## Headline: better than the original audit thought, but two real MVP holes remain

**Important correction up front.** The audit panel reviewed an *older snapshot* of `main.py`. Reading the **current** `C:\Users\rjfla\Documents\TruAgent\main.py`, four of the audit's most severe findings are **already fixed** in your live code. I'm flagging those as resolved so you don't pay twice. The genuinely open items are fewer, and three of them are small.

### Already fixed (do not re-do)

| Audit gap (original severity) | Status in live code | Evidence |
|---|---|---|
| Chat is "talk-only", can't act | **FIXED** — `/chat` is now a real OpenAI tool-calling loop. | `_run_agent_loop` (main.py:550-585) dispatches tool calls through `execute_agent_tool` (471-509); tools defined at 401-468. |
| Whole DB dumped into the prompt (cost/overflow) | **FIXED** — compact summary (max 40 jobs, no blobs) + tool drill-down. | `_compact_job` + `_build_chat_system_prompt` (393-397, 512-547). |
| Financial leak to field crew via prompt | **MITIGATED at the data layer** — `user` role gets no financial tools, and `get_job` strips `invoices`/`expenses` for crew. | `execute_agent_tool` (478-489), `tools_for_role` (464-468). |
| Document id collision + path traversal | **FIXED** — monotonic id via `max(existing_ids)+1`, filename sanitized with `os.path.basename`, id-prefixed on disk. | `upload_document` (961-971). |

That leaves the following genuinely open. Prioritized.

---

## BLOCKERS (MVP is not met until these are fixed)

### B1. Ephemeral storage wipes all data on every deploy
**MVP task blocked:** *pull Roofr data in* (and keep it).
Every Railway redeploy resets `db.json` and the `documents/` folder. Synced Roofr jobs, uploaded estimates/contracts, **and any newly created users** vanish — the app reverts to the three seed demo logins. The MVP is built around data that currently doesn't survive a deploy.
**Fix (cheapest viable):** attach a Railway persistent volume and point `db_file` + the `documents/` dir at the mounted path (e.g. `/data/db.json`, `/data/documents`) via an env var. **Better long-term:** move to Supabase Postgres + Storage, matching your sibling apps. Until done, treat every deploy as a full data-loss event.
**File:** `main.py:60` (`db_file`), `:958` (`os.makedirs("documents")`), `docs/handoff.md`.
**Effort:** S–M.

### B2. No UI path for an employee to update Roofr
**MVP task blocked:** *update Roofr.*
The backend (`/roofr/update`, `/ai/action`) works, but the front end **never calls it.** `grep` of `static/app.js` shows it only ever hits `/chat`, `/chat/history`, and `/transcribe` — the Jobs tab renders read-only cards with a Refresh button. So the *only* human ways to update Roofr today are the AI chat or `curl`. There is no deterministic button.
**Fix:** add per-job-card controls in the Jobs render — a status / workflow-stage `<select>` and an "Add note" box with a Save button that POSTs to `/roofr/update` with the Bearer token, shown to manager+ only. Surface the `"partial"` result (saved locally, Roofr push failed) so users see sync state. This gives a reliable update path that doesn't depend on the AI behaving.
**File:** `static/app.js` (Jobs render, around the financial-field filter at line 353), `static/index.html` (Jobs tab).
**Effort:** S.

---

## MAJOR (MVP partially works; these break a promised capability)

### M1. No production or scheduling data exists — so those questions can't be answered
**MVP task blocked:** *answer production/scheduling questions.*
There is no inbound feed or data shape for Delta daily logs (gallons, wet-mil, hours, weather) and no scheduling/dispatch concept anywhere in `db.json` or `main.py`. The chat can only answer from jobs/documents/financials. "How many gallons did we apply this week?" or "what's scheduled Thursday?" have no data to draw on regardless of how good the AI is.
**Fix:** add an inbound `POST /production/webhook` (mirror `/quickbooks/webhook`, gated by a `PRODUCTION_SECRET`) storing daily entries under `jobs[job_id]["production_logs"]`. For scheduling, at minimum add `scheduled_date` + `crew_assignment` fields on jobs. Then include both in the chat context / expose via tools. *(This is the "Daily Production Log ingest" + "Crew Calendar" MVP features in the catalog — the gap and the feature are the same work.)*
**File:** `main.py:761` (QuickBooks webhook = the pattern to copy).
**Effort:** M.

### M2. Chat model id is hardcoded, contradicts the docs, and was never confirmed against the account
**MVP task blocked:** *run without errors / answer questions.*
`main.py:555` and `:582` hardcode `"model": "gpt-5.5"`, while `docs/architecture.md` says `gpt-4o-mini`. If the live OpenAI account can't serve `gpt-5.5`, **every chat call 500s** ("AI Error") and the flagship feature is down. This is the single point of failure for the whole AI feature, so do not rely on the id being valid until you have **confirmed it against your actual account** — not trusted the handoff.
**Fix (do all of it):**
1. Make it an env var `OPENAI_MODEL`, set it in **both** call sites, and reconcile the docs.
2. Give it a **known-good default** (`gpt-4o-mini`, with `gpt-4o` as the heavier fallback) so a blank or bad value can't take chat down.
3. **Confirm the id against the account** before relying on it — either run a one-off `client.models.list()` and check that your chosen id is present, or make the first call at startup and fall back to a known-good id (and log a clear warning) if the API returns an "unknown model" / 404 error. A raw 500 to the user is the failure mode to design out.
**File:** `main.py:555, 582`; `docs/architecture.md`.
**Effort:** S.

---

## MINOR (stability / security hygiene — fix before real staff and real customers use it)

### N1. Flat-file writes are not atomic and not locked — *only worth fixing if you keep the flat file*
A concurrent Roofr webhook firing while a user saves a note (or two webhooks at once) can interleave and lose writes; a crash mid-write can truncate `db.json` into invalid JSON that fails to load on next boot.
**Fix:** write to a temp file then `os.replace()` onto `db.json`, and serialize the load→mutate→save sequence with a lock.
**Important sequencing caveat:** this fix is only worth doing **if you keep the flat file** — including the cheapest B1 option (a Railway volume is still a single flat file, so the locking is still needed there). **If you instead satisfy B1 by moving to Supabase Postgres** (the "better long-term" option this doc recommends), Postgres handles concurrency and atomicity for you and **this work becomes moot** — don't write locking code you're about to delete. Decide B1's destination first, then do N1 only on the keep-the-file branch.
**File:** `main.py:114-116` (`save_db`) and every route doing `load_db`/`save_db`.
**Effort:** S.

### N2. Production security/config hygiene
- **CORS** is `allow_origins=["*"]` with `allow_credentials=True` (main.py:25-26).
- **SESSION_SECRET** defaults to a fresh random value per process (main.py:48) — combined with ephemeral restarts, this silently logs everyone out on every redeploy.
- **ZAPIER_SECRET / QUICKBOOKS_SECRET** ship with `"change_this..."` placeholders the webhooks will happily accept if env is unset (main.py:52-54).
- **Passwords** are unsalted single-round SHA-256 (main.py:98, 600, 1291); demo passwords (`truline2024` etc.) are still live.
**Fix:** pin CORS to your Railway origin; require `SESSION_SECRET` at boot (fail fast if unset); refuse to start if the Zapier/QuickBooks secrets equal the placeholder; switch hashing to bcrypt/argon2 (passlib); rotate the seed passwords before staff use.
**File:** `main.py:23-58, 95-111, 246-1291`.
**Effort:** S.

### N3. Verify `.env` stays gitignored + rotate the example secret if it was ever live
**Status correction:** the earlier audit claimed a plaintext `ZAPIER_SECRET` was committed at `INTEGRATION_GUIDE.md` line ~321. **That is no longer true.** Reading the current file, **line 323 already shows the placeholder `<YOUR_ZAPIER_SECRET>`**, and a scan for the old `jSlhh7mtn2jmq2EvNgZ7…`-style value (and any 20+ char token) finds nothing — the plaintext secret has already been scrubbed. So there is **no committed secret to fix** here.
What remains is hygiene, not a leak:
- **Confirm `.env` stays gitignored** (it is, per `docs/env_template.md`) so a real secret never lands in git.
- **Rotate the value if that secret was ever live** (i.e. if the scrubbed string was a real key that had been pushed before the scrub) — scrubbing the file doesn't un-leak a value that was in git history.
- **Doc cleanup:** the file already carries the Railway hosting banner, but a few body lines still say "Replit Secrets" (e.g. lines 319 and 333). Update those to Railway env vars so the guide isn't self-contradictory.
**File:** `INTEGRATION_GUIDE.md` (line 323 already correct; tidy the "Replit Secrets" lines at ~319/333).
**Effort:** S (mostly verification).

---

## Priority order (what to fix, in sequence)

| Order | Item | Severity | Effort | Unblocks |
|---|---|---|---|---|
| 1 | **B1 — Persistent storage** | Blocker | S–M | "pull Roofr data in" + every future stateful feature |
| 2 | **B2 — Jobs-tab update UI** | Blocker | S | "update Roofr" (the headline MVP verb) |
| 3 | **M2 — Model id → env var + account confirmation** | Major | S | "runs without errors" / chat reliability |
| 4 | **N1 — Atomic + locked writes** *(only if keeping the flat file — skip if B1 → Postgres)* | Minor | S | data integrity under concurrent webhooks |
| 5 | **M1 — Production/scheduling data feed** | Major | M | "answer production/scheduling questions" |
| 6 | **N2 / N3 — Security & secret hygiene** | Minor | S | safe to put in front of staff/customers |

*Note on ordering #4:* N1 sits ahead of M1 because it's cheap data-integrity insurance — **but its necessity is contingent on B1's destination.** If B1 lands on a Railway volume (still a flat file), keep N1 at #4. If B1 lands on Supabase Postgres, drop N1 entirely and M1 moves up to #4.

**Bottom line.** The plumbing is real and the AI agent is no longer talk-only — that's a genuine step up from the original audit. But the app is **not yet a system of record** (B1) and an ordinary employee **still can't click to update Roofr** (B2). Those two, plus the model-id env var + account confirmation (M2), are the short path to actually meeting the stated MVP. M1 is the larger piece that turns "answers job/accounting questions" into the full "job/accounting/**production/scheduling**" promise — and it's the same work as the catalog's production-log and calendar features, so it doubles as your first real coating-specific build.