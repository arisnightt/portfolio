(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const EN = {
    'Свернуть меню': 'Collapse menu',
    'Закрыть': 'Close',
    'Главная': 'Home',
    'Проекты': 'Projects',
    'Видео': 'Videos',
    'Обо мне': 'About',
    'Навыки': 'Skills',
    'Контакты': 'Contacts',
    'Java и Python': 'Java & Python',
    'Пишу на Java и Python: приложения, боты и моды': 'I build apps, bots and mods in Java and Python',
    'Я ArisNight. Делаю десктопные программы на JavaFX, ботов для Discord и Telegram, плагины и моды для Minecraft. Сейчас развиваю KeyStash — локальный менеджер паролей.': 'I’m ArisNight. I build desktop apps with JavaFX, bots for Discord and Telegram, and plugins and mods for Minecraft. Right now I’m working on KeyStash, a local password manager.',
    'Смотреть проекты': 'View projects',
    'Все': 'All',
    'Связаться': 'Get in touch',
    'технологий в стеке': 'technologies in my stack',
    'проектов': 'projects',
    'сообщества': 'communities',
    'Локальный и безопасный менеджер паролей для Windows и Linux. Исходный код открыт на GitHub.': 'A local, secure password manager for Windows and Linux. The source code is open on GitHub.',
    'Локальный и безопасный менеджер паролей для Windows и Linux. Пароли не уходят в облако, а исходный код проекта открыт на GitHub.': 'A local, secure password manager for Windows and Linux. Your passwords never go to the cloud, and the source code is open on GitHub.',
    'Пишу на Java и Python. Делаю десктопные приложения на JavaFX, ботов для Discord и Telegram, а также плагины и моды для Minecraft.': 'I write Java and Python. I build desktop apps with JavaFX, bots for Discord and Telegram, and plugins and mods for Minecraft.',
    'Сейчас изучаю JavaScript, чтобы делать не только программы и ботов, но и интерфейсы для веба.': 'I’m learning JavaScript right now, so I can build not only programs and bots but also web interfaces.',
    'Сейчас': 'Now',
    'Развиваю KeyStash': 'Working on KeyStash',
    'Изучаю': 'Learning',
    'Сообщества': 'Communities',
    'Telegram-канал и Discord-сервер': 'Telegram channel and Discord server',
    'Стек': 'Stack',
    'Веб': 'Web',
    'JavaScript (изучаю)': 'JavaScript (learning)',
    'Пишите в Telegram или заходите на сервер': 'Message me on Telegram or join the server',
    'Открыть Telegram': 'Open Telegram',
    'Открыть проект': 'Open project',
    'Плагин для Paper и Spigot: невидимые рамки для предметов с блокировкой поворота.': 'A Paper and Spigot plugin: invisible item frames with rotation lock.',
    'Лёгкий плагин для Paper и Spigot 1.21+. Скрывает рамку, оставляя предмет видимым, блокирует поворот и сбрасывает рамку одним кликом. Нужна Java 21+, внешние зависимости не требуются.': 'A lightweight plugin for Paper and Spigot 1.21+. It hides the frame while keeping the item visible, locks rotation, and resets the frame in one click. Requires Java 21+, no external dependencies.',
    'Простой плагин для настройки чата.': 'A simple plugin for chat customization.',
    'Простой плагин для настройки чата. Исходный код открыт на GitHub под лицензией MIT.': 'A simple plugin for chat customization. The source code is open on GitHub under the MIT license.',
    'Плагин': 'Plugin',
    'Админ-панель': 'Admin panel',
    'Вход в аккаунт': 'Sign in',
    'Логин': 'Username',
    'Пароль': 'Password',
    'Войти': 'Sign in',
    'Добавить проект': 'Add project',
    'Выйти': 'Sign out',
    'Новый проект': 'New project',
    'Название': 'Name',
    'Описание': 'Description',
    'Описание на русском': 'Description in Russian',
    'Описание на английском': 'Description in English',
    'Ссылка': 'Link',
    'Цвет карточки': 'Card color',
    'Теги (через запятую)': 'Tags (comma-separated)',
    'Сохранить': 'Save',
    'Отмена': 'Cancel',
    'Загружаю проекты…': 'Loading projects…',
    'Загружаю видео…': 'Loading videos…',
    'Ничего не найдено': 'Nothing found',
    'Не удалось загрузить проекты. Убедитесь, что сервер запущен.': 'Could not load projects. Make sure the server is running.',
    'Не удалось загрузить видео. Убедитесь, что сервер запущен.': 'Could not load videos. Make sure the server is running.',
    'Неверный логин или пароль.': 'Incorrect username or password.',
    'Слишком много попыток. Попробуйте позже.': 'Too many attempts. Try again later.',
    'Войдите в аккаунт администратора.': 'Sign in with an administrator account.',
    'Сервер отклонил запрос.': 'The server rejected the request.',
    'Проверьте соединение с сервером и повторите попытку.': 'Check the connection to the server and try again.',
    'Проект сохранён.': 'Project saved.',
    'Проект удалён.': 'Project deleted.',
    'Удалить': 'Delete',
    'Изменить': 'Edit',
    'Вы уверены, что хотите удалить проект?': 'Are you sure you want to delete this project?',
    'Удалить проект?': 'Delete project?',
    'Не удалось выполнить запрос.': 'The request could not be completed.',
    'Ошибка сервера. Подробности доступны в окне PowerShell.': 'Server error. Check the PowerShell window for details.',
    'Сервер вернул некорректный ответ. Проверьте окно PowerShell.': 'The server returned an invalid response. Check the PowerShell window.'
  };

  let lang = 'ru';

  try {
    lang = localStorage.getItem('lang') === 'en' ? 'en' : 'ru';
  } catch (e) {}

  const tr = s => lang === 'en' && EN[s] ? EN[s] : s;
  const esc = s => String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  const pair = (ru, en) => '<t-i><t-r>' + esc(ru) + '</t-r><t-e>' + esc(en || EN[ru] || ru) + '</t-e></t-i>';

  function wrapAll() {
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const list = [];

    for (let n; n = w.nextNode();) {
      if (n.parentNode.closest('script,#title,t-i')) continue;
      if (EN[n.nodeValue.trim()]) list.push(n);
    }

    list.forEach(n => {
      const v = n.nodeValue;
      const k = v.trim();
      const i = v.indexOf(k);
      const t = document.createElement('template');
      t.innerHTML = pair(k);
      n.replaceWith(v.slice(0, i), t.content, v.slice(i + k.length));
    });
  }

  function applyLang() {
    document.documentElement.lang = lang;
    $('#lang').setAttribute('aria-checked', String(lang === 'en'));

    $$('[aria-label]').forEach(el => {
      if (el.id === 'lang') return;
      el.dataset.ru = el.dataset.ru || el.getAttribute('aria-label');
      el.setAttribute('aria-label', tr(el.dataset.ru));
    });
  }

  $('#lang').onclick = () => {
    lang = lang === 'en' ? 'ru' : 'en';

    try {
      localStorage.setItem('lang', lang);
    } catch (e) {}

    applyLang();
  };

  window.i18n = {
    pair,
    text: value => tr(value),
    english: value => EN[value] || value,
    get language() {
      return lang;
    }
  };
  wrapAll();
  applyLang();
})();
