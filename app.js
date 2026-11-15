// Only deliberate same-origin desktop writes receive the in-memory session capability.
// Never retry a mutation automatically: publishing may already have reached a provider.
(() => {
  let sessionPromise;
  window.cueCrateFetch = async (input, options = {}) => {
    const url = new URL(input, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) {
      throw new Error('Cue Crate requests must use this local app origin.');
    }
    const method = String(options.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
      if (!sessionPromise) {
        sessionPromise = fetch('/api/session', {cache: 'no-store'}).then(async response => {
          if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
            throw new Error('Could not open a local session. Restart the Cue Crate server and reload.');
          }
          const session = await response.json();
          if (!session.csrf_token) throw new Error('Local session unavailable. Reload Cue Crate.');
          return session.csrf_token;
        }).catch(error => { sessionPromise = null; throw error; });
      }
      const headers = new Headers(options.headers || {});
      headers.set('X-Cue-Crate-CSRF', await sessionPromise);
      options = {...options, headers};
    }
    const response = await fetch(url, {...options, credentials: 'same-origin'});
    if (response.status === 403) sessionPromise = null;
    return response;
  };
})();

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
