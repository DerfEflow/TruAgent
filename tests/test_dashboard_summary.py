"""Integration test for GET /dashboard/summary (step 9 cross-app dashboard).

Standalone + dependency-light: no pytest required. Run with the project venv:

    .\\.venv\\Scripts\\python.exe tests\\test_dashboard_summary.py

It seeds an in-memory db, monkeypatches main.load_db, and calls the route
handler directly via asyncio to prove the role gating and computations:

  (a) a 'user' (field crew) response has NO 'leads' key and financials is null
  (b) a 'manager' response includes financials and EXCLUDES scope=='public' leads
  (c) by_stage counts and thin_flags / thin_flag_total compute correctly
"""
import asyncio
import os
import sys

# Make the repo root importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def _seed_db() -> dict:
    return {
        "users": {
            "crew@x.com": {"email": "crew@x.com", "role": "user"},
            "boss@x.com": {"email": "boss@x.com", "role": "manager"},
        },
        "jobs": {
            "1001": {
                "job_id": "1001", "client_name": "Acme Warehouse",
                "address": "123 Main St", "status": "In Progress",
                "workflow_stage": "In Progress", "pct_complete": 40.0,
                "alerts": [{"type": "gallons_overrun"}],
                "production_logs": [
                    {
                        "date": "2026-06-10", "crew": "Blue", "sqft_coated": 5000,
                        "logged_at": "2026-06-10T12:00:00",
                        "dft_readings": [
                            {"reading": 18, "is_thin": True, "sample_number": 1},
                            {"reading": 22, "is_thin": False, "sample_number": 2},
                        ],
                        "wft_readings": [
                            {"reading": 30, "is_thin": True},
                        ],
                    },
                    {
                        "date": "2026-06-11", "crew": "Blue", "sqft_coated": 3000,
                        "logged_at": "2026-06-11T12:00:00",
                        "dft_readings": [
                            {"reading": 25, "is_thin": False, "sample_number": 1},
                        ],
                        # no wft_readings on this log
                    },
                ],
            },
            "1002": {
                "job_id": "1002", "client_name": "Bay Storage",
                "address": "9 Dock Rd", "status": "Pending",
                "workflow_stage": "Lead", "pct_complete": 0.0,
                # no alerts, no production_logs
            },
            "1003": {
                "job_id": "1003", "client_name": "No Stage Co",
                "address": "5 Blank Ave", "status": "Pending",
                # no workflow_stage -> should bucket under "Unstaged"
            },
        },
        "opportunities": {
            "opp_1": {"id": "opp_1", "client_name": "Truline Lead A",
                      "source": "roofr", "stage": "New Lead",
                      "last_seen": "2026-06-14T10:00:00", "scope": None},
            "opp_2": {"id": "opp_2", "client_name": "Public Dominate Co",
                      "source": "dominate", "stage": "New Lead",
                      "last_seen": "2026-06-14T11:00:00", "scope": "public"},
            "opp_3": {"id": "opp_3", "client_name": "Won Client",
                      "source": "referral", "stage": "Won",
                      "last_seen": "2026-06-13T09:00:00", "scope": None},
        },
        "financials": {
            "invoices": {"INV-1": {"amount": 10000, "status": "sent"}},
            "expenses": {"EXP-1": {"amount": 4000}},
        },
    }


async def _call(role: str) -> dict:
    user = {"email": "x", "role": role}
    return await main.dashboard_summary(current_user=user)


def main_test() -> int:
    seed = _seed_db()
    main.load_db = lambda: seed  # monkeypatch the data layer

    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # ---- (a) field crew: no leads key, financials null ----
    user_resp = asyncio.run(_call("user"))
    check("leads" not in user_resp, "FAIL(a): 'user' response must NOT contain a 'leads' key")
    check(user_resp.get("financials") is None, "FAIL(a): 'user' financials must be null")
    check(user_resp.get("role") == "user", "FAIL(a): role echoed should be 'user'")

    # ---- (b) manager: financials present, public leads excluded ----
    mgr_resp = asyncio.run(_call("manager"))
    fin = mgr_resp.get("financials")
    check(isinstance(fin, dict), "FAIL(b): 'manager' financials must be present")
    check(fin and fin.get("total_revenue") == 10000, "FAIL(b): revenue should be 10000")
    check(fin and fin.get("total_costs") == 4000, "FAIL(b): costs should be 4000")
    check(fin and fin.get("profit") == 6000, "FAIL(b): profit should be 6000")
    check(fin and fin.get("margin_percent") == 60.0, "FAIL(b): margin should be 60%")

    leads = mgr_resp.get("leads")
    check(isinstance(leads, dict), "FAIL(b): 'manager' must have a leads block")
    lead_names = [r["client_name"] for r in (leads or {}).get("recent", [])]
    check("Public Dominate Co" not in lead_names,
          "FAIL(b): scope=='public' lead must be excluded")
    check("Truline Lead A" in lead_names, "FAIL(b): non-public lead should appear")
    check("Won Client" in lead_names,
          "FAIL(b): won lead still shows in recent (it is just not 'open')")
    # open = visible (non-public) minus terminal stages. opp_1 open, opp_3 Won. => 1
    check(leads and leads.get("open") == 1,
          f"FAIL(b): open should be 1, got {leads and leads.get('open')}")

    # ---- (c) by_stage + thin flags ----
    by_stage = mgr_resp["jobs"]["by_stage"]
    check(by_stage.get("In Progress") == 1, f"FAIL(c): In Progress count, got {by_stage}")
    check(by_stage.get("Lead") == 1, f"FAIL(c): Lead count, got {by_stage}")
    check(by_stage.get("Unstaged") == 1, f"FAIL(c): Unstaged count, got {by_stage}")
    check(mgr_resp["jobs"]["total"] == 3, "FAIL(c): total jobs should be 3")

    # job 1001: log1 has 2 thin (1 dft + 1 wft), log2 has 0 -> total 2
    check(mgr_resp["field"]["thin_flag_total"] == 2,
          f"FAIL(c): thin_flag_total should be 2, got {mgr_resp['field']['thin_flag_total']}")
    log_flags = {l["date"]: l["thin_flags"] for l in mgr_resp["field"]["recent_logs"]}
    check(log_flags.get("2026-06-10") == 2, f"FAIL(c): 06-10 thin_flags, got {log_flags}")
    check(log_flags.get("2026-06-11") == 0, f"FAIL(c): 06-11 thin_flags, got {log_flags}")

    # alert_count surfaces on the recent jobs
    recent_alerts = {j["job_id"]: j["alert_count"] for j in mgr_resp["jobs"]["recent"]}
    check(recent_alerts.get("1001") == 1, f"FAIL(c): 1001 alert_count, got {recent_alerts}")
    check(recent_alerts.get("1002") == 0, f"FAIL(c): 1002 alert_count, got {recent_alerts}")

    # field crew sees the same operational job/field data (no money/leads leak)
    check(user_resp["field"]["thin_flag_total"] == 2,
          "FAIL(a): field crew still gets thin_flag_total")
    check(user_resp["jobs"]["total"] == 3, "FAIL(a): field crew still gets job counts")

    if failures:
        print("DASHBOARD SUMMARY TEST: FAILED")
        for f in failures:
            print("  - " + f)
        return 1
    print("DASHBOARD SUMMARY TEST: PASSED (a role-gate, b financials+lead-scope, c by_stage+thin_flags)")
    return 0


if __name__ == "__main__":
    sys.exit(main_test())
