# Truline Roofing AI Agent - Complete Integration Guide

> **Hosting note:** This app runs on **Railway**. Set all secrets and webhook URLs in **Railway → the TruAgent service → Variables**. The live base URL is `https://truagent-production.up.railway.app`. For the current, confirmed Roofr field mappings see `docs/handoff.md`. For step-by-step QuickBooks setup, see `docs/CONNECT_QUICKBOOKS.md`.

## Overview

This guide covers all Zapier integrations for the Truline Roofing AI Agent platform. The system supports bi-directional data flows with Roofr CRM, QuickBooks financial data, email automation, and SMS notifications.

---

## Table of Contents

1. [Bi-Directional Roofr Sync](#1-bi-directional-roofr-sync)
2. [QuickBooks Financial Integration](#2-quickbooks-financial-integration)
3. [Email Automation](#3-email-automation)
4. [SMS Notifications](#4-sms-notifications)
5. [Environment Variables](#5-environment-variables)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Bi-Directional Roofr Sync

The Roofr integration works in BOTH directions:
- **Inbound**: Roofr → AI Agent (jobs sync TO your app)
- **Outbound**: AI Agent → Roofr (updates sync BACK to Roofr)

### 1.1 Inbound: Roofr to AI Agent (Already Configured)

**Purpose**: Automatically sync new and updated jobs from Roofr to your AI Agent.

**Webhook Endpoint**:
```
https://truagent-production.up.railway.app/zapier/webhook
```

**Secret Key**:
```
<YOUR_ZAPIER_SECRET>
```

See ZAPIER_QUICKSTART.md for detailed setup instructions.

### 1.2 Outbound: AI Agent to Roofr (NEW)

**Purpose**: When your AI agent updates job status or adds notes, those changes sync BACK to Roofr automatically.

**What Syncs Back to Roofr:**
- Job status changes
- Workflow stage transitions (Lead → Quote → Approved → In Progress → Complete)
- Notes added to jobs
- All updates include timestamp and user who made the change

**Setup Steps:**

#### Step 1: Create Roofr Update Zap
1. Log into [Zapier](https://zapier.com)
2. Click "Create Zap"
3. **Trigger**: Webhooks by Zapier → Catch Hook
4. Copy the webhook URL Zapier provides

#### Step 2: Configure Environment Variable
1. Go to Railway (railway.app) → project **valiant-generosity** → the **TruAgent** service
2. Open the **Variables** tab
3. Add a variable:
   - Key: `ROOFR_WEBHOOK_URL`
   - Value: [Paste the webhook URL from Step 1]

#### Step 3: Configure Roofr Action
1. In your Zap, add **Action**: Roofr → Update Job
2. Map the webhook data to Roofr fields:
   ```
   Job ID: {{job_id}}
   Status: {{status}}
   Workflow Stage: {{workflow_stage}}
   Notes: {{new_note}}
   Updated By: {{updated_by}}
   Updated At: {{updated_at}}
   ```

#### Step 4: Test & Activate
1. In your AI Agent, ask the AI: "Update job ABC123 status to In Progress"
2. Check Zapier task history - you should see the webhook received
3. Check Roofr - the job should be updated
4. Turn your Zap ON

**How It Works:**
- When you or the AI updates a job in the AI Agent, it automatically POSTs to your Roofr webhook
- Zapier receives the update and pushes it to Roofr
- Your Roofr CRM stays in sync with your AI Agent in real-time!

---

## 2. QuickBooks Financial Integration

**Purpose**: Automatically import invoices and expenses from QuickBooks to track job profitability.

**Webhook Endpoint**:
```
https://truagent-production.up.railway.app/quickbooks/webhook
```

**Secret Key** (Railway → TruAgent service → Variables — **already set**):
- Key: `QUICKBOOKS_SECRET`
- Value: already configured; **copy the existing value**, do not create a new one. For full step-by-step QuickBooks setup see `docs/CONNECT_QUICKBOOKS.md`.

### 2.1 Invoice Import Setup

#### Step 1: Create QuickBooks Invoice Zap
1. Log into [Zapier](https://zapier.com)
2. Click "Create Zap"
3. **Trigger**: QuickBooks → New Invoice
4. Connect your QuickBooks account

#### Step 2: Configure Webhook Action
1. Add **Action**: Webhooks by Zapier → POST
2. Configure:
   ```
   URL: https://truagent-production.up.railway.app/quickbooks/webhook
   Payload Type: JSON
   Data:
     secret: [Your QUICKBOOKS_SECRET]
     transaction_type: invoice
     transaction_id: {{Invoice ID}}
     job_id: {{Job Number}}
     amount: {{Total Amount}}
     date: {{Invoice Date}}
     customer_name: {{Customer Name}}
     status: {{Status}}
   ```

#### Step 3: Test & Activate
1. Create a test invoice in QuickBooks
2. Check Zapier task history
3. In AI Agent, check Admin tab → View job financials
4. Turn Zap ON

### 2.2 Expense Import Setup

#### Step 1: Create QuickBooks Expense Zap
1. Log into [Zapier](https://zapier.com)
2. Click "Create Zap"
3. **Trigger**: QuickBooks → New Expense
4. Connect your QuickBooks account

#### Step 2: Configure Webhook Action
1. Add **Action**: Webhooks by Zapier → POST
2. Configure:
   ```
   URL: https://truagent-production.up.railway.app/quickbooks/webhook
   Payload Type: JSON
   Data:
     secret: [Your QUICKBOOKS_SECRET]
     transaction_type: expense
     transaction_id: {{Expense ID}}
     job_id: {{Job Number or Memo}}
     amount: {{Amount}}
     date: {{Expense Date}}
     vendor_name: {{Vendor Name}}
     category: {{Category}}
     description: {{Description}}
   ```

**Important**: Make sure your QuickBooks expenses include the job ID in a custom field or memo so they can be linked to jobs.

#### Step 3: Test & Activate
1. Create a test expense in QuickBooks
2. Check Zapier task history
3. Turn Zap ON

### 2.3 Viewing Job Profitability

Once configured, managers and admins can:
- View financials for any job: `GET /job/{job_id}/financials`
- See total revenue (from invoices)
- See total costs (from expenses)
- View profit: revenue - costs
- See profit margin: (profit / revenue) × 100%

**Example API Response:**
```json
{
  "job_id": "ABC123",
  "client_name": "Acme Corp",
  "invoices": [...],
  "expenses": [...],
  "summary": {
    "total_revenue": 50000.00,
    "total_costs": 32000.00,
    "profit": 18000.00,
    "margin_percent": 36.00
  }
}
```

---

## 3. Email Automation

**Purpose**: Send emails to customers, vendors, or crew with document attachments via Gmail, SendGrid, or any email service.

**Webhook Endpoint**:
```
https://truagent-production.up.railway.app/send-email
```

### 3.1 Gmail Email Setup

#### Step 1: Create Email Webhook Zap
1. Log into [Zapier](https://zapier.com)
2. Click "Create Zap"
3. **Trigger**: Webhooks by Zapier → Catch Hook
4. Copy the webhook URL

#### Step 2: Configure Environment Variable
1. Go to Railway (railway.app) → project **valiant-generosity** → the **TruAgent** service
2. Open the **Variables** tab
3. Add a variable:
   - Key: `EMAIL_WEBHOOK_URL`
   - Value: [Paste webhook URL from Step 1]

#### Step 3: Configure Gmail Action
1. In your Zap, add **Action**: Gmail → Send Email
2. Connect your Gmail account
3. Map fields:
   ```
   To: {{to}}
   Subject: {{subject}}
   Body: {{body}} or {{html}}
   Attachments: {{attachments}}
   ```

#### Step 4: Test & Activate
1. In AI Agent, ask: "Send an email to customer@example.com with subject 'Project Update' and body 'Your roofing project is on schedule'"
2. Check recipient's inbox
3. Turn Zap ON

### 3.2 Email with Document Attachments

The AI can attach documents from the document library:

**Example AI Command:**
```
"Send an email to john@example.com with subject 'Your Estimate' 
and attach document ID 5 from our library"
```

The system will:
1. Retrieve document #5
2. Convert to base64
3. Include in email payload
4. Send via Zapier to Gmail/SendGrid

**Supported Attachment Format:**
```json
{
  "attachments": [
    {
      "filename": "estimate.pdf",
      "content": "base64_encoded_content...",
      "contentType": "application/pdf"
    }
  ]
}
```

---

## 4. SMS Notifications

**Purpose**: Send SMS text messages to crew, customers, or vendors for urgent notifications via Twilio.

**Webhook Endpoint**:
```
https://truagent-production.up.railway.app/send-sms
```

### 4.1 Twilio SMS Setup

#### Step 1: Create SMS Webhook Zap
1. Log into [Zapier](https://zapier.com)
2. Click "Create Zap"
3. **Trigger**: Webhooks by Zapier → Catch Hook
4. Copy the webhook URL

#### Step 2: Configure Environment Variable
1. Go to Railway (railway.app) → project **valiant-generosity** → the **TruAgent** service
2. Open the **Variables** tab
3. Add a variable:
   - Key: `SMS_WEBHOOK_URL`
   - Value: [Paste webhook URL from Step 1]

#### Step 3: Configure Twilio Action
1. In your Zap, add **Action**: Twilio → Send SMS
2. Connect your Twilio account
3. Map fields:
   ```
   To: {{to}}
   Message: {{message}}
   From: [Your Twilio Phone Number]
   ```

#### Step 4: Test & Activate
1. In AI Agent, ask: "Send SMS to +1234567890: Job ABC123 is complete"
2. Check recipient's phone
3. Turn Zap ON

### 4.2 AI SMS Commands

**Example Commands:**
- "Text the customer at +1234567890 that we'll arrive at 9am tomorrow"
- "Send SMS to crew: Job at 123 Main St is ready for final inspection"
- "Text +1555555555: Your estimate is ready for review"

---

## 5. Environment Variables

Configure these in **Railway → TruAgent service → Variables**:

| Variable | Purpose | Example Value |
|----------|---------|---------------|
| `ZAPIER_SECRET` | Authenticate incoming Roofr webhooks | `<YOUR_ZAPIER_SECRET>` |
| `ROOFR_WEBHOOK_URL` | Send job updates back to Roofr | `https://hooks.zapier.com/hooks/catch/...` |
| `QUICKBOOKS_SECRET` | Authenticate incoming QB webhooks | `create_strong_secret_123` |
| `EMAIL_WEBHOOK_URL` | Trigger email sending via Zapier | `https://hooks.zapier.com/hooks/catch/...` |
| `SMS_WEBHOOK_URL` | Trigger SMS sending via Zapier | `https://hooks.zapier.com/hooks/catch/...` |

**Security Best Practices:**
- Use strong, random secrets (at least 32 characters)
- Never share secrets in code or commits
- Rotate secrets periodically
- Store them only in Railway Variables (never in code or commits)

---

## 6. Troubleshooting

### 6.1 Bi-Directional Roofr Sync Issues

**Problem**: AI updates not syncing to Roofr

**Solutions**:
1. Check `ROOFR_WEBHOOK_URL` is set in Railway Variables
2. Verify Zapier task history for errors
3. Ensure Roofr Zap is turned ON
4. Check AI Agent response - it will say "synced", "not configured", or "sync failed: [error]"

### 6.2 QuickBooks Integration Issues

**Problem**: Invoices/expenses not appearing

**Solutions**:
1. Verify `QUICKBOOKS_SECRET` matches in both Zapier and Railway
2. Ensure `job_id` field is mapped correctly (this links transactions to jobs)
3. Check Zapier task history for 403 errors (wrong secret) or 400 errors (invalid data)
4. Confirm QuickBooks Zaps are ON

### 6.3 Email/SMS Not Sending

**Problem**: Communications failing

**Solutions**:
1. Check webhook URLs are configured:
   - `EMAIL_WEBHOOK_URL` for email
   - `SMS_WEBHOOK_URL` for SMS
2. Verify Zapier Zaps are turned ON
3. Check Zapier task history for errors
4. Ensure Gmail/Twilio accounts are connected in Zapier
5. For Twilio SMS, verify phone numbers are in E.164 format: +1234567890

### 6.4 Document Attachments Failing

**Problem**: Emails sent but attachments missing

**Solutions**:
1. Verify document exists in AI Agent (Documents tab)
2. Check document ID is correct
3. Ensure AI is using correct document_ids parameter
4. Check Zapier payload - attachments should be base64 encoded
5. Verify Gmail/email service supports attachments in Zapier

### 6.5 General Debugging Steps

1. **Check Zapier Task History**:
   - Go to Zapier → Zap History
   - Look for failed tasks (red X)
   - Click to see error details

2. **Check AI Agent Logs**:
   - Error messages will indicate what failed
   - Look for "not configured", "sync failed", etc.

3. **Verify Webhook URLs**:
   - In browser, visit Admin tab
   - Check "View Webhook Info" shows all URLs configured

4. **Test Manually**:
   - Use Postman or curl to POST test data to webhooks
   - Verify Zapier receives the data correctly

---

## Quick Reference Card

### API Endpoints

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/zapier/webhook` | POST | Receive jobs from Roofr | Secret |
| `/roofr/update` | POST | Send job updates to Roofr | JWT |
| `/quickbooks/webhook` | POST | Receive QB financials | Secret |
| `/job/{job_id}/financials` | GET | View job profitability | JWT (Manager+) |
| `/send-email` | POST | Send email via Zapier | JWT |
| `/send-sms` | POST | Send SMS via Zapier | JWT |

### AI Agent Capabilities

The AI can automatically:
- ✅ Update job status (syncs to Roofr)
- ✅ Add notes to jobs (syncs to Roofr)
- ✅ Move jobs through workflow stages
- ✅ Send emails with document attachments
- ✅ Send SMS text messages
- ✅ Calculate job profitability
- ✅ Generate financial reports (Manager/Admin only)

### User Access Levels

| Role | Capabilities |
|------|-------------|
| **Super Admin** | Full access, delete permissions, user management, all financials |
| **Manager** | View all data + financials, no delete permissions |
| **User** | Job info, updates, communications, NO financial access |

---

## Need Help?

**Login Credentials:**
The demo passwords were rotated on 2026-06-14. The current strong passwords live in
the private, git-ignored file `ROTATED-LOGINS-2026-06-14.txt` (ask Fred). Accounts:
- Super Admin: fred@trulineroofing.com
- Manager: office@trulineroofing.com
- Field Crew: fieldcrew@trulineroofing.com

**Support Resources:**
1. Check this guide first
2. Review Zapier task history for errors
3. Check AI Agent error messages (they're descriptive!)
4. Test with small data first before going live

---

**You're all set!** 🎉

Your Truline AI Agent is now a complete business intelligence platform with:
- ✅ Bi-directional Roofr CRM sync
- ✅ QuickBooks financial tracking
- ✅ Job profitability analytics
- ✅ Email automation with attachments
- ✅ SMS notifications
- ✅ Role-based access control
- ✅ AI-powered assistance

All data flows automatically - just ask your AI agent and it handles the rest!
