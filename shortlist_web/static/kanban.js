(() => {
  const graphEl = document.getElementById('kanban-graph');
  if (!graphEl) return;
  const graph = JSON.parse(graphEl.textContent);

  let dragging = null;

  function isAllowed(from, to) {
    if (from === to) return false;
    return (graph[from] || []).includes(to);
  }

  function showToast(html) {
    const t = document.getElementById('toast');
    if (t) t.innerHTML = html;
  }

  function refreshColumn(col) {
    const cards = col.querySelectorAll('.card').length;
    const count = col.querySelector('.count');
    if (count) count.textContent = `(${cards})`;
    const empty = col.querySelector('.empty');
    if (empty) empty.toggleAttribute('hidden', cards > 0);
  }

  function onDragStart(e) {
    const card = e.target.closest('.card');
    if (!card) return;
    dragging = card;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', card.dataset.jobId);
    card.classList.add('dragging');
  }

  function onDragEnd() {
    if (dragging) dragging.classList.remove('dragging');
    document.querySelectorAll('.kanban-col.drop-target').forEach((c) =>
      c.classList.remove('drop-target'),
    );
    dragging = null;
  }

  function onDragOver(e) {
    if (!dragging) return;
    const col = e.currentTarget;
    if (!isAllowed(dragging.dataset.status, col.dataset.status)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    col.classList.add('drop-target');
  }

  function onDragLeave(e) {
    e.currentTarget.classList.remove('drop-target');
  }

  async function onDrop(e) {
    e.preventDefault();
    const col = e.currentTarget;
    col.classList.remove('drop-target');
    if (!dragging) return;
    const from = dragging.dataset.status;
    const to = col.dataset.status;
    if (!isAllowed(from, to)) return;

    const jobId = dragging.dataset.jobId;
    const fromCol = document.querySelector(`.kanban-col[data-status="${from}"]`);

    const fd = new FormData();
    fd.append('status', to);
    let resp;
    try {
      resp = await fetch(`/p/${KANBAN_SLUG}/applications/move/${jobId}`, {
        method: 'POST',
        body: fd,
      });
    } catch (err) {
      showToast(`<div class="error">network error: ${err}</div>`);
      return;
    }
    const text = await resp.text();
    showToast(text);
    if (!resp.ok) return;

    dragging.dataset.status = to;
    col.querySelector('.kanban-cards').appendChild(dragging);
    refreshColumn(col);
    if (fromCol) refreshColumn(fromCol);
  }

  document.querySelectorAll('.card').forEach((card) => {
    card.addEventListener('dragstart', onDragStart);
    card.addEventListener('dragend', onDragEnd);
  });
  document.querySelectorAll('.kanban-col').forEach((col) => {
    col.addEventListener('dragover', onDragOver);
    col.addEventListener('dragleave', onDragLeave);
    col.addEventListener('drop', onDrop);
  });
})();
