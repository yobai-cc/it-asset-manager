"""IT 资产管理 MVP — 自动化测试

覆盖：资产 CRUD、生命周期事件、维修记录、申请流程、标签/二维码生成
"""
import os
import sys
import tempfile
import subprocess
import pytest

# 确保项目目录在 path 中
sys.path.insert(0, os.path.dirname(__file__))

from models import Database


LEGACY_MVP_SCHEMA = """
CREATE TABLE "user" (
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

CREATE TABLE asset (
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

CREATE TABLE lifecycle_event (
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

CREATE TABLE maintenance_record (
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

CREATE TABLE asset_application (
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


# ---- Fixtures ----

@pytest.fixture
def db():
    """每个测试一个临时数据库"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    database.init_db()
    database.upgrade_db()
    yield database
    os.unlink(path)


@pytest.fixture
def legacy_mvp_db():
    """旧 MVP 数据库：缺少 warranty_date、activity_log、app_config，密码为明文。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    with database.get_conn() as conn:
        conn.executescript(LEGACY_MVP_SCHEMA)
        conn.execute(
            """INSERT INTO "user" (employee_id, name, department, phone, email, role, password_hash)
               VALUES ('admin', '管理员', 'IT部', '', 'admin@company.com', 'admin', 'admin123')"""
        )
        conn.execute(
            """INSERT INTO "user" (employee_id, name, department, phone, email, role, password_hash)
               VALUES ('emp001', '张三', '研发部', '13800000001', 'zhangsan@company.com', 'employee', 'emp001')"""
        )
        conn.execute(
            """INSERT INTO asset (asset_tag, name, category, brand, model, serial_number,
               status, current_holder_id, location, purchase_date, purchase_price, notes)
               VALUES ('PC-2026-0001', 'Legacy PC', 'computer', 'Lenovo', 'T14s',
               'LEGACY-SN-001', 'assigned', 2, '工位A-101', '2026-01-15', 6999.0, '旧库资产')"""
        )
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, target_user_id,
               from_location, to_location, notes)
               VALUES (1, 'assign', 1, 2, '仓库', '工位A-101', '旧库分配记录')"""
        )
    yield database
    os.unlink(path)


def configure_test_server(database, monkeypatch):
    os.environ["DB_PATH"] = database.db_path
    monkeypatch.setenv("DB_PATH", database.db_path)

    import importlib
    import server as srv
    importlib.reload(srv)
    srv.DB_PATH = database.db_path
    srv.app.config["TESTING"] = True
    srv.app.config["SECRET_KEY"] = "test-secret"
    return srv


@pytest.fixture
def app_client(db, monkeypatch):
    """Flask 测试客户端"""
    srv = configure_test_server(db, monkeypatch)

    with srv.app.test_client() as client:
        yield client


def seed_test_data(db):
    """插入测试基础数据"""
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO "user" (employee_id, name, department, role, password_hash)
               VALUES ('admin', '管理员', 'IT部', 'admin', 'admin123')"""
        )
        conn.execute(
            """INSERT INTO "user" (employee_id, name, department, role, password_hash)
               VALUES ('emp001', '张三', '研发部', 'employee', 'emp001')"""
        )
        conn.execute(
            """INSERT INTO "user" (employee_id, name, department, role, password_hash)
               VALUES ('emp002', '李四', '市场部', 'employee', 'emp002')"""
        )


def login_admin(client):
    """以管理员身份登录"""
    return client.post("/api/login", json={"employee_id": "admin", "password": "admin123"})


def login_employee(client, emp_id="emp001"):
    """以员工身份登录"""
    return client.post("/api/login", json={"employee_id": emp_id, "password": emp_id})


# ---- 模型层测试 ----

class TestModels:
    def test_init_db_creates_tables(self, db):
        """数据库初始化应创建所有表"""
        with db.get_conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()]
        assert "asset" in tables
        assert "user" in tables
        assert "lifecycle_event" in tables
        assert "maintenance_record" in tables
        assert "asset_application" in tables

    def test_init_db_schema_is_complete_without_upgrade(self):
        """全新安装只执行 init_db() 就应得到当前完整结构。"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            database = Database(path)
            database.init_db()
            with database.get_conn() as conn:
                asset_cols = [r[1] for r in conn.execute("PRAGMA table_info(asset)").fetchall()]
                tables = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()]
            assert "warranty_date" in asset_cols
            assert "activity_log" in tables
            assert "app_config" in tables
        finally:
            os.unlink(path)

    def test_generate_asset_tag_first(self, db):
        """第一个资产标签应从 0001 开始"""
        with db.get_conn() as conn:
            tag = db.generate_asset_tag(conn, "computer")
        assert tag.startswith("PC-")
        assert tag.endswith("-0001")

    def test_generate_asset_tag_sequential(self, db):
        """后续标签应递增"""
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO asset (asset_tag, name, category, status) VALUES (?, ?, ?, ?)",
                ("PC-2026-0001", "test", "computer", "in_stock"),
            )
            tag = db.generate_asset_tag(conn, "computer")
        assert tag.endswith("-0002")

    def test_generate_asset_tag_different_categories(self, db):
        """不同分类应有不同前缀"""
        with db.get_conn() as conn:
            t1 = db.generate_asset_tag(conn, "computer")
            t2 = db.generate_asset_tag(conn, "monitor")
        assert t1.startswith("PC-")
        assert t2.startswith("MON-")


