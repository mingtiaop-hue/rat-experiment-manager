"""
工具函数：照片压缩、Excel 导出、二维码
"""

import os, io, base64
import pandas as pd
from datetime import datetime
from PIL import Image

from config import GROUPS, GROUP_LABELS, TIMELINE, get_rat_type_label
from database import get_all_data, EXPORT_DIR, PHOTO_DIR

PHOTO_MAX_WIDTH = 1920
PHOTO_MAX_HEIGHT = 1920
PHOTO_JPEG_QUALITY = 85


def compress_photo(input_data) -> tuple[bytes, int, int]:
    img = Image.open(input_data)
    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img.convert("RGBA"))
    img = img.convert("RGB")
    w, h = img.size
    if w > PHOTO_MAX_WIDTH or h > PHOTO_MAX_HEIGHT:
        ratio = min(PHOTO_MAX_WIDTH / w, PHOTO_MAX_HEIGHT / h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=PHOTO_JPEG_QUALITY, optimize=True)
    return buf.getvalue(), img.size[0], img.size[1]


def save_uploaded_photo(uploaded_file, save_path: str) -> dict:
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    data, w, h = compress_photo(uploaded_file)
    with open(save_path, "wb") as f:
        f.write(data)
    return {"path": save_path, "width": w, "height": h, "size_kb": round(len(data) / 1024, 1)}


def generate_qr_code(url: str) -> str:
    try:
        import qrcode
        from qrcode.image.styledpil import StyledPilImage
        from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(image_factory=StyledPilImage, module_drawer=RoundedModuleDrawer())
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        import qrcode as qs
        qr = qs.QRCode(box_size=8, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()


def export_to_excel(group_filter: str = None) -> str:
    records = get_all_data(group=group_filter)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = os.path.join(EXPORT_DIR, f"experiment_{ts}.xlsx")

    # Sheet 1: 原始数据
    s1 = []
    for r in records:
        if r["experiment_day"] is None:
            continue
        s1.append({
            "鼠编号": r["rat_id"],
            "鼠类型": get_rat_type_label(r["rat_id"]),
            "伤口": r["wound_id"],
            "伤口位": f"W{r['wound_position']}",
            "分组": GROUP_LABELS.get(r["group_name"], r["group_name"]),
            "天数": r["experiment_day"],
            "治疗后天数": TIMELINE.get(r["experiment_day"], ("?",))[0],
            "伤口面积(mm²)": r["wound_area_mm2"],
            "备注": r["notes"] or "",
        })
    df1 = pd.DataFrame(s1)

    # Sheet 2: GraphPad 格式
    s2 = []
    from database import get_conn
    conn = get_conn()
    wounds = conn.execute("SELECT * FROM wounds ORDER BY rat_id, wound_position").fetchall()
    conn.close()
    for w in wounds:
        w = dict(w)
        row = {"伤口ID": w["wound_id"], "鼠编号": w["rat_id"],
               "分组": GROUP_LABELS.get(w["group_name"], w["group_name"])}
        for r in records:
            if r["wound_id"] == w["wound_id"] and r["experiment_day"]:
                row[f"D{r['experiment_day']}_面积"] = r["wound_area_mm2"]
        s2.append(row)
    df2 = pd.DataFrame(s2)

    with pd.ExcelWriter(fp, engine="openpyxl") as writer:
        df1.to_excel(writer, sheet_name="原始数据", index=False)
        df2.to_excel(writer, sheet_name="GraphPad格式", index=False)
        for sn in ["原始数据", "GraphPad格式"]:
            ws = writer.sheets[sn]
            for col in ws.columns:
                mx = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(mx + 4, 30)
    return fp


def check_photo_integrity() -> dict:
    from database import get_conn
    conn = get_conn()
    db_ps = {r["file_path"].replace("\\", "/") for r in conn.execute("SELECT file_path FROM photos").fetchall()}
    conn.close()
    fs = set()
    for root, _, files in os.walk(PHOTO_DIR):
        for f in files:
            if f.endswith((".jpg", ".jpeg", ".png")):
                fs.add(os.path.join(root, f).replace("\\", "/"))
    return {"orphan": list(fs - db_ps), "missing": list(db_ps - fs), "ok": len(db_ps & fs)}


def cleanup_orphan_photos() -> int:
    result = check_photo_integrity()
    for f in result["orphan"]:
        try:
            os.remove(f)
        except OSError:
            pass
    return len(result["orphan"])
