# Zapier Integration Setup Guide

This guide explains how to integrate your Truline Roofing AI Agent with Roofr CRM using Zapier.

## Overview
Since Roofr doesn't have a public API, we use Zapier's webhook feature to send data from Roofr to your Truline AI Agent app.

## Prerequisites
1. Zapier account (free or paid)
2. Access to Roofr CRM
3. Admin access to Truline Roofing AI Agent (fred@trulineroofing.com)

## Step-by-Step Setup

### 1. Get Your Webhook Configuration
1. Log into the Truline AI Agent as admin (fred@trulineroofing.com)
2. Go to the **Admin** tab
3. Copy both:
   - **Webhook URL** (e.g., `https://your-app.repl.co/zapier/webhook`)
   - **Secret Key** (for security verification)

### 2. Create a Zap in Zapier

#### Trigger (Roofr)
1. In Zapier, create a new Zap
2. Select **Roofr** as the trigger app
3. Choose a trigger event (e.g., "New Job", "Updated Job", "New Lead")
4. Connect your Roofr account
5. Configure the trigger settings
6. Test the trigger to ensure it's working

#### Action (Webhooks by Zapier)
1. Click **Add Action**
2. Search for and select **Webhooks by Zapier**
3. Choose **POST** as the action event
4. Configure the webhook:

   **URL**: Paste your webhook URL from step 1
   
   **Payload Type**: `JSON`
   
   **Data** (map your Roofr fields):
   ```json
   {
     "secret": "YOUR_SECRET_KEY_FROM_STEP_1",
     "job_id": "{{roofr_job_id}}",
     "client_name": "{{roofr_client_name}}",
     "address": "{{roofr_address}}",
     "status": "{{roofr_status}}",
     "data": {
       "phone": "{{roofr_phone}}",
       "email": "{{roofr_email}}",
       "notes": "{{roofr_notes}}"
     }
   }
   ```

   **Important**: Always include the `secret` field with your secret key for security.

5. Test the action to ensure data is being sent correctly

### 3. Verify the Integration
1. In the Truline AI Agent, go to the **Jobs** tab
2. Trigger a test event in Roofr (create or update a job)
3. Refresh the Jobs tab in the AI Agent
4. Verify that the job data appears correctly

## Data Mapping Examples

### Required Fields
- `secret` - Your webhook secret key (REQUIRED for security)
- `job_id` - Unique identifier for the job

### Optional Fields
- `client_name` - Client's name
- `address` - Job site address
- `status` - Job status (e.g., "Pending", "In Progress", "Completed")
- `data` - Any additional custom data as a JSON object

### Example Payloads

**Simple Job Update:**
```json
{
  "secret": "your_secret_key_here",
  "job_id": "R-12345",
  "client_name": "ABC Manufacturing",
  "address": "123 Industrial Pkwy, Dallas, TX",
  "status": "In Progress"
}
```

**Job with Additional Data:**
```json
{
  "secret": "your_secret_key_here",
  "job_id": "R-12345",
  "client_name": "ABC Manufacturing",
  "address": "123 Industrial Pkwy, Dallas, TX",
  "status": "Pending",
  "data": {
    "phone": "214-555-0123",
    "email": "contact@abcmfg.com",
    "roof_type": "Commercial TPO",
    "square_footage": "15000",
    "estimate_amount": "$45000"
  }
}
```

## Security Notes

1. **Always include the secret key** - Requests without the correct secret will be rejected
2. **Keep your secret key confidential** - Don't share it publicly or commit it to version control
3. **Use HTTPS** - The webhook URL uses HTTPS for encrypted communication
4. **Admin access required** - Only Fred Wolfe (admin) can view the webhook configuration

## Troubleshooting

### Jobs not appearing in the app
- Verify the webhook URL is correct
- Check that the secret key matches
- Ensure `job_id` is included in the payload
- Check Zapier task history for errors

### Authentication errors
- Verify the secret key is correct
- Make sure the `secret` field is included in the payload

### Data not updating
- Check that the `job_id` matches existing jobs for updates
- Verify field names match the expected format
- Review the Zapier task history for any error messages

## Advanced Usage

### Multiple Zaps
You can create multiple Zaps for different Roofr events:
- New jobs → Create job in AI Agent
- Updated jobs → Update job in AI Agent
- Job status changes → Update status in AI Agent
- New estimates → Add estimate data to jobs

### Custom Automations
Use the AI Agent's chat feature to:
- Generate reports from synced job data
- Query job statuses
- Analyze trends across all jobs
- Get summaries of pending work

## Support
For issues with:
- **Zapier setup**: Check Zapier's documentation
- **Roofr data**: Contact Roofr support
- **AI Agent functionality**: Contact Fred Wolfe
