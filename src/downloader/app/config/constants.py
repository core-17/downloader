import re

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_HTTP_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
}

IMAGE_EXTENSIONS: set[str] = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".avif",
    ".tiff",
    ".svg",
    ".jfif",
}

VIDEO_EXTENSIONS: set[str] = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".avi",
    ".flv",
    ".m4v",
    ".ts",
}

AUDIO_EXTENSIONS: set[str] = {
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".flac",
    ".wav",
}

DOCUMENT_EXTENSIONS: set[str] = {
    ".pdf",
    ".epub",
    ".mobi",
    ".djvu",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".iso",
    ".apk",
    ".docx",
    ".xlsx",
    ".pptx",
}

DIRECT_MEDIA_DOMAINS: set[str] = {
    "i.pinimg.com",
    "v1.pinimg.com",
    "pbs.twimg.com",
    "video.twimg.com",
    "i.redd.it",
    "preview.redd.it",
    "v.redd.it",
    "i.imgur.com",
    "images.unsplash.com",
    "cdn.discordapp.com",
    "media.discordapp.net",
}

MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "audio/wav": ".wav",
    "application/pdf": ".pdf",
    "application/epub+zip": ".epub",
    "application/zip": ".zip",
}

# Ліміти Telegram Bot API
TELEGRAM_MAX_BOT_API_FILE_BYTES: int = 50 * 1024 * 1024  # 50 МБ
TELEGRAM_MAX_PHOTO_BYTES: int = 10 * 1024 * 1024  # 10 МБ для sendPhoto

# Регулярні вирази для парсингу повідомлень
URL_REGEX = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
HASHTAG_REGEX = re.compile(r"#([\wа-яА-ЯіїєґІЇЄҐ0-9_]+)", re.UNICODE)

QUALITY_HEIGHT_MAP: dict[str, int] = {
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "2160p": 2160,
    "4k": 2160,
    "best": 4320,
}

