const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const app = $('#app');
const scroll = $('#scroll');
const links = $$('#nav a');
const title = $('#title');
const sideContact = $('.side-contact');
const sideFooter = $('.side-footer');
const contactBreakpoint = matchMedia('(max-width:820px)');

function placeSideContact({ matches }) {
  if (matches) sideFooter.insertBefore(sideContact, $('.admin-trigger', sideFooter));
  else $('#nav').after(sideContact);
}

placeSideContact(contactBreakpoint);
contactBreakpoint.addEventListener('change', placeSideContact);

let shown = '';

// collapse sidebar (remember choice if storage is available)
try {
  if (localStorage.getItem('side') === '1') app.classList.add('collapsed');
} catch (e) {}

$('#toggle').onclick = () => {
  app.classList.toggle('collapsed');

  try {
    localStorage.setItem('side', app.classList.contains('collapsed') ? '1' : '0');
  } catch (e) {}
};

const mobileMenuToggle = $('#mobile-menu-toggle');
mobileMenuToggle.onclick = () => {
  const isOpen = $('.side').classList.toggle('menu-open');
  mobileMenuToggle.setAttribute('aria-expanded', String(isOpen));
};

document.addEventListener('keydown', event => {
  if (!event.ctrlKey || event.altKey || event.shiftKey || event.repeat || event.key.toLowerCase() !== 'b') return;
  if (event.target instanceof Element && (
    event.target.matches('input, textarea, select') || event.target.isContentEditable
  )) return;

  event.preventDefault();
  $('#toggle').click();
});

// nav click -> smooth scroll inside panel
links.forEach(a => a.addEventListener('click', e => {
  e.preventDefault();
  const t = $(a.getAttribute('href'));
  if (!t) return;

  const mobile = matchMedia('(max-width:820px)').matches;
  if (mobile) {
    t.scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('.side').classList.remove('menu-open');
    mobileMenuToggle.setAttribute('aria-expanded', 'false');
  }
  else scroll.scrollTo({
    top: scroll.scrollTop + t.getBoundingClientRect().top - scroll.getBoundingClientRect().top - 28,
    behavior: 'smooth'
  });
}));

$$('.cta a, .links a').forEach(a => a.addEventListener('click', e => {
  const h = a.getAttribute('href');
  if (h === '#') {
    e.preventDefault();
    return;
  }

  if (h && h.startsWith('#')) {
    e.preventDefault();
    links.find(l => l.getAttribute('href') === h)?.click();
  }
}));

const projectGrid = $('#project-grid');
const projectFilters = $('#project-filters');
let activeProjectTag = '';

function renderProjectFilters(projects) {
  const tags = [...new Set(projects.flatMap(project => project.tags))];
  const all = document.createElement('button');
  all.type = 'button';
  all.className = 'chip on';
  all.dataset.tag = '';
  all.setAttribute('aria-pressed', 'true');
  all.innerHTML = i18n.pair('Все');

  projectFilters.replaceChildren(all, ...tags.map(tag => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chip';
    button.dataset.tag = tag;
    button.setAttribute('aria-pressed', 'false');
    button.textContent = tag;
    return button;
  }));
}

projectFilters.addEventListener('click', event => {
  const button = event.target.closest('.chip');
  if (!button) return;

  activeProjectTag = button.dataset.tag;
  $$('.chip', projectFilters).forEach(chip => {
    const active = chip === button;
    chip.classList.toggle('on', active);
    chip.setAttribute('aria-pressed', String(active));
  });

  $$('.proj', projectGrid).forEach(card => {
    const matches = !activeProjectTag || [...card.querySelectorAll('.tags span')]
      .some(tag => tag.textContent === activeProjectTag);
    card.hidden = !matches;
  });
});

function renderProject(project) {
  const card = document.createElement('div');
  card.className = 'proj';
  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');
  card.dataset.id = project.id;
  card.dataset.href = project.url;
  card.dataset.name = project.name;
  card.dataset.color = project.color;
  card.dataset.desc = project.description;
  card.dataset.descEn = project.description_en;

  const shot = document.createElement('div');
  shot.className = 'shot';
  shot.style.setProperty('--c', project.color);
  for (let i = 0; i < 3; i++) shot.append(document.createElement('i'));

  const content = document.createElement('div');
  content.className = 'pm';
  const name = document.createElement('h4');
  name.textContent = project.name;
  const description = document.createElement('p');
  description.innerHTML = i18n.pair(project.description, project.description_en);
  const tags = document.createElement('div');
  tags.className = 'tags';
  project.tags.forEach(tag => {
    const item = document.createElement('span');
    item.textContent = tag;
    tags.append(item);
  });

  content.append(name, description, tags);
  card.append(shot, content);
  return card;
}

async function loadProjects() {
  try {
    const response = await fetch('/api/projects');
    if (!response.ok) throw new Error('request_failed');
    const projects = await response.json();
    renderProjectFilters(projects);
    projectGrid.replaceChildren(...projects.map(renderProject));
    $('.stats .stat:nth-child(2) b').textContent = projects.length;
  } catch {
    const message = document.createElement('p');
    message.className = 'project-message';
    message.setAttribute('role', 'alert');
    message.textContent = i18n.text('Не удалось загрузить проекты. Убедитесь, что сервер запущен.');
    projectGrid.replaceChildren(message);
  }
}

