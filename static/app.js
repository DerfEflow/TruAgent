let token = localStorage.getItem('token');
let userRole = localStorage.getItem('user_role') || 'user';

function isSuperAdmin() {
  return userRole === 'super_admin';
}

function isManagerOrAbove() {
  return userRole === 'super_admin' || userRole === 'manager';
}

function isUser() {
  return userRole === 'user';
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/service-worker.js')
    .then(() => console.log('Service Worker registered'))
    .catch(err => console.log('Service Worker registration failed:', err));
}

window.addEventListener('DOMContentLoaded', () => {
  if (token) {
    showDashboard();
  } else {
    showLogin();
  }
});

function showLogin() {
  document.getElementById('login-screen').classList.remove('hidden');
  document.getElementById('dashboard-screen').classList.add('hidden');
}

function showDashboard() {
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('dashboard-screen').classList.remove('hidden');
  
  const userEmail = localStorage.getItem('user_email') || 'User';
  document.getElementById('user-email').textContent = userEmail;
  
  const roleDisplay = document.getElementById('user-role-display');
  if (roleDisplay) {
    const roleNames = {
      'super_admin': 'Super Admin',
      'manager': 'Manager',
      'user': 'Field Crew/Sales'
    };
    roleDisplay.textContent = roleNames[userRole] || 'User';
  }
  
  if (isSuperAdmin()) {
    document.querySelectorAll('.admin-only').forEach(el => el.classList.remove('hidden'));
    document.querySelectorAll('.super-admin-only').forEach(el => el.classList.remove('hidden'));
    loadWebhookInfo();
  }
  
  if (isManagerOrAbove()) {
    document.querySelectorAll('.manager-only').forEach(el => el.classList.remove('hidden'));
  }
  
  if (isUser()) {
    document.querySelectorAll('.hide-for-user').forEach(el => el.classList.add('hidden'));
  }
  
  loadChatHistory();
  refreshJobs();
  refreshDocuments();
}

async function login() {
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  const errorDiv = document.getElementById('login-error');
  
  try {
    showLoading(true);
    const response = await fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    
    if (response.ok) {
      const data = await response.json();
      localStorage.setItem('token', data.token);
      localStorage.setItem('user_role', data.role);
      localStorage.setItem('user_email', email);
      token = data.token;
      userRole = data.role;
      errorDiv.textContent = '';
      showDashboard();
    } else {
      errorDiv.textContent = 'Invalid email or password';
    }
  } catch (error) {
    errorDiv.textContent = 'Login failed. Please try again.';
  } finally {
    showLoading(false);
  }
}

function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('user_role');
  localStorage.removeItem('user_email');
  token = null;
  userRole = 'user';
  showLogin();
}

function showTab(tabName) {
  document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
  
  event.target.classList.add('active');
  document.getElementById(`${tabName}-tab`).classList.add('active');
  
  if (tabName === 'jobs') refreshJobs();
  if (tabName === 'documents') refreshDocuments();
}

function showLoading(show) {
  if (show) {
    document.getElementById('loading').classList.remove('hidden');
  } else {
    document.getElementById('loading').classList.add('hidden');
  }
}

