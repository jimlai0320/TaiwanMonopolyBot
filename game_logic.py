# -*- coding: utf-8 -*-
"""大富翁規則、金錢、回合、AI 與逾時處理。"""
import asyncio
import html
import logging
from telegram.error import TelegramError, BadRequest
import random
from typing import Optional
from config import PASS_GO_REWARD, QUICK_ROUNDS, MAX_LEVEL, JAIL_FINE, ROLL_TIMEOUT, BUY_TIMEOUT, JAIL_TIMEOUT
from board_data import BOARD, CHANCE_EVENTS, JAIL_INDEX
from models import Game, Player
from helpers import (
    player_key, current_player, active_players, get_owner, property_rent,
    upgrade_cost, mortgage_value, total_asset_value, move_player, next_alive_index,
)
from ui import refresh_all_ui

def creditor_from_key(game: Game, key: Optional[int]) -> Optional[Player]:
    if key is None:
        return None
    return next((p for p in game.players if player_key(p) == key), None)

def liquidatable_value(player: Player) -> int:
    return player.money + sum(mortgage_value(i) for i in player.properties if i not in player.mortgaged)

def bankrupt_player(game: Game, player: Player, creditor: Optional[Player]):
    if player.bankrupt:
        return
    player.bankrupt = True
    for idx in list(player.properties):
        if creditor and not creditor.bankrupt:
            game.property_owner[idx] = player_key(creditor)
            creditor.properties.append(idx)
            if idx in player.mortgaged:
                creditor.mortgaged.add(idx)
        else:
            game.property_owner.pop(idx, None)
            game.property_level[idx] = 0
        player.mortgaged.discard(idx)
    player.properties.clear()
    player.money = 0

async def request_payment(game: Game, payer: Player, receiver: Optional[Player], amount: int, reason: str, context):
    amount = max(0, int(amount))
    if amount == 0:
        return True
    if payer.money >= amount:
        payer.money -= amount
        if receiver:
            receiver.money += amount
        return True
    if liquidatable_value(payer) < amount:
        # 直接破產，現金全付出
        if receiver:
            receiver.money += payer.money
        payer.money = 0
        bankrupt_player(game, payer, receiver)
        game.last_action_text = f"☠️ {payer.safe_name} 無力支付 ${amount}，宣告破產。"
        return True
    game.phase = "debt"
    game.pending_debt_amount = amount
    game.pending_creditor_key = player_key(receiver) if receiver else None
    game.pending_debt_reason = reason
    game.last_action_text = f"⚠️ {payer.safe_name} 資金不足，需籌款支付 ${amount}。"
    await refresh_all_ui(game, context)
    if payer.is_bot:
        asyncio.create_task(run_bot_debt(game, payer, context))
    return False

async def settle_pending_debt(game: Game, payer: Player, context):
    amount = game.pending_debt_amount
    receiver = creditor_from_key(game, game.pending_creditor_key)
    if payer.money < amount:
        return False
    payer.money -= amount
    if receiver:
        receiver.money += amount
    game.pending_debt_amount = 0
    game.pending_creditor_key = None
    game.pending_debt_reason = ""
    game.phase = "roll"
    game.last_action_text = f"✅ {payer.safe_name} 已成功籌款並支付 ${amount}。"
    await after_action_advance(game, payer, context)
    return True

