# -*- coding: utf-8 -*-
"""32 格台灣大富翁棋盤渲染器（完整卡片素材版）。

重點：
- 32 格全部使用相同尺寸。
- 每格直接使用 assets/tiles/ 內原本生成的完整卡片；不重畫地名、編號、價格。
- 不同來源卡片比例不一致時，完整卡片等比例置中，空白區以同一張卡的模糊延伸補滿，避免黑邊。
- 中央為長版台灣主視覺。
- 群組棋盤精準切成上下兩張，切線落在格線，不切到任何格子。
"""
import io
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

from board_data import BOARD, PLAYER_COLORS
from models import Game
from helpers import current_player, get_owner

ASSET_DIR = Path(__file__).resolve().parent / "assets"
TILE_ASSET_DIR = ASSET_DIR / "tiles"

_FONT_CACHE_DIR = Path("/tmp/taiwan_monopoly_fonts")
_CJK_FONT_URL = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
_CJK_FONT_CACHE = None

# ===== 長版 32 格棋盤規格 =====
# 卡片固定 3:4；所有 32 格的外框尺寸完全相同。
CARD_W = 210
CARD_H = 280
GRID_COLS = 8
GRID_ROWS = 10
BOARD_X = 50
BOARD_Y = 170
BOARD_W = GRID_COLS * CARD_W          # 1680
BOARD_H = GRID_ROWS * CARD_H          # 2800
W = BOARD_X * 2 + BOARD_W             # 1780
H = BOARD_Y + BOARD_H + 30            # 3000

TILE_ART_FILES = {
    0: "01_go.png",
    1: "02_keelung_port.png",
    2: "03_tamsui.png",
    3: "04_chance.png",
    4: "05_bali.png",
    5: "06_taipei_station.png",
    6: "07_ximending.png",
    7: "08_income_tax.png",
    8: "09_cks_memorial_hall.png",
    9: "10_songshan_airport.png",
    10: "11_raohe_night_market.png",
    11: "12_taipei_101.png",
    12: "13_beitou_hot_spring.png",
    13: "14_chance.png",
    14: "15_jiufen.png",
    15: "16_jail_visit.png",
    16: "17_hsinchu.png",
    17: "18_high_speed_rail.png",
    18: "19_taichung.png",
    19: "20_sun_moon_lake.png",
    20: "21_changhua.png",
    21: "22_license_tax.png",
    22: "23_lukang.png",
    23: "24_nantou.png",
    24: "25_free_rest.png",
    25: "26_anping_fort.png",
    26: "27_tainan.png",
    27: "28_kaohsiung.png",
    28: "29_pier2_art_center.png",
    29: "30_chance.png",
    30: "31_hualien.png",
    31: "32_go_to_jail.png",
}

# 小尺寸正規化後的卡片快取；避免每一回合重解碼 32 張高解析 PNG。
_CARD_CACHE = {}


def _resolve_cjk_font():
    global _CJK_FONT_CACHE
    if _CJK_FONT_CACHE and Path(_CJK_FONT_CACHE).exists():
        return _CJK_FONT_CACHE
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msjh.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            _CJK_FONT_CACHE = candidate
            return candidate
    try:
        import urllib.request
        _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached = _FONT_CACHE_DIR / "NotoSansCJKtc-Regular.otf"
        if not cached.exists() or cached.stat().st_size < 1_000_000:
            urllib.request.urlretrieve(_CJK_FONT_URL, cached)
        _CJK_FONT_CACHE = str(cached)
        return _CJK_FONT_CACHE
    except Exception as exc:
        logging.warning("無法取得繁體中文字型：%s", exc)
        return None


def get_font(size, bold=False):
    cjk = _resolve_cjk_font()
    if cjk:
        try:
            return ImageFont.truetype(cjk, size)
        except Exception:
            pass
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    return ImageFont.load_default()


def fit_text(draw, text, max_width, start_size=30, min_size=12, bold=False):
    for size in range(start_size, min_size - 1, -1):
        f = get_font(size, bold)
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= max_width:
            return f
    return get_font(min_size, bold)


