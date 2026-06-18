"""Security + inbound-door regression tests (launch hardening T2-T8).

Standalone + dependency-light (uses FastAPI's bundled TestClient, no pytest).
Run with the project venv from the repo root:

    .\\.venv\\Scripts\\python.exe tests\\test_security_doors.py

It boots the real app in-process against an ISOLATED temp DATA_DIR (never the
real db.json) with known test door secrets, and asserts:

  T2  GET /admin/webhook-info never returns the live ZAPIER_SECRET (masked hint
      only) and stays super-admin-gated.
  doors  every inbound door rejects a bad secret with 403 and accepts the valid
      secret (write path) — the fail-closed contract.
  role  field crew (user) cannot read /job/{id}/financials; manager can.
  T3  POST /login is rate-limited (429 after 5 failures from one IP).
  T4  /cron/tick authenticates via the X-Cron-Secret header (and the ?secret=
      query fallback), and rejects a bad/missing secret with 403.
  T7  save_db is guarded by a module-level write lock.
  T8  _normalize_db backfills outbox/sms_outbox as lists on an old db.
"""
import os
import sys
import tempfile

# -- Isolate BEFORE importing main: a throwaway DATA_DIR so no test ever touches
# the real db.json, and known door secrets so each door is enabled with a value
# we control. load_dotenv() runs at import with override=False, so these win. --
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="truagent_sec_test_")
os.environ["DATA_DIR"] = _TMP
os.environ["SESSION_SECRET"] = "test-session-secret-not-real"
os.environ["ZAPIER_SECRET"] = "test-zap-secret"
os.environ["QUICKBOOKS_SECRET"] = "test-qb-secret"
os.environ["ALPHA_SECRET"] = "test-alpha-secret"
os.environ["PRODUCTION_SECRET"] = "test-prod-secret"
os.environ["LEADS_SECRET"] = "test-leads-secret"
os.environ["CRON_SECRET"] = "test-cron-secret"
os.environ["ESIGN_SECRET"] = "test-esign-secret"

from datetime import timedelta  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)

# Tokens minted with the app's own signer (no password needed). The seeded users
# are fred(super_admin) / office(manager) / fieldcrew(user); get_current_user
# resolves the effective role from the db, so these map to real role gates.
def _tok(email):
    return main.create_access_token({"sub": email, "role": "x"}, timedelta(minutes=60))

SUPER = {"Authorization": f"Bearer {_tok('fred@trulineroofing.com')}"}
MANAGER = {"Authorization": f"Bearer {_tok('office@trulineroofing.com')}"}
USER = {"Authorization": f"Bearer {_tok('fieldcrew@trulineroofing.com')}"}

_failures = []
def check(cond, msg):
    if not cond:
        _failures.append(msg)
    label = "ok  " if cond else "FAIL"
    print(f"  [{label}] {msg}")


