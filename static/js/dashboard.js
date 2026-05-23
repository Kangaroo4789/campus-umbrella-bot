/* =====================================================================
   dashboard.js — 圖表、平面地圖、即時輪詢
   ===================================================================== */

let stationBarChart = null;
let userPieChart    = null;
let creditPieChart  = null;
let dragTarget      = null;
let mapMode         = 'view'; // 'view' | 'edit'

/* ----- 顏色工具 ----- */
const STATUS_COLORS = {
  idle:        '#27ae60',
  borrowing:   '#2980b9',
  unregistered:'#95a5a6',
  wait_name:   '#f39c12',
  wait_department:'#f39c12',
  wait_id_card:'#f39c12',
  wait_borrow_station:'#e67e22',
  wait_borrow_aruco:  '#e67e22',
  wait_return_station:'#8e44ad',
  wait_return_aruco:  '#8e44ad',
  wait_return_yolo:   '#8e44ad',
  wait_repair_station:'#c0392b',
  wait_repair_photo:  '#c0392b',
};

function inventoryColor(count, max) {
  const ratio = max > 0 ? count / max : 0;
  if (ratio > 0.5) return '#27ae60';
  if (ratio > 0.2) return '#f39c12';
  if (count > 0)   return '#e67e22';
  return '#e74c3c';
}

/* ----- 即時輪詢 ----- */
async function fetchStats() {
  try {
    const r = await fetch('/api/stats');
    if (!r.ok) return;
    const data = await r.json();
    updateStatCards(data);
    updateCharts(data);
  } catch(e) { console.warn('stats fetch failed', e); }
}

async function fetchStations() {
  try {
    const r = await fetch('/api/stations');
    if (!r.ok) return;
    const stations = await r.json();
    renderMap(stations);
    updateStationTable(stations);
  } catch(e) { console.warn('stations fetch failed', e); }
}

function refreshAll() { fetchStats(); fetchStations(); }

/* ----- Stats Cards ----- */
function updateStatCards(d) {
  setText('card-borrowing',    d.borrowing_count);
  setText('card-available',    d.total_available);
  setText('card-low-credit',   d.low_credit_count);
  setText('card-repairs',      d.pending_repairs);
  setText('card-users',        d.total_users);
  setText('card-verified',     d.verified_users);
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

/* ----- Chart.js 初始化 ----- */
function initCharts(initData) {
  const barCtx  = document.getElementById('chartStationBar');
  const pieCtx  = document.getElementById('chartUserPie');
  const credCtx = document.getElementById('chartCreditPie');

  if (barCtx) {
    stationBarChart = new Chart(barCtx, {
      type: 'bar',
      data: { labels: [], datasets: [{
        label: '可用雨傘數',
        data: [],
        backgroundColor: [],
        borderRadius: 6,
      }]},
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { color: '#f0f0f0' } },
          x: { grid: { display: false } }
        }
      }
    });
  }

  if (pieCtx) {
    userPieChart = new Chart(pieCtx, {
      type: 'doughnut',
      data: { labels: ['閒置', '借用中', '未完成註冊', '其他'], datasets: [{
        data: [0,0,0,0],
        backgroundColor: ['#27ae60','#2980b9','#95a5a6','#f39c12'],
        borderWidth: 2, borderColor: '#fff'
      }]},
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' } }
      }
    });
  }

  if (credCtx) {
    creditPieChart = new Chart(credCtx, {
      type: 'doughnut',
      data: { labels: ['高信用(80+)', '中信用(60-79)', '低信用(<60)'], datasets: [{
        data: [0,0,0],
        backgroundColor: ['#27ae60','#f39c12','#e74c3c'],
        borderWidth: 2, borderColor: '#fff'
      }]},
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' } }
      }
    });
  }

  if (initData) updateCharts(initData);
}

