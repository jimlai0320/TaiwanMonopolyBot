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

## 32 格完整卡片素材版（最新）
- 棋盤固定 32 格，上 8 / 右 8 / 下 8 / 左 8。
- 每格使用 `assets/tiles/` 內的完整生成卡片，不再由 Pillow 重畫地名、編號與價格。
- 32 格尺寸固定一致：210 × 280 px。
- 來源卡片比例不同時，完整卡片會等比例保留；多出的空間用同卡片模糊延伸補滿，避免黑邊。
- 群組棋盤會切成上下兩張 Telegram 圖，切線在格線上，不會切到任何卡片。
- 玩家棋子、擁有者色框與房屋/飯店資訊會以疊加方式顯示，不修改原卡片素材。
