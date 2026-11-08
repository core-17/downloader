import asyncio
from dataclasses import dataclass
import html
import logging
from pathlib import Path
import re
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from downloader.app.config.constants import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    URL_REGEX,
    VIDEO_EXTENSIONS,
)
from downloader.app.config.settings import get_settings
from downloader.app.connect.telegram.handlers.search import record_task
from downloader.app.connect.web.state import broadcast_progress, downloader
from downloader.app.core.dto.task import TaskProgress, TaskStatus
from downloader.app.service.compression.transcoder import process_image

logger = logging.getLogger("downloader.discord")
_settings = get_settings()

BOORU_INLINE_REGEX = re.compile(r"\b(?:booru|yande\.re):[^\s<>\"']+", re.IGNORECASE)
HASHTAG_REGEX = re.compile(r"#([a-zA-Z0-9_\u0400-\u04FF]+)")
# Discord free standard limit is 10 MB (or 25 MB on boosted/newer servers). Safe default is 10 MB.
DISCORD_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@dataclass
class DiscordUserPrefs:
    quality: str = "1080p"
    image_format: str = "original"
    image_max_side: int | None = None
    dual_thread_delivery: bool = True  # Якщо існує гілка під тег, надсилати і в неї, і в дефолтну

    @property
    def max_height(self) -> int:
        from downloader.app.config.constants import QUALITY_HEIGHT_MAP

        if self.quality.lower() in ("best", "original", "max"):
            return 0
        return QUALITY_HEIGHT_MAP.get(self.quality.lower(), 1080)


_discord_user_prefs: dict[int, DiscordUserPrefs] = {}


def get_discord_user_prefs(user_id: int) -> DiscordUserPrefs:
    if user_id not in _discord_user_prefs:
        _discord_user_prefs[user_id] = DiscordUserPrefs(
            quality=_settings.DEFAULT_VIDEO_QUALITY.lower(),
            image_format="original",
            image_max_side=None,
            dual_thread_delivery=True,
        )
    return _discord_user_prefs[user_id]


def extract_urls_and_tags_from_text(text: str) -> tuple[list[str], list[str]]:
    raw_text = (text or "").strip()
    urls: list[str] = []
    for m in URL_REGEX.findall(raw_text):
        cleaned = m.rstrip(".,;:!?)>]}")
        if cleaned not in urls:
            urls.append(cleaned)

    for bm in BOORU_INLINE_REGEX.findall(raw_text):
        cleaned = bm.rstrip(".,;:!?)>]}")
        if cleaned not in urls:
            urls.append(cleaned)

    tags: list[str] = []
    for tag in HASHTAG_REGEX.findall(raw_text):
        if tag not in tags:
            tags.append(tag)
    return urls, tags


async def sync_discord_progress(prog: TaskProgress) -> None:
    record_task(prog)
    try:
        await broadcast_progress(prog)
    except Exception:
        pass

    # Асинхронний non-blocking ping веб-сервера через aiohttp (fire-and-forget)
    try:
        async def _notify_web():
            try:
                import aiohttp
                timeout = aiohttp.ClientTimeout(total=0.8)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    await session.post("http://127.0.0.1:8000/api/v1/internal/broadcast", json=prog.model_dump(mode="json"))
            except Exception:
                pass
        asyncio.create_task(_notify_web())
    except Exception:
        pass


def is_user_allowed(user_id: int) -> bool:
    allowed = _settings.DISCORD_ALLOWED_USERS
    if not allowed:
        return True
    return user_id in allowed


class DownloaderDiscordBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        # Реєструємо слеш-команди глобально
        try:
            await self.tree.sync()
            logger.info("🌲 Discord Application Slash Commands синхронізовано.")
        except Exception as exc:
            logger.warning("Не вдалося синхронізувати команди Discord: %s", exc)

    async def on_ready(self) -> None:
        logger.info("🚀 Discord-бот успішно підключено як %s (ID: %s)", self.user, self.user.id if self.user else "N/A")
        try:
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name="завантаження медіа | !help",
            )
            await self.change_presence(activity=activity)
        except Exception:
            pass


bot = DownloaderDiscordBot()


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFound):
        # Ігноруємо невизначені команди, щоб не засмічувати логи
        return
    logger.error("Помилка виконання команди Discord: %s", error)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    # Перевірка білого списку
    if not is_user_allowed(message.author.id):
        return

    text = message.content or ""
    urls, tags = extract_urls_and_tags_from_text(text)

    # 1. Обробка прямих вкладень (файли/картинки, прикріплені до повідомлення)
    if message.attachments:
        asyncio.create_task(handle_discord_attachments(message, tags))

    # 2. Обробка знайдених посилань (YouTube, TikTok, Twitter, Booru тощо)
    if urls:
        for u in urls:
            asyncio.create_task(process_discord_url(message, u, tags))

    await bot.process_commands(message)


