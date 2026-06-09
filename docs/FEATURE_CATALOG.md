# TruAgent Feature Catalog — Roof Coating Operations

*Decision-ready catalog for Truline Roofing's internal AI ops app. Grouped by domain, split into MVP / Fast-follow / Later, with effort (S/M/L) and roles. Ends with a Top-10 "build next" shortlist you can pick from by number.*

**How to read effort:** S = a few hours to a day. M = a few days. L = a week-plus. All scoped to your solo, autonomous build pace.

**Roles:** `SA` = super_admin (you), `MGR` = manager (office), `USR` = field crew (operational only, never financials).

---

## 1. Field Production, Coating QA & Warranty

This is the "production half" of the app — today it has **no data feed at all**, so every item here is net-new value.

| Feature | What it gives you | Tier | Effort | Roles |
|---|---|---|---|---|
| **Daily Production Log ingest (from Delta)** | Inbound webhook appends each crew's end-of-day log (gallons by product, sqft coated, **wet-mil readings**, hours, weather, photos) to a job's `production_logs[]`. The single biggest production data feed. | MVP | M | SA/MGR/USR |
| **Gallons applied vs. estimated tracker** | Running total + % of estimate consumed per product, flags when gallons cross estimate before the roof is fully coated. Note: *applied* gallons are one of three distinct gallon buckets (estimated / applied / purchased — see Cross-Domain Patterns); this feature tracks applied vs estimated only and must not be summed with QuickBooks *purchased* gallons. | MVP | M | SA/MGR |
| **Coverage-rate reconciliation (sqft/gal → achieved dry-mil)** | Computes achieved dry-mil from gallons applied, coated sqft, and the **per-product volume-solids percentage pulled from the specs corpus** (dry-mil ≈ gallons × 1604 × volume-solids% ÷ sqft); compares to estimate AND manufacturer spec minimum; flags too-thin (warranty risk) or too-thick (margin loss). **Volume-solids is the controlling variable and differs sharply by chemistry** — silicones often 90–96%, water-based acrylics ~45–55%, some solvent products lower — so it is read per product, never a generic constant. | MVP | M | SA/MGR |
| **Dry-mil thickness log & QA checkpoint** | Crew logs **wet-mil readings taken during application** (the real-time gauge) per coat per section; converts to expected dry-mil via the product's volume-solids; later dry-mil verification (often destructive) is recorded separately. Auto-flags below warranty minimum. | MVP | M | SA/MGR/USR |
| **Substrate prep sign-off checklist** | Per-area prep gate (clean, rust, seams, ponding, primer, sealing) signed by crew lead; required items driven by substrate type. | MVP | M | SA/MGR/USR |
| **Weather / dew-point application window check** | Per application event, record temp/surface/RH/dewpoint/wind vs the product's window; flag out-of-window applications. Also captures the **post-application rain-free hours actually achieved** vs the product's minimum-cure-before-rain (the spec line that voids acrylic warranties). | MVP | M | SA/MGR/USR |
| **Job production dashboard & % complete** | Per-job rollup (sqft coated, gallons vs est, current coat, crew-days, weather status, QA flags) + a "production health" badge on the jobs list. | MVP | M | SA/MGR/USR |
| **Inter-coat recoat-window & cure-time tracker** | Tracks coats as ordered stages with the required *inter-coat recoat WINDOW* (hours-to-days between coats during install) and cure intervals; warns on too-soon recoat or a lapsed window that would force re-prep/scuff. *(Distinct from the multi-year maintenance re-coat cycle in Sales — see naming note below.)* | Fast-follow | M | SA/MGR |
| **Photo documentation tied to job/area/stage** | Photos tagged to job + roof area + stage (before/prep/each coat/after) with timestamp; gallery per job. *Needs persistent storage.* | Fast-follow | M | SA/MGR/USR |
| **Punch list per job** | Open items (touch-ups, thin spots, unsealed penetrations) with area/assignee/photo/status; auto-seeded from failed QA. | Fast-follow | S | SA/MGR/USR |
| **AI production assistant (field-data Q&A)** | Chat answers "which jobs are over their estimated gallons / had out-of-window applications / are missing mil readings." Field role stays financial-blind. | Fast-follow | M | SA/MGR/USR |
| **Final QA inspection & customer sign-off packet** | Confirms prep/mil/cure/punch-list/photos all complete, then generates a customer-approvable sign-off. Triggers final invoicing + warranty clock. | Later | M | SA/MGR |
| **Manufacturer warranty registration tracker** | Captures system/warranty type/required mil/deadline; pre-flights documentation before submission; stores returned warranty number. | Later | L | SA/MGR |
| **Rework / callback tracking** | Logs callbacks (blistering, delamination, thin-spot) with cause, extra gallons/hours, warranty coverage; rolls cost back into job profitability. | Later | M | SA/MGR |

> **Naming note (avoids a data-model collision):** two different intervals share the word "recoat." Sec 1 owns the short **inter-coat window** (hours-to-days between coats during install). Sec 3 owns the multi-year **renewal / re-coat cycle** at end of warranty life (the recurring-revenue flywheel). Keep them named distinctly in the schema (`inter_coat_window` vs `renewal_recoat_cycle`) so they never get conflated.

---

## 2. Accounting, Job Costing & Finance

Job costing is meaningless without the **estimate baseline** — that one import unlocks every variance/margin/WIP feature.

| Feature | What it gives you | Tier | Effort | Roles |
|---|---|---|---|---|
| **Estimate baseline import (from Alpha Estimator)** | Pulls each won estimate in as the job's `budget` block (contract value, gallons/product, dry-mil, sqft, labor hours by method, quoted margin, **and the loaded-labor-rate + material-$/gal assumptions** so downstream projected costing has multipliers to apply). The yardstick for everything else. | MVP | M | SA/MGR |
| **Coating material cost tracking by gallon** | QuickBooks expense lines carry product/manufacturer/**gallons purchased**/$-per-gal/lot#; rolls up purchased-vs-budgeted gallons; flags PO price drift. Note: *purchased* gallons is the third distinct gallon bucket (vs *estimated* and *applied*) — kept separate, never summed (see Cross-Domain Patterns). | MVP | M | SA/MGR |
| **Labor cost capture w/ 45% burden (from Delta)** | Daily crew hours → burdened labor cost (hours × loaded rate × 1.45), split spray vs prep/roller for variance vs estimate. The loaded rate comes in on the Alpha estimate baseline or a config — TruAgent holds no rate table of its own. | MVP | M | SA/MGR |
| **Per-job cost-category breakdown** | Buckets cost into burdened labor / material (gal) / equipment & solvent / prep / sub / other instead of one lump profit number. | MVP | M | SA/MGR |
| **Margin alert vs. estimate** | Fires when live margin drops >5 pts below quote or gallons/hours exceed budget; surfaces in finance tab, AI chat, and optionally email/SMS. *Scheduled variant depends on the scheduler + persistent storage landing first.* | MVP | S | SA/MGR |
| **Company-wide profitability dashboard** | Backlog, billed-to-date, blended margin, sliced by coating system / substrate / crew / month. Tells you which systems and substrates actually make money. | MVP | M | SA/MGR |
| **WIP report (earned vs billed)** | Percent-complete per job → earned revenue, billed-to-date, over/under-billing position. What your accountant and bonding agent expect. | Fast-follow | M | SA/MGR |
| **Progress billing w/ draw schedule & retainage** | Deposit + milestone draws + held retainage (typ. 10%); computes next due draw and pushes a QuickBooks invoice via Zapier net of retainage. | Fast-follow | L | SA/MGR |
| **Change order tracking** | Per-job CO log (discovered wet insulation, extra fabric, extra pass) with added gallons/hours/price/approval; approved COs revise the baseline. | Fast-follow | M | SA/MGR |
| **AR aging & collections view** | Buckets unpaid invoices 0-30/31-60/61-90/90+; one-click reminder via existing comms webhooks; retainage tracked separately. | Fast-follow | S | SA/MGR |
| **AP / vendor bill & PO tracking** | Expenses grouped by vendor with due-date aging + optional PO capture and PO-to-bill matching to catch material overruns early. | Later | M | SA/MGR |
| **Payroll / time export** | Aggregates Delta hours per employee per pay period (spray vs prep, per-job) into a payroll-ready CSV/webhook. | Later | S | SA/MGR |
| **Equipment & consumables cost allocation** | Allocates spray-rig day-rate, hose/tip wear, solvent, fuel/mob to jobs so spray cost stops hiding in overhead. | Later | M | SA/MGR |
| **Warranty-hold / retainage-release tracker** | Gates the final retainage-release invoice on warranty registered + final inspection passed + punch list cleared. | Later | M | SA/MGR |