def run():
    print("-- T2: /admin/webhook-info does not leak the secret --")
    r = client.get("/admin/webhook-info", headers=SUPER)
    check(r.status_code == 200, f"webhook-info as super_admin -> 200 (got {r.status_code})")
    body_text = r.text
    check("test-zap-secret" not in body_text,
          "webhook-info response must NOT contain the live ZAPIER_SECRET value")
    j = r.json()
    check("secret" not in j, "webhook-info must not expose a raw 'secret' field")
    check(j.get("secret_configured") is True, "webhook-info reports secret_configured=true")
    check(j.get("secret_hint") == "****cret",
          f"webhook-info hint is masked, suffix only (got {j.get('secret_hint')!r})")
    check(client.get("/admin/webhook-info", headers=USER).status_code == 403,
          "webhook-info is forbidden (403) for a non-super-admin user")

    print("-- doors: bad secret -> 403 --")
    bad = "definitely-wrong"
    door_bad = {
        "/zapier/webhook": {"secret": bad, "job_id": "x"},
        "/quickbooks/webhook": {"secret": bad, "transaction_type": "invoice",
                                "transaction_id": "t1", "amount": 100.0, "date": "2026-06-18"},
        "/alpha/webhook": {"secret": bad, "job_id": "AE-x"},
        "/production/webhook": {"secret": bad, "job_id": "AE-x", "date": "2026-06-18"},
        "/leads/webhook": {"secret": bad, "client_name": "X"},
        "/esign/webhook": {"secret": bad, "status": "signed"},
    }
    for path, payload in door_bad.items():
        sc = client.post(path, json=payload).status_code
        check(sc == 403, f"{path} bad secret -> 403 (got {sc})")

    print("-- doors: valid secret -> write (non-403) --")
    r = client.post("/alpha/webhook", json={
        "secret": "test-alpha-secret", "job_id": "AE-test-1",
        "client_name": "Acme Warehouse", "contract_value": 50000.0,
        "coating_system": "silicone", "substrate": "tpo"})
    check(r.status_code == 200, f"/alpha/webhook valid -> 200 (got {r.status_code})")
    # the write landed and is readable back (manager sees the imported budget)
    jr = client.get("/job/AE-test-1", headers=MANAGER)
    check(jr.status_code == 200 and isinstance(jr.json().get("budget"), dict),
          "alpha import created job AE-test-1 with a budget block")

    r = client.post("/production/webhook", json={
        "secret": "test-prod-secret", "job_id": "AE-test-1", "date": "2026-06-18",
        "crew": "Blue", "sqft_coated": 2000.0})
    check(r.status_code == 200, f"/production/webhook valid (existing job) -> 200 (got {r.status_code})")

    r = client.post("/leads/webhook", json={
        "secret": "test-leads-secret", "client_name": "New Lead Co", "address": "9 Dock Rd"})
    check(r.status_code == 200 and r.json().get("opportunity_id"),
          f"/leads/webhook valid -> 200 + opportunity_id (got {r.status_code})")

    r = client.post("/zapier/webhook", json={
        "secret": "test-zap-secret", "job_id": "ZAP-1", "client_name": "Zap Co"})
    check(r.status_code == 200, f"/zapier/webhook valid -> 200 (got {r.status_code})")

    print("-- role gating on financials --")
    check(client.get("/job/AE-test-1/financials", headers=USER).status_code == 403,
          "field-crew (user) is denied /job/{id}/financials (403)")
    check(client.get("/job/AE-test-1/financials", headers=MANAGER).status_code == 200,
          "manager can read /job/{id}/financials (200)")

    print("-- T4: cron secret via header + query fallback, bad -> 403 --")
    check(client.post("/cron/tick", headers={"X-Cron-Secret": "test-cron-secret"}).status_code == 200,
          "/cron/tick with X-Cron-Secret header -> 200")
    check(client.post("/cron/tick?secret=test-cron-secret").status_code == 200,
          "/cron/tick with ?secret= query fallback -> 200")
    check(client.post("/cron/tick", headers={"X-Cron-Secret": "nope"}).status_code == 403,
          "/cron/tick with wrong header -> 403")
    check(client.post("/cron/tick").status_code == 403,
          "/cron/tick with no secret -> 403")

    print("-- T3: login rate limit (429 after 5 failures) --  [run last: blocks this IP]")
    codes = [client.post("/login", json={"email": "fred@trulineroofing.com",
                                          "password": "wrong"}).status_code
             for _ in range(5)]
    check(all(c == 401 for c in codes), f"first 5 wrong logins -> 401 (got {codes})")
    sixth = client.post("/login", json={"email": "fred@trulineroofing.com",
                                        "password": "wrong"}).status_code
    check(sixth == 429, f"6th wrong login -> 429 (got {sixth})")

    print("-- T7/T8: write-lock present + normalize backfills outbox --")
    check(hasattr(main, "_DB_WRITE_LOCK"), "save_db has a module-level write lock (_DB_WRITE_LOCK)")
    d = {"users": {}}
    changed = main._normalize_db(d)
    check(changed is True, "_normalize_db reports a change for an old db")
    check(d.get("outbox") == [] and d.get("sms_outbox") == [],
          "_normalize_db backfills outbox + sms_outbox as lists")

    print()
    if _failures:
        print(f"SECURITY/DOOR TESTS: FAILED ({len(_failures)} check(s))")
        for f in _failures:
            print("  - " + f)
        return 1
    print("SECURITY/DOOR TESTS: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(run())