function updateCharts(d) {
  if (stationBarChart && d.stations) {
    stationBarChart.data.labels = d.stations.map(s => s.name);
    stationBarChart.data.datasets[0].data = d.stations.map(s => s.umbrella_count);
    stationBarChart.data.datasets[0].backgroundColor = d.stations.map(s =>
      inventoryColor(s.umbrella_count, s.max_capacity || 10)
    );
    stationBarChart.update('none');
  }

  if (userPieChart && d.user_status) {
    const us = d.user_status;
    userPieChart.data.datasets[0].data = [
      us.idle || 0, us.borrowing || 0, us.unregistered || 0, us.other || 0
    ];
    userPieChart.update('none');
  }

  if (creditPieChart && d.credit_dist) {
    const cd = d.credit_dist;
    creditPieChart.data.datasets[0].data = [cd.high||0, cd.mid||0, cd.low||0];
    creditPieChart.update('none');
  }
}

/* ----- 平面地圖 ----- */
function renderMap(stations) {
  const container = document.getElementById('map-container');
  if (!container) return;

  // 保留既有 marker 位置避免閃爍，僅更新數字與顏色
  stations.forEach(s => {
    let marker = document.getElementById('marker-' + s.id);
    if (!marker) {
      marker = createMarker(s);
      container.appendChild(marker);
    } else {
      updateMarkerStyle(marker, s);
    }
  });

  // 移除已刪除的站點 marker
  container.querySelectorAll('.station-marker').forEach(el => {
    const id = parseInt(el.dataset.stationId);
    if (!stations.find(s => s.id === id)) el.remove();
  });
}

function createMarker(s) {
  const marker = document.createElement('div');
  marker.className = 'station-marker';
  marker.id = 'marker-' + s.id;
  marker.dataset.stationId = s.id;
  marker.style.left = (s.map_x || 50) + '%';
  marker.style.top  = (s.map_y || 50) + '%';

  updateMarkerStyle(marker, s);

  marker.addEventListener('click', () => {
    if (mapMode === 'edit') return;
    openStationModal(s.id);
  });

  // 拖曳（編輯模式）
  marker.addEventListener('mousedown', e => {
    if (mapMode !== 'edit') return;
    e.preventDefault();
    dragTarget = marker;
  });

  return marker;
}

function updateMarkerStyle(marker, s) {
  const color = inventoryColor(s.umbrella_count, s.max_capacity || 10);
  const active = s.is_active;
  marker.innerHTML = `
    <div class="marker-dot" style="background:${active ? color : '#bdc3c7'}">
      <i class="bi bi-umbrella-fill"></i>
    </div>
    <div class="marker-label">${s.name}<br><span style="color:${color}">${s.umbrella_count}把</span></div>
  `;
  marker.style.opacity = active ? '1' : '0.5';
  marker.dataset.stationData = JSON.stringify(s);
}

// 拖曳事件
document.addEventListener('mousemove', e => {
  if (!dragTarget) return;
  const container = document.getElementById('map-container');
  const rect = container.getBoundingClientRect();
  const x = Math.min(Math.max((e.clientX - rect.left) / rect.width * 100, 3), 97);
  const y = Math.min(Math.max((e.clientY - rect.top)  / rect.height * 100, 3), 97);
  dragTarget.style.left = x + '%';
  dragTarget.style.top  = y + '%';
});

document.addEventListener('mouseup', async () => {
  if (!dragTarget) return;
  const id = dragTarget.dataset.stationId;
  const x  = parseFloat(dragTarget.style.left);
  const y  = parseFloat(dragTarget.style.top);
  dragTarget = null;

  try {
    await fetch('/admin/stations/position', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({id, map_x: x, map_y: y})
    });
  } catch(e) { console.warn('position save failed', e); }
});

