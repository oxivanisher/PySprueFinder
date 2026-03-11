(() => {
  const canvas = document.getElementById('overlay-canvas');
  const ctx = canvas.getContext('2d');
  const img = document.getElementById('sprue-img');

  let locations = INITIAL_LOCATIONS.map(l => ({ ...l }));
  let mode = 'select';
  let selectedId = null;

  let isDrawing = false;
  let dragStart = null;
  let dragCurrent = null;
  let pendingBox = null;

  // ── Canvas sync ──────────────────────────────────────────────────────────

  function syncCanvas() {
    canvas.width = img.naturalWidth || img.offsetWidth;
    canvas.height = img.naturalHeight || img.offsetHeight;
    draw();
  }

  img.addEventListener('load', syncCanvas);
  if (img.complete) syncCanvas();

  // ── Drawing ──────────────────────────────────────────────────────────────

  function toCanvas(relX, relY) {
    return [relX * canvas.width, relY * canvas.height];
  }

  function toRel(cx, cy) {
    return [cx / canvas.width, cy / canvas.height];
  }

  function getEventPos(e) {
    const rect = canvas.getBoundingClientRect();
    const sx = canvas.width / rect.width;
    const sy = canvas.height / rect.height;
    const cx = e.touches ? e.touches[0].clientX : e.clientX;
    const cy = e.touches ? e.touches[0].clientY : e.clientY;
    return [(cx - rect.left) * sx, (cy - rect.top) * sy];
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const loc of locations) {
      const [x, y] = toCanvas(loc.x, loc.y);
      const w = loc.width * canvas.width;
      const h = loc.height * canvas.height;
      const sel = loc.id === selectedId;

      ctx.strokeStyle = sel ? '#f59e0b' : '#22c55e';
      ctx.lineWidth = sel ? 3 : 2;
      ctx.strokeRect(x, y, w, h);

      const label = String(loc.number);
      ctx.font = 'bold 14px monospace';
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = sel ? '#f59e0b' : '#22c55e';
      ctx.fillRect(x, y - 18, tw + 6, 18);
      ctx.fillStyle = '#fff';
      ctx.fillText(label, x + 3, y - 4);
    }

    if (isDrawing && dragStart && dragCurrent) {
      const [x1, y1] = dragStart, [x2, y2] = dragCurrent;
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 3]);
      ctx.strokeRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
      ctx.setLineDash([]);
    }
  }

  // ── Number list ──────────────────────────────────────────────────────────

  function refreshNumberList() {
    const container = document.getElementById('number-list');
    const empty = document.getElementById('number-list-empty');
    const count = document.getElementById('number-count');
    if (!container) return;

    // Group by number value
    const byNum = {};
    for (const loc of locations) {
      (byNum[loc.number] = byNum[loc.number] || []).push(loc.id);
    }
    const sorted = Object.keys(byNum).map(Number).sort((a, b) => a - b);

    container.innerHTML = '';
    if (sorted.length === 0) {
      empty && empty.classList.remove('hidden');
    } else {
      empty && empty.classList.add('hidden');
      for (const num of sorted) {
        const ids = byNum[num];
        const btn = document.createElement('button');
        btn.textContent = ids.length > 1 ? `${num} ×${ids.length}` : String(num);
        btn.dataset.num = num;
        btn.className = num === (locations.find(l => l.id === selectedId) || {}).number
          ? 'px-2 py-0.5 text-xs font-mono font-semibold rounded bg-amber-400 text-white'
          : 'px-2 py-0.5 text-xs font-mono font-semibold rounded bg-green-100 text-green-800 hover:bg-amber-400 hover:text-white transition-colors';
        btn.addEventListener('click', () => selectByNumber(num));
        container.appendChild(btn);
      }
    }

    if (count) count.textContent = locations.length;
  }

  function selectByNumber(num) {
    const loc = locations.find(l => l.number === num);
    if (!loc) return;
    selectedId = loc.id;
    document.getElementById('panel-info').classList.add('hidden');
    document.getElementById('panel-edit').classList.remove('hidden');
    document.getElementById('edit-number').value = loc.number;
    draw();
    refreshNumberList();
  }

  // ── Mode ─────────────────────────────────────────────────────────────────

  function setMode(m) {
    mode = m;
    selectedId = null;
    pendingBox = null;
    isDrawing = false;
    dragStart = null;
    dragCurrent = null;

    const active = 'px-3 py-1.5 text-sm rounded-lg bg-amber-500 text-white font-semibold';
    const inactive = 'px-3 py-1.5 text-sm rounded-lg bg-slate-200 text-slate-700 font-semibold hover:bg-slate-300';
    document.getElementById('btn-select').className = m === 'select' ? active : inactive;
    document.getElementById('btn-add').className = m === 'add' ? active : inactive;

    document.getElementById('panel-info').classList.toggle('hidden', m !== 'select');
    document.getElementById('panel-edit').classList.add('hidden');
    document.getElementById('panel-add').classList.toggle('hidden', m !== 'add');
    canvas.className = `absolute inset-0 w-full h-full mode-${m}`;
    draw();
    refreshNumberList();
  }
  window.setMode = setMode;

  // ── Mouse events ─────────────────────────────────────────────────────────

  canvas.addEventListener('mousedown', e => {
    const [cx, cy] = getEventPos(e);
    if (mode === 'select') {
      let hit = null;
      for (let i = locations.length - 1; i >= 0; i--) {
        const l = locations[i];
        const [bx, by] = toCanvas(l.x, l.y);
        if (cx >= bx && cx <= bx + l.width * canvas.width && cy >= by && cy <= by + l.height * canvas.height) {
          hit = l; break;
        }
      }
      if (hit) {
        selectedId = hit.id;
        document.getElementById('panel-info').classList.add('hidden');
        document.getElementById('panel-edit').classList.remove('hidden');
        document.getElementById('edit-number').value = hit.number;
      } else {
        deselectBox();
      }
      draw();
      refreshNumberList();
    } else if (mode === 'add') {
      isDrawing = true;
      dragStart = dragCurrent = [cx, cy];
    }
  });

  canvas.addEventListener('mousemove', e => {
    if (!isDrawing) return;
    dragCurrent = getEventPos(e);
    draw();
  });

  canvas.addEventListener('mouseup', e => {
    if (mode !== 'add' || !isDrawing) return;
    isDrawing = false;
    const [x1, y1] = dragStart, [x2, y2] = dragCurrent;
    const x = Math.min(x1, x2), y = Math.min(y1, y2);
    const w = Math.abs(x2 - x1), h = Math.abs(y2 - y1);
    if (w < 5 || h < 5) { pendingBox = null; draw(); return; }
    const [rx, ry] = toRel(x, y);
    pendingBox = { x: rx, y: ry, width: w / canvas.width, height: h / canvas.height };
    document.getElementById('panel-add').classList.remove('hidden');
    document.getElementById('add-number').focus();
    draw();
  });

  // ── Actions ──────────────────────────────────────────────────────────────

  function deselectBox() {
    selectedId = null;
    document.getElementById('panel-edit').classList.add('hidden');
    document.getElementById('panel-info').classList.remove('hidden');
    draw();
    refreshNumberList();
  }
  window.deselectBox = deselectBox;

  async function saveEdit() {
    if (!selectedId) return;
    const number = parseInt(document.getElementById('edit-number').value);
    if (!number || number < 1 || number > 999) { alert('Enter a number between 1 and 999.'); return; }
    const res = await fetch(`/api/numbers/${selectedId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ number }),
    });
    if (!res.ok) { alert('Failed to save.'); return; }
    const updated = await res.json();
    const idx = locations.findIndex(l => l.id === selectedId);
    if (idx >= 0) locations[idx] = updated;
    deselectBox();
    refreshNumberList();
  }
  window.saveEdit = saveEdit;

  async function deleteSelected() {
    if (!selectedId) return;
    if (!confirm('Delete this number location?')) return;
    const res = await fetch(`/api/numbers/${selectedId}`, { method: 'DELETE' });
    if (!res.ok) { alert('Failed to delete.'); return; }
    locations = locations.filter(l => l.id !== selectedId);
    deselectBox();
    refreshNumberList();
  }
  window.deleteSelected = deleteSelected;

  async function saveNewBox() {
    if (!pendingBox) { alert('Draw a box on the image first.'); return; }
    const number = parseInt(document.getElementById('add-number').value);
    if (!number || number < 1 || number > 999) { alert('Enter a number between 1 and 999.'); return; }
    const res = await fetch(`/api/sprues/${SPRUE_ID}/numbers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ number, ...pendingBox, confidence: 100 }),
    });
    if (!res.ok) { alert('Failed to save.'); return; }
    locations.push(await res.json());
    pendingBox = null;
    document.getElementById('add-number').value = '';
    draw();
    refreshNumberList();
  }
  window.saveNewBox = saveNewBox;

  // ── OCR preview ──────────────────────────────────────────────────────────

  async function loadPreview() {
    const profile = document.getElementById('preview-profile').value;
    const container = document.getElementById('preview-container');
    const loading = document.getElementById('preview-loading');
    container.classList.add('hidden');
    loading.classList.remove('hidden');
    // Cache-bust so switching profiles always reloads
    document.getElementById('preview-img').src =
      `/api/sprues/${SPRUE_ID}/ocr-preview?profile=${profile}&t=${Date.now()}`;
    document.getElementById('preview-img').onload = () => {
      loading.classList.add('hidden');
      container.classList.remove('hidden');
    };
    document.getElementById('preview-img').onerror = () => {
      loading.textContent = 'Failed to load preview.';
    };
  }
  window.loadPreview = loadPreview;

  async function rerunOcr() {
    const profile = document.getElementById('preview-profile').value;
    if (!confirm(`Re-run OCR with profile "${profile}"? This replaces all existing detections.`)) return;
    const btn = document.getElementById('btn-rerun');
    btn.textContent = 'Running…';
    btn.disabled = true;
    const res = await fetch(`/api/sprues/${SPRUE_ID}/reprocess?profile=${profile}`, { method: 'POST' });
    if (!res.ok) {
      alert('OCR failed.');
      btn.textContent = 'Apply Profile & Re-run OCR';
      btn.disabled = false;
      return;
    }
    const data = await res.json();
    alert(`OCR complete — ${data.count} number(s) detected with profile "${data.profile}".`);
    window.location.reload();
  }
  window.rerunOcr = rerunOcr;

  // ── Init ─────────────────────────────────────────────────────────────────
  setMode('select');
  refreshNumberList();
})();
