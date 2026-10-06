# -*- coding: utf-8 -*-
"""Telegram 公開群組棋盤與操作 UI。"""
import asyncio
import html
import inspect
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import BadRequest, Forbidden, TimedOut, NetworkError, RetryAfter
from config import MAX_PLAYERS, JAIL_FINE, MAX_LEVEL, BUY_TIMEOUT
from region_photos import PHOTOS, photo_source, photo_credit
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
    lines = ["🏙 <b>【台灣大富翁 32格】</b>", "", f"👥 玩家 {len(game.players)}/{MAX_PLAYERS}", f"🎮 模式：{mode}"]
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
    lines = [
        f"🎲 <b>第 {game.round_number} 回合</b>｜現在輪到：<b>{curr.safe_name}</b>",
        f"💰 ${curr.money}｜📍 {html.escape(BOARD[curr.position]['name'])}｜{phase_map.get(game.phase,'處理中')}",
        game.last_action_text,
    ]
    if game.phase == "buy" and game.pending_property is not None:
        tile = BOARD[game.pending_property]
        lines.append(f"🏠 【{html.escape(tile['name'])}】售價 <b>${tile.get('price',200)}</b>，請在購地訊息選擇購買或不買。")
    elif game.phase == "jail":
        lines.append(f"🔒 付 ${JAIL_FINE} 出獄，或試擲雙數。")
    elif game.phase == "debt":
        lines.append(f"⚠️ 應付 ${game.pending_debt_amount}｜還差 ${max(0,game.pending_debt_amount-curr.money)}，請抵押地產籌款。")
    if not curr.is_bot:
        lines.append("👇 本回合操作只限目前玩家，所有人均可查看資產。")
    return "\n".join(lines)


def board_keyboard(game: Game, bot_username: str = ""):
    rows = []
    if game.started and not game.finished:
        player = current_player(game)
        if not player.is_bot and not player.bankrupt:
            def action(text, data, style=None):
                return button(text, f"{data}|{game.action_revision}", style=style)
            if game.phase == "roll":
                rows.append([action("🎲 擲骰子", "mono_roll", "primary")])
                idx = player.position
                if (idx in player.properties and BOARD[idx]["kind"] == "property"
                        and idx not in player.mortgaged and game.property_level.get(idx,0) < MAX_LEVEL):
                    rows.append([action(f"⬆️ 升級 {BOARD[idx]['name']} ${upgrade_cost(idx)}", "mono_upgrade", "success")])
            elif game.phase == "jail":
                rows.append([action(f"💰 付 ${JAIL_FINE} 出獄", "mono_jail_pay", "success"),
                             action("🎲 試擲雙數", "mono_jail_roll")])
            elif game.phase == "buy" and game.pending_property is not None and not game.purchase_prompt_id:
                tile = BOARD[game.pending_property]
                rows.append([action(f"🏠 購買 ${tile.get('price',200)}", "mono_buy", "success"),
                             action("❌ 不買", "mono_pass_buy", "danger")])
            elif game.phase == "debt":
                for idx in player.properties:
                    if idx not in player.mortgaged:
                        rows.append([action(f"🏦 抵押 {BOARD[idx]['name']} +${mortgage_value(idx)}", f"mono_mortgage:{idx}")])
                rows.append([action("☠️ 宣告破產", "mono_bankrupt", "danger")])
    rows.append([button("📊 查看排名", "mono_status"), button("💼 我的資產", "mono_assets"),
                 button("🗺 查看地圖", "mono_map")])
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

async def safe_edit_or_send_board(game: Game, context):
    """群組上下雙圖，操作按鈕放在下半張；兩張各自處理未變更。"""
    caption = board_caption(game)
    markup = board_keyboard(game)
    top_img, bottom_img = generate_group_board_images(game)
    try:
        if game.board_message_id and game.board_message_id2:
            try:
                for mid, img, is_bottom in (
                    (game.board_message_id, top_img, False),
                    (game.board_message_id2, bottom_img, True),
                ):
                    img.seek(0)
                    try:
                        await context.bot.edit_message_media(
                            chat_id=game.chat_id, message_id=mid,
                            media=InputMediaPhoto(media=img, caption=caption if is_bottom else None,
                                                  parse_mode="HTML" if is_bottom else None),
                            reply_markup=markup if is_bottom else None,
                        )
                    except BadRequest as exc:
                        if "message is not modified" not in str(exc).lower():
                            raise
                return
            except RetryAfter as exc:
                await asyncio.sleep(float(exc.retry_after))
            except Exception:
                logging.exception("更新群組雙圖棋盤失敗")

        for mid in (game.board_message_id, game.board_message_id2):
            if mid:
                try:
                    await context.bot.delete_message(chat_id=game.chat_id, message_id=mid)
                except Exception:
                    pass
        game.board_message_id = None
        game.board_message_id2 = None
        top_img.seek(0); bottom_img.seek(0)
        msg1 = await context.bot.send_photo(chat_id=game.chat_id, photo=top_img)
        game.board_message_id = msg1.message_id
        msg2 = await context.bot.send_photo(
            chat_id=game.chat_id, photo=bottom_img, caption=caption,
            reply_markup=markup, parse_mode="HTML",
        )
        game.board_message_id2 = msg2.message_id
    except Exception:
        logging.exception("發送群組雙圖棋盤失敗")
    finally:
        top_img.close(); bottom_img.close()


