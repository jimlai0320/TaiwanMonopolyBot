# -*- coding: utf-8 -*-
"""48 格台灣大富翁地圖與事件資料。"""

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

