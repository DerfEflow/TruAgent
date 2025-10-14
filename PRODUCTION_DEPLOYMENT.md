# Production Deployment Guide

## Pre-Deployment Checklist

### Required Environment Variables

Before deploying to production, you **MUST** set the following environment variables:

#### 1. OPENAI_API_KEY ✅ (Already Set)
Your OpenAI API key for the AI agent functionality.

#### 2. SESSION_SECRET ⚠️ (CRITICAL - Must Set)
A secure random string used to sign JWT tokens.

**To generate a secure secret:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Setting in Replit:**
1. Go to the "Secrets" tab (🔒 icon in left sidebar)
2. Add a new secret with key: `SESSION_SECRET`
3. Paste your generated secure string as the value
4. Click "Add Secret"

⚠️ **WARNING**: If not set, the app will auto-generate a secret that changes on every restart, invalidating all user sessions!

#### 3. ZAPIER_SECRET ⚠️ (CRITICAL - Must Set)
A secure secret key for authenticating Zapier webhook requests.

**To generate a secure secret:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Setting in Replit:**
1. Go to the "Secrets" tab (🔒 icon in left sidebar)
2. Add a new secret with key: `ZAPIER_SECRET`
3. Paste your generated secure string as the value
4. Click "Add Secret"

⚠️ **WARNING**: The default value "change_this_secret_in_production" is NOT secure for production use!

### Security Recommendations

1. **Strong Secrets**: Use cryptographically secure random strings (at least 32 characters)
2. **Never Commit Secrets**: Environment variables are stored securely and not committed to code
3. **Rotate Regularly**: Consider rotating SESSION_SECRET and ZAPIER_SECRET periodically
4. **Update Zapier**: After setting ZAPIER_SECRET, update your Zapier webhook configuration with the new secret

### Deployment Steps

1. **Set Environment Variables** (see above)
2. **Test Locally**: Verify the app works with all features before deploying
3. **Deploy to Production**: Use Replit's deployment feature
4. **Update Zapier**: Configure your Zapier webhook with the production URL and secret
5. **Test End-to-End**: Verify authentication, document management, and Zapier integration

### Post-Deployment Verification

- [ ] Admin login works (fred@trulineroofing.com)
- [ ] JWT tokens are being generated correctly
- [ ] Document upload/download/delete functions properly
- [ ] Zapier webhook receives and processes data
- [ ] AI agent chat is functional
- [ ] PWA is installable on mobile/desktop
- [ ] Service worker caches assets for offline use

### Monitoring

1. Check application logs regularly
2. Monitor Zapier task history for errors
3. Verify user sessions persist across app restarts
4. Test webhook authentication is working

### Troubleshooting

#### Sessions expire immediately
- Verify SESSION_SECRET is set and doesn't change
- Check that JWT tokens are being signed correctly

#### Zapier webhooks fail
- Verify ZAPIER_SECRET matches in both app and Zapier
- Check webhook payload includes "secret" field
- Review Zapier task history for error details

#### Documents won't download
- Verify JWT authentication is working
- Check browser console for errors
- Ensure file permissions are correct

### Backup and Recovery

The app stores data in `db.json` which includes:
- User accounts
- Jobs from Roofr
- Document metadata
- Chat history

**Backup Strategy:**
1. Regularly download `db.json` for backup
2. Store backups securely
3. Document restoration procedure

### Production URLs

Once deployed, your app will be accessible at:
- Main app: `https://[your-repl-name].[your-username].repl.co`
- Zapier webhook: `https://[your-repl-name].[your-username].repl.co/zapier/webhook`

### Support

For issues:
- **Authentication/Security**: Review this deployment guide
- **Zapier Integration**: Check ZAPIER_SETUP.md
- **General Issues**: Contact Fred Wolfe (admin)
