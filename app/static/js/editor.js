(() => {
  const canvas = document.getElementById('overlay-canvas');
  const ctx = canvas.getContext('2d');
  const img = document.getElementById('sprue-img');

  let locations = INITIAL_LOCATIONS.map(l => ({ ...l }));
  let mode = 'select';
  let selectedId = null;
  let showOverlay = true;
  let imgDimmed = false;
  // Tracks which instance index was last selected per number value, for cycling.
  const lastPickedIndex = {};

  let isDrawing = false;
  let dragStart = null;
  let dragCurrent = null;
  let pendingBox = null;

  // Display crop (relative coords). `crop` is what is saved; `pendingCrop` is a
  // box drawn in crop mode that has not been saved yet.
  let crop = INITIAL_CROP;
  let pendingCrop = null;

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
    // Clamped, since drags are tracked on the window and may leave the image.
    const x = Math.min(Math.max((cx - rect.left) * sx, 0), canvas.width);
    const y = Math.min(Math.max((cy - rect.top) * sy, 0), canvas.height);
    return [x, y];
  }

  function dragBoxRel() {
    const [x1, y1] = dragStart, [x2, y2] = dragCurrent;
    const [x, y] = toRel(Math.min(x1, x2), Math.min(y1, y2));
    return { x, y, width: Math.abs(x2 - x1) / canvas.width, height: Math.abs(y2 - y1) / canvas.height };
  }

  function drawCrop() {
    const dragging = mode === 'crop' && isDrawing && dragStart && dragCurrent;
    const box = dragging ? dragBoxRel() : (mode === 'crop' && pendingCrop) || crop;
    if (!box) return;
    // Canvas runs at the photo's native resolution; scale strokes to screen pixels.
    const px = canvas.width / (canvas.getBoundingClientRect().width || canvas.width);
    const [x, y] = toCanvas(box.x, box.y);
    const w = box.width * canvas.width;
    const h = box.height * canvas.height;
    if (mode === 'crop') {
      ctx.fillStyle = 'rgba(15, 23, 42, 0.55)';
      ctx.beginPath();
      ctx.rect(0, 0, canvas.width, canvas.height);
      ctx.rect(x, y, w, h);
      ctx.fill('evenodd');
    }
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 2 * px;
    ctx.setLineDash([8 * px, 6 * px]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!showOverlay) {
      if (mode === 'crop') drawCrop();
      return;
    }

    for (const loc of locations) {
      const [x, y] = toCanvas(loc.x, loc.y);
      const w = loc.width * canvas.width;
      const h = loc.height * canvas.height;
      const sel = loc.id === selectedId;

      const color = sel ? '#f59e0b' : '#22c55e';

      // Box outline
      ctx.strokeStyle = color;
      ctx.lineWidth = sel ? 3 : 2;
      ctx.strokeRect(x, y, w, h);

      // Number fitted inside the box — sized to fill the box height
      const label = String(loc.number);
      let fontSize = h;
      ctx.font = `bold ${fontSize}px monospace`;
      const measuredW = ctx.measureText(label).width;
      if (measuredW > w) fontSize *= w / measuredW;
      ctx.font = `bold ${fontSize}px monospace`;
      ctx.fillStyle = color;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, x + w / 2, y + h / 2);
      ctx.textAlign = 'left';
      ctx.textBaseline = 'alphabetic';
    }

    drawCrop();

    if (mode === 'add' && isDrawing && dragStart && dragCurrent) {
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
    const locs = locations.filter(l => l.number === num);
    if (!locs.length) return;
    // Cycle through all instances of this number on repeated clicks.
    const prev = lastPickedIndex[num] ?? -1;
    const next = (prev + 1) % locs.length;
    lastPickedIndex[num] = next;
    const loc = locs[next];
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
    document.getElementById('btn-crop').className = m === 'crop' ? active : inactive;

    document.getElementById('panel-info').classList.toggle('hidden', m !== 'select');
    document.getElementById('panel-edit').classList.add('hidden');
    document.getElementById('panel-add').classList.toggle('hidden', m !== 'add');
    document.getElementById('panel-crop').classList.toggle('hidden', m !== 'crop');
    pendingCrop = null;
    setCropStatus(crop ? 'A crop is saved (dashed outline).' : 'No crop saved; search shows the whole photo.');
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
    } else if (mode === 'add' || mode === 'crop') {
      isDrawing = true;
      dragStart = dragCurrent = [cx, cy];
    }
  });

  // Tracked on the window so a drag that ends outside the image still completes.
  window.addEventListener('mousemove', e => {
    if (!isDrawing) return;
    dragCurrent = getEventPos(e);
    draw();
  });

  window.addEventListener('mouseup', () => {
    if (!isDrawing) return;
    isDrawing = false;
    const box = dragBoxRel();
    if (box.width * canvas.width < 5 || box.height * canvas.height < 5) { pendingBox = null; draw(); return; }
    if (mode === 'crop') {
      pendingCrop = box;
      setCropStatus('Not saved yet.');
      draw();
      return;
    }
    pendingBox = box;
    document.getElementById('panel-add').classList.remove('hidden');
    document.getElementById('add-number').focus();
    draw();
  });

  // ── Actions ──────────────────────────────────────────────────────────────

  function deselectBox() {
    selectedId = null;
    // Reset cycle index for all numbers so next click starts at first instance.
    for (const k in lastPickedIndex) delete lastPickedIndex[k];
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

  // ── Crop ─────────────────────────────────────────────────────────────────

  function setCropStatus(text, isError = false) {
    const el = document.getElementById('crop-status');
    el.textContent = text;
    el.className = `text-xs mt-2 ${isError ? 'text-red-600 font-semibold' : 'text-slate-500'}`;
  }

  async function patchCrop(box) {
    const res = await fetch(`/api/sprues/${SPRUE_ID}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crop: box }),
    });
    if (!res.ok) { setCropStatus(`Failed to save crop (HTTP ${res.status}).`, true); return false; }
    return true;
  }

  async function saveCrop() {
    if (!pendingCrop) { setCropStatus('Drag a box on the image first.', true); return; }
    const round = v => Math.round(v * 10000) / 10000;
    const box = {
      x: round(pendingCrop.x), y: round(pendingCrop.y),
      width: round(pendingCrop.width), height: round(pendingCrop.height),
    };
    if (!await patchCrop(box)) return;
    crop = box;
    pendingCrop = null;
    setCropStatus('Crop saved.');
    draw();
  }
  window.saveCrop = saveCrop;

  async function removeCrop() {
    if (!await patchCrop(null)) return;
    crop = null;
    pendingCrop = null;
    setCropStatus('Crop removed; search shows the whole photo.');
    draw();
  }
  window.removeCrop = removeCrop;

  // Suggest a crop: the bounding box of all detected numbers plus a margin, since
  // the labels sit on the frame and the sprue edge is just outside them.
  function fitCropToNumbers() {
    if (!locations.length) { setCropStatus('No numbers detected to fit to.', true); return; }
    const margin = 0.03;
    const x1 = Math.max(0, Math.min(...locations.map(l => l.x)) - margin);
    const y1 = Math.max(0, Math.min(...locations.map(l => l.y)) - margin);
    const x2 = Math.min(1, Math.max(...locations.map(l => l.x + l.width)) + margin);
    const y2 = Math.min(1, Math.max(...locations.map(l => l.y + l.height)) + margin);
    pendingCrop = { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
    setCropStatus('Suggested from the detected numbers. Not saved yet.');
    draw();
  }
  window.fitCropToNumbers = fitCropToNumbers;

  // ── OCR preview ──────────────────────────────────────────────────────────

  // OCR takes 10–30 s; show a live elapsed timer in the panel and over the
  // image, and lock both OCR buttons so a second click can't queue another run.
  function startOcrBusy(label) {
    const status = document.getElementById('ocr-status');
    const statusText = document.getElementById('ocr-status-text');
    const spinner = document.getElementById('ocr-status-spinner');
    const overlay = document.getElementById('ocr-overlay');
    const overlayText = document.getElementById('ocr-overlay-text');
    const buttons = [document.getElementById('btn-preview'), document.getElementById('btn-rerun')];

    const started = Date.now();
    const render = () => {
      const text = `${label}… ${Math.round((Date.now() - started) / 1000)} s`;
      statusText.textContent = text;
      overlayText.textContent = text;
    };
    render();
    const timer = setInterval(render, 1000);
    status.className = 'flex items-center gap-2 text-xs font-semibold text-amber-700 bg-amber-50 rounded-lg px-3 py-2 mb-2';
    spinner.classList.remove('hidden');
    overlay.classList.remove('hidden');
    buttons.forEach(b => { b.disabled = true; });

    return function stop(errorMessage) {
      clearInterval(timer);
      overlay.classList.add('hidden');
      buttons.forEach(b => { b.disabled = false; });
      if (errorMessage) {
        status.className = 'flex items-center gap-2 text-xs font-semibold text-red-700 bg-red-50 rounded-lg px-3 py-2 mb-2';
        spinner.classList.add('hidden');
        statusText.textContent = errorMessage;
      } else {
        status.classList.add('hidden');
      }
    };
  }

  async function errorDetail(res) {
    try {
      const body = await res.json();
      if (body.detail) return `${res.status}: ${body.detail}`;
    } catch (e) { /* not JSON */ }
    return `HTTP ${res.status}`;
  }

  function loadPreview() {
    const container = document.getElementById('preview-container');
    const previewImg = document.getElementById('preview-img');
    container.classList.add('hidden');
    const stop = startOcrBusy('Finding candidates');
    previewImg.onload = () => {
      stop();
      container.classList.remove('hidden');
    };
    previewImg.onerror = () => stop('Failed to load preview.');
    // Cache-bust so a repeated click re-runs OCR
    previewImg.src = `/api/sprues/${SPRUE_ID}/ocr-preview?t=${Date.now()}`;
  }
  window.loadPreview = loadPreview;

  async function rerunOcr() {
    if (!confirm('Re-run OCR? This replaces all existing detections, including manual edits.')) return;
    const stop = startOcrBusy('Running OCR');
    let res;
    try {
      res = await fetch(`/api/sprues/${SPRUE_ID}/reprocess`, { method: 'POST' });
    } catch (e) {
      stop(`OCR failed: ${e.message}`);
      return;
    }
    if (!res.ok) {
      stop(`OCR failed (${await errorDetail(res)}).`);
      return;
    }
    // Keep the overlay up through the reload; the new count shows in "Detected Numbers".
    window.location.reload();
  }
  window.rerunOcr = rerunOcr;

  // ── Overlay toggle ───────────────────────────────────────────────────────
  function toggleOverlay() {
    showOverlay = !showOverlay;
    const btn = document.getElementById('btn-toggle-overlay');
    btn.textContent = showOverlay ? 'Hide Numbers' : 'Show Numbers';
    btn.className = showOverlay
      ? 'px-3 py-1.5 text-sm rounded-lg bg-slate-200 text-slate-700 font-semibold hover:bg-slate-300'
      : 'px-3 py-1.5 text-sm rounded-lg bg-amber-500 text-white font-semibold hover:bg-amber-600';
    draw();
  }
  window.toggleOverlay = toggleOverlay;

  // ── Dim image ────────────────────────────────────────────────────────────
  function toggleImageDim() {
    imgDimmed = !imgDimmed;
    img.style.filter = imgDimmed ? 'brightness(0.08)' : '';
    const btn = document.getElementById('btn-dim-image');
    btn.textContent = imgDimmed ? 'Brighten Image' : 'Dim Image';
    btn.className = imgDimmed
      ? 'px-3 py-1.5 text-sm rounded-lg bg-amber-500 text-white font-semibold hover:bg-amber-600'
      : 'px-3 py-1.5 text-sm rounded-lg bg-slate-200 text-slate-700 font-semibold hover:bg-slate-300';
  }
  window.toggleImageDim = toggleImageDim;

  // ── Edit names panel ─────────────────────────────────────────────────────
  let namesPanelOpen = false;
  function toggleNamesPanel() {
    namesPanelOpen = !namesPanelOpen;
    document.getElementById('names-panel').classList.toggle('hidden', !namesPanelOpen);
    document.getElementById('names-chevron').textContent = namesPanelOpen ? '▲' : '▼';
    if (namesPanelOpen) {
      document.getElementById('edit-project-name').value = INITIAL_PROJECT_NAME;
      document.getElementById('edit-sprue-letter').value = INITIAL_SPRUE_LETTER;
      document.getElementById('edit-sprue-name').value = INITIAL_SPRUE_NAME;
    }
  }
  window.toggleNamesPanel = toggleNamesPanel;

  async function saveNames() {
    const projectName = document.getElementById('edit-project-name').value.trim();
    const sprueLetter = document.getElementById('edit-sprue-letter').value.trim();
    const sprueName = document.getElementById('edit-sprue-name').value.trim();

    const [r1, r2] = await Promise.all([
      fetch(`/api/projects/${PROJECT_ID}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: projectName || INITIAL_PROJECT_NAME }),
      }),
      fetch(`/api/sprues/${SPRUE_ID}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ letter: sprueLetter || INITIAL_SPRUE_LETTER, name: sprueName }),
      }),
    ]);
    if (!r1.ok || !r2.ok) { alert('Failed to save names.'); return; }
    window.location.reload();
  }
  window.saveNames = saveNames;

  // ── Keyboard shortcuts ───────────────────────────────────────────────────
  document.getElementById('edit-number').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); saveEdit(); }
  });
  document.getElementById('add-number').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); saveNewBox(); }
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Delete' && e.key !== 'Backspace') return;
    const tag = document.activeElement && document.activeElement.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (selectedId === null) return;
    e.preventDefault();
    deleteSelected();
  });

  // ── Init ─────────────────────────────────────────────────────────────────
  setMode('select');
  refreshNumberList();
})();
