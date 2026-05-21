"""IT 资产管理 MVP — 数据模型 (SQLite + 原生 SQL)"""
import sqlite3
from datetime import date
from contextlib import contextmanager

# ---- 分类缩写映射 (用于 asset_tag 生成) ----
CATEGORY_PREFIX = {
    "computer": "PC",
    "monitor": "MON",
    "phone": "PH",
    "tablet": "TAB",
    "printer": "PRN",
    "server": "SRV",
    "network": "NET",
    "firewall": "FW",
    "switch": "SW",
}

# 分类显示名
CATEGORY_NAMES = {
    "computer": "电脑", "monitor": "显示器", "phone": "手机",
    "tablet": "平板", "printer": "打印机", "server": "服务器",
    "network": "网络设备", "firewall": "防火墙", "switch": "交换机",
}

# 分类图标
CATEGORY_ICONS = {
    "computer": "💻", "monitor": "🖥️", "phone": "📱", "tablet": "📋",
    "printer": "🖨️", "server": "🗄️", "network": "🌐", "firewall": "🛡️",
    "switch": "🔀",
}

# 分类颜色
CATEGORY_COLORS = {
    "computer": "#2563eb", "monitor": "#7c3aed", "phone": "#059669",
    "tablet": "#d97706", "printer": "#dc2626", "server": "#475569",
    "network": "#0891b2", "firewall": "#be185d", "switch": "#65a30d",
}

VALID_CATEGORIES = list(CATEGORY_PREFIX.keys())
VALID_STATUSES = ["in_stock", "assigned", "maintenance", "scrapped"]
VALID_EVENT_TYPES = [
    "stock_in", "assign", "return", "transfer",
    "maintenance_start", "maintenance_end", "scrap", "label_print",
]
VALID_MAINTENANCE_STATUSES = ["pending", "in_progress", "resolved"]
VALID_APPLICATION_STATUSES = ["pending", "approved", "rejected", "fulfilled"]
VALID_ROLES = ["admin", "employee"]

# 状态转换表: {current_status: [allowed_events]}
STATE_TRANSITIONS = {
    "in_stock": ["stock_in", "assign", "scrap"],
    "assigned": ["return", "transfer", "maintenance_start", "scrap"],
    "maintenance": ["maintenance_end", "scrap"],
    "scrapped": [],
}

# 事件 → 目标状态
EVENT_TO_STATUS = {
    "stock_in": "in_stock",
    "assign": "assigned",
    "return": "in_stock",
    "transfer": "assigned",
    "maintenance_start": "maintenance",
    "maintenance_end": None,  # 取决于 return_to_stock 参数
    "scrap": "scrapped",
    "label_print": None,  # 状态不变
}

# 标签字段可选值
LABEL_FIELD_OPTIONS = {
    "name": "名称",
    "serial_number": "序列号",
    "holder": "持有人",
    "location": "位置",
    "brand": "品牌",
    "model": "型号",
}

LABEL_FIELDS_DEFAULT = ["name"]


def get_categories_meta():
    """返回分类元数据列表，供 API 和模板统一使用"""
    result = []
    for cat in VALID_CATEGORIES:
        result.append({
            "key": cat,
            "name": CATEGORY_NAMES.get(cat, cat),
            "prefix": CATEGORY_PREFIX.get(cat, "IT"),
            "icon": CATEGORY_ICONS.get(cat, ""),
            "color": CATEGORY_COLORS.get(cat, "#64748b"),
        })
    return result


