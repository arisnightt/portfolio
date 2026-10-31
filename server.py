import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def _load_env_file(path: Path) -> None:
    """Загружает KEY=VALUE из файла .env, не перетирая уже заданные переменные."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Грузим .env до import youtube: модуль читает YOUTUBE_CACHE_TTL при импорте.
_load_env_file(Path(__file__).resolve().parent / ".env")

import youtube


ROOT = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("DATABASE_PATH", ROOT / "data" / "projects.sqlite3"))
YOUTUBE_CHANNEL = os.environ.get("YOUTUBE_CHANNEL", "https://www.youtube.com/@arisnightt")
SESSION_COOKIE = "admin_session"
SESSION_TTL = 60 * 60 * 12
PASSWORD_ITERATIONS = 310_000
MAX_REQUEST_SIZE = 64 * 1024
REQUEST_TIMEOUT = 30
LOGIN_LIMIT = 5
LOGIN_WINDOW = 15 * 60
LOGIN_ATTEMPTS = {}
LOGIN_LOCK = threading.Lock()

INITIAL_PROJECTS = (
    {
        "name": "KeyStash",
        "description": "Локальный и безопасный менеджер паролей для Windows и Linux. Пароли не уходят в облако, а исходный код проекта открыт на GitHub.",
        "url": "https://github.com/arisnightt/KeyStash",
        "color": "#1ed760",
        "tags": ["Java", "Windows", "Linux"],
    },
    {
        "name": "Veilframe",
        "description": "Лёгкий плагин для Paper и Spigot 1.21+. Скрывает рамку, оставляя предмет видимым, блокирует поворот и сбрасывает рамку одним кликом. Нужна Java 21+, внешние зависимости не требуются.",
        "url": "https://github.com/arisnightt/Veilframe",
        "color": "#9b6bff",
        "tags": ["Java", "Paper", "Spigot"],
    },
    {
        "name": "SimpleChatStyler",
        "description": "Простой плагин для настройки чата. Исходный код открыт на GitHub под лицензией MIT.",
        "url": "https://github.com/arisnightt/SimpleChatStyler",
        "color": "#19c3b0",
        "tags": ["Плагин", "MIT"],
    },
)


def connect_db():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def db_connection():
    connection = connect_db()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_iterations INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                description_en TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL,
                color TEXT NOT NULL,
                tags TEXT NOT NULL
            )
            """
        )
        project_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(projects)")
        }
        if "description_en" not in project_columns:
            connection.execute(
                "ALTER TABLE projects ADD COLUMN description_en TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        seeded = connection.execute(
            "SELECT 1 FROM app_meta WHERE key = 'projects_seeded'"
        ).fetchone()
        if not seeded:
            connection.executemany(
                """
                INSERT INTO projects (name, description, url, color, tags)
                VALUES (:name, :description, :url, :color, :tags)
                """,
                [
                    {**project, "tags": json.dumps(project["tags"], ensure_ascii=False)}
                    for project in INITIAL_PROJECTS
                ],
            )
            connection.execute(
                "INSERT INTO app_meta (key, value) VALUES ('projects_seeded', '1')"
            )


def hash_password(password, salt=None, iterations=PASSWORD_ITERATIONS):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return salt.hex(), digest.hex(), iterations