---

## 3. Sales, Estimating Pipeline & CRM

| Feature | What it gives you | Tier | Effort | Roles |
|---|---|---|---|---|
| **Unified sales pipeline (Kanban by stage)** | Coating-specific stages (New Lead → Site Survey → Measured/Cores → Estimating → Proposal → Negotiation → Won/Lost); drag-to-advance pushes the stage to Roofr via the existing outbound webhook. | MVP | M | SA/MGR/USR |
| **Lead intake normalizer & router** | One inbound door ingests leads from Dominate / Roofr / web / phone, tags source + geography, dedupes by address+name, assigns rep, stamps a first-touch SLA. | MVP | M | SA/MGR |
| **Follow-up cadence engine** | Per-stage reminders ("no contact 48h after Proposal Sent", "weather-postponed → rebook"); cadence templates aware of weather-window sensitivity. *Needs a scheduler (and persistent storage so the cadence state survives deploys).* | MVP | M | SA/MGR/USR |
| **Estimate/proposal pipeline sync (Alpha)** | Creates/updates an opportunity with full coating scope (system, gallons, dry-mil, prep, warranty, price); revised estimates update in place, not duplicate. | MVP | M | SA/MGR |
| **Win/Loss tracking w/ coating loss reasons** | Structured loss reasons (price, chose tear-off, competitor system, substrate too saturated, warranty too short, weather); win-rate by source/rep/substrate/system. | MVP | S | SA/MGR |
| **Proposal e-sign / acceptance capture** | Sends the Alpha proposal for signature; acceptance flips stage to Won, attaches the PDF, and fires the production/procurement handoff. | Fast-follow | M | SA/MGR |
| **Referral & online-review capture** | On completion, queues a review-ask timed to post-cure; captures referrals as new source-tagged leads (loops to Dominate). | Fast-follow | M | SA/MGR |
| **Renewal / re-coat maintenance engine** | Stores warranty term + install date + achieved mil, computes a **renewal re-coat-due date** (the multi-year maintenance cycle, NOT the inter-coat window from Sec 1), and surfaces "due for re-coat" warm leads with original scope pre-filled. **The recurring-revenue flywheel.** | Fast-follow | M | SA/MGR |
| **Territory & rep performance dashboard** | Per-rep/territory: leads, SLA hit rate, win rate, gallons sold, value, margin (money columns manager+ only). | Fast-follow | M | SA/MGR |
| **AI pipeline copilot** | Chat queries by gallons/system/renewal-due, advances stages, logs win/loss, drafts cadence emails. | Fast-follow | M | SA/MGR/USR |
| **Opportunity timeline & comm log** | One activity feed per opportunity: emails/SMS, stage changes, estimate revisions, signed events, survey notes. | Fast-follow | S | SA/MGR/USR |
| **Weather-window & quote-expiry watchlist** | Flags proposals whose quote is expiring or whose seasonal application window is closing; sends a "lock in before the season closes" nudge. | Later | M | SA/MGR/USR |
| **Proposal versioning & change tracking** | Tracks estimate versions (v1 acrylic 20-mil vs v2 silicone 25-mil + seam fabric); shows the diff and which version is active/accepted. | Later | M | SA/MGR |
| **Sales-to-production & procurement handoff** | On Won, generates a structured handoff (system, gallons, mil, prep, site notes) to Delta + an optional material PO draft. | Later | M | SA/MGR |

---

## 4. Scheduling, Dispatch & Crew

Coating is weather-bounded and sequenced (prep → cure → coat → cure → coat). Generic schedulers can't model this.

