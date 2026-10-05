# 台灣大富翁 Telegram Bot（多檔案版）

## 檔案結構

- `main.py`：啟動 Bot
- `config.py`：遊戲參數
- `board_data.py`：48 格地圖與機會事件
- `models.py`：Player / Game
- `helpers.py`：租金、資產、移動等共用計算
- `game_logic.py`：回合、買地、租金、監獄、破產、AI
- `renderer.py`：棋盤圖片；要改美術主要改這裡
- `ui.py`：Telegram 群組與私訊 UI
- `handlers.py`：指令與按鈕處理
- `health.py`：Render health check
- `assets/taiwan_bg.png`：中央台灣背景圖

## Render

Build Command:
```bash
pip install -r requirements.txt
```

Start Command:
```bash
python main.py
```

Environment Variable:
```text
BOT_TOKEN=你的 Telegram Bot Token
```

## 修改 UI

目前主棋盤採 **直式長圖、48 格繞一圈、8/16/8/16**。
想換背景或外觀，優先修改 `renderer.py` 與 `assets/taiwan_bg.png`，不需要碰遊戲規則。


## Telegram 顯示優化
群組棋盤會先生成完整直式環島版，再自動依格線位置裁成上下兩張連續圖片；兩張之間會保留少量重疊，避免裁到格子。
這不是把地圖拆成兩套規則，而是同一張完整棋盤的兩個視窗，目的是避免 Telegram 把超長照片縮得太小。
私訊只顯示文字與操作按鈕，降低記憶體與上傳流量。
