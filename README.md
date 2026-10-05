# 台灣大富翁 Telegram Bot — 32 格版

目前整合版本：

- 32 格正式地圖
- 所有格子固定同尺寸
- 單張 Telegram 棋盤圖
- 中央卡通精緻台灣背景
- 第一批 10 格使用正式生成素材
- 其餘格子由 renderer 暫時繪製，之後可逐批替換成正式素材
- 2～8 人
- 快速模式 / 經典模式
- 群組顯示棋盤，私訊操作

## Render

Build Command:
```bash
pip install -r requirements.txt
```

Start Command:
```bash
python main.py
```

環境變數：
- `BOT_TOKEN`

## 主要檔案
- `board_data.py`：32 格地圖資料
- `renderer.py`：統一格子棋盤 UI
- `game_logic.py`：遊戲邏輯
- `ui.py`：Telegram 群組 / 私訊 UI
- `handlers.py`：指令與按鈕事件
- `assets/taiwan_bg.png`：中央背景
- `assets/tiles/`：格子素材