async def handle_discord_attachments(message: discord.Message, tags: list[str]) -> None:
    """Зберігає прикріплені файли у локальне сховище та застосовує налаштування транскодування."""
    prefs = get_discord_user_prefs(message.author.id)
    try:
        await message.add_reaction("👀")
    except Exception:
        pass

    for attachment in message.attachments:
        task_id = str(uuid.uuid4())[:8]
        task_dir = _settings.DOWNLOAD_TEMP_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        dest_file = task_dir / attachment.filename
        progress = TaskProgress(
            task_id=task_id,
            url=attachment.url,
            status=TaskStatus.DOWNLOADING,
            title=attachment.filename,
            source_platform="discord_upload",
            file_name=attachment.filename,
            tags=tags,
            quality=prefs.quality,
            percent=10.0,
        )
        await sync_discord_progress(progress)

        try:
            await attachment.save(dest_file)
            saved_paths = [dest_file]

            # Транскодування фото за потреби
            if dest_file.suffix.lower() in IMAGE_EXTENSIONS and (
                prefs.image_format != "original" or prefs.image_max_side
            ):
                converted = await process_image(
                    dest_file,
                    target_format=prefs.image_format,
                    max_side=prefs.image_max_side,
                )
                if converted and converted.exists():
                    saved_paths = [converted]

            final_paths: list[str] = []
            for p in saved_paths:
                vault_path = await downloader.storage.save_file(
                    p,
                    subfolder="discord",
                    title=attachment.filename,
                    source_url=attachment.url,
                    source_platform="discord_upload",
                    tags=list(dict.fromkeys(["discord", "discord_upload", *(tags or [])])),
                )
                final_paths.append(str(vault_path))

            progress.status = TaskStatus.FINISHED
            progress.percent = 100.0
            progress.file_paths = final_paths
            progress.file_path = final_paths[0] if final_paths else None
            await sync_discord_progress(progress)

            try:
                await message.add_reaction("✅")
            except Exception:
                pass

        except Exception as exc:
            logger.error("Помилка збереження вкладення Discord: %s", exc)
            progress.status = TaskStatus.ERROR
            progress.error_message = str(exc)
            await sync_discord_progress(progress)
            try:
                await message.add_reaction("❌")
            except Exception:
                pass


async def process_discord_url(
    message: discord.Message,
    url: str,
    tags: list[str],
) -> None:
    """Завантажує медіа за посиланням через універсальний диспетчер і надсилає назад."""
    prefs = get_discord_user_prefs(message.author.id)
    task_id = str(uuid.uuid4())[:8]

    try:
        await message.add_reaction("👀")
    except Exception:
        pass

    status_msg = await message.reply(
        f"⏳ **Завантаження розпочато** (`{prefs.quality.upper()}`)...\n<{url}>",
        mention_author=False,
    )

    async def on_progress(p: TaskProgress) -> None:
        if tags and not p.tags:
            p.tags = tags
        await sync_discord_progress(p)

    try:
        result = await downloader.download(
            url=url,
            max_height=prefs.max_height,
            task_id=task_id,
            progress_callback=on_progress,
            extra_tags=list(dict.fromkeys(["discord", *(tags or [])])),
        )

        if result.status == TaskStatus.FINISHED and (result.file_paths or result.file_path):
            try:
                await message.add_reaction("✅")
            except Exception:
                pass

            file_paths = [Path(p) for p in result.file_paths if Path(p).exists()]
            if not file_paths and result.file_path and Path(result.file_path).exists():
                file_paths = [Path(result.file_path)]

            # Транскодування фото за потребою
            processed_paths: list[Path] = []
            for fp in file_paths:
                if fp.suffix.lower() in IMAGE_EXTENSIONS and (
                    prefs.image_format != "original" or prefs.image_max_side
                ):
                    conv = await process_image(
                        fp,
                        target_format=prefs.image_format,
                        max_side=prefs.image_max_side,
                    )
                    processed_paths.append(conv if conv and conv.exists() else fp)
                else:
                    processed_paths.append(fp)

            await deliver_discord_files(message, status_msg, result, processed_paths)

        else:
            err = result.error_message or "Невідома помилка завантаження"
            try:
                await message.add_reaction("❌")
            except Exception:
                pass
            await status_msg.edit(content=f"❌ **Помилка завантаження:** {err}")

    except Exception as exc:
        logger.exception("Виняток при завантаженні у Discord: %s", exc)
        try:
            await message.add_reaction("❌")
        except Exception:
            pass
        await status_msg.edit(content=f"❌ **Помилка:** {exc}")


