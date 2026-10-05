# -*- coding: utf-8 -*-
"""群組棋盤圖片渲染。UI 美術要改，主要改這個檔案。"""
import io
import html
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from board_data import BOARD, PLAYER_COLORS
from models import Game
from helpers import current_player, get_owner

ASSET_DIR = Path(__file__).resolve().parent / "assets"

_FONT_CACHE_DIR = Path("/tmp/taiwan_monopoly_fonts")
_CJK_FONT_URL = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
_CJK_FONT_CACHE = None


def _resolve_cjk_font():
    """取得可顯示繁體中文的字型；Render 沒有中文字型時自動快取一份到 /tmp。"""
    global _CJK_FONT_CACHE
    if _CJK_FONT_CACHE and Path(_CJK_FONT_CACHE).exists():
        return _CJK_FONT_CACHE

    # 常見 Linux / Render / 本機字型位置。
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/mingliu.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            _CJK_FONT_CACHE = candidate
            return candidate

    # Render Free 常沒有 CJK 字型；只在缺字型時下載一次到 /tmp。
    try:
        import urllib.request
        _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached = _FONT_CACHE_DIR / "NotoSansCJKtc-Regular.otf"
        if not cached.exists() or cached.stat().st_size < 1_000_000:
            urllib.request.urlretrieve(_CJK_FONT_URL, cached)
        _CJK_FONT_CACHE = str(cached)
        return _CJK_FONT_CACHE
    except Exception as exc:
        # 失敗時仍讓 Bot 繼續跑；只是圖片中文字可能退回方框。
        import logging
        logging.warning("無法取得繁體中文字型：%s", exc)
        return None


def get_font(size, bold=False):
    cjk = _resolve_cjk_font()
    if cjk:
        try:
            # 同一套 TC 字型同時用於一般與粗體；粗體視覺由較大字級/描邊輔助。
            return ImageFont.truetype(cjk, size)
        except Exception:
            pass

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
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
        "start": "GO", "chance": "?", "tax": "$", "transport": "T",
        "jail": "JAIL", "gotojail": "JAIL", "free": "REST",
        "teleport": ">>", "special": "+$",
    }.get(kind, "")