class Database:
    """SQLite 数据库操作封装"""

    def __init__(self, db_path="it_asset.db"):
        self.db_path = db_path

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        """初始化数据库表结构"""
        with self.get_conn() as conn:
            conn.executescript(SCHEMA)

    def upgrade_db(self):
        """幂等升级旧库：只补齐历史 schema 缺失项，可重复执行。"""
        with self.get_conn() as conn:
            conn.executescript(LEGACY_MIGRATION_SCHEMA)
            # 新增列（幂等：先检查是否存在）
            cols = [r[1] for r in conn.execute("PRAGMA table_info(asset)").fetchall()]
            if "warranty_date" not in cols:
                conn.execute("ALTER TABLE asset ADD COLUMN warranty_date DATE")
            # 迁移明文密码
            self._upgrade_passwords(conn)

    def _upgrade_passwords(self, conn):
        """将明文密码迁移为哈希"""
        from werkzeug.security import generate_password_hash
        rows = conn.execute('SELECT id, password_hash FROM "user"').fetchall()
        for row in rows:
            raw = row["password_hash"]
            if raw and "$" not in raw:
                conn.execute(
                    'UPDATE "user" SET password_hash = ? WHERE id = ?',
                    (generate_password_hash(raw), row["id"]),
                )

    def generate_asset_tag(self, conn, category):
        """生成 asset_tag: {分类缩写}-{年份}-{4位序号}"""
        prefix = CATEGORY_PREFIX.get(category, "IT")
        year = date.today().year
        tag_prefix = f"{prefix}-{year}-"

        row = conn.execute(
            "SELECT asset_tag FROM asset WHERE asset_tag LIKE ? ORDER BY asset_tag DESC LIMIT 1",
            (tag_prefix + "%",),
        ).fetchone()

        if row:
            last_num = int(row["asset_tag"].split("-")[-1])
            next_num = last_num + 1
        else:
            next_num = 1

        return f"{tag_prefix}{next_num:04d}"

    # ---- 通用配置读写 ----

    def get_config(self, key, default=None):
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM app_config WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def set_config(self, key, value, conn=None):
        """写入配置；传入 conn 时加入调用方事务，否则自开事务。"""
        if conn is not None:
            conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                (key, value),
            )
            return
        with self.get_conn() as own_conn:
            own_conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                (key, value),
            )


def log_activity(conn, user_id, action, target_type=None, target_id=None, detail=None):
    """记录关键操作，在已有 conn 中执行"""
    conn.execute(
        """INSERT INTO activity_log (user_id, action, target_type, target_id, detail)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, action, target_type, target_id, detail),
    )


SCHEMA = """
CREATE TABLE IF NOT EXISTS "user" (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    department      TEXT,
    phone           TEXT,
    email           TEXT,
    role            TEXT NOT NULL DEFAULT 'employee',
    password_hash   TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asset (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_tag           TEXT UNIQUE NOT NULL,
    name                TEXT NOT NULL,
    category            TEXT NOT NULL,
    brand               TEXT,
    model               TEXT,
    serial_number       TEXT UNIQUE,
    status              TEXT NOT NULL DEFAULT 'in_stock',
    current_holder_id   INTEGER REFERENCES user(id),
    location            TEXT,
    purchase_date       DATE,
    purchase_price      REAL,
    warranty_date       DATE,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lifecycle_event (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES asset(id),
    event_type      TEXT NOT NULL,
    operator_id     INTEGER NOT NULL REFERENCES user(id),
    target_user_id  INTEGER REFERENCES user(id),
    from_location   TEXT,
    to_location     TEXT,
    notes           TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS maintenance_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES asset(id),
    reported_by     INTEGER NOT NULL REFERENCES user(id),
    description     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    cost            REAL,
    repair_notes    TEXT,
    resolved_at     DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asset_application (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id    INTEGER NOT NULL REFERENCES user(id),
    asset_category  TEXT,
    reason          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    admin_id        INTEGER REFERENCES user(id),
    admin_notes     TEXT,
    approved_at     DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    action          TEXT NOT NULL,
    target_type     TEXT,
    target_id       INTEGER,
    detail          TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_config (
    key             TEXT PRIMARY KEY,
    value           TEXT
);
"""

LEGACY_MIGRATION_SCHEMA = """
-- Legacy MVP databases predated activity logging and app-level settings.
-- Fresh installs get these tables from SCHEMA above; this block is only
-- for idempotently filling gaps in existing SQLite files.
CREATE TABLE IF NOT EXISTS activity_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    action          TEXT NOT NULL,
    target_type     TEXT,
    target_id       INTEGER,
    detail          TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_config (
    key             TEXT PRIMARY KEY,
    value           TEXT
);
"""
