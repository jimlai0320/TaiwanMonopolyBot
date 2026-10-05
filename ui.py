# -*- coding: utf-8 -*-
"""Telegram 群組 / 私訊 UI。"""
import asyncio
import html
import inspect
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import BadRequest, Forbidden, TimedOut, NetworkError, RetryAfter
from config import MAX_PLAYERS, JAIL_FINE, MAX_LEVEL
from board_data import BOARD
from models import Game, Player
from helpers import current_player, total_asset_value, upgrade_cost, mortgage_value
from renderer import generate_board_image, generate_group_board_images

def button(text, callback_data=None, url=None, style=None):
    kwargs = {"text": text}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if style and "style" in inspect.signature(InlineKeyboardButton).parameters:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)

def lobby_text(game: Game):
    mode = "⚡ 30回合快速模式" if game.mode == "quick" else "🏆 經典淘汰模式"
    lines = ["🏙 <b>【台灣大富翁 48格】</b>", "", f"👥 玩家 {len(game.players)}/{MAX_PLAYERS}", f"🎮 模式：{mode}"]
    for i,p in enumerate(game.players,1):
        lines.append(f"{i}. {'🤖' if p.is_bot else '👤'} {p.safe_name}")
    lines += ["", "2～8 人可開始；建議 4～6 人。", "不足人數可補電腦到 4 人。"]
    return "\n".join(lines)

def lobby_keyboard():
    return InlineKeyboardMarkup([
        [button("🙋 加入遊戲", "mono_join", style="success"), button("🤖 補到4人", "mono_fill_ai")],
        [button("⚡ 30回合", "mono_mode_quick", style="primary"), button("🏆 經典", "mono_mode_classic")],
        [button("🎮 開始遊戲", "mono_start_game", style="primary"), button("❌ 取消", "mono_cancel", style="danger")],
    ])

def board_caption(game: Game):
    if game.finished:
        ranking = sorted(game.players, key=lambda p: total_asset_value(game,p), reverse=True)
        winner = ranking[0]
        return f"🏆 <b>遊戲結束｜{winner.safe_name} 獲勝！</b>\n💰 總資產：<code>${total_asset_value(game,winner)}</code>"
    curr = current_player(game)
    phase_map = {"roll":"擲骰子", "buy":"決定是否購買", "jail":"監獄選擇", "debt":"處理欠款"}
    return (
        f"🎲 <b>第 {game.round_number} 回合</b>｜現在輪到：<b>{curr.safe_name}</b>\n"
        f"💰 ${curr.money}｜📍 {BOARD[curr.position]['name']}｜{phase_map.get(game.phase,'處理中')}\n"
        f"{game.last_action_text}"
    )

def board_keyboard(game: Game, bot_username: str):
    rows = []
    if not game.finished and not current_player(game).is_bot:
        rows.append([button("👉 前往操作", url=f"https://t.me/{bot_username}")])
    rows.append([button("📊 查看排名", "mono_status"), button("🗺 查看地圖", "mono_map")])
    return InlineKeyboardMarkup(rows)

def player_assets_text(game: Game, player: Player):
    lines = [f"💼 <b>{player.safe_name} 的資產</b>", f"💰 現金：<code>${player.money}</code>", f"📍 位置：{html.escape(BOARD[player.position]['name'])}", ""]
    if not player.properties:
        lines.append("🏠 尚未持有任何地產。")
    else:
        lines.append("🏠 <b>持有地產：</b>")
        for idx in player.properties:
            tile = BOARD[idx]
            mort = "（已抵押）" if idx in player.mortgaged else ""
            lvl = game.property_level.get(idx,0)
            lvtext = "飯店" if lvl == 4 else f"{lvl}級" if lvl else "空地"
            lines.append(f"• {html.escape(tile['name'])}｜{lvtext}{mort}")
    lines += ["", f"📈 總資產約：<code>${total_asset_value(game,player)}</code>"]
    return "\n".join(lines)

def private_caption(game: Game, player: Player):
    curr = current_player(game)
    lines = [
        f"🏙 <b>台灣大富翁｜第 {game.round_number} 回合</b>",
        f"💰 金錢：<code>${player.money}</code>",
        f"📍 位置：<b>{html.escape(BOARD[player.position]['name'])}</b>",
        f"🏠 持有地：<code>{len(player.properties)}</code> 處",
    ]
    if player.bankrupt:
        lines.append("☠️ 你已破產，等待本局結束。")
    elif curr == player:
        if game.phase == "roll":
            lines.append("\n🎲 <b>現在輪到你，請擲骰子。</b>")
        elif game.phase == "jail":
            lines.append(f"\n🔒 <b>你在監獄。</b> 可付 ${JAIL_FINE} 出獄，或嘗試擲雙數。")
        elif game.phase == "buy" and game.pending_property is not None:
            tile = BOARD[game.pending_property]
            lines += [f"\n🏠 你停在 <b>【{html.escape(tile['name'])}】</b>", f"價格：<code>${tile.get('price',200)}</code>", "目前無人持有，要購買嗎？"]
        elif game.phase == "debt":
            lines += [f"\n⚠️ <b>資金不足</b>，尚欠 <code>${game.pending_debt_amount}</code>", html.escape(game.pending_debt_reason), "請抵押地產籌款；無資產可抵押時將破產。"]
    else:
        lines.append(f"\n⏳ 等待 <b>{curr.safe_name}</b> 操作。")
    return "\n".join(lines)

