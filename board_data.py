# -*- coding: utf-8 -*-
"""32 格台灣大富翁地圖與事件資料。

正式 32 格版本配置：
- 上方：1～8
- 右側：9～16
- 下方：17～24
- 左側：25～32
- 16 = 監獄／探監
- 32 = 前往監獄
"""

BOARD = [
    # ===== 上方 1～8 =====
    {"name": "出發",       "kind": "start"},
    {"name": "基隆港",     "kind": "property",  "price": 120, "rent": 24, "group": "北海岸"},
    {"name": "淡水",       "kind": "property",  "price": 140, "rent": 28, "group": "北海岸"},
    {"name": "機會",       "kind": "chance"},
    {"name": "八里",       "kind": "property",  "price": 160, "rent": 32, "group": "北海岸"},
    {"name": "台北車站",   "kind": "transport"},
    {"name": "西門町",     "kind": "property",  "price": 220, "rent": 45, "group": "台北核心"},
    {"name": "所得稅",     "kind": "tax",       "amount": 120},

    # ===== 右側 9～16 =====
    {"name": "中正紀念堂", "kind": "property",  "price": 240, "rent": 50, "group": "台北核心"},
    {"name": "松山機場",   "kind": "transport"},
    {"name": "饒河夜市",   "kind": "property",  "price": 240, "rent": 50, "group": "台北東區"},
    {"name": "台北101",    "kind": "property",  "price": 280, "rent": 60, "group": "台北東區"},
    {"name": "北投溫泉",   "kind": "property",  "price": 260, "rent": 55, "group": "北台灣"},
    {"name": "機會",       "kind": "chance"},
    {"name": "九份",       "kind": "property",  "price": 260, "rent": 55, "group": "北台灣"},
    {"name": "監獄／探監", "kind": "jail"},

    # ===== 下方 17～24 =====
    {"name": "新竹",       "kind": "property",  "price": 280, "rent": 60, "group": "中台灣"},
    {"name": "高鐵",       "kind": "transport"},
    {"name": "台中",       "kind": "property",  "price": 320, "rent": 70, "group": "中台灣"},
    {"name": "日月潭",     "kind": "property",  "price": 320, "rent": 70, "group": "中台灣"},
    {"name": "彰化",       "kind": "property",  "price": 300, "rent": 65, "group": "中台灣"},
    {"name": "牌照稅",     "kind": "tax",       "amount": 100},
    {"name": "鹿港",       "kind": "property",  "price": 300, "rent": 65, "group": "中台灣"},
    {"name": "南投",       "kind": "property",  "price": 280, "rent": 60, "group": "中台灣"},

    # ===== 左側 25～32 =====
    {"name": "免費休息",   "kind": "free"},
    {"name": "安平古堡",   "kind": "property",  "price": 320, "rent": 70, "group": "南台灣"},
    {"name": "台南",       "kind": "property",  "price": 340, "rent": 75, "group": "南台灣"},
    {"name": "高雄",       "kind": "property",  "price": 360, "rent": 80, "group": "南台灣"},
    {"name": "駁二特區",   "kind": "property",  "price": 340, "rent": 75, "group": "南台灣"},
    {"name": "機會",       "kind": "chance"},
    {"name": "花蓮",       "kind": "property",  "price": 340, "rent": 75, "group": "東台灣"},
    {"name": "前往監獄",   "kind": "gotojail"},
]

assert len(BOARD) == 32

# BOARD 使用 0-based index；第 16 格「監獄／探監」= index 15。
JAIL_INDEX = 15

# 玩家擁有 1 / 2 / 3 個交通格時的租金。
# helpers.py 目前會以 transport_count 作為索引。
TRANSPORT_RENTS = [0, 30, 60, 120, 200]

PLAYER_COLORS = [
    (235, 67, 53),   # 紅
    (62, 126, 236),  # 藍
    (247, 196, 49),  # 黃
    (46, 184, 92),   # 綠
    (158, 74, 219),  # 紫
    (242, 130, 48),  # 橘
    (236, 92, 150),  # 粉
    (65, 206, 206),  # 青
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
