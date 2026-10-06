# -*- coding: utf-8 -*-
"""玩家、牌局資料模型與記憶體中的遊戲狀態。"""
import asyncio
import html
from dataclasses import dataclass, field
from typing import Optional
from config import START_MONEY

@dataclass(eq=False)
class Player:
    user_id: Optional[int]
    name: str
    is_bot: bool = False
    money: int = START_MONEY
    position: int = 0
    properties: list[int] = field(default_factory=list)
    mortgaged: set[int] = field(default_factory=set)
    bankrupt: bool = False
    jail_attempts: int = 0
    ui_message_id: Optional[int] = None

    @property
    def safe_name(self):
        return html.escape(self.name or "玩家")

@dataclass
class Game:
    chat_id: int
    players: list[Player] = field(default_factory=list)
    host_user_id: Optional[int] = None
    started: bool = False
    finished: bool = False
    mode: str = "quick"  # quick / classic
    current_index: int = 0
    round_number: int = 1
    purchase_prompt_id: Optional[int] = None
    pending_prompt_deletions: list[int] = field(default_factory=list)
    action_revision: int = 0
    phase: str = "lobby"  # lobby / roll / buy / jail / debt / end
    board_message_id: Optional[int] = None
    board_message_id2: Optional[int] = None
    property_owner: dict[int, int] = field(default_factory=dict)
    property_level: dict[int, int] = field(default_factory=dict)
    pending_property: Optional[int] = None
    pending_debt_amount: int = 0
    pending_creditor_key: Optional[int] = None
    pending_debt_reason: str = ""
    last_action_text: str = "等待玩家加入"
    turn_task: Optional[asyncio.Task] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_dice: tuple[int, int] = (0, 0)
    extra_turn: bool = False

# 每個群組一場遊戲；目前 V1 仍是記憶體狀態，Render 重啟會清空正在玩的局。
games: dict[int, Game] = {}
user_to_chat: dict[int, int] = {}
