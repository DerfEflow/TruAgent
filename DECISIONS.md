# Decisions Log — TruAgent

Plain-English record of the judgment calls made while getting TruAgent running.
Newest at the bottom. (Dated 2026-06-07.)

1. **Worked only in a fresh copy.** Copied the app from the backup folder to
   `Documents\TruAgent` and did all work there. The two backup folders were
   never touched.

2. **Used a normal Python setup instead of Replit's.** Created an isolated
   Python environment (a "venv") inside the project and installed the app's
   needed packages there, so it runs on your PC without Replit.

3. **Added a settings file (`.env`).** The app needed a place to read its
   settings from. Added the standard tool for that and a `.env` file. Also added
   a blank template (`.env.example`) that's safe to share.

4. **Fixed the start-up crash.** The app used to crash on launch if no OpenAI key
   was present. Changed it so it starts fine with the AI turned off, and the chat
   simply says "AI isn't configured yet" until a key is added.

5. **Left all paid/external services turned OFF.** OpenAI, Roofr, QuickBooks,
   email, and SMS are all dormant (their settings left blank), so you can review
   the app safely with nothing connected. Each shows a friendly "not configured"
   message instead of erroring.

6. **Generated strong local passwords for the app's internal secrets.** The
   security keys the app uses behind the scenes (for sign-in tokens and webhook
   checks) were filled with strong random values in the local `.env`.

7. **Checked for leaked secrets — none found.** Scanned the code and its full
   history for any real API keys or a committed `.env`. Clean. Nothing to rotate.

8. **Kept the three demo logins exactly as they were.** Changing them would lock
   you out during review. Replacing them with real passwords is listed as a
   pre-launch task in ROADMAP.md.

9. **Ran the app on port 5050 for review (not 5000).** Your Coating Log app is
   already using port 5000 on this PC. To avoid a conflict, TruAgent runs on
   5050 for local review. The app still defaults to 5000 anywhere else; the port
   is just an adjustable setting (`PORT` in `.env`).

10. **Made the port adjustable.** Small code change so the app can read its port
    from a setting — needed for the above, and useful for hosting later.
