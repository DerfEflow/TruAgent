# Truline Roofing AI Agent PWA

A progressive web app AI agent for Truline Roofing commercial roofing company. This app provides AI-powered assistance for managing jobs, documents, and CRM data integration with Roofr via Zapier webhooks.

## 🚀 Features

### AI-Powered Assistant
- Chat with an AI agent that understands your jobs and documents
- Get summaries, reports, and insights about your roofing projects
- Ask questions about job status, client information, and more

### Roofr CRM Integration
- Automatic synchronization with Roofr via Zapier webhooks
- Real-time job updates from your CRM
- Secure webhook authentication with secret keys

### Document Management
- Upload company documents (contracts, photos, reports)
- Download documents on any device
- Admin-only document deletion for security

### Progressive Web App
- Install on mobile and desktop devices
- Works offline with service worker caching
- Professional Truline Roofing branding

### Role-Based Access Control
- Admin controls for Fred Wolfe (document deletion, user management)
- Field crew and office staff access levels
- Secure JWT-based authentication

## 📱 Getting Started

### User Accounts

**Admin Account:**
- Email: `fred@trulineroofing.com`
- Password: `truline2024`
- Can delete documents and manage users

**Field Crew:**
- Email: `fieldcrew@trulineroofing.com`
- Password: `roof123`

**Office Staff:**
- Email: `office@trulineroofing.com`
- Password: `office123`

### Installing the PWA

1. Open the app in your browser
2. Look for the "Install" button in your browser's address bar
3. Click "Install" to add to your home screen
4. Access the app offline anytime

## 🔧 Setup & Configuration

### For Administrators

1. **Zapier Integration**: See [ZAPIER_SETUP.md](ZAPIER_SETUP.md) for detailed instructions
2. **Production Deployment**: See [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) for security setup

### Environment Variables

Required for production deployment:
- `OPENAI_API_KEY` - Your OpenAI API key (already configured)
- `SESSION_SECRET` - JWT signing secret (must set before deployment!)
- `ZAPIER_SECRET` - Webhook authentication secret (must set before deployment!)

## 📖 How to Use

### AI Agent Chat
1. Log in to your account
2. Navigate to the "AI Agent" tab
3. Ask questions like:
   - "Show me all pending jobs"
   - "What's the status of job R-12345?"
   - "Give me a summary of this week's projects"

### Managing Jobs
1. Go to the "Jobs" tab
2. View all jobs synced from Roofr
3. Jobs update automatically via Zapier webhooks

### Document Management
1. Navigate to the "Documents" tab
2. Click "Upload Document" to add files
3. Download documents by clicking "Download"
4. Admin can delete documents when needed

### Admin Controls (Fred Wolfe Only)
1. Go to the "Admin" tab
2. View webhook configuration
3. Copy webhook URL and secret for Zapier setup
4. Manage user access as needed

## 🔒 Security Features

- **JWT Authentication**: Secure token-based user sessions
- **Bearer Token Authorization**: All API endpoints protected
- **Webhook Secret Verification**: Zapier requests authenticated
- **Admin-Only Actions**: Sensitive operations restricted to admin
- **Password Hashing**: User passwords securely hashed with SHA-256

## 📂 Project Structure

```
.
├── main.py                    # FastAPI backend application
├── static/
│   ├── index.html            # Main application UI
│   ├── app.js                # Frontend JavaScript logic
│   ├── style.css             # Truline Roofing styling
│   ├── manifest.json         # PWA configuration
│   ├── service-worker.js     # Offline caching
│   └── logo.png              # Truline emblem
├── documents/                 # Uploaded documents storage
├── db.json                    # Application database (auto-created)
├── ZAPIER_SETUP.md           # Zapier integration guide
├── PRODUCTION_DEPLOYMENT.md  # Deployment instructions
└── README.md                 # This file
```

## 🛠 Technology Stack

- **Backend**: FastAPI, Uvicorn, python-jose (JWT)
- **AI**: OpenAI API (gpt-4o-mini model)
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Database**: JSON file storage (persistent)
- **PWA**: Service Worker, Web App Manifest
- **Integration**: Zapier webhooks
- **Security**: JWT tokens, Bearer authentication

## 📋 API Endpoints

All endpoints require JWT authentication (except login):

- `POST /login` - User authentication
- `GET /jobs` - Get all jobs
- `POST /job` - Add/update job
- `GET /job/{job_id}` - Get specific job
- `POST /zapier/webhook` - Receive Roofr data (requires secret)
- `POST /documents/upload` - Upload document
- `GET /documents` - List all documents
- `GET /documents/{doc_id}/download` - Download document
- `DELETE /documents/{doc_id}` - Delete document (admin only)
- `POST /chat` - Send message to AI agent
- `GET /chat/history` - Get chat history
- `POST /ai/action` - Execute AI actions
- `DELETE /users/{email}` - Remove user (admin only)
- `GET /admin/webhook-info` - Get webhook config (admin only)

## 🚢 Deployment

### Before Deploying

1. Set `SESSION_SECRET` environment variable (see PRODUCTION_DEPLOYMENT.md)
2. Set `ZAPIER_SECRET` environment variable (see PRODUCTION_DEPLOYMENT.md)
3. Verify OpenAI API key is configured

### Deploy to Production

1. Click the "Publish" button in Replit
2. Configure your custom domain (optional)
3. Update Zapier with production webhook URL
4. Test all features end-to-end

## 📱 PWA Installation

The app can be installed on:
- iOS devices (Safari)
- Android devices (Chrome)
- Desktop (Chrome, Edge, Safari)

Benefits:
- Offline access to cached data
- Native app experience
- Home screen icon
- Faster loading times

## 🆘 Troubleshooting

### Can't log in
- Verify email and password are correct
- Check that SESSION_SECRET is set in production

### Jobs not appearing
- Verify Zapier webhook is configured correctly
- Check that ZAPIER_SECRET matches
- Review Zapier task history for errors

### Documents won't download
- Ensure you're logged in
- Check browser console for errors
- Verify JWT token is valid

### AI agent not responding
- Verify OPENAI_API_KEY is set
- Check application logs for errors
- Ensure sufficient OpenAI credits

## 📞 Support

For technical issues or questions:
- **Admin**: Fred Wolfe (fred@trulineroofing.com)
- **Zapier Setup**: See ZAPIER_SETUP.md
- **Deployment**: See PRODUCTION_DEPLOYMENT.md

## 🔄 Next Phase Features

Planned enhancements:
- Automated job status updates via Zapier
- Advanced AI automations for report generation
- Expanded role-based permission system
- Real-time collaboration features
- Data export and backup functionality
- Integration with additional CRM systems

---

**Built for Truline Roofing** 🏗️
Professional commercial roofing solutions powered by AI
