# TruAgent Build Progress

Tracker for the feature set in `docs/NEXT_INSTANCE_BUILD_PLAN.md`. Build top-to-bottom. Tick a box only after the item is implemented **and** verified **and** committed. Don't push without Fred's OK.

## Phase F — Foundations (build first)
- [ ] F1. Inbound Alpha Estimator door — estimate baseline import
- [ ] F2. Inbound Delta door — daily production log ingest (= "Delta progress sync")
- [ ] F3. Inbound Dominate lead door + lead intake normalizer/router
- [ ] F4. Scheduler primitive (cron/Zapier-Schedule → endpoint)
- [ ] F5. QuickBooks expense enrichment → coating material cost by gallon
- [ ] F6. Per-coating-system weather rule profiles (+ weather source)

## Phase A — Accounting, Job Costing & Finance (all of Section 2)
- [ ] A7. Per-job cost-category breakdown
- [ ] A8. Labor cost capture w/ 45% burden (from Delta)
- [ ] A9. Gallons applied vs. estimated tracker
- [ ] A10. Coverage-rate reconciliation → achieved dry-mil
- [ ] A11. Margin alert vs. estimate
- [ ] A12. Company-wide profitability dashboard
- [ ] A13. WIP report (earned vs billed)
- [ ] A14. Progress billing w/ draw schedule & retainage
- [ ] A15. Change order tracking
- [ ] A16. AR aging & collections view
- [ ] A17. AP / vendor bill & PO tracking
- [ ] A18. Payroll / time export
- [ ] A19. Equipment & consumables cost allocation
- [ ] A20. Warranty-hold / retainage-release tracker

## Phase P — Production & QA (Sec 1 MVP + Fast-follow + requested warranty registration)
- [ ] P21. Dry-mil thickness log & QA checkpoint
- [ ] P22. Substrate prep sign-off checklist
- [ ] P23. Weather/dew-point application window check
- [ ] P24. Job production dashboard & % complete
- [ ] P25. Inter-coat recoat-window & cure-time tracker
- [ ] P26. Photo documentation tied to job/area/stage
- [ ] P27. Punch list per job
- [ ] P28. AI production assistant (field-data Q&A)
- [ ] P29. Manufacturer warranty registration tracker  *(requested Later item)*

## Phase S — Sales, Estimating Pipeline & CRM (Sec 3 MVP + Fast-follow)
- [ ] S30. Unified sales pipeline (Kanban by coating stage)
- [ ] S31. Follow-up cadence engine
- [ ] S32. Win/Loss tracking w/ coating loss reasons
- [ ] S33. Proposal e-sign / acceptance capture
- [ ] S34. Referral & online-review capture
- [ ] S35. Renewal / re-coat maintenance engine
- [ ] S36. Territory & rep performance dashboard
- [ ] S37. AI pipeline copilot
- [ ] S38. Opportunity timeline & comm log

## Phase C — Scheduling, Dispatch & Crew (Sec 4 MVP + Fast-follow)
- [ ] C39. Crew calendar & job scheduling board
- [ ] C40. Weather-aware application window flags (GREEN/YELLOW/RED)
- [ ] C41. Multi-day coating sequence templates
- [ ] C42. Equipment & sprayer assignment
- [ ] C43. Material staging & delivery coordination
- [ ] C44. Daily dispatch sheet (night-before auto-send)
- [ ] C45. Crew time & location check-in

## Phase O — Office Admin, Compliance & Safety (Sec 5 MVP + Fast-follow + requested e-sign routing)
- [ ] O46. COI registry & expiry tracking (company + subs)
- [ ] O47. Subcontractor / vendor compliance profiles
- [ ] O48. Document template library + mail-merge
- [ ] O49. Manufacturer warranty document registry
- [ ] O50. SDS library for coatings & solvents
- [ ] O51. Employee certification & training tracker
- [ ] O52. Compliance dashboard with AI Q&A
- [ ] O53. Lien waiver generation & tracking
- [ ] O54. Customer communication log
- [ ] O55. Permit tracker
- [ ] O56. Job safety / pre-task plan (JHA)
- [ ] O57. Contract / proposal e-signature routing  *(requested Later item)*

## Phase I — AI, Voice & Mobile-First Field UX (Sec 6 MVP + Fast-follow)
- [ ] I58. Structured voice field report
- [ ] I59. Morning ops digest (role-scoped)
- [ ] I60. Document RAG over specs/SDS/warranties/contracts
- [ ] I61. Natural-language job report
- [ ] I62. Job-over-budget & stalled-job anomaly detection
- [ ] I63. Mobile-first field mode

---
**Already done (this engagement's predecessor session):** persistent storage migration ✅ · AI agent tool-calling ✅ · Jobs-tab Roofr update controls ✅ · `OPENAI_MODEL` env var ✅
**Total to build:** 63 items (F1–I63).