async def deliver_discord_files(
    orig_message: discord.Message,
    status_message: discord.Message,
    progress: TaskProgress,
    files: list[Path],
) -> None:
    """Відправляє завантажені файли у канал або повідомляє, якщо файл збережено локально."""
    title = (progress.title or "Медіафайл")[:180]
    platform = f" [{progress.source_platform}]" if progress.source_platform else ""
    tags_line = ("\n🏷️ " + " ".join(f"#{t}" for t in progress.tags[:10])) if progress.tags else ""
    caption = f"**{title}**{platform}\n🔗 <{progress.url}>{tags_line}"

    oversized = [p for p in files if p.stat().st_size > DISCORD_MAX_UPLOAD_BYTES]
    sendable = [p for p in files if p.stat().st_size <= DISCORD_MAX_UPLOAD_BYTES]

    # Видаляємо статус-повідомлення 'Завантаження розпочато...'
    try:
        await status_message.delete()
    except Exception:
        pass

    # Якщо файли завеликі для Discord — сповіщаємо, що вони збережені в Vault
    if oversized:
        vault_info = "\n".join(
            f"• `{p.name}` ({round(p.stat().st_size / (1024 * 1024), 1)} MB) -> `{p}`"
            for p in oversized
        )
        await orig_message.reply(
            f"💾 **Файл перевищує ліміт Discord (10 MB) та надійно збережений у сховищі:**\n"
            f"{vault_info}\n\n{caption}",
            mention_author=False,
        )

    if not sendable:
        return

    # Discord підтримує до 10 вкладень в одному повідомленні
    for i in range(0, len(sendable), 10):
        chunk = sendable[i : i + 10]
        discord_files = [discord.File(fp, filename=fp.name) for fp in chunk]
        chunk_caption = caption if i == 0 else None
        await orig_message.reply(
            content=chunk_caption or "",
            files=discord_files,
            mention_author=False,
        )


async def get_vault_tags_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Динамічні підказки тегів сховища при введенні у слеш-командах."""
    current_lower = (current or "").strip().lower().lstrip("#")
    results: list[app_commands.Choice[str]] = []
    try:
        special_choices = [
            ("📁 Тип: booru (ілюстрації Yande.re)", "booru"),
            ("🎬 Тип: video (відео та кліпи)", "video"),
            ("🖼️ Тип: image (зображення та фото)", "image"),
            ("🎵 Тип: audio (музика та треки)", "audio"),
        ]
        for label, val in special_choices:
            if not current_lower or current_lower in val:
                results.append(app_commands.Choice(name=label[:100], value=val))

        files = await downloader.storage.list_files()
        tag_counts: dict[str, int] = {}
        for f in files:
            for t in f.tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1

        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        for t, count in sorted_tags:
            if not current_lower or current_lower in t.lower():
                display_name = f"#{t} ({count} файлів)"[:100]
                results.append(app_commands.Choice(name=display_name, value=t[:100]))
                if len(results) >= 25:
                    break

        return results[:25]
    except Exception as exc:
        logger.error("Помилка autocomplete в Discord: %s", exc)
        return results[:25]


async def get_booru_tags_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Динамічні підказки для пошуку на Booru (Yande.re)."""
    current_lower = (current or "").strip().lower().lstrip("#")
    results: list[app_commands.Choice[str]] = []
    try:
        # Спочатку шукаємо через API Booru-сервісу
        suggestions = await downloader.booru_service.search_tags(query=current_lower, limit=25)
        for s in suggestions:
            name = s.get("name", "")
            cnt = s.get("count", 0)
            lbl = s.get("type_label", "Тег")
            display = f"{name} ({cnt}) [{lbl}]"[:100]
            results.append(app_commands.Choice(name=display, value=name[:100]))
            if len(results) >= 25:
                break
        return results[:25]
    except Exception as exc:
        logger.error("Помилка Booru autocomplete: %s", exc)
        return results[:25]


def find_existing_tag_thread(guild: discord.Guild | None, tag: str) -> discord.Thread | None:
    """Шукає вже створену активну гілку під вказаний тег."""
    if not guild or not tag:
        return None
    cleaned = tag.strip().lower().lstrip("#")
    if not cleaned:
        return None

    try:
        for th in guild.threads:
            if th.archived:
                continue
            th_name = th.name.lower()
            if cleaned == th_name or f"#{cleaned}" in th_name or f"🏷️ {cleaned}" in th_name:
                return th
    except Exception:
        pass
    return None


def detect_file_media_category(item) -> str:
    """Визначає базову категорію файлу (booru, video, image, audio, document)."""
    platform = str(getattr(item, "source_platform", "") or "").lower()
    name = str(getattr(item, "name", "") or "").lower()

    if "yande.re" in platform or "booru" in platform or name.startswith("yande.re_") or "booru" in name:
        return "booru"

    ext = Path(name).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    return "document"


