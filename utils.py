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
PHOTO_JPEG_QUALITY = 80  # 降低质量到80，大幅减小体积且视觉差异极小
PHOTO_MAX_MEGAPIXELS = 20  # 超过20MP的图先粗暴缩小


def compress_photo(input_data) -> tuple[bytes, int, int]:
    """压缩照片，返回 (jpeg_bytes, width, height)。遇损坏图片抛出带中文的 ValueError。"""
    try:
        img = Image.open(input_data)
    except Exception as e:
        raise ValueError(f"无法识别图片格式，可能是损坏文件: {e}") from e

    try:
        # RGBA / P / LA 模式先合成白色背景
        if img.mode in ("RGBA", "P", "LA"):
            if img.mode == "P":
                img = img.convert("RGBA")
            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            img = Image.alpha_composite(bg, img.convert("RGBA"))
        img = img.convert("RGB")

        w, h = img.size
        mp = (w * h) / 1_000_000

        # 超大图先快速缩小到合理范围
        if mp > PHOTO_MAX_MEGAPIXELS:
            ratio = (PHOTO_MAX_MEGAPIXELS / mp) ** 0.5
            img = img.resize((int(w * ratio), int(h * ratio)), Image.NEAREST)
            w, h = img.size

        # 再精确缩放到目标尺寸
        if w > PHOTO_MAX_WIDTH or h > PHOTO_MAX_HEIGHT:
            ratio = min(PHOTO_MAX_WIDTH / w, PHOTO_MAX_HEIGHT / h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=PHOTO_JPEG_QUALITY, optimize=True)
        return buf.getvalue(), img.size[0], img.size[1]
    except Exception as e:
        raise ValueError(f"图片压缩失败: {e}") from e


def save_uploaded_photo(uploaded_file, save_path: str) -> dict:
    """保存上传照片，返回 {path, width, height, size_kb}。失败抛出 ValueError。"""
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

    # Sheet 1: 原始数据 (含死亡信息 + 愈合率)
    s1 = []
    # 先收集Day1基线面积
    day1_areas = {}
    for r in records:
        if r["experiment_day"] == 1 and r["wound_area_mm2"] is not None:
            day1_areas[r["wound_id"]] = r["wound_area_mm2"]

    for r in records:
        if r["experiment_day"] is None:
            continue
        # 愈合率
        healing_rate = None
        if r["wound_id"] in day1_areas and r["wound_area_mm2"] is not None and day1_areas[r["wound_id"]] > 0:
            healing_rate = round((day1_areas[r["wound_id"]] - r["wound_area_mm2"]) / day1_areas[r["wound_id"]] * 100, 1)
        s1.append({
            "鼠编号": r["rat_id"],
            "鼠类型": get_rat_type_label(r["rat_id"]),
            "鼠状态": r.get("rat_status", ""),
            "伤口": r["wound_id"],
            "伤口位": f"W{r['wound_position']}",
            "分组": GROUP_LABELS.get(r["group_name"], r["group_name"]),
            "天数": r["experiment_day"],
            "治疗后天数": TIMELINE.get(r["experiment_day"], ("?",))[0],
            "伤口面积(mm²)": r["wound_area_mm2"],
            "愈合率(%)": healing_rate,
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

    # Sheet 3: 鼠信息
    from database import get_all_rats
    rats = get_all_rats()
    s3 = [{
        "鼠编号": r["rat_id"],
        "类型": get_rat_type_label(r["rat_id"]),
        "状态": r["status"],
        "死亡类型": r.get("death_type") or "",
        "死亡原因": r.get("death_reason") or "",
        "死亡天数": f"Day {r['death_day']}" if r.get("death_day") else "",
        "死亡时间": r.get("death_time") or "",
    } for r in rats]
    df3 = pd.DataFrame(s3)

    with pd.ExcelWriter(fp, engine="openpyxl") as writer:
        df1.to_excel(writer, sheet_name="原始数据", index=False)
        df2.to_excel(writer, sheet_name="GraphPad格式", index=False)
        df3.to_excel(writer, sheet_name="鼠信息", index=False)
        for sn in ["原始数据", "GraphPad格式", "鼠信息"]:
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