# 成功傳送後重用 Telegram file_id，避免每次回合都向照片來源下載。
_PHOTO_FILE_IDS = {}


async def clear_purchase_prompt(game: Game, context):
    if game.purchase_prompt_id:
        game.pending_prompt_deletions.append(game.purchase_prompt_id)
        game.purchase_prompt_id = None
    remaining = []
    for mid in dict.fromkeys(game.pending_prompt_deletions):
        try:
            await context.bot.delete_message(chat_id=game.chat_id, message_id=mid)
        except BadRequest as exc:
            if "message to delete not found" in str(exc).lower():
                continue
            remaining.append(mid)
        except Exception:
            remaining.append(mid)
        else:
            continue
        # 刪除暫時失敗也先移除可點按鈕；下次更新再清理。
        try:
            await context.bot.edit_message_reply_markup(chat_id=game.chat_id, message_id=mid, reply_markup=None)
        except Exception:
            pass
    game.pending_prompt_deletions = remaining


async def show_purchase_prompt(game: Game, context):
    idx = game.pending_property
    if game.finished or game.phase != "buy" or idx is None:
        return
    player = current_player(game)
    tile = BOARD[idx]
    price = tile.get("price", 200)
    caption = (
        f"📍 <b>抵達｜{html.escape(tile['name'])}</b>\n"
        f"👤 {player.safe_name}｜💰 現金 ${player.money}\n\n"
        f"🏠 售價 <b>${price}</b>｜購買後剩餘 ${player.money-price}\n"
    )
    if tile["kind"] == "property":
        caption += f"💵 空地基本租金 ${tile['rent']}\n"
    else:
        caption += "🚉 租金依持有交通站數量計算\n"
    markup = None
    if player.is_bot:
        caption += "\n🤖 電腦正在決定是否購買…"
    else:
        caption += f"\n要購買嗎？僅 {player.safe_name} 可選擇。\n⏳ {BUY_TIMEOUT} 秒未選擇將自動不買；選完後此訊息會刪除。"
        markup = InlineKeyboardMarkup([[
            button(f"🏠 購買 ${price}", f"mono_buy|{game.action_revision}", style="success"),
            button("❌ 不買", f"mono_pass_buy|{game.action_revision}", style="danger"),
        ]])
    if idx in PHOTOS:
        caption += "\n\n" + photo_credit(idx)
        key = (getattr(context.bot, "id", None), idx)
        source = _PHOTO_FILE_IDS.get(key) or photo_source(idx)
        try:
            msg = await context.bot.send_photo(
                chat_id=game.chat_id, photo=source, caption=caption,
                reply_markup=markup, parse_mode="HTML", read_timeout=15, write_timeout=15,
            )
            game.purchase_prompt_id = msg.message_id
            if msg.photo:
                _PHOTO_FILE_IDS[key] = msg.photo[-1].file_id
            return
        except Exception:
            _PHOTO_FILE_IDS.pop(key, None)
            logging.exception("地區照片發送失敗，改用文字購地選項 index=%s", idx)
    try:
        msg = await context.bot.send_message(
            chat_id=game.chat_id, text=caption + "\n\n（照片暫時無法載入，可正常選擇。）",
            reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True,
        )
        game.purchase_prompt_id = msg.message_id
    except Exception:
        logging.exception("購地提示發送失敗，改用棋盤按鈕")


async def refresh_all_ui(game: Game, context):
    game.action_revision += 1
    await clear_purchase_prompt(game, context)
    await show_purchase_prompt(game, context)
    await safe_edit_or_send_board(game, context)