def determine_category_name(files: list, query: str = "", use_tag_as_thread: bool = False) -> str:
    """
    Визначає назву цільової гілки:
    - За замовчуванням (дефолт): завжди базова категорія (🌸 Booru Сховище, 🎬 Відео Сховище, 🖼️ Зображення Сховище, 🎵 Музика Сховище).
    - Тільки якщо користувач явно вказав прапорець (use_tag_as_thread=True, --tag / -t): назва гілки формується за тегом (🏷️ <Тег>).
    """
    q = (query or "").strip().lower()

    # Якщо користувач явно забажав створити гілку за введеним тегом
    if use_tag_as_thread and q:
        if "booru" in q or "yande" in q:
            return f"🌸 Booru: {q}"
        return f"🏷️ {q.capitalize()}"

    # Дефолтний розподіл за категоріями медіа
    categories = {detect_file_media_category(f) for f in files}

    if "booru" in categories and (len(categories) == 1 or q.startswith("booru") or q.startswith("yande")):
        return "🌸 Booru Сховище"

    if len(categories) == 1:
        cat = list(categories)[0]
        if cat == "booru":
            return "🌸 Booru Сховище"
        if cat == "video":
            return "🎬 Відео Сховище"
        if cat == "image":
            return "🖼️ Зображення Сховище"
        if cat == "audio":
            return "🎵 Музика Сховище"
        return "📁 Документи Сховище"

    if any(c == "booru" for c in categories):
        return "🌸 Booru Сховище"

    return "📁 Сховище файлів"


async def resolve_thread_targets(
    channel_or_msg,
    target_identifiers: list[str],
    default_name: str,
) -> list[discord.Thread | discord.abc.Messageable]:
    """Знаходить існуючі гілки (Threads) за згадкою <#ID>, ID або назвою; або створює нову гілку з цією назвою."""
    base_channel = getattr(channel_or_msg, "channel", channel_or_msg)
    guild = getattr(base_channel, "guild", None)

    if not guild or not target_identifiers:
        # Якщо цільові гілки не вказані — використовуємо гілку за замовчуванням у поточному каналі
        th = await get_or_create_destination_thread(base_channel, default_name)
        return [th]

    resolved: list[discord.Thread | discord.abc.Messageable] = []

    # Отримуємо всі активні гілки на сервері
    active_threads: list[discord.Thread] = []
    try:
        active_threads = list(guild.threads)
    except Exception:
        pass

    for ident in target_identifiers:
        cleaned = ident.strip().lstrip("#")
        found_thread: discord.Thread | None = None

        if cleaned.isdigit():
            tid = int(cleaned)
            # 1. Перевірка прямого ID гілки
            found_thread = guild.get_thread(tid)
            if not found_thread and hasattr(guild, "get_channel_or_thread"):
                obj = guild.get_channel_or_thread(tid)
                if isinstance(obj, discord.Thread):
                    found_thread = obj

        # 2. Пошук за назвою серед відкритих гілок
        if not found_thread:
            for th in active_threads:
                if not th.archived and (th.name.lower() == cleaned.lower() or cleaned.lower() in th.name.lower()):
                    found_thread = th
                    break

        # 3. Якщо знайдено текстовий канал замість гілки — створюємо гілку з такою назвою всередині нього
        if not found_thread:
            matched_channel: discord.TextChannel | None = None
            if cleaned.isdigit():
                matched_channel = guild.get_channel(int(cleaned))
            if not matched_channel:
                for tch in guild.text_channels:
                    if tch.name.lower() == cleaned.lower():
                        matched_channel = tch
                        break

            if matched_channel:
                found_thread = await get_or_create_destination_thread(matched_channel, default_name)

        # 4. Якщо нічого не знайдено — створюємо нову гілку з назвою 'cleaned' у поточному каналі
        if not found_thread and hasattr(base_channel, "create_thread"):
            clean_thread_name = cleaned[:95] if not cleaned.isdigit() else default_name
            found_thread = await get_or_create_destination_thread(base_channel, clean_thread_name)

        if found_thread and found_thread not in resolved:
            resolved.append(found_thread)

    return resolved if resolved else [await get_or_create_destination_thread(base_channel, default_name)]


async def get_or_create_destination_thread(
    channel_or_msg,
    thread_name: str,
) -> discord.Thread | discord.abc.Messageable:
    """Знаходить існуючу активну гілку з такою назвою або створює нову гілку для категорії."""
    channel = getattr(channel_or_msg, "channel", channel_or_msg)

    # Якщо це вже гілка або приватне повідомлення (DM) — надсилаємо напряму
    if isinstance(channel, (discord.Thread, discord.DMChannel)):
        return channel

    guild = getattr(channel, "guild", None)
    if not guild or not hasattr(channel, "create_thread"):
        return channel

    # Шукаємо вже існуючу незакриту гілку з цією назвою на каналі
    try:
        if hasattr(channel, "threads"):
            for active_thread in channel.threads:
                if not active_thread.archived and active_thread.name.lower() == thread_name.lower():
                    return active_thread
    except Exception:
        pass

    # Створюємо нову публічну гілку каналу
    try:
        new_thread = await channel.create_thread(
            name=thread_name[:95],
            auto_archive_duration=1440,  # 24 години
        )
        return new_thread
    except Exception as exc:
        logger.warning("Не вдалося створити гілку '%s': %s. Використовуємо звичайний канал.", thread_name, exc)
        return channel


