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

async function apiCall(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Authorization': `Bearer ${token}` } };
  if (body !== null) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
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

function showTab(tabName, btn) {
  document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById(`${tabName}-tab`).classList.add('active');
  if (tabName === 'jobs') refreshJobs();
  if (tabName === 'documents') refreshDocuments();
  if (tabName === 'financials') refreshFinancials();
  if (tabName === 'admin') loadUsers();
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

// ─── VOICE INPUT ────────────────────────────────────────────────
let _mediaRecorder = null;
let _audioChunks = [];
let _isRecording = false;

function toggleRecording() {
  if (_isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
    _mediaRecorder = new MediaRecorder(stream, { mimeType });
    _audioChunks = [];

    _mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) _audioChunks.push(e.data);
    };

    _mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(_audioChunks, { type: mimeType });
      await transcribeAudio(blob, mimeType);
    };

    _mediaRecorder.start();
    _isRecording = true;
    const btn = document.getElementById('mic-btn');
    btn.classList.add('recording');
    btn.title = 'Tap to stop';
  } catch (err) {
    alert('Microphone access denied. Please allow microphone permission and try again.');
  }
}

function stopRecording() {
  if (_mediaRecorder && _isRecording) {
    _mediaRecorder.stop();
    _isRecording = false;
    const btn = document.getElementById('mic-btn');
    btn.classList.remove('recording');
    btn.title = 'Voice input';
  }
}

async function transcribeAudio(blob, mimeType) {
  const btn = document.getElementById('mic-btn');
  btn.disabled = true;
  btn.title = 'Transcribing…';
  try {
    const ext = mimeType.includes('webm') ? 'webm' : 'mp4';
    const formData = new FormData();
    formData.append('audio', blob, `recording.${ext}`);

    const res = await fetch('/transcribe', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData
    });

    if (!res.ok) throw new Error('Transcription failed');
    const data = await res.json();
    if (data.text) {
      const input = document.getElementById('chat-input');
      input.value = data.text;
      input.focus();
    }
  } catch (err) {
    alert('Could not transcribe audio. Please try again.');
  } finally {
    btn.disabled = false;
    btn.title = 'Voice input';
  }
}
// ────────────────────────────────────────────────────────────────

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

