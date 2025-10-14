# Truline Roofing AI Agent PWA

## Overview
A progressive web app (PWA) AI agent for Truline Roofing commercial roofing company. The app provides AI-powered assistance for managing jobs, documents, and CRM data integration with Roofr via Zapier webhooks.

**Company**: Truline Roofing  
**Admin**: Fred Wolfe (fred@trulineroofing.com)  
**Current Status**: Initial MVP implementation

## Recent Changes (October 14, 2025)
- Created FastAPI backend with authentication and AI agent integration
- Implemented document management system with role-based access control
- Built progressive web app frontend with offline capabilities
- Added Zapier webhook integration for Roofr CRM synchronization
- Integrated OpenAI API for AI agent functionality
- Implemented user authentication with hard-coded user list
- Added admin-only controls for document deletion and user management

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
- **Authentication**: Email/password with SHA-256 hashing
- **Admin Role**: fred@trulineroofing.com (can delete documents and manage users)

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
- `POST /login`: User authentication
- `GET /jobs`: Get all jobs
- `POST /job`: Add/update job
- `GET /job/{job_id}`: Get specific job
- `POST /zapier/webhook`: Receive Roofr data from Zapier
- `POST /documents/upload`: Upload document
- `GET /documents`: List all documents
- `GET /documents/{doc_id}/download`: Download document
- `DELETE /documents/{doc_id}`: Delete document (admin only)
- `POST /chat`: Send message to AI agent
- `GET /chat/history`: Get chat history
- `DELETE /users/{email}`: Remove user access (admin only)

### User Accounts
- **fred@trulineroofing.com**: Admin (password: truline2024)
- **fieldcrew@trulineroofing.com**: Field crew (password: roof123)
- **office@trulineroofing.com**: Office staff (password: office123)

## Technology Stack
- **Backend**: FastAPI, Uvicorn
- **AI**: OpenAI API (gpt-4o-mini model)
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Database**: JSON file storage (Replit-persistent)
- **PWA**: Service Worker, Web App Manifest
- **Integration**: Zapier webhooks

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