| Feature | What it gives you | Tier | Effort | Roles |
|---|---|---|---|---|
| **Crew calendar & job scheduling board** | Drag-and-drop day/week board assigning Roofr jobs to crews/dates; multi-day blocks colored by stage. There is nowhere to lay out the week today. | MVP | M | SA/MGR/USR |
| **Weather-aware application window flags** | Morning forecast per job address vs per-system limits → GREEN/YELLOW/RED day, checking both application-time limits AND the post-application rain-free window. The defining scheduling risk for coating. *Needs scheduler + weather source (and persistent storage).* | MVP | M | SA/MGR/USR |
| **Per-coating-system weather rule profiles** | Admin-editable table of limits per chemistry, seeded from the scraped specs corpus. Columns: min/max air temp, min/max surface temp, RH ceiling, surface-minus-dewpoint, application-time rain-free hours, **post-application minimum-cure-before-rain hours** (a first-class column — this is the moisture-sensitivity line that voids acrylic and single-component moisture-cure urethane warranties, and where silicones are far more tolerant), and the inter-coat recoat window. | MVP | M | SA/MGR |
| **Estimate-to-schedule intake (Alpha)** | Won estimate creates/updates a job pre-filled with system, dry-mil, gallons, sqft, substrate — the exact inputs the calendar + weather + material engines need. | Fast-follow | M | SA/MGR |
| **Multi-day coating sequence templates** | Job = ordered phases with cure gaps; calendar auto-lays phases, inserts required inter-coat windows, skips RED days. | Fast-follow | L | SA/MGR |
| **Equipment & sprayer assignment** | Registry of rigs/tips/lifts assignable per job/day; hard-blocks double-booking the spray rig (your scarcest resource). | Fast-follow | M | SA/MGR |
| **Material staging & delivery coordination** | Computes required gallons, sets a material-needed-by date tied to first coat, flags un-staged jobs N days from start. | Fast-follow | M | SA/MGR |
| **Daily dispatch sheet (night-before auto-send)** | Per-crew tomorrow sheet (address, access notes, system + target mil, gallons staged, weather verdict, phase) via existing email/SMS Zaps. Field-safe (no pricing). | Fast-follow | M | SA/MGR/USR |
| **Crew time & location check-in** | Tap Arrive/Depart with timestamp + optional geolocation → `timelog`; feeds labor cost into financials. | Fast-follow | M | SA/MGR/USR |
| **Cure & inter-coat-window tracker** | Per completed coat, displays earliest/latest next-coat date and alerts when the inter-coat window is about to close (missing it = re-prep the whole roof). | Later | S | SA/MGR/USR |
| **Weather auto-reschedule & crew notify** | RED day auto-marks the phase weather-held, cascades cure/recoat windows forward, notifies crew + office, logs the reason for warranty. | Later | L | SA/MGR/USR |
| **Subcontractor coordination & scheduling** | Subs as a scheduling resource with insurance-expiry visibility; prevents an uninsured sub on the roof. | Later | M | SA/MGR |
| **Delta progress sync** | Daily log advances the phase, decrements remaining gallons/area, updates % complete on the calendar; thin mils raise a QA flag. | Later | M | SA/MGR/USR |
| **Schedule conflict & readiness pre-flight** | One-click "what's not ready next week" — weather + sprayer + material + spec + cure timing in one list, also answerable in chat. | Later | M | SA/MGR |
| **Seasonal capacity & backlog planner** | Buckets unscheduled backlog (gallons + crew-days) against remaining good-weather days in the season → hire/defer/push decision. | Later | L | SA/MGR |

---

## 5. Office Admin, Compliance & Safety

