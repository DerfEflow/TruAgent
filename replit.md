# Truline Roofing AI Agent PWA

## Overview
A progressive web app (PWA) AI agent for Truline Roofing commercial roofing company. The app provides AI-powered assistance for managing jobs, documents, and CRM data integration with Roofr via Zapier webhooks.

**Company**: Truline Roofing  
**Admin**: Fred Wolfe (fred@trulineroofing.com)  
**Current Status**: Initial MVP implementation

## Recent Changes (October 14, 2025)
- Created FastAPI backend with JWT authentication and AI agent integration
- Implemented document management system with role-based access control
- Built progressive web app frontend with offline capabilities
- Added Zapier webhook integration for Roofr CRM synchronization with secret key verification
- Integrated OpenAI API for AI agent functionality
- Implemented secure JWT-based user authentication with server-side session management
- Added admin-only controls for document deletion and user management
- Fixed critical security issues: replaced email-based tokens with signed JWTs, added webhook secret authentication, and implemented proper role-based access control

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
1. **AI Agent Chat**: OpenAI-powered assistant for data manipulation and queries
2. **Job Management**: View and manage jobs synced from Roofr via Zapier
3. **Document Management**: Upload, download, and delete (admin only) company documents
4. **Zapier Integration**: Webhook endpoint for receiving Roofr CRM data
5. **Progressive Web App**: Installable, offline-capable mobile/desktop app
6. **Role-Based Access**: Admin controls for Fred Wolfe only

### API Endpoints
- `POST /login`: User authentication (returns JWT token)
- `GET /jobs`: Get all jobs (requires JWT)
- `POST /job`: Add/update job (requires JWT)
- `GET /job/{job_id}`: Get specific job (requires JWT)
- `POST /zapier/webhook`: Receive Roofr data from Zapier (requires secret key)
- `POST /documents/upload`: Upload document (requires JWT)
- `GET /documents`: List all documents (requires JWT)
- `GET /documents/{doc_id}/download`: Download document (requires JWT)
- `DELETE /documents/{doc_id}`: Delete document (admin only, requires JWT)
- `POST /chat`: Send message to AI agent (requires JWT)
- `GET /chat/history`: Get chat history (requires JWT)
- `POST /ai/action`: Execute AI actions on data (requires JWT)
- `DELETE /users/{email}`: Remove user access (admin only, requires JWT)
- `GET /admin/webhook-info`: Get webhook configuration (admin only, requires JWT)

### User Accounts
- **fred@trulineroofing.com**: Admin (password: truline2024)
- **fieldcrew@trulineroofing.com**: Field crew (password: roof123)
- **office@trulineroofing.com**: Office staff (password: office123)

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
