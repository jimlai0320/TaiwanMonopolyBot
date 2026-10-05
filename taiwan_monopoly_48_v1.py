import os
import io
import html
import random
import asyncio
import logging
import threading
import inspect
from dataclasses import dataclass, field
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler

from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest, Forbidden, TimedOut, NetworkError, RetryAfter

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ============================================================
# Render / health check
# ============================================================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Taiwan Monopoly 48 Bot is alive!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), SimpleHandler).serve_forever()


# ============================================================
# Rules
# ============================================================
START_MONEY = 1500
PASS_GO_REWARD = 200
MAX_PLAYERS = 8
MIN_PLAYERS = 2
ROLL_TIMEOUT = 30
BUY_TIMEOUT = 18
JAIL_TIMEOUT = 20
MAX_LEVEL = 4  # 0空地 / 1~3房屋 / 4飯店
JAIL_FINE = 100
QUICK_ROUNDS = 30

# 48格 = 28地產 + 5機會 + 3稅金 + 4交通 + 2監獄相關 + 1免費休息 + 2傳送 + 1起點 + 2特殊
# group 用於同區收集；同一玩家擁有完整 group 時，未升級地租金 x2。
BOARD = [
    {"name":"出發", "kind":"start"},
    {"name":"基隆港", "kind":"property", "price":120, "rent":24, "group":"北海岸"},
    {"name":"淡水", "kind":"property", "price":140, "rent":28, "group":"北海岸"},
    {"name":"機會", "kind":"chance"},
    {"name":"八里", "kind":"property", "price":140, "rent":28, "group":"北海岸"},
    {"name":"台北車站", "kind":"property", "price":220, "rent":45, "group":"台北核心"},
    {"name":"西門町", "kind":"property", "price":220, "rent":45, "group":"台北核心"},
    {"name":"所得稅", "kind":"tax", "amount":120},
    {"name":"中正紀念堂", "kind":"property", "price":240, "rent":50, "group":"台北核心"},
    {"name":"松山機場", "kind":"transport"},
    {"name":"饒河夜市", "kind":"property", "price":240, "rent":50, "group":"台北東區"},
    {"name":"信義區", "kind":"property", "price":280, "rent":60, "group":"台北東區"},
    {"name":"台北101", "kind":"property", "price":380, "rent":85, "group":"台北東區"},
    {"name":"台北捷運", "kind":"transport"},

    {"name":"北投溫泉", "kind":"property", "price":160, "rent":32, "group":"北台灣"},
    {"name":"機會", "kind":"chance"},
    {"name":"九份", "kind":"property", "price":180, "rent":36, "group":"北台灣"},
    {"name":"野柳", "kind":"property", "price":180, "rent":36, "group":"北台灣"},
    {"name":"前往監獄", "kind":"gotojail"},
    {"name":"新竹", "kind":"property", "price":200, "rent":40, "group":"桃竹苗"},
    {"name":"竹北", "kind":"property", "price":200, "rent":40, "group":"桃竹苗"},
    {"name":"機會", "kind":"chance"},
    {"name":"苗栗", "kind":"property", "price":180, "rent":36, "group":"桃竹苗"},
    {"name":"台中", "kind":"property", "price":240, "rent":50, "group":"中台灣"},

    {"name":"免費休息", "kind":"free"},
    {"name":"彰化", "kind":"property", "price":200, "rent":40, "group":"中台灣"},
    {"name":"鹿港", "kind":"property", "price":200, "rent":40, "group":"中台灣"},
    {"name":"牌照稅", "kind":"tax", "amount":100},
    {"name":"南投", "kind":"property", "price":220, "rent":45, "group":"中台灣"},
    {"name":"日月潭", "kind":"property", "price":240, "rent":50, "group":"中台灣"},
    {"name":"高鐵", "kind":"transport"},
    {"name":"嘉義", "kind":"property", "price":200, "rent":40, "group":"嘉南"},
    {"name":"機會", "kind":"chance"},
    {"name":"台南", "kind":"property", "price":240, "rent":50, "group":"嘉南"},
    {"name":"安平", "kind":"property", "price":220, "rent":45, "group":"嘉南"},
    {"name":"高雄", "kind":"property", "price":260, "rent":55, "group":"高屏"},
    {"name":"傳送：東部", "kind":"teleport", "target":43},
    {"name":"監獄／探監", "kind":"jail"},

    {"name":"駁二", "kind":"property", "price":220, "rent":45, "group":"高屏"},
    {"name":"墾丁", "kind":"property", "price":260, "rent":55, "group":"高屏"},
    {"name":"屏東", "kind":"property", "price":200, "rent":40, "group":"高屏"},
    {"name":"機會", "kind":"chance"},
    {"name":"花蓮", "kind":"property", "price":220, "rent":45, "group":"東台灣"},
    {"name":"台東", "kind":"property", "price":220, "rent":45, "group":"東台灣"},
    {"name":"台鐵", "kind":"transport"},
    {"name":"綠島", "kind":"property", "price":180, "rent":36, "group":"東台灣"},
    {"name":"環島獎金", "kind":"special", "amount":150},
    {"name":"傳送：北部", "kind":"teleport", "target":5},
]

assert len(BOARD) == 48
JAIL_INDEX = 37
TRANSPORT_RENTS = [0, 30, 60, 120, 200]

PLAYER_COLORS = [
    (235, 67, 53), (62, 126, 236), (247, 196, 49), (46, 184, 92),
    (158, 74, 219), (242, 130, 48), (236, 92, 150), (65, 206, 206),
]

CHANCE_EVENTS = [
    ("🎁 年終獎金 +$150", "money", 150),
    ("🧧 發票中獎 +$200", "money", 200),
    ("🚑 臨時醫療費 -$100", "money", -100),
    ("🚕 交通支出 -$60", "money", -60),
    ("🏦 銀行紅利 +$100", "money", 100),
    ("📱 手機摔壞 -$80", "money", -80),
    ("🚄 高鐵快線，前進 5 格", "move", 5),
    ("↩️ 走錯路，後退 3 格", "move", -3),
    ("🎉 每位其他玩家給你 $30", "collect_each", 30),
    ("🎁 你給每位其他玩家 $20", "pay_each", 20),
    ("🚔 直接前往監獄", "jail", 0),
    ("✈️ 免費機票，前往下一個交通站", "next_transport", 0),
]


# ============================================================
# Data models
# ============================================================
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
    phase: str = "lobby"  # lobby / roll / buy / jail / debt / end
    board_message_id: Optional[int] = None
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


games: dict[int, Game] = {}
user_to_chat: dict[int, int] = {}


# ============================================================
# Core helpers
# ============================================================
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