@bot.command(name="help", aliases=["рудз", "допомога", "хелп"])
async def cmd_help(ctx: commands.Context) -> None:
    if not is_user_allowed(ctx.author.id):
        return

    embed = discord.Embed(
        title="📥 Downloader Vault Bot — Довідка",
        description="Універсальний завантажувач медіафайлів для Discord.",
        color=0x5865F2,
    )
    embed.add_field(
        name="🔗 Завантаження за посиланням",
        value="Просто надішліть посилання на YouTube, TikTok, Reddit, Pinterest, Twitter/X, Booru у чат. Разом із посиланням можна додавати хештеги `#тег`.",
        inline=False,
    )
    embed.add_field(
        name="🌸 Yande.re Booru",
        value="`!booru <теги> [кількість]`\nПриклад: `!booru landscape 5` або `booru:genshin 3`",
        inline=False,
    )
    embed.add_field(
        name="📁 Сховище (Vault)",
        value="`!vault` — показати останні збережені файли\n`!vault <тег> [к-сть]` — надіслати збережені файли за тегом у чат",
        inline=False,
    )
    embed.add_field(
        name="⚙️ Налаштування якості",
        value="`!settings` — переглянути поточні параметри\n`!quality <1080p|720p|best>` — змінити роздільність відео",
        inline=False,
    )
    embed.add_field(
        name="🆔 Мій ID",
        value="`!myid` — показує ваш Discord User ID",
        inline=True,
    )
    await ctx.reply(embed=embed, mention_author=False)


@bot.command(name="myid")
async def cmd_myid(ctx: commands.Context) -> None:
    await ctx.reply(f"🆔 Ваш Discord User ID: `{ctx.author.id}`", mention_author=False)


@bot.command(name="settings")
async def cmd_settings(ctx: commands.Context) -> None:
    if not is_user_allowed(ctx.author.id):
        return

    prefs = get_discord_user_prefs(ctx.author.id)
    embed = discord.Embed(
        title="⚙️ Налаштування завантаження (Discord)",
        color=0x5865F2,
    )
    embed.add_field(name="🎬 Якість відео", value=f"`{prefs.quality.upper()}`", inline=True)
    embed.add_field(name="🖼️ Формат фото", value=f"`{prefs.image_format.upper()}`", inline=True)
    side_str = f"{prefs.image_max_side} px" if prefs.image_max_side else "Оригінал"
    embed.add_field(name="📐 Макс. сторона фото", value=f"`{side_str}`", inline=True)
    embed.add_field(
        name="🔀 Авто-дублювання у гілку тегу",
        value="`УВІМКНЕНО (і в дефолтну, і в гілку тегу)`" if prefs.dual_thread_delivery else "`ВИМКНЕНО (тільки в одну)`",
        inline=False,
    )
    embed.set_footer(text="Зміна: !dualthread on|off, !quality 1080p, !quality best")
    await ctx.reply(embed=embed, mention_author=False)


@bot.command(name="dualthread")
async def cmd_dualthread(ctx: commands.Context, state: str = "") -> None:
    """Перемикання дуальної доставки: !dualthread on або !dualthread off."""
    if not is_user_allowed(ctx.author.id):
        return

    prefs = get_discord_user_prefs(ctx.author.id)
    s = state.strip().lower()
    if s in ("on", "true", "1", "так", "увімк"):
        prefs.dual_thread_delivery = True
        await ctx.reply("✅ Авто-дублювання **увімкнено**: якщо існує гілка під тег, файли надсилатимуться і в неї, і в дефолтну категорію.", mention_author=False)
    elif s in ("off", "false", "0", "ні", "вимк"):
        prefs.dual_thread_delivery = False
        await ctx.reply("⏹️ Авто-дублювання **вимкнено**: файли надсилатимуться лише в одну цільову гілку.", mention_author=False)
    else:
        status_text = "увімкнено" if prefs.dual_thread_delivery else "вимкнено"
        await ctx.reply(f"ℹ️ Поточний стан авто-дублювання: **{status_text}**.\nДля зміни: `!dualthread on` або `!dualthread off`", mention_author=False)


@bot.command(name="quality")
async def cmd_quality(ctx: commands.Context, quality: str) -> None:
    if not is_user_allowed(ctx.author.id):
        return

    q = quality.strip().lower()
    valid_qualities = ["2160p", "1440p", "1080p", "720p", "480p", "360p", "best"]
    if q not in valid_qualities:
        await ctx.reply(
            f"❌ Невідома якість. Доступні: {', '.join(valid_qualities)}",
            mention_author=False,
        )
        return

    prefs = get_discord_user_prefs(ctx.author.id)
    prefs.quality = q
    await ctx.reply(f"✅ Встановлено якість відео: **{q.upper()}**", mention_author=False)


