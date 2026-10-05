# -*- coding: utf-8 -*-
"""不涉及 Telegram I/O 的共用遊戲計算。"""
from typing import Optional
from config import PASS_GO_REWARD
from board_data import BOARD, TRANSPORT_RENTS
from models import Player, Game, games, user_to_chat

def player_key(player: Player) -> int:
    if player.user_id is not None:
        return player.user_id
    return -1000000 - abs(hash(player.name)) % 900000000

def find_game_by_user(user_id: int) -> Optional[Game]:
    chat_id = user_to_chat.get(user_id)
    if chat_id in games:
        return games[chat_id]
    for game in games.values():
        for p in game.players:
            if p.user_id == user_id:
                user_to_chat[user_id] = game.chat_id
                return game
    return None

def current_player(game: Game) -> Player:
    return game.players[game.current_index]

def active_players(game: Game):
    return [p for p in game.players if not p.bankrupt]

def get_owner(game: Game, tile_index: int) -> Optional[Player]:
    key = game.property_owner.get(tile_index)
    if key is None:
        return None
    return next((p for p in game.players if player_key(p) == key), None)

def group_tiles(group: str):
    return [i for i, t in enumerate(BOARD) if t.get("group") == group]

def owns_full_group(game: Game, player: Player, group: str) -> bool:
    tiles = group_tiles(group)
    return bool(tiles) and all(get_owner(game, i) == player for i in tiles)

def transport_count(game: Game, player: Player) -> int:
    return sum(1 for i in player.properties if BOARD[i]["kind"] == "transport" and i not in player.mortgaged)

def property_rent(game: Game, tile_index: int) -> int:
    tile = BOARD[tile_index]
    owner = get_owner(game, tile_index)
    if owner is None or tile_index in owner.mortgaged:
        return 0
    if tile["kind"] == "transport":
        return TRANSPORT_RENTS[min(transport_count(game, owner), 4)]
    if tile["kind"] != "property":
        return 0
    base = tile["rent"]
    level = game.property_level.get(tile_index, 0)
    if level == 0 and owns_full_group(game, owner, tile.get("group", "")):
        return base * 2
    # 1房 x2 / 2房 x3 / 3房 x5 / 飯店 x8
    multiplier = [1, 2, 3, 5, 8][min(level, 4)]
    return base * multiplier

def upgrade_cost(tile_index: int) -> int:
    return max(80, BOARD[tile_index].get("price", 0) // 2)

def mortgage_value(tile_index: int) -> int:
    return BOARD[tile_index].get("price", 0) // 2

def total_asset_value(game: Game, player: Player) -> int:
    value = player.money
    for idx in player.properties:
        value += BOARD[idx].get("price", 0)
        value += upgrade_cost(idx) * game.property_level.get(idx, 0)
    return value

def move_player(player: Player, steps: int):
    old = player.position
    new = (old + steps) % len(BOARD)
    passed = steps > 0 and old + steps >= len(BOARD)
    player.position = new
    if passed:
        player.money += PASS_GO_REWARD
    return passed

def next_alive_index(game: Game, from_idx: int):
    n = len(game.players)
    for step in range(1, n + 1):
        idx = (from_idx + step) % n
        if not game.players[idx].bankrupt:
            return idx
    return from_idx