def create_admin():
    initialize_database()
    username = input("Admin username: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
        raise ValueError("Username must be 3-32 letters, digits, dots, underscores or hyphens.")

    password = getpass.getpass("Admin password (at least 8 characters): ")
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    confirmation = getpass.getpass("Repeat password: ")
    if not hmac.compare_digest(password, confirmation):
        raise ValueError("Passwords do not match.")

    salt, password_hash, iterations = hash_password(password)
    with db_connection() as connection:
        if connection.execute("SELECT 1 FROM admins LIMIT 1").fetchone():
            raise ValueError("An admin account already exists.")
        connection.execute(
            """
            INSERT INTO admins (username, password_hash, password_salt, password_iterations)
            VALUES (?, ?, ?, ?)
            """,
            (username, password_hash, salt, iterations),
        )
    print("Admin account created.")


def _reject_bidi_controls(value):
    """Запрещает невидимые/bidi-символы, которыми можно подменить отображение."""
    if any(
        0x200B <= ord(ch) <= 0x200F
        or 0x202A <= ord(ch) <= 0x202E
        or 0x2066 <= ord(ch) <= 0x2069
        or ord(ch) == 0xFEFF
        for ch in value
    ):
        raise ValueError("invalid_project")


def sanitize_text(value, *, max_length, allow_newlines=False):
    if not isinstance(value, str):
        raise ValueError("invalid_project")

    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_length:
        raise ValueError("invalid_project")

    if any(ord(ch) < 32 and (not allow_newlines or ch not in "\n\r\t") for ch in cleaned):
        raise ValueError("invalid_project")

    _reject_bidi_controls(cleaned)

    if re.search(r"<\s*(script|iframe|object|embed|svg|img|style|link|meta|base|form|button|input)\b", cleaned, re.IGNORECASE):
        raise ValueError("invalid_project")

    if re.search(r"(?:javascript|data|vbscript)\s*:", cleaned, re.IGNORECASE):
        raise ValueError("invalid_project")

    return cleaned


def sanitize_url(value):
    if not isinstance(value, str):
        raise ValueError("invalid_project")

    url = value.strip()
    if not url or len(url) > 500 or any(ord(ch) < 32 for ch in url):
        raise ValueError("invalid_project")
    if re.search(r"(?:javascript|data|vbscript)\s*:", url, re.IGNORECASE):
        raise ValueError("invalid_project")

    _reject_bidi_controls(url)

    try:
        parsed_url = urlsplit(url)
    except ValueError:
        raise ValueError("invalid_project")

    if (
        parsed_url.scheme.lower() not in ("https", "http")
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.hostname.strip() == ""
    ):
        raise ValueError("invalid_project")

    return url


def project_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid_project")

    name = payload.get("name")
    description = payload.get("description")
    description_en = payload.get("description_en", description)
    url = payload.get("url")
    color = payload.get("color")
    tags = payload.get("tags")

    name = sanitize_text(name, max_length=80)
    description = sanitize_text(description, max_length=2000, allow_newlines=True)
    description_en = sanitize_text(description_en, max_length=2000, allow_newlines=True)
    url = sanitize_url(url)

    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("invalid_project")
    if not isinstance(tags, list) or not 1 <= len(tags) <= 20:
        raise ValueError("invalid_project")
    cleaned_tags = []
    for tag in tags:
        cleaned_tag = sanitize_text(tag, max_length=40)
        if "," in cleaned_tag:
            raise ValueError("invalid_project")
        cleaned_tags.append(cleaned_tag)

    return {
        "name": name,
        "description": description,
        "description_en": description_en,
        "url": url,
        "color": color.lower(),
        "tags": json.dumps(cleaned_tags, ensure_ascii=False),
    }


class PortfolioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def setup(self):
        super().setup()
        # Таймаут сокета защищает от «медленных» клиентов (slowloris).
        self.connection.settimeout(REQUEST_TIMEOUT)

    def handle(self):
        try:
            super().handle()
        except (socket.timeout, ConnectionError):
            # Клиент оборвал соединение или не прислал данные — просто закрываем.
            pass

    def client_ip(self):
        """IP клиента; за доверенным прокси берётся X-Forwarded-For."""
        if os.environ.get("TRUST_PROXY") == "1":
            forwarded = self.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return self.client_address[0]

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https://i.ytimg.com; connect-src 'self'; font-src 'self' https://fonts.gstatic.com; object-src 'none'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests"
        )
        super().end_headers()

    def send_error(self, code, message=None, explain=None):
        if urlsplit(self.path).path.startswith("/api/"):
            error = "internal_error" if code >= HTTPStatus.INTERNAL_SERVER_ERROR else "request_failed"
            self.send_error_json(code, error)
            return
        super().send_error(code, message, explain)

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.address_string(), format_string % args))

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if headers:
            for name, value in headers:
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, code):
        self.send_json(status, {"error": code})

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid_json")
        if length < 1 or length > MAX_REQUEST_SIZE:
            raise ValueError("invalid_json")
        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            raise ValueError("invalid_json")
        if not isinstance(value, dict):
            raise ValueError("invalid_json")
        return value

    def require_same_origin(self):
        origin = self.headers.get("Origin")
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if fetch_site and fetch_site not in ("same-origin", "none"):
            return False
        if not origin:
            return False
        try:
            parsed_origin = urlsplit(origin)
        except ValueError:
            return False
        return (
            parsed_origin.scheme in ("http", "https")
            and parsed_origin.netloc.lower() == self.headers.get("Host", "").lower()
        )

    def session_admin(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        if not morsel:
            return None
        token_hash = hashlib.sha256(morsel.value.encode("ascii", errors="ignore")).hexdigest()
        now = int(time.time())
        with db_connection() as connection:
            row = connection.execute(
                """
                SELECT admins.id, admins.username
                FROM sessions
                JOIN admins ON admins.id = sessions.admin_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        return row

    def require_admin(self):
        admin = self.session_admin()
        if not admin:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "unauthorized")
            return None
        return admin

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/projects":
            with db_connection() as connection:
                rows = connection.execute(
                    "SELECT id, name, description, description_en, url, color, tags FROM projects ORDER BY id"
                ).fetchall()
            self.send_json(
                HTTPStatus.OK,
                [
                    {**dict(row), "tags": json.loads(row["tags"])}
                    for row in rows
                ],
            )
            return
        if path == "/api/videos":
            try:
                videos = youtube.fetch_latest_videos(YOUTUBE_CHANNEL, limit=5)
            except Exception as error:  # noqa: BLE001 — сеть/парсинг: деградируем до пустого списка
                print(f"[youtube] {error}", file=sys.stderr)
                videos = []
            self.send_json(HTTPStatus.OK, {"videos": videos})
            return
        if path == "/api/session":
            admin = self.session_admin()
            self.send_json(
                HTTPStatus.OK,
                {"authenticated": bool(admin), "username": admin["username"] if admin else None},
            )
            return
        if path.startswith("/api/"):
            self.send_error_json(HTTPStatus.NOT_FOUND, "not_found")
            return
        if path == "/":
            self.path = "/index.html"
            path = "/index.html"
        relative = unquote(path).lstrip("/")
        requested = (ROOT / relative).resolve()
        allowed = (
            requested == ROOT / "index.html"
            or requested == ROOT / "favicon.svg"
            or requested == ROOT / "modals.html"
            or requested.parent in (ROOT / "css", ROOT / "js")
        )
        if not allowed or not requested.is_file() or not requested.is_relative_to(ROOT):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/login":
            self.login()
            return
        if path == "/api/logout":
            if not self.require_same_origin():
                self.send_error_json(HTTPStatus.FORBIDDEN, "forbidden")
                return
            self.logout()
            return
        if path == "/api/projects":
            if not self.require_same_origin():
                self.send_error_json(HTTPStatus.FORBIDDEN, "forbidden")
                return
            if not self.require_admin():
                return
            self.save_project()
            return
        if path.startswith("/api/"):
            self.send_error_json(HTTPStatus.NOT_FOUND, "not_found")
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self):
        match = re.fullmatch(r"/api/projects/([0-9]+)", urlsplit(self.path).path)
        if not match:
            self.send_error_json(HTTPStatus.NOT_FOUND, "not_found")
            return
        if not self.require_same_origin():
            self.send_error_json(HTTPStatus.FORBIDDEN, "forbidden")
            return
        if not self.require_admin():
            return
        try:
            project = project_payload(self.read_json())
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        with db_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET name = :name, description = :description, description_en = :description_en,
                    url = :url, color = :color, tags = :tags
                WHERE id = :id
                """,
                {**project, "id": int(match.group(1))},
            )
        if cursor.rowcount == 0:
            self.send_error_json(HTTPStatus.NOT_FOUND, "not_found")
            return
        self.send_json(HTTPStatus.OK, {"ok": True})

    def do_DELETE(self):
        match = re.fullmatch(r"/api/projects/([0-9]+)", urlsplit(self.path).path)
        if not match:
            self.send_error_json(HTTPStatus.NOT_FOUND, "not_found")
            return
        if not self.require_same_origin():
            self.send_error_json(HTTPStatus.FORBIDDEN, "forbidden")
            return
        if not self.require_admin():
            return
        with db_connection() as connection:
            cursor = connection.execute("DELETE FROM projects WHERE id = ?", (int(match.group(1)),))
        if cursor.rowcount == 0:
            self.send_error_json(HTTPStatus.NOT_FOUND, "not_found")
            return
        self.send_json(HTTPStatus.OK, {"ok": True})

    def login(self):
        if not self.require_same_origin():
            self.send_error_json(HTTPStatus.FORBIDDEN, "forbidden")
            return

        now = time.time()
        address = self.client_ip()

        try:
            payload = self.read_json()
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        username = payload.get("username")
        password = payload.get("password")
        if (
            not isinstance(username, str)
            or not isinstance(password, str)
            or len(username) > 32
            or len(password) > 1024
        ):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "invalid_credentials")
            return

        # Резервируем попытку до PBKDF2, чтобы параллельные запросы не могли
        # обойти лимит. Вся работа с LOGIN_ATTEMPTS — под блокировкой.
        with LOGIN_LOCK:
            for client, stamps in list(LOGIN_ATTEMPTS.items()):
                active = [stamp for stamp in stamps if now - stamp < LOGIN_WINDOW]
                if active:
                    LOGIN_ATTEMPTS[client] = active
                else:
                    LOGIN_ATTEMPTS.pop(client, None)
            attempts = [stamp for stamp in LOGIN_ATTEMPTS.get(address, []) if now - stamp < LOGIN_WINDOW]
            if len(attempts) >= LOGIN_LIMIT:
                LOGIN_ATTEMPTS[address] = attempts
                self.send_error_json(HTTPStatus.TOO_MANY_REQUESTS, "rate_limited")
                return
            LOGIN_ATTEMPTS[address] = attempts + [now]

        with db_connection() as connection:
            admin = connection.execute(
                "SELECT id, password_hash, password_salt, password_iterations FROM admins WHERE username = ?",
                (username.strip(),),
            ).fetchone()

        if admin:
            salt = bytes.fromhex(admin["password_salt"])
            iterations = admin["password_iterations"]
            password_hash = admin["password_hash"]
        else:
            # Несуществующий пользователь: считаем на фейковых данных, чтобы
            # время ответа не раскрывало существование логина.
            salt = bytes(16)
            iterations = PASSWORD_ITERATIONS
            password_hash = ""

        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        ).hex()
        valid = bool(admin) and hmac.compare_digest(digest, password_hash)

        if not valid:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "invalid_credentials")
            return

        with LOGIN_LOCK:
            LOGIN_ATTEMPTS.pop(address, None)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        expires_at = int(now) + SESSION_TTL
        with db_connection() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(now),))
            connection.execute(
                "INSERT INTO sessions (token_hash, admin_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, admin["id"], expires_at),
            )

        secure = "; Secure" if os.environ.get("COOKIE_SECURE") == "1" else ""
        cookie = (
            f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_TTL}; "
            f"HttpOnly; SameSite=Strict{secure}"
        )
        self.send_json(
            HTTPStatus.OK,
            {"ok": True},
            [("Set-Cookie", cookie)],
        )

    def logout(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            cookie = SimpleCookie()
        morsel = cookie.get(SESSION_COOKIE)
        if morsel:
            token_hash = hashlib.sha256(morsel.value.encode("ascii", errors="ignore")).hexdigest()
            with db_connection() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        self.send_json(
            HTTPStatus.OK,
            {"ok": True},
            [("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")],
        )

    def save_project(self):
        try:
            project = project_payload(self.read_json())
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        with db_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects (name, description, description_en, url, color, tags)
                VALUES (:name, :description, :description_en, :url, :color, :tags)
                """,
                project,
            )
            project_id = cursor.lastrowid
        self.send_json(HTTPStatus.CREATED, {"id": project_id})


def run_server():
    initialize_database()
    host = os.environ.get("HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError:
        print("PORT должен быть числом. Использую 8000.", file=sys.stderr)
        port = 8000
    server = ThreadingHTTPServer((host, port), PortfolioHandler)
    server.daemon_threads = True
    print(f"Portfolio server listening at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-admin":
        try:
            create_admin()
        except (ValueError, sqlite3.IntegrityError) as error:
            print(f"Could not create admin: {error}", file=sys.stderr)
            sys.exit(1)
    else:
        run_server()