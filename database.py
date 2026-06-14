"""
数据库层：SQLite 表创建与 CRUD 操作
数据模型：每鼠 4 伤口，伤口级分组，伤口面积可后补（ImageJ 计算）
"""

import sqlite3, os, shutil
from datetime import datetime
from typing import Optional

DB_DIR = os.path.join(os.path.dirname(__file__), "experiment_data")
DB_PATH = os.path.join(DB_DIR, "experiment.db")
PHOTO_DIR = os.path.join(DB_DIR, "photos")
EXPORT_DIR = os.path.join(DB_DIR, "exports")

for d in [DB_DIR, PHOTO_DIR, EXPORT_DIR]:
    os.makedirs(d, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS experiment_meta (
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS rats (
            rat_id INTEGER PRIMARY KEY,
            rat_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active',
            death_reason TEXT,
            death_time TIMESTAMP,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS wounds (
            wound_id TEXT PRIMARY KEY,
            rat_id INTEGER NOT NULL,
            wound_position INTEGER NOT NULL,
            group_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active',
            FOREIGN KEY (rat_id) REFERENCES rats(rat_id)
        );
        -- 伤口每日记录（伤口面积可选，后续用 ImageJ 补填）
        CREATE TABLE IF NOT EXISTS wound_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wound_id TEXT NOT NULL,
            experiment_day INTEGER NOT NULL,
            wound_area_mm2 REAL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wound_id) REFERENCES wounds(wound_id),
            UNIQUE(wound_id, experiment_day)
        );
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wound_id TEXT NOT NULL,
            experiment_day INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (wound_id) REFERENCES wounds(wound_id),
            UNIQUE(wound_id, experiment_day)
        );
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wound_id TEXT NOT NULL,
            harvest_day INTEGER NOT NULL,
            sample_type TEXT NOT NULL,
            sample_id TEXT,
            storage_location TEXT,
            fixation_method TEXT,
            FOREIGN KEY (wound_id) REFERENCES wounds(wound_id)
        );
        CREATE INDEX IF NOT EXISTS idx_wounds_rat ON wounds(rat_id);
        CREATE INDEX IF NOT EXISTS idx_wounds_group ON wounds(group_name);
        CREATE INDEX IF NOT EXISTS idx_wrecords_wound_day ON wound_records(wound_id, experiment_day);
        CREATE INDEX IF NOT EXISTS idx_photos_wound_day ON photos(wound_id, experiment_day);
        CREATE INDEX IF NOT EXISTS idx_samples_wound ON samples(wound_id);
    """)
    # Migrations: add columns if not exist
    for col, col_type in [
        ("death_time", "TIMESTAMP"),
        ("death_type", "TEXT"),
        ("death_day", "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE rats ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()


def get_meta(key: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute("SELECT value FROM experiment_meta WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_meta(key: str, value: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO experiment_meta (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# ==================== 初始化 ====================
def init_experiment():
    from config import NON_ES_RATS, ES_RATS, WOUND_MAPPING, WOUND_COUNT
    conn = get_conn()
    if conn.execute("SELECT COUNT(*) as cnt FROM rats").fetchone()["cnt"] > 0:
        conn.close()
        raise RuntimeError("实验已初始化")

    for rat_id in NON_ES_RATS:
        conn.execute("INSERT INTO rats (rat_id, rat_type) VALUES (?, 'non_es')", (rat_id,))
        for pos in range(1, WOUND_COUNT + 1):
            wound_id = f"{rat_id}_W{pos}"
            conn.execute("INSERT INTO wounds (wound_id, rat_id, wound_position, group_name) VALUES (?,?,?,?)",
                         (wound_id, rat_id, pos, WOUND_MAPPING["non_es"][pos]))

    for rat_id in ES_RATS:
        conn.execute("INSERT INTO rats (rat_id, rat_type) VALUES (?, 'es')", (rat_id,))
        for pos in range(1, WOUND_COUNT + 1):
            wound_id = f"{rat_id}_W{pos}"
            conn.execute("INSERT INTO wounds (wound_id, rat_id, wound_position, group_name) VALUES (?,?,?,?)",
                         (wound_id, rat_id, pos, WOUND_MAPPING["es"][pos]))

    conn.commit()
    conn.close()


# ==================== 鼠 ====================
def get_all_rats() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rats ORDER BY rat_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_rats() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM rats WHERE status = 'Active' ORDER BY rat_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_rats_alive_on_day(day: int) -> list[dict]:
    """返回在指定实验天存活的鼠（死亡日当天仍显示，之后不显示）"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM rats WHERE status = 'Active' OR (status = 'Deceased' AND death_day >= ?) ORDER BY rat_id",
        (day,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_rat_day_completion(day: int) -> dict[int, dict]:
    """返回每只存活鼠在指定天的录入情况。
    Returns: {rat_id: {total: 存活伤口数, done: 已录入(有照片或面积)伤口数, wound_ids: [...]}}"""
    alive = get_rats_alive_on_day(day)
    conn = get_conn()
    result = {}
    for rat in alive:
        rid = rat["rat_id"]
        wounds = conn.execute(
            "SELECT wound_id FROM wounds WHERE rat_id=? AND status='Active'", (rid,)).fetchall()
        wound_ids = [w["wound_id"] for w in wounds]
        if not wound_ids:
            result[rid] = {"total": 0, "done": 0, "wound_ids": []}
            continue
        placeholders = ",".join("?" * len(wound_ids))
        # 有照片或面积记录即视为已录入
        done_photos = set(r[0] for r in conn.execute(
            f"SELECT DISTINCT wound_id FROM photos WHERE experiment_day=? AND wound_id IN ({placeholders})",
            (day, *wound_ids)).fetchall())
        done_areas = set(r[0] for r in conn.execute(
            f"SELECT DISTINCT wound_id FROM wound_records WHERE experiment_day=? AND wound_area_mm2 IS NOT NULL AND wound_id IN ({placeholders})",
            (day, *wound_ids)).fetchall())
        done = len(done_photos | done_areas)
        result[rid] = {"total": len(wound_ids), "done": done, "wound_ids": wound_ids}
    conn.close()
    return result


def update_rat_status(rat_id: int, status: str, death_reason: str = None,
                      death_type: str = None, death_day: int = None):
    """更新鼠状态。death_type: '实验死亡' | '取材处死'
    伤口状态不变——通过 get_rats_alive_on_day() 按 death_day 控制后续天是否出现。
    """
    conn = get_conn()
    if status == "Deceased":
        dt = death_type or "实验死亡"
        conn.execute(
            "UPDATE rats SET status=?, death_reason=?, death_type=?, death_day=?, death_time=CURRENT_TIMESTAMP WHERE rat_id=?",
            (status, death_reason, dt, death_day, rat_id))
        # 伤口保持不变：死亡当天仍可录入；后续天由 get_rats_alive_on_day 过滤
    else:
        conn.execute("UPDATE rats SET status=?, death_reason=?, death_type=NULL, death_day=NULL WHERE rat_id=?",
                     (status, death_reason, rat_id))
    conn.commit()
    conn.close()


# ==================== 伤口 ====================
def get_wounds_by_rat(rat_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM wounds WHERE rat_id=? ORDER BY wound_position", (rat_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_wound_status_summary() -> dict:
    """伤口分组状态，区分鼠存活/实验死亡/取材处死"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT w.group_name, w.status AS wound_status,
               CASE WHEN r.status = 'Active' THEN 'Active'
                    WHEN r.death_type = '取材处死' THEN '取材处死'
                    ELSE '实验死亡'
               END AS rat_state,
               COUNT(*) as cnt
        FROM wounds w JOIN rats r ON w.rat_id = r.rat_id
        GROUP BY w.group_name, w.status, rat_state
    """).fetchall()
    conn.close()
    from config import GROUPS
    summary = {g: {"Active": 0, "Harvested": 0, "Deceased": 0, "实验死亡": 0, "取材处死": 0} for g in GROUPS}
    for r in rows:
        g = r["group_name"]
        if r["rat_state"] == "Active":
            summary[g][r["wound_status"]] += r["cnt"]
        else:
            summary[g][r["rat_state"]] += r["cnt"]
    return summary


def update_wound_status(wound_id: str, status: str):
    conn = get_conn()
    conn.execute("UPDATE wounds SET status=? WHERE wound_id=?", (status, wound_id))
    conn.commit()
    conn.close()


def get_wound_group(wound_id: str) -> str:
    conn = get_conn()
    row = conn.execute("SELECT group_name FROM wounds WHERE wound_id=?", (wound_id,)).fetchone()
    conn.close()
    return row["group_name"] if row else "?"


# ==================== 伤口记录 ====================
def get_wound_record(wound_id: str, day: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM wound_records WHERE wound_id=? AND experiment_day=?", (wound_id, day)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_wound_record(wound_id: str, day: int, area: float = None, notes: str = None):
    conn = get_conn()
    exist = conn.execute(
        "SELECT id FROM wound_records WHERE wound_id=? AND experiment_day=?", (wound_id, day)).fetchone()
    if exist:
        conn.execute("UPDATE wound_records SET wound_area_mm2=COALESCE(?,wound_area_mm2), notes=COALESCE(?,notes), created_at=CURRENT_TIMESTAMP WHERE wound_id=? AND experiment_day=?",
                     (area, notes, wound_id, day))
    else:
        conn.execute("INSERT INTO wound_records (wound_id, experiment_day, wound_area_mm2, notes) VALUES (?,?,?,?)",
                     (wound_id, day, area, notes))
    conn.commit()
    conn.close()


# ==================== 照片 ====================
def get_photo_path(group: str, wound_id: str, day: int) -> str:
    dir_path = os.path.join(PHOTO_DIR, group, str(wound_id))
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, f"Day_{day}.jpg")


def save_photo_info(wound_id: str, day: int, file_path: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO photos (wound_id, experiment_day, file_path, upload_time) VALUES (?,?,?,CURRENT_TIMESTAMP)",
                 (wound_id, day, file_path))
    conn.commit()
    conn.close()


def get_wound_photos(wound_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM photos WHERE wound_id=? ORDER BY experiment_day", (wound_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_photo(wound_id: str, day: int) -> bool:
    """删除指定伤口某天的照片（DB记录+文件）。返回是否成功。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT file_path FROM photos WHERE wound_id=? AND experiment_day=?",
        (wound_id, day)).fetchone()
    if row:
        path = row["file_path"]
        conn.execute("DELETE FROM photos WHERE wound_id=? AND experiment_day=?", (wound_id, day))
        conn.commit()
        conn.close()
        # 删除物理文件
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        return True
    conn.close()
    return False


# ==================== 样本 ====================
def add_sample(wound_id: str, harvest_day: int, sample_type: str,
               sample_id: str = None, storage: str = None, fixation: str = None):
    conn = get_conn()
    conn.execute("INSERT INTO samples (wound_id, harvest_day, sample_type, sample_id, storage_location, fixation_method) VALUES (?,?,?,?,?,?)",
                 (wound_id, harvest_day, sample_type, sample_id, storage, fixation))
    conn.commit()
    conn.close()


def get_all_samples() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.*, w.group_name, w.rat_id, w.wound_position
        FROM samples s JOIN wounds w ON s.wound_id = w.wound_id
        ORDER BY s.harvest_day, w.rat_id, w.wound_position
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==================== 导出 ====================
def get_all_data(group: str = None, day: int = None) -> list[dict]:
    conn = get_conn()
    q = """SELECT r.rat_id, r.rat_type, r.status as rat_status,
           w.wound_id, w.wound_position, w.group_name, w.status as wound_status,
           wr.wound_area_mm2, wr.notes, wr.experiment_day
           FROM rats r JOIN wounds w ON r.rat_id=w.rat_id
           LEFT JOIN wound_records wr ON w.wound_id=wr.wound_id WHERE 1=1"""
    params = []
    if group:
        q += " AND w.group_name=?"
        params.append(group)
    if day:
        q += " AND (wr.experiment_day=? OR wr.experiment_day IS NULL)"
        params.append(day)
    q += " ORDER BY r.rat_id, w.wound_position, wr.experiment_day"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def backup_database() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bp = os.path.join(EXPORT_DIR, f"backup_{ts}.db")
    shutil.copy2(DB_PATH, bp)
    return bp


def is_initialized() -> bool:
    conn = get_conn()
    cnt = conn.execute("SELECT COUNT(*) as cnt FROM rats").fetchone()
    conn.close()
    return cnt["cnt"] > 0
