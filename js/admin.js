(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const dialog = $('#admin-dialog');
  const projectDialog = $('#project-dialog');
  const colorDialog = $('#color-dialog');
  const deleteConfirmDialog = $('#delete-confirm-dialog');
  const loginForm = $('#login-form');
  const dashboard = $('#admin-dashboard');
  const projectForm = $('#project-form');
  const message = $('#admin-message');
  const projectMessage = $('#project-message');
  const projectList = $('#admin-projects');
  const colorInput = $('#project-color');
  const colorSwatch = $('#project-color-swatch');
  const colorPlane = $('#color-plane');
  const colorPlaneCursor = $('#color-plane-cursor');
  const colorHue = $('#color-hue');
  const colorHex = $('#color-hex');
  const colorPreview = $('#color-preview');
  let adminProjects = [];
  let pickerHue = 130;
  let pickerSaturation = 0.85;
  let pickerValue = 0.84;

  function parseHex(hex) {
    if (!/^#[0-9a-f]{6}$/i.test(hex)) return null;
    return {
      red: parseInt(hex.slice(1, 3), 16) / 255,
      green: parseInt(hex.slice(3, 5), 16) / 255,
      blue: parseInt(hex.slice(5, 7), 16) / 255
    };
  }

  function hexToHsv(hex) {
    const { red, green, blue } = parseHex(hex);
    const maximum = Math.max(red, green, blue);
    const minimum = Math.min(red, green, blue);
    const difference = maximum - minimum;
    let hue = 0;

    if (difference) {
      if (maximum === red) hue = ((green - blue) / difference) % 6;
      else if (maximum === green) hue = (blue - red) / difference + 2;
      else hue = (red - green) / difference + 4;
    }

    return {
      hue: (hue * 60 + 360) % 360,
      saturation: maximum ? difference / maximum : 0,
      value: maximum
    };
  }

  function hsvToHex(hue, saturation, value) {
    const chroma = value * saturation;
    const section = hue / 60;
    const secondary = chroma * (1 - Math.abs(section % 2 - 1));
    const [red, green, blue] = section < 1 ? [chroma, secondary, 0]
      : section < 2 ? [secondary, chroma, 0]
        : section < 3 ? [0, chroma, secondary]
          : section < 4 ? [0, secondary, chroma]
            : section < 5 ? [secondary, 0, chroma]
              : [chroma, 0, secondary];
    const offset = value - chroma;
    return `#${[red, green, blue].map(channel => Math.round((channel + offset) * 255).toString(16).padStart(2, '0')).join('')}`.toUpperCase();
  }

  function renderColorPicker(syncHex = true) {
    const hex = hsvToHex(pickerHue, pickerSaturation, pickerValue);
    colorPlane.style.setProperty('--picker-hue', `hsl(${pickerHue} 100% 50%)`);
    colorPlaneCursor.style.left = `${pickerSaturation * 100}%`;
    colorPlaneCursor.style.top = `${(1 - pickerValue) * 100}%`;
    colorHue.value = pickerHue;
    colorPreview.style.backgroundColor = hex;
    colorPlane.setAttribute('aria-valuenow', String(Math.round(pickerValue * 100)));
    colorPlane.setAttribute('aria-valuetext', hex);
    if (syncHex) colorHex.value = hex;
  }

  function setPickerFromHex(hex) {
    const color = hexToHsv(hex);
    if (!color) return false;
    pickerHue = color.hue;
    pickerSaturation = color.saturation;
    pickerValue = color.value;
    renderColorPicker();
    return true;
  }

  function updateColorSwatch() {
    const validColor = parseHex(colorInput.value);
    colorSwatch.style.setProperty('--swatch-color', validColor ? colorInput.value : 'transparent');
    colorSwatch.setAttribute('aria-invalid', String(!validColor));
  }

  function updatePickerFromPointer(event) {
    const bounds = colorPlane.getBoundingClientRect();
    pickerSaturation = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    pickerValue = 1 - Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height));
    renderColorPicker();
  }

  function showMessage(text) {
    message.textContent = i18n.text(text);
  }

  function confirmDelete() {
    return new Promise(resolve => {
      deleteConfirmDialog.returnValue = '';
      deleteConfirmDialog.addEventListener('close', () => {
        resolve(deleteConfirmDialog.returnValue === 'confirm');
      }, { once: true });
      deleteConfirmDialog.showModal();
    });
  }

  async function request(url, options = {}) {
    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers
      }
    });
    const body = await response.text();
    let data;

    try {
      data = JSON.parse(body);
    } catch {
      const error = new Error('invalid_response');
      error.status = response.status;
      throw error;
    }

    if (!response.ok) {
      const error = new Error(data.error || 'request_failed');
      error.status = response.status;
      throw error;
    }

    return data;
  }

  function errorMessage(error) {
    if (error.message === 'invalid_credentials') return 'Неверный логин или пароль.';
    if (error.message === 'rate_limited') return 'Слишком много попыток. Попробуйте позже.';
    if (error.message === 'unauthorized') return 'Войдите в аккаунт администратора.';
    if (error.message === 'forbidden') return 'Сервер отклонил запрос.';
    if (error.message === 'internal_error') return 'Ошибка сервера. Подробности доступны в окне PowerShell.';
    if (error.message === 'invalid_response') {
      return `${i18n.text('Сервер вернул некорректный ответ. Проверьте окно PowerShell.')} (HTTP ${error.status})`;
    }
    if (error.status >= 500) {
      return `${i18n.text('Ошибка сервера. Подробности доступны в окне PowerShell.')} (HTTP ${error.status})`;
    }
    if (error instanceof TypeError) return 'Проверьте соединение с сервером и повторите попытку.';
    return 'Не удалось выполнить запрос.';
  }

  function setAuthenticated(authenticated) {
    loginForm.hidden = authenticated;
    dashboard.hidden = !authenticated;
    message.textContent = '';
  }

  async function loadAdminProjects() {
    adminProjects = await request('/api/projects');
    projectList.replaceChildren();

    adminProjects.forEach(project => {
      const item = document.createElement('article');
      item.className = 'proj admin-project';

      const shot = document.createElement('div');
      shot.className = 'shot';
      shot.style.setProperty('--c', project.color);
      for (let index = 0; index < 3; index++) shot.append(document.createElement('i'));

      const content = document.createElement('div');
      content.className = 'pm';

      const heading = document.createElement('h4');
      heading.textContent = project.name;

      const actions = document.createElement('div');
      actions.className = 'admin-project-actions';
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'btn s';
      edit.dataset.action = 'edit';
      edit.dataset.id = project.id;
      edit.textContent = i18n.text('Изменить');
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn s';
      remove.dataset.action = 'delete';
      remove.dataset.id = project.id;
      remove.textContent = i18n.text('Удалить');

      actions.append(edit, remove);
      content.append(heading, actions);
      item.append(shot, content);
      projectList.append(item);
    });
  }

  async function openAdmin() {
    message.textContent = '';
    loginForm.reset();
    try {
      const session = await request('/api/session');
      setAuthenticated(session.authenticated);
      if (session.authenticated) await loadAdminProjects();
    } catch (error) {
      setAuthenticated(false);
      showMessage(errorMessage(error));
    }
    if (!dialog.open) dialog.showModal();
  }

  function beginEdit(project) {
    $('#project-id').value = project.id;
    $('#project-name').value = project.name;
    $('#project-description').value = project.description;
    $('#project-description-en').value = project.description_en || i18n.english(project.description);
    $('#project-url').value = project.url;
    colorInput.value = project.color;
    updateColorSwatch();
    $('#project-tags').value = project.tags.join(', ');
    $('#project-form-title').textContent = i18n.text('Изменить');
    openProjectEditor();
  }

  function beginAdd() {
    projectForm.reset();
    $('#project-id').value = '';
    colorInput.value = '#1ed760';
    updateColorSwatch();
    $('#project-form-title').textContent = i18n.text('Новый проект');
    openProjectEditor();
  }

  function openProjectEditor() {
    projectMessage.textContent = '';
    dialog.close();
    projectDialog.showModal();
  }

  $('#admin-open').addEventListener('click', openAdmin);
  $('#admin-close').addEventListener('click', () => dialog.close());
  $('#project-close').addEventListener('click', () => projectDialog.close());
  colorSwatch.addEventListener('click', () => {
    if (!setPickerFromHex(colorInput.value)) setPickerFromHex('#1ed760');
    colorDialog.showModal();
  });
  colorInput.addEventListener('input', updateColorSwatch);
  $('#color-close').addEventListener('click', () => colorDialog.close());
  $('#color-cancel').addEventListener('click', () => colorDialog.close());
  $('#color-apply').addEventListener('click', () => {
    if (!colorHex.reportValidity()) return;
    colorInput.value = colorHex.value.toUpperCase();
    updateColorSwatch();
    colorDialog.close();
  });
  colorPlane.addEventListener('pointerdown', event => {
    colorPlane.setPointerCapture(event.pointerId);
    updatePickerFromPointer(event);
  });
  colorPlane.addEventListener('pointermove', event => {
    if (colorPlane.hasPointerCapture(event.pointerId)) updatePickerFromPointer(event);
  });
  colorPlane.addEventListener('keydown', event => {
    const step = event.shiftKey ? 0.1 : 0.01;
    if (event.key === 'ArrowLeft') pickerSaturation = Math.max(0, pickerSaturation - step);
    else if (event.key === 'ArrowRight') pickerSaturation = Math.min(1, pickerSaturation + step);
    else if (event.key === 'ArrowUp') pickerValue = Math.min(1, pickerValue + step);
    else if (event.key === 'ArrowDown') pickerValue = Math.max(0, pickerValue - step);
    else return;
    event.preventDefault();
    renderColorPicker();
  });
  colorHue.addEventListener('input', () => {
    pickerHue = Number(colorHue.value);
    renderColorPicker();
  });
  colorHex.addEventListener('input', () => {
    const value = colorHex.value.trim();
    if (parseHex(value)) setPickerFromHex(value);
  });
  colorHex.addEventListener('blur', () => {
    if (!parseHex(colorHex.value.trim())) renderColorPicker();
  });
  projectDialog.addEventListener('close', () => {
    projectForm.reset();
    projectMessage.textContent = '';
    if (!dashboard.hidden && !dialog.open) dialog.showModal();
  });

  loginForm.addEventListener('submit', async event => {
    event.preventDefault();
    showMessage('');

    try {
      await request('/api/login', {
        method: 'POST',
        body: JSON.stringify({
          username: $('#login-username').value,
          password: $('#login-password').value
        })
      });
      setAuthenticated(true);
      await loadAdminProjects();
    } catch (error) {
      showMessage(errorMessage(error));
    }
  });

  $('#add-project').addEventListener('click', beginAdd);
  $('#cancel-project').addEventListener('click', () => projectDialog.close());

  projectForm.addEventListener('submit', async event => {
    event.preventDefault();
    const id = $('#project-id').value;
    const payload = {
      name: $('#project-name').value,
      description: $('#project-description').value,
      description_en: $('#project-description-en').value,
      url: $('#project-url').value,
      color: colorInput.value.toUpperCase(),
      tags: $('#project-tags').value.split(',').map(tag => tag.trim()).filter(Boolean)
    };

    try {
      await request(id ? `/api/projects/${id}` : '/api/projects', {
        method: id ? 'PUT' : 'POST',
        body: JSON.stringify(payload)
      });
      projectForm.reset();
      showMessage('Проект сохранён.');
      await loadAdminProjects();
      await window.loadProjects();
      projectDialog.close();
    } catch (error) {
      projectMessage.textContent = errorMessage(error);
    }
  });

  projectList.addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;

    try {
      if (button.dataset.action === 'edit') {
        const project = adminProjects.find(item => String(item.id) === button.dataset.id);
        if (project) beginEdit(project);
        return;
      }

      if (button.dataset.action === 'delete' && await confirmDelete()) {
        await request(`/api/projects/${button.dataset.id}`, { method: 'DELETE' });
        showMessage('Проект удалён.');
        await loadAdminProjects();
        await window.loadProjects();
      }
    } catch (error) {
      showMessage(errorMessage(error));
    }
  });

  $('#logout').addEventListener('click', async () => {
    try {
      await request('/api/logout', { method: 'POST' });
      setAuthenticated(false);
      projectList.replaceChildren();
      dialog.close();
    } catch (error) {
      showMessage(errorMessage(error));
    }
  });
})();