async def resolve_tile(game: Game, player: Player, context, chain_depth=0):
    if chain_depth > 3:
        return "done"
    tile = BOARD[player.position]
    kind = tile["kind"]
    game.pending_property = None

    if kind in ("property", "transport"):
        owner = get_owner(game, player.position)
        if owner is None:
            price = tile.get("price", 200 if kind == "transport" else 0)
            if player.money >= price:
                game.phase = "buy"
                game.pending_property = player.position
                game.last_action_text = f"🏠 {player.safe_name} 停在【{html.escape(tile['name'])}】，等待是否購買。"
                return "wait"
            game.last_action_text = f"🏠 {player.safe_name} 停在【{html.escape(tile['name'])}】，但現金不足。"
        elif owner == player:
            game.last_action_text = f"🏠 {player.safe_name} 回到自己的【{html.escape(tile['name'])}】。"
        else:
            rent = property_rent(game, player.position)
            if rent == 0:
                game.last_action_text = f"🏦 【{html.escape(tile['name'])}】目前抵押中，不收租。"
            else:
                ok = await request_payment(game, player, owner, rent, f"支付 {owner.name} 的【{tile['name']}】租金", context)
                if not ok:
                    return "wait"
                game.last_action_text = f"💸 {player.safe_name} 支付 ${rent} 租金給 {owner.safe_name}。"

    elif kind == "tax":
        ok = await request_payment(game, player, None, tile["amount"], f"支付【{tile['name']}】", context)
        if not ok:
            return "wait"
        game.last_action_text = f"💰 {player.safe_name} 支付 {html.escape(tile['name'])} ${tile['amount']}。"

    elif kind == "chance":
        text_evt, etype, val = random.choice(CHANCE_EVENTS)
        game.last_action_text = f"🎴 {player.safe_name}：{text_evt}"
        if etype == "money":
            if val >= 0:
                player.money += val
            else:
                ok = await request_payment(game, player, None, -val, text_evt, context)
                if not ok:
                    return "wait"
        elif etype == "move":
            if val > 0:
                move_player(player, val)
            else:
                player.position = (player.position + val) % len(BOARD)
            return await resolve_tile(game, player, context, chain_depth+1)
        elif etype == "collect_each":
            for other in game.players:
                if other != player and not other.bankrupt:
                    amt = min(other.money, val)
                    other.money -= amt; player.money += amt
        elif etype == "pay_each":
            total = val * (len(active_players(game))-1)
            ok = await request_payment(game, player, None, total, text_evt, context)
            if not ok:
                return "wait"
            for other in game.players:
                if other != player and not other.bankrupt:
                    other.money += val
        elif etype == "jail":
            player.position = JAIL_INDEX
            player.jail_attempts = 1
        elif etype == "next_transport":
            for step in range(1, len(BOARD)+1):
                idx = (player.position + step) % len(BOARD)
                if BOARD[idx]["kind"] == "transport":
                    if player.position + step >= len(BOARD):
                        player.money += PASS_GO_REWARD
                    player.position = idx
                    break
            return await resolve_tile(game, player, context, chain_depth+1)

    elif kind == "gotojail":
        player.position = JAIL_INDEX
        player.jail_attempts = 1
        game.last_action_text = f"🚓 {player.safe_name} 被送進監獄。"

    elif kind == "jail":
        game.last_action_text = f"👮 {player.safe_name} 只是來探監。"

    elif kind == "free":
        game.last_action_text = f"🏖 {player.safe_name} 在免費休息區放鬆一下。"

    elif kind == "teleport":
        player.position = tile["target"]
        game.last_action_text = f"🌀 {player.safe_name} 使用傳送，前往【{BOARD[player.position]['name']}】！"
        return await resolve_tile(game, player, context, chain_depth+1)

    elif kind == "special":
        player.money += tile.get("amount",0)
        game.last_action_text = f"🎁 {player.safe_name} 獲得環島獎金 ${tile.get('amount',0)}！"

    elif kind == "start":
        game.last_action_text = f"🏁 {player.safe_name} 停在出發點。"

    return "done"

async def finish_if_needed(game: Game, context):
    alive = active_players(game)
    if len(alive) <= 1:
        game.finished = True; game.phase = "end"
    elif game.mode == "quick" and game.round_number > QUICK_ROUNDS:
        game.finished = True; game.phase = "end"
        ranking = sorted(game.players, key=lambda p: total_asset_value(game,p), reverse=True)
        game.last_action_text = f"⏱ 30回合結束，{ranking[0].safe_name} 以最高總資產獲勝！"
    if game.finished:
        if game.turn_task and game.turn_task is not asyncio.current_task():
            game.turn_task.cancel()
        await refresh_all_ui(game, context)
        return True
    return False

async def after_action_advance(game: Game, player: Player, context):
    if await finish_if_needed(game, context):
        return
    keep_same = game.extra_turn and not player.bankrupt
    if keep_same:
        game.phase = "roll"
        game.pending_property = None
        game.extra_turn = False
        game.last_action_text += " 🎯 骰到對子，再擲一次！"
        await refresh_all_ui(game, context)
        if player.is_bot:
            asyncio.create_task(run_bot_turn(game, context))
        else:
            start_turn_timer(game, context)
        return
    old = game.current_index
    game.current_index = next_alive_index(game, old)
    if game.current_index <= old:
        game.round_number += 1
    game.phase = "jail" if current_player(game).jail_attempts > 0 else "roll"
    game.pending_property = None
    game.extra_turn = False
    await refresh_all_ui(game, context)
    curr = current_player(game)
    if curr.is_bot:
        asyncio.create_task(run_bot_turn(game, context))
    else:
        start_turn_timer(game, context, phase=game.phase)

