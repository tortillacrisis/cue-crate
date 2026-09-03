(() => {
  const target = document.querySelector('[data-app-shell]');
  if (!target) return;
  const active = document.documentElement.dataset.page || '';
  // Cue Crate serves every desktop screen through one local origin.
  const pages = [
    ['library', 'Library', 'viewer.html'],
    ['quick-crate', 'Quick crate', 'quick-crate.html'],
    ['review', 'Review', 'review.html'],
    ['playlists', 'Playlists', 'playlists.html'],
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
