try {
  const response = await fetch('./modals.html', { cache: 'no-store' });
  if (!response.ok) throw new Error('modals_request_failed');

  document.body.insertAdjacentHTML('beforeend', await response.text());
  await import('./translations.js');
  await import('./script.js');
  await import('./admin.js');
} catch (error) {
  console.error('Failed to initialize the page.', error);
  const message = document.createElement('p');
  message.className = 'project-message';
  message.setAttribute('role', 'alert');
  message.textContent = 'Не удалось загрузить интерфейс. Перезагрузите страницу.';
  document.querySelector('main')?.prepend(message);
}