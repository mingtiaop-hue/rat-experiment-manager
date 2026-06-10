"""
动物实验记录与数据管理系统 v3.1 — Streamlit
每鼠 4 伤口 | 拖拽照片自动保存 | 批量上传 | 跨鼠对比
"""
import streamlit as st
import os, socket, time
import pandas as pd
from datetime import datetime

from config import (
    GROUPS, GROUP_LABELS, TIMELINE, SAMPLING_DAYS,
    NON_ES_RATS, ES_RATS, WOUND_COUNT,
    SAMPLE_TYPES, FIXATION_METHODS, TOTAL_DAYS,
    get_rat_type_label,
)
from database import (
    init_db, is_initialized, init_experiment,
    get_all_rats, get_active_rats, update_rat_status,
    get_wounds_by_rat, get_wound_record, upsert_wound_record,
    update_wound_status, get_wound_group, get_wound_status_summary,
    get_photo_path, save_photo_info, get_wound_photos,
    add_sample, get_all_samples, get_all_data,
    backup_database, set_meta, get_meta,
)
from utils import (
    save_uploaded_photo, export_to_excel, generate_qr_code,
    check_photo_integrity, cleanup_orphan_photos, compress_photo,
)

st.set_page_config(page_title="动物实验管理", page_icon="🐀", layout="wide")
init_db()


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1); s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ========== 辅助弹窗（必须在 Tab 之前定义） ==========
def _render_one_dialog(day: int):
    """只渲染当前激活的那一个弹窗"""
    for key in list(st.session_state):
        if key.startswith("harv_") and st.session_state[key]:
            wound_id = key.replace("harv_", "")
            group = get_wound_group(wound_id)
            st.divider()
            st.warning(f"🔪 取材: **{wound_id}** ({GROUP_LABELS.get(group, group)})")
            with st.form(key=f"hf_{wound_id}_{day}"):
                stypes = st.multiselect("样本类型", SAMPLE_TYPES, key=f"ht_{wound_id}")
                sid = st.text_input("样本编号", key=f"hi_{wound_id}")
                slo = st.text_input("保存位置", key=f"hl_{wound_id}")
                sfi = st.selectbox("固定方法", options=[""] + FIXATION_METHODS, key=f"hf_{wound_id}")
                c1, c2 = st.columns(2)
                if c1.form_submit_button("✅ 确认", type="primary", use_container_width=True):
                    if not stypes:
                        st.error("请选样本类型")
                    else:
                        update_wound_status(wound_id, "Harvested")
                        for t in stypes:
                            add_sample(wound_id, day, t, sid or None, slo or None, sfi or None)
                        st.success(f"{wound_id} 已取材")
                        del st.session_state[key]; st.rerun()
                if c2.form_submit_button("❌ 取消", use_container_width=True):
                    del st.session_state[key]; st.rerun()
            return
        if key.startswith("deadw_") and st.session_state[key]:
            wound_id = key.replace("deadw_", "")
            st.divider(); st.error(f"💀 伤口坏疽: **{wound_id}**")
            with st.form(key=f"dwf_{wound_id}_{day}"):
                st.markdown("该伤口将标记为 Deceased。")
                c1, c2 = st.columns(2)
                if c1.form_submit_button("✅ 确认", type="primary", use_container_width=True):
                    update_wound_status(wound_id, "Deceased")
                    st.warning(f"{wound_id} 已标记"); del st.session_state[key]; st.rerun()
                if c2.form_submit_button("❌ 取消", use_container_width=True):
                    del st.session_state[key]; st.rerun()
            return
        if key.startswith("deadr_") and st.session_state[key]:
            rat_id = int(key.replace("deadr_", ""))
            st.divider(); st.error(f"💀 鼠死亡: **{rat_id}**")
            with st.form(key=f"drf_{rat_id}_{day}"):
                reason = st.text_area("死亡原因（必填）", placeholder="麻醉过量、感染...")
                c1, c2 = st.columns(2)
                if c1.form_submit_button("✅ 确认", type="primary", use_container_width=True):
                    if not reason.strip():
                        st.error("必填死亡原因")
                    else:
                        update_rat_status(rat_id, "Deceased", reason.strip())
                        st.warning(f"鼠 {rat_id} 已标记死亡"); del st.session_state[key]; st.rerun()
                if c2.form_submit_button("❌ 取消", use_container_width=True):
                    del st.session_state[key]; st.rerun()
            return


