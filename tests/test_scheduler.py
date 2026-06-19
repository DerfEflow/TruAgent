"""In-process scheduler unit test (built-in scheduled scans).

Standalone + dependency-light (no pytest). Run with the project venv:

    .\\.venv\\Scripts\\python.exe tests\\test_scheduler.py

Monkeypatches main.load_db/save_db with an in-memory db and exercises
_run_due_scheduled_tasks: the first tick runs every due db-only job and persists
last-run stamps; an immediate second tick runs nothing (intervals not elapsed);
back-dating the heartbeat stamp makes ONLY the hourly heartbeat re-run.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402

_failures = []
def check(cond, msg):
    if not cond:
        _failures.append(msg)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {msg}")


def run():
    db = main._seed_db()
    main._normalize_db(db)
    store = {"db": db}
    main.load_db = lambda: store["db"]
    main.save_db = lambda d: store.__setitem__("db", d)

    print("-- first tick: all scheduled jobs due --")
    ran1 = {t for t, _ in main._run_due_scheduled_tasks()}
    check(ran1 == {"compliance_scan", "anomaly_scan", "suite_sync_heartbeat"},
          f"first tick runs all 3 db-only jobs (got {sorted(ran1)})")
    d = store["db"]
    check("compliance_alerts" in d, "compliance_scan wrote compliance_alerts")
    check("anomaly_snapshot" in d, "anomaly_scan wrote anomaly_snapshot")
    check("sync_heartbeat" in d, "suite_sync_heartbeat wrote sync_heartbeat")
    check(set(d.get("scheduler_runs", {})) >= {"compliance_scan", "anomaly_scan", "suite_sync_heartbeat"},
          "last-run stamps persisted for all 3 jobs")

    print("-- second tick immediately: nothing due --")
    ran2 = main._run_due_scheduled_tasks()
    check(ran2 == [], f"nothing re-runs within its interval (got {ran2})")

    print("-- back-date heartbeat >1h: only the hourly heartbeat re-runs --")
    store["db"]["scheduler_runs"]["suite_sync_heartbeat"] = \
        (datetime.now() - timedelta(hours=2)).isoformat()
    ran3 = [t for t, _ in main._run_due_scheduled_tasks()]
    check(ran3 == ["suite_sync_heartbeat"], f"only the hourly heartbeat is due (got {ran3})")

    print()
    if _failures:
        print(f"SCHEDULER TEST: FAILED ({len(_failures)} check(s))")
        for f in _failures:
            print("  - " + f)
        return 1
    print("SCHEDULER TEST: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(run())
