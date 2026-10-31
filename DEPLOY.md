# Развертывание на Docker

Потребуются Docker Engine с Docker Compose, публичный IP-адрес сервера и открытые входящие порты TCP 80 и 443.

## DNS

Настройте для `arisnight.dpdns.org` запись A на публичный IP сервера. Если для домена опубликована запись AAAA, она тоже должна указывать на этот сервер и быть доступна извне.

## Первый запуск

В каталоге проекта создайте учетную запись администратора и запустите приложение с Nginx:

```sh
docker compose run --rm app python server.py create-admin
docker compose up -d --build
```

До выпуска сертификата сайт будет доступен по HTTP. Укажите адрес электронной почты вместо `EMAIL` и запросите сертификат:

```sh
docker compose --profile certbot run --rm certbot certonly --webroot -w /var/www/certbot -d arisnight.dpdns.org --email EMAIL --agree-tos --no-eff-email
docker compose restart nginx
```

После перезапуска Nginx автоматически выберет HTTPS-конфигурацию, и сайт будет доступен по адресу `https://arisnight.dpdns.org`. Убедитесь, что DNS уже указывает на этот сервер и порт 80 доступен для проверки Let's Encrypt.

До включения HTTPS вход в админку заблокирован, чтобы пароль не передавался по HTTP.

## Обновление и данные

Для обновления приложения:

```sh
git pull
docker compose up -d --build
```

SQLite хранится в томе `portfolio_data` и переживает пересоздание контейнеров. Не выполняйте `docker compose down -v`, если хотите сохранить базу данных. Чтобы перенести существующую `data/projects.sqlite3`, до создания администратора скопируйте ее в том:

```sh
docker compose up -d app
docker compose stop app
docker compose cp data/projects.sqlite3 app:/app/data/projects.sqlite3
```

Затем создайте администратора и запустите все сервисы командами из раздела первого запуска. Если импорт базы не нужен, сразу выполняйте команды оттуда.

Сертификат Let's Encrypt действует ограниченное время. Периодически запускайте продление и перезапускайте Nginx для перечитывания сертификата:

```sh
docker compose --profile certbot run --rm certbot renew
docker compose restart nginx
```

Ключ YouTube Data API, если он нужен, можно задать в файле `.env` в каталоге проекта:

```dotenv
YOUTUBE_API_KEY=your-key
YOUTUBE_CACHE_TTL=60
```

Compose читает эти значения при запуске. Файл `.env` не включается в Docker-образ.