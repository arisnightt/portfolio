"""Получение последних обычных видео с YouTube-канала.

Поддерживаются два источника данных (только стандартная библиотека):

1. **RSS-лента** (по умолчанию, без ключа) — ``/feeds/videos.xml``. Подходит,
   когда YouTube доступен напрямую (например, сервер за рубежом).
2. **YouTube Data API v3** (если задана переменная ``YOUTUBE_API_KEY``) —
   ходит на ``googleapis.com`` и работает даже там, где сам YouTube блокируется
   провайдером.

В обоих случаях возвращаются только полноценные ролики — Shorts исключаются.

RSS-лента канала:

    https://www.youtube.com/feeds/videos.xml?channel_id=<ID канала>

Обычная лента содержит и Shorts, и прямые эфиры. Чтобы получить только
полноценные ролики, используется плейлист с префиксом ``UULF``:

    https://www.youtube.com/feeds/videos.xml?playlist_id=UULF<ID канала без UC>

Data API при заданном ключе резолвит хендл через ``channels.list``, берёт
плейлист загрузок и отфильтровывает Shorts по длительности ролика.

Результат каждого видео — словарь с ключами ``id``, ``title``, ``url``,
``thumbnail`` (16:9) и ``thumbnail_fallback``, а также ``published`` (ISO-8601).

Список видео кэшируется на ``YOUTUBE_CACHE_TTL`` секунд (по умолчанию 60;
``0`` — без кэша). При перечитывании удалённые ролики исчезают автоматически:
их больше нет ни в RSS-ленте, ни в плейлисте загрузок.

Проверка из командной строки::

    python youtube.py https://www.youtube.com/@arisnightt
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

__all__ = ["fetch_latest_videos"]

# Лента «обычные видео» (без Shorts и прямых эфиров).
_FEED_URL = "https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"

# Плейлист «обычные видео» — это ID канала, где префикс UC заменён на UULF.
_STANDARD_PLAYLIST_PREFIX = "UULF"

_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Указываем согласие, чтобы YouTube не отдал заглушку-«consent page».
_CONSENT_COOKIE = "CONSENT=YES+cb.20210328-17-p0.en+FX+000"

_CHANNEL_ID = r"UC[A-Za-z0-9_-]{22}"

# YouTube Data API v3.
_API_BASE = "https://www.googleapis.com/youtube/v3"
# Видео короче этой длительности считаем Shorts (классический порог — 60 сек).
_SHORTS_MAX_SECONDS = 60
_ISO_DURATION_RE = re.compile(
    r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$"
)

# Параметры кэша и сети.
_FETCH_TIMEOUT = 15
_CHANNEL_TTL = 60 * 60 * 24          # ID канала меняется редко — сутки.

# Как часто перечитывать список видео. Короткий интервал нужен, чтобы удалённые
# ролики быстро пропадали с сайта. Переопределяется переменной окружения
# YOUTUBE_CACHE_TTL (в секундах); 0 — кэш отключён (читать на каждый запрос).
try:
    _VIDEO_TTL = max(0, int(os.environ.get("YOUTUBE_CACHE_TTL", "60")))
except ValueError:
    _VIDEO_TTL = 60

# Простейший потокобезопасный кэш в памяти.
_channel_cache: dict[str, tuple[float, str]] = {}
_video_cache: dict[str, tuple[float, list[dict]]] = {}
_channel_lock = threading.Lock()
_video_lock = threading.Lock()


def _http_get(url: str) -> bytes:
    """GET-запрос с браузерным User-Agent и таймаутом."""
    request = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": _CONSENT_COOKIE,
        },
    )
    with urlopen(request, timeout=_FETCH_TIMEOUT) as response:
        return response.read()


def _parse_channel(value: str) -> tuple[str, str]:
    """Возвращает пару ``(kind, target)``.

    ``kind`` — ``"id"`` или ``"handle"``; ``target`` — channel ID (``UC…``) или
    хендл с ``@`` (например ``@arisnightt``).
    """
    value = (value or "").strip()
    if not value:
        raise ValueError("Пустой идентификатор канала")

    if re.fullmatch(_CHANNEL_ID, value):
        return "id", value
    if value.startswith("@"):
        return "handle", value

    parsed = urlsplit(value)
    if parsed.scheme in ("http", "https") and "youtube.com" in (parsed.netloc or ""):
        parts = [part for part in parsed.path.split("/") if part]
        for i, part in enumerate(parts):
            if part == "channel" and i + 1 < len(parts):
                return "id", parts[i + 1]
        for part in parts:
            if part.startswith("@"):
                return "handle", part
        for i, part in enumerate(parts):
            if part in ("user", "c") and i + 1 < len(parts):
                return "handle", "@" + parts[i + 1]

    raise ValueError(f"Не удалось распознать канал: {value!r}")


def _find_channel_id(page_text: str) -> str | None:
    """Ищет channel ID (``UC…``) в HTML страницы канала.

    Порядок важен: начинаем с однозначных источников в ``<head>`` (canonical и
    microdata), и только потом смотрим JSON-ключи, которые встречаются в
    странице много раз (в т.ч. у «рекомендуемых» каналов).
    """
    patterns = (
        r'rel="canonical"\s+href="https://www\.youtube\.com/channel/(?P<id>'
        + _CHANNEL_ID
        + r')"',
        r'itemprop="channelId"\s+content="(?P<id>' + _CHANNEL_ID + r')"',
        r'itemprop="identifier"\s+content="(?P<id>' + _CHANNEL_ID + r')"',
        r'"externalId"\s*:\s*"(?P<id>' + _CHANNEL_ID + r')"',
        r'"channelId"\s*:\s*"(?P<id>' + _CHANNEL_ID + r')"',
        r"/channel/(?P<id>" + _CHANNEL_ID + r")",
    )
    for pattern in patterns:
        match = re.search(pattern, page_text)
        if match:
            return match.group("id")
    return None


def _channel_id(handle: str) -> str:
    """Резолвит хендл канала в channel ID (с кэшем и singleflight)."""
    with _channel_lock:
        cached = _channel_cache.get(handle)
        if cached and time.time() - cached[0] < _CHANNEL_TTL:
            return cached[1]

        page = _http_get("https://www.youtube.com/" + handle).decode("utf-8", "replace")
        channel_id = _find_channel_id(page)
        if not channel_id:
            raise LookupError(f"Не найден ID канала для {handle!r}")

        _channel_cache[handle] = (time.time(), channel_id)
        return channel_id


def _entry_text(entry: ElementTree.Element, tag: str) -> str:
    node = entry.find(tag)
    if node is not None and node.text:
        return node.text.strip()
    return ""


def _entry_video_id(entry: ElementTree.Element) -> str | None:
    node = entry.find(f"{_YT}videoId")
    if node is not None and node.text:
        return node.text.strip()

    id_node = entry.find(f"{_ATOM}id")
    if id_node is not None and id_node.text:
        text = id_node.text.strip()
        if text.startswith("yt:video:"):
            return text[len("yt:video:"):]
    return None


def _parse_feed(xml_bytes: bytes, limit: int) -> list[dict]:
    """Разбирает Atom-ленту YouTube в список видео (новые первыми)."""
    root = ElementTree.fromstring(xml_bytes)
    videos: list[dict] = []

    for entry in root.findall(f"{_ATOM}entry"):
        video_id = _entry_video_id(entry)
        if not video_id:
            continue

        videos.append(
            {
                "id": video_id,
                "title": _entry_text(entry, f"{_ATOM}title"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                # maxresdefault — настоящие 16:9; если у ролика его нет,
                # фронтенд откатывается на hqdefault (4:3 с полями, кадрируется).
                "thumbnail": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
                "thumbnail_fallback": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                "published": _entry_text(entry, f"{_ATOM}published"),
            }
        )
        if len(videos) >= limit:
            break

    return videos


def _duration_seconds(value: str) -> int | None:
    """Переводит ISO-8601 длительность (``PT1M2S``) в секунды."""
    match = _ISO_DURATION_RE.match(value or "")
    if not match:
        return None
    days, hours, minutes, seconds = (int(group or 0) for group in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _thumb_url(thumbnails: dict, *keys: str) -> str:
    """Берёт первый доступный размер превью из ответа Data API."""
    for key in keys:
        node = thumbnails.get(key)
        if node and node.get("url"):
            return node["url"]
    return ""


def _api_json(path: str, params: dict, api_key: str) -> dict:
    """GET к YouTube Data API и разбор JSON-ответа."""
    query = urlencode({**params, "key": api_key})
    url = f"{_API_BASE}{path}?{query}"
    try:
        body = _http_get(url)
    except HTTPError as error:
        detail = ""
        try:
            payload = json.loads(error.read().decode("utf-8", "replace"))
            detail = (payload.get("error") or {}).get("message", "")
        except Exception:  # noqa: BLE001 — детали ошибки не критичны
            pass
        raise RuntimeError(
            f"YouTube Data API: HTTP {error.code} {detail or error.reason}"
        ) from error
    return json.loads(body.decode("utf-8"))


def _api_channel_id(handle: str, api_key: str) -> str:
    """Резолвит хендл в channel ID через Data API (с кэшем и singleflight)."""
    with _channel_lock:
        cached = _channel_cache.get(handle)
        if cached and time.time() - cached[0] < _CHANNEL_TTL:
            return cached[1]

        data = _api_json("/channels", {"part": "id", "forHandle": handle}, api_key)
        items = data.get("items") or []
        if not items and handle.startswith("@"):
            # На случай, если forHandle требует хендл без «@».
            data = _api_json("/channels", {"part": "id", "forHandle": handle[1:]}, api_key)
            items = data.get("items") or []
        if not items:
            raise LookupError(f"Канал {handle!r} не найден через Data API")

        channel_id = items[0].get("id")
        if not channel_id:
            raise LookupError(f"Не удалось получить ID канала {handle!r}")

        _channel_cache[handle] = (time.time(), channel_id)
        return channel_id


def _fetch_via_api(channel: str, api_key: str, limit: int) -> list[dict]:
    """Получение видео через YouTube Data API v3 (с singleflight-кэшем)."""
    kind, target = _parse_channel(channel)
    if kind == "id":
        channel_id = target
    else:
        channel_id = _api_channel_id(target, api_key)

    # Держим блокировку на время сетевых запросов, чтобы параллельные вызовы
    # не делали дублирующие запросы к API (singleflight).
    with _video_lock:
        cached = _video_cache.get(channel_id)
        if cached and time.time() - cached[0] < _VIDEO_TTL:
            return list(cached[1][:limit])

        # Плейлист загрузок = ID канала с префиксом UU (аналог UULF у RSS).
        uploads = "UU" + channel_id[2:]
        data = _api_json(
            "/playlistItems",
            {"part": "snippet", "playlistId": uploads, "maxResults": 50},
            api_key,
        )

        entries = []
        for item in data.get("items") or []:
            snippet = item.get("snippet") or {}
            video_id = (snippet.get("resourceId") or {}).get("videoId")
            if video_id:
                entries.append({"id": video_id, "snippet": snippet})

        videos: list[dict] = []
        if entries:
            # Длительности нужны, чтобы отсеять Shorts.
            details = _api_json(
                "/videos",
                {"part": "contentDetails", "id": ",".join(e["id"] for e in entries)},
                api_key,
            )
            durations = {
                item["id"]: _duration_seconds(
                    (item.get("contentDetails") or {}).get("duration")
                )
                for item in details.get("items") or []
                if item.get("id")
            }

            for entry in entries:
                if entry["id"] not in durations:
                    # videos.list не вернул ролик — он удалён/приватён: пропускаем,
                    # чтобы удалённое видео исчезло с сайта.
                    continue

                seconds = durations[entry["id"]]
                if seconds is not None and seconds <= _SHORTS_MAX_SECONDS:
                    continue  # это Short — пропускаем

                snippet = entry["snippet"]
                thumbnails = snippet.get("thumbnails") or {}
                videos.append(
                    {
                        "id": entry["id"],
                        "title": snippet.get("title", ""),
                        "url": f"https://www.youtube.com/watch?v={entry['id']}",
                        "thumbnail": _thumb_url(
                            thumbnails, "maxres", "high", "medium", "default"
                        ),
                        "thumbnail_fallback": _thumb_url(
                            thumbnails, "high", "medium", "default"
                        ),
                        "published": snippet.get("publishedAt", ""),
                    }
                )
                if len(videos) >= limit:
                    break

        _video_cache[channel_id] = (time.time(), videos)
        return list(videos)


def _fetch_via_rss(channel: str, limit: int) -> list[dict]:
    """Получение видео через публичную RSS-ленту (с singleflight-кэшем)."""
    kind, target = _parse_channel(channel)
    channel_id = target if kind == "id" else _channel_id(target)

    with _video_lock:
        cached = _video_cache.get(channel_id)
        if cached and time.time() - cached[0] < _VIDEO_TTL:
            return list(cached[1][:limit])

        feed_url = _FEED_URL.format(
            playlist_id=_STANDARD_PLAYLIST_PREFIX + channel_id[2:]
        )
        videos = _parse_feed(_http_get(feed_url), limit)
        _video_cache[channel_id] = (time.time(), videos)
        return list(videos)


def fetch_latest_videos(channel: str, limit: int = 5) -> list[dict]:
    """Возвращает до ``limit`` последних обычных (не Shorts) видео канала.

    Если задана переменная окружения ``YOUTUBE_API_KEY`` — используется
    YouTube Data API v3 (работает и при блокировке самого YouTube). Иначе —
    публичная RSS-лента.

    Параметр ``channel`` — ссылка на канал, хендл ``@handle`` или channel ID.
    При отсутствии видео возвращается пустой список.
    """
    limit = max(1, int(limit))
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if api_key:
        return _fetch_via_api(channel, api_key, limit)
    return _fetch_via_rss(channel, limit)


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Использование: python youtube.py <канал> [количество]")
        sys.exit(1)

    channel = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    try:
        videos = fetch_latest_videos(channel, count)
    except Exception as error:  # noqa: BLE001 — CLI: показать ошибку пользователю
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)

    if not videos:
        print("Ничего не найдено")
        sys.exit(0)

    print(json.dumps(videos, ensure_ascii=False, indent=2))
