import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from downloader.app.connect.web import STATIC_DIR, web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Життєвий цикл веб-сервера.
    Боти запускаються автономно в окремих tmux-сесіях для повної ізоляції:
    один впав — решта живе без блокувань та синхронних залежностей.
    Якщо встановлено RUN_EMBEDDED_BOTS=true — запускає ботів всередині процесу (legacy режим).
    """
    tasks = []
    if os.getenv("RUN_EMBEDDED_BOTS", "false").lower() in ("true", "1", "yes"):
        from downloader.app.connect.telegram.bot import run_bot
        from downloader.app.connect.discord.bot import run_discord_bot
        tasks.append(asyncio.create_task(run_bot(handle_signals=False)))
        tasks.append(asyncio.create_task(run_discord_bot()))

    try:
        yield
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Universal Media Downloader API",
        version="0.5.0",
        description="Асинхронний медіа-комбайн для YouTube, соцмереж, Booru (Yande.re), веб-сторінок та локального сховища.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(web_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("downloader.app.main:app", host="0.0.0.0", port=8000, reload=True)
