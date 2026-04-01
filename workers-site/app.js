// Gare Scraper Dashboard - Frontend JS

const PAGE_SIZE = 50;
let allErrors = [];
let filteredErrors = [];
let currentPage = 1;

// 驗證資訊管理（使用 localStorage 儲存）
const AUTH_STORAGE_KEY = 'gare_auth_config';

function loadAuthConfig() {
  try {
    const stored = localStorage.getItem(AUTH_STORAGE_KEY);
    return stored ? JSON.parse(stored) : { cookie: '', token: '' };
  } catch (e) {
    console.error('Failed to load auth config:', e);
    return { cookie: '', token: '' };
  }
}

async function saveAuthConfig(cookie, token) {
  // 同時儲存到後端 API 和本地 localStorage
  try {
    // 儲存到本地
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ cookie, token }));
    
    // 嘗試儲存到後端 KV（如果可用）
    try {
      await fetch('/api/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cookie, token })
      });
    } catch (apiErr) {
      console.warn('Backend KV not available, using localStorage only:', apiErr);
    }
    
    return true;
  } catch (e) {
    console.error('Failed to save auth config:', e);
    return false;
  }
}

async function testAuthConnection() {
  const statusEl = document.getElementById('auth-status');
  statusEl.className = 'status-message loading';
  statusEl.textContent = '測試連線中...';
  
  try {
    const response = await fetch('https://grok.com', {
      method: 'HEAD',
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    if (response.status === 200) {
      statusEl.className = 'status-message success';
      statusEl.textContent = '✅ 連線成功！grok.com 可訪問';
    } else if (response.status === 403) {
      statusEl.className = 'status-message error';
      statusEl.textContent = '⚠️ 403 Forbidden - 需要驗證資訊';
    } else {
      statusEl.className = 'status-message warning';
      statusEl.textContent = `⚠️ 狀態碼：${response.status}`;
    }
  } catch (e) {
    statusEl.className = 'status-message error';
    statusEl.textContent = `❌ 連線失敗：${e.message}`;
  }
}

async function fetchData() {
  try {
    const response = await fetch('/api/data');
    const data = await response.json();
    return data;
  } catch (e) {
    console.error('Failed to fetch data:', e);
    return null;
  }
}

// For local demo: load scraping_index.json directly if served as static
async function fetchIndexJson() {
  try {
    const response = await fetch('/scraping_index.json');
    const data = await response.json();
    return data;
  } catch (e) {
    return null;
  }
}

function renderStats(data) {
  const stats = data.statistics || {};
  document.getElementById('pages-count').textContent = stats.pages_downloaded ?? '-';
  document.getElementById('assets-count').textContent = stats.assets_downloaded ?? '-';
  document.getElementById('errors-count').textContent = stats.errors ?? '-';
  document.getElementById('size-count').textContent =
    stats.total_size_mb != null ? stats.total_size_mb.toFixed(2) : '-';
}

function renderMeta(data) {
  const meta = data.metadata || {};
  document.getElementById('meta-url').textContent = meta.url ?? '-';
  document.getElementById('meta-domain').textContent = meta.domain ?? '-';
  document.getElementById('meta-cloned-at').textContent = meta.cloned_at ?? '-';
  document.getElementById('meta-duration').textContent =
    meta.duration_seconds != null ? meta.duration_seconds.toFixed(2) + ' 秒' : '-';
  document.getElementById('meta-tool').textContent = meta.tool ?? '-';
}

function renderErrors(errors, page) {
  const tbody = document.getElementById('errors-tbody');
  tbody.innerHTML = '';
  if (!errors.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="loading">無錯誤記錄</td></tr>';
    return;
  }
  const start = (page - 1) * PAGE_SIZE;
  const slice = errors.slice(start, start + PAGE_SIZE);
  slice.forEach((err, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${start + idx + 1}</td>
      <td style="word-break:break-all;max-width:400px;">${err.url ?? ''}</td>
      <td>${err.error ?? ''}</td>
      <td>${err.timestamp ?? ''}</td>
    `;
    tbody.appendChild(tr);
  });
  renderPagination(errors.length, page);
}

function renderPagination(total, page) {
  const container = document.getElementById('pagination');
  const totalPages = Math.ceil(total / PAGE_SIZE);
  container.innerHTML = '';
  if (totalPages <= 1) return;

  const prev = document.createElement('button');
  prev.textContent = '上一頁';
  prev.disabled = page === 1;
  prev.onclick = () => { currentPage--; renderErrors(filteredErrors, currentPage); };

  const info = document.createElement('span');
  info.textContent = ` 第 ${page} / ${totalPages} 頁 `;
  info.style.margin = '0 6px';

  const next = document.createElement('button');
  next.textContent = '下一頁';
  next.disabled = page === totalPages;
  next.onclick = () => { currentPage++; renderErrors(filteredErrors, currentPage); };

  container.appendChild(prev);
  container.appendChild(info);
  container.appendChild(next);
}

function applyFilters() {
  const searchVal = document.getElementById('error-search').value.toLowerCase();
  const filterVal = document.getElementById('error-filter').value;
  filteredErrors = allErrors.filter(e => {
    const url = (e.url ?? '').toLowerCase();
    const errMsg = (e.error ?? '');
    const matchSearch = !searchVal || url.includes(searchVal);
    const matchFilter = !filterVal || errMsg.includes(filterVal);
    return matchSearch && matchFilter;
  });
  currentPage = 1;
  renderErrors(filteredErrors, currentPage);
  document.getElementById('error-count-badge').textContent = filteredErrors.length;
}

async function init() {
  // 初始化登入表單
  initLoginForm();
  
  // Try to load scraping_index.json (when hosted as static site)
  let data = await fetchIndexJson();

  // Fallback to Worker API
  if (!data) {
    data = await fetchData();
  }

  if (!data) {
    document.getElementById('errors-tbody').innerHTML =
      '<tr><td colspan="4" class="loading">無法載入數據</td></tr>';
    return;
  }

  renderStats(data);
  renderMeta(data);

  allErrors = data.errors ?? [];
  filteredErrors = allErrors;
  document.getElementById('error-count-badge').textContent = allErrors.length;
  renderErrors(filteredErrors, currentPage);

  document.getElementById('error-search').addEventListener('input', applyFilters);
  document.getElementById('error-filter').addEventListener('change', applyFilters);
}

function initLoginForm() {
  // 載入已儲存的驗證資訊
  const authConfig = loadAuthConfig();
  if (authConfig.cookie) {
    document.getElementById('cookie-input').value = authConfig.cookie;
  }
  if (authConfig.token) {
    document.getElementById('token-input').value = authConfig.token;
  }
  
  // 表單提交：儲存驗證資訊
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const cookie = document.getElementById('cookie-input').value.trim();
      const token = document.getElementById('token-input').value.trim();
      
      if (!cookie && !token) {
        const statusEl = document.getElementById('auth-status');
        statusEl.className = 'status-message warning';
        statusEl.textContent = '⚠️ 請至少輸入 Cookie 或 Bearer Token';
        return;
      }
      
      const saved = saveAuthConfig(cookie, token);
      const statusEl = document.getElementById('auth-status');
      
      if (saved) {
        statusEl.className = 'status-message success';
        statusEl.textContent = '✅ 驗證資訊已儲存！下次爬蟲時將使用此資訊。';
      } else {
        statusEl.className = 'status-message error';
        statusEl.textContent = '❌ 儲存失敗，請檢查瀏覽器設定。';
      }
    });
  }
  
  // 測試連線按鈕
  const testBtn = document.getElementById('test-auth-btn');
  if (testBtn) {
    testBtn.addEventListener('click', testAuthConnection);
  }
}

document.addEventListener('DOMContentLoaded', init);
