# Zapier Quick Setup Guide for Fred Wolfe

## Your Webhook Configuration (Copy These Exact Values)

**Webhook URL:**
```
https://workspace-fredwolfe.replit.app/zapier/webhook
```

**Webhook Secret:**
```
jSlhh7mtn2jmq2EvNgZ7-FIUJX-4loCRW-KlNArx1xE
```

---

## Step-by-Step Instructions

### Step 1: Open Your Existing Zapier Webhook
1. Log into [Zapier](https://zapier.com)
2. Go to "My Zaps"
3. Find your Roofr webhook and click "Edit"

### Step 2: Configure the Webhook Action
In your Zap's "Webhooks by Zapier" action:

1. **Action Event**: Select "POST"

2. **URL**: Paste this exactly:
   ```
   https://workspace-fredwolfe.replit.app/zapier/webhook
   ```

3. **Payload Type**: Select "JSON"

4. **Data**: Add these fields (map to your Roofr fields):

   **Field 1 - secret** (REQUIRED):
   ```
   jSlhh7mtn2jmq2EvNgZ7-FIUJX-4loCRW-KlNArx1xE
   ```
   ⚠️ This must be the EXACT value above. Copy/paste it.

   **Field 2 - job_id**:
   Select the Roofr field that contains the job ID

   **Field 3 - client_name**:
   Select the Roofr field for client/customer name

   **Field 4 - address**:
   Select the Roofr field for job address

   **Field 5 - status**:
   Select the Roofr field for job status

   **Optional - data** (for additional fields):
   You can add any other Roofr fields here as needed

### Step 3: Test the Connection
1. Click "Test & Continue" in Zapier
2. Zapier will send a test payload to your app
3. You should see "200 OK" or "Success"
4. Go to your Truline AI Agent app → Jobs tab → Refresh
5. You should see the test job appear!

### Step 4: Turn On Your Zap
1. Click "Publish" or turn the Zap ON
2. From now on, any new/updated jobs in Roofr will automatically sync to your AI Agent!

---

## Example Zapier Data Configuration

Here's exactly how your Data section should look:

```
secret: jSlhh7mtn2jmq2EvNgZ7-FIUJX-4loCRW-KlNArx1xE
job_id: {{Roofr Job ID}}
client_name: {{Roofr Client Name}}
address: {{Roofr Address}}
status: Pending
data: {
  "phone": "{{Roofr Phone}}",
  "email": "{{Roofr Email}}",
  "notes": "{{Roofr Notes}}"
}
```

The `{{Roofr ...}}` parts will be replaced by actual Roofr fields when you select them in Zapier.

---

## Troubleshooting

### Error: "Invalid webhook secret"
- Make sure you copied the secret EXACTLY: `jSlhh7mtn2jmq2EvNgZ7-FIUJX-4loCRW-KlNArx1xE`
- No spaces before or after
- Must be in a field called "secret"

### Jobs not appearing in the app
1. Log into your AI Agent as admin (fred@trulineroofing.com / truline2024)
2. Go to Jobs tab
3. Click Refresh
4. Check Zapier task history for errors

### Still having issues?
1. Check the Zapier task history for error messages
2. Make sure the Zap is turned ON
3. Verify the webhook URL is correct

---

## Quick Reference

**Login to your AI Agent:**
- URL: https://workspace-fredwolfe.replit.app
- Email: fred@trulineroofing.com
- Password: truline2024

**View synchronized jobs:**
- Login → Jobs tab → Refresh

**Ask AI about your jobs:**
- Login → AI Agent tab → Type your question

---

You're all set! Once you complete these steps, your Roofr jobs will automatically sync to your AI Agent. 🎉