# 留出原生骰子動畫播放時間；Telegram 不提供客戶端播放完成回呼。
DICE_ANIMATION_SECONDS = 4.0


async def native_dice(game, player, context, count):
    """呼叫者持有 game.lock；只採用 Telegram 回傳點數，不另抽籤。"""
    previous_phase = game.phase
    game.phase = "rolling"
    game.action_revision += 1
    if game.turn_task and game.turn_task is not asyncio.current_task():
        game.turn_task.cancel()
    messages, values = [], []
    try:
        for _ in range(count):
            msg = await context.bot.send_dice(
                chat_id=game.chat_id, emoji="🎲", disable_notification=True,
                read_timeout=15, write_timeout=15, connect_timeout=10,
            )
            messages.append(msg.message_id)
            if not msg.dice or not 1 <= msg.dice.value <= 6:
                raise ValueError("Telegram returned an invalid dice result")
            values.append(msg.dice.value)
        await asyncio.sleep(DICE_ANIMATION_SECONDS)
    except (TelegramError, ValueError):
        # 發送逾時可能已送出，不能盲目重送或用本機點數冒充動畫結果。
        logging.warning("原生骰子未完成，chat_id=%s", game.chat_id)
        values = []
    finally:
        for mid in messages:
            try:
                await context.bot.delete_message(chat_id=game.chat_id, message_id=mid)
            except BadRequest as exc:
                if "message to delete not found" not in str(exc).lower():
                    game.pending_prompt_deletions.append(mid)
            except TelegramError:
                game.pending_prompt_deletions.append(mid)
        if not game.finished:
            game.phase = previous_phase
    if game.finished:
        return None
    if len(values) != count:
        game.last_action_text = "⚠️ 骰子傳送未完成，本次不計步，請重新擲骰。"
        await refresh_all_ui(game, context)
        # 人類可立即重試，電腦及逾時代擲也有下一次機會。
        game.turn_task = asyncio.create_task(turn_timeout(game, player, previous_phase, context))
        return None
    return tuple(values)


async def do_roll(game: Game, player: Player, context, auto=False):
    if game.phase != "roll" or current_player(game) != player or player.bankrupt:
        return
    dice = await native_dice(game, player, context, 2)
    if dice is None:
        return
    d1, d2 = dice
    game.last_dice = (d1,d2)
    passed = move_player(player, d1+d2)
    prefix = "⏰ 系統代擲" if auto else "🎲 擲骰子"
    reward = f"，經過出發點 +${PASS_GO_REWARD}" if passed else ""
    game.last_action_text = f"{prefix}：{player.safe_name} 擲出 {d1}+{d2}={d1+d2}{reward}。"
    roll_text = game.last_action_text
    game.extra_turn = (d1 == d2)
    result = await resolve_tile(game, player, context)
    if game.last_action_text != roll_text:
        game.last_action_text = roll_text + "\n" + game.last_action_text
    if result == "wait" or await finish_if_needed(game, context):
        if result == "wait" and game.phase == "buy":
            await refresh_all_ui(game, context)
            if player.is_bot: asyncio.create_task(run_bot_buy_decision(game, player, context))
            else: start_turn_timer(game, context, phase="buy")
        return
    await after_action_advance(game, player, context)

async def buy_property(game: Game, player: Player, buy: bool, context, auto=False):
    idx = game.pending_property
    if game.phase != "buy" or idx is None or current_player(game) != player:
        return
    tile = BOARD[idx]
    price = tile.get("price", 200)
    if get_owner(game,idx) is None and buy and player.money >= price:
        player.money -= price
        player.properties.append(idx)
        game.property_owner[idx] = player_key(player)
        game.property_level[idx] = 0
        game.last_action_text = f"🏠 {player.safe_name} 購買【{html.escape(tile['name'])}】${price}。"
    else:
        game.last_action_text = f"❌ {player.safe_name} 放棄購買【{html.escape(tile['name'])}】{'（逾時）' if auto else ''}。"
    game.pending_property = None
    game.phase = "roll"
    await after_action_advance(game, player, context)

