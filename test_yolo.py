from ultralytics import YOLO

model = YOLO("runs/detect/umbrella_custom/weights/best.pt")
results = model("train/IMG_2103.jpeg", conf=0.25, save=True)

boxes = results[0].boxes
print(f"偵測到 {len(boxes)} 個物件")
for b in boxes:
    cls  = int(b.cls)
    conf = float(b.conf)
    name = model.names[cls]
    print(f"  → {name}  信心值：{conf:.2%}")
