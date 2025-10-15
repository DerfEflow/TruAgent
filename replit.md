# Truline Roofing AI Agent PWA

## Overview
A comprehensive AI-powered business operations platform (PWA) for Truline Roofing commercial roofing company. The app provides bi-directional CRM sync, financial profitability tracking, automated communications, and AI-powered assistance for complete business intelligence.

**Company**: Truline Roofing  
**Admin**: Fred Wolfe (fred@trulineroofing.com)  
**Current Status**: Phase 2 Complete - Full Business Intelligence Platform

## Recent Changes (October 15, 2025 - Phase 2)
- **Bi-Directional Roofr CRM Integration**
  - Job updates from AI Agent automatically sync BACK to Roofr
  - Status changes, notes, and workflow transitions push to Roofr via Zapier
  - Full audit trail with user and timestamp tracking
- **QuickBooks Financial Integration**
  - Automatic import of invoices and expenses from QuickBooks via Zapier
  - Financial data linked to job records for profitability tracking
  - Support for both invoice and expense transaction types
- **Financial Profitability Engine**
  - Calculate revenue, costs, profit, and margins per job
  - Manager/Admin-only financial endpoint with comprehensive analytics
  - Real-time profitability tracking across all jobs
- **Email & SMS Communication Automation**
  - Send emails with document attachments via Zapier/Gmail
  - Send SMS text messages via Zapier/Twilio
  - AI agent can draft and send communications automatically
  - All messages tracked with sender and timestamp
- **Enhanced AI Agent Communication Capabilities**
  - AI can send emails with document attachments from library
  - AI can send SMS for urgent notifications
  - Updated system prompts for all roles with communication features
  - Proper error handling and status reporting

## Phase 1 Changes (October 15, 2025)
- **Implemented three-tier role-based access control (RBAC)**
  - Super Admin: Full access including delete operations and user management
  - Manager: View all data including financials, no delete permissions
  - User: Field crew/sales access, no financial data visibility
- **Enhanced AI agent with role-aware filtering**
  - Blocks financial queries for User role
  - Provides full data access for Manager and Super Admin roles
- **Added comprehensive user management system**
  - Super Admin can create, list, and update user roles
  - Role-based UI visibility in frontend
  - User role badge display in dashboard header

## Previous Changes (October 14, 2025)
- Created FastAPI backend with JWT authentication and AI agent integration
- Implemented document management system with role-based access control
- Built progressive web app frontend with offline capabilities
- Added Zapier webhook integration for Roofr CRM synchronization with secret key verification
- Integrated OpenAI API for AI agent functionality
- Implemented secure JWT-based user authentication with server-side session management
- Fixed critical security issues: replaced email-based tokens with signed JWTs, added webhook secret authentication

## User Preferences
- Use personal OpenAI API key (already configured)
- Follow provided starter code architecture using FastAPI and vanilla JavaScript
- Use Zapier webhooks for Roofr CRM integration (no direct API available)
- Professional, clean dashboard design with Truline branding colors (green theme)
- Offline-capable PWA for field crew access

## Project Architecture

### Backend (FastAPI)
- **main.py**: FastAPI application with all endpoints
- **Database**: JSON file-based storage (db.json) for persistence
- **Authentication**: JWT-based authentication with signed tokens (SESSION_SECRET environment variable)
- **Admin Role**: fred@trulineroofing.com (can delete documents and manage users)
- **Security**: Webhook secret verification, Bearer token authentication, role-based access control

### Frontend (PWA)
- **static/index.html**: Single-page application structure
- **static/style.css**: Truline Roofing brand styling (green theme)
- **static/app.js**: Client-side logic for all features
- **static/manifest.json**: PWA configuration
- **static/service-worker.js**: Offline caching functionality
- **static/logo.png**: Truline Roofing emblem