function formatMoney(val) {
  const num = typeof val === 'number'
    ? val
    : parseFloat(String(val).replace(/[^0-9.\-]/g, ''));
  if (isNaN(num)) return String(val);
  return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
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
        jobsList.innerHTML = '<div class="empty-state"><div class="empty-icon">&#9634;</div><p>No jobs synced yet</p><span>Jobs appear here once Roofr is connected</span></div>';
      } else {
        jobs.forEach(job => {
          const status = job.status || 'Unknown';
          const statusClass = status.toLowerCase().replace(/\s+/g, '-');
          const notesText = (job.notes || [])
            .map(n => (typeof n === 'string' ? n : (n && n.note) ? n.note : ''))
            .filter(Boolean)
            .join('; ');

          // Job name is the headline; fall back to customer name, then the id.
          const title = job.job_name || job.client_name || `Job ${job.job_id || ''}`.trim();

          // Prominent dollar value line, shown only when a value was sent.
          const valueHtml = (job.job_value !== undefined && job.job_value !== null && job.job_value !== '')
            ? `<div class="job-value">${formatMoney(job.job_value)}</div>` : '';

          // Known detail rows, each rendered only when present.
          const rows = [];
          if (job.job_name && job.client_name) rows.push(['Customer', job.client_name]);
          if (job.customer_phone) rows.push(['Phone', job.customer_phone]);
          if (job.customer_email) rows.push(['Email', job.customer_email]);
          if (job.assigned_to) rows.push(['Assigned', job.assigned_to]);
          if (job.address) rows.push(['Address', job.address]);
          if (job.job_id) rows.push(['Job ID', job.job_id]);

          // Catch-all: surface any other field Roofr sends that we don't already
          // show, so mapping a new field in Zapier just works with no code change.
          const HIDE = new Set(['job_id', 'job_name', 'client_name', 'job_value',
            'status', 'address', 'customer_phone', 'customer_email', 'assigned_to',
            'notes', 'images', 'invoices', 'expenses', 'workflow_stage']);
          Object.keys(job).forEach(k => {
            if (HIDE.has(k)) return;
            const v = job[k];
            if (v === null || v === undefined || v === '' || typeof v === 'object') return;
            const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            rows.push([label, v]);
          });

          const rowsHtml = rows
            .map(([label, val]) => `<p><strong>${label}:</strong> ${val}</p>`)
            .join('');

          // Update controls: change pipeline stage / add a note. POSTs to
          // /roofr/update, which saves locally and syncs to Roofr best-effort.
          // Operational (non-financial), so available to all roles — matches
          // what the AI agent already lets any user do.
          const jid = job.job_id;
          const STAGES = ['Lead', 'Quote', 'Approved', 'In Progress', 'Complete'];
          const currentStage = job.workflow_stage || '';
          const stageOptions = ['<option value="">Update stage…</option>']
            .concat(STAGES.map(s =>
              `<option value="${s}"${s === currentStage ? ' selected' : ''}>${s}</option>`))
            .join('');
          const actionsHtml = jid ? `
            <div class="job-actions">
              <select class="job-stage-select" onchange="updateJobStage('${jid}', this.value)">${stageOptions}</select>
              <div class="job-note-row">
                <input type="text" class="job-note-input" id="note-${jid}" placeholder="Add a note…"
                       onkeydown="if(event.key==='Enter'){addJobNote('${jid}')}">
                <button class="btn-secondary btn-small" onclick="addJobNote('${jid}')">Save Note</button>
              </div>
              <div class="sync-status" id="sync-${jid}"></div>
            </div>` : '';

          const jobCard = document.createElement('div');
          jobCard.className = 'job-card';
          jobCard.innerHTML = `
            <h3>${title}</h3>
            ${valueHtml}
            ${rowsHtml}
            <p><strong>Status:</strong> <span class="status-badge status-${statusClass}">${status}</span></p>
            ${notesText ? `<p><strong>Notes:</strong> ${notesText}</p>` : ''}
            ${actionsHtml}
          `;
          jobsList.appendChild(jobCard);
        });
      }
    }
  } catch (error) {
    console.error('Failed to load jobs:', error);
  }
}

// ─── JOB UPDATE CONTROLS ───────────────────────────────────────
async function postJobUpdate(jobId, payload) {
  const syncEl = document.getElementById(`sync-${jobId}`);
  if (syncEl) { syncEl.textContent = 'Saving…'; syncEl.className = 'sync-status pending'; }
  try {
    const res = await fetch('/roofr/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(Object.assign({ job_id: jobId }, payload))
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      const sync = data.roofr_sync || 'saved';
      const msg = sync === 'synced' ? '✓ Saved & synced to Roofr'
        : sync === 'not configured' ? '✓ Saved (Roofr sync not set up yet)'
        : `✓ Saved locally — Roofr ${sync}`;
      if (syncEl) { syncEl.textContent = msg; syncEl.className = 'sync-status ok'; }
      // Show the confirmation briefly, then re-render so the badge/notes update.
      setTimeout(refreshJobs, 1500);
    } else if (syncEl) {
      syncEl.textContent = (data && data.detail) ? data.detail : 'Update failed';
      syncEl.className = 'sync-status err';
    }
  } catch (e) {
    if (syncEl) { syncEl.textContent = 'Update failed'; syncEl.className = 'sync-status err'; }
  }
}

function updateJobStage(jobId, stage) {
  if (!stage) return;
  // For a coating job the pipeline stage is effectively the status, so set both.
  postJobUpdate(jobId, { workflow_stage: stage, status: stage });
}

async function addJobNote(jobId) {
  const input = document.getElementById(`note-${jobId}`);
  const note = input ? input.value.trim() : '';
  if (!note) return;
  if (input) input.value = '';
  await postJobUpdate(jobId, { notes: note });
}
// ────────────────────────────────────────────────────────────────

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
        documentsList.innerHTML = '<div class="empty-state"><div class="empty-icon">&#9634;</div><p>No documents uploaded</p><span>Upload estimates, specs, contracts, or any job files</span></div>';
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

function showAddUserModal() {
  document.getElementById('add-user-modal').classList.remove('hidden');
}

