// Gare Scraper Dashboard - Frontend JS

const PAGE_SIZE = 50;
let allErrors = [];
let filteredErrors = [];
let currentPage = 1;

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

document.addEventListener('DOMContentLoaded', init);
