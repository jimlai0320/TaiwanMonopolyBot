# -*- coding: utf-8 -*-
"""地區實景照片：Wikimedia Commons，保留作者、來源及授權。

照片由 Telegram 讀取 960px 線上縮圖，首次成功後使用 Telegram file_id。
不是 AI 生成圖片；來源圖未裁切，Commons 縮圖僅等比例縮放。
可在 assets/places/ 放置 02.jpg（第2格）等同來源照片作本機備援。
"""
import hashlib
import html
from pathlib import Path
from urllib.parse import quote

# BOARD 的 0-based 格子編號: (Commons 檔名, 作者, 授權, 實際拍攝景點)
PHOTOS = {
    1: ('Panorama view of central Keelung and the harbor.png', 'Harrison Kuo', 'CC BY-SA 4.0', '基隆港全景'),
    2: ('Sunset of Tamsui 1.jpg', 'Minghong', 'CC BY-SA 3.0', '淡水河畔夕陽'),
    4: ('2021 Bali Left Bank Bikeway in Bali District, New Taipei TAIWAN.jpg', 'Taiwankengo', 'CC BY-SA 4.0', '八里左岸'),
    5: ('TaipeiMainStation.jpg', 'Peellden', 'CC BY-SA 3.0', '台北車站'),
    6: ('Ximending banner.jpg', 'Edson Hiroshi Aoki', 'CC BY-SA 4.0', '西門町夜景'),
    8: ('Chiang Kai-shek memorial hall.jpg', 'Shubham2712', 'CC BY-SA 4.0', '中正紀念堂'),
    9: ('Taipei Songshan Airport from Old Place Airplane Observation Deck April 2026 2.jpg', '4300streetcar', 'CC BY 4.0', '松山機場'),
    10: ('Raohe Street Night Market 饒河街觀光夜市西口 20100328.jpg', 'ktanaka', 'CC BY 3.0', '饒河街夜市西口'),
    11: ('Taipei 101 April 2026 1.jpg', '4300streetcar', 'CC BY 4.0', '台北101'),
    12: ('Thermal Valley in Beitou.jpg', 'GiveMeMollusks', 'CC0 1.0', '北投地熱谷'),
    14: ('Jiufen, November 28, 2024 - 033 (cropped).jpg', 'Another Believer', 'CC BY-SA 4.0', '九份老街'),
    16: ('Hsinchu City East Gate.jpg', 'Foxy1219', 'CC BY-SA 3.0', '新竹迎曦門'),
    17: ('Taiwan High Speed Rail train 619 at Taipei Main Station March 2026.jpg', '4300streetcar', 'CC BY 4.0', '台灣高鐵列車'),
    18: ('2017-10-29 National Taichung Theater.jpg', 'Xiquinho Silva', 'CC BY 2.0', '台中國家歌劇院'),
    19: ('Sun Moon Lake, Taiwan.jpg', 'Photnart', 'CC BY-SA 4.0', '日月潭'),
    20: ('Changhua buddha.png', 'Bpp88520', 'CC0 1.0', '彰化八卦山大佛'),
    22: ('鹿港老街 三槐挺秀宅 Lukang Old Street - panoramio.jpg', 'Foxy Who \\(^∀^)/', 'CC BY-SA 3.0', '鹿港老街'),
    23: ('南投 藍田書院.jpg', 'TS Lai', 'CC BY-SA 4.0', '南投藍田書院'),
    25: ('Fort Zeelandia, Anping District, Tainan City (Taiwan).jpg', 'Malcolm Koo', 'CC BY 4.0', '安平古堡'),
    26: ('Fort Provintia (Chihkan Tower) (赤崁樓), Wenchang Pavilion, Tainan City (Taiwan).jpg', 'Malcolm Koo', 'CC BY 4.0', '台南赤崁樓文昌閣'),
    27: ('The skyline of Kaohsiung City.jpg', 'Surmoer', 'CC BY-SA 3.0', '高雄市天際線'),
    28: ('The Pier-2 Art Center 2020070901.jpg', 'ABOVE THE SKY', 'CC BY-SA 4.0', '駁二藝術特區'),
    30: ('QIXINGTAN beach taiwan.jpg', 'Mamtapawar512', 'CC BY-SA 4.0', '花蓮七星潭'),
}
LICENSE_URLS = {
    'CC BY-SA 4.0': 'https://creativecommons.org/licenses/by-sa/4.0/',
    'CC BY-SA 3.0': 'https://creativecommons.org/licenses/by-sa/3.0/',
    'CC BY 4.0': 'https://creativecommons.org/licenses/by/4.0/',
    'CC BY 3.0': 'https://creativecommons.org/licenses/by/3.0/',
    'CC BY 2.0': 'https://creativecommons.org/licenses/by/2.0/',
    'CC0 1.0': 'https://creativecommons.org/publicdomain/zero/1.0/',
}

def photo_source(index):
    local = Path(__file__).resolve().parent / 'assets' / 'places' / f'{index+1:02d}.jpg'
    if local.is_file():
        return local
    filename = PHOTOS[index][0].replace(' ', '_')
    digest = hashlib.md5(filename.encode('utf-8')).hexdigest()
    encoded = quote(filename, safe='')
    return f'https://upload.wikimedia.org/wikipedia/commons/thumb/{digest[0]}/{digest[:2]}/{encoded}/960px-{encoded}'


def photo_credit(index):
    filename, author, license_name, landmark = PHOTOS[index]
    source = 'https://commons.wikimedia.org/wiki/File:' + quote(filename.replace(' ', '_'), safe='')
    return (f'📷 {html.escape(landmark)}｜{html.escape(author)}\n'
            f'<a href="{source}">照片來源</a> · '
            f'<a href="{LICENSE_URLS[license_name]}">{license_name}</a>')
