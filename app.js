(() => {
  const target = document.querySelector('[data-app-shell]');
  if (!target) return;
  const active = document.documentElement.dataset.page || '';
  // The catalogue is usually served statically on :8000, while review and
  // playlist management use the small profile-aware local API on :8766/8765.
  // Send those navigation routes to their local services when browsing the
  // static catalogue.
  const staticLocal = ['127.0.0.1', 'localhost'].includes(location.hostname) && location.port === '8000';
  const playlistHref = staticLocal
    ? 'http://127.0.0.1:8766/playlists.html'
    : 'playlists.html';
  const reviewHref = staticLocal
    ? 'http://127.0.0.1:8765/review.html'
    : 'review.html';
  const pages = [
    ['library', 'Library', 'viewer.html'],
    ['quick-crate', 'Quick crate', 'quick-crate.html'],
    ['review', 'Review', reviewHref],
    ['playlists', 'Playlists', playlistHref],
    ['scout', 'Scout', 'taste-profile.html'],
  ];
  const links = pages.map(([id, label, href]) =>
    `<a href="${href}" ${id === active ? 'aria-current="page"' : ''}>${label}</a>`
  ).join('');
  target.className = 'app-shell';
  target.innerHTML = `
    <a class="app-brand" href="viewer.html" aria-label="Cue Crate library">
      <span class="brand-mark" aria-hidden="true">◒</span><span>Cue Crate</span>
    </a>
    <nav class="app-nav" aria-label="Primary navigation">${links}</nav>
    <div class="app-utility">Local collection</div>
  `;
})();
