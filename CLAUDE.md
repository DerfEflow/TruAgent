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

Demo logins (do not change during the build):
- Super Admin: fred@trulineroofing.com / truline2024
- Manager: office@trulineroofing.com / office123
- User: fieldcrew@trulineroofing.com / roof123

@docs/architecture.md
@docs/data_model.md
@docs/env_template.md