| Feature | What it gives you | Tier | Effort | Roles |
|---|---|---|---|---|
| **COI registry & expiry tracking (company + subs)** | Stores COIs with carrier/limits/expiry; daily scan flags 30/14/0-day expirations. Expired sub COI = crew turned away at the gate. *The scan depends on persistent storage + scheduler.* | MVP | M | SA/MGR |
| **Subcontractor / vendor compliance profiles** | A `parties` record per sub/vendor (COI, W-9, subcontract, trade) with a green/yellow/red "cleared to work" rollup. | MVP | M | SA/MGR |
| **Document template library + mail-merge** | Reusable subcontract/proposal/warranty/lien-waiver templates with merge tokens ({{coating_system}}, {{dry_mil_spec}}, {{warranty_years}}). | MVP | M | SA/MGR |
| **Manufacturer warranty document registry** | Per-job warranty record tying the cert to as-applied system + dry-mil + lots; surfaces "registration pending" until the cert is on file. | MVP | M | SA/MGR |
| **SDS library for coatings & solvents** | Phone-accessible Safety Data Sheets by product (coatings, primers, xylene/MEK). OSHA HazCom requirement. | MVP | S | SA/MGR/USR |
| **Employee certification & training tracker** | Per-employee OSHA, fall-protection, respirator fit-test, lift cert, manufacturer applicator cert with expiry alerting. Lapsed fit-test = OSHA violation + barred crew. | MVP | M | SA/MGR |
| **Compliance dashboard with AI Q&A** | One tab rolling up everything expiring/missing; ask "which subs can't work next week?" The payoff screen that makes the trackers get used. | MVP | M | SA/MGR |
| **Persistent storage migration (compliance)** | Move db.json + documents off ephemeral Railway disk so signed contracts/COIs/warranties survive restarts. Foundation for all of the above. | Fast-follow* | M | SA |
| **Lien waiver generation & tracking** | Generates conditional/unconditional progress/final waivers from job + payment data; tracks sent → signed → received per job and per sub. | Fast-follow | M | SA/MGR |
| **Customer communication log** | Auto-captured per-job timeline of every email/SMS sent + logged calls/site visits. Defends disputes ("we told the owner the silicone needed 24h cure"). | Fast-follow | S | SA/MGR/USR |
| **Permit tracker** | Per-job permit records + status gate so a job can't be marked ready-to-start without an issued permit where required. | Fast-follow | S | SA/MGR |
| **Job safety / pre-task plan (JHA)** | Coating-specific JHA (fall protection, respirator/solvent controls, silica, overspray/wind limits) auto-filled from the job's system; daily crew sign-off. | Fast-follow | M | SA/MGR/USR |
| **Contract / proposal e-signature routing** | Routes proposals/subcontracts/warranties for e-sign; tracks sent → viewed → signed; files the executed PDF on the job. | Later | M | SA/MGR |
| **Insurance audit & renewal package export** | Cross-references sub payments (QuickBooks) with COI validity during the work period; flags any sub paid while uninsured. Saves back-charged workers'-comp premium. | Later | M | SA/MGR |

\* *Storage migration is logically MVP-blocking (see the gap doc) — listed here under the compliance lens where it was raised, but treat it as a foundation item, not optional.*

---

## 6. AI Assistant, Voice & Mobile-First Field UX

Note: your live `/chat` is **already an agentic tool-calling loop** (it can list/read jobs, update status, add notes — both syncing to Roofr — send email/SMS, and read financials for manager+). Several items below extend that real foundation rather than build it from scratch.