def draw_centered(draw, box, text, font, fill, stroke_width=0, stroke_fill=None):
    x0, y0, x1, y1 = box
    b = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    tw, th = b[2] - b[0], b[3] - b[1]
    tx = x0 + (x1 - x0 - tw) / 2 - b[0]
    ty = y0 + (y1 - y0 - th) / 2 - b[1]
    draw.text((tx, ty), text, font=font, fill=fill,
              stroke_width=stroke_width, stroke_fill=stroke_fill)


def draw_die(draw, box, face=5):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=12, fill=(248, 249, 250), outline=(20, 38, 50), width=3)
    pts = {
        1: [(0.5, 0.5)],
        2: [(0.3, 0.3), (0.7, 0.7)],
        3: [(0.3, 0.3), (0.5, 0.5), (0.7, 0.7)],
        4: [(0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)],
        5: [(0.3, 0.3), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.7, 0.7)],
        6: [(0.3, 0.25), (0.7, 0.25), (0.3, 0.5), (0.7, 0.5), (0.3, 0.75), (0.7, 0.75)],
    }.get(face, [(0.5, 0.5)])
    r = max(4, int((x1 - x0) * 0.065))
    for px, py in pts:
        cx = x0 + (x1 - x0) * px
        cy = y0 + (y1 - y0) * py
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(18, 31, 43))


def tile_coords(index: int):
    """32 格：上 8、右 8、下 8、左 8；每格固定 CARD_W x CARD_H。"""
    if not 0 <= index < 32:
        raise IndexError(index)
    if index < 8:
        col, row = index, 0
    elif index < 16:
        col, row = 7, index - 7       # row 1..8
    elif index < 24:
        col, row = 7 - (index - 16), 9
    else:
        col, row = 0, 8 - (index - 24)  # row 8..1
    x0 = BOARD_X + col * CARD_W
    y0 = BOARD_Y + row * CARD_H
    return x0, y0, x0 + CARD_W, y0 + CARD_H


