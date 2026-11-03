import hashlib
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "igshid",
    "igsh",
    "si",
    "feature",
    "ref",
    "ref_src",
    "ref_url",
    "s",
    "t",
}


def normalize_url(url: str) -> str:
    """Очищує посилання від трекінгових параметрів для дедуплікації та коректної обробки."""
    raw = url.strip()
    try:
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        # Для YouTube не видаляємо 't' якщо це таймкод, але 'si' та 'feature' прибираємо
        query_items = []
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            kl = k.lower()
            if kl in TRACKING_QUERY_PARAMS:
                if kl == "t" and ("youtube.com" in host or "youtu.be" in host):
                    query_items.append((k, v))
                continue
            query_items.append((k, v))

        clean_query = urlencode(query_items, doseq=True)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                clean_query,
                "",  # прибираємо #fragment
            )
        )
    except Exception:
        return raw


def compute_file_sha256(file_path: Path) -> str:
    """Обчислює SHA-256 хеш локального файлу для другого етапу дедуплікації."""
    sha = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()

