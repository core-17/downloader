#!/usr/bin/env bash
# ==============================================================================
# Downloader Ecosystem - Microservice Multi-Session Supervisor (tmux)
# Кожен великий сервіс запускається в окремій ізольованій сесії tmux:
# 1. 'web'      - FastAPI Web Server + WebSocket + Web UI
# 2. 'telegram' - Telegram Bot
# 3. 'discord'  - Discord Bot
# Ізоляція: якщо один сервіс падає або зависає, решта працює незалежно!
# ==============================================================================

PROJECT_DIR="/root/downloader"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
VENV_UVICORN="${PROJECT_DIR}/.venv/bin/uvicorn"

cd "$PROJECT_DIR" || exit 1

# Якщо в середовищі /tmp має некоректні права (unsafe permissions)
if tmux ls 2>&1 | grep -q "unsafe permissions"; then
    export TMUX_TMPDIR="${PROJECT_DIR}/.tmux_tmp"
    mkdir -p "$TMUX_TMPDIR" && chmod 700 "$TMUX_TMPDIR"
fi

case "$1" in
    start)
        echo "🚀 Запуск сервісів Downloader в ізольованих tmux-сесіях..."

        # 1. Web Server Session
        if tmux has-session -t web 2>/dev/null; then
            echo "ℹ️ Сесія 'web' вже запущена."
        else
            echo "🌐 Стартуємо Web Server (порт 8000)..."
            tmux new-session -d -s web "cd $PROJECT_DIR && PYTHONPATH=src $VENV_UVICORN downloader.app.main:app --host 0.0.0.0 --port 8000 --reload"
        fi

        sleep 1

        # 2. Telegram Bot Session
        if tmux has-session -t telegram 2>/dev/null; then
            echo "ℹ️ Сесія 'telegram' вже запущена."
        else
            echo "✈️ Стартуємо Telegram-бота..."
            tmux new-session -d -s telegram "cd $PROJECT_DIR && PYTHONPATH=src $VENV_PYTHON -m downloader.app.connect.telegram.bot"
        fi

        # 3. Discord Bot Session
        if tmux has-session -t discord 2>/dev/null; then
            echo "ℹ️ Сесія 'discord' вже запущена."
        else
            echo "🎮 Стартуємо Discord-бота..."
            tmux new-session -d -s discord "cd $PROJECT_DIR && PYTHONPATH=src $VENV_PYTHON -m downloader.app.connect.discord.bot"
        fi

        echo "✅ Всі сервіси запущені! Використовуйте: './manage_services.sh status'"
        ;;

    stop)
        echo "🛑 Зупинка сервісів..."
        tmux kill-session -t discord 2>/dev/null && echo " - Discord-бот зупинено"
        tmux kill-session -t telegram 2>/dev/null && echo " - Telegram-бот зупинено"
        tmux kill-session -t web 2>/dev/null && echo " - Web Server зупинено"
        echo "✅ Всі окремі сесії зупинено."
        ;;

    restart)
        $0 stop
        sleep 1
        $0 start
        ;;

    status)
        echo "📊 Поточний статус tmux-сесій:"
        for s in web telegram discord; do
            if tmux has-session -t "$s" 2>/dev/null; then
                echo "  🟢 $s: ПРАЦЮЄ (активна сесія tmux)"
            else
                echo "  ⚪ $s: ЗУПИНЕНО"
            fi
        done
        ;;

    logs)
        TARGET="${2:-web}"
        if tmux has-session -t "$TARGET" 2>/dev/null; then
            echo "📜 Останні логи для '$TARGET' (Ctrl+C для виходу):"
            tmux capture-pane -t "$TARGET" -p -S -50
        else
            echo "❌ Сесія '$TARGET' не знайдена."
        fi
        ;;

    *)
        echo "Використання: $0 {start|stop|restart|status|logs [web|telegram|discord]}"
        exit 1
        ;;
esac

