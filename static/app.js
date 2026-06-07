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
        jobsList.innerHTML = '<div class="empty-state"><div class="empty-icon">&#9634;</div><p>No jobs synced yet</p><span>Jobs appear here once Roofr is connected</span></div>';
      } else {
        jobs.forEach(job => {
          const status = job.status || 'Unknown';
          const statusClass = status.toLowerCase().replace(/\s+/g, '-');
          const notesText = (job.notes || [])
            .map(n => (typeof n === 'string' ? n : (n && n.note) ? n.note : ''))
            .filter(Boolean)
            .join('; ');
          const jobCard = document.createElement('div');
          jobCard.className = 'job-card';
          jobCard.innerHTML = `
            <h3>${job.client_name || 'N/A'}</h3>
            <p><strong>Job ID:</strong> ${job.job_id || 'N/A'}</p>
            <p><strong>Address:</strong> ${job.address || 'N/A'}</p>
            <p><strong>Status:</strong> <span class="status-badge status-${statusClass}">${status}</span></p>
            ${notesText ? `<p><strong>Notes:</strong> ${notesText}</p>` : ''}
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
