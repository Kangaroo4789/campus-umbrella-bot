# 建立 LINE Bot Rich Menu（底部快捷選單）

import os
import requests
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv(".env")
TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

W, H     = 2500, 1686
COLS     = 3
CELL_W   = W // COLS
CELL_H   = H // 2

BUTTONS = [
    ("借  傘", "借傘"),
    ("還  傘", "還傘"),
    ("雨傘地圖", "地圖"),
    ("我的狀態", "狀態"),
    ("報  修", "報修"),
    ("任務看板", "任務"),
]

FONT_PATHS = [
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/kaiu.ttf",
    "C:/Windows/Fonts/mingliu.ttc",
]

def get_font(size):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def build_image():
    img  = Image.new("RGB", (W, H), color=(26, 60, 94))
    draw = ImageDraw.Draw(img)
    font = get_font(160)

    for i, (label, _) in enumerate(BUTTONS):
        row, col = divmod(i, COLS)
        x = col * CELL_W
        y = row * CELL_H

        # 交替底色讓按鈕區別更明顯
        bg = (20, 50, 80) if (row + col) % 2 == 0 else (30, 70, 110)
        draw.rectangle([x, y, x + CELL_W, y + CELL_H], fill=bg)
        draw.rectangle([x + 8, y + 8, x + CELL_W - 8, y + CELL_H - 8],
                       outline=(255, 255, 255), width=4)

        bbox = draw.textbbox((0, 0), label, font=font)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        draw.text(
            (x + (CELL_W - tw) // 2, y + (CELL_H - th) // 2),
            label, fill=(255, 255, 255), font=font
        )

    path = "richmenu_bg.png"
    img.save(path)
    print(f"✅ 選單圖片已建立：{path}")
    return path

def create_richmenu():
    headers_json = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    headers_img  = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "image/png"}

    # 刪除現有預設選單
    resp = requests.get("https://api.line.me/v2/bot/user/all/richmenu", headers=headers_json)
    if resp.status_code == 200:
        old_id = resp.json().get("richMenuId")
        if old_id:
            requests.delete(f"https://api.line.me/v2/bot/richmenu/{old_id}", headers=headers_json)
            print(f"🗑 已刪除舊選單：{old_id}")

    # 建立新選單
    areas = []
    for i, (_, text) in enumerate(BUTTONS):
        row, col = divmod(i, COLS)
        areas.append({
            "bounds": {"x": col * CELL_W, "y": row * CELL_H,
                       "width": CELL_W, "height": CELL_H},
            "action": {"type": "message", "text": text}
        })

    resp = requests.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=headers_json,
        json={
            "size": {"width": W, "height": H},
            "selected": True,
            "name": "Campus Umbrella Menu",
            "chatBarText": "選單",
            "areas": areas
        }
    )
    if resp.status_code != 200:
        print(f"❌ 建立失敗：{resp.status_code} {resp.text}")
        return
    richmenu_id = resp.json()["richMenuId"]
    print(f"✅ 選單已建立：{richmenu_id}")

    # 上傳背景圖
    img_path = build_image()
    with open(img_path, "rb") as f:
        resp = requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{richmenu_id}/content",
            headers=headers_img,
            data=f.read()
        )
    if resp.status_code != 200:
        print(f"❌ 圖片上傳失敗：{resp.status_code} {resp.text}")
        return
    print("✅ 背景圖已上傳")

    # 設為預設選單
    resp = requests.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{richmenu_id}",
        headers=headers_json
    )
    if resp.status_code == 200:
        print("✅ 已設為預設選單，重新開啟 LINE 即可看到")
    else:
        print(f"❌ 設預設失敗：{resp.status_code} {resp.text}")

if __name__ == "__main__":
    create_richmenu()