def generate_board_image(game: Game) -> io.BytesIO:
    # V9：直式長圖 + 外圈環島棋盤（8 / 16 / 8 / 16）
    # 目標：保留「繞一圈」的視覺，同時把每格放大到更適合 Telegram 觀看。
    W, H = 1200, 2200
    img = Image.new("RGBA", (W, H), (9, 28, 45, 255))
    d = ImageDraw.Draw(img)

    # ==== 背景與外框 ====
    d.rounded_rectangle((8, 8, W - 8, H - 8), radius=34, fill=(10, 31, 48), outline=(60, 111, 138), width=4)
    d.rounded_rectangle((18, 18, W - 18, H - 18), radius=28, outline=(25, 70, 92), width=2)

    # ==== 上方標題條 ====
    d.rounded_rectangle((26, 24, W - 26, 144), radius=28, fill=(12, 46, 74), outline=(92, 151, 183), width=3)
    d.ellipse((42, 40, 118, 116), fill=(245, 245, 249), outline=(13, 23, 30), width=2)
    d.text((58, 56), "🎲", font=get_font(42, True), fill=(40, 40, 40))
    d.text((132, 35), "台灣大富翁", font=get_font(66, True), fill=(255, 211, 86), stroke_width=5, stroke_fill=(25, 38, 47))
    mode = "快速模式" if game.mode == "quick" else "經典模式"
    d.rounded_rectangle((412, 42, 690, 96), radius=18, fill=(17, 61, 103), outline=(105, 171, 214), width=2)
    _draw_centered(d, (412, 42, 690, 96), f"第 {game.round_number} 回合｜{mode}", get_font(23, True), (246, 247, 249))

    cur = current_player(game)
    cur_color = PLAYER_COLORS[game.current_index % len(PLAYER_COLORS)]
    d.rounded_rectangle((726, 34, W - 42, 116), radius=22, fill=(11, 38, 64), outline=(245, 205, 92), width=3)
    d.ellipse((744, 48, 796, 100), fill=cur_color, outline=(248, 248, 248), width=3)
    d.text((818, 43), f"目前輪到：{cur.name}", font=get_font(42, True), fill=(255, 227, 133))
    d.text((818, 82), "擲骰子，展開你的台灣之旅吧！", font=get_font(20), fill=(210, 226, 236))

    # ==== 棋盤區域：8 / 16 / 8 / 16 ====
    board_left, board_top = 26, 168
    board_right, board_bottom = W - 26, H - 26
    top_n, side_n = 8, 16
    tile_w = int((board_right - board_left) / top_n)   # 約 143
    side_w = tile_w
    top_h = 148
    bottom_h = 148
    inner_left = board_left + side_w
    inner_right = board_right - side_w
    inner_top = board_top + top_h
    inner_bottom = board_bottom - bottom_h
    side_h = (inner_bottom - inner_top) / side_n

    def tile_coords(index: int):
        # 0-7 上，8-23 右，24-31 下（由右往左），32-47 左（由下往上）
        if index < 8:
            x0 = board_left + index * tile_w
            return int(x0), board_top, int(x0 + tile_w), board_top + top_h
        if index < 24:
            j = index - 8
            y0 = inner_top + j * side_h
            return board_right - side_w, int(y0), board_right, int(y0 + side_h)
        if index < 32:
            j = index - 24
            x1 = board_right - j * tile_w
            return int(x1 - tile_w), board_bottom - bottom_h, int(x1), board_bottom
        j = index - 32
        y1 = board_bottom - bottom_h - j * side_h
        return board_left, int(y1 - side_h), board_left + side_w, int(y1)

    # ==== 中央背景：優先使用預先生成的漂亮台灣圖 ====
    cx0, cy0, cx1, cy1 = inner_left + 12, inner_top + 12, inner_right - 12, inner_bottom - 12
    d.rounded_rectangle((cx0, cy0, cx1, cy1), radius=30, fill=(18, 97, 153), outline=(80, 152, 194), width=3)

    bg_candidates = [str(ASSET_DIR / 'taiwan_bg.png')]
    bg_loaded = False
    for bg_path in bg_candidates:
        try:
            bg = Image.open(bg_path).convert('RGBA')
            bw, bh = bg.size
            # 優先裁出中央的台灣主視覺區域
            # 專案素材已裁成適合中央區的台灣主視覺，直接使用。
            crop = bg
            crop = crop.resize((cx1 - cx0 - 24, cy1 - cy0 - 24))
            # 柔化邊緣底板
            panel = Image.new('RGBA', img.size, (0, 0, 0, 0))
            panel_draw = ImageDraw.Draw(panel)
            panel_draw.rounded_rectangle((cx0 + 12, cy0 + 12, cx1 - 12, cy1 - 12), radius=24, fill=(255, 255, 255, 255))
            panel.paste(crop, (cx0 + 12, cy0 + 12), crop)
            img.alpha_composite(panel)
            bg.close()
            bg_loaded = True
            break
        except Exception:
            pass

    if not bg_loaded:
        # Fallback：純 Pillow 繪製簡化海面 + 台灣島
        d.rounded_rectangle((cx0 + 12, cy0 + 12, cx1 - 12, cy1 - 12), radius=24, fill=(80, 176, 216))
        island = [
            (718, 478), (764, 548), (754, 650), (799, 760), (777, 902), (742, 1056),
            (700, 1176), (654, 1264), (607, 1226), (571, 1113), (545, 978), (533, 830),
            (540, 687), (565, 568), (612, 488)
        ]
        d.polygon(island, fill=(98, 184, 94), outline=(39, 102, 60))
        d.line([(652, 520), (678, 622), (660, 736), (696, 860), (666, 980), (638, 1112)], fill=(59, 124, 67), width=10)
        for ex, ey, rx, ry in [(402, 632, 28, 14), (920, 584, 34, 16), (386, 1020, 20, 10), (945, 1154, 30, 14)]:
            d.ellipse((ex-rx, ey-ry, ex+rx, ey+ry), fill=(236, 229, 175), outline=(84, 112, 124), width=2)

    # 中央標題卡
    d.rounded_rectangle((cx0 + 44, cy0 + 84, cx0 + 465, cy0 + 208), radius=24, fill=(13, 57, 101), outline=(255, 220, 108), width=3)
    d.text((cx0 + 68, cy0 + 96), "台灣大富翁", font=get_font(58, True), fill=(255, 214, 88), stroke_width=4, stroke_fill=(28, 49, 67))
    d.text((cx0 + 106, cy0 + 168), "環島之旅・買下全台・成為大富翁！", font=get_font(22, True), fill=(239, 243, 246))

    # ==== 格子顏色 ====
    type_colors = {
        'start': (218, 245, 205), 'property': (241, 246, 230), 'chance': (255, 222, 122),
        'tax': (255, 182, 136), 'transport': (198, 228, 247), 'jail': (205, 217, 236),
        'gotojail': (208, 217, 232), 'free': (189, 235, 197), 'teleport': (220, 199, 248),
        'special': (255, 201, 221),
    }

    def center_text(box, text, size, fill, yoff=0, bold=True):
        font = get_font(size, bold)
        _draw_centered(d, box, text, font, fill, y=box[1] + yoff)

    # ==== 繪製 48 格 ====
    for i, tile in enumerate(BOARD):
        x0, y0, x1, y1 = tile_coords(i)
        kind = tile['kind']
        fill = type_colors.get(kind, (240, 242, 244))
        owner = get_owner(game, i)
        owner_color = None
        if owner:
            owner_color = PLAYER_COLORS[game.players.index(owner) % len(PLAYER_COLORS)]
            fill = tuple(int(fill[k] * 0.73 + owner_color[k] * 0.27) for k in range(3))

        d.rounded_rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), radius=10, fill=fill, outline=(17, 43, 58), width=2)
        # 小編號角標
        d.rounded_rectangle((x0 + 4, y0 + 4, x0 + 32, y0 + 28), radius=8, fill=(23, 92, 58), outline=(247, 247, 247), width=1)
        _draw_centered(d, (x0 + 4, y0 + 3, x0 + 32, y0 + 28), str(i + 1), get_font(15, True), (255, 255, 255))

        # 擁有者色條
        if owner_color:
            if i < 8 or 24 <= i < 32:
                d.rectangle((x0 + 6, y0 + 30, x1 - 6, y0 + 38), fill=owner_color)
            else:
                d.rectangle((x0 + 6, y0 + 30, x0 + 14, y1 - 6), fill=owner_color)

        # 名稱
        name_font = fit_text(d, tile['name'], x1 - x0 - 10, 22 if (i < 8 or 24 <= i < 32) else 20, 10, True)
        _draw_centered(d, (x0 + 6, y0 + 34, x1 - 6, y0 + 68), tile['name'], name_font, (14, 31, 39), y=y0 + 38)

        # 中段內容
        if kind == 'property':
            pic_box = (x0 + 8, y0 + 62, x1 - 8, y1 - 26)
            d.rounded_rectangle(pic_box, radius=8, fill=(193, 225, 246), outline=(155, 191, 214), width=1)
            # 超簡景點插圖感
            d.polygon([(pic_box[0] + 8, pic_box[3] - 8), ((pic_box[0] + pic_box[2]) // 2), pic_box[1] + 8, (pic_box[2] - 8, pic_box[3] - 8)], fill=(132, 193, 121))
            # 小格（左右側）高度較低，建築圖示必須依可用高度縮放，避免座標反轉。
            pb_h = max(8, pic_box[3] - pic_box[1])
            by0 = pic_box[1] + max(3, int(pb_h * 0.22))
            by1 = pic_box[3] - max(3, int(pb_h * 0.12))
            if by1 >= by0:
                d.rectangle((pic_box[0] + (pic_box[2]-pic_box[0])*0.43, by0, pic_box[0] + (pic_box[2]-pic_box[0])*0.57, by1), fill=(219, 198, 167))
            price = f"${tile['price']}"
            d.text((x0 + 10, y1 - 22), price, font=fit_text(d, price, x1 - x0 - 10, 18, 10, True), fill=(26, 43, 53))
            lvl = game.property_level.get(i, 0)
            if lvl:
                lv = '🏨' if lvl == 4 else '★' * lvl
                d.text((x1 - 38, y1 - 24), lv, font=get_font(16, True), fill=(183, 88, 18))
        elif kind == 'chance':
            _draw_centered(d, (x0, y0 + 54, x1, y1 - 8), '?', get_font(50, True), (195, 59, 42), y=y0 + 62)
        elif kind == 'tax':
            center_text((x0, y0 + 58, x1, y1 - 40), '稅金', 18, (93, 56, 22), 0)
            amt = f"-${tile['amount']}"
            _draw_centered(d, (x0, y1 - 28, x1, y1 - 4), amt, get_font(19, True), (167, 61, 26), y=y1 - 24)
        elif kind == 'transport':
            center_text((x0, y0 + 56, x1, y1 - 12), '交通', 19, (36, 86, 110), 8)
        elif kind == 'jail':
            center_text((x0, y0 + 56, x1, y1 - 12), '監獄', 24, (42, 54, 76), 8)
        elif kind == 'gotojail':
            f = fit_text(d, '前往監獄', x1 - x0 - 10, 20, 11, True)
            _draw_centered(d, (x0 + 4, y0 + 56, x1 - 4, y1 - 10), '前往監獄', f, (42, 54, 76), y=y0 + 70)
        elif kind == 'free':
            f = fit_text(d, '免費休息', x1 - x0 - 10, 20, 11, True)
            _draw_centered(d, (x0 + 4, y0 + 56, x1 - 4, y1 - 10), '免費休息', f, (40, 98, 58), y=y0 + 70)
        elif kind == 'teleport':
            center_text((x0, y0 + 56, x1, y1 - 12), '傳送', 22, (78, 53, 121), 8)
        elif kind == 'special':
            amt = f"+${tile['amount']}"
            center_text((x0, y0 + 56, x1, y1 - 12), amt, 24, (145, 75, 16), 8)
        elif kind == 'start':
            center_text((x0, y0 + 52, x1, y1 - 12), 'GO', 40, (23, 124, 53), 8)

    # ==== 棋子（支援同格多人）====
    occ = {}
    for idx, p in enumerate(game.players):
        if not p.bankrupt:
            occ.setdefault(p.position, []).append(idx)
    for pos, ids in occ.items():
        x0, y0, x1, y1 = tile_coords(pos)
        for n, pi in enumerate(ids):
            c = PLAYER_COLORS[pi % len(PLAYER_COLORS)]
            px = x1 - 24 - (n % 2) * 26
            py = y0 + 48 + (n // 2) * 30
            d.ellipse((px - 10, py - 10, px + 10, py + 10), fill=c, outline=(248, 248, 248), width=2)
            d.polygon([(px, py + 8), (px - 12, py + 28), (px + 12, py + 28)], fill=c, outline=(16, 25, 31))

    # ==== 輸出 ====
    out = io.BytesIO()
    img = img.convert('RGB')
    img.save(out, format='PNG', optimize=True)
    out.seek(0)
    try:
        img.close()
    except Exception:
        pass
    return out


def generate_group_board_images(game: Game):
    """
    產生 Telegram 群組專用的兩張連續棋盤圖。

    不是簡單在正中間硬切，而是：
    1. 先渲染完整 1200x2200 的長型環島棋盤
    2. 依棋盤實際格線位置切成上下兩張
    3. 在中央背景區保留少量重疊

    這樣可以避免切線剛好切到格子，並讓上下看起來像同一張完整地圖。
    """
    full_buf = generate_board_image(game)
    full_buf.seek(0)
    with Image.open(full_buf) as full:
        full = full.convert("RGB")
        w, h = full.size

        # 與 generate_board_image 的 V9 版面一致
        board_top = 168
        board_bottom = h - 26
        top_h = 148
        bottom_h = 148
        inner_top = board_top + top_h
        inner_bottom = board_bottom - bottom_h
        side_n = 16
        side_h = (inner_bottom - inner_top) / side_n

        # 取中間分界：左右邊格子的第 8 / 9 列之間，屬於格線邊界，不會切到格子。
        # 這裡不要再做重疊，否則 Telegram 直向堆疊時會看起來「沒對齊」或重複一段。
        split_boundary = int(round(inner_top + side_h * 8))

        top_end = split_boundary
        bottom_start = split_boundary

        top = full.crop((0, 0, w, top_end))
        bottom = full.crop((0, bottom_start, w, h))

        top_buf = io.BytesIO()
        bottom_buf = io.BytesIO()
        top.save(top_buf, format="PNG", optimize=True)
        bottom.save(bottom_buf, format="PNG", optimize=True)
        top_buf.seek(0)
        bottom_buf.seek(0)
        try:
            top.close()
            bottom.close()
        except Exception:
            pass
    try:
        full_buf.close()
    except Exception:
        pass
    return top_buf, bottom_buf
