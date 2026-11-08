import re
import struct
from pathlib import Path
from urllib.parse import urlparse


BOORU_HOST_MAP = {
    "yande.re": "Yande.re",
    "files.yande.re": "Yande.re",
    "gelbooru.com": "Gelbooru",
    "img.gelbooru.com": "Gelbooru",
    "img2.gelbooru.com": "Gelbooru",
    "img3.gelbooru.com": "Gelbooru",
    "konachan.com": "Konachan",
    "konachan.net": "Konachan",
    "safebooru.org": "Safebooru",
    "zerochan.net": "Zerochan",
    "s1.zerochan.net": "Zerochan",
    "static.zerochan.net": "Zerochan",
    "danbooru.donmai.us": "Danbooru",
    "cdn.donmai.us": "Danbooru",
    "aibooru.online": "Aibooru",
    "tbib.org": "TBIB",
    "rule34.xxx": "Rule34",
    "e621.net": "e621",
}

KNOWN_HOST_MAP = {
    "pinterest": "Pinterest",
    "pinimg.com": "Pinterest",
    "pin.it": "Pinterest",
    "twitter.com": "Twitter/X",
    "x.com": "Twitter/X",
    "twimg.com": "Twitter/X",
    "fxtwitter.com": "Twitter/X",
    "vxtwitter.com": "Twitter/X",
    "reddit.com": "Reddit",
    "redd.it": "Reddit",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "tiktok.com": "TikTok",
    "instagram.com": "Instagram",
    "pixiv.net": "Pixiv",
    "pximg.net": "Pixiv",
    "artstation.com": "ArtStation",
    "deviantart.com": "DeviantArt",
    "deviantart.net": "DeviantArt",
    "catbox.moe": "Catbox",
    "imgur.com": "Imgur",
    "discord": "Discord",
    "telegram": "Telegram",
    "t.me": "Telegram",
    "vk.com": "VK",
    "vk.me": "VK",
    "threads.net": "Threads",
    "tumblr.com": "Tumblr",
    "twitch.tv": "Twitch",
    "soundcloud.com": "SoundCloud",
    "vimeo.com": "Vimeo",
}

COMMON_CDN_PREFIXES = (
    "www.", "cdn.", "media.", "images.", "image.", "img.",
    "static.", "assets.", "files.", "file.", "upload.", "uploads.", "public."
)


def clean_domain_name(netloc: str) -> str:
    """Очищає хост від службових портів та типових cdn/images префіксів для красивого відображення сайту."""
    host = netloc.split(":")[0].lower().strip()
    if not host:
        return "Web"

    # Якщо це відомий хост, повертаємо його назву
    for key, name in KNOWN_HOST_MAP.items():
        if key in host:
            return name

    # Зрізаємо префікси на кшталт cdn., images., files.
    for pfx in COMMON_CDN_PREFIXES:
        if host.startswith(pfx) and len(host) > len(pfx):
            sub = host[len(pfx):]
            if "." in sub:
                host = sub
            break

    # Форматуємо домен: першу літеру з великої
    parts = host.split(".")
    if len(parts) >= 2:
        parts[0] = parts[0].capitalize()
        return ".".join(parts)
    return host.capitalize()


def detect_source_platform(
    url: str | None = None,
    name: str | None = None,
    tags: list[str] | None = None,
    existing_platform: str | None = None,
    default: str | None = None,
) -> str:
    """
    Визначає реальну платформу або назву сайту-джерела за URL, ім'ям файлу чи тегами.
    НІКОЛИ не повертає 'direct' для Booru або звичайних сайтів.
    """
    # Якщо вже є валідне значення платформи (не direct / unknown / generic)
    if existing_platform:
        clean_p = str(existing_platform).strip()
        if clean_p.lower() not in ("direct", "direct_stream", "unknown", "none", ""):
            return clean_p

    raw_url = str(url or "").strip()

    # 1. Спеціальні booru префікси
    if raw_url.startswith(("booru:", "yande.re:", "konachan:", "safebooru:", "zerochan:", "gelbooru:", "danbooru:")):
        pfx = raw_url.split(":", 1)[0].lower()
        if pfx == "booru":
            rest = raw_url.split(":", 1)[1]
            if ":" in rest:
                pfx = rest.split(":", 1)[0].lower()
        for b_key, b_val in BOORU_HOST_MAP.items():
            if pfx in b_key:
                return b_val
        return pfx.capitalize()

    # 2. Перевірка хоста з URL
    if raw_url.startswith(("http://", "https://", "//")):
        try:
            parsed = urlparse(raw_url)
            host = (parsed.netloc or "").lower().split(":")[0]

            # Перевірка на Booru сайти
            for b_host, b_name in BOORU_HOST_MAP.items():
                if b_host in host:
                    return b_name

            # Перевірка на інші відомі сервіси
            for k_host, k_name in KNOWN_HOST_MAP.items():
                if k_host in host:
                    return k_name

            # Звичайний веб-сайт: повертаємо домен із великої літери
            if host:
                return clean_domain_name(host)
        except Exception:
            pass

    # 3. Аналіз імені файлу або тегів (якщо URL відсутній або був прямим)
    name_lower = str(name or "").lower()
    tags_lower = [str(t).lower() for t in (tags or [])]

    for b_key, b_name in BOORU_HOST_MAP.items():
        base = b_key.split(".")[0]
        if b_key in name_lower or base in name_lower or b_key in tags_lower or base in tags_lower:
            return b_name

    for k_key, k_name in KNOWN_HOST_MAP.items():
        base = k_key.split(".")[0]
        if k_key in name_lower or base in name_lower or k_key in tags_lower or base in tags_lower:
            return k_name

    if default and default.lower() not in ("direct", "direct_stream", "unknown", "none", ""):
        return default

    return "Web"


def get_image_dimensions(file_path: Path) -> tuple[int | None, int | None]:
    """Швидко витягує розміри (width, height) із заголовка файлу за частки мілісекунди."""
    try:
        with open(file_path, "rb") as f:
            head = f.read(1024)
            if len(head) < 24:
                return None, None

            # PNG
            if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
                w, h = struct.unpack(">II", head[16:24])
                return w, h

            # GIF
            if head.startswith((b"GIF87a", b"GIF89a")) and len(head) >= 10:
                w, h = struct.unpack("<HH", head[6:10])
                return w, h

            # WebP
            if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
                if head[12:16] == b"VP8 ":
                    w, h = struct.unpack("<HH", head[26:30])
                    return w & 0x3FFF, h & 0x3FFF
                elif head[12:16] == b"VP8L":
                    b0, b1, b2, b3 = head[21:25]
                    w = 1 + (((b1 & 0x3F) << 8) | b0)
                    h = 1 + (((b3 & 0xF) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
                    return w, h
                elif head[12:16] == b"VP8X" and len(head) >= 30:
                    w = 1 + int.from_bytes(head[24:27], "little")
                    h = 1 + int.from_bytes(head[27:30], "little")
                    return w, h

            # JPEG
            if head.startswith(b"\xff\xd8"):
                f.seek(0)
                data = f.read(65536)
                idx = 2
                while idx < len(data) - 9:
                    if data[idx] != 0xFF:
                        idx += 1
                        continue
                    marker = data[idx + 1]
                    if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        h, w = struct.unpack(">HH", data[idx + 5 : idx + 9])
                        return w, h
                    length = struct.unpack(">H", data[idx + 2 : idx + 4])[0]
                    idx += 2 + length
    except Exception:
        pass
    return None, None