@bot.command(name="booru")
async def cmd_booru(ctx: commands.Context, *, args: str = "") -> None:
    """Завантаження з Yande.re Booru (!booru <теги> [кількість])."""
    if not is_user_allowed(ctx.author.id):
        return

    if not args.strip():
        await ctx.reply(
            "🌸 Використання: `!booru <теги> [кількість]`\nПриклад: `!booru landscape 5`",
            mention_author=False,
        )
        return

    tokens = args.strip().split()
    limit = 5
    if len(tokens) > 1 and tokens[-1].isdigit():
        limit = max(1, min(10, int(tokens.pop())))

    booru_tags = " ".join(tokens)
    target_url = f"booru:{booru_tags}?limit={limit}"
    tags = [t.lstrip("#") for t in tokens if not t.startswith("order:")]

    await process_discord_url(ctx.message, target_url, tags)


@bot.command(name="vault", aliases=["сховище", "файли"])
async def cmd_vault(ctx: commands.Context, *, args: str = "") -> None:
    """Перегляд сховища або масова відправка файлів (!vault [тег] [к-сть] [--tag-only | --tag] [thread:гілка])."""
    if not is_user_allowed(ctx.author.id):
        return

    raw_args = args.strip()
    prefs = get_discord_user_prefs(ctx.author.id)

    # 1. Прапорці:
    # --tag-only: тільки в гілку під тег (без дефолтної)
    # --tag / -t: створити гілку під тег
    tag_only = bool(re.search(r"(?:^|\s)(?:--tag-only|--only-tag)(?:\s|$)", raw_args, re.IGNORECASE))
    cleaned_args = re.sub(r"(?:^|\s)(?:--tag-only|--only-tag)(?:\s|$)", " ", raw_args, flags=re.IGNORECASE).strip()

    force_tag_thread = bool(re.search(r"(?:^|\s)(?:--tag|--as-tag|-t)(?:\s|$)", cleaned_args, re.IGNORECASE))
    cleaned_args = re.sub(r"(?:^|\s)(?:--tag|--as-tag|-t)(?:\s|$)", " ", cleaned_args, flags=re.IGNORECASE).strip()

    # 2. Витягуємо явні цільові гілки: thread:art, to:#music, to:<#123456789>
    target_thread_ids = re.findall(r"\b(?:thread|to):(?:<#)?#?([0-9a-zA-Z_\-]+)>?", cleaned_args, re.IGNORECASE)
    cleaned_args = re.sub(r"\b(?:thread|to):(?:<#)?#?([0-9a-zA-Z_\-]+)>?", "", cleaned_args, flags=re.IGNORECASE).strip()

    tokens = cleaned_args.split()
    batch_count: int | None = None
    if tokens and tokens[-1].isdigit():
        batch_count = max(1, min(50, int(tokens.pop())))
    query = " ".join(tokens).strip().lower().lstrip("#")

    files = await downloader.storage.list_files()
    if query:
        files = [
            f
            for f in files
            if query in f.name.lower()
            or (f.title and query in f.title.lower())
            or (f.source_platform and query in f.source_platform.lower())
            or (query in detect_file_media_category(f))
            or any(query in t.lower() for t in f.tags)
        ]

    if not files:
        if query:
            await ctx.reply(f"🔍 У сховищі не знайдено файлів за тегом `{query}`.", mention_author=False)
        else:
            await ctx.reply("📁 Сховище порожнє.", mention_author=False)
        return

    latest = sorted(files, key=lambda x: x.modified_ts, reverse=True)

    # Якщо користувач попросив надіслати n файлів у чат (!vault genshin 5 або !vault 10)
    if batch_count:
        sendable_items: list = []
        sendable_paths: list[Path] = []
        for sf in latest:
            p = downloader.storage.resolve_path(sf.relative_path)
            if p.exists() and p.stat().st_size <= DISCORD_MAX_UPLOAD_BYTES:
                sendable_items.append(sf)
                sendable_paths.append(p)
                if len(sendable_paths) == batch_count:
                    break

        if not sendable_paths:
            await ctx.reply(
                "⚠️ Усі знайдені файли перевищують ліміт Discord (10 MB). Завантажте їх через веб-інтерфейс.",
                mention_author=False,
            )
            return

        # Визначаємо дефолтну категорійну гілку
        default_thread_name = determine_category_name(sendable_items, query, use_tag_as_thread=force_tag_thread)

        # Перевіряємо, чи існує вже окрема відкрита гілка під цей тег
        existing_tag_thread = find_existing_tag_thread(ctx.guild, query) if query else None

        # Формуємо список гілок для надсилання
        dest_threads: list[discord.Thread | discord.abc.Messageable] = []

        if target_thread_ids:
            # Якщо користувач явно вказав цільові гілки
            dest_threads = await resolve_thread_targets(ctx.channel, target_thread_ids, default_thread_name)
        elif tag_only and existing_tag_thread:
            # Тільки в гілку тегу
            dest_threads = [existing_tag_thread]
        elif tag_only and query:
            tag_thread = await get_or_create_destination_thread(ctx.channel, f"🏷️ {query.capitalize()}")
            dest_threads = [tag_thread]
        else:
            # Дефолтна гілка категорії
            def_th = await get_or_create_destination_thread(ctx.channel, default_thread_name)
            dest_threads = [def_th]

            # Якщо існує гілка під цей тег і увімкнена дуальна доставка — автоматично додаємо і її!
            if existing_tag_thread and prefs.dual_thread_delivery and existing_tag_thread.id != getattr(def_th, "id", None):
                dest_threads.append(existing_tag_thread)

        dest_mentions = ", ".join(t.mention if hasattr(t, "mention") else str(t) for t in dest_threads)
        status_msg = await ctx.reply(
            f"📦 Відправляємо `{len(sendable_paths)}` файлів у {dest_mentions}...",
            mention_author=False,
        )

        for dest in dest_threads:
            for i in range(0, len(sendable_paths), 10):
                chunk = sendable_paths[i : i + 10]
                discord_files = [discord.File(p, filename=p.name) for p in chunk]
                header = f"📁 Файли зі сховища (`{query or 'останні'}`):" if i == 0 else None
                await dest.send(content=header or "", files=discord_files)

        try:
            await status_msg.edit(content=f"✅ `{len(sendable_paths)}` файлів успішно надіслано в {dest_mentions}!")
        except Exception:
            pass
        return

    # Інакше показуємо список останніх збережених файлів
    embed = discord.Embed(
        title="📁 Локальне сховище (Vault)",
        description=f"Всього файлів: **{len(files)}**" + (f" (фільтр: `{query}`)" if query else ""),
        color=0x5865F2,
    )
    for idx, f in enumerate(latest[:8], 1):
        name = f.title or f.name
        size_mb = round(f.size_bytes / (1024 * 1024), 2)
        tags_str = (" | #" + " #".join(f.tags[:3])) if f.tags else ""
        embed.add_field(
            name=f"{idx}. {name[:45]}",
            value=f"`{size_mb} MB` • {f.source_platform or 'локально'}{tags_str}",
            inline=False,
        )
    embed.set_footer(text="Для відправки файлів у чат напишіть: !vault <тег> <кількість>")
    await ctx.reply(embed=embed, mention_author=False)