# ==================== 侧边栏 ====================
with st.sidebar:
    st.title("🐀 实验管理")
    st.caption("糖尿病大鼠创面愈合")
    if is_initialized():
        summary = get_wound_status_summary()
        st.divider()
        for g in GROUPS:
            gs = summary.get(g, {"Active": 0, "Harvested": 0, "Deceased": 0})
            total = sum(gs.values())
            st.markdown(f"**{g}**  {gs['Active']}/{total}  🟢{gs['Active']} 🔵{gs['Harvested']} 🔴{gs['Deceased']}")
        st.divider()
        if st.button("💾 备份数据库", use_container_width=True):
            st.success(f"已备份: {os.path.basename(backup_database())}")
        if st.button("🧹 清理孤儿照片", use_container_width=True):
            st.success(f"已删除 {cleanup_orphan_photos()}")
        st.divider()
        url = f"http://{get_lan_ip()}:8501"
        st.markdown(
            f'<div style="text-align:center"><img src="data:image/png;base64,{generate_qr_code(url)}" width="160">'
            f'<p style="font-size:11px;color:#888;margin-top:3px">{url}</p></div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning("实验未初始化")
    st.divider()
    st.caption(datetime.now().strftime("%Y-%m-%d %H:%M"))

# ==================== 主页面 ====================
st.title("🐀 糖尿病大鼠创面愈合实验")
st.caption("拖拽照片自动保存 | 批量上传 | 伤口面积 ImageJ 后补 | 跨鼠对比")

# ==================== 初始化 ====================
if not is_initialized():
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**不电刺激 (10只)**: {', '.join(str(r) for r in NON_ES_RATS)}\n\nW1→Control / W2→Alginate / W3,W4→Alginate_HJ")
    with col_b:
        st.markdown(f"**电刺激 (7只)**: {', '.join(str(r) for r in ES_RATS)}\n\nW1,W2→Pure_ES / W3,W4→Stretched_HJ_ES")
    if st.button("🚀 初始化实验", type="primary", use_container_width=True):
        init_experiment(); set_meta("created_at", datetime.now().isoformat())
        st.success("17只鼠，68个伤口。")
        st.rerun()
    st.stop()

# ==================== 主 Tabs ====================
tab_entry, tab_batch, tab_gallery, tab_compare, tab_export, tab_samples, tab_status = st.tabs([
    "📋 日常录入", "📦 批量上传", "🖼️ 照片长廊", "🔬 跨鼠对比",
    "📊 数据导出", "🧪 样本管理", "🐁 状态总览",
])

# ==================== TAB 1: 日常录入 ====================
with tab_entry:
    day_col, info_col = st.columns([1, 3])
    with day_col:
        current_day = st.selectbox("实验天数", options=list(range(1, TOTAL_DAYS + 1)),
                                   format_func=lambda d: f"Day {d}", key="day")
    with info_col:
        pt_day, desc, is_sampling = TIMELINE[current_day]
        if is_sampling:
            st.error(f"⚡ 取材日 Day {current_day} ({pt_day}) — {desc}")
        else:
            st.info(f"📌 Day {current_day} ({pt_day}) — {desc}")

    active_rats = get_active_rats()
    if not active_rats:
        st.warning("没有存活鼠。")
    else:
        st.markdown(f"### 🐁 {len(active_rats)} 只存活鼠")

        for rat in active_rats:
            rat_id = rat["rat_id"]
            wounds = [w for w in get_wounds_by_rat(rat_id) if w["status"] == "Active"]
            if not wounds:
                continue
            with st.expander(
                f"鼠 {rat_id} ({get_rat_type_label(rat_id)}) — {len(wounds)} 存活伤口",
                expanded=len(active_rats) <= 2,
            ):
                # 每伤口一行：面积 + 照片 + 操作
                for w in wounds:
                    wound_id = w["wound_id"]
                    pos = w["wound_position"]
                    group = w["group_name"]
                    label = GROUP_LABELS.get(group, group)

                    c1, c2, c3, c4 = st.columns([1.5, 2.5, 1, 1])
                    c1.markdown(f"**W{pos}** — {label}")

                    exist = get_wound_record(wound_id, current_day)
                    area = c2.number_input(
                        "伤口面积 mm²",
                        min_value=0.0, max_value=5000.0, step=0.1,
                        value=exist["wound_area_mm2"] if exist and exist["wound_area_mm2"] else None,
                        key=f"a_{wound_id}_{current_day}", label_visibility="visible",
                        help="可留空，ImageJ 后补",
                    )

                    photo = c2.file_uploader(
                        f"📸 拖拽照片", type=["jpg", "jpeg", "png"],
                        key=f"ph_{wound_id}_{current_day}", label_visibility="visible",
                    )
                    if photo:
                        sp = get_photo_path(group, wound_id, current_day)
                        info = save_uploaded_photo(photo, sp)
                        save_photo_info(wound_id, current_day, sp)
                        # 自动保存面积（如果填了）
                        if area and area > 0:
                            upsert_wound_record(wound_id, current_day, area)
                        st.toast(f"{wound_id} 📸 {info['size_kb']}KB 已保存", icon="✅")

                    save_label = "✏️" if exist else "💾"
                    if c3.button(save_label, key=f"sv_{wound_id}_{current_day}", use_container_width=True, help="保存伤口面积"):
                        upsert_wound_record(wound_id, current_day, area if area else None)
                        st.toast(f"{wound_id} 已保存", icon="✅")

                    if is_sampling:
                        if c4.button("🔪", key=f"hv_{wound_id}", use_container_width=True, help="取材"):
                            st.session_state[f"harv_{wound_id}"] = True
                    if c4.button("💀", key=f"dd_{wound_id}", use_container_width=True, help="坏疽"):
                        st.session_state[f"deadw_{wound_id}"] = True

                st.divider()
                if st.button(f"💀 鼠 {rat_id} 死亡", key=f"dr_{rat_id}"):
                    st.session_state[f"deadr_{rat_id}"] = True

        _render_one_dialog(current_day)

# ==================== TAB 2: 批量上传 ====================
with tab_batch:
    st.subheader("📦 批量上传 — 一键拖入 4 张照片")
    st.caption("按 W1→W4 顺序拖入照片，自动分配到对应伤口。也支持单鼠拖入后再逐一调整。")

    batch_day = st.selectbox("实验天数", list(range(1, TOTAL_DAYS + 1)),
                             format_func=lambda d: f"Day {d}", key="batch_day")
    pt_day, desc, is_sampling = TIMELINE[batch_day]
    if is_sampling:
        st.error(f"⚡ 取材日 Day {batch_day} ({pt_day})")
    else:
        st.info(f"📌 Day {batch_day} ({pt_day})")

    # 选择一只鼠，一次性拖入 4 张照片
    batch_rat = st.selectbox("选择鼠", options=[r["rat_id"] for r in get_active_rats()],
                             format_func=lambda r: f"鼠 {r} ({get_rat_type_label(r)})", key="batch_rat")

    if batch_rat:
        wounds = [w for w in get_wounds_by_rat(batch_rat) if w["status"] == "Active"]
        st.markdown(f"### 鼠 {batch_rat} — {len(wounds)} 个存活伤口")

        # 拖入多张照片
        batch_files = st.file_uploader(
            f"📸 拖入照片（按 W1→W2→W3→W4 顺序，可多选）",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key=f"batch_{batch_rat}_{batch_day}",
            help="按顺序选择：第1张→W1, 第2张→W2, 第3张→W3, 第4张→W4",
        )

        if batch_files:
            # 浏览器多文件上传顺序经常是反的，反转后第1张→W1
            batch_files = list(reversed(batch_files))
            # 预览所有照片
            preview_cols = st.columns(min(len(batch_files), 4))
            for i, bf in enumerate(batch_files):
                with preview_cols[i]:
                    st.image(bf, caption=f"第{i + 1}张", width=180)

            if st.button(f"🚀 一键保存 {len(batch_files)} 张照片", type="primary", use_container_width=True):
                saved_count = 0
                for i, bf in enumerate(batch_files):
                    if i >= len(wounds):
                        st.warning(f"照片数量({len(batch_files)})超过存活伤口数({len(wounds)})，第{i + 1}张及之后跳过")
                        break
                    wound_id = wounds[i]["wound_id"]
                    group = wounds[i]["group_name"]
                    sp = get_photo_path(group, wound_id, batch_day)
                    info = save_uploaded_photo(bf, sp)
                    save_photo_info(wound_id, batch_day, sp)
                    saved_count += 1
                st.success(f"✅ 已保存 {saved_count} 张照片")
                st.balloons()

        # 显示当前已上传的照片
        st.divider()
        st.markdown("#### 当前已有照片")
        photo_cols = st.columns(min(len(wounds), 4))
        for i, w in enumerate(wounds):
            photos = get_wound_photos(w["wound_id"])
            dp = next((p for p in photos if p["experiment_day"] == batch_day), None)
            with photo_cols[i]:
                st.markdown(f"**W{w['wound_position']}** — {GROUP_LABELS.get(w['group_name'], w['group_name'])}")
                if dp and os.path.exists(dp["file_path"]):
                    st.image(dp["file_path"], width=180)
                else:
                    st.markdown("<div style='height:80px;background:#eee;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#bbb;font-size:11px'>无照片</div>", unsafe_allow_html=True)

# ==================== TAB 3: 照片长廊 ====================
with tab_gallery:
    st.subheader("🖼️ 单鼠伤口时间线")

    rats = get_all_rats()
    rat_ids = [r["rat_id"] for r in rats]
    if rat_ids:
        cr1, cr2 = st.columns(2)
        with cr1:
            sel_rat = cr1.selectbox("鼠编号", options=rat_ids, key="gal_rat")
        if sel_rat is not None:
            wounds = get_wounds_by_rat(sel_rat)
            with cr2:
                sel_w = cr2.selectbox("伤口", options=list(range(len(wounds))),
                                      format_func=lambda i: f"W{wounds[i]['wound_position']} — {GROUP_LABELS.get(wounds[i]['group_name'], wounds[i]['group_name'])}",
                                      key="gal_w")
            if sel_w is not None:
                wound_id = wounds[sel_w]["wound_id"]
                photos = get_wound_photos(wound_id)
                if not photos:
                    st.info("暂无照片。拖拽上传即可。")
                else:
                    cols = st.columns(min(len(photos), 7))
                    for i, p in enumerate(photos):
                        with cols[i % 7]:
                            if os.path.exists(p["file_path"]):
                                st.image(p["file_path"], caption=f"D{p['experiment_day']}", width=180)
                    st.divider()
                    st.markdown("#### Day 1–14 全时间线")
                    grid = st.columns(7)
                    for day in range(1, TOTAL_DAYS + 1):
                        dp = next((p for p in photos if p["experiment_day"] == day), None)
                        with grid[(day - 1) % 7]:
                            if dp and os.path.exists(dp["file_path"]):
                                st.image(dp["file_path"], caption=f"D{day}", width=180)
                            else:
                                st.markdown(f"<div style='height:55px;background:#eee;border-radius:4px;display:flex;align-items:center;justify-content:center;color:#bbb;font-size:10px'>D{day}</div>", unsafe_allow_html=True)
    else:
        st.info("请先初始化实验。")

# ==================== TAB 4: 跨鼠对比 ====================
with tab_compare:
    st.subheader("🔬 跨鼠照片对比")
    st.caption("实验结束后，选择不同鼠的同一伤口位，横向对比愈合效果。选择数据用。")

    # 选择要对比的伤口位置
    comp_pos = st.radio("对比伤口位", options=[1, 2, 3, 4], horizontal=True,
                        format_func=lambda p: f"W{p}")
    comp_group = GROUPS[[1, 2, 3, 3][comp_pos - 1] if comp_pos else 0]  # 默认 W1→Control
    st.caption(f"该伤口位对应组: **{GROUP_LABELS.get(comp_group or 'Control', '?')}**")

    # 选择多只鼠
    all_rats = get_all_rats()
    comp_rats = st.multiselect(
        "选择要对比的鼠（可多选）",
        options=[r["rat_id"] for r in all_rats],
        default=[r["rat_id"] for r in all_rats[:3]],
        help="Ctrl+Click 多选",
    )

    # 选择对比的天
    comp_days = st.multiselect(
        "选择对比的天",
        options=list(range(1, TOTAL_DAYS + 1)),
        default=[1, 3, 5, 7],
        format_func=lambda d: f"Day {d}",
    )

    if comp_rats and comp_days:
        st.markdown("---")
        # 表格形式：行=鼠，列=天
        for rat_id in sorted(comp_rats):
            st.markdown(f"### 🐁 鼠 {rat_id} ({get_rat_type_label(rat_id)})")
            wounds = get_wounds_by_rat(rat_id)
            w = next((w for w in wounds if w["wound_position"] == comp_pos), None)
            if w is None:
                st.caption(f"W{comp_pos} 不存在")
                continue
            wound_id = w["wound_id"]
            photos = get_wound_photos(wound_id)
            cols = st.columns(len(comp_days))
            for i, day in enumerate(comp_days):
                dp = next((p for p in photos if p["experiment_day"] == day), None)
                with cols[i]:
                    st.markdown(f"**D{day}**")
                    if dp and os.path.exists(dp["file_path"]):
                        st.image(dp["file_path"], width=180)
                    else:
                        st.markdown("<div style='height:70px;background:#eee;border-radius:4px;display:flex;align-items:center;justify-content:center;color:#bbb;font-size:10px'>—</div>", unsafe_allow_html=True)

# ==================== TAB 5: 数据导出 ====================
with tab_export:
    st.subheader("📊 数据导出")
    cf1, cf2 = st.columns(2)
    with cf1:
        f_group = st.selectbox("分组", ["全部"] + GROUPS, key="fg")
    with cf2:
        f_day = st.selectbox("天数", ["全部"] + list(range(1, TOTAL_DAYS + 1)), key="fd")
    gv = None if f_group == "全部" else f_group
    dv = None if f_day == "全部" else f_day
    records = [r for r in get_all_data(group=gv, day=dv) if r["experiment_day"]]
    if records:
        df = pd.DataFrame(records).rename(columns={
            "rat_id": "鼠", "wound_id": "伤口ID", "wound_position": "位",
            "group_name": "分组", "experiment_day": "天", "wound_area_mm2": "面积",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)
    st.divider()
    ce1, ce2 = st.columns([1, 3])
    if ce1.button("📥 导出 Excel", type="primary", use_container_width=True):
        fp = export_to_excel(group_filter=gv)
        with open(fp, "rb") as f:
            ce2.download_button("⬇️ 下载", data=f, file_name=os.path.basename(fp),
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.success(f"已导出: {os.path.basename(fp)}")
    if st.button("🔍 照片完整性检查", use_container_width=True):
        r = check_photo_integrity()
        st.metric("正常", r["ok"])
        if r["orphan"]: st.warning(f"孤儿文件: {len(r['orphan'])}")
        if r["missing"]: st.error(f"缺失: {len(r['missing'])}")

# ==================== TAB 6: 样本管理 ====================
with tab_samples:
    st.subheader("🧪 组织样本")
    samples = get_all_samples()
    if samples:
        sdata = [{
            "伤口": s["wound_id"], "鼠": s["rat_id"],
            "分组": GROUP_LABELS.get(s["group_name"], ""), "取材日": f"D{s['harvest_day']}",
            "类型": s["sample_type"], "编号": s["sample_id"] or "—",
            "位置": s["storage_location"] or "—", "固定": s["fixation_method"] or "—",
        } for s in samples]
        st.dataframe(pd.DataFrame(sdata), use_container_width=True, hide_index=True)
    else:
        st.info("暂无样本。")

# ==================== TAB 7: 状态总览 ====================
with tab_status:
    st.subheader("🐁 状态总览")
    all_rats = get_all_rats()
    summary = get_wound_status_summary()
    ar = sum(1 for r in all_rats if r["status"] == "Active")
    cols = st.columns(5)
    cols[0].metric("鼠数", len(all_rats))
    cols[1].metric("存活鼠", ar)
    cols[2].metric("总伤口", sum(sum(g.values()) for g in summary.values()))
    cols[3].metric("存活伤口", sum(g["Active"] for g in summary.values()))
    cols[4].metric("已取样", sum(g["Harvested"] for g in summary.values()))
    st.divider()
    tdata = [{"分组": g, "中文": GROUP_LABELS[g],
              "存活": f"🟢 {summary.get(g,{}).get('Active',0)}",
              "取材": f"🔵 {summary.get(g,{}).get('Harvested',0)}",
              "坏疽": f"🔴 {summary.get(g,{}).get('Deceased',0)}",
              "计": sum(summary.get(g, {"Active":0,"Harvested":0,"Deceased":0}).values())} for g in GROUPS]
    st.dataframe(pd.DataFrame(tdata), use_container_width=True, hide_index=True)
    st.divider()
    for rat in all_rats:
        wounds = get_wounds_by_rat(rat["rat_id"])
        aw = [w for w in wounds if w["status"] == "Active"]
        si = {"Active": "🟢", "Harvested": "🔵", "Deceased": "🔴"}.get(rat["status"], "⚪")
        with st.expander(
            f"{si} 鼠 {rat['rat_id']} ({get_rat_type_label(rat['rat_id'])}) — {len(aw)}/{len(wounds)}"
            + (f" | {rat['death_reason']}" if rat.get("death_reason") else ""),
            expanded=rat["status"] == "Active",
        ):
            wc = st.columns(len(wounds))
            for i, w in enumerate(wounds):
                wi = {"Active": "🟢", "Harvested": "🔵", "Deceased": "🔴"}[w["status"]]
                wc[i].markdown(f"{wi} W{w['wound_position']}\n{GROUP_LABELS.get(w['group_name'], w['group_name'])}")

st.divider()
st.caption("🐀 v3.1 | 拖拽自动保存 | 批量上传 | 跨鼠对比 | ImageJ 后补面积")