window.loadProjects = loadProjects;

const videoGrid = $('#video-grid');

function formatVideoDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const locale = i18n.language === 'en' ? 'en-GB' : 'ru-RU';
  return date.toLocaleDateString(locale, {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  });
}

function renderVideo(video) {
  const card = document.createElement('a');
  card.className = 'video';
  card.href = video.url;
  card.target = '_blank';
  card.rel = 'noopener';

  const thumb = document.createElement('div');
  thumb.className = 'vthumb';
  const img = document.createElement('img');
  img.src = video.thumbnail;
  img.alt = '';
  img.loading = 'lazy';
  img.referrerPolicy = 'no-referrer';
  img.onerror = () => {
    if (img.dataset.fallback !== '1') {
      img.dataset.fallback = '1';
      img.src = video.thumbnail_fallback;
    }
  };
  const play = document.createElement('span');
  play.className = 'vplay';
  play.setAttribute('aria-hidden', 'true');
  thumb.append(img, play);

  const info = document.createElement('div');
  info.className = 'vm';
  const title = document.createElement('h4');
  title.textContent = video.title;
  const date = document.createElement('time');
  date.dateTime = video.published;
  date.textContent = formatVideoDate(video.published);
  info.append(title, date);

  card.append(thumb, info);
  return card;
}

async function loadVideos() {
  try {
    const response = await fetch('/api/videos');
    if (!response.ok) throw new Error('request_failed');
    const { videos } = await response.json();
    if (!videos.length) {
      const message = document.createElement('p');
      message.className = 'project-message';
      message.setAttribute('role', 'status');
      message.textContent = i18n.text('Ничего не найдено');
      videoGrid.replaceChildren(message);
      return;
    }
    videoGrid.replaceChildren(...videos.map(renderVideo));
  } catch {
    const message = document.createElement('p');
    message.className = 'project-message';
    message.setAttribute('role', 'alert');
    message.textContent = i18n.text('Не удалось загрузить видео. Убедитесь, что сервер запущен.');
    videoGrid.replaceChildren(message);
  }
}

window.loadVideos = loadVideos;

projectGrid.addEventListener('click', event => {
  const card = event.target.closest('.proj');
  if (card) openProject(card);
});

projectGrid.addEventListener('keydown', event => {
  const card = event.target.closest('.proj');
  if (card && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault();
    openProject(card);
  }
});

// scroll spy
function setActive(id) {
  links.forEach(l => l.classList.toggle('on', l.getAttribute('href') === '#' + id));
  const s = $('#' + id);

  if (s && id !== shown) {
    shown = id;
    title.innerHTML = i18n.pair(s.dataset.t);
  }
}

const spy = () => {
  const mobile = matchMedia('(max-width:820px)').matches;
  const secs = $$('section');
  let cur = secs[0].id;
  const probe = mobile
    ? window.innerHeight * .35
    : scroll.getBoundingClientRect().top + scroll.clientHeight * .35;

  secs.forEach(s => {
    if (s.getBoundingClientRect().top <= probe) cur = s.id;
  });

  // последний раздел короткий и не доезжает до середины экрана — в самом низу выбираем его
  const el = mobile ? document.scrollingElement : scroll;
  if (el.scrollTop > 0 && el.scrollTop + el.clientHeight >= el.scrollHeight - 4) {
    cur = secs[secs.length - 1].id;
  }

  setActive(cur);
};

scroll.addEventListener('scroll', spy, { passive: true });
addEventListener('scroll', spy, { passive: true });
spy();

// project dialog
const dlg = $('#dlg');

function openProject(p) {
  if (!p.dataset.name) return;
  $('#dlg-t').textContent = p.dataset.name;
  $('#dlg-d').innerHTML = i18n.pair(p.dataset.desc, p.dataset.descEn);
  $('#dlg-shot').style.setProperty('--c', p.dataset.color);
  const tags = $('#dlg-tags');
  tags.replaceChildren(...[...p.querySelectorAll('.tags span')].map(tag => {
    const item = document.createElement('span');
    item.textContent = tag.textContent;
    return item;
  }));
  $('#dlg-a').href = p.dataset.href;
  $('#dlg-u').textContent = p.dataset.href.replace('https://', '');
  dlg.showModal();
  document.documentElement.classList.add('lock');
}

$('#dlg-x').onclick = () => dlg.close();
dlg.addEventListener('click', e => {
  if (e.target === dlg) dlg.close();
});
dlg.addEventListener('close', () => document.documentElement.classList.remove('lock'));
document.addEventListener('touchmove', e => {
  if (dlg.open) e.preventDefault();
}, { passive: false });

// counters + skill bars on first view
function count(el) {
  const n = +el.dataset.n;
  const t0 = performance.now();
  const d = 1100;

  (function f(t) {
    const k = Math.min((t - t0) / d, 1);
    el.textContent = Math.round(n * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(f);
  })(t0);
}

const io = new IntersectionObserver(es => es.forEach(e => {
  if (!e.isIntersecting) return;
  $$('[data-n]', e.target).forEach(count);
  $$('[data-w]', e.target).forEach(b => b.style.width = b.dataset.w + '%');
  io.unobserve(e.target);
}), { threshold: .3 });

$$('#home,#skills').forEach(s => io.observe(s));

loadProjects();
loadVideos();