# ==========================================
# Слеш-команди Discord (Slash Commands)
# ==========================================


@bot.tree.command(name="download", description="Завантажити медіа за посиланням")
@app_commands.describe(
    url="Посилання на YouTube, TikTok, Reddit, Booru тощо",
    tags="Хештеги через пробіл (наприклад: genshin art)",
)
async def slash_download(interaction: discord.Interaction, url: str, tags: str = "") -> None:
    if not is_user_allowed(interaction.user.id):
        await interaction.response.send_message("❌ У вас немає доступу до бота.", ephemeral=True)
        return

    parsed_tags = [t.lstrip("#") for t in tags.split()]
    await interaction.response.send_message(f"⏳ Прийнято в обробку: <{url}>", ephemeral=True)
    msg = await interaction.original_response()
    asyncio.create_task(process_discord_url(msg, url, parsed_tags))


@bot.tree.command(name="booru", description="Завантажити ілюстрації з Yande.re Booru")
@app_commands.describe(tags="Теги для пошуку", count="Кількість зображень (1-10)")
@app_commands.autocomplete(tags=get_booru_tags_autocomplete)
async def slash_booru(interaction: discord.Interaction, tags: str, count: int = 5) -> None:
    if not is_user_allowed(interaction.user.id):
        await interaction.response.send_message("❌ У вас немає доступу до бота.", ephemeral=True)
        return

    clamped_count = max(1, min(10, count))
    target_url = f"booru:{tags}?limit={clamped_count}"
    await interaction.response.send_message(
        f"🌸 Шукаємо `{clamped_count}` ілюстрацій з Yande.re за тегами `{tags}`...",
        ephemeral=True,
    )
    msg = await interaction.original_response()
    tag_list = [t.lstrip("#") for t in tags.split() if not t.startswith("order:")]
    asyncio.create_task(process_discord_url(msg, target_url, tag_list))