/* ----- 編輯模式切換 ----- */
function toggleMapMode() {
  mapMode = mapMode === 'view' ? 'edit' : 'view';
  const btn = document.getElementById('btn-map-mode');
  const hint = document.getElementById('map-mode-hint');
  if (mapMode === 'edit') {
    btn.className = 'btn btn-warning btn-sm';
    btn.innerHTML = '<i class="bi bi-check-lg me-1"></i>完成編輯';
    if (hint) hint.style.display = 'block';
    document.querySelectorAll('.station-marker').forEach(m => m.style.cursor = 'move');
  } else {
    btn.className = 'btn btn-outline-secondary btn-sm';
    btn.innerHTML = '<i class="bi bi-arrows-move me-1"></i>調整位置';
    if (hint) hint.style.display = 'none';
    document.querySelectorAll('.station-marker').forEach(m => m.style.cursor = 'pointer');
  }
}

/* ----- 站點 Modal ----- */
function openStationModal(stationId) {
  const marker = document.getElementById('marker-' + stationId);
  if (!marker) return;
  const s = JSON.parse(marker.dataset.stationData);

  document.getElementById('modal-station-name').textContent   = s.name;
  document.getElementById('modal-station-count').textContent  = s.umbrella_count + ' 把';
  document.getElementById('modal-station-max').textContent    = s.max_capacity || 10;
  document.getElementById('modal-station-status').textContent = s.is_active ? '營運中' : '已停用';
  document.getElementById('modal-edit-id').value              = s.id;

  document.getElementById('adj-station-id').value = s.id;

  const modal = new bootstrap.Modal(document.getElementById('stationDetailModal'));
  modal.show();
}

function openAddModal() {
  document.getElementById('add-station-form').reset();
  const modal = new bootstrap.Modal(document.getElementById('addStationModal'));
  modal.show();
}

function openEditModal() {
  const id = document.getElementById('modal-edit-id').value;
  const marker = document.getElementById('marker-' + id);
  if (!marker) return;
  const s = JSON.parse(marker.dataset.stationData);

  document.getElementById('edit-id').value            = s.id;
  document.getElementById('edit-name').value          = s.name;
  document.getElementById('edit-max').value           = s.max_capacity || 10;
  document.getElementById('edit-active').checked      = !!s.is_active;

  bootstrap.Modal.getInstance(document.getElementById('stationDetailModal')).hide();
  setTimeout(() => {
    const modal = new bootstrap.Modal(document.getElementById('editStationModal'));
    modal.show();
  }, 300);
}

/* ----- 站點資料表更新 ----- */
function updateStationTable(stations) {
  const tbody = document.getElementById('station-tbody');
  if (!tbody) return;
  tbody.innerHTML = stations.map(s => {
    const color = inventoryColor(s.umbrella_count, s.max_capacity || 10);
    const ratio = s.max_capacity > 0 ? Math.round(s.umbrella_count / s.max_capacity * 100) : 0;
    return `
    <tr>
      <td><span class="fw-semibold">${s.name}</span> ${!s.is_active ? '<span class="badge bg-secondary ms-1">停用</span>':''}</td>
      <td>
        <div class="d-flex align-items-center gap-2">
          <span class="fw-bold" style="color:${color}">${s.umbrella_count}</span>
          <div class="progress flex-grow-1" style="height:8px">
            <div class="progress-bar" style="width:${ratio}%;background:${color}"></div>
          </div>
          <small class="text-muted">${s.max_capacity||10}</small>
        </div>
      </td>
      <td><span class="badge" style="background:${color}">${
        s.umbrella_count === 0 ? '缺傘' : ratio > 50 ? '充足' : '偏少'
      }</span></td>
      <td>
        <button class="btn btn-sm btn-outline-primary" onclick="openStationModal(${s.id})">
          <i class="bi bi-pencil"></i>
        </button>
      </td>
    </tr>`;
  }).join('');
}

/* ----- 啟動 ----- */
document.addEventListener('DOMContentLoaded', () => {
  initCharts(window.INIT_DATA || null);
  refreshAll();
  setInterval(refreshAll, 30000);
});
