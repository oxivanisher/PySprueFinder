(() => {
  const input = document.getElementById('search-input');
  const resultsDiv = document.getElementById('search-results');
  const noResults = document.getElementById('no-results');
  const placeholder = document.getElementById('search-placeholder');
  let debounceTimer = null;
  let selectTimer = null;

  // Called by number chip buttons in the catalog section
  window.quickSearch = async function(q) {
    input.value = q;
    input.focus();
    await fetchResults(q);
    resultsDiv.firstElementChild?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    clearTimeout(selectTimer);
    const q = input.value.trim();
    if (!q) {
      resultsDiv.innerHTML = '';
      noResults.classList.add('hidden');
      placeholder && placeholder.classList.remove('hidden');
      return;
    }
    placeholder && placeholder.classList.add('hidden');
    debounceTimer = setTimeout(() => fetchResults(q), 300);
    selectTimer = setTimeout(() => input.select(), 2000);
  });

  async function fetchResults(q) {
    try {
      const res = await fetch(`/api/projects/${PROJECT_ID}/search?q=${encodeURIComponent(q)}`);
      if (!res.ok) return;
      const data = await res.json();
      renderResults(data);
      resultsDiv.firstElementChild?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) {
      console.error('Search error:', e);
    }
  }

  function renderResults(results) {
    resultsDiv.innerHTML = '';
    if (!results.length) {
      noResults.classList.remove('hidden');
      return;
    }
    noResults.classList.add('hidden');

    for (const result of results) {
      const card = document.createElement('div');
      card.className = 'bg-white rounded-xl shadow p-4';

      const header = document.createElement('div');
      header.className = 'flex items-center justify-between mb-3';
      header.innerHTML = `
        <h3 class="font-semibold text-slate-800 text-lg">
          Sprue ${escHtml(result.sprue_letter)}
          ${result.sprue_name ? `<span class="font-normal text-slate-500 text-base">— ${escHtml(result.sprue_name)}</span>` : ''}
        </h3>
        <span class="text-sm text-slate-500">${result.locations.length} location(s)</span>
      `;
      card.appendChild(header);

      const wrapper = document.createElement('div');
      wrapper.style.position = 'relative';
      wrapper.style.display = 'inline-block';
      wrapper.style.width = '100%';

      const img = document.createElement('img');
      img.src = `/uploads/${result.image_filename}`;
      img.style.display = 'block';
      img.style.width = '100%';
      img.alt = `Sprue ${result.sprue_letter}`;
      img.className = 'rounded';
      wrapper.appendChild(img);

      // With a display crop, the wrapper becomes a window onto the crop area:
      // the full photo is scaled up and shifted so the crop fills the width.
      const crop = result.crop || { x: 0, y: 0, width: 1, height: 1 };
      if (result.crop) {
        wrapper.style.overflow = 'hidden';
        wrapper.className = 'rounded';
        img.className = '';
        img.style.position = 'absolute';
        img.style.maxWidth = 'none';
        img.style.width = `${100 / crop.width}%`;
        img.style.height = `${100 / crop.height}%`;
        img.style.left = `${-crop.x / crop.width * 100}%`;
        img.style.top = `${-crop.y / crop.height * 100}%`;
        const setAspect = () => {
          wrapper.style.aspectRatio = `${crop.width * img.naturalWidth} / ${crop.height * img.naturalHeight}`;
        };
        if (img.complete && img.naturalWidth) setAspect();
        else img.addEventListener('load', setAspect);
      }

      for (const loc of result.locations) {
        const box = document.createElement('div');
        box.className = 'highlight-box';
        const top = (loc.y - crop.y) / crop.height;
        box.style.left = `${(loc.x - crop.x) / crop.width * 100}%`;
        box.style.top = `${top * 100}%`;
        box.style.width = `${loc.width / crop.width * 100}%`;
        box.style.height = `${loc.height / crop.height * 100}%`;
        // Label above the box, or below it when the box is at the top edge
        // (a cropped wrapper clips anything outside it).
        const labelPos = result.crop && top < 0.06 ? 'top: 100%; margin-top: 2px;' : 'top: -20px;';
        const label = document.createElement('span');
        label.style.cssText = `
          position: absolute;
          ${labelPos}
          left: 0;
          background: #ef4444;
          color: white;
          font-size: 11px;
          font-weight: bold;
          padding: 1px 4px;
          border-radius: 2px;
          white-space: nowrap;
        `;
        label.textContent = loc.number;
        box.appendChild(label);
        wrapper.appendChild(box);
      }

      card.appendChild(wrapper);
      resultsDiv.appendChild(card);
    }
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
})();