### Key Features
1. **AI Agent Chat**: OpenAI-powered assistant for data manipulation, queries, and automated actions (role-aware with financial data filtering)
2. **Bi-Directional CRM Sync**: Job updates automatically sync between AI Agent and Roofr CRM in both directions
3. **Financial Intelligence**: QuickBooks integration for real-time profitability tracking (revenue, costs, profit, margins)
4. **Job Management**: View and manage jobs synced from Roofr via Zapier
5. **Document Management**: Upload, download, and delete (super admin only) company documents
6. **Communication Automation**: AI-powered email and SMS with document attachments via Zapier
7. **Progressive Web App**: Installable, offline-capable mobile/desktop app
8. **Three-Tier Role-Based Access Control**:
   - **Super Admin**: Full system access, delete permissions, user management
   - **Manager**: View all data including financials, no delete permissions
   - **User**: Field crew/sales access, no financial data visibility

### API Endpoints

**Authentication & Users**
- `POST /login`: User authentication (returns JWT token with role)
- `POST /users`: Create new user (super admin only, requires JWT)
- `GET /users`: List all users (super admin only, requires JWT)
- `PUT /users/{email}/role`: Update user role (super admin only, requires JWT)
- `DELETE /users/{email}`: Remove user access (super admin only, requires JWT)

**Job Management**
- `GET /jobs`: Get all jobs (requires JWT)
- `POST /job`: Add/update job (requires JWT)
- `GET /job/{job_id}`: Get specific job (requires JWT)
- `GET /job/{job_id}/financials`: Get job profitability data (manager/admin only, requires JWT)

**Bi-Directional CRM Sync**
- `POST /zapier/webhook`: Receive Roofr data FROM Zapier (requires secret key)
- `POST /roofr/update`: Send job updates TO Roofr via Zapier (requires JWT)

**Financial Integration**
- `POST /quickbooks/webhook`: Receive invoices/expenses from QuickBooks via Zapier (requires secret key)

**Document Management**
- `POST /documents/upload`: Upload document (requires JWT)
- `GET /documents`: List all documents (requires JWT)
- `GET /documents/{doc_id}/download`: Download document (requires JWT)
- `DELETE /documents/{doc_id}`: Delete document (super admin only, requires JWT)

**Communication**
- `POST /send-email`: Send email with optional document attachments via Zapier (requires JWT)
- `POST /send-sms`: Send SMS text message via Zapier (requires JWT)

**AI Agent**
- `POST /chat`: Send message to AI agent (role-aware, requires JWT)
- `GET /chat/history`: Get chat history (requires JWT)
- `POST /ai/action`: Execute AI actions (update jobs, send emails/SMS, etc.) (requires JWT)

**Admin**
- `GET /admin/webhook-info`: Get webhook configuration (super admin only, requires JWT)

### User Accounts
- **fred@trulineroofing.com**: Super Admin (password: truline2024) - Full access, can delete and manage users
- **office@trulineroofing.com**: Manager (password: office123) - View all data including financials, cannot delete
- **fieldcrew@trulineroofing.com**: User (password: roof123) - Field crew/sales access, no financial visibility

## Technology Stack
- **Backend**: FastAPI, Uvicorn, python-jose (JWT)
- **AI**: OpenAI API (gpt-4o-mini model)
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Database**: JSON file storage (Replit-persistent)
- **PWA**: Service Worker, Web App Manifest
- **Integration**: Zapier webhooks with secret key authentication
- **Security**: JWT tokens, Bearer authentication, role-based access control

## Environment Variables
- `OPENAI_API_KEY`: OpenAI API key for AI agent
- `SESSION_SECRET`: Secret key for JWT signing (auto-generated if not set)
- `ZAPIER_SECRET`: Secret key for webhook authentication (set in production)
- `ROOFR_WEBHOOK_URL`: Zapier webhook URL for sending job updates TO Roofr (bi-directional sync)
- `QUICKBOOKS_SECRET`: Secret key for QuickBooks webhook authentication
- `EMAIL_WEBHOOK_URL`: Zapier webhook URL for sending emails via Gmail/SendGrid
- `SMS_WEBHOOK_URL`: Zapier webhook URL for sending SMS via Twilio

## Deployment
- Server runs on port 5000 (0.0.0.0:5000)
- PWA is installable on mobile and desktop devices
- Offline caching enabled for field crew access

## Next Phase Features
- Automated job status updates via Zapier
- Advanced AI automations for report generation
- Role-based permission system expansion
- Real-time collaboration features
- Data export and backup functionality
- Google Photos integration for job-specific photo albums
