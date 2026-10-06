# -*- coding: utf-8 -*-
"""Telegram 指令與按鈕 Callback。"""
import asyncio
import logging
import random
from telegram import Update, BotCommand
from telegram.ext import ContextTypes, Application
from telegram.error import RetryAfter, TimedOut, NetworkError
from config import START_MONEY, MAX_PLAYERS, MIN_PLAYERS, JAIL_FINE
from board_data import BOARD
from models import Player, Game, games, user_to_chat
from helpers import find_game_by_user, current_player, total_asset_value, mortgage_value
from ui import lobby_text, lobby_keyboard, player_assets_text, refresh_all_ui, clear_purchase_prompt
from game_logic import (
    do_roll, buy_property, do_jail_choice, upgrade_current_property,
    creditor_from_key, bankrupt_player, settle_pending_debt, after_action_advance,
    start_turn_timer, run_bot_turn,
)

def assets_popup_text(game, player):
    """Callback alert 上限 200 字元，完整列出摘要並盡量列入地產。"""
    lines = [f"💼 我的資產｜{'已破產' if player.bankrupt else '遊戲中'}",
             f"現金 ${player.money}｜總資產 ${total_asset_value(game, player)}",
             f"位置：{BOARD[player.position]['name']}",
             f"地產 {len(player.properties)} 處｜抵押 {len(player.mortgaged)} 處"]
    if not player.properties:
        lines.append("尚未持有地產")
    for n, idx in enumerate(player.properties):
        level = game.property_level.get(idx, 0)
        label = "飯店" if level == 4 else f"{level}級" if level else "空地"
        if idx in player.mortgaged:
            label += "／抵押"
        line = f"{BOARD[idx]['name']}：{label}"
        # 留空間標示未列出的數量，也保守計算 UTF-16 長度。
        candidate = "\n".join(lines + [line])
        if len(candidate.encode("utf-16-le")) // 2 > 175:
            lines.append(f"另有 {len(player.properties) - n} 處未列出")
            break
        lines.append(line)
    return "\n".join(lines)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏙 <b>台灣大富翁 32格</b>\n\n請到群組輸入 /newgame 建立遊戲。\n"
        "擲骰子、購買地產及其他操作都在群組棋盤下方，不需要私訊。\n2～8 人可玩。",
        parse_mode="HTML",
    )

async def newgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("請在群組使用 /newgame。")
        return

    chat_id = update.effective_chat.id
    if chat_id in games and not games[chat_id].finished:
        await update.message.reply_text("⚠️ 已有一場遊戲，先 /cancel。")
        return

    u = update.effective_user
    p = Player(u.id, u.first_name or u.last_name or "玩家")
    game = Game(chat_id=chat_id, players=[p], host_user_id=u.id)

    # 先嘗試把大廳訊息真正送出去，成功後才把遊戲寫進 games。
    # 這樣 Telegram 暫時逾時時，不會留下「看不到的大廳」卡住 /newgame。
    msg = None
    last_exc = None
    for attempt in range(3):
        try:
            msg = await update.message.reply_text(
                lobby_text(game),
                reply_markup=lobby_keyboard(),
                parse_mode="HTML",
            )
            break
        except RetryAfter as exc:
            last_exc = exc
            await asyncio.sleep(float(exc.retry_after) + 0.5)
        except (TimedOut, NetworkError) as exc:
            last_exc = exc
            await asyncio.sleep(1.0 + attempt)
        except Exception as exc:
            last_exc = exc
            logging.exception("建立大富翁大廳失敗 chat_id=%s", chat_id)
            break

    if msg is None:
        # 不留下幽靈遊戲；下次 /newgame 可以直接重試。
        games.pop(chat_id, None)
        user_to_chat.pop(u.id, None)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ 大廳建立失敗，Telegram 暫時沒有回應，請再輸入一次 /newgame。",
            )
        except Exception:
            pass
        if last_exc:
            logging.error("/newgame 最終失敗：%r", last_exc)
        return

    games[chat_id] = game
    user_to_chat[u.id] = chat_id
    game.board_message_id = msg.message_id

async def add_human_to_game(game: Game, user, context):
    if any(p.user_id == user.id for p in game.players) or len(game.players)>=MAX_PLAYERS:
        return
    ai = next((p for p in game.players if p.is_bot), None)
    if ai: game.players.remove(ai)
    p = Player(user.id, user.first_name or user.last_name or "玩家")
    game.players.append(p); user_to_chat[user.id]=game.chat_id
    try:
        await context.bot.edit_message_text(chat_id=game.chat_id,message_id=game.board_message_id,text=lobby_text(game),reply_markup=lobby_keyboard(),parse_mode="HTML")
    except Exception: pass

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = games.get(update.effective_chat.id)
    if not game or game.started:
        await update.message.reply_text("目前沒有可加入的遊戲。")
        return
    await add_human_to_game(game,update.effective_user,context)

