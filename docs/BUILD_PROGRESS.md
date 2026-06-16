# TruAgent Build Progress

Tracker for the feature set in `docs/NEXT_INSTANCE_BUILD_PLAN.md`. Build top-to-bottom. Tick a box only after the item is implemented **and** verified **and** committed. Don't push without Fred's OK.

## Phase F — Foundations (build first)
- [x] F1. Inbound Alpha Estimator door — estimate baseline import
- [x] F2. Inbound Delta door — daily production log ingest (= "Delta progress sync")
- [x] F3. Inbound Dominate lead door + lead intake normalizer/router
- [x] F4. Scheduler primitive (cron/Zapier-Schedule → endpoint)
- [x] F5. QuickBooks expense enrichment → coating material cost by gallon
- [x] F6. Per-coating-system weather rule profiles (+ weather source)

## Phase A — Accounting, Job Costing & Finance (all of Section 2)
- [x] A7. Per-job cost-category breakdown
- [x] A8. Labor cost capture w/ 45% burden (from Delta)
- [x] A9. Gallons applied vs. estimated tracker
- [x] A10. Coverage-rate reconciliation → achieved dry-mil
- [x] A11. Margin alert vs. estimate
- [x] A12. Company-wide profitability dashboard
- [x] A13. WIP report (earned vs billed)
- [x] A14. Progress billing w/ draw schedule & retainage
- [x] A15. Change order tracking
- [x] A16. AR aging & collections view
- [x] A17. AP / vendor bill & PO tracking
- [x] A18. Payroll / time export
- [x] A19. Equipment & consumables cost allocation
- [x] A20. Warranty-hold / retainage-release tracker

## Phase P — Production & QA (Sec 1 MVP + Fast-follow + requested warranty registration)
- [x] P21. Dry-mil thickness log & QA checkpoint
- [x] P22. Substrate prep sign-off checklist
- [x] P23. Weather/dew-point application window check
- [x] P24. Job production dashboard & % complete
- [x] P25. Inter-coat recoat-window & cure-time tracker
- [x] P26. Photo documentation tied to job/area/stage
- [x] P27. Punch list per job
- [x] P28. AI production assistant (field-data Q&A)
- [x] P29. Manufacturer warranty registration tracker  *(requested Later item)*

## Phase S — Sales, Estimating Pipeline & CRM (Sec 3 MVP + Fast-follow)
- [x] S30. Unified sales pipeline (Kanban by coating stage)
- [x] S31. Follow-up cadence engine
- [x] S32. Win/Loss tracking w/ coating loss reasons
- [x] S33. Proposal e-sign / acceptance capture
- [x] S34. Referral & online-review capture
- [x] S35. Renewal / re-coat maintenance engine
- [x] S36. Territory & rep performance dashboard
- [x] S37. AI pipeline copilot
- [x] S38. Opportunity timeline & comm log

## Phase C — Scheduling, Dispatch & Crew (Sec 4 MVP + Fast-follow)
- [x] C39. Crew calendar & job scheduling board
- [x] C40. Weather-aware application window flags (GREEN/YELLOW/RED)
- [x] C41. Multi-day coating sequence templates
- [x] C42. Equipment & sprayer assignment
- [x] C43. Material staging & delivery coordination
- [x] C44. Daily dispatch sheet (night-before auto-send)
- [x] C45. Crew time & location check-in

## Phase O — Office Admin, Compliance & Safety (Sec 5 MVP + Fast-follow + requested e-sign routing)
- [x] O46. COI registry & expiry tracking (company + subs)
- [x] O47. Subcontractor / vendor compliance profiles
- [x] O48. Document template library + mail-merge
- [x] O49. Manufacturer warranty document registry
- [x] O50. SDS library for coatings & solvents
- [x] O51. Employee certification & training tracker
- [x] O52. Compliance dashboard with AI Q&A
- [x] O53. Lien waiver generation & tracking
- [x] O54. Customer communication log
- [x] O55. Permit tracker
- [x] O56. Job safety / pre-task plan (JHA)
- [x] O57. Contract / proposal e-signature routing  *(requested Later item)*

## Phase I — AI, Voice & Mobile-First Field UX (Sec 6 MVP + Fast-follow)
- [x] I58. Structured voice field report
- [x] I59. Morning ops digest (role-scoped)
- [x] I60. Document RAG over specs/SDS/warranties/contracts
- [x] I61. Natural-language job report
- [x] I62. Job-over-budget & stalled-job anomaly detection
- [x] I63. Mobile-first field mode

---
**Already done (this engagement's predecessor session):** persistent storage migration ✅ · AI agent tool-calling ✅ · Jobs-tab Roofr update controls ✅ · `OPENAI_MODEL` env var ✅
**Total to build:** 63 items (F1–I63).
**All 63 items complete ✅ — verified locally 2026-06-09. Do NOT push to main without Fred's OK.**