| Feature | What it gives you | Tier | Effort | Roles |
|---|---|---|---|---|
| **Structured voice field report** | Crew speaks a daily report; the existing Whisper endpoint (`/transcribe`, `main.py:1231`, model `whisper-1`) transcribes it, then a chat/extraction call turns the transcript into a typed object (job, gallons, product, wet-mil, sqft, prep, weather, hours) and writes a `production_log` entry with a confirm card. Whisper alone is not sufficient — **the extractor reuses the same chat-completions model and therefore depends on the `OPENAI_MODEL` env-var fix from #3** (today that model is the hardcoded `gpt-5.5`). Turns the existing mic into the core field data pipe. | MVP | M | USR/MGR/SA |
| **Morning ops digest (role-scoped)** | Once-daily push per role: stalled jobs, gallons-over-estimate, past-due invoices, unscheduled approved jobs (mgr); today's addresses + system + target mil + weather (crew). *Needs scheduler + persistent storage.* | MVP | M | MGR/SA/USR |
| **Document RAG over specs/SDS/warranties/contracts** | On upload, parse + embed; chat answers "what's the inter-coat window / volume-solids for the Gaco silicone?" **with a citation.** Today the AI literally can't read the file contents — this closes that gap, and the volume-solids it surfaces feeds the dry-mil reconciliation in Sec 1. | MVP | L | USR/MGR/SA |
| **Natural-language job report** | "How did we do on the Acme job?" → stage, gallons vs est, mil compliance, days on site, money (manager+ only, stripped at the data layer for crew), open issues, next action. | MVP | S | MGR/SA/USR |
| **Persistent storage migration (AI/history foundation)** | Move db.json + documents to a Railway volume / managed store so production logs, embeddings, warranty dates, and digest history survive deploys. **Precondition for everything that remembers over time — including every scheduled scan below, whose value is near-zero until this lands.** | MVP | S–M | SA |
| **Weather-window go/no-go alerts per active job** | Scheduled forecast check vs the *spec'd product's* cure constraints — including the post-application minimum-cure-before-rain window, not just application-time limits; same-day SMS ("acrylic min temp not met until 10am; rain forecast inside the cure window will void the warranty — silicone field only or push to Thu"). *Hard-depends on scheduler + persistent storage.* | Fast-follow | M | MGR/SA/USR |
| **Material reconciliation & dry-mil coverage check** | Math tying gallons applied + coated sqft + the **per-product volume-solids% from the specs corpus** → achieved dry-mil vs warranty minimum (dry-mil ≈ gallons × 1604 × volume-solids% ÷ sqft); flags under-application (warranty void) and over-application (margin loss). Volume-solids is read per product, never assumed — silicones run 90–96%, acrylics ~45–55%, so a single constant would make the achieved-mil number meaningless. Where available, reconciles against the crew's wet-mil readings too. | Fast-follow | M | MGR/SA |
| **Job-over-budget & stalled-job anomaly detection** | Scheduled scan flags margin under floor, jobs with no log/expense in N days, past-due invoices, approved-no-start; each becomes a digest line + "Needs Attention" badge. *Hard-depends on scheduler + persistent storage.* | Fast-follow | M | MGR/SA |
| **Mobile-first field mode** | Dedicated crew view: oversized voice button, big tappable job cards (address + system + target mil + weather), photo capture, offline queue. No financial UI renders at all for this role. | Fast-follow | L | USR |
| **Sibling-app intake (Alpha estimates / Dominate leads)** | Configurable inbound webhook seeds coating job fields (system, dry-mil, sqft, est gallons, price) — the baseline that makes reconciliation/anomaly detection possible. | Fast-follow | M | MGR/SA |
| **Photo intake with AI defect/coverage tagging** | A vision model auto-tags ponding/blistering/exposed substrate/rust/incomplete coverage; searchable warranty evidence. **Net-new model plumbing, not an extension of the current chat loop:** the app today only calls text chat-completions (the hardcoded `gpt-5.5`) and `whisper-1` — there is no vision-capable model wired and no image-upload path into the model. This requires both, plus persistent storage. *Needs vision model + image pipeline + persistent storage.* | Later | M | USR/MGR/SA |
| **Warranty & renewal re-coat tracker w/ reminders** | Captures manufacturer/term/install date/renewal interval; proactively flags renewal re-coat dates and registration deadlines. *Reminders depend on scheduler + persistent storage.* | Later | M | MGR/SA |
| **Customer closeout & status comms (AI-drafted, human-approved)** | Drafts coating-specific closeout (system, dry-mil achieved, warranty, before/after photos) and milestone updates; owner approves before send. | Later | S | MGR/SA |

---

## Cross-Domain Patterns Worth Noticing

A handful of items appear in multiple panels because they're load-bearing for the whole suite. When the same capability shows up 3-4 times, that's the signal to build it early:

- **Estimate baseline import from Alpha** appears in Finance, Sales, Scheduling, and AI. It's the yardstick for every variance/margin/coverage/anomaly feature, and it also carries the loaded-labor-rate + material-$/gal multipliers that downstream projected costing needs. **Build the inbound estimate door once; four domains light up.**
- **Daily Production Log ingest from Delta** appears in Production, Finance (labor/material actuals), Scheduling (% complete), and AI (voice/anomaly). **The second universal door.**
- **The three-bucket gallon model.** A single job carries **three different gallon numbers that must never be summed or conflated:** *estimated* gallons (from the Alpha baseline), *applied* gallons (from Delta field logs), and *purchased* gallons (from QuickBooks expense lines). "Gallons applied vs estimated" uses the first two; "purchased-vs-budgeted gallons" uses estimated + purchased. Keep all three as distinct fields with distinct provenance so reconciliation stays honest (you genuinely want to see when applied < purchased — that's waste or theft — and when applied > estimated — that's a margin leak).
- **Volume-solids is the controlling variable for every coverage/mil calculation.** It is a per-product spec-corpus field (silicones ~90–96%, acrylics ~45–55%, some solvent products lower), so the reconciliation features pull it per product rather than assuming a constant. Wire it once; Sec 1 coverage-rate, Sec 6 material reconciliation, and the RAG citation feature all consume it.
- **A scheduler** (Railway cron or a Zapier Schedule hitting an endpoint) is a hard dependency for cadence reminders, weather alerts, morning digests, COI/cert expiry scans, and renewal re-coat reminders. You have none today. **One scheduling primitive unblocks ~6 features across 4 domains — but every one of those scans reads data that the ephemeral disk wipes on each deploy, so the scheduler's value is near-zero until persistent storage (#1) lands. Sequence storage first.**
- **Persistent storage** is named MVP-blocking by three separate panels. Nothing that "remembers over time" is trustworthy until this lands.
- **Per-system weather rule profiles** (seeded from your scraped specs corpus) feed both Scheduling weather flags and AI go/no-go alerts — including the post-application minimum-cure-before-rain column that protects warranties.