@bot.tree.command(name="vault", description="Переглянути або надіслати збережені файли зі сховища")
@app_commands.describe(
    tag="Фільтр за тегом або типом (booru, video, image, music)",
    count="Кількість файлів для надсилання у чат (опціонально)",
    tag_only="Надсилати виключно в гілку тегу без дефолтної (True/False)",
    thread="Цільова гілка для надсилання (опціонально)",
)
@app_commands.autocomplete(tag=get_vault_tags_autocomplete)
async def slash_vault(
    interaction: discord.Interaction,
    tag: str = "",
    count: int = 0,
    tag_only: bool = False,
    thread: discord.Thread | None = None,
) -> None:
    if not is_user_allowed(interaction.user.id):
        await interaction.response.send_message("❌ У вас немає доступу до бота.", ephemeral=True)
        return

    prefs = get_discord_user_prefs(interaction.user.id)
    query = tag.strip().lower().lstrip("#")
    files = await downloader.storage.list_files()
    if query:
        files = [
            f
            for f in files
            if query in f.name.lower()
            or (f.title and query in f.title.lower())
            or (f.source_platform and query in f.source_platform.lower())
            or (query in detect_file_media_category(f))
            or any(query in t.lower() for t in f.tags)
        ]

    if not files:
        msg = f"🔍 У сховищі не знайдено файлів за тегом `{query}`." if query else "📁 Сховище порожнє."
        await interaction.response.send_message(msg, ephemeral=True)
        return

    latest = sorted(files, key=lambda x: x.modified_ts, reverse=True)

    if count > 0:
        clamped = max(1, min(50, count))
        sendable_items: list = []
        sendable_paths: list[Path] = []
        for sf in latest:
            p = downloader.storage.resolve_path(sf.relative_path)
            if p.exists() and p.stat().st_size <= DISCORD_MAX_UPLOAD_BYTES:
                sendable_items.append(sf)
                sendable_paths.append(p)
                if len(sendable_paths) == clamped:
                    break

        if not sendable_paths:
            await interaction.response.send_message(
                "⚠️ Усі знайдені файли перевищують ліміт Discord (10 MB). Скористайтеся веб-інтерфейсом.",
                ephemeral=True,
            )
            return

        default_thread_name = determine_category_name(sendable_items, query, use_tag_as_thread=False)
        existing_tag_thread = find_existing_tag_thread(interaction.guild, query) if query else None

        dest_threads: list[discord.Thread | discord.abc.Messageable] = []

        if thread:
            dest_threads = [thread]
        elif tag_only and existing_tag_thread:
            dest_threads = [existing_tag_thread]
        elif tag_only and query:
            th = await get_or_create_destination_thread(interaction.channel, f"🏷️ {query.capitalize()}")
            dest_threads = [th]
        else:
            def_th = await get_or_create_destination_thread(interaction.channel, default_thread_name)
            dest_threads = [def_th]
            if existing_tag_thread and prefs.dual_thread_delivery and existing_tag_thread.id != getattr(def_th, "id", None):
                dest_threads.append(existing_tag_thread)

        dest_mentions = ", ".join(t.mention if hasattr(t, "mention") else str(t) for t in dest_threads)
        await interaction.response.send_message(
            f"📦 Відправляємо `{len(sendable_paths)}` файлів у {dest_mentions}...",
            ephemeral=True,
        )

        for dest in dest_threads:
            for i in range(0, len(sendable_paths), 10):
                chunk = sendable_paths[i : i + 10]
                dfiles = [discord.File(p, filename=p.name) for p in chunk]
                header = f"📁 Файли зі сховища (`{query or 'останні'}`):" if i == 0 else None
                await dest.send(content=header or "", files=dfiles)

        try:
            await interaction.edit_original_response(
                content=f"✅ `{len(sendable_paths)}` файлів успішно надіслано в {dest_mentions}!"
            )
        except Exception:
            pass
        return

    embed = discord.Embed(
        title="📁 Локальне сховище (Vault)",
        description=f"Всього знайдено файлів: **{len(files)}**" + (f" (фільтр: `{query}`)" if query else ""),
        color=0x5865F2,
    )
    for idx, f in enumerate(latest[:8], 1):
        name = f.title or f.name
        size_mb = round(f.size_bytes / (1024 * 1024), 2)
        tags_str = (" | #" + " #".join(f.tags[:3])) if f.tags else ""
        embed.add_field(
            name=f"{idx}. {name[:45]}",
            value=f"`{size_mb} MB` • {f.source_platform or 'локально'}{tags_str}",
            inline=False,
        )
    embed.set_footer(text="Щоб надіслати файли у чат: /vault [tag] [count]")
    await interaction.response.send_message(embed=embed)


# ==========================================
# Життєвий цикл запуску Discord-бота
# ==========================================


async def run_discord_bot() -> None:
    """Запускає Discord бота, якщо у конфігурації присутній DISCORD_BOT_TOKEN."""
    settings = get_settings()
    if not settings.DISCORD_BOT_TOKEN:
        logger.info("ℹ️ DISCORD_BOT_TOKEN не вказано — Discord-бот деактивовано.")
        return

    token = settings.DISCORD_BOT_TOKEN.get_secret_value().strip()
    if not token or token == "your_discord_bot_token_here":
        logger.info("ℹ️ DISCORD_BOT_TOKEN не задано або містить плейсхолдер — Discord-бот деактивовано.")
        return

    logger.info("🚀 Запуск Discord-бота...")
    try:
        await bot.start(token)
    except asyncio.CancelledError:
        logger.info("🛑 Процес Discord-бота скасовано.")
    except Exception as exc:
        logger.error("Помилка роботи Discord-бота: %s", exc)
    finally:
        if not bot.is_closed():
            await bot.close()


def main() -> None:
    asyncio.run(run_discord_bot())


if __name__ == "__main__":
    main()

