import re
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from downloader.app.connect.web.state import STATIC_DIR

router = APIRouter(tags=["Web UI"])

INCLUDE_REGEX = re.compile(r'<!--\s*#include\s+virtual=["\']([^"\']+)["\']\s*-->')


def _render_full_html() -> str:
    """Збирає головний HTML із розділених файлів вкладок та модалок."""
    index_file = STATIC_DIR / "index.html"
    content = index_file.read_text(encoding="utf-8")

    def _replace_include(match: re.Match) -> str:
        rel_path = match.group(1).lstrip("/")
        # Якщо шлях починається зі static/, прибираємо його відносно STATIC_DIR
        if rel_path.startswith("static/"):
            rel_path = rel_path[len("static/") :]
        sub_file = STATIC_DIR / rel_path
        if sub_file.exists():
            return sub_file.read_text(encoding="utf-8")
        return f"<!-- Include missing: {rel_path} -->"

    return INCLUDE_REGEX.sub(_replace_include, content)


@router.get("/", response_class=HTMLResponse)
@router.get("/monitor", response_class=HTMLResponse)
async def serve_web_ui() -> HTMLResponse:
    html_content = _render_full_html()
    return HTMLResponse(html_content)