async def start_game(game: Game, context):
    if game.started or len(game.players)<MIN_PLAYERS: return
    game.started=True; game.finished=False; game.phase="roll"; game.current_index=random.randrange(len(game.players)); game.round_number=1
    game.property_owner.clear(); game.property_level.clear(); game.pending_property=None
    for p in game.players:
        p.money=START_MONEY; p.position=0; p.properties.clear(); p.mortgaged.clear(); p.bankrupt=False; p.jail_attempts=0; p.ui_message_id=None
    game.last_action_text=f"🎮 遊戲開始！由 {current_player(game).safe_name} 先手。"
    for mid in (game.board_message_id, game.board_message_id2):
        if mid:
            try: await context.bot.delete_message(game.chat_id, mid)
            except Exception: pass
    game.board_message_id = None
    game.board_message_id2 = None
    await refresh_all_ui(game,context)
    p=current_player(game)
    if p.is_bot: asyncio.create_task(run_bot_turn(game,context))
    else: start_turn_timer(game,context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = games.get(update.effective_chat.id) or find_game_by_user(update.effective_user.id)
    if not game:
        await update.message.reply_text("目前沒有遊戲。"); return
    if game.turn_task: game.turn_task.cancel()
    game.finished = True
    await clear_purchase_prompt(game,context)
    for p in game.players:
        if p.user_id: user_to_chat.pop(p.user_id,None)
    games.pop(game.chat_id,None)
    await update.message.reply_text("🗑 大富翁遊戲已取消。")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = games.get(update.effective_chat.id) or find_game_by_user(update.effective_user.id)
    if not game:
        await update.message.reply_text("目前沒有遊戲。"); return
    ranking=sorted(game.players,key=lambda p:total_asset_value(game,p),reverse=True)
    lines=["📊 <b>目前資產排名</b>"]
    for i,p in enumerate(ranking,1):
        lines.append(f"{i}. {p.safe_name}｜現金 ${p.money}｜地產 {len(p.properties)}｜總資產約 ${total_asset_value(game,p)}{'｜破產' if p.bankrupt else ''}")
    await update.message.reply_text("\n".join(lines),parse_mode="HTML")

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; data=q.data or ""; uid=q.from_user.id
    revision = None
    if "|" in data:
        data, value = data.rsplit("|", 1)
        try:
            revision = int(value)
        except ValueError:
            await q.answer("按鈕無效，請使用最新棋盤。", show_alert=True)
            return
    if update.effective_chat.type == "private":
        await q.answer("操作已移到群組，請使用群組的最新棋盤。", show_alert=True)
        return

    if data == "mono_join":
        game=games.get(update.effective_chat.id)
        if not game or game.started: await q.answer("目前無法加入。",show_alert=True); return
        if any(p.user_id==uid for p in game.players): await q.answer("你已經加入了。"); return
        if len(game.players)>=MAX_PLAYERS: await q.answer("人數已滿。",show_alert=True); return
        await add_human_to_game(game,q.from_user,context); await q.answer("加入成功！"); return

    if data == "mono_fill_ai":
        game=games.get(update.effective_chat.id)
        if not game or game.started: await q.answer("目前無法補電腦。",show_alert=True); return
        n=1
        while len(game.players)<4 and len(game.players)<MAX_PLAYERS:
            while any(p.name==f"電腦{n}" for p in game.players): n+=1
            game.players.append(Player(None,f"電腦{n}",is_bot=True)); n+=1
        try: await q.edit_message_text(lobby_text(game),reply_markup=lobby_keyboard(),parse_mode="HTML")
        except Exception: pass
        await q.answer("已補到 4 人。"); return

    if data in ("mono_mode_quick","mono_mode_classic"):
        game=games.get(update.effective_chat.id)
        if not game or game.started: await q.answer("遊戲已開始，不能改模式。",show_alert=True); return
        game.mode = "quick" if data.endswith("quick") else "classic"
        try: await q.edit_message_text(lobby_text(game),reply_markup=lobby_keyboard(),parse_mode="HTML")
        except Exception: pass
        await q.answer("模式已切換。"); return

    if data == "mono_start_game":
        game=games.get(update.effective_chat.id)
        if not game: await q.answer("找不到遊戲。",show_alert=True); return
        if len(game.players)<MIN_PLAYERS: await q.answer("至少需要 2 人。",show_alert=True); return
        await q.answer("開始！"); await start_game(game,context); return

    if data == "mono_cancel":
        game=games.get(update.effective_chat.id)
        if not game: await q.answer("找不到遊戲。"); return
        game.finished = True
        if game.turn_task: game.turn_task.cancel()
        await clear_purchase_prompt(game,context)
        for p in game.players:
            if p.user_id: user_to_chat.pop(p.user_id,None)
        games.pop(game.chat_id,None)
        try: await q.edit_message_text("🗑 遊戲已取消。")
        except Exception: pass
        return

    # 依訊息所在群組查找牌局，避免同一人在不同群組操作串場。
    game = games.get(update.effective_chat.id)
    if not game or not game.started:
        await q.answer("這個群組目前沒有進行中的遊戲。", show_alert=True)
        return
    player = next((p for p in game.players if p.user_id == uid), None)

    if data == "mono_status":
        ranking = sorted(game.players, key=lambda p: total_asset_value(game,p), reverse=True)
        lines = ["📊 總資產排名"]
        for i, p in enumerate(ranking, 1):
            name = (p.name or "玩家").replace("\n", " ")
            name = name[:4] + ("…" if len(name) > 4 else "")
            lines.append(f"{i}. {name} ${total_asset_value(game,p)}{'×' if p.bankrupt else ''}")
        text = "\n".join(lines)
        if len(text.encode("utf-16-le")) // 2 > 200:
            # 長名稱或大額資產時，改以玩家加入序號，仍保留全部名次。
            lines = ["📊 總資產排名（玩家序號）"]
            for i, p in enumerate(ranking, 1):
                lines.append(f"{i}. 玩家{game.players.index(p)+1} ${total_asset_value(game,p)}{'×' if p.bankrupt else ''}")
            text = "\n".join(lines)
        await q.answer(text, show_alert=True, cache_time=0)
        return
    if data == "mono_assets":
        if player is None:
            await q.answer("你不在這場遊戲。", show_alert=True)
            return
        await q.answer(assets_popup_text(game, player), show_alert=True, cache_time=0)
        return
    if data == "mono_map":
        curr = current_player(game)
        await q.answer(f"32格地圖｜{curr.name} 目前在第 {curr.position+1} 格：{BOARD[curr.position]['name']}", show_alert=True)
        return

    async with game.lock:
        if game.finished:
            await q.answer("遊戲已結束。", show_alert=True)
            return
        expected_message = game.purchase_prompt_id if game.phase == "buy" and game.purchase_prompt_id else game.board_message_id2
        if (revision != game.action_revision or q.message.message_id != expected_message):
            await q.answer("這是舊操作按鈕，請使用群組最新棋盤。", show_alert=True)
            return
        if player is None or current_player(game) != player or player.bankrupt:
            await q.answer(f"現在輪到 {current_player(game).name}，只有他可以操作。", show_alert=True)
            return
        phases = {
            "mono_roll": "roll", "mono_buy": "buy", "mono_pass_buy": "buy",
            "mono_jail_pay": "jail", "mono_jail_roll": "jail", "mono_upgrade": "roll",
            "mono_bankrupt": "debt",
        }
        required = "debt" if data.startswith("mono_mortgage:") else phases.get(data)
        if required is None or required != game.phase:
            await q.answer("這個操作目前不可用。", show_alert=True)
            return
        if data == "mono_jail_pay" and player.money < JAIL_FINE:
            await q.answer("現金不足，請選擇試擲雙數。", show_alert=True)
            return
        idx = None
        if data.startswith("mono_mortgage:"):
            try:
                idx = int(data.split(":",1)[1])
            except ValueError:
                await q.answer("地產按鈕無效。", show_alert=True)
                return
            if idx not in player.properties or idx in player.mortgaged:
                await q.answer("無法抵押。", show_alert=True)
                return
        if game.turn_task:
            game.turn_task.cancel()
        await q.answer("操作已收到。")
        if data == "mono_roll":
            await do_roll(game,player,context)
        elif data == "mono_buy":
            await clear_purchase_prompt(game,context)
            await buy_property(game,player,True,context)
        elif data == "mono_pass_buy":
            await clear_purchase_prompt(game,context)
            await buy_property(game,player,False,context)
        elif data == "mono_jail_pay":
            await do_jail_choice(game,player,context,pay=True)
        elif data == "mono_jail_roll":
            await do_jail_choice(game,player,context,pay=False)
        elif data == "mono_upgrade":
            ok = await upgrade_current_property(game,player,context)
            if not ok:
                await context.bot.send_message(chat_id=game.chat_id, text="目前無法升級：請確認現金、地產等級及抵押狀態。")
            start_turn_timer(game,context)
        elif idx is not None:
            player.mortgaged.add(idx)
            value = mortgage_value(idx)
            player.money += value
            game.last_action_text = f"🏦 {player.safe_name} 抵押【{BOARD[idx]['name']}】取得 ${value}。"
            if player.money >= game.pending_debt_amount:
                await settle_pending_debt(game,player,context)
            else:
                await refresh_all_ui(game,context)
        elif data == "mono_bankrupt":
            receiver = creditor_from_key(game,game.pending_creditor_key)
            if receiver:
                receiver.money += player.money
            player.money = 0
            bankrupt_player(game,player,receiver)
            game.phase = "roll"
            game.last_action_text = f"☠️ {player.safe_name} 宣告破產。"
            await after_action_advance(game,player,context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.exception("Telegram update 發生未處理錯誤", exc_info=context.error)

async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start","開啟遊戲"), BotCommand("newgame","建立大富翁房間"),
        BotCommand("join","加入遊戲"), BotCommand("status","查看排名"), BotCommand("cancel","取消遊戲"),
    ])