---

## Top 10 Recommended Next Features (build-next shortlist)

Ordered by leverage-per-effort given what's *already* built. Pick by number.

| # | Feature | Why it's next | Effort | Domain |
|---|---|---|---|---|
| **1** | **Persistent storage migration** | MVP-blocking. Every Railway redeploy wipes your synced jobs, documents, and new users today. Nothing else is trustworthy until this lands — and every scheduled scan (#6) is worthless until it does. Cheapest high-stakes fix. | S–M | Foundation |
| **2** | **Per-job-card UI controls (status dropdown + note box)** | Your backend can update Roofr, but **no button in the app reaches it** — only the AI or curl can. A deterministic manager+ control closes the headline "update Roofr" MVP gap independent of the AI. | S | Sales/Ops |
| **3** | **Make the chat model id an env var (`OPENAI_MODEL`)** | Model is hardcoded `gpt-5.5` in two places (`main.py:555, 582`) and contradicts the docs (`gpt-4o-mini`). One env var + a known-good default + a startup model-list check (confirm the id against the actual account, fall back to `gpt-4o` / `gpt-4o-mini`) means an unrecognized id never 500s your flagship feature. Also unblocks #7's voice extractor, which shares this model path. | S | AI |
| **4** | **Estimate baseline import from Alpha Estimator** | The yardstick that unlocks Finance variance, Sales pipeline scope, Scheduling inputs, and AI anomaly detection — all four at once. Also delivers the loaded-rate + $/gal multipliers and the *estimated* gallon bucket. The suite's spine. | M | Finance/Sales |
| **5** | **Daily Production Log ingest from Delta** | The single biggest production data feed; without it the app is blind to whether jobs are on pace or burning material. Lights up production dashboards, costing, and AI Q&A. Carries the *applied* gallon bucket + wet-mil readings. | M | Production |
| **6** | **A scheduler primitive (Zapier Schedule → endpoint)** | Unblocks morning digest, weather alerts, follow-up cadence, COI/cert expiry scans, and renewal reminders. Build the tick once — **but only after #1, since every scan reads data that ephemeral storage erases each deploy.** | S–M | Foundation |
| **7** | **Structured voice field report** | Reuses your existing Whisper endpoint (`/transcribe`); the extraction step rides the same chat model, so it lands cleanly once #3 is in. Turns the mic into the core field data pipe (gallons + wet-mil) that feeds reconciliation, warranty, and costing. Glove-friendly = data actually gets logged. | M | AI/Field |
| **8** | **Gallons-applied + coverage-rate + dry-mil reconciliation** | Once #4 + #5/#7 land, this is the coating-specific killer feature: ties field data to both warranty compliance and margin in one number. **Keys off per-product volume-solids from the specs corpus (not a constant)** and respects the three-bucket gallon model. No off-the-shelf tool does it. | M | Production/Finance |
| **9** | **Crew calendar + weather-window flags + per-system rule profiles** | There's nowhere to lay out the week today, and weather is *the* coating risk. Seed the rule profiles from your already-scraped specs corpus — including the post-application minimum-cure-before-rain column that voids acrylic warranties. | M (×2) | Scheduling |
| **10** | **Document RAG over specs/SDS/warranties** | Today the AI can't read document *contents*, only filenames. Embeddings + cited answers turn "call the rep" into a 5-second on-roof answer (including the volume-solids value #8 needs) and prevent warranty-voiding mistakes. | L | AI |

**Suggested sequencing:** Do the three foundation/cleanup items first (#1, #3, #6 — and note #6 must follow #1) and the cheap deterministic UI win (#2) — they're small and unblock the rest. Then build the two inbound doors (#4, #5) since they feed four domains apiece. Then the coating-specific payoff stack (#7 → #8) and the scheduling pair (#9). Save RAG (#10) for last in this set — highest effort, and it benefits from persistent storage (#1) already being in place.