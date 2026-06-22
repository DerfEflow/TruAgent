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

  // Reset role-gated visibility first, so switching accounts in-place (logout →
  // login without a page reload) can never leave a higher role's tabs showing.
  document.querySelectorAll('.manager-only, .admin-only, .super-admin-only')
    .forEach(el => el.classList.add('hidden'));

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
  if (tabName === 'pipeline') refreshPipeline();
  if (tabName === 'inbox') refreshInbox();
  if (tabName === 'customers') refreshCustomers();
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
    // GET /jobs returns { jobs: { <id>: {...} } } (an object, not an array).
    Object.values(data.jobs || {}).forEach(j => {
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
    // coverage + margin-alert are manager+ only; for field crew they reject and
    // degrade gracefully (allSettled), so the production dashboard still renders.
    const [dash, gallons, coverage, margin, punch] = await Promise.allSettled([
      apiCall(`/job/${jobId}/production-dashboard`),
      apiCall(`/job/${jobId}/gallons-tracker`),
      apiCall(`/job/${jobId}/coverage`),
      apiCall(`/job/${jobId}/margin-alert`),
      apiCall(`/job/${jobId}/punch-items`),
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
    // Backend verdict vocabulary is GREEN / YELLOW / RED / UNKNOWN.
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
const LOSS_REASONS = ['price', 'tear_off', 'competitor', 'saturated', 'warranty_short', 'weather', 'timing', 'other'];
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function refreshPipeline() {
  const el = document.getElementById('pipeline-content');
  showLoading(true);
  try {
    const [pipe, renewals, winLoss, alerts, perf, srcRoi] = await Promise.allSettled([
      apiCall('/pipeline'), apiCall('/renewals'), apiCall('/sales/win-loss'),
      apiCall('/sales/alerts'), apiCall('/sales/performance'), apiCall('/sales/source-roi'),
    ]);
    const stages = (pipe.value || {}).pipeline || {};
    const ren = (renewals.value || {}).renewals || [];
    const wl = winLoss.value || {};
    const al = alerts.value || { sla_breaches: [], overdue_followups: [] };
    const pf = perf.value || { by_rep: {}, by_territory: {} };
    const sr = (srcRoi.value || {}).by_source || {};
    const overdue = (al.overdue_followups || []), sla = (al.sla_breaches || []);

    // Summary cards
    let html = `<div class="pipeline-summary" style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1rem">
      <div class="summary-card"><div class="summary-label">Win Rate</div><div class="summary-value">${wl.win_rate_pct || 0}%</div><div class="summary-detail">${wl.wins || 0}W / ${wl.losses || 0}L</div></div>
      <div class="summary-card"><div class="summary-label">Follow-ups Overdue</div><div class="summary-value" style="color:${overdue.length ? '#e8920a' : 'inherit'}">${overdue.length}</div></div>
      <div class="summary-card"><div class="summary-label">SLA Breaches</div><div class="summary-value" style="color:${sla.length ? '#e53935' : 'inherit'}">${sla.length}</div></div>
    </div>`;

    // Alerts banner
    if (overdue.length || sla.length) {
      const items = [...sla.map(o => ({ ...o, kind: 'SLA breach', col: '#e53935' })),
                     ...overdue.map(o => ({ ...o, kind: 'Follow-up overdue', col: '#e8920a' }))];
      html += `<div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:.6rem .8rem;margin-bottom:1rem">
        <div style="font-weight:600;font-size:.85rem;margin-bottom:.35rem">&#9888; Needs attention (${items.length})</div>
        ${items.slice(0, 12).map(o => `<div style="font-size:.8rem;cursor:pointer" onclick="openOppDetail('${o.id}')">
          <span style="color:${o.col}">&bull; ${esc(o.kind)}</span> — ${esc(o.client_name || 'Unknown')} <span class="help-text">(${esc(o.stage || '')})</span></div>`).join('')}
      </div>`;
    }

    // Kanban (drag-and-drop)
    html += `<div class="kanban" style="display:flex;gap:.75rem;overflow-x:auto;padding-bottom:.5rem">`;
    for (const stage of PIPELINE_STAGES) {
      const opps = stages[stage] || [];
      html += `<div class="kanban-col" ondragover="event.preventDefault()" ondrop="oppDrop(event,'${stage}')"
          style="min-width:190px;background:#1e293b;border-radius:8px;padding:.75rem">
        <div style="font-weight:600;font-size:.85rem;margin-bottom:.5rem;color:#94a3b8">${esc(stage)} (${opps.length})</div>
        ${opps.map(o => kanbanCard(o)).join('')}
      </div>`;
    }
    html += '</div>';

    // Rep / Territory / Source / Loss-reason analytics
    html += perfTables(pf, wl, sr);
    el.innerHTML = html;

    const renEl = document.getElementById('renewals-content');
    renEl.innerHTML = ren.length
      ? `<table class="financial-table"><thead><tr><th>Client</th><th>Address</th><th>System</th><th>Due</th><th>Days</th></tr></thead><tbody>
          ${ren.slice(0, 10).map(r => `<tr><td>${esc(r.client)}</td><td>${esc(r.address)}</td><td>${esc(r.system)}</td><td>${esc(r.renewal_due)}</td><td style="color:${r.days_until_due < 90 ? '#e53935' : '#00a855'}">${r.days_until_due}</td></tr>`).join('')}
        </tbody></table>`
      : '<p class="help-text">No renewals due.</p>';
  } catch (e) {
    el.innerHTML = `<p class="error-message">Failed to load pipeline: ${e.message}</p>`;
  } finally { showLoading(false); }
}

function kanbanCard(o) {
  return `<div class="kanban-card" draggable="true" ondragstart="oppDragStart(event,'${o.id}')"
      style="background:#0f172a;border-radius:6px;padding:.5rem;margin-bottom:.5rem;font-size:.82rem;cursor:grab">
    <div onclick="openOppDetail('${o.id}')" style="cursor:pointer">
      <div style="font-weight:600">${esc(o.client_name || 'Unknown')}</div>
      <div class="help-text">${esc(o.address || '')}</div>
      ${o.contract_value ? `<div class="help-text">$${Number(o.contract_value).toLocaleString()}</div>` : ''}
      ${o.rep ? `<div class="help-text">Rep: ${esc(o.rep)}</div>` : ''}
    </div>
    <div style="margin-top:.4rem;display:flex;gap:.25rem;flex-wrap:wrap">
      <button onclick="event.stopPropagation();markOutcome('${o.id}','won')" style="font-size:.7rem;padding:1px 6px" class="btn-primary">Won</button>
      <button onclick="event.stopPropagation();markOutcome('${o.id}','lost')" style="font-size:.7rem;padding:1px 6px" class="btn-secondary">Lost</button>
      ${o.job_id
        ? `<span style="font-size:.7rem;color:var(--green-hi)" title="${esc(o.job_id)}">&#10003; Job</span>`
        : `<button onclick="event.stopPropagation();convertOpp('${o.id}')" style="font-size:.7rem;padding:1px 6px" class="btn-secondary">&rarr; Job</button>`}
    </div>
  </div>`;
}

function perfTables(pf, wl, sr) {
  const rep = pf.by_rep || {}, terr = pf.by_territory || {}, reasons = wl.by_loss_reason || {}, src = sr || {};
  const tbl = (title, data, label) => {
    const rows = Object.entries(data);
    if (!rows.length) return '';
    return `<div style="margin-top:1.5rem"><h3>${title}</h3>
      <table class="financial-table"><thead><tr><th>${label}</th><th>Leads</th><th>Won</th><th>Lost</th><th>Open</th><th>Win %</th><th>Won $</th></tr></thead><tbody>
      ${rows.map(([k, d]) => `<tr><td>${esc(k)}</td><td>${d.leads}</td><td>${d.won}</td><td>${d.lost}</td><td>${d.open}</td><td>${d.win_rate_pct}%</td><td>$${Number(d.won_value || 0).toLocaleString()}</td></tr>`).join('')}
      </tbody></table></div>`;
  };
  let html = tbl('Rep Performance', rep, 'Rep') + tbl('Territory Performance', terr, 'Territory')
           + tbl('Lead Source ROI', src, 'Source');
  const rEntries = Object.entries(reasons);
  if (rEntries.length) {
    html += `<div style="margin-top:1.5rem"><h3>Loss Reasons</h3>
      <table class="financial-table"><thead><tr><th>Reason</th><th>Count</th></tr></thead><tbody>
      ${rEntries.sort((a, b) => b[1] - a[1]).map(([k, n]) => `<tr><td>${esc(k)}</td><td>${n}</td></tr>`).join('')}
      </tbody></table></div>`;
  }
  return html;
}

// Drag-and-drop (P1-7)
function oppDragStart(ev, oppId) { ev.dataTransfer.setData('text/plain', oppId); ev.dataTransfer.effectAllowed = 'move'; }
async function oppDrop(ev, stage) {
  ev.preventDefault();
  const oppId = ev.dataTransfer.getData('text/plain');
  if (oppId) await moveOpp(oppId, stage);
}

async function moveOpp(oppId, stage) {
  try {
    await apiCall(`/pipeline/${oppId}/stage`, 'PUT', { stage, notes: '' });
    refreshPipeline();
  } catch (e) { alert('Failed to move opportunity: ' + e.message); }
}

async function convertOpp(oppId) {
  if (!confirm('Create a linked production job for this opportunity?')) return;
  try {
    const r = await apiCall(`/pipeline/${oppId}/convert`, 'POST', {});
    alert(r.message || 'Converted to job');
    refreshPipeline();
  } catch (e) { alert('Failed to convert: ' + e.message); }
}

// Win/Loss (P1-2)
async function markOutcome(oppId, outcome) {
  let body = { outcome };
  if (outcome === 'lost') {
    const reason = prompt('Loss reason (' + LOSS_REASONS.join(' / ') + '):', 'price');
    if (reason === null) return;
    body.loss_reason = reason;
  } else if (!confirm('Mark this opportunity WON? (If it has a linked job, it will be handed to production.)')) {
    return;
  }
  try {
    await apiCall(`/pipeline/${oppId}/win-loss`, 'POST', body);
    refreshPipeline();
  } catch (e) { alert('Failed to record outcome: ' + e.message); }
}

// Opportunity detail modal (P1-8): timeline + cadence + comm-log + log-follow-up
async function openOppDetail(oppId) {
  let modal = document.getElementById('opp-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'opp-modal';
    modal.className = 'modal';
    document.body.appendChild(modal);
  }
  modal.classList.remove('hidden');
  modal.innerHTML = `<div class="modal-content"><p class="help-text">Loading…</p></div>`;
  try {
    const tl = await apiCall(`/pipeline/${oppId}/timeline`);
    const timeline = (tl.timeline || []).slice().reverse();
    const cadence = (tl.cadence_log || []).slice().reverse();
    let html = `<div class="modal-content" style="max-width:560px;max-height:80vh;overflow:auto">
      <h3>Opportunity Detail</h3>
      <div style="margin:.5rem 0">
        <h4 style="margin:.5rem 0 .25rem">Log a follow-up</h4>
        <div style="display:flex;gap:.4rem;flex-wrap:wrap;align-items:center">
          <select id="cad-type"><option value="call">Call</option><option value="email">Email</option><option value="sms">SMS</option><option value="visit">Visit</option><option value="note">Note</option></select>
          <input id="cad-summary" placeholder="What happened / next step" style="flex:1;min-width:160px">
          <label class="help-text">Next due <input id="cad-due" type="date"></label>
          <button class="btn-primary" onclick="logFollowup('${oppId}')">Save</button>
        </div>
      </div>
      <h4 style="margin:.75rem 0 .25rem">Cadence (${cadence.length})</h4>
      ${cadence.length ? cadence.map(c => `<div style="font-size:.82rem;border-bottom:1px solid var(--border);padding:.3rem 0">
        <strong>${esc(c.contact_type)}</strong> — ${esc(c.summary)} <span class="help-text">(${esc((c.at||'').slice(0,16))}${c.due_at ? ', next ' + esc(c.due_at.slice(0,10)) : ''})</span></div>`).join('') : '<p class="help-text">No cadence steps yet.</p>'}
      <h4 style="margin:.75rem 0 .25rem">Timeline (${timeline.length})</h4>
      ${timeline.length ? timeline.map(t => `<div style="font-size:.8rem;border-bottom:1px solid var(--border);padding:.25rem 0">
        <span style="color:var(--green-hi)">${esc(t.event)}</span> <span class="help-text">${esc((t.at||'').slice(0,16))}</span>
        ${t.to ? ' &rarr; ' + esc(t.to) : ''}${t.summary ? ' — ' + esc(t.summary) : ''}${t.job_id ? ' (' + esc(t.job_id) + ')' : ''}</div>`).join('') : '<p class="help-text">No timeline yet.</p>'}
      <div class="modal-actions" style="margin-top:1rem"><button class="btn-secondary" onclick="closeOppDetail()">Close</button></div>
    </div>`;
    modal.innerHTML = html;
  } catch (e) {
    modal.innerHTML = `<div class="modal-content"><p class="error-message">Failed to load: ${e.message}</p><div class="modal-actions"><button class="btn-secondary" onclick="closeOppDetail()">Close</button></div></div>`;
  }
}
function closeOppDetail() { const m = document.getElementById('opp-modal'); if (m) m.classList.add('hidden'); }
async function logFollowup(oppId) {
  const contact_type = document.getElementById('cad-type').value;
  const summary = document.getElementById('cad-summary').value.trim();
  if (!summary) { alert('Add a short summary.'); return; }
  const dueVal = document.getElementById('cad-due').value;
  const body = { contact_type, summary };
  if (dueVal) body.due_at = new Date(dueVal).toISOString();
  try {
    await apiCall(`/pipeline/${oppId}/cadence`, 'POST', body);
    closeOppDetail();
    refreshPipeline();
  } catch (e) { alert('Failed to log follow-up: ' + e.message); }
}

// ─────────────────────────────────────────────────────────────────────────────
// INBOX TAB  (P2-10 unified comms)
// ─────────────────────────────────────────────────────────────────────────────

let _currentThread = null;

async function refreshInbox() {
  const listEl = document.getElementById('inbox-threads');
  try {
    const r = await apiCall('/inbox');
    const threads = r.threads || [];
    if (!threads.length) {
      listEl.innerHTML = '<p class="help-text" style="padding:.5rem">No messages yet. Inbound email/SMS will appear here once the inbox door is wired.</p>';
      return;
    }
    listEl.innerHTML = threads.map(t => `
      <div class="inbox-thread-item${t.unread ? ' unread' : ''}" onclick="openInboxThread('${t.thread_key}')">
        <div style="display:flex;justify-content:space-between;gap:.5rem">
          <strong style="font-size:.85rem">${esc(t.client_name || t.contact || 'Unknown')}</strong>
          ${t.unread ? `<span class="inbox-badge">${t.unread}</span>` : ''}
        </div>
        <div class="help-text" style="font-size:.75rem">${t.channel === 'sms' ? '&#128241;' : '&#9993;'} ${esc(t.contact || '')}</div>
        <div class="help-text" style="font-size:.78rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${t.last_direction === 'outbound' ? '&rarr; ' : ''}${esc(t.last_snippet || '')}</div>
      </div>`).join('');
  } catch (e) {
    listEl.innerHTML = `<p class="error-message">Failed to load inbox: ${e.message}</p>`;
  }
}

async function openInboxThread(key) {
  _currentThread = key;
  const el = document.getElementById('inbox-thread-view');
  el.innerHTML = '<p class="help-text">Loading…</p>';
  try {
    const r = await apiCall('/inbox/thread?key=' + encodeURIComponent(key));
    const msgs = r.messages || [];
    const channel = (msgs[0] || {}).channel || 'email';
    const contact = (msgs.find(m => m.direction === 'inbound') || msgs[0] || {}).contact || '';
    const bubbles = msgs.map(m => `
      <div style="margin:.4rem 0;display:flex;${m.direction === 'outbound' ? 'justify-content:flex-end' : ''}">
        <div style="max-width:80%;background:${m.direction === 'outbound' ? 'var(--green-dim)' : 'var(--panel-hi)'};border:1px solid var(--border);border-radius:8px;padding:.5rem .65rem">
          ${m.subject ? `<div style="font-weight:600;font-size:.8rem">${esc(m.subject)}</div>` : ''}
          <div style="font-size:.85rem;white-space:pre-wrap">${esc(m.body || '')}</div>
          <div class="help-text" style="font-size:.68rem;margin-top:.2rem">${m.direction === 'outbound' ? 'You' : esc(m.name || contact)} &middot; ${esc((m.at || '').slice(0, 16))}${m.status === 'queued' ? ' &middot; queued' : ''}</div>
        </div>
      </div>`).join('');
    el.innerHTML = `
      <div style="font-weight:600;margin-bottom:.5rem">${channel === 'sms' ? '&#128241; SMS' : '&#9993; Email'} &middot; ${esc(contact)}</div>
      <div style="max-height:50vh;overflow:auto;padding-right:.25rem">${bubbles}</div>
      <div style="margin-top:.6rem;display:flex;gap:.4rem;align-items:flex-end">
        <textarea id="inbox-reply" rows="2" placeholder="Type a reply…" style="flex:1"></textarea>
        <button class="btn-primary" onclick="sendInboxReply('${esc(channel)}','${esc(contact)}')">Send</button>
      </div>
      <p class="help-text" style="font-size:.72rem;margin-top:.3rem">Replies queue until the ${channel === 'sms' ? 'SMS' : 'email'} Zap is connected.</p>`;
    if (r.messages.some(m => m.direction === 'inbound' && m.status === 'unread')) {
      apiCall('/inbox/thread/read?key=' + encodeURIComponent(key), 'POST', {}).then(refreshInbox);
    }
  } catch (e) {
    el.innerHTML = `<p class="error-message">Failed to load thread: ${e.message}</p>`;
  }
}

async function sendInboxReply(channel, to) {
  const ta = document.getElementById('inbox-reply');
  const body = (ta.value || '').trim();
  if (!body) { alert('Type a message first.'); return; }
  try {
    await apiCall('/inbox/send', 'POST', { channel, to, body, subject: 'Re: (Truline Roofing)' });
    if (_currentThread) await openInboxThread(_currentThread);
    refreshInbox();
  } catch (e) { alert('Failed to send: ' + e.message); }
}

// ─────────────────────────────────────────────────────────────────────────────
// CUSTOMERS TAB  (P2-9) + material orders (P2-11)
// ─────────────────────────────────────────────────────────────────────────────

function showAddCustomer() { document.getElementById('add-customer-row').classList.remove('hidden'); }

async function addCustomer() {
  const name = document.getElementById('cust-name').value.trim();
  if (!name) { alert('Name is required.'); return; }
  const emails = document.getElementById('cust-emails').value.split(',').map(s => s.trim()).filter(Boolean);
  const phones = document.getElementById('cust-phones').value.split(',').map(s => s.trim()).filter(Boolean);
  const company = document.getElementById('cust-company').value.trim();
  try {
    await apiCall('/customers', 'POST', { name, company, emails, phones });
    document.getElementById('add-customer-row').classList.add('hidden');
    ['cust-name', 'cust-company', 'cust-emails', 'cust-phones'].forEach(id => document.getElementById(id).value = '');
    refreshCustomers();
  } catch (e) { alert('Failed to add customer: ' + e.message); }
}

async function refreshCustomers() {
  const el = document.getElementById('customers-list');
  try {
    const r = await apiCall('/customers');
    const cs = r.customers || [];
    if (!cs.length) { el.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128100;</div><p>No customers yet</p><span>Add one, or they auto-link from jobs by email/phone</span></div>'; return; }
    el.innerHTML = cs.map(c => `
      <div class="job-card" style="cursor:pointer" onclick="openCustomer('${c.id}')">
        <div style="display:flex;justify-content:space-between">
          <strong>${esc(c.name)}</strong>
          <span class="help-text">${c.job_count} jobs &middot; ${c.opp_count} opps &middot; ${c.thread_count} threads</span>
        </div>
        <div class="help-text">${esc(c.company || '')} ${esc((c.emails || []).join(', '))} ${esc((c.phones || []).join(', '))}</div>
      </div>`).join('');
  } catch (e) { el.innerHTML = `<p class="error-message">Failed to load customers: ${e.message}</p>`; }
}

async function openCustomer(cid) {
  let modal = document.getElementById('opp-modal');
  if (!modal) { modal = document.createElement('div'); modal.id = 'opp-modal'; modal.className = 'modal'; document.body.appendChild(modal); }
  modal.classList.remove('hidden');
  modal.innerHTML = '<div class="modal-content"><p class="help-text">Loading…</p></div>';
  try {
    const r = await apiCall('/customer/' + encodeURIComponent(cid));
    const c = r.customer;
    const jobs = r.jobs || [], opps = r.opportunities || [], threads = r.threads || [];
    modal.innerHTML = `<div class="modal-content" style="max-width:580px;max-height:82vh;overflow:auto">
      <h3>${esc(c.name)}</h3>
      <div class="help-text">${esc(c.company || '')}</div>
      <div class="help-text">${esc((c.emails || []).join(', '))} ${esc((c.phones || []).join(', '))}</div>
      <h4 style="margin:.75rem 0 .25rem">Jobs (${jobs.length})</h4>
      ${jobs.length ? jobs.map(j => `<div style="font-size:.83rem;border-bottom:1px solid var(--border);padding:.35rem 0;display:flex;justify-content:space-between;gap:.5rem;align-items:center">
        <span>${esc(j.client_name || j.job_id)} <span class="help-text">${esc(j.workflow_stage || '')} &middot; ${j.material_orders} order(s)</span></span>
        <button class="btn-secondary" style="font-size:.7rem;padding:1px 6px" onclick="makeMaterialOrder('${j.job_id}')">Material order</button>
      </div>`).join('') : '<p class="help-text">No linked jobs.</p>'}
      <h4 style="margin:.75rem 0 .25rem">Opportunities (${opps.length})</h4>
      ${opps.length ? opps.map(o => `<div style="font-size:.83rem;border-bottom:1px solid var(--border);padding:.3rem 0">${esc(o.client_name || o.id)} <span class="help-text">${esc(o.stage || '')}</span></div>`).join('') : '<p class="help-text">No linked opportunities.</p>'}
      <h4 style="margin:.75rem 0 .25rem">Message threads (${threads.length})</h4>
      ${threads.length ? threads.map(t => `<div style="font-size:.8rem" class="help-text">${esc(t)}</div>`).join('') : '<p class="help-text">No threads.</p>'}
      <div class="modal-actions" style="margin-top:1rem"><button class="btn-secondary" onclick="closeOppDetail()">Close</button></div>
    </div>`;
  } catch (e) {
    modal.innerHTML = `<div class="modal-content"><p class="error-message">Failed: ${e.message}</p><div class="modal-actions"><button class="btn-secondary" onclick="closeOppDetail()">Close</button></div></div>`;
  }
}

async function makeMaterialOrder(jobId) {
  const supplier = prompt('Supplier name (optional):', '');
  if (supplier === null) return;
  const sendTo = prompt('Email the order to (optional — leave blank to just save a draft):', '');
  if (sendTo === null) return;
  try {
    const body = { supplier, waste_pct: 10 };
    if (sendTo.trim()) body.send_to = sendTo.trim();
    const r = await apiCall(`/job/${jobId}/material-order`, 'POST', body);
    const lines = (r.order.line_items || []).map(li => `${li.product}: ${li.order_gallons} ${li.unit}`).join('\n');
    alert(`Material order ${r.order.status}:\n\n${lines || '(no estimate gallons on this job)'}`);
  } catch (e) { alert('Failed to create material order: ' + e.message); }
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
      const verdictColor = { GREEN: '#22c55e', YELLOW: '#f59e0b', RED: '#ef4444', UNKNOWN: '#6b7280' };
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
    const expCerts = (data.expiring_certs || []);
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
      ${expCerts.length ? `
        <h4>Expiring Employee Certs</h4>
        <table class="financial-table"><thead><tr><th>Employee</th><th>Cert</th><th>Expiry</th><th>Days</th></tr></thead>
        <tbody>${expCerts.slice(0, 10).map(c =>
          `<tr><td>${c.name || c.employee_id}</td><td>${(c.cert_type || '').replace(/_/g,' ')}</td><td>${c.expiry || 'Missing'}</td>
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