function closeAddUserModal() {
  document.getElementById('add-user-modal').classList.add('hidden');
  document.getElementById('new-user-email').value = '';
  document.getElementById('new-user-password').value = '';
  document.getElementById('new-user-role').value = '';
}

async function createUser() {
  const email = document.getElementById('new-user-email').value;
  const password = document.getElementById('new-user-password').value;
  const role = document.getElementById('new-user-role').value;
  
  try {
    showLoading(true);
    const response = await fetch('/users', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ email, password, role })
    });
    
    if (response.ok) {
      alert('User created successfully!');
      closeAddUserModal();
      loadUsers();
    } else {
      const data = await response.json();
      alert(`Failed to create user: ${data.detail || 'Unknown error'}`);
    }
  } catch (error) {
    alert('Failed to create user');
  } finally {
    showLoading(false);
  }
}

async function loadUsers() {
  if (!isSuperAdmin()) return;
  
  try {
    const response = await fetch('/users', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      const data = await response.json();
      const usersList = document.getElementById('users-list');
      usersList.innerHTML = '';
      
      const currentEmail = localStorage.getItem('user_email');
      
      data.users.forEach(user => {
        const userCard = document.createElement('div');
        userCard.className = 'user-card';
        
        const roleNames = {
          'super_admin': 'Super Admin',
          'manager': 'Manager',
          'user': 'User'
        };
        
        const isSelf = user.email === currentEmail;
        
        userCard.innerHTML = `
          <div class="user-info-card">
            <strong>${user.email}</strong>
            <span class="role-badge">${roleNames[user.role]}</span>
            ${isSelf ? '<small style="color: var(--truline-gray);"> (You)</small>' : ''}
          </div>
          <div class="user-actions">
            ${!isSelf ? `
              <select onchange="updateUserRole('${user.email}', this.value)" class="btn-small">
                <option value="">Change Role</option>
                <option value="super_admin">Super Admin</option>
                <option value="manager">Manager</option>
                <option value="user">User</option>
              </select>
              <button onclick="deleteUser('${user.email}')" class="btn-danger btn-small">Delete</button>
            ` : '<span style="color: var(--truline-gray); font-size: 13px;">Cannot modify your own account</span>'}
          </div>
        `;
        usersList.appendChild(userCard);
      });
    }
  } catch (error) {
    console.error('Failed to load users:', error);
  }
}

async function updateUserRole(email, newRole) {
  if (!newRole) return;
  
  if (!confirm(`Are you sure you want to change ${email}'s role to ${newRole}?`)) {
    return;
  }
  
  try {
    showLoading(true);
    const response = await fetch(`/users/${encodeURIComponent(email)}/role`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ role: newRole })
    });
    
    if (response.ok) {
      alert('User role updated successfully!');
      loadUsers();
    } else {
      const data = await response.json();
      alert(`Failed to update role: ${data.detail || 'Unknown error'}`);
    }
  } catch (error) {
    alert('Failed to update user role');
  } finally {
    showLoading(false);
  }
}

