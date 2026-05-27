"""
用 16 張照片 fine-tune YOLOv8n，加強資料擴增避免過擬合。
執行：python train_model.py
"""

from pathlib import Path
from ultralytics import YOLO

DATA_YAML   = Path("dataset/data.yaml")
BASE_MODEL  = "yolov8n.pt"
OUTPUT_NAME = "umbrella_custom"

def main():
    if not DATA_YAML.exists():
        print("❌ 找不到 dataset/data.yaml，請先執行 python prepare_dataset.py")
        return

    model = YOLO(BASE_MODEL)

    results = model.train(
        data    = str(DATA_YAML),
        epochs  = 100,
        imgsz   = 640,
        batch   = 8,
        name    = OUTPUT_NAME,
        patience= 20,       # 20 epochs 沒進步就提早停止

        # 資料擴增（小資料集必開）
        flipud  = 0.3,
        fliplr  = 0.5,
        degrees = 15,
        translate=0.1,
        scale   = 0.4,
        hsv_h   = 0.02,
        hsv_s   = 0.5,
        hsv_v   = 0.3,
        mosaic  = 0.5,
    )

    # 找出最佳模型路徑
    best = Path(f"runs/detect/{OUTPUT_NAME}/weights/best.pt")
    if best.exists():
        print(f"\n✅ 訓練完成！")
        print(f"   最佳模型：{best.resolve()}")
        print(f"\n下一步：將 app.py 的 YOLO('yolov8n.pt') 改為 YOLO('{best}')")
    else:
        print(f"\n⚠️ 訓練結束，請確認 runs/detect/{OUTPUT_NAME}/weights/ 資料夾")

if __name__ == "__main__":
    main()
