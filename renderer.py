# -*- coding: utf-8 -*-
"""32 格台灣大富翁棋盤渲染器。

設計原則：
- 32 格全部完全相同尺寸。
- 8 格上方 + 8 格右側 + 8 格下方 + 8 格左側。
- 實際幾何是 8 欄 x 10 列外框，因此四邊可以各放 8 格且不重複。
- 中央使用 assets/taiwan_bg.png。
- assets/tiles/ 若有對應格子素材，會裁出插圖區使用；沒有素材則用程式簡圖。
"""
import io
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from board_data import BOARD, PLAYER_COLORS
from models import Game
from helpers import current_player, get_owner

ASSET_DIR = Path(__file__).resolve().parent / "assets"
TILE_ASSET_DIR = ASSET_DIR / "tiles"

_FONT_CACHE_DIR = Path("/tmp/taiwan_monopoly_fonts")
_CJK_FONT_URL = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
_CJK_FONT_CACHE = None

# ===== 畫布規格：所有格子完全相同 =====
W = 1200
CELL = 135
GRID_COLS = 8
GRID_ROWS = 10
BOARD_X = (W - GRID_COLS * CELL) // 2   # 60
BOARD_Y = 165
BOARD_W = GRID_COLS * CELL              # 1080
BOARD_H = GRID_ROWS * CELL              # 1350
H = BOARD_Y + BOARD_H + 24               # 1539

# 第一批正式素材；之後新增素材只需要延伸這個 mapping。
TILE_ART_FILES = {
    0: "01_start.png",
    1: "02_keelung.png",
    2: "03_tamsui.png",
    3: "04_chance.png",
    4: "05_bali.png",
    5: "06_taipei_station.png",
    6: "07_ximending.png",
    7: "08_income_tax.png",
    8: "09_cksmh.png",
    9: "10_songshan_airport.png",
}


def _resolve_cjk_font():
    global _CJK_FONT_CACHE
    if _CJK_FONT_CACHE and Path(_CJK_FONT_CACHE).exists():
        return _CJK_FONT_CACHE
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


def fit_text(draw, text, max_width, start_size=26, min_size=10, bold=False):
    for size in range(start_size, min_size - 1, -1):
        font = get_font(size, bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
    return get_font(min_size, bold)


def draw_centered(draw, box, text, font, fill, stroke_width=0, stroke_fill=None):
    x0, y0, x1, y1 = box
    tb = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    tx = x0 + (x1 - x0 - tw) / 2 - tb[0]
    ty = y0 + (y1 - y0 - th) / 2 - tb[1]
    draw.text((tx, ty), text, font=font, fill=fill,
              stroke_width=stroke_width, stroke_fill=stroke_fill)


def draw_die(draw, box, face=5):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=10, fill=(248, 249, 250), outline=(20, 38, 50), width=2)
    pts = {
        1: [(0.5, 0.5)],
        2: [(0.3, 0.3), (0.7, 0.7)],
        3: [(0.3, 0.3), (0.5, 0.5), (0.7, 0.7)],
        4: [(0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)],
        5: [(0.3, 0.3), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.7, 0.7)],
        6: [(0.3, 0.25), (0.7, 0.25), (0.3, 0.5), (0.7, 0.5), (0.3, 0.75), (0.7, 0.75)],
    }.get(face, [(0.5, 0.5)])
    r = max(3, int((x1 - x0) * 0.065))
    for px, py in pts:
        cx = x0 + (x1 - x0) * px
        cy = y0 + (y1 - y0) * py
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(18, 31, 43))


def tile_coords(index: int):
    """32 格：上 8、右 8、下 8、左 8；全部 135x135。"""
    if not 0 <= index < 32:
        raise IndexError(index)
    # 1～8：最上方 8 格
    if index < 8:
        col, row = index, 0
    # 9～16：右側，由上往下（不重複右上角）
    elif index < 16:
        col, row = 7, index - 7  # row 1..8
    # 17～24：底部，由右往左（含右下與左下）
    elif index < 24:
        col, row = 7 - (index - 16), 9
    # 25～32：左側，由下往上（不重複左下與左上）
    else:
        col, row = 0, 8 - (index - 24)  # row 8..1
    x0 = BOARD_X + col * CELL
    y0 = BOARD_Y + row * CELL
    return x0, y0, x0 + CELL, y0 + CELL