def private_keyboard(game: Game, player: Player):
    rows = []
    curr = current_player(game)
    if not player.bankrupt and curr == player:
        if game.phase == "roll":
            rows.append([button("🎲 擲骰子", "mono_roll", style="primary")])
        elif game.phase == "jail":
            rows.append([button(f"💰 付 ${JAIL_FINE} 出獄", "mono_jail_pay", style="success"), button("🎲 試擲雙數", "mono_jail_roll")])
        elif game.phase == "buy" and game.pending_property is not None:
            tile = BOARD[game.pending_property]
            rows.append([button(f"🏠 購買 ${tile.get('price',200)}", "mono_buy", style="success"), button("❌ 不買", "mono_pass_buy", style="danger")])
        elif game.phase == "debt":
            mort = [idx for idx in player.properties if idx not in player.mortgaged]
            for idx in mort[:8]:
                rows.append([button(f"🏦 抵押 {BOARD[idx]['name']} +${mortgage_value(idx)}", f"mono_mortgage:{idx}")])
            rows.append([button("☠️ 宣告破產", "mono_bankrupt", style="danger")])
    # 自己停到自己的地，可升級（不在其他強制 phase 時）
    if not player.bankrupt and player.position in player.properties and game.phase in ("roll",):
        idx = player.position
        if BOARD[idx]["kind"] == "property" and idx not in player.mortgaged and game.property_level.get(idx,0) < MAX_LEVEL:
            rows.append([button(f"⬆️ 升級目前地產 ${upgrade_cost(idx)}", "mono_upgrade", style="success")])
    rows.append([button("📊 查看資產", "mono_assets"), button("🗺 查看地圖", "mono_map")])
    return InlineKeyboardMarkup(rows)

async def safe_edit_or_send_board(game: Game, context):
    """群組使用兩張近方形大圖，避免 Telegram 把超長圖縮得太小。"""
    caption = board_caption(game)
    markup = board_keyboard(game, context.bot.username or "")
    top_img, bottom_img = generate_group_board_images(game)

    # 已有兩張棋盤訊息：直接更新。
    if game.board_message_id and game.board_message_id2:
        try:
            await context.bot.edit_message_media(
                chat_id=game.chat_id,
                message_id=game.board_message_id,
                media=InputMediaPhoto(media=top_img, caption="🗺 <b>台灣大富翁｜地圖上半部</b>", parse_mode="HTML"),
            )
            await context.bot.edit_message_media(
                chat_id=game.chat_id,
                message_id=game.board_message_id2,
                media=InputMediaPhoto(media=bottom_img, caption=caption, parse_mode="HTML"),
                reply_markup=markup,
            )
            return
        except BadRequest as e:
            if "Message is not modified" in str(e):
                return
        except RetryAfter as e:
            await asyncio.sleep(float(e.retry_after))
        except Exception:
            logging.exception("更新群組雙圖棋盤失敗")

    # 舊版若只留下一張訊息，先嘗試刪掉，避免殘留。
    for mid in (game.board_message_id, game.board_message_id2):
        if mid:
            try:
                await context.bot.delete_message(chat_id=game.chat_id, message_id=mid)
            except Exception:
                pass
    game.board_message_id = None
    game.board_message_id2 = None

    try:
        msg1 = await context.bot.send_photo(
            chat_id=game.chat_id,
            photo=top_img,
            caption="🗺 <b>台灣大富翁｜地圖上半部</b>",
            parse_mode="HTML",
        )
        msg2 = await context.bot.send_photo(
            chat_id=game.chat_id,
            photo=bottom_img,
            caption=caption,
            reply_markup=markup,
            parse_mode="HTML",
        )
        game.board_message_id = msg1.message_id
        game.board_message_id2 = msg2.message_id
    except Exception:
        logging.exception("發送群組雙圖棋盤失敗")
    finally:
        for b in (top_img, bottom_img):
            try:
                b.close()
            except Exception:
                pass

async def send_private_ui(game: Game, player: Player, context):
    """
    私訊只保留文字 + 按鈕，不再重複傳 1200x2200 棋盤。
    這樣群組棋盤能保持高畫質，同時大幅降低記憶體與上傳流量。
    """
    if player.is_bot or not player.user_id:
        return
    caption = private_caption(game, player)
    markup = private_keyboard(game, player)

    if player.ui_message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=player.user_id,
                message_id=player.ui_message_id,
                text=caption,
                reply_markup=markup,
                parse_mode="HTML",
            )
            return
        except BadRequest as e:
            if "Message is not modified" in str(e):
                return
        except (Forbidden, TimedOut, NetworkError):
            pass
        except Exception:
            logging.exception("編輯私人介面失敗 user=%s", player.user_id)

    try:
        msg = await context.bot.send_message(
            chat_id=player.user_id,
            text=caption,
            reply_markup=markup,
            parse_mode="HTML",
        )
        player.ui_message_id = msg.message_id
    except Forbidden:
        logging.warning("無法私訊 %s：玩家尚未 /start 或封鎖 Bot", player.name)
    except Exception:
        logging.exception("私人介面發送失敗 user=%s", player.user_id)

async def refresh_all_ui(game: Game, context):
    await safe_edit_or_send_board(game, context)
    await asyncio.gather(*(send_private_ui(game,p,context) for p in game.players if not p.is_bot), return_exceptions=True)