# ---- API 认证测试 ----

class TestAuth:
    def test_login_success(self, app_client, db):
        seed_test_data(db)
        res = login_admin(app_client)
        assert res.status_code == 200
        data = res.get_json()
        assert data["user"]["role"] == "admin"
        assert data["user"]["name"] == "管理员"

    def test_login_wrong_password(self, app_client, db):
        seed_test_data(db)
        res = app_client.post("/api/login", json={"employee_id": "admin", "password": "wrong"})
        assert res.status_code == 401

    def test_login_nonexistent_user(self, app_client, db):
        seed_test_data(db)
        res = app_client.post("/api/login", json={"employee_id": "nobody", "password": "x"})
        assert res.status_code == 401

    def test_me_without_login(self, app_client, db):
        seed_test_data(db)
        res = app_client.get("/api/me")
        assert res.status_code == 401

    def test_me_with_login(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/me")
        assert res.status_code == 200
        assert res.get_json()["user"]["role"] == "admin"


# ---- 资产 CRUD 测试 ----

class TestAssetCRUD:
    def test_create_asset(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={
            "name": "ThinkPad T14s", "category": "computer",
            "brand": "Lenovo", "model": "T14s", "serial_number": "SN-001",
            "location": "仓库", "purchase_price": 6999,
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data["asset_tag"].startswith("PC-")
        assert data["status"] == "in_stock"
        assert data["name"] == "ThinkPad T14s"

    def test_create_asset_generates_stock_in_event(self, app_client, db):
        """创建资产应自动生成 stock_in 生命周期事件"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={
            "name": "Test PC", "category": "computer",
        })
        asset_id = res.get_json()["id"]
        res = app_client.get(f"/api/assets/{asset_id}")
        events = res.get_json()["events"]
        assert len(events) == 1
        assert events[0]["event_type"] == "stock_in"

    def test_create_asset_auto_tag(self, app_client, db):
        """资产标签应自动生成"""
        seed_test_data(db)
        login_admin(app_client)
        res1 = app_client.post("/api/assets", json={"name": "PC1", "category": "computer"})
        res2 = app_client.post("/api/assets", json={"name": "PC2", "category": "computer"})
        tag1 = res1.get_json()["asset_tag"]
        tag2 = res2.get_json()["asset_tag"]
        assert tag1 != tag2

    def test_list_assets(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/assets", json={"name": "PC1", "category": "computer"})
        res = app_client.get("/api/assets")
        assert res.status_code == 200
        data = res.get_json()
        assert data["total"] >= 1
        assert len(data["assets"]) >= 1

    def test_list_assets_filter_category(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/assets", json={"name": "PC1", "category": "computer"})
        app_client.post("/api/assets", json={"name": "Mon1", "category": "monitor"})
        res = app_client.get("/api/assets?category=computer")
        data = res.get_json()
        assert all(a["category"] == "computer" for a in data["assets"])

    def test_list_assets_search(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/assets", json={"name": "ThinkPad T14s", "category": "computer"})
        res = app_client.get("/api/assets?search=ThinkPad")
        data = res.get_json()
        assert data["total"] >= 1

    def test_get_asset_detail(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={"name": "Test PC", "category": "computer"})
        aid = create_res.get_json()["id"]
        res = app_client.get(f"/api/assets/{aid}")
        assert res.status_code == 200
        data = res.get_json()
        assert data["name"] == "Test PC"
        assert "events" in data
        assert "maintenance_records" in data

    def test_update_asset(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={"name": "Test PC", "category": "computer"})
        aid = create_res.get_json()["id"]
        res = app_client.put(f"/api/assets/{aid}", json={"name": "Updated PC", "brand": "Lenovo"})
        assert res.status_code == 200
        assert res.get_json()["name"] == "Updated PC"

    def test_delete_asset_in_stock(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={"name": "Test PC", "category": "computer"})
        aid = create_res.get_json()["id"]
        res = app_client.delete(f"/api/assets/{aid}")
        assert res.status_code == 200

    def test_delete_asset_assigned_fails(self, app_client, db):
        """不能删除已分配的资产"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={"name": "Test PC", "category": "computer"})
        aid = create_res.get_json()["id"]
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        res = app_client.delete(f"/api/assets/{aid}")
        assert res.status_code == 400

    def test_create_asset_missing_field(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={"name": "Test"})
        assert res.status_code == 400

    def test_create_requires_admin(self, app_client, db):
        seed_test_data(db)
        login_employee(app_client)
        res = app_client.post("/api/assets", json={"name": "Test", "category": "computer"})
        assert res.status_code == 403


# ---- 生命周期操作测试 ----

class TestLifecycle:
    def _create_and_login(self, client, db):
        seed_test_data(db)
        login_admin(client)
        res = client.post("/api/assets", json={"name": "Test PC", "category": "computer"})
        return res.get_json()["id"]

    def test_assign_asset(self, app_client, db):
        """AC5: 领用操作 → 状态变 assigned → 持有人更新"""
        aid = self._create_and_login(app_client, db)
        res = app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "assigned"
        assert data["current_holder_id"] == 2

    def test_return_asset(self, app_client, db):
        """AC6: 归还操作 → 状态变 in_stock → 持有人清空"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        res = app_client.post(f"/api/assets/{aid}/return", json={"notes": "归还"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "in_stock"
        assert data["current_holder_id"] is None

    def test_transfer_asset(self, app_client, db):
        """AC7: 转移操作 → 持有人变更 (状态仍 assigned)"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        res = app_client.post(f"/api/assets/{aid}/transfer", json={"target_user_id": 3})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "assigned"
        assert data["current_holder_id"] == 3

    def test_maintenance_start(self, app_client, db):
        """AC8: 维修操作 → 状态变 maintenance → 维修记录生成"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        res = app_client.post(f"/api/assets/{aid}/maintenance", json={"description": "键盘故障"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "maintenance"
        assert "maintenance_record_id" in data

    def test_maintenance_resolve_return_to_user(self, app_client, db):
        """AC9: 维修完成 → 回到原持有人"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        res = app_client.post(f"/api/assets/{aid}/maintenance", json={"description": "键盘故障"})
        record_id = res.get_json()["maintenance_record_id"]
        res = app_client.post(
            f"/api/assets/{aid}/maintenance/{record_id}/resolve",
            json={"repair_notes": "已更换键盘", "return_to_stock": False},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "assigned"
        assert data["current_holder_id"] == 2

    def test_maintenance_resolve_return_to_stock(self, app_client, db):
        """AC9: 维修完成 → 归还库存"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        res = app_client.post(f"/api/assets/{aid}/maintenance", json={"description": "故障"})
        record_id = res.get_json()["maintenance_record_id"]
        res = app_client.post(
            f"/api/assets/{aid}/maintenance/{record_id}/resolve",
            json={"return_to_stock": True},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "in_stock"
        assert data["current_holder_id"] is None

    def test_scrap_asset(self, app_client, db):
        """AC10: 报废 → 状态变 scrapped (终态)"""
        aid = self._create_and_login(app_client, db)
        res = app_client.post(f"/api/assets/{aid}/scrap", json={"notes": "报废原因"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "scrapped"

    def test_scrap_is_terminal(self, app_client, db):
        """报废是终态，不可再操作"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/scrap", json={"notes": "报废"})
        res = app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        assert res.status_code == 400

    def test_invalid_transition(self, app_client, db):
        """不允许非法状态转换：in_stock → return"""
        aid = self._create_and_login(app_client, db)
        res = app_client.post(f"/api/assets/{aid}/return", json={"notes": "非法"})
        assert res.status_code == 400

    def test_lifecycle_events_recorded(self, app_client, db):
        """每次操作都应记录生命周期事件"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        app_client.post(f"/api/assets/{aid}/return", json={"notes": "归还"})
        res = app_client.get(f"/api/assets/{aid}/events")
        events = res.get_json()["events"]
        event_types = [e["event_type"] for e in events]
        assert "stock_in" in event_types
        assert "assign" in event_types
        assert "return" in event_types


# ---- 维修记录测试 ----

class TestMaintenance:
    def test_maintenance_list(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = res.get_json()["id"]
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        app_client.post(f"/api/assets/{aid}/maintenance", json={"description": "故障"})
        res = app_client.get("/api/maintenance")
        data = res.get_json()
        assert len(data["records"]) >= 1

    def test_maintenance_filter_status(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/maintenance?status=resolved")
        data = res.get_json()
        assert all(r["status"] == "resolved" for r in data["records"])


# ---- 资产申请测试 ----

class TestApplications:
    def test_employee_submit_application(self, app_client, db):
        """AC13: 员工提交申请"""
        seed_test_data(db)
        login_employee(app_client)
        res = app_client.post("/api/my/applications", json={
            "asset_category": "computer", "reason": "开发需要笔记本",
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data["status"] == "pending"
        assert data["reason"] == "开发需要笔记本"

    def test_admin_sees_applications(self, app_client, db):
        """AC13: admin 能看到申请"""
        seed_test_data(db)
        login_employee(app_client)
        app_client.post("/api/my/applications", json={
            "asset_category": "computer", "reason": "需要",
        })
        login_admin(app_client)
        res = app_client.get("/api/applications")
        data = res.get_json()
        assert len(data["applications"]) >= 1

    def test_admin_approve_application(self, app_client, db):
        """AC13: admin 批准申请"""
        seed_test_data(db)
        login_employee(app_client)
        create_res = app_client.post("/api/my/applications", json={
            "asset_category": "computer", "reason": "需要",
        })
        app_id = create_res.get_json()["id"]
        login_admin(app_client)
        res = app_client.put(f"/api/applications/{app_id}/approve", json={"admin_notes": "批准"})
        assert res.status_code == 200
        assert res.get_json()["status"] == "approved"

    def test_admin_reject_application(self, app_client, db):
        """AC13: admin 驳回申请"""
        seed_test_data(db)
        login_employee(app_client)
        create_res = app_client.post("/api/my/applications", json={
            "reason": "需要",
        })
        app_id = create_res.get_json()["id"]
        login_admin(app_client)
        res = app_client.put(f"/api/applications/{app_id}/reject", json={"admin_notes": "不批"})
        assert res.status_code == 200
        assert res.get_json()["status"] == "rejected"

    def test_cannot_approve_twice(self, app_client, db):
        """不能重复审批"""
        seed_test_data(db)
        login_employee(app_client)
        create_res = app_client.post("/api/my/applications", json={"reason": "需要"})
        app_id = create_res.get_json()["id"]
        login_admin(app_client)
        app_client.put(f"/api/applications/{app_id}/approve", json={})
        res = app_client.put(f"/api/applications/{app_id}/approve", json={})
        assert res.status_code == 400

    def test_employee_my_applications(self, app_client, db):
        seed_test_data(db)
        login_employee(app_client)
        app_client.post("/api/my/applications", json={"reason": "需要"})
        res = app_client.get("/api/my/applications")
        assert res.status_code == 200
        assert len(res.get_json()["applications"]) >= 1


# ---- 员工自助测试 ----

class TestEmployeeSelfService:
    def test_my_assets(self, app_client, db):
        """AC14: 员工查看名下资产"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = res.get_json()["id"]
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        login_employee(app_client)
        res = app_client.get("/api/my/assets")
        assert res.status_code == 200
        assets = res.get_json()["assets"]
        assert any(a["id"] == aid for a in assets)

    def test_my_assets_search(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/assets", json={"name": "ThinkPad", "category": "computer"})
        res = app_client.post("/api/assets", json={"name": "ThinkPad", "category": "computer"})
        aid = res.get_json()["id"]
        app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})

        login_employee(app_client)
        res = app_client.get("/api/my/assets?search=ThinkPad")
        assert len(res.get_json()["assets"]) >= 1


# ---- 标签/二维码测试 ----

class TestLabelAndQR:
    def test_qr_code_generation(self, app_client, db):
        """AC11: 二维码生成"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = res.get_json()["id"]
        res = app_client.get(f"/api/assets/{aid}/qr")
        assert res.status_code == 200
        assert res.content_type == "image/png"

    def test_label_page_accessible(self, app_client, db):
        """AC11: 标签页面可访问"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = res.get_json()["id"]
        res = app_client.get(f"/assets/{aid}/label")
        assert res.status_code == 200
        assert b"label-card" in res.data or b"asset" in res.data.lower()

    def test_label_page_requires_admin(self, app_client, db):
        """标签打印页是管理员页面，员工不能访问"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = res.get_json()["id"]
        login_employee(app_client)
        res = app_client.get(f"/assets/{aid}/label")
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]

    def test_batch_labels(self, app_client, db):
        """批量打印标签"""
        seed_test_data(db)
        login_admin(app_client)
        r1 = app_client.post("/api/assets", json={"name": "PC1", "category": "computer"})
        r2 = app_client.post("/api/assets", json={"name": "PC2", "category": "computer"})
        id1, id2 = r1.get_json()["id"], r2.get_json()["id"]
        res = app_client.post("/api/batch-labels", json={"asset_ids": [id1, id2]})
        assert res.status_code == 200
        assert len(res.get_json()["assets"]) == 2

    def test_batch_labels_rejects_missing_assets(self, app_client, db):
        """批量打印标签时任一资产不存在应返回 400，避免静默漏打"""
        seed_test_data(db)
        login_admin(app_client)
        r1 = app_client.post("/api/assets", json={"name": "PC1", "category": "computer"})
        id1 = r1.get_json()["id"]
        res = app_client.post("/api/batch-labels", json={"asset_ids": [id1, 9999]})
        assert res.status_code == 400
        assert "不存在" in res.get_json()["error"]

    def test_logo_upload_saves_file_and_config(self, app_client, db):
        """企业 Logo 上传后应保存文件，并在标签相关接口中返回可访问路径。"""
        import io

        seed_test_data(db)
        login_admin(app_client)
        payload = {"file": (io.BytesIO(b"fake-png-data"), "logo.png")}
        logo = None
        try:
            res = app_client.post("/api/settings/logo", data=payload, content_type="multipart/form-data")
            assert res.status_code == 200
            logo = res.get_json()["logo"]
            assert logo == "/static/uploads/company_logo.png"
            assert db.get_config("company_logo") == logo

            get_res = app_client.get("/api/settings/logo")
            assert get_res.status_code == 200
            assert get_res.get_json()["logo"] == logo
        finally:
            if logo:
                root = os.path.dirname(os.path.dirname(__file__))
                saved = os.path.join(root, logo.lstrip("/"))
                if os.path.exists(saved):
                    os.unlink(saved)

    def test_qr_nonexistent_asset(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/assets/9999/qr")
        assert res.status_code == 404

    def test_public_asset_lookup_returns_minimal_fields(self, app_client, db):
        """公开扫码查找只返回最小字段，不暴露敏感信息"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={"name": "PC", "category": "computer", "brand": "Lenovo", "location": "工位A-01"})
        aid = res.get_json()["id"]

        lookup = app_client.get("/api/public/asset-lookup", query_string={"asset_tag": res.get_json()["asset_tag"]})
        assert lookup.status_code == 200
        data = lookup.get_json()
        assert set(data.keys()) == {"id", "asset_tag", "name", "category", "status"}
        assert data["id"] == aid

        pub = app_client.get(f"/api/public/asset/{aid}")
        assert pub.status_code == 200
        pub_data = pub.get_json()
        assert set(pub_data.keys()) == {"id", "asset_tag", "name", "category", "status"}

    def test_scan_pages_use_public_lookup_and_no_asset_listing_leak(self, app_client, db):
        """扫码页不应把匿名查找导向 /api/assets 列表接口"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = res.get_json()["id"]

        scan_page = app_client.get(f"/scan/{aid}")
        camera_page = app_client.get("/scan")
        assert scan_page.status_code == 200
        assert camera_page.status_code == 200
        assert b"/api/public/asset/" in scan_page.data
        assert b"/api/public/asset-lookup" in camera_page.data
        assert b"/api/assets?search=" not in camera_page.data

    def test_csv_import_rejects_invalid_status(self, app_client, db):
        """CSV 导入遇到非法状态应跳过该行并返回行级错误"""
        import io
        seed_test_data(db)
        login_admin(app_client)
        csv_text = "name,category,status\nBad PC,computer,unknown\nGood PC,computer,in_stock\n"
        data = {
            "file": (io.BytesIO(csv_text.encode("utf-8")), "assets.csv"),
        }
        res = app_client.post("/api/assets/import", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["success"] == 1
        assert payload["total"] == 2
        assert any("无效状态" in err["error"] for err in payload["errors"])
        with db.get_conn() as conn:
            assert conn.execute("SELECT COUNT(*) FROM asset WHERE name = 'Good PC'").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM asset WHERE name = 'Bad PC'").fetchone()[0] == 0


# ---- 新增增强功能回归测试 ----

class TestEnhancementRegressions:
    def test_upgrade_db_migrates_legacy_mvp_schema(self, legacy_mvp_db, monkeypatch):
        """旧 MVP schema 应能补齐结构、保留数据、迁移密码，且迁移后登录可用。"""
        with legacy_mvp_db.get_conn() as conn:
            old_asset_cols = [r[1] for r in conn.execute("PRAGMA table_info(asset)").fetchall()]
            old_tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            assert "warranty_date" not in old_asset_cols
            assert "activity_log" not in old_tables
            assert "app_config" not in old_tables

        legacy_mvp_db.upgrade_db()
        with legacy_mvp_db.get_conn() as conn:
            asset_cols = [r[1] for r in conn.execute("PRAGMA table_info(asset)").fetchall()]
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            user = conn.execute(
                'SELECT * FROM "user" WHERE employee_id = ?', ("admin",)
            ).fetchone()
            asset = conn.execute(
                "SELECT * FROM asset WHERE asset_tag = ?", ("PC-2026-0001",)
            ).fetchone()
            assert "warranty_date" in asset_cols
            assert "activity_log" in tables
            assert "app_config" in tables
            assert conn.execute("SELECT COUNT(*) FROM lifecycle_event").fetchone()[0] == 1
            assert user["password_hash"] != "admin123"
            assert "$" in user["password_hash"]
            assert asset["name"] == "Legacy PC"
            assert asset["warranty_date"] is None

        legacy_mvp_db.upgrade_db()
        with legacy_mvp_db.get_conn() as conn:
            assert [r[1] for r in conn.execute("PRAGMA table_info(asset)").fetchall()].count("warranty_date") == 1
            assert conn.execute("SELECT COUNT(*) FROM asset").fetchone()[0] == 1
            migrated_hash = conn.execute(
                'SELECT password_hash FROM "user" WHERE employee_id = ?', ("admin",)
            ).fetchone()["password_hash"]

        legacy_mvp_db.upgrade_db()
        with legacy_mvp_db.get_conn() as conn:
            assert conn.execute(
                'SELECT password_hash FROM "user" WHERE employee_id = ?', ("admin",)
            ).fetchone()["password_hash"] == migrated_hash

        srv = configure_test_server(legacy_mvp_db, monkeypatch)
        with srv.app.test_client() as client:
            res = client.post("/api/login", json={"employee_id": "admin", "password": "admin123"})
            assert res.status_code == 200
            assert res.get_json()["user"]["role"] == "admin"
            assert client.get("/api/me").status_code == 200

    def test_init_db_script_initializes_fresh_database_with_seed_data(self):
        """init_db.py 新装初始化应包含增强字段/表，不因种子数据写新字段失败"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(path)
        try:
            res = subprocess.run(
                [sys.executable, "init_db.py", path],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert res.returncode == 0, res.stderr
            database = Database(path)
            with database.get_conn() as conn:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(asset)").fetchall()]
                assert "warranty_date" in cols
                assert conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0] >= 0
                assert conn.execute("SELECT COUNT(*) FROM asset").fetchone()[0] == 10
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_upgrade_db_is_idempotent_and_plaintext_passwords_migrate_once(self, db):
        """upgrade_db 可重复执行，明文密码迁移后仍可登录且不会二次哈希"""
        seed_test_data(db)
        db.upgrade_db()
        with db.get_conn() as conn:
            first_hash = conn.execute(
                'SELECT password_hash FROM "user" WHERE employee_id = ?', ("admin",)
            ).fetchone()["password_hash"]
        assert first_hash != "admin123"
        assert "$" in first_hash

        db.upgrade_db()
        with db.get_conn() as conn:
            second_hash = conn.execute(
                'SELECT password_hash FROM "user" WHERE employee_id = ?', ("admin",)
            ).fetchone()["password_hash"]
        assert second_hash == first_hash

    def test_label_settings_get_uses_default_when_stored_json_is_invalid(self, app_client, db):
        seed_test_data(db)
        db.set_config("label_fields", "not json")
        res = app_client.get("/api/settings/label")
        assert res.status_code == 200
        assert res.get_json()["fields"] == ["name"]

    def test_asset_and_activity_pagination_rejects_non_numeric_values(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        assert app_client.get("/api/assets?page=abc").status_code == 400
        assert app_client.get("/api/activity?limit=abc").status_code == 400

    def test_settings_updates_write_config_and_activity_in_same_transaction(self, app_client, db, monkeypatch):
        """设置写入与 activity_log 应同事务；日志失败时配置不应被提前提交"""
        import server as srv

        seed_test_data(db)
        login_admin(app_client)

        def fail_log_activity(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(srv, "log_activity", fail_log_activity)
        with pytest.raises(RuntimeError):
            app_client.put("/api/settings/qr-base-url", json={"url": "http://example.test"})

        assert db.get_config("qr_base_url") is None

    def test_assets_export_content_type_has_single_charset(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/assets", json={"name": "PC", "category": "computer", "warranty_date": "2027-01-01"})
        res = app_client.get("/api/assets/export")
        assert res.status_code == 200
        content_type = res.headers["Content-Type"].lower()
        assert content_type.count("charset") == 1
        assert res.data.startswith("\ufeff".encode("utf-8"))
        assert b"warranty_date" in res.data


# ---- 统计 API 测试 ----

class TestStats:
    def test_stats(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/assets", json={"name": "PC1", "category": "computer"})
        app_client.post("/api/assets", json={"name": "Mon1", "category": "monitor"})
        res = app_client.get("/api/stats")
        assert res.status_code == 200
        data = res.get_json()
        assert data["total"] == 2
        assert data["in_stock"] == 2
        assert "by_category" in data
        assert "recent_events" in data


# ---- 集成：完整生命周期端到端 ----

class TestFullLifecycle:
    def test_complete_lifecycle(self, app_client, db):
        """完整生命周期: 入库 → 分配 → 归还 → 再分配 → 送修 → 完成 → 报废"""
        seed_test_data(db)
        login_admin(app_client)

        # 创建 (自动 stock_in)
        r = app_client.post("/api/assets", json={"name": "Test PC", "category": "computer"})
        aid = r.get_json()["id"]
        assert r.get_json()["status"] == "in_stock"

        # 分配
        r = app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 2})
        assert r.get_json()["status"] == "assigned"

        # 归还
        r = app_client.post(f"/api/assets/{aid}/return", json={"notes": "归还"})
        assert r.get_json()["status"] == "in_stock"

        # 再分配
        r = app_client.post(f"/api/assets/{aid}/assign", json={"target_user_id": 3})
        assert r.get_json()["status"] == "assigned"
        assert r.get_json()["current_holder_id"] == 3

        # 转移
        r = app_client.post(f"/api/assets/{aid}/transfer", json={"target_user_id": 2})
        assert r.get_json()["current_holder_id"] == 2

        # 送修
        r = app_client.post(f"/api/assets/{aid}/maintenance", json={"description": "故障"})
        assert r.get_json()["status"] == "maintenance"
        record_id = r.get_json()["maintenance_record_id"]

        # 维修完成 (回原持有人)
        r = app_client.post(
            f"/api/assets/{aid}/maintenance/{record_id}/resolve",
            json={"repair_notes": "已修", "return_to_stock": False},
        )
        assert r.get_json()["status"] == "assigned"

        # 报废
        r = app_client.post(f"/api/assets/{aid}/scrap", json={"notes": "老化报废"})
        assert r.get_json()["status"] == "scrapped"

        # 验证事件时间线
        r = app_client.get(f"/api/assets/{aid}/events")
        events = r.get_json()["events"]
        event_types = [e["event_type"] for e in events]
        assert event_types == [
            "stock_in", "assign", "return", "assign", "transfer",
            "maintenance_start", "maintenance_end", "scrap",
        ]