def _normalized_card(index: int):
    """完整保留原始卡片內容，統一到固定 210x280。

    來源卡片有 2:3 與 3:4 兩種比例。前景永遠採 contain，絕不裁字或價格；
    多出的區域以同圖模糊放大作底，因此不會出現黑色補邊。
    """
    cached = _CARD_CACHE.get(index)
    if cached is not None:
        return cached.copy()

    filename = TILE_ART_FILES.get(index)
    if not filename:
        return None
    path = TILE_ASSET_DIR / filename
    if not path.exists():
        return None

    try:
        src = Image.open(path).convert("RGB")

        # 背景：同一張卡片 cover + 模糊，只用來補比例差造成的空間。
        bg = ImageOps.fit(src, (CARD_W, CARD_H), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=7))

        # 原卡完整等比例縮放，不裁任何內容。
        fg = ImageOps.contain(src, (CARD_W, CARD_H), method=Image.Resampling.LANCZOS)
        ox = (CARD_W - fg.width) // 2
        oy = (CARD_H - fg.height) // 2

        # 圓角遮罩只去掉原圖四角的黑色背景，不動金框、文字、插圖、價格。
        mask = Image.new("L", fg.size, 0)
        md = ImageDraw.Draw(mask)
        radius = max(8, min(fg.size) // 22)
        md.rounded_rectangle((0, 0, fg.width-1, fg.height-1), radius=radius, fill=255)
        bg.paste(fg, (ox, oy), mask)

        # 統一外緣細金線，讓 32 格視覺尺寸完全一致。
        bd = ImageDraw.Draw(bg)
        bd.rounded_rectangle((1, 1, CARD_W-2, CARD_H-2), radius=12,
                             outline=(248, 198, 64), width=3)

        src.close(); fg.close(); mask.close()
        _CARD_CACHE[index] = bg.copy()
        return bg
    except Exception:
        logging.exception("讀取完整格子卡片失敗 index=%s", index)
        return None


def _draw_tile(img, draw, game, index):
    x0, y0, x1, y1 = tile_coords(index)
    card = _normalized_card(index)
    if card is not None:
        img.paste(card, (x0, y0))
        card.close()
    else:
        draw.rounded_rectangle((x0, y0, x1-1, y1-1), radius=12,
                               fill=(238, 232, 208), outline=(248, 198, 64), width=3)
        tile = BOARD[index]
        f = fit_text(draw, tile.get("name", str(index+1)), CARD_W-20, 28, 12, True)
        draw_centered(draw, (x0+10, y0+10, x1-10, y1-10), tile.get("name", ""), f, (12, 40, 72))

    # 擁有者：只加最外圈色框，不蓋住卡片文字。
    owner = get_owner(game, index)
    if owner:
        color = PLAYER_COLORS[game.players.index(owner) % len(PLAYER_COLORS)]
        draw.rounded_rectangle((x0+4, y0+4, x1-5, y1-5), radius=12,
                               outline=color, width=8)

    # 房屋 / 飯店：小徽章放右上，不改原卡內容。
    level = game.property_level.get(index, 0)
    if level and BOARD[index]["kind"] == "property":
        badge = "🏨" if level >= 4 else "🏠" * min(level, 3)
        bf = get_font(24, True)
        bb = draw.textbbox((0, 0), badge, font=bf)
        bw, bh = bb[2]-bb[0]+14, bb[3]-bb[1]+10
        bx1, by0 = x1-8, y0+8
        bx0, by1 = bx1-bw, by0+bh
        draw.rounded_rectangle((bx0, by0, bx1, by1), radius=8, fill=(8, 32, 48))
        draw.text((bx0+7-bb[0], by0+5-bb[1]), badge, font=bf, fill=(255, 240, 192))


def _draw_header(draw, game):
    draw.rounded_rectangle((BOARD_X, 24, W-BOARD_X, 145), radius=28,
                           fill=(10, 44, 72), outline=(82, 145, 178), width=4)
    draw_die(draw, (BOARD_X+20, 43, BOARD_X+82, 105), 5)

    title_box = (BOARD_X+100, 32, BOARD_X+570, 108)
    tf = fit_text(draw, "台灣大富翁", title_box[2]-title_box[0], 58, 32, True)
    draw_centered(draw, title_box, "台灣大富翁", tf, (255, 211, 84), 2, (25, 38, 47))

    mode = "快速模式" if game.mode == "quick" else "經典模式"
    mid = (BOARD_X+600, 44, BOARD_X+1000, 112)
    draw.rounded_rectangle(mid, radius=20, fill=(16, 62, 102), outline=(107, 174, 215), width=2)
    txt = f"第 {game.round_number} 回合｜{mode}"
    mf = fit_text(draw, txt, mid[2]-mid[0]-20, 29, 18, True)
    draw_centered(draw, mid, txt, mf, (247, 248, 250))

    cur = current_player(game)
    ci = game.current_index % len(PLAYER_COLORS)
    right = (BOARD_X+1030, 38, W-BOARD_X-20, 118)
    draw.rounded_rectangle(right, radius=22, fill=(11, 38, 64), outline=(245, 205, 92), width=3)
    c = PLAYER_COLORS[ci]
    draw.ellipse((right[0]+20, 57, right[0]+64, 101), fill=c, outline=(250,250,250), width=2)
    text = f"目前輪到：{cur.name}"
    rf = fit_text(draw, text, right[2]-right[0]-95, 34, 18, True)
    draw_centered(draw, (right[0]+78, 47, right[2]-10, 108), text, rf, (255, 229, 144))


def _draw_center_map(img, draw):
    x0 = BOARD_X + CARD_W + 8
    y0 = BOARD_Y + CARD_H + 8
    x1 = BOARD_X + 7*CARD_W - 8
    y1 = BOARD_Y + 9*CARD_H - 8
    draw.rounded_rectangle((x0, y0, x1, y1), radius=30,
                           fill=(34, 137, 190), outline=(59, 124, 159), width=4)
    path = ASSET_DIR / "taiwan_bg.png"
    if path.exists():
        try:
            bg = Image.open(path).convert("RGB")
            fitted = ImageOps.fit(bg, (x1-x0-10, y1-y0-10), method=Image.Resampling.LANCZOS, centering=(0.5,0.5))
            mask = Image.new("L", fitted.size, 0)
            md = ImageDraw.Draw(mask)
            md.rounded_rectangle((0,0,fitted.width-1,fitted.height-1), radius=26, fill=255)
            img.paste(fitted, (x0+5, y0+5), mask)
            bg.close(); fitted.close(); mask.close()
            return
        except Exception:
            logging.exception("載入中央台灣背景失敗")
    draw.rounded_rectangle((x0+5,y0+5,x1-5,y1-5), radius=26, fill=(80,177,216))


_PAWN_CACHE = {}


def _pawn_sprite(color, width, height, active=False, number=1):
    """帶球形頭部、收腰和橢圓底座的立體桌遊棋子。"""
    key = (tuple(color), width, height, active, number)
    if key in _PAWN_CACHE:
        return _PAWN_CACHE[key]
    scale = 2
    sw, sh = 140 * scale, 190 * scale
    sprite = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(sprite)

    def ellipse(box, **kwargs):
        d.ellipse(tuple(int(v * scale) for v in box), **kwargs)

    # 先完成棋子本體，再統一描邊，避免輪廓融入卡片插畫。

    def shaded_part(mask, kind):
        edge = mask.filter(ImageFilter.MaxFilter(7))
        sprite.paste((255, 247, 222, 255), (0, 0), edge)
        part = Image.new("RGBA", (sw, sh))
        pixels, mp = part.load(), mask.load()
        for y in range(sh):
            for x in range(sw):
                if not mp[x, y]:
                    continue
                xx, yy = x / scale, y / scale
                if kind == "head":
                    nx, ny = (xx - 70) / 28, (yy - 43) / 28
                    nz = max(0, 1 - nx * nx - ny * ny) ** 0.5
                    light = max(0, -0.48 * nx - 0.55 * ny + 0.68 * nz)
                    shade = 0.40 + 0.60 * light
                    shine = 0.48 * max(0, 1 - ((xx-59)/14)**2 - ((yy-30)/12)**2)**2
                else:
                    shade = 0.46 + 0.48 * max(0, 1 - ((xx-56)/62)**2)
                    shine = 0.33 * max(0, 1 - abs(xx-49)/17)**3
                    if kind == "base":
                        shade *= 0.75 + 0.25 * max(0, 1 - (yy-143)/35)
                rgb = tuple(min(255, int(v * shade + (255-v*shade) * shine)) for v in color)
                pixels[x, y] = (*rgb, mp[x, y])
        sprite.alpha_composite(part)
        part.close(); edge.close()

    # 曲線輪廓：細頸向下展開，底部向內收至底座。
    points = []
    def curve(p0, p1, p2, p3):
        for i in range(25):
            t = i / 24; u = 1-t
            points.append((int((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0])*scale),
                           int((u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1])*scale)))
    curve((57, 63), (60, 88), (48, 112), (34, 142))
    curve((34, 142), (32, 156), (108, 156), (106, 142))
    curve((106, 142), (92, 112), (80, 88), (83, 63))
    mask = Image.new("L", (sw, sh), 0)
    md = ImageDraw.Draw(mask); md.polygon(points, fill=255)
    shaded_part(mask, "body"); mask.close()

    # 底座側面和上緣，營造厚度。
    mask = Image.new("L", (sw, sh), 0); md = ImageDraw.Draw(mask)
    md.rounded_rectangle((22*scale, 149*scale, 118*scale, 165*scale), radius=8*scale, fill=255)
    md.ellipse((22*scale, 150*scale, 118*scale, 178*scale), fill=255)
    shaded_part(mask, "base"); mask.close()
    ellipse((23, 139, 117, 165), fill=tuple(int(v*0.85) for v in color)+(255,),
            outline=(255, 239, 201, 255), width=2*scale)
    d.arc((30*scale, 142*scale, 110*scale, 160*scale), 190, 290,
          fill=(255, 255, 255, 150), width=2*scale)

    mask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(mask).ellipse((42*scale, 15*scale, 98*scale, 71*scale), fill=255)
    shaded_part(mask, "head"); mask.close()
    # 外深內白的雙層輪廓；亮、暗與同色背景上都能保持清晰。
    alpha = sprite.getchannel("A")
    white_edge = alpha.filter(ImageFilter.MaxFilter(21))
    dark_edge = alpha.filter(ImageFilter.MaxFilter(29))
    outlined = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    od = ImageDraw.Draw(outlined)
    od.ellipse((8*scale, 157*scale, 132*scale, 189*scale),
               fill=(12, 22, 38, 235), outline=(255, 255, 255, 255), width=3*scale)
    if active:
        od.ellipse((8*scale, 157*scale, 132*scale, 189*scale),
                   fill=(255, 202, 45, 255), outline=(28, 32, 42, 255), width=3*scale)
    outlined.paste((12, 22, 38, 255), (0, 0), dark_edge)
    outlined.paste((255, 255, 255, 255), (0, 0), white_edge)
    outlined.alpha_composite(sprite)
    # 編號與玩家加入順序一致，避免只靠顏色辨識。
    od = ImageDraw.Draw(outlined)
    od.ellipse((48*scale, 103*scale, 92*scale, 147*scale),
               fill=(15, 25, 42, 255), outline=(255, 255, 255, 255), width=2*scale)
    od.text((70*scale, 124*scale), str(number), font=get_font(31*scale, True),
            fill=(255, 255, 255, 255), anchor="mm")
    result = outlined.resize((width, height), Image.Resampling.LANCZOS)
    outlined.close(); alpha.close(); white_edge.close(); dark_edge.close()
    sprite.close()
    _PAWN_CACHE[key] = result
    return result


