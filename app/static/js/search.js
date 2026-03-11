(() => {
  const input = document.getElementById('search-input');
  const resultsDiv = document.getElementById('search-results');
  const noResults = document.getElementById('no-results');
  let debounceTimer = null;

  // Called by number chip buttons in the catalog section
  window.quickSearch = function(q) {
    input.value = q;
    input.focus();
    fetchResults(q);
  };

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (!q) {
      resultsDiv.innerHTML = '';
      noResults.classList.add('hidden');
      return;
    }
    debounceTimer = setTimeout(() => fetchResults(q), 300);
  });

  async function fetchResults(q) {
    try {
      const res = await fetch(`/api/projects/${PROJECT_ID}/search?q=${encodeURIComponent(q)}`);
      if (!res.ok) return;
      const data = await res.json();
      renderResults(data);
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

      for (const loc of result.locations) {
        const box = document.createElement('div');
        box.className = 'highlight-box';
        box.style.left = `${loc.x * 100}%`;
        box.style.top = `${loc.y * 100}%`;
        box.style.width = `${loc.width * 100}%`;
        box.style.height = `${loc.height * 100}%`;
        // Label
        const label = document.createElement('span');
        label.style.cssText = `
          position: absolute;
          top: -20px;
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
