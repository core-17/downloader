import re
from urllib.parse import urlparse
import aiohttp

from downloader.app.config.constants import DEFAULT_HTTP_HEADERS
from downloader.app.core.dto.media import ExtractedMediaItem, ExtractedPageMedia, MediaType
from downloader.app.service.scrapers.base import BaseScraper

TWEET_ID_RE = re.compile(
    r"(?:twitter\.com|x\.com|fxtwitter\.com|vxtwitter\.com|fixupx\.com)/(?:[^/]+/status|i/web/status|status)/(\d+)",
    re.IGNORECASE,
)


class TwitterScraper(BaseScraper):
    """Ізольований скрапер для Twitter/X (FxTwitter, VxTwitter, Twitter Syndication API)."""

    def can_handle(self, url: str) -> bool:
        host = (urlparse(url).netloc or "").lower()
        return any(
            d in host
            for d in ("twitter.com", "x.com", "fxtwitter.com", "vxtwitter.com", "fixupx.com", "t.co")
        )

    async def _resolve_redirects(self, session: aiohttp.ClientSession, url: str) -> str:
        try:
            async with session.get(url, allow_redirects=True) as resp:
                return str(resp.url)
        except Exception:
            return url

    async def extract(self, url: str) -> ExtractedPageMedia | None:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(headers=DEFAULT_HTTP_HEADERS, timeout=timeout) as session:
            if "t.co/" in url:
                url = await self._resolve_redirects(session, url)

            match = TWEET_ID_RE.search(url)
            if not match:
                return None
            tweet_id = match.group(1)

            # 1. FxTwitter API
            try:
                fx_url = f"https://api.fxtwitter.com/status/{tweet_id}"
                async with session.get(fx_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tweet = data.get("tweet") or {}
                        media = tweet.get("media") or {}
                        all_media = media.get("all") or (media.get("photos", []) + media.get("videos", []))
                        items: list[ExtractedMediaItem] = []
                        for m in all_media:
                            m_url = m.get("url")
                            if not m_url:
                                continue
                            m_type = m.get("type", "photo")
                            if m_type in ("video", "gif"):
                                items.append(
                                    ExtractedMediaItem(
                                        url=m_url,
                                        media_type=MediaType.VIDEO,
                                        ext=".mp4",
                                    )
                                )
                            else:
                                items.append(
                                    ExtractedMediaItem(
                                        url=m_url,
                                        media_type=MediaType.IMAGE,
                                    )
                                )
                        if items:
                            author = (tweet.get("author") or {}).get("screen_name") or "x_user"
                            text = tweet.get("text") or f"Tweet {tweet_id}"
                            return ExtractedPageMedia(
                                source_url=url,
                                platform="Twitter/X",
                                title=f"@{author} - {text[:80]}",
                                description=text,
                                author=author,
                                items=items,
                            )
            except Exception:
                pass

            # 2. VxTwitter API
            try:
                vx_url = f"https://api.vxtwitter.com/Twitter/status/{tweet_id}"
                async with session.get(vx_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        media_ext = data.get("media_extended") or []
                        items = []
                        for m in media_ext:
                            m_url = m.get("url")
                            if not m_url:
                                continue
                            m_type = m.get("type", "image")
                            items.append(
                                ExtractedMediaItem(
                                    url=m_url,
                                    media_type=MediaType.VIDEO if m_type in ("video", "gif") else MediaType.IMAGE,
                                )
                            )
                        if items:
                            author = data.get("user_screen_name") or "x_user"
                            text = data.get("text") or f"Tweet {tweet_id}"
                            return ExtractedPageMedia(
                                source_url=url,
                                platform="Twitter/X",
                                title=f"@{author} - {text[:80]}",
                                description=text,
                                author=author,
                                items=items,
                            )
            except Exception:
                pass

            # 3. Twitter Syndication API
            try:
                syn_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=x"
                async with session.get(syn_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = []
                        for m in data.get("mediaDetails") or []:
                            m_type = m.get("type")
                            if m_type in ("video", "animated_gif"):
                                variants = (m.get("video_info") or {}).get("variants") or []
                                mp4s = [v for v in variants if v.get("content_type") == "video/mp4" and v.get("url")]
                                if mp4s:
                                    best_mp4 = max(mp4s, key=lambda v: v.get("bitrate", 0))
                                    items.append(
                                        ExtractedMediaItem(
                                            url=best_mp4["url"],
                                            media_type=MediaType.VIDEO,
                                            ext=".mp4",
                                        )
                                    )
                            else:
                                img_url = m.get("media_url_https")
                                if img_url:
                                    items.append(
                                        ExtractedMediaItem(
                                            url=img_url,
                                            media_type=MediaType.IMAGE,
                                        )
                                    )
                        if not items:
                            for p in data.get("photos") or []:
                                if p.get("url"):
                                    items.append(ExtractedMediaItem(url=p["url"], media_type=MediaType.IMAGE))
                        if items:
                            user = (data.get("user") or {}).get("screen_name") or "x_user"
                            text = data.get("text") or f"Tweet {tweet_id}"
                            return ExtractedPageMedia(
                                source_url=url,
                                platform="Twitter/X",
                                title=f"@{user} - {text[:80]}",
                                description=text,
                                author=user,
                                items=items,
                            )
            except Exception:
                pass

        return None