def _load_tile_art(index, size):
    filename = TILE_ART_FILES.get(index)
    if not filename:
        return None
    path = TILE_ASSET_DIR / filename
    if not path.exists():
        return None
    try:
        im = Image.open(path).convert("RGB")
        w, h = im.size
        # 正式卡片本身含大標題和大價格；棋盤只取中央插畫區。
        crop = im.crop((int(w * 0.05), int(h * 0.20), int(w * 0.95), int(h * 0.81)))
        result = ImageOps.fit(crop, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        im.close()
        return result
    except Exception:
        logging.exception("讀取格子素材失敗 index=%s", index)
        return None


def _draw_fallback_art(draw, box, tile, index):
    x0, y0, x1, y1 = box
    kind = tile["kind"]
    # 簡潔景點底圖，不再使用綠色三角形佔位。
    if kind == "chance":
        draw.rounded_rectangle(box, radius=8, fill=(255, 218, 112), outline=(233, 178, 54), width=1)
        draw_centered(draw, box, "?", get_font(52, True), (196, 61, 42), 1, (255, 241, 184))
        return
    if kind == "tax":
        draw.rounded_rectangle(box, radius=8, fill=(255, 201, 171), outline=(228, 142, 106), width=1)
        draw_centered(draw, (x0, y0, x1, (y0+y1)//2), "TAX", get_font(23, True), (102, 47, 36))
        draw_centered(draw, ((x0), (y0+y1)//2, x1, y1), "$$", get_font(25, True), (170, 68, 38))
        return
    if kind in ("jail", "gotojail"):
        draw.rounded_rectangle(box, radius=8, fill=(211, 222, 238), outline=(122, 143, 170), width=1)
        # 監獄鐵欄
        for n in range(4):
            xx = x0 + 18 + n * ((x1-x0-36)//3)
            draw.rectangle((xx, y0+12, xx+6, y1-12), fill=(48, 62, 80))
        return
    if kind == "free":
        draw.rounded_rectangle(box, radius=8, fill=(194, 236, 203), outline=(119, 183, 133), width=1)
        # 小涼亭
        mid=(x0+x1)//2
        draw.polygon([(mid, y0+9),(x0+12,y0+30),(x1-12,y0+30)],fill=(176,80,49))
        draw.rectangle((x0+22,y0+30,x1-22,y1-12),fill=(236,210,155))
        return
    if kind == "transport":
        draw.rounded_rectangle(box, radius=8, fill=(199, 229, 247), outline=(127, 181, 211), width=1)
        # 車/飛機抽象線條
        draw.rounded_rectangle((x0+13,y0+26,x1-13,y1-20), radius=14, fill=(244,248,250), outline=(67,118,150), width=2)
        draw.line((x0+20,(y0+y1)//2,x1-20,(y0+y1)//2), fill=(60,132,178), width=5)
        return
    if kind == "start":
        draw.rounded_rectangle(box, radius=8, fill=(204, 241, 205), outline=(117, 181, 121), width=1)
        draw.polygon([(x0+17,(y0+y1)//2),(x1-22,y0+14),(x1-22,y0+35),(x1-7,y0+35),(x1-7,y1-16),(x1-22,y1-16),(x1-22,y1-2)],fill=(37,155,63))
        return

    # 一般地產：依地區名稱畫不同的簡化景物。
    draw.rounded_rectangle(box, radius=8, fill=(196, 227, 246), outline=(139, 188, 216), width=1)
    name = tile["name"]
    if any(k in name for k in ("港", "淡水", "花蓮", "日月潭", "九份")):
        draw.rectangle((x0, (y0+y1)//2, x1, y1), fill=(92, 184, 222))
        draw.polygon([(x0+12,(y0+y1)//2),(x0+42,y0+14),(x0+68,(y0+y1)//2)], fill=(79,159,99))
        draw.polygon([(x1-74,(y0+y1)//2),(x1-42,y0+20),(x1-12,(y0+y1)//2)], fill=(95,174,105))
    elif "101" in name:
        mid=(x0+x1)//2
        draw.rectangle((mid-11,y0+10,mid+11,y1-8),fill=(49,151,181))
        for yy in range(y0+20,y1-12,13):
            draw.rectangle((mid-17,yy,mid+17,yy+5),fill=(70,174,197))
    elif any(k in name for k in ("夜市", "西門", "鹿港")):
        for n in range(3):
            xx=x0+8+n*36
            draw.rectangle((xx,y0+25,xx+30,y1-8),fill=((214,83+20*n,66)))
            draw.polygon([(xx-2,y0+25),(xx+15,y0+10),(xx+32,y0+25)],fill=(244,193,75))
    elif "溫泉" in name:
        draw.rectangle((x0,y0,x1,y1),fill=(188,226,217))
        for n in range(3):
            draw.arc((x0+15+n*26,y0+12,x0+44+n*26,y0+53),180,355,fill=(255,255,255),width=4)
        draw.ellipse((x0+12,y0+43,x1-12,y1-9),fill=(95,190,192))
    else:
        # 城市 / 古蹟
        draw.rectangle((x0+16,y0+33,x1-16,y1-8),fill=(230,199,153),outline=(143,106,77),width=2)
        draw.polygon([(x0+10,y0+35),((x0+x1)//2),y0+9,(x1-10,y0+35)],fill=(190,66,50))
        for xx in (x0+28,(x0+x1)//2,x1-28):
            draw.rectangle((xx-5,y0+48,xx+5,y1-15),fill=(87,123,144))


def _draw_tile(img, draw, game, index):
    tile = BOARD[index]
    x0, y0, x1, y1 = tile_coords(index)
    kind = tile["kind"]
    type_colors = {
        "start": (213, 244, 211),
        "property": (246, 243, 225),
        "chance": (255, 222, 125),
        "tax": (255, 192, 166),
        "transport": (203, 231, 248),
        "jail": (211, 222, 238),
        "gotojail": (255, 187, 170),
        "free": (195, 237, 204),
    }
    fill = type_colors.get(kind, (242, 242, 238))
    owner = get_owner(game, index)
    owner_color = None
    if owner:
        owner_color = PLAYER_COLORS[game.players.index(owner) % len(PLAYER_COLORS)]
        fill = tuple(int(fill[k] * 0.80 + owner_color[k] * 0.20) for k in range(3))

    # 卡片陰影與本體
    draw.rounded_rectangle((x0+4,y0+5,x1-2,y1-1), radius=13, fill=(5,19,28))
    draw.rounded_rectangle((x0+2,y0+2,x1-4,y1-4), radius=13, fill=fill, outline=(19,53,69), width=3)

    # 編號圓章：完全在格內
    badge_r=15
    cx=x0+21; cy=y0+20
    draw.ellipse((cx-badge_r,cy-badge_r,cx+badge_r,cy+badge_r), fill=(22,92,128), outline=(245,245,245), width=2)
    nf=fit_text(draw,str(index+1),24,16,10,True)
    draw_centered(draw,(cx-badge_r,cy-badge_r,cx+badge_r,cy+badge_r),str(index+1),nf,(255,255,255))

    # 地名：固定高度、真正置中
    name_box=(x0+38,y0+7,x1-8,y0+39)
    name_font=fit_text(draw,tile["name"],name_box[2]-name_box[0],24,12,True)
    draw_centered(draw,name_box,tile["name"],name_font,(17,39,48))

    # 插圖區
    art_box=(x0+8,y0+42,x1-8,y1-30)
    art_size=(art_box[2]-art_box[0],art_box[3]-art_box[1])
    art=_load_tile_art(index, art_size)
    if art is not None:
        mask=Image.new("L",art_size,0)
        md=ImageDraw.Draw(mask)
        md.rounded_rectangle((0,0,art_size[0]-1,art_size[1]-1),radius=8,fill=255)
        img.paste(art,(art_box[0],art_box[1]),mask)
        art.close(); mask.close()
    else:
        _draw_fallback_art(draw,art_box,tile,index)

    # 價格 / 效果列
    footer=(x0+6,y1-29,x1-7,y1-6)
    if kind == "property":
        text=f"${tile['price']}"
        fill_text=(20,42,50)
    elif kind == "tax":
        text=f"-${tile['amount']}"
        fill_text=(165,52,35)
    elif kind == "transport":
        text="交通"
        fill_text=(33,83,109)
    elif kind == "chance":
        text="機會"
        fill_text=(165,72,26)
    elif kind == "start":
        text="GO"
        fill_text=(30,121,52)
    elif kind == "jail":
        text="監獄／探監"
        fill_text=(47,58,79)
    elif kind == "gotojail":
        text="前往監獄"
        fill_text=(133,49,40)
    elif kind == "free":
        text="休息一回合"
        fill_text=(37,96,57)
    else:
        text=""
        fill_text=(20,42,50)
    ff=fit_text(draw,text,footer[2]-footer[0],21,11,True)
    draw_centered(draw,footer,text,ff,fill_text)

    # 擁有者色條
    if owner_color:
        draw.rounded_rectangle((x0+6,y1-7,x1-8,y1-3),radius=2,fill=owner_color)

    # 房屋 / 飯店
    level=game.property_level.get(index,0)
    if level and kind=="property":
        label="H" if level==4 else "★"*level
        lf=fit_text(draw,label,42,15,9,True)
        lb=draw.textbbox((0,0),label,font=lf)
        draw.text((x1-9-(lb[2]-lb[0]),y0+41-lb[1]),label,font=lf,fill=(166,78,18))


def _draw_header(draw, game):
    # 外框
    draw.rounded_rectangle((28,22,W-28,140),radius=28,fill=(10,44,72),outline=(82,145,178),width=3)

    # 左：骰子 + 標題
    draw_die(draw,(48,42,108,102),5)
    title_box=(122,31,485,105)
    tf=fit_text(draw,"台灣大富翁",title_box[2]-title_box[0],55,30,True)
    draw_centered(draw,title_box,"台灣大富翁",tf,(255,211,84),2,(25,38,47))

    # 中：回合 / 模式
    mode="快速模式" if game.mode=="quick" else "經典模式"
    mid=(500,45,765,112)
    draw.rounded_rectangle(mid,radius=20,fill=(16,62,102),outline=(107,174,215),width=2)
    txt=f"第 {game.round_number} 回合｜{mode}"
    mf=fit_text(draw,txt,mid[2]-mid[0]-18,25,16,True)
    draw_centered(draw,mid,txt,mf,(247,248,250))

    # 右：目前輪到
    cur=current_player(game)
    ci=game.current_index % len(PLAYER_COLORS)
    right=(785,38,1150,118)
    draw.rounded_rectangle(right,radius=22,fill=(11,38,64),outline=(245,205,92),width=3)
    c=PLAYER_COLORS[ci]
    draw.ellipse((804,57,848,101),fill=c,outline=(250,250,250),width=2)
    text=f"目前輪到：{cur.name}"
    rf=fit_text(draw,text,275,32,18,True)
    draw_centered(draw,(860,47,1135,108),text,rf,(255,229,144))


def _draw_center_map(img, draw):
    # 中央區 = 6 欄 x 8 列，剛好被統一格子包住。
    x0=BOARD_X+CELL+8
    y0=BOARD_Y+CELL+8
    x1=BOARD_X+7*CELL-8
    y1=BOARD_Y+9*CELL-8
    draw.rounded_rectangle((x0,y0,x1,y1),radius=26,fill=(34,137,190),outline=(59,124,159),width=3)
    path=ASSET_DIR/"taiwan_bg.png"
    if path.exists():
        try:
            bg=Image.open(path).convert("RGB")
            fitted=ImageOps.fit(bg,(x1-x0-10,y1-y0-10),method=Image.Resampling.LANCZOS,centering=(0.5,0.5))
            mask=Image.new("L",fitted.size,0)
            md=ImageDraw.Draw(mask)
            md.rounded_rectangle((0,0,fitted.size[0]-1,fitted.size[1]-1),radius=22,fill=255)
            img.paste(fitted,(x0+5,y0+5),mask)
            bg.close(); fitted.close(); mask.close()
            return
        except Exception:
            logging.exception("載入中央台灣背景失敗")
    # fallback
    draw.rounded_rectangle((x0+5,y0+5,x1-5,y1-5),radius=22,fill=(80,177,216))


def _draw_pawns(draw, game):
    occupied={}
    for pi,p in enumerate(game.players):
        if not p.bankrupt:
            occupied.setdefault(p.position,[]).append(pi)
    for pos, ids in occupied.items():
        x0,y0,x1,y1=tile_coords(pos)
        for n,pi in enumerate(ids):
            c=PLAYER_COLORS[pi % len(PLAYER_COLORS)]
            px=x1-18-(n%2)*28
            py=y0+52+(n//2)*30
            draw.ellipse((px-10,py-10,px+10,py+10),fill=c,outline=(255,255,255),width=2)
            draw.polygon([(px,py+7),(px-12,py+27),(px+12,py+27)],fill=c,outline=(13,29,38))


def generate_board_image(game: Game) -> io.BytesIO:
    img=Image.new("RGB",(W,H),(7,24,39))
    draw=ImageDraw.Draw(img)
    draw.rounded_rectangle((10,10,W-10,H-10),radius=34,fill=(8,29,46),outline=(57,111,140),width=4)
    _draw_header(draw,game)
    _draw_center_map(img,draw)
    for i in range(len(BOARD)):
        _draw_tile(img,draw,game,i)
    _draw_pawns(draw,game)

    out=io.BytesIO()
    img.save(out,format="PNG",optimize=True)
    out.seek(0)
    img.close()
    return out


def generate_group_board_images(game: Game):
    """保留相容接口：把完整棋盤精準切成上下兩張，不切格子。

    32 格版因為總高度已縮短，UI 預設使用單張完整棋盤；此函式留給未來需要雙圖時使用。
    """
    full_buf=generate_board_image(game)
    full_buf.seek(0)
    with Image.open(full_buf) as full:
        full=full.convert("RGB")
        # 在第 5 / 6 列之間切，剛好是格線，不會切到格子。
        split=BOARD_Y+5*CELL
        top=full.crop((0,0,W,split))
        bottom=full.crop((0,split,W,H))
        a=io.BytesIO(); b=io.BytesIO()
        top.save(a,format="PNG",optimize=True); bottom.save(b,format="PNG",optimize=True)
        a.seek(0); b.seek(0)
        top.close(); bottom.close()
    full_buf.close()
    return a,b
