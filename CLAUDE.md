# TruAgent

Internal AI business-operations app (PWA) for Truline Roofing. Python FastAPI
backend (`main.py`), vanilla-JS front end (`static/`), JSON-file storage
(`db.json`). All external integrations (OpenAI, Zapier/Roofr, QuickBooks, email,
SMS) are optional and dormant until their env vars are set.

## Run locally (Windows)

```
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install fastapi "openai" pydantic pyjwt "python-jose[cryptography]" python-multipart requests uvicorn python-dotenv
.\.venv\Scripts\python.exe main.py
```

Then open http://localhost:5000 (set `PORT` in `.env` to use another port — local
review currently uses 5050 because Coating Log occupies 5000).

Logins (rotated 2026-06-14, sec-02): the old public demo passwords
(truline2024 / office123 / roof123) are retired. Strong replacements live in the
git-ignored `ROTATED-LOGINS-2026-06-14.txt` (not committed). Roles unchanged:
- Super Admin: fred@trulineroofing.com
- Manager: office@trulineroofing.com
- User: fieldcrew@trulineroofing.com

@docs/architecture.md
@docs/data_model.md
@docs/env_template.md