async function loadChatHistory() {
  try {
    const response = await fetch('/chat/history', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      const data = await response.json();
      const chatMessages = document.getElementById('chat-messages');
      chatMessages.innerHTML = '';
      
      data.history.forEach(msg => {
        if (msg.role === 'user' || msg.role === 'assistant') {
          addMessageToChat(msg.content, msg.role);
        }
      });
      
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  } catch (error) {
    console.error('Failed to load chat history:', error);
  }
}

function addMessageToChat(content, role) {
  const chatMessages = document.getElementById('chat-messages');
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${role}`;
  messageDiv.textContent = content;
  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChatMessage() {
  const input = document.getElementById('chat-input');
  const message = input.value.trim();
  
  if (!message) return;
  
  addMessageToChat(message, 'user');
  input.value = '';
  
  try {
    showLoading(true);
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ message })
    });
    
    if (response.ok) {
      const data = await response.json();
      addMessageToChat(data.response, 'assistant');
    } else {
      addMessageToChat('Sorry, I encountered an error. Please try again.', 'assistant');
    }
  } catch (error) {
    addMessageToChat('Sorry, I encountered an error. Please try again.', 'assistant');
  } finally {
    showLoading(false);
  }
}

function handleChatKeypress(event) {
  if (event.key === 'Enter') {
    sendChatMessage();
  }
}

async function loadWebhookInfo() {
  try {
    const response = await fetch('/admin/webhook-info', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      const data = await response.json();
      const webhookUrl = `${window.location.origin}${data.webhook_url}`;
      document.getElementById('webhook-url').textContent = webhookUrl;
      document.getElementById('webhook-secret').textContent = data.secret;
    }
  } catch (error) {
    console.error('Failed to load webhook info:', error);
  }
}

async function refreshJobs() {
  try {
    const response = await fetch('/jobs', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      const data = await response.json();
      const jobsList = document.getElementById('jobs-list');
      jobsList.innerHTML = '';
      
      const jobs = Object.values(data.jobs);
      
      if (jobs.length === 0) {
        jobsList.innerHTML = '<p style="color: var(--truline-gray);">No jobs found. Jobs will appear here when synced from Roofr via Zapier.</p>';
      } else {
        jobs.forEach(job => {
          const jobCard = document.createElement('div');
          jobCard.className = 'job-card';
          jobCard.innerHTML = `
            <h3>${job.client_name || 'N/A'}</h3>
            <p><strong>Job ID:</strong> ${job.job_id}</p>
            <p><strong>Address:</strong> ${job.address || 'N/A'}</p>
            <p><strong>Status:</strong> <span class="status-badge status-${job.status.toLowerCase().replace(' ', '-')}">${job.status}</span></p>
            ${job.notes && job.notes.length > 0 ? `<p><strong>Notes:</strong> ${job.notes.join(', ')}</p>` : ''}
          `;
          jobsList.appendChild(jobCard);
        });
      }
    }
  } catch (error) {
    console.error('Failed to load jobs:', error);
  }
}

async function refreshDocuments() {
  try {
    const response = await fetch('/documents', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      const data = await response.json();
      const documentsList = document.getElementById('documents-list');
      documentsList.innerHTML = '';
      
      const documents = Object.values(data.documents);
      
      if (documents.length === 0) {
        documentsList.innerHTML = '<p style="color: var(--truline-gray);">No documents uploaded yet.</p>';
      } else {
        documents.forEach(doc => {
          const docCard = document.createElement('div');
          docCard.className = 'document-card';
          docCard.innerHTML = `
            <h3>${doc.filename}</h3>
            <p>${doc.description || 'No description'}</p>
            <p><strong>Uploaded:</strong> ${new Date(doc.uploaded_at).toLocaleDateString()}</p>
            <p><strong>By:</strong> ${doc.uploaded_by}</p>
            <div class="document-actions">
              <button onclick="downloadDocument('${doc.id}')" class="btn-secondary btn-small">Download</button>
              ${isSuperAdmin() ? `<button onclick="deleteDocument('${doc.id}')" class="btn-danger btn-small">Delete</button>` : ''}
            </div>
          `;
          documentsList.appendChild(docCard);
        });
      }
    }
  } catch (error) {
    console.error('Failed to load documents:', error);
  }
}

async function uploadDocument() {
  const fileInput = document.getElementById('file-upload');
  const file = fileInput.files[0];
  
  if (!file) return;
  
  const description = prompt('Enter a description for this document (optional):');
  
  const formData = new FormData();
  formData.append('file', file);
  formData.append('description', description || '');
  
  try {
    showLoading(true);
    const response = await fetch('/documents/upload', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData
    });
    
    if (response.ok) {
      alert('Document uploaded successfully!');
      refreshDocuments();
    } else {
      alert('Failed to upload document');
    }
  } catch (error) {
    alert('Failed to upload document');
  } finally {
    showLoading(false);
    fileInput.value = '';
  }
}

async function downloadDocument(docId) {
  try {
    showLoading(true);
    const response = await fetch(`/documents/${docId}/download`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      const blob = await response.blob();
      const contentDisposition = response.headers.get('content-disposition');
      let filename = `document-${docId}`;
      
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
        if (filenameMatch) {
          filename = filenameMatch[1];
        }
      }
      
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } else {
      alert('Failed to download document');
    }
  } catch (error) {
    alert('Failed to download document');
  } finally {
    showLoading(false);
  }
}

async function deleteDocument(docId) {
  if (!confirm('Are you sure you want to delete this document? This action cannot be undone.')) {
    return;
  }
  
  try {
    showLoading(true);
    const response = await fetch(`/documents/${docId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      alert('Document deleted successfully');
      refreshDocuments();
    } else {
      alert('Failed to delete document');
    }
  } catch (error) {
    alert('Failed to delete document');
  } finally {
    showLoading(false);
  }
}

function copyWebhookUrl() {
  const webhookUrl = document.getElementById('webhook-url').textContent;
  navigator.clipboard.writeText(webhookUrl);
  alert('Webhook URL copied to clipboard!');
}

function copyWebhookSecret() {
  const webhookSecret = document.getElementById('webhook-secret').textContent;
  navigator.clipboard.writeText(webhookSecret);
  alert('Webhook secret copied to clipboard!');
}
