# -*- coding: utf-8 -*-
import os
import asyncio
import logging
import threading
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, BaseUpdateProcessor
from handlers import (
    start_command, newgame_command, join_command, status_command, cancel_command,
    callback_router, error_handler, post_init,
)
from health import run_web_server

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

class QueryResponsiveProcessor(BaseUpdateProcessor):
    """查詢可與遊戲操作並行；會改變牌局的更新仍依序處理。"""
    def __init__(self):
        super().__init__(32)
        self.action_lock = asyncio.Lock()

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_process_update(self, update, coroutine):
        query = getattr(update, "callback_query", None)
        data = (getattr(query, "data", None) or "").split("|", 1)[0]
        if data in {"mono_assets", "mono_status", "mono_map"}:
            await coroutine
        else:
            async with self.action_lock:
                await coroutine


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("請設定 BOT_TOKEN")

    threading.Thread(target=run_web_server, daemon=True).start()
    app = Application.builder().token(token).concurrent_updates(QueryResponsiveProcessor()).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("newgame", newgame_command))
    app.add_handler(CommandHandler("join", join_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(callback_router, pattern=r"^mono_"))
    app.add_error_handler(error_handler)
    logging.info("台灣大富翁 32格 Bot 啟動")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