# ============================================================
# UI helpers
# ============================================================
def button(text, callback_data=None, url=None, style=None):
    kwargs = {"text": text}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if style and "style" in inspect.signature(InlineKeyboardButton).parameters:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def fit_text(draw, text, max_width, start_size=22, min_size=10, bold=False):
    for size in range(start_size, min_size - 1, -1):
        font = get_font(size, bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
    return get_font(min_size, bold)


def tile_coords(index: int):
    """V5：接近排7比例的群組棋盤座標，讓 Telegram 預覽盡量吃滿聊天寬度。"""
    x_left, x_right = 14, 1186
    y_top, y_bottom = 108, 985
    top_n, side_n = 14, 10
    top_h, side_w = 108, 118
    inner_h = (y_bottom - y_top) - 2 * top_h
    top_w = (x_right - x_left) / top_n

    if index < 14:
        x0 = x_left + index * top_w
        return int(x0), y_top, int(x0 + top_w), y_top + top_h
    if index < 24:
        j = index - 14
        y0 = y_top + top_h + j * (inner_h / side_n)
        return x_right - side_w, int(y0), x_right, int(y0 + inner_h / side_n)
    if index < 38:
        j = index - 24
        x1 = x_right - j * top_w
        return int(x1 - top_w), y_bottom - top_h, int(x1), y_bottom
    j = index - 38
    y1 = y_bottom - top_h - j * (inner_h / side_n)
    return x_left, int(y1 - inner_h / side_n), x_left + side_w, int(y1)

def _draw_centered(draw, box, text, font, fill, y=None, stroke_width=0, stroke_fill=None):
    x0, y0, x1, y1 = box
    tb = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    tx = x0 + (x1 - x0 - tw) / 2
    ty = y if y is not None else y0 + (y1 - y0 - th) / 2
    draw.text((tx, ty), text, font=font, fill=fill,
              stroke_width=stroke_width, stroke_fill=stroke_fill)


def _tile_symbol(kind):
    return {
        "start": "GO", "chance": "?", "tax": "$", "transport": "交通",
        "jail": "監獄", "gotojail": "監獄", "free": "休息",
        "teleport": ">>", "special": "+$",
    }.get(kind, "")


def _plain_text(text: str) -> str:
    return html.unescape(
        text.replace("<b>", "").replace("</b>", "")
            .replace("<code>", "").replace("</code>", "")
            .replace("<i>", "").replace("</i>", "")
    )


def _draw_taiwan_center(d: ImageDraw.ImageDraw):
    """V5：中央主視覺只佔棋盤內圈，不再拉高整張圖。"""
    d.rounded_rectangle((132, 224, 1068, 872), radius=28,
                        fill=(73, 178, 218), outline=(111, 211, 235), width=3)
    island = [
        (615,292),(650,326),(674,370),(684,423),(673,476),(661,530),
        (641,583),(626,637),(603,692),(580,748),(557,801),(540,842),
        (512,807),(493,756),(480,701),(468,645),(468,590),(479,534),
        (490,480),(505,426),(525,377),(548,335),(576,305)
    ]
    d.polygon(island, fill=(82,162,88), outline=(34,85,72))
    d.line(island+[island[0]], fill=(36,105,76), width=5)
    mountains=[(574,350),(620,405),(558,474),(620,538),(552,610),(604,682),(548,760)]
    d.line(mountains, fill=(38,119,76), width=24)
    d.line(mountains, fill=(120,190,111), width=9)
    for x,y in [(566,390),(628,462),(534,545),(600,610),(548,694),(590,760)]:
        d.ellipse((x-8,y-8,x+8,y+8), fill=(255,231,108), outline=(34,85,72), width=2)
    for x,y,r in [(220,300,25),(960,310,23),(234,730,20),(943,770,25)]:
        d.ellipse((x-r,y-r//2,x+r,y+r//2), fill=(223,238,191), outline=(36,113,115), width=2)

def generate_board_image(game: Game) -> io.BytesIO:
    """V5 Telegram 大字版：只把棋盤放進圖片，玩家明細留在 caption。"""
    W, H = 1200, 1020
    img = Image.new("RGB", (W, H), (7, 20, 32))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle((8, 8, W-8, H-8), radius=26, fill=(10,28,43), outline=(45,103,132), width=4)

    # 頂部資訊列
    d.text((28, 18), "台灣大富翁", font=get_font(42, True), fill=(255,221,83),
           stroke_width=2, stroke_fill=(33,48,42))
    mode = "30回合" if game.mode == "quick" else "經典"
    d.text((32, 67), f"第 {game.round_number} 回合｜{mode}", font=get_font(18, True), fill=(218,235,244))
    if game.players:
        cur = game.players[game.current_index]
        cc = PLAYER_COLORS[game.current_index % len(PLAYER_COLORS)]
        d.rounded_rectangle((690, 18, 1170, 88), radius=15, fill=(14,37,53), outline=cc, width=4)
        d.ellipse((710, 34, 750, 74), fill=cc, outline=(245,245,245), width=2)
        turn = "遊戲結束" if game.finished else f"目前輪到：{cur.name}"
        d.text((768, 29), turn, font=fit_text(d, turn, 380, 27, 16, True), fill=(245,247,250))
        if not game.finished:
            d.text((768, 60), f"${cur.money}｜{BOARD[cur.position]['name']}", font=get_font(15), fill=(164,198,214))

    type_colors = {
        "start": (255,220,112), "property": (241,246,224), "chance": (255,216,109),
        "tax": (255,224,150), "transport": (187,224,244), "jail": (214,226,236),
        "gotojail": (218,224,233), "free": (185,228,199), "teleport": (215,194,247),
        "special": (255,197,214),
    }

    for i, tile in enumerate(BOARD):
        x0,y0,x1,y1 = tile_coords(i)
        fill = type_colors.get(tile["kind"], (232,235,238))
        owner = get_owner(game, i)
        owner_color = None
        if owner:
            oi = game.players.index(owner)
            owner_color = PLAYER_COLORS[oi % len(PLAYER_COLORS)]
            fill = tuple(int(fill[k]*.80 + owner_color[k]*.20) for k in range(3))
        d.rounded_rectangle((x0+2,y0+2,x1-2,y1-2), radius=6, fill=fill, outline=(20,43,56), width=2)
        if owner_color:
            d.rectangle((x0+4,y0+4,x1-4,y0+10), fill=owner_color)
        name = tile["name"]
        f = fit_text(d, name, max(42,x1-x0-8), 17, 9, True)
        _draw_centered(d,(x0+2,y0+5,x1-2,y0+34),name,f,(17,34,42),y=y0+7)
        kind=tile["kind"]
        if kind=="property":
            price=f"${tile['price']}"
            pf=fit_text(d,price,max(40,x1-x0-8),15,9,True)
            _draw_centered(d,(x0,y1-26,x1,y1-3),price,pf,(20,47,55),y=y1-25)
            level=game.property_level.get(i,0)
            if level:
                lv="飯店" if level==4 else "房"*level
                _draw_centered(d,(x0,y0+36,x1,y1-28),lv,fit_text(d,lv,max(38,x1-x0-10),13,9,True),(139,76,20),y=y0+39)
        elif kind=="chance":
            _draw_centered(d,(x0,y0+30,x1,y1),"?",get_font(34,True),(192,57,42),y=y0+39)
        elif kind=="tax":
            t=f"-${tile['amount']}"
            _draw_centered(d,(x0,y0+30,x1,y1),t,fit_text(d,t,max(40,x1-x0-8),15,9,True),(174,77,0),y=y1-26)
        else:
            symbol=_tile_symbol(kind)
            if symbol:
                _draw_centered(d,(x0,y0+30,x1,y1-4),symbol,fit_text(d,symbol,max(42,x1-x0-10),17,9,True),(28,70,88),y=y0+42)

    _draw_taiwan_center(d)
    _draw_centered(d,(250,345,950,430),"台灣大富翁",get_font(58,True),(255,222,80),
                   y=350,stroke_width=4,stroke_fill=(38,55,40))
    _draw_centered(d,(300,432,900,475),"環島之旅・買下全台！",get_font(19,True),(244,249,250),
                   y=438,stroke_width=2,stroke_fill=(26,76,92))

    occ={}
    for idx,p in enumerate(game.players):
        if not p.bankrupt:
            occ.setdefault(p.position,[]).append(idx)
    for pos,ids in occ.items():
        x0,y0,x1,y1=tile_coords(pos)
        for n,pi in enumerate(ids):
            c=PLAYER_COLORS[pi % len(PLAYER_COLORS)]
            px=x0+18+(n%4)*21; py=y1-29-(n//4)*21
            d.ellipse((px-8,py-8,px+8,py+8),fill=c,outline=(6,16,22),width=2)
            d.polygon([(px,py+5),(px-10,py+22),(px+10,py+22)],fill=c,outline=(6,16,22))

    out=io.BytesIO()
    img.save(out,format="PNG",optimize=False,compress_level=6)
    img.close()
    out.seek(0)
    return out

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


# ============================================================
# UI send/update
# ============================================================
async def safe_edit_or_send_board(game: Game, context):
    caption = board_caption(game)
    markup = board_keyboard(game, context.bot.username or "")
    if game.board_message_id:
        try:
            await context.bot.edit_message_media(
                chat_id=game.chat_id, message_id=game.board_message_id,
                media=InputMediaPhoto(media=generate_board_image(game), caption=caption, parse_mode="HTML"),
                reply_markup=markup)
            return
        except BadRequest as e:
            if "Message is not modified" in str(e):
                return
        except RetryAfter as e:
            await asyncio.sleep(float(e.retry_after))
        except Exception:
            logging.exception("更新群組棋盤失敗")
    try:
        msg = await context.bot.send_photo(game.chat_id, generate_board_image(game), caption=caption, reply_markup=markup, parse_mode="HTML")
        game.board_message_id = msg.message_id
    except Exception:
        logging.exception("發送群組棋盤失敗")


async def send_private_ui(game: Game, player: Player, context):
    if player.is_bot or not player.user_id:
        return
    caption = private_caption(game, player)
    markup = private_keyboard(game, player)
    if player.ui_message_id:
        try:
            await context.bot.edit_message_media(
                chat_id=player.user_id, message_id=player.ui_message_id,
                media=InputMediaPhoto(media=generate_board_image(game), caption=caption, parse_mode="HTML"),
                reply_markup=markup)
            return
        except BadRequest as e:
            if "Message is not modified" in str(e):
                return
        except (Forbidden, TimedOut, NetworkError):
            pass
        except Exception:
            logging.exception("編輯私人介面失敗 user=%s", player.user_id)
    try:
        msg = await context.bot.send_photo(player.user_id, generate_board_image(game), caption=caption, reply_markup=markup, parse_mode="HTML")
        player.ui_message_id = msg.message_id
    except Forbidden:
        logging.warning("無法私訊 %s：玩家尚未 /start 或封鎖 Bot", player.name)
    except Exception:
        logging.exception("私人介面發送失敗 user=%s", player.user_id)


async def refresh_all_ui(game: Game, context):
    await safe_edit_or_send_board(game, context)
    await asyncio.gather(*(send_private_ui(game,p,context) for p in game.players if not p.is_bot), return_exceptions=True)


# ============================================================
# Money / debt / bankruptcy
# ============================================================
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


# ============================================================
# Tile resolution / gameplay
# ============================================================
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
        if game.turn_task:
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


async def do_roll(game: Game, player: Player, context, auto=False):
    if game.phase != "roll" or current_player(game) != player or player.bankrupt:
        return
    d1,d2 = random.randint(1,6), random.randint(1,6)
    game.last_dice = (d1,d2)
    passed = move_player(player, d1+d2)
    prefix = "⏰ 系統代擲" if auto else "🎲 擲骰子"
    reward = f"，經過出發點 +${PASS_GO_REWARD}" if passed else ""
    game.last_action_text = f"{prefix}：{player.safe_name} 擲出 {d1}+{d2}={d1+d2}{reward}。"
    game.extra_turn = (d1 == d2)
    result = await resolve_tile(game, player, context)
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
    roll = random.randint(1,6)
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


# ============================================================
# Timers / AI
# ============================================================
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


# ============================================================
# Commands / callbacks
# ============================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        game = find_game_by_user(update.effective_user.id)
        if game:
            p = next((p for p in game.players if p.user_id == update.effective_user.id), None)
            if p:
                await send_private_ui(game,p,context); return
    await update.message.reply_text("🏙 <b>台灣大富翁 48格</b>\n\n請到群組輸入 /newgame 建立遊戲。\n2～8 人可玩。", parse_mode="HTML")


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
    games[chat_id]=game; user_to_chat[u.id]=chat_id
    msg = await update.message.reply_text(lobby_text(game), reply_markup=lobby_keyboard(), parse_mode="HTML")
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
    if game.board_message_id:
        try: await context.bot.delete_message(game.chat_id,game.board_message_id)
        except Exception: pass
        game.board_message_id=None
    await refresh_all_ui(game,context)
    p=current_player(game)
    if p.is_bot: asyncio.create_task(run_bot_turn(game,context))
    else: start_turn_timer(game,context)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = games.get(update.effective_chat.id) or find_game_by_user(update.effective_user.id)
    if not game:
        await update.message.reply_text("目前沒有遊戲。"); return
    if game.turn_task: game.turn_task.cancel()
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
        for p in game.players:
            if p.user_id: user_to_chat.pop(p.user_id,None)
        games.pop(game.chat_id,None)
        try: await q.edit_message_text("🗑 遊戲已取消。")
        except Exception: pass
        return

    game=find_game_by_user(uid)
    if not game:
        await q.answer("找不到你的遊戲。",show_alert=True); return
    player=next((p for p in game.players if p.user_id==uid),None)
    if not player:
        await q.answer("你不在這場遊戲。",show_alert=True); return

    if data == "mono_status":
        ranking=sorted(game.players,key=lambda p:total_asset_value(game,p),reverse=True)
        txt="\n".join(f"{i}. {p.name}｜${total_asset_value(game,p)}{' ☠' if p.bankrupt else ''}" for i,p in enumerate(ranking,1))
        await q.answer(txt,show_alert=True); return
    if data == "mono_assets":
        await q.answer(player_assets_text(game,player),show_alert=True); return
    if data == "mono_map":
        await q.answer(f"48格地圖｜你目前在第 {player.position+1} 格：{BOARD[player.position]['name']}",show_alert=True); return

    async with game.lock:
        if current_player(game)!=player or player.bankrupt:
            await q.answer("現在不是你的回合。",show_alert=True); return
        if game.turn_task: game.turn_task.cancel()

        if data == "mono_roll":
            await q.answer("🎲 擲骰子！"); await do_roll(game,player,context); return
        if data == "mono_buy":
            await q.answer("購買！"); await buy_property(game,player,True,context); return
        if data == "mono_pass_buy":
            await q.answer("已放棄。"); await buy_property(game,player,False,context); return
        if data == "mono_jail_pay":
            await q.answer("支付保釋金。"); await do_jail_choice(game,player,context,pay=True); return
        if data == "mono_jail_roll":
            await q.answer("試擲！"); await do_jail_choice(game,player,context,pay=False); return
        if data == "mono_upgrade":
            ok=await upgrade_current_property(game,player,context)
            await q.answer("升級完成！" if ok else "目前無法升級。",show_alert=not ok); return
        if data.startswith("mono_mortgage:") and game.phase=="debt":
            try: idx=int(data.split(":",1)[1])
            except Exception: await q.answer(); return
            if idx not in player.properties or idx in player.mortgaged:
                await q.answer("無法抵押。",show_alert=True); return
            player.mortgaged.add(idx); value=mortgage_value(idx); player.money+=value
            game.last_action_text=f"🏦 {player.safe_name} 抵押【{BOARD[idx]['name']}】取得 ${value}。"
            if player.money>=game.pending_debt_amount:
                await q.answer("籌款完成！"); await settle_pending_debt(game,player,context)
            else:
                await q.answer(f"抵押取得 ${value}"); await refresh_all_ui(game,context)
            return
        if data == "mono_bankrupt" and game.phase=="debt":
            receiver=creditor_from_key(game,game.pending_creditor_key)
            if receiver: receiver.money += player.money
            player.money=0; bankrupt_player(game,player,receiver); game.phase="roll"
            game.last_action_text=f"☠️ {player.safe_name} 宣告破產。"
            await q.answer("已宣告破產。"); await after_action_advance(game,player,context); return

    await q.answer()


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start","開啟遊戲"), BotCommand("newgame","建立大富翁房間"),
        BotCommand("join","加入遊戲"), BotCommand("status","查看排名"), BotCommand("cancel","取消遊戲"),
    ])


def main():
    token=os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("請設定 BOT_TOKEN")
    threading.Thread(target=run_web_server,daemon=True).start()
    app=(Application.builder().token(token).post_init(post_init).build())
    app.add_handler(CommandHandler("start",start_command))
    app.add_handler(CommandHandler("newgame",newgame_command))
    app.add_handler(CommandHandler("join",join_command))
    app.add_handler(CommandHandler("status",status_command))
    app.add_handler(CommandHandler("cancel",cancel_command))
    app.add_handler(CallbackQueryHandler(callback_router, pattern=r"^mono_"))
    logging.info("台灣大富翁 48格 Bot 啟動")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
