"""IT 资产管理 MVP — 数据模型 (SQLite + 原生 SQL)"""
import sqlite3
from datetime import datetime, date
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
"""