async function deleteUser(email) {
  const currentEmail = localStorage.getItem('user_email');
  
  if (email === currentEmail) {
    alert('You cannot delete your own account');
    return;
  }
  
  if (!confirm(`Are you sure you want to delete ${email}? This action cannot be undone.`)) {
    return;
  }
  
  try {
    showLoading(true);
    const response = await fetch(`/users/${encodeURIComponent(email)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      alert('User deleted successfully');
      loadUsers();
    } else {
      const data = await response.json();
      alert(`Failed to delete user: ${data.detail || 'Unknown error'}`);
    }
  } catch (error) {
    alert('Failed to delete user');
  } finally {
    showLoading(false);
  }
}

async function refreshFinancials() {
  if (!isManagerOrAbove()) return;
  
  try {
    showLoading(true);
    const response = await fetch('/jobs', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      const data = await response.json();
      const jobs = Object.values(data.jobs || {});
      const jobSelect = document.getElementById('job-select');
      jobSelect.innerHTML = '<option value="">-- Select a job --</option>';
      
      if (jobs.length > 0) {
        jobs.forEach(job => {
          const option = document.createElement('option');
          option.value = job.job_id;
          option.textContent = `${job.job_id} - ${job.client_name || 'Unknown'}`;
          jobSelect.appendChild(option);
        });
      }
    }
  } catch (error) {
    console.error('Failed to load jobs for financials:', error);
  } finally {
    showLoading(false);
  }
}

async function loadJobFinancials() {
  const jobId = document.getElementById('job-select').value;
  const contentDiv = document.getElementById('financials-content');
  
  if (!jobId) {
    contentDiv.innerHTML = '<p class="help-text">Select a job to view its financial profitability report.</p>';
    return;
  }
  
  try {
    showLoading(true);
    const response = await fetch(`/job/${encodeURIComponent(jobId)}/financials`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (response.ok) {
      const data = await response.json();
      displayFinancialReport(data);
    } else if (response.status === 403) {
      contentDiv.innerHTML = '<p class="error-message">You do not have permission to view financial data.</p>';
    } else {
      const error = await response.json();
      contentDiv.innerHTML = `<p class="error-message">${error.detail || 'Failed to load financial data'}</p>`;
    }
  } catch (error) {
    contentDiv.innerHTML = '<p class="error-message">Failed to load financial data. Please try again.</p>';
  } finally {
    showLoading(false);
  }
}

function displayFinancialReport(data) {
  const contentDiv = document.getElementById('financials-content');
  const summary = data.summary;
  
  let html = `
    <div class="financial-report">
      <div class="report-header">
        <h3>${data.job_id} - ${data.client_name || 'Unknown Client'}</h3>
      </div>
      
      <div class="financial-summary">
        <div class="summary-card revenue">
          <div class="summary-label">Total Revenue</div>
          <div class="summary-value">$${summary.total_revenue.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
          <div class="summary-detail">${data.invoices.length} invoice(s)</div>
        </div>
        
        <div class="summary-card costs">
          <div class="summary-label">Total Costs</div>
          <div class="summary-value">$${summary.total_costs.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
          <div class="summary-detail">${data.expenses.length} expense(s)</div>
        </div>
        
        <div class="summary-card profit ${summary.profit >= 0 ? 'positive' : 'negative'}">
          <div class="summary-label">Net Profit</div>
          <div class="summary-value">$${summary.profit.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
          <div class="summary-detail">${summary.margin_percent.toFixed(2)}% margin</div>
        </div>
      </div>
      
      <div class="financial-details">
        <div class="financial-section">
          <h4>Invoices (${data.invoices.length})</h4>
          ${data.invoices.length > 0 ? `
            <table class="financial-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Invoice ID</th>
                  <th>Customer</th>
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                ${data.invoices.map(inv => `
                  <tr>
                    <td>${inv.date || 'N/A'}</td>
                    <td>${inv.transaction_id}</td>
                    <td>${inv.customer_name || 'N/A'}</td>
                    <td>$${parseFloat(inv.amount).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    <td><span class="status-badge">${inv.status || 'N/A'}</span></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          ` : '<p class="help-text">No invoices recorded for this job.</p>'}
        </div>
        
        <div class="financial-section">
          <h4>Expenses (${data.expenses.length})</h4>
          ${data.expenses.length > 0 ? `
            <table class="financial-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Expense ID</th>
                  <th>Vendor</th>
                  <th>Category</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                ${data.expenses.map(exp => `
                  <tr>
                    <td>${exp.date || 'N/A'}</td>
                    <td>${exp.transaction_id}</td>
                    <td>${exp.vendor_name || 'N/A'}</td>
                    <td>${exp.category || 'N/A'}</td>
                    <td>$${parseFloat(exp.amount).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          ` : '<p class="help-text">No expenses recorded for this job.</p>'}
        </div>
      </div>
    </div>
  `;
  
  contentDiv.innerHTML = html;
}

// ─────────────────────────────────────────────────────────────────────────────
// PRODUCTION TAB  (F2, P21–P29)
// ─────────────────────────────────────────────────────────────────────────────

async function refreshProductionJobs() {
  const sel = document.getElementById('prod-job-select');
  const currentVal = sel.value;
  try {
    const data = await apiCall('/jobs');
    sel.innerHTML = '<option value="">Select a job&hellip;</option>';
    (data.jobs || []).forEach(j => {
      const opt = document.createElement('option');
      opt.value = j.job_id;
      opt.textContent = `${j.job_id} — ${j.client_name || 'Unknown'}`;
      if (j.job_id === currentVal) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch (e) { console.error('refreshProductionJobs', e); }
}

async function loadProductionDashboard() {
  const jobId = document.getElementById('prod-job-select').value;
  const el = document.getElementById('production-content');
  if (!jobId) { el.innerHTML = '<div class="empty-state"><p>Select a job above</p></div>'; return; }
  showLoading(true);
  try {
    const [dash, gallons, coverage, margin, punch, qaReadings] = await Promise.allSettled([
      apiCall(`/job/${jobId}/production-dashboard`),
      apiCall(`/job/${jobId}/gallons-tracker`),
      apiCall(`/job/${jobId}/coverage`),
      apiCall(`/job/${jobId}/margin-alert`),
      apiCall(`/job/${jobId}/punch-items`),
      apiCall(`/job/${jobId}/qa-reading`).catch(() => ({ qa_readings: [] })),
    ]);
    const d = dash.value || {};
    const g = gallons.value || {};
    const cov = coverage.value || {};
    const mar = margin.value || {};
    const punches = (punch.value || {}).punch_items || [];

    const healthColor = { good: '#22c55e', warning: '#f59e0b', alert: '#ef4444' };
    const badge = d.health_badge || 'good';

    let gallonRows = '';
    for (const [prod, info] of Object.entries(g.gallons || {})) {
      const pct = info.pct_consumed != null ? info.pct_consumed.toFixed(1) + '%' : 'N/A';
      const over = info.overrun ? ' style="color:#ef4444;font-weight:600"' : '';
      gallonRows += `<tr${over}><td>${prod}</td><td>${info.estimated}</td><td>${info.applied}</td><td>${pct}</td></tr>`;
    }

    const openPunch = punches.filter(p => p.status !== 'done');
    const punchRows = openPunch.map(p =>
      `<li class="punch-item">${p.description}${p.area ? ` <span class="help-text">(${p.area})</span>` : ''}
        <button onclick="closePunchItem('${jobId}', '${p.id}')" class="btn-secondary" style="padding:2px 8px;font-size:0.75rem;margin-left:8px;">Done</button>
      </li>`
    ).join('');

    el.innerHTML = `
      <div class="prod-dashboard">
        <div class="prod-header">
          <span class="health-badge" style="background:${healthColor[badge] || '#6b7280'};color:#fff;padding:3px 10px;border-radius:999px;font-size:0.8rem;text-transform:uppercase">${badge}</span>
          <h3 style="margin:0">${d.client || jobId}</h3>
          <span class="help-text">${d.last_log_date ? 'Last log: ' + d.last_log_date : 'No logs yet'}</span>
        </div>
        <div class="summary-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem;margin:1rem 0">
          <div class="summary-card"><div class="summary-label">% Complete</div><div class="summary-value">${(d.pct_complete || 0).toFixed(1)}%</div></div>
          <div class="summary-card"><div class="summary-label">Sqft Coated</div><div class="summary-value">${(d.total_sqft_coated || 0).toLocaleString()}</div><div class="summary-detail">of ${(d.sqft_target || 0).toLocaleString()}</div></div>
          <div class="summary-card"><div class="summary-label">Achieved Mil</div><div class="summary-value">${cov.achieved_dry_mil != null ? cov.achieved_dry_mil : '—'}</div><div class="summary-detail">target ${cov.target_dry_mil || '—'}</div></div>
          <div class="summary-card ${mar.alerts && mar.alerts.length ? 'negative' : ''}"><div class="summary-label">Margin Alerts</div><div class="summary-value">${(mar.alerts || []).length}</div></div>
          <div class="summary-card"><div class="summary-label">QA Flags</div><div class="summary-value">${d.qa_flag_count || 0}</div></div>
          <div class="summary-card"><div class="summary-label">Open Punch</div><div class="summary-value">${d.open_punch_items || 0}</div></div>
        </div>
        ${gallonRows ? `
          <h4>Gallons Tracker</h4>
          <table class="financial-table"><thead><tr><th>Product</th><th>Estimated</th><th>Applied</th><th>% Used</th></tr></thead>
          <tbody>${gallonRows}</tbody></table>` : ''}
        ${mar.alerts && mar.alerts.length ? `<div class="error-message" style="margin:1rem 0">${mar.alerts.join('<br>')}</div>` : ''}
        ${openPunch.length ? `<h4>Open Punch Items (${openPunch.length})</h4><ul class="punch-list" style="padding-left:1rem">${punchRows}</ul>` : ''}
        <div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
          <button onclick="showAddPunchModal('${jobId}')" class="btn-secondary">+ Punch Item</button>
          <button onclick="checkWeather('${jobId}')" class="btn-secondary">Weather Check</button>
          <button onclick="showQAModal('${jobId}')" class="btn-secondary">+ QA Reading</button>
        </div>
      </div>`;
  } catch (e) {
    el.innerHTML = `<p class="error-message">Failed to load production data: ${e.message}</p>`;
  } finally { showLoading(false); }
}

async function closePunchItem(jobId, itemId) {
  try {
    await apiCall(`/job/${jobId}/punch-items/${itemId}`, 'PUT', { status: 'done' });
    loadProductionDashboard();
  } catch (e) { alert('Failed to close punch item: ' + e.message); }
}

async function checkWeather(jobId) {
  showLoading(true);
  try {
    const res = await apiCall(`/job/${jobId}/weather-check`, 'POST', {});
    const color = res.verdict === 'GO' ? '#22c55e' : res.verdict === 'HOLD' ? '#ef4444' : '#f59e0b';
    alert(`Weather: ${res.verdict}\n${res.reason || ''}`);
    loadProductionDashboard();
  } catch (e) { alert('Weather check failed: ' + e.message); }
  finally { showLoading(false); }
}

function showQAModal(jobId) {
  const product = prompt('Product/system (e.g. silicone):');
  if (!product) return;
  const wetMilStr = prompt('Wet-mil readings (comma-separated, e.g. 20,21,19):');
  if (!wetMilStr) return;
  const wetMil = wetMilStr.split(',').map(v => parseFloat(v.trim())).filter(v => !isNaN(v));
  const coat = prompt('Coat number (1, 2, etc.):') || '1';
  apiCall(`/job/${jobId}/qa-reading`, 'POST', {
    product, wet_mil: wetMil, coat_seq: parseInt(coat), area: ''
  }).then(() => { alert('QA reading saved'); loadProductionDashboard(); })
    .catch(e => alert('Failed: ' + e.message));
}

function showAddPunchModal(jobId) {
  const desc = prompt('Describe the punch item:');
  if (!desc) return;
  const area = prompt('Area (optional):') || '';
  apiCall(`/job/${jobId}/punch-items`, 'POST', { description: desc, area }).then(() => {
    alert('Punch item added');
    loadProductionDashboard();
  }).catch(e => alert('Failed: ' + e.message));
}

// ─────────────────────────────────────────────────────────────────────────────
// PIPELINE TAB  (S30–S38)
// ─────────────────────────────────────────────────────────────────────────────

const PIPELINE_STAGES = ['New Lead', 'Site Survey', 'Measured/Cores', 'Estimating', 'Proposal', 'Negotiation', 'Won', 'Lost'];

async function refreshPipeline() {
  const el = document.getElementById('pipeline-content');
  showLoading(true);
  try {
    const [pipe, renewals, winLoss] = await Promise.allSettled([
      apiCall('/pipeline'),
      apiCall('/renewals'),
      apiCall('/sales/win-loss'),
    ]);
    const stages = (pipe.value || {}).pipeline || {};
    const ren = (renewals.value || {}).renewals || [];
    const wl = winLoss.value || {};

    let html = `<div class="pipeline-summary" style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1rem">
      <div class="summary-card"><div class="summary-label">Win Rate</div><div class="summary-value">${wl.win_rate_pct || 0}%</div><div class="summary-detail">${wl.wins || 0}W / ${wl.losses || 0}L</div></div>
    </div>
    <div class="kanban" style="display:flex;gap:.75rem;overflow-x:auto;padding-bottom:.5rem">`;

    for (const stage of PIPELINE_STAGES) {
      const opps = stages[stage] || [];
      html += `<div class="kanban-col" style="min-width:180px;background:#1e293b;border-radius:8px;padding:.75rem">
        <div style="font-weight:600;font-size:.85rem;margin-bottom:.5rem;color:#94a3b8">${stage} (${opps.length})</div>
        ${opps.map(o => `
          <div class="kanban-card" style="background:#0f172a;border-radius:6px;padding:.5rem;margin-bottom:.5rem;font-size:.82rem">
            <div style="font-weight:600">${o.client_name || 'Unknown'}</div>
            <div class="help-text">${o.address || ''}</div>
            <div style="margin-top:.35rem;display:flex;gap:.25rem;flex-wrap:wrap">
              ${PIPELINE_STAGES.filter(s => s !== stage && s !== 'Lost').map(s =>
                `<button onclick="moveOpp('${o.id}','${s}')" style="font-size:.7rem;padding:1px 5px" class="btn-secondary">${s.split(' ')[0]}</button>`
              ).join('')}
            </div>
          </div>`).join('')}
        </div>`;
    }
    html += '</div>';
    el.innerHTML = html;

    const renEl = document.getElementById('renewals-content');
    if (ren.length) {
      renEl.innerHTML = `<table class="financial-table"><thead><tr><th>Client</th><th>Address</th><th>System</th><th>Due</th><th>Days</th></tr></thead><tbody>
        ${ren.slice(0, 10).map(r => `<tr><td>${r.client || ''}</td><td>${r.address || ''}</td><td>${r.system || ''}</td><td>${r.renewal_due || ''}</td><td style="color:${r.days_until_due < 90 ? '#ef4444' : '#22c55e'}">${r.days_until_due}</td></tr>`).join('')}
      </tbody></table>`;
    } else {
      renEl.innerHTML = '<p class="help-text">No renewals due.</p>';
    }
  } catch (e) {
    el.innerHTML = `<p class="error-message">Failed to load pipeline: ${e.message}</p>`;
  } finally { showLoading(false); }
}

async function moveOpp(oppId, stage) {
  try {
    await apiCall(`/pipeline/${oppId}/stage`, 'PUT', { stage, notes: '' });
    refreshPipeline();
  } catch (e) { alert('Failed to move opportunity: ' + e.message); }
}

// ─────────────────────────────────────────────────────────────────────────────
// SCHEDULE TAB  (C39–C45)
// ─────────────────────────────────────────────────────────────────────────────

async function refreshSchedule() {
  const el = document.getElementById('schedule-content');
  const weatherEl = document.getElementById('weather-verdicts-bar');
  showLoading(true);
  try {
    const [assignments, verdicts, anomalies] = await Promise.allSettled([
      apiCall('/schedule/assignments'),
      apiCall('/schedule/weather-verdicts'),
      apiCall('/jobs/anomalies'),
    ]);

    const asgns = (assignments.value || {}).assignments || [];
    const vds = (verdicts.value || {}).scheduled_jobs || [];
    const flags = (anomalies.value || {}).anomaly_flags || [];

    // Weather verdicts bar
    if (vds.length) {
      const verdictColor = { GO: '#22c55e', HOLD: '#ef4444', CAUTION: '#f59e0b', UNKNOWN: '#6b7280' };
      weatherEl.innerHTML = `<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem">
        ${vds.map(v => `<span style="background:${verdictColor[v.verdict] || '#6b7280'};color:#fff;padding:4px 10px;border-radius:999px;font-size:.8rem">
          ${v.client || v.job_id}: ${v.verdict}</span>`).join('')}
      </div>`;
    } else {
      weatherEl.innerHTML = '';
    }

    // Anomaly flags
    let anomalyHtml = '';
    if (flags.length) {
      anomalyHtml = `<div class="error-message" style="margin-bottom:1rem">
        <strong>${flags.length} anomaly flag(s):</strong>
        <ul style="margin:.25rem 0 0 1rem;padding:0">
          ${flags.slice(0, 5).map(f => `<li>${f.type.replace(/_/g,' ')} — ${f.client || f.job_id}</li>`).join('')}
        </ul>
      </div>`;
    }

    // Grouped by date
    const byDate = {};
    asgns.forEach(a => {
      const d = a.date || 'No date';
      (byDate[d] = byDate[d] || []).push(a);
    });

    let html = anomalyHtml;
    if (!Object.keys(byDate).length) {
      html += '<div class="empty-state"><p>No assignments scheduled</p></div>';
    } else {
      Object.keys(byDate).sort().forEach(date => {
        html += `<div style="margin-bottom:1rem"><h4 style="margin:0 0 .5rem">${date}</h4>
          <table class="financial-table"><thead><tr><th>Job</th><th>Client</th><th>Crew</th><th>Phase</th><th>Weather</th></tr></thead><tbody>
          ${byDate[date].map(a => `<tr>
            <td>${a.job_id}</td>
            <td>${a.client || ''}</td>
            <td>${a.crew || ''}</td>
            <td>${a.phase || ''}</td>
            <td>${(a.weather_status || {}).verdict || '?'}</td>
          </tr>`).join('')}
          </tbody></table></div>`;
      });
    }
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<p class="error-message">Failed to load schedule: ${e.message}</p>`;
  } finally { showLoading(false); }
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPLIANCE TAB  (O46–O56)
// ─────────────────────────────────────────────────────────────────────────────

async function refreshCompliance() {
  const el = document.getElementById('compliance-content');
  showLoading(true);
  try {
    const data = await apiCall('/compliance/dashboard');
    const expCOIs = (data.expiring_cois || []);
    const expCerts = (data.expiring_employee_certs || []);
    const uncleared = (data.uncleared_parties || []);
    const sdsGaps = (data.sds_gaps || []);

    el.innerHTML = `
      <div class="summary-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin-bottom:1.5rem">
        <div class="summary-card ${expCOIs.length ? 'negative' : ''}">
          <div class="summary-label">Expiring COIs</div>
          <div class="summary-value">${expCOIs.length}</div>
        </div>
        <div class="summary-card ${expCerts.length ? 'negative' : ''}">
          <div class="summary-label">Expiring Certs</div>
          <div class="summary-value">${expCerts.length}</div>
        </div>
        <div class="summary-card ${uncleared.length ? 'negative' : ''}">
          <div class="summary-label">Uncleared Subs</div>
          <div class="summary-value">${uncleared.length}</div>
        </div>
        <div class="summary-card ${sdsGaps.length ? 'negative' : ''}">
          <div class="summary-label">SDS Gaps</div>
          <div class="summary-value">${sdsGaps.length}</div>
        </div>
      </div>
      ${expCOIs.length ? `
        <h4>Expiring / Missing COIs</h4>
        <table class="financial-table"><thead><tr><th>Party</th><th>Expiry</th><th>Days</th></tr></thead>
        <tbody>${expCOIs.slice(0, 10).map(c =>
          `<tr><td>${c.name || c.party_id}</td><td>${c.expiry || 'Missing'}</td>
           <td style="color:${c.days_until_expiry < 30 ? '#ef4444' : '#f59e0b'}">${c.days_until_expiry != null ? c.days_until_expiry : '—'}</td></tr>`).join('')}
        </tbody></table>` : ''}
      ${uncleared.length ? `
        <h4>Uncleared Subs/Vendors</h4>
        <ul style="padding-left:1rem">${uncleared.slice(0, 10).map(p => `<li>${p.name}</li>`).join('')}</ul>` : ''}
      ${sdsGaps.length ? `
        <h4>Products Missing SDS</h4>
        <ul style="padding-left:1rem">${sdsGaps.slice(0, 10).map(p => `<li>${p}</li>`).join('')}</ul>` : ''}
      ${!expCOIs.length && !uncleared.length && !sdsGaps.length && !expCerts.length
        ? '<div class="empty-state"><p style="color:#22c55e">All clear — no compliance gaps</p></div>' : ''}`;
  } catch (e) {
    el.innerHTML = `<p class="error-message">Failed to load compliance data: ${e.message}</p>`;
  } finally { showLoading(false); }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab init hooks — load data when switching to new tabs
// ─────────────────────────────────────────────────────────────────────────────

const _tabInitializers = {
  production: () => refreshProductionJobs(),
  pipeline: () => refreshPipeline(),
  schedule: () => refreshSchedule(),
  compliance: () => refreshCompliance(),
};

// Patch showTab to call initializers
const _origShowTab = showTab;
window.showTab = function(tabName, btn) {
  _origShowTab(tabName, btn);
  if (_tabInitializers[tabName]) _tabInitializers[tabName]();
};