async def do_jail_choice(game: Game, player: Player, context, pay=False, auto=False):
    if game.phase != "jail" or current_player(game) != player:
        return
    if pay and player.money >= JAIL_FINE:
        player.money -= JAIL_FINE
        player.jail_attempts = 0
        game.phase = "roll"
        game.last_action_text = f"🔓 {player.safe_name} 支付 ${JAIL_FINE} 出獄。"
        await refresh_all_ui(game, context)
        if player.is_bot: asyncio.create_task(run_bot_turn(game, context))
        else: start_turn_timer(game, context)
        return
    dice = await native_dice(game, player, context, 1)
    if dice is None:
        return
    roll = dice[0]
    if roll % 2 == 0:
        player.jail_attempts = 0
        game.phase = "roll"
        game.last_action_text = f"🎲 {player.safe_name} 擲出 {roll}（雙數），免費出獄！"
        await refresh_all_ui(game, context)
        if player.is_bot: asyncio.create_task(run_bot_turn(game, context))
        else: start_turn_timer(game, context)
    else:
        player.jail_attempts += 1
        if player.jail_attempts >= 3:
            paid = min(player.money, JAIL_FINE)
            player.money -= paid
            player.jail_attempts = 0
            game.phase = "roll"
            game.last_action_text = f"🔓 第2次失敗，{player.safe_name} 強制支付 ${paid} 出獄。"
            await refresh_all_ui(game, context)
            if player.is_bot: asyncio.create_task(run_bot_turn(game, context))
            else: start_turn_timer(game, context)
        else:
            game.last_action_text = f"🔒 {player.safe_name} 擲出 {roll}，本回合仍留在監獄。"
            await after_action_advance(game, player, context)

async def upgrade_current_property(game: Game, player: Player, context):
    idx = player.position
    if idx not in player.properties or BOARD[idx]["kind"] != "property" or idx in player.mortgaged:
        return False
    level = game.property_level.get(idx,0)
    cost = upgrade_cost(idx)
    if level >= MAX_LEVEL or player.money < cost:
        return False
    player.money -= cost
    game.property_level[idx] = level + 1
    label = "飯店" if level+1 == 4 else f"{level+1}級房屋"
    game.last_action_text = f"⬆️ {player.safe_name} 將【{BOARD[idx]['name']}】升級為 {label}，花費 ${cost}。"
    await refresh_all_ui(game, context)
    return True

async def turn_timeout(game: Game, player: Player, phase: str, context):
    seconds = BUY_TIMEOUT if phase == "buy" else JAIL_TIMEOUT if phase == "jail" else ROLL_TIMEOUT
    try:
        await asyncio.sleep(seconds)
        async with game.lock:
            if game.finished or current_player(game) != player or game.phase != phase:
                return
            if phase == "roll": await do_roll(game, player, context, auto=True)
            elif phase == "buy": await buy_property(game, player, False, context, auto=True)
            elif phase == "jail": await do_jail_choice(game, player, context, pay=False, auto=True)
    except asyncio.CancelledError:
        return

def start_turn_timer(game: Game, context, phase=None):
    if game.turn_task and game.turn_task is not asyncio.current_task():
        game.turn_task.cancel()
    p = current_player(game)
    if p.is_bot: return
    phase = phase or game.phase
    if phase in ("roll","buy","jail"):
        game.turn_task = asyncio.create_task(turn_timeout(game,p,phase,context))

async def run_bot_turn(game: Game, context):
    await asyncio.sleep(random.uniform(0.7,1.2))
    async with game.lock:
        if game.finished: return
        p = current_player(game)
        if not p.is_bot: return
        if game.phase == "jail":
            await do_jail_choice(game,p,context,pay=(p.money>=500))
        elif game.phase == "roll":
            await do_roll(game,p,context)

async def run_bot_buy_decision(game: Game, player: Player, context):
    await asyncio.sleep(random.uniform(0.5,0.9))
    async with game.lock:
        if game.finished or current_player(game) != player or game.phase != "buy": return
        idx = game.pending_property
        if idx is None: return
        price = BOARD[idx].get("price",200)
        await buy_property(game,player,player.money-price>=300,context)

async def run_bot_debt(game: Game, player: Player, context):
    await asyncio.sleep(0.5)
    async with game.lock:
        while game.phase == "debt" and current_player(game) == player and player.money < game.pending_debt_amount:
            options = [i for i in player.properties if i not in player.mortgaged]
            if not options:
                receiver = creditor_from_key(game, game.pending_creditor_key)
                bankrupt_player(game, player, receiver)
                game.last_action_text = f"☠️ {player.safe_name} 無資產可抵押，宣告破產。"
                game.phase = "roll"
                await after_action_advance(game, player, context)
                return
            idx = max(options, key=mortgage_value)
            player.mortgaged.add(idx)
            player.money += mortgage_value(idx)
        if game.phase == "debt":
            await settle_pending_debt(game,player,context)
