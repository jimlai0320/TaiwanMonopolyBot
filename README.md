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
