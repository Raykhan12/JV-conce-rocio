document.addEventListener('DOMContentLoaded', () => {
  const header = document.querySelector('[data-site-header]');
  const toggle = document.querySelector('[data-menu-toggle]');
  const nav = document.querySelector('[data-menu]');

  const setScrolled = () => header?.classList.toggle('is-scrolled', window.scrollY > 12);
  setScrolled();
  window.addEventListener('scroll', setScrolled, { passive: true });

  document.querySelectorAll('[data-news-image]').forEach((image) => {
    const hideBrokenImage = () => image.classList.add('is-unavailable');
    image.addEventListener('error', hideBrokenImage, { once: true });
    if (image.complete && image.naturalWidth === 0) hideBrokenImage();
  });

  if (!toggle || !nav) return;

  const closeMenu = () => {
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Abrir menú');
    nav.classList.remove('is-open');
    document.body.classList.remove('menu-open');
  };

  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!open));
    toggle.setAttribute('aria-label', open ? 'Abrir menú' : 'Cerrar menú');
    nav.classList.toggle('is-open', !open);
    document.body.classList.toggle('menu-open', !open);
  });

  nav.querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMenu));
  window.addEventListener('resize', () => {
    if (window.innerWidth > 760) closeMenu();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMenu();
  });
});