def _draw_pawns(img, draw, game):
    occupied = {}
    for pi, player in enumerate(game.players):
        if not player.bankrupt:
            occupied.setdefault(player.position, []).append(pi)

    for pos, ids in occupied.items():
        x0, y0, x1, y1 = tile_coords(pos)
        count = len(ids)
        columns = 1 if count == 1 else (2 if count <= 4 else (3 if count <= 6 else 4))
        rows = (count + columns - 1) // columns
        width, height = (140, 190) if count == 1 else ((94, 128) if count == 2 else ((65, 88) if count <= 4 else ((58, 79) if count <= 6 else (46, 63))))
        gap = 4
        block_h = rows * height + (rows - 1) * gap
        top = y0 + (CARD_H - block_h) // 2
        for n, pi in enumerate(ids):
            row, col = divmod(n, columns)
            row_count = min(columns, count - row * columns)
            row_w = row_count * width + (row_count - 1) * gap
            x = x0 + (CARD_W - row_w) // 2 + col * (width + gap)
            y = top + row * (height + gap)
            pawn = _pawn_sprite(PLAYER_COLORS[pi % len(PLAYER_COLORS)], width, height,
                                active=pi == game.current_index, number=pi + 1)
            img.paste(pawn, (x, y), pawn)


def generate_board_image(game: Game) -> io.BytesIO:
    img = Image.new("RGB", (W, H), (7, 24, 39))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((12, 12, W-12, H-12), radius=38,
                           fill=(8,29,46), outline=(57,111,140), width=5)
    _draw_header(draw, game)
    _draw_center_map(img, draw)
    for i in range(len(BOARD)):
        _draw_tile(img, draw, game, i)
    _draw_pawns(img, draw, game)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    out.seek(0)
    img.close()
    return out


def generate_group_board_images(game: Game):
    """切成 TG 上下兩張；切線精準落在第 5/6 列之間，不切卡片。"""
    full_buf = generate_board_image(game)
    full_buf.seek(0)
    with Image.open(full_buf) as full:
        full = full.convert("RGB")
        # row 0..4 在上半，row 5..9 在下半；任何格子都不會被切開。
        split = BOARD_Y + 5 * CARD_H
        top = full.crop((0, 0, W, split))
        bottom = full.crop((0, split, W, H))
        a, b = io.BytesIO(), io.BytesIO()
        top.save(a, format="PNG", optimize=True)
        bottom.save(b, format="PNG", optimize=True)
        a.seek(0); b.seek(0)
        top.close(); bottom.close()
    full_buf.close()
    return a, b
