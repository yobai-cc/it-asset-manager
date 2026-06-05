"""IT 资产管理 MVP — 自动化测试

覆盖：资产 CRUD、生命周期事件、维修记录、申请流程、标签/二维码生成
"""
import os
import sys
import tempfile
import subprocess
import pytest
from datetime import date, timedelta

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
        # 员工
        conn.execute("INSERT INTO employee (name, department) VALUES ('管理员', 'IT部')")
        conn.execute("INSERT INTO employee (name, department) VALUES ('张三', '研发部')")
        conn.execute("INSERT INTO employee (name, department) VALUES ('李四', '市场部')")

        # 用户
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
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
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
        res = app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "assigned"
        assert data["current_holder_id"] == 2

    def test_return_asset(self, app_client, db):
        """AC6: 归还操作 → 状态变 in_stock → 持有人清空"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        res = app_client.post(f"/api/assets/{aid}/return", json={"notes": "归还"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "in_stock"
        assert data["current_holder_id"] is None

    def test_transfer_asset(self, app_client, db):
        """AC7: 转移操作 → 持有人变更 (状态仍 assigned)"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        res = app_client.post(f"/api/assets/{aid}/transfer", json={"target_employee_id": 3})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "assigned"
        assert data["current_holder_id"] == 3

    def test_maintenance_start(self, app_client, db):
        """AC8: 维修操作 → 状态变 maintenance → 维修记录生成"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        res = app_client.post(f"/api/assets/{aid}/maintenance", json={"description": "键盘故障"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "maintenance"
        assert "maintenance_record_id" in data

    def test_maintenance_resolve_return_to_user(self, app_client, db):
        """AC9: 维修完成 → 回到原持有人"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
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
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
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
        res = app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        assert res.status_code == 400

    def test_invalid_transition(self, app_client, db):
        """不允许非法状态转换：in_stock → return"""
        aid = self._create_and_login(app_client, db)
        res = app_client.post(f"/api/assets/{aid}/return", json={"notes": "非法"})
        assert res.status_code == 400

    def test_lifecycle_events_recorded(self, app_client, db):
        """每次操作都应记录生命周期事件"""
        aid = self._create_and_login(app_client, db)
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
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
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
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
    def test_my_assets_unlinked_system_user_has_no_roster_assets(self, app_client, db):
        """普通员工不再默认登录系统；未绑定花名册的系统用户不返回资产。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = res.get_json()["id"]
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        login_employee(app_client)
        res = app_client.get("/api/my/assets")
        assert res.status_code == 200
        assets = res.get_json()["assets"]
        assert all(a["id"] != aid for a in assets)

    def test_my_assets_search_unlinked_user_returns_empty(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/assets", json={"name": "ThinkPad", "category": "computer"})
        res = app_client.post("/api/assets", json={"name": "ThinkPad", "category": "computer"})
        aid = res.get_json()["id"]
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})

        login_employee(app_client)
        res = app_client.get("/api/my/assets?search=ThinkPad")
        assert res.get_json()["assets"] == []

    def test_employee_list_hides_inactive_by_default(self, app_client, db):
        """员工列表默认只显示在职花名册，停用员工需显式请求 inactive/all。"""
        seed_test_data(db)
        login_admin(app_client)
        app_client.put("/api/employees/2", json={"name": "张三", "department": "研发部", "status": "inactive"})
        res = app_client.get("/api/employees")
        names = [e["name"] for e in res.get_json()["employees"]]
        assert "张三" not in names
        inactive = app_client.get("/api/employees", query_string={"status": "inactive"})
        assert any(e["name"] == "张三" for e in inactive.get_json()["employees"])


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
                    try:
                        os.unlink(saved)
                    except PermissionError:
                        pass

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
        assert b"location.href = decodedText" in camera_page.data
        assert b"url.origin !== window.location.origin" in camera_page.data
        assert b"new URL(decodedText, window.location.origin)" in camera_page.data

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

    def test_employee_import_creates_and_updates_intelligently(self, app_client, db):
        """员工导入：system_id 精准更新，姓名+部门唯一匹配更新，其他新增。"""
        import io

        seed_test_data(db)
        login_admin(app_client)
        csv_text = (
            "system_id,name,department,notes\n"
            "2,张三,研发平台,按系统ID更新\n"
            ",李四,市场部,按姓名部门更新\n"
            ",王五,财务部,新增员工\n"
        )
        res = app_client.post(
            "/api/employees/import",
            data={"file": (io.BytesIO(csv_text.encode("utf-8")), "employees.csv")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["created"] == 1
        assert payload["updated"] == 2
        assert payload["errors"] == []
        with db.get_conn() as conn:
            zhang = conn.execute("SELECT * FROM employee WHERE id = 2").fetchone()
            li = conn.execute("SELECT * FROM employee WHERE name = '李四'").fetchone()
            wang = conn.execute("SELECT * FROM employee WHERE name = '王五'").fetchone()
            assert zhang["department"] == "研发平台"
            assert zhang["notes"] == "按系统ID更新"
            assert li["notes"] == "按姓名部门更新"
            assert wang["department"] == "财务部"

    def test_employee_import_rejects_ambiguous_name_department_without_system_id(self, app_client, db):
        """允许重名员工；无 system_id 且姓名+部门重复时不能自动更新。"""
        import io

        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/employees", json={"name": "张三", "department": "研发部"})
        csv_text = "name,department,notes\n张三,研发部,无法判断\n"
        res = app_client.post(
            "/api/employees/import",
            data={"file": (io.BytesIO(csv_text.encode("utf-8")), "employees.csv")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["success"] == 0
        assert "多个员工" in payload["errors"][0]["error"]


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
            employee_cols = [r[1] for r in conn.execute("PRAGMA table_info(employee)").fetchall()]
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            user = conn.execute(
                'SELECT * FROM "user" WHERE employee_id = ?', ("admin",)
            ).fetchone()
            asset = conn.execute(
                "SELECT * FROM asset WHERE asset_tag = ?", ("PC-2026-0001",)
            ).fetchone()
            employee = conn.execute(
                "SELECT * FROM employee WHERE employee_id = ?", ("emp001",)
            ).fetchone()
            event = conn.execute(
                "SELECT * FROM lifecycle_event WHERE asset_id = ?", (asset["id"],)
            ).fetchone()
            employee_indexes = [r[1] for r in conn.execute("PRAGMA index_list(employee)").fetchall()]
            assert "warranty_date" in asset_cols
            assert "employee_id" in employee_cols
            assert "status" in employee_cols
            assert "notes" in employee_cols
            assert "updated_at" in employee_cols
            assert "activity_log" in tables
            assert "app_config" in tables
            assert "idx_employee_employee_id" in employee_indexes
            assert conn.execute("SELECT COUNT(*) FROM lifecycle_event").fetchone()[0] == 1
            assert user["password_hash"] != "admin123"
            assert "$" in user["password_hash"]
            assert asset["name"] == "Legacy PC"
            assert asset["current_holder_id"] == employee["id"]
            assert event["target_employee_id"] == employee["id"]
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
                assert conn.execute("SELECT COUNT(*) FROM asset").fetchone()[0] >= 10
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_init_db_seed_consumables_are_attached_to_printers(self):
        """init_db 种子墨粉不能因硬编码 asset_id 关联到非打印机资产。"""
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
                rows = conn.execute(
                    """SELECT pc.name, a.asset_tag, a.category
                       FROM printer_consumable pc
                       JOIN asset a ON pc.asset_id = a.id"""
                ).fetchall()
            assert rows
            assert all(row["category"] == "printer" for row in rows)
            assert {row["asset_tag"] for row in rows} == {"PRN-2026-0001", "PRN-2026-0002"}
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
        data = res.get_json()
        assert data["fields"] == ["name", "serial_number"]
        assert data["max_fields"] == 3
        assert {"key": "qr", "label": "QR 二维码"} in data["fixed_fields"]
        assert any(option["key"] == "holder" and option["volatile"] for option in data["options"])

    def test_label_settings_update_filters_deduplicates_and_limits_fields(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.put(
            "/api/settings/label",
            json={"fields": ["name", "serial_number", "brand", "model", "holder", "name", "bad"]},
        )
        assert res.status_code == 200
        assert res.get_json()["fields"] == ["name", "serial_number", "brand"]
        assert res.get_json()["max_fields"] == 3

        res = app_client.put("/api/settings/label", json={"fields": []})
        assert res.status_code == 200
        assert res.get_json()["fields"] == []

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
        r = app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        assert r.get_json()["status"] == "assigned"

        # 归还
        r = app_client.post(f"/api/assets/{aid}/return", json={"notes": "归还"})
        assert r.get_json()["status"] == "in_stock"

        # 再分配
        r = app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 3})
        assert r.get_json()["status"] == "assigned"
        assert r.get_json()["current_holder_id"] == 3

        # 转移
        r = app_client.post(f"/api/assets/{aid}/transfer", json={"target_employee_id": 2})
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


# ---- 打印机耗材管理测试 ----

class TestConsumablesSchema:
    def test_init_db_creates_consumable_table(self, db):
        """新装数据库应包含 printer_consumable 表"""
        with db.get_conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()]
        assert "printer_consumable" in tables

    def test_consumable_table_has_expected_columns(self, db):
        """printer_consumable 表应包含必要列"""
        with db.get_conn() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(printer_consumable)").fetchall()]
        assert "id" in cols
        assert "name" in cols
        assert "type" in cols
        assert "stock" in cols
        assert "threshold" in cols
        assert "asset_id" in cols
        assert "unit" in cols
        assert "color" in cols
        assert "model" in cols
        assert "current_price" in cols
        assert "installed_at" in cols
        assert "notes" in cols
        assert "created_at" in cols

    def test_init_db_creates_consumable_replacement_table(self, db):
        """新装数据库应包含耗材更替历史表"""
        with db.get_conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()]
            cols = [r[1] for r in conn.execute("PRAGMA table_info(consumable_replacement)").fetchall()]
        assert "consumable_replacement" in tables
        for col in [
            "id", "consumable_id", "asset_id_snapshot", "consumable_name_snapshot",
            "old_installed_at", "replaced_at", "usage_days", "price", "daily_cost",
            "new_installed_at", "new_price", "reason", "notes", "created_at",
        ]:
            assert col in cols

    def test_upgrade_db_adds_lightweight_consumable_columns_to_existing_table(self, db):
        """已有耗材表升级后应补齐轻量生命周期字段和更替历史表"""
        with db.get_conn() as conn:
            conn.execute("DROP TABLE printer_consumable")
            conn.execute("""CREATE TABLE printer_consumable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'other',
                stock INTEGER NOT NULL DEFAULT 0,
                threshold INTEGER NOT NULL DEFAULT 0,
                asset_id INTEGER REFERENCES asset(id),
                unit TEXT DEFAULT '个',
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        db.upgrade_db()
        db.upgrade_db()
        with db.get_conn() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(printer_consumable)").fetchall()]
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "color" in cols
        assert "model" in cols
        assert "current_price" in cols
        assert "installed_at" in cols
        assert "consumable_replacement" in tables

    def test_upgrade_db_adds_consumable_table_to_legacy(self, legacy_mvp_db, monkeypatch):
        """旧库升级后应有 printer_consumable 表"""
        legacy_mvp_db.upgrade_db()
        with legacy_mvp_db.get_conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert "printer_consumable" in tables

    def test_upgrade_db_consumable_idempotent(self, legacy_mvp_db):
        """重复升级不应报错"""
        legacy_mvp_db.upgrade_db()
        legacy_mvp_db.upgrade_db()
        with legacy_mvp_db.get_conn() as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert "printer_consumable" in tables


class TestConsumablesAPI:
    def _seed_printer_and_login(self, client, db):
        seed_test_data(db)
        login_admin(client)
        res = client.post("/api/assets", json={
            "name": "HP LaserJet", "category": "printer",
            "brand": "HP", "model": "M404dn",
        })
        return res.get_json()["id"]

    def test_create_consumable(self, app_client, db):
        """管理员可以创建耗材记录"""
        printer_id = self._seed_printer_and_login(app_client, db)
        res = app_client.post("/api/consumables", json={
            "name": "黑色硒鼓", "type": "toner",
            "stock": 5, "threshold": 2,
            "asset_id": printer_id, "unit": "个",
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data["name"] == "黑色硒鼓"
        assert data["type"] == "toner"
        assert data["stock"] == 5
        assert data["color"] is None
        assert data["current_price"] is None
        assert data["installed_at"] is None

    def test_create_consumable_with_lifecycle_fields(self, app_client, db):
        """耗材项可记录当前这支的颜色、型号、价格和安装日期"""
        printer_id = self._seed_printer_and_login(app_client, db)
        res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "color": "black", "model": "原装",
            "stock": 1, "threshold": 1, "asset_id": printer_id,
            "current_price": 320.5, "installed_at": "2026-01-01",
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data["color"] == "black"
        assert data["model"] == "原装"
        assert data["current_price"] == 320.5
        assert data["installed_at"] == "2026-01-01"
        assert data["usage_days"] >= 1
        assert data["estimated_daily_cost"] is not None

    def test_create_consumable_without_printer(self, app_client, db):
        """墨粉可以不关联打印机"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "通用黑色墨粉", "type": "toner",
            "stock": 20, "threshold": 5, "unit": "个",
        })
        assert res.status_code == 201
        assert res.get_json()["asset_id"] is None

    def test_create_consumable_auto_generates_name(self, app_client, db):
        """创建耗材不提供 name 时应自动生成"""
        seed_test_data(db)
        login_admin(app_client)
        # 先创建一台打印机资产
        printer_res = app_client.post("/api/assets", json={
            "name": "TestPrinter", "category": "printer", "brand": "HP", "model": "M404",
            "printer_type": "mono",
        })
        pid = printer_res.get_json()["id"]
        res = app_client.post("/api/consumables", json={
            "type": "toner", "stock": 1, "color": "black", "asset_id": pid,
        })
        assert res.status_code == 201
        data = res.get_json()
        assert "TestPrinter" in data["name"]
        assert "黑色" in data["name"]

    def test_create_consumable_requires_admin(self, app_client, db):
        """员工不能创建耗材"""
        seed_test_data(db)
        login_employee(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 1,
        })
        assert res.status_code == 403

    def test_list_consumables(self, app_client, db):
        """管理员可以列出所有墨粉"""
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/consumables", json={"name": "硒鼓", "type": "toner", "stock": 3})
        app_client.post("/api/consumables", json={"name": "备用墨粉", "type": "toner", "stock": 10})
        res = app_client.get("/api/consumables")
        assert res.status_code == 200
        data = res.get_json()
        assert data["total"] == 2
        assert len(data["consumables"]) == 2

    def test_list_consumables_filter_by_type(self, app_client, db):
        """按类型筛选墨粉"""
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/consumables", json={"name": "硒鼓", "type": "toner", "stock": 3})
        app_client.post("/api/consumables", json={"name": "备用墨粉", "type": "toner", "stock": 10})
        res = app_client.get("/api/consumables?type=toner")
        data = res.get_json()
        assert data["total"] == 2
        assert all(c["type"] == "toner" for c in data["consumables"])

    def test_list_consumables_filter_by_asset(self, app_client, db):
        """按关联打印机筛选耗材"""
        printer_id = self._seed_printer_and_login(app_client, db)
        app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 3, "asset_id": printer_id,
        })
        app_client.post("/api/consumables", json={"name": "备用墨粉", "type": "toner", "stock": 10})
        res = app_client.get(f"/api/consumables?asset_id={printer_id}")
        data = res.get_json()
        assert data["total"] == 1
        assert data["consumables"][0]["asset_id"] == printer_id

    def test_list_consumables_rejects_non_numeric_asset_id(self, app_client, db):
        """asset_id 非数字应返回 400，而不是 500"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/consumables?asset_id=abc")
        assert res.status_code == 400
        assert "asset_id" in res.get_json()["error"]

    def test_replace_consumable_creates_history_and_resets_current_cycle(self, app_client, db):
        """更替单个耗材只归档该耗材旧周期，并开启新周期"""
        printer_id = self._seed_printer_and_login(app_client, db)
        start = (date.today() - timedelta(days=10)).isoformat()
        create_res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "color": "black", "model": "原装",
            "stock": 2, "asset_id": printer_id,
            "current_price": 300, "installed_at": start,
        })
        cid = create_res.get_json()["id"]

        res = app_client.post(f"/api/consumables/{cid}/replace", json={
            "replaced_at": date.today().isoformat(),
            "new_installed_at": date.today().isoformat(),
            "new_price": 320,
            "use_stock": True,
            "reason": "用尽",
            "notes": "测试更替",
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["consumable"]["installed_at"] == date.today().isoformat()
        assert data["consumable"]["current_price"] == 320
        assert data["consumable"]["stock"] == 1
        replacement = data["replacement"]
        assert replacement["consumable_id"] == cid
        assert replacement["usage_days"] == 10
        assert replacement["price"] == 300
        assert replacement["daily_cost"] == 30
        assert replacement["new_price"] == 320

    def test_replace_one_of_four_printer_consumables_does_not_affect_siblings(self, app_client, db):
        """同一台打印机多个墨粉独立更替，互不影响"""
        printer_id = self._seed_printer_and_login(app_client, db)
        ids = {}
        for color, name in [("black", "黑粉"), ("cyan", "青粉"), ("magenta", "品红粉"), ("yellow", "黄粉")]:
            res = app_client.post("/api/consumables", json={
                "name": name, "type": "toner", "color": color, "asset_id": printer_id,
                "stock": 1, "current_price": 280, "installed_at": "2026-01-01",
            })
            ids[color] = res.get_json()["id"]
        res = app_client.post(f"/api/consumables/{ids['black']}/replace", json={
            "replaced_at": "2026-01-11", "new_installed_at": "2026-01-11",
            "new_price": 300, "use_stock": False,
        })
        assert res.status_code == 200
        list_res = app_client.get(f"/api/consumables?asset_id={printer_id}")
        by_color = {c["color"]: c for c in list_res.get_json()["consumables"]}
        assert by_color["black"]["installed_at"] == "2026-01-11"
        assert by_color["black"]["current_price"] == 300
        for color in ["cyan", "magenta", "yellow"]:
            assert by_color[color]["installed_at"] == "2026-01-01"
            assert by_color[color]["current_price"] == 280

    def test_replace_consumable_using_stock_below_zero_fails(self, app_client, db):
        """从备用库存取用时库存不足应拒绝"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "黑粉", "type": "toner", "stock": 0,
            "current_price": 300, "installed_at": "2026-01-01",
        })
        cid = create_res.get_json()["id"]
        res = app_client.post(f"/api/consumables/{cid}/replace", json={
            "replaced_at": "2026-01-11", "new_price": 320, "use_stock": True,
        })
        assert res.status_code == 400

    def test_list_consumable_replacement_history(self, app_client, db):
        """可以查看单个耗材的更替历史"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "黑粉", "type": "toner", "stock": 1,
            "current_price": 300, "installed_at": "2026-01-01",
        })
        cid = create_res.get_json()["id"]
        app_client.post(f"/api/consumables/{cid}/replace", json={
            "replaced_at": "2026-01-11", "new_price": 320,
        })
        res = app_client.get(f"/api/consumables/{cid}/replacements")
        assert res.status_code == 200
        data = res.get_json()
        assert data["total"] == 1
        assert data["replacements"][0]["usage_days"] == 10

    def test_get_consumable_detail(self, app_client, db):
        """查看耗材详情"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 3,
            "threshold": 1, "unit": "个", "notes": "备用",
        })
        cid = create_res.get_json()["id"]
        res = app_client.get(f"/api/consumables/{cid}")
        assert res.status_code == 200
        data = res.get_json()
        assert data["name"] == "硒鼓"
        assert data["notes"] == "备用"

    def test_get_consumable_not_found(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/consumables/9999")
        assert res.status_code == 404

    def test_update_consumable(self, app_client, db):
        """更新耗材信息"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 3,
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={
            "stock": 10, "notes": "已补货",
        })
        assert res.status_code == 200
        assert res.get_json()["stock"] == 10
        assert res.get_json()["notes"] == "已补货"

    def test_delete_consumable(self, app_client, db):
        """删除耗材"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 3,
        })
        cid = create_res.get_json()["id"]
        res = app_client.delete(f"/api/consumables/{cid}")
        assert res.status_code == 200
        assert app_client.get(f"/api/consumables/{cid}").status_code == 404

    def test_adjust_stock(self, app_client, db):
        """库存调整：加减库存"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 5,
        })
        cid = create_res.get_json()["id"]
        # 减库存
        res = app_client.post(f"/api/consumables/{cid}/adjust", json={"delta": -2})
        assert res.status_code == 200
        assert res.get_json()["stock"] == 3
        # 加库存
        res = app_client.post(f"/api/consumables/{cid}/adjust", json={"delta": 5})
        assert res.status_code == 200
        assert res.get_json()["stock"] == 8

    def test_adjust_stock_below_zero_fails(self, app_client, db):
        """库存不能低于 0"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 2,
        })
        cid = create_res.get_json()["id"]
        res = app_client.post(f"/api/consumables/{cid}/adjust", json={"delta": -5})
        assert res.status_code == 400

    def test_list_low_stock_consumables(self, app_client, db):
        """低库存耗材查询"""
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 1, "threshold": 2,
        })
        app_client.post("/api/consumables", json={
            "name": "备用墨粉", "type": "toner", "stock": 10, "threshold": 2,
        })
        res = app_client.get("/api/consumables?low_stock=true")
        data = res.get_json()
        assert data["total"] == 1
        assert data["consumables"][0]["name"] == "硒鼓"

    # ---- Blocker 1: Consumable input validation ----

    def test_create_consumable_invalid_type_returns_400(self, app_client, db):
        """创建耗材时无效 type 应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "坏类型", "type": "fire_extinguisher",
        })
        assert res.status_code == 400

    def test_create_consumable_negative_stock_returns_400(self, app_client, db):
        """创建耗材时负库存应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "负库存", "type": "toner", "stock": -1,
        })
        assert res.status_code == 400

    def test_create_consumable_negative_threshold_returns_400(self, app_client, db):
        """创建耗材时负阈值应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "负阈值", "type": "toner", "threshold": -1,
        })
        assert res.status_code == 400

    def test_create_consumable_negative_current_price_returns_400(self, app_client, db):
        """创建耗材时负价格应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "负价格", "type": "toner", "current_price": -10,
        })
        assert res.status_code == 400

    def test_create_consumable_string_current_price_returns_400(self, app_client, db):
        """创建耗材时 current_price='abc' 应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "字符串价格", "type": "toner", "current_price": "abc",
        })
        assert res.status_code == 400

    def test_create_consumable_invalid_installed_at_returns_400(self, app_client, db):
        """创建耗材时无效日期 installed_at 应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "坏日期", "type": "toner", "installed_at": "not-a-date",
        })
        assert res.status_code == 400

    def test_create_consumable_invalid_stock_type_returns_400(self, app_client, db):
        """创建耗材时 stock 为非数字应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "字符串库存", "type": "toner", "stock": "abc",
        })
        assert res.status_code == 400

    def test_update_consumable_invalid_type_returns_400(self, app_client, db):
        """更新耗材时无效 type 应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 3,
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={
            "type": "fire_extinguisher",
        })
        assert res.status_code == 400

    def test_update_consumable_negative_stock_returns_400(self, app_client, db):
        """更新耗材时负库存应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 3,
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={
            "stock": -5,
        })
        assert res.status_code == 400

    def test_update_consumable_negative_current_price_returns_400(self, app_client, db):
        """更新耗材时负价格应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 3,
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={
            "current_price": -100,
        })
        assert res.status_code == 400

    def test_update_consumable_string_current_price_returns_400(self, app_client, db):
        """更新耗材时 current_price='abc' 应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 3,
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={
            "current_price": "abc",
        })
        assert res.status_code == 400

    def test_update_consumable_invalid_installed_at_returns_400(self, app_client, db):
        """更新耗材时无效日期应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 3,
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={
            "installed_at": "bad-date",
        })
        assert res.status_code == 400

    def test_adjust_stock_non_integer_delta_returns_400(self, app_client, db):
        """库存调整时 delta 非整数应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "stock": 5,
        })
        cid = create_res.get_json()["id"]
        res = app_client.post(f"/api/consumables/{cid}/adjust", json={"delta": 1.5})
        assert res.status_code == 400
        res = app_client.post(f"/api/consumables/{cid}/adjust", json={"delta": "abc"})
        assert res.status_code == 400

    def test_replace_consumable_negative_new_price_returns_400(self, app_client, db):
        """更替耗材时负 new_price 应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "黑粉", "type": "toner", "stock": 1,
            "current_price": 300, "installed_at": "2026-01-01",
        })
        cid = create_res.get_json()["id"]
        res = app_client.post(f"/api/consumables/{cid}/replace", json={
            "replaced_at": "2026-01-11", "new_price": -50,
        })
        assert res.status_code == 400

    def test_replace_consumable_string_new_price_returns_400(self, app_client, db):
        """更替耗材时 new_price='abc' 应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "黑粉", "type": "toner", "stock": 1,
            "current_price": 300, "installed_at": "2026-01-01",
        })
        cid = create_res.get_json()["id"]
        res = app_client.post(f"/api/consumables/{cid}/replace", json={
            "replaced_at": "2026-01-11", "new_price": "abc",
        })
        assert res.status_code == 400

    # ---- Blocker 2: Consumable asset_id must be printer ----

    def test_create_consumable_with_non_printer_asset_returns_400(self, app_client, db):
        """绑定耗材到非打印机资产应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        # 创建一个电脑资产
        computer_res = app_client.post("/api/assets", json={
            "name": "ThinkPad", "category": "computer",
        })
        computer_id = computer_res.get_json()["id"]
        res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "asset_id": computer_id,
        })
        assert res.status_code == 400

    def test_create_consumable_with_nonexistent_asset_returns_400(self, app_client, db):
        """绑定耗材到不存在的资产应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "asset_id": 99999,
        })
        assert res.status_code == 400

    def test_update_consumable_with_non_printer_asset_returns_400(self, app_client, db):
        """更新耗材绑定到非打印机资产应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner",
        })
        cid = create_res.get_json()["id"]
        computer_res = app_client.post("/api/assets", json={
            "name": "ThinkPad", "category": "computer",
        })
        computer_id = computer_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={
            "asset_id": computer_id,
        })
        assert res.status_code == 400

    def test_update_consumable_with_nonexistent_asset_returns_400(self, app_client, db):
        """更新耗材绑定到不存在的资产应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner",
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={
            "asset_id": 99999,
        })
        assert res.status_code == 400

    def test_create_consumable_with_printer_asset_succeeds(self, app_client, db):
        """绑定耗材到打印机资产应成功"""
        printer_id = self._seed_printer_and_login(app_client, db)
        res = app_client.post("/api/consumables", json={
            "name": "硒鼓", "type": "toner", "asset_id": printer_id,
        })
        assert res.status_code == 201
        assert res.get_json()["asset_id"] == printer_id

    def test_create_consumable_without_asset_id_succeeds(self, app_client, db):
        """不绑定资产的耗材应能创建"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "通用硒鼓", "type": "toner",
        })
        assert res.status_code == 201

    def test_global_replacements_api(self, app_client, db):
        """GET /api/consumables/replacements 返回全局更换历史"""
        seed_test_data(db)
        login_admin(app_client)
        # 创建打印机 + 墨粉 + 更换记录
        pr = app_client.post("/api/assets", json={
            "name": "TestPrinter", "category": "printer", "brand": "HP", "model": "M404",
            "printer_type": "mono",
        })
        pid = pr.get_json()["id"]
        c = app_client.post("/api/consumables", json={
            "type": "toner", "color": "black", "asset_id": pid,
            "stock": 2, "threshold": 1, "current_price": 300, "installed_at": "2026-01-01",
        })
        cid = c.get_json()["id"]
        app_client.post(f"/api/consumables/{cid}/replace", json={
            "replaced_at": "2026-05-01", "new_price": 310, "reason": "用尽",
        })
        res = app_client.get("/api/consumables/replacements")
        assert res.status_code == 200
        data = res.get_json()
        assert data["total"] >= 1
        assert "replacements" in data
        r = data["replacements"][0]
        assert r["printer_name"] == "TestPrinter"
        assert r["toner_color"] == "black"
        assert r["reason"] == "用尽"

    def test_global_replacements_filter_by_printer(self, app_client, db):
        """全局历史支持按 printer_id 筛选"""
        seed_test_data(db)
        login_admin(app_client)
        pr1 = app_client.post("/api/assets", json={
            "name": "P1", "category": "printer", "printer_type": "mono",
        })
        pr2 = app_client.post("/api/assets", json={
            "name": "P2", "category": "printer", "printer_type": "mono",
        })
        pid1, pid2 = pr1.get_json()["id"], pr2.get_json()["id"]
        c1 = app_client.post("/api/consumables", json={
            "type": "toner", "color": "black", "asset_id": pid1, "current_price": 100, "installed_at": "2026-01-01",
        })
        c2 = app_client.post("/api/consumables", json={
            "type": "toner", "color": "black", "asset_id": pid2, "current_price": 200, "installed_at": "2026-01-01",
        })
        app_client.post(f"/api/consumables/{c1.get_json()['id']}/replace", json={"replaced_at": "2026-05-01"})
        app_client.post(f"/api/consumables/{c2.get_json()['id']}/replace", json={"replaced_at": "2026-05-01"})
        res = app_client.get(f"/api/consumables/replacements?printer_id={pid1}")
        data = res.get_json()
        assert data["total"] == 1
        assert data["replacements"][0]["printer_name"] == "P1"

    def test_cost_summary_api(self, app_client, db):
        """GET /api/consumables/cost-summary 返回成本汇总"""
        seed_test_data(db)
        login_admin(app_client)
        pr = app_client.post("/api/assets", json={
            "name": "CostPrinter", "category": "printer", "printer_type": "mono",
        })
        pid = pr.get_json()["id"]
        c = app_client.post("/api/consumables", json={
            "type": "toner", "color": "black", "asset_id": pid,
            "current_price": 300, "installed_at": "2026-01-01",
        })
        cid = c.get_json()["id"]
        app_client.post(f"/api/consumables/{cid}/replace", json={
            "replaced_at": "2026-04-01", "new_price": 320, "reason": "用尽",
        })
        res = app_client.get("/api/consumables/cost-summary")
        assert res.status_code == 200
        data = res.get_json()
        assert data["total_cost"] > 0
        assert data["total_replacements"] >= 1
        assert len(data["by_printer"]) >= 1
        assert data["by_printer"][0]["printer_name"] == "CostPrinter"


# ---- 管理员用户管理测试 ----

class TestUserManagementAPI:
    def test_admin_can_list_users_with_details(self, app_client, db):
        """管理员获取用户列表应包含详细字段"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/users")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data["users"]) == 3
        # 确认不暴露 password_hash
        for u in data["users"]:
            assert "password_hash" not in u

    def test_admin_can_create_user(self, app_client, db):
        """管理员可以创建用户"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/users", json={
            "employee_id": "emp010",
            "name": "王五",
            "department": "财务部",
            "phone": "13900000010",
            "email": "wangwu@company.com",
            "role": "employee",
            "password": "pass123",
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data["employee_id"] == "emp010"
        assert data["name"] == "王五"
        assert data["role"] == "employee"
        assert "password_hash" not in data

    def test_create_user_hashed_password(self, app_client, db):
        """创建用户后密码应被哈希存储"""
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/users", json={
            "employee_id": "emp010", "name": "王五",
            "role": "employee", "password": "pass123",
        })
        with db.get_conn() as conn:
            row = conn.execute(
                'SELECT password_hash FROM "user" WHERE employee_id = ?', ("emp010",)
            ).fetchone()
        assert row["password_hash"] != "pass123"
        assert "$" in row["password_hash"]

    def test_create_user_does_not_create_employee_record(self, app_client, db):
        """创建登录用户不应自动新增花名册员工。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/users", json={
            "employee_id": "emp_sync",
            "name": "同步员工",
            "department": "运维部",
            "role": "employee",
            "password": "emp_sync",
        })
        assert res.status_code == 201
        employees = app_client.get("/api/employees").get_json()["employees"]
        assert all(e["name"] != "同步员工" for e in employees)

    def test_create_user_duplicate_employee_id_fails(self, app_client, db):
        """重复工号应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/users", json={
            "employee_id": "admin", "name": "重复", "role": "employee", "password": "x",
        })
        assert res.status_code == 400

    def test_create_user_requires_admin(self, app_client, db):
        """员工不能创建用户"""
        seed_test_data(db)
        login_employee(app_client)
        res = app_client.post("/api/users", json={
            "employee_id": "emp010", "name": "王五", "role": "employee", "password": "x",
        })
        assert res.status_code == 403

    def test_create_user_missing_required_fields(self, app_client, db):
        """缺少必填字段应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/users", json={"name": "无工号"})
        assert res.status_code == 400

    def test_admin_can_update_user(self, app_client, db):
        """管理员可以更新用户信息"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.put("/api/users/2", json={
            "department": "测试部", "phone": "13800001111", "email": "new@company.com",
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["department"] == "测试部"
        assert data["phone"] == "13800001111"

    def test_admin_can_set_user_role(self, app_client, db):
        """管理员可以更改用户角色"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.put("/api/users/2", json={"role": "admin"})
        assert res.status_code == 200
        assert res.get_json()["role"] == "admin"

    def test_update_user_invalid_role_fails(self, app_client, db):
        """无效角色应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.put("/api/users/2", json={"role": "superadmin"})
        assert res.status_code == 400

    def test_update_user_not_found(self, app_client, db):
        """更新不存在的用户应返回 404"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.put("/api/users/9999", json={"name": "不存在"})
        assert res.status_code == 404

    def test_admin_can_reset_password(self, app_client, db):
        """管理员可以重置用户密码"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/users/2/reset-password", json={"new_password": "newpass456"})
        assert res.status_code == 200
        # 验证新密码可以登录
        app_client.post("/api/logout")
        login_res = app_client.post("/api/login", json={
            "employee_id": "emp001", "password": "newpass456",
        })
        assert login_res.status_code == 200

    def test_reset_password_requires_admin(self, app_client, db):
        """员工不能重置密码"""
        seed_test_data(db)
        login_employee(app_client)
        res = app_client.post("/api/users/2/reset-password", json={"new_password": "x"})
        assert res.status_code == 403

    def test_reset_password_empty_fails(self, app_client, db):
        """空密码应返回 400"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/users/2/reset-password", json={"new_password": ""})
        assert res.status_code == 400

    def test_delete_user(self, app_client, db):
        """管理员可以删除用户"""
        seed_test_data(db)
        login_admin(app_client)
        # 先创建一个不持有资产的用户
        app_client.post("/api/users", json={
            "employee_id": "emp_del", "name": "待删", "role": "employee", "password": "***",
        })
        users = app_client.get("/api/users").get_json()["users"]
        uid = next(u["id"] for u in users if u["employee_id"] == "emp_del")
        res = app_client.delete(f"/api/users/{uid}")
        assert res.status_code == 200

    def test_delete_user_does_not_depend_on_employee_assets(self, app_client, db):
        """删除系统用户不应受花名册资产约束。"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = create_res.get_json()["id"]
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        res = app_client.delete("/api/users/2")
        assert res.status_code == 200

    def test_delete_employee_requires_stock_transfer(self, app_client, db):
        """停用员工时若持有资产，应提示先转入库房。"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = create_res.get_json()["id"]
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        res = app_client.delete("/api/employees/2")
        assert res.status_code == 400
        assert res.get_json()["requires_asset_transfer"] is True

    def test_delete_employee_moves_assets_to_stock_when_requested(self, app_client, db):
        """停用员工并转库房时，资产应回收入库。"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={"name": "PC", "category": "computer"})
        aid = create_res.get_json()["id"]
        app_client.post(f"/api/assets/{aid}/assign", json={"target_employee_id": 2})
        res = app_client.delete(
            "/api/employees/2",
            json={"move_assets_to_stock": True, "stock_location": "库房"},
        )
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["employee"]["status"] == "inactive"
        assert aid in payload["moved_asset_ids"]
        with db.get_conn() as conn:
            asset = conn.execute("SELECT * FROM asset WHERE id = ?", (aid,)).fetchone()
            assert asset["status"] == "in_stock"
            assert asset["current_holder_id"] is None
            assert asset["location"] == "库房"

    def test_delete_self_fails(self, app_client, db):
        """管理员不能删除自己，避免锁死当前会话"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.delete("/api/users/1")
        assert res.status_code == 400
        assert "自己" in res.get_json()["error"]

    def test_delete_last_admin_fails(self, app_client, db):
        """不能删除系统最后一个管理员"""
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/users", json={
            "employee_id": "admin2", "name": "第二管理员", "role": "admin", "password": "admin2",
        })
        app_client.post("/api/users", json={
            "employee_id": "emp_del", "name": "待删", "role": "employee", "password": "del123",
        })
        users = app_client.get("/api/users").get_json()["users"]
        admin2_id = next(u["id"] for u in users if u["employee_id"] == "admin2")
        emp_del_id = next(u["id"] for u in users if u["employee_id"] == "emp_del")
        assert app_client.delete(f"/api/users/{emp_del_id}").status_code == 200
        assert app_client.delete(f"/api/users/{admin2_id}").status_code == 200
        res = app_client.delete("/api/users/1")
        assert res.status_code == 400
        assert "最后一个管理员" in res.get_json()["error"]

    def test_api_users_response_excludes_password_hash(self, app_client, db):
        """GET /api/users 响应不得包含 password_hash"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/users")
        data = res.get_json()
        for u in data["users"]:
            assert "password_hash" not in u

    # ---- Blocker 3: User role admin lockout protection ----

    def test_admin_cannot_downgrade_self_role(self, app_client, db):
        """管理员不能将自己降级为普通员工"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.put("/api/users/1", json={"role": "employee"})
        assert res.status_code == 400
        assert "自己" in res.get_json()["error"]

    def test_admin_cannot_downgrade_last_admin_role(self, app_client, db):
        """不能将系统唯一管理员降级为普通员工"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.put("/api/users/1", json={"role": "employee"})
        assert res.status_code == 400

    def test_admin_can_downgrade_other_admin_when_multiple_exist(self, app_client, db):
        """多个管理员时可以将其他管理员降级"""
        seed_test_data(db)
        login_admin(app_client)
        # 创建第二个管理员
        app_client.post("/api/users", json={
            "employee_id": "admin2", "name": "第二管理员", "role": "admin", "password": "admin2",
        })
        users = app_client.get("/api/users").get_json()["users"]
        admin2_id = next(u["id"] for u in users if u["employee_id"] == "admin2")
        res = app_client.put(f"/api/users/{admin2_id}", json={"role": "employee"})
        assert res.status_code == 200
        assert res.get_json()["role"] == "employee"

    def test_admin_cannot_downgrade_only_remaining_other_admin(self, app_client, db):
        """只有两个管理员时不能把对方降级（降后只剩自己一个）"""
        seed_test_data(db)
        login_admin(app_client)
        app_client.post("/api/users", json={
            "employee_id": "admin2", "name": "第二管理员", "role": "admin", "password": "admin2",
        })
        users = app_client.get("/api/users").get_json()["users"]
        admin2_id = next(u["id"] for u in users if u["employee_id"] == "admin2")
        # admin2 也是 admin，可以降级因为有 2 个 admin
        # 但如果只有一个 admin 了就不能降
        # 先降级 admin2 为 employee
        res = app_client.put(f"/api/users/{admin2_id}", json={"role": "employee"})
        assert res.status_code == 200
        # 再升回 admin
        res = app_client.put(f"/api/users/{admin2_id}", json={"role": "admin"})
        assert res.status_code == 200
        # 2 个 admin，admin 降级 admin2 没问题
        res = app_client.put(f"/api/users/{admin2_id}", json={"role": "employee"})
        assert res.status_code == 200


# ---- 耗材管理/用户管理页面路由测试 ----

class TestConsumablesPage:
    def test_consumables_page_accessible(self, app_client, db):
        """耗材管理页面对管理员可访问"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        assert b"consumables" in res.data

    def test_consumables_page_requires_admin(self, app_client, db):
        """耗材管理页面需管理员权限"""
        seed_test_data(db)
        login_employee(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]

    def test_consumables_page_has_page_hook(self, app_client, db):
        """耗材管理页面包含 data-page-title 持久钩子"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        assert b'data-page-title="consumables"' in res.data

    def test_consumables_page_has_modal_hooks(self, app_client, db):
        """耗材管理页面包含弹窗持久钩子"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        assert b'data-modal="consumable-form"' in res.data
        assert b'data-modal="adjust-stock"' in res.data

    def test_consumables_page_has_printer_card_list(self, app_client, db):
        """耗材管理页面包含打印机卡片列表区域"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        assert b'data-section="printer-card-list"' in res.data

    def test_consumables_page_has_printer_detail_drawer(self, app_client, db):
        """耗材管理页面包含打印机耗材详情抽屉区域"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        assert b'data-section="printer-detail-drawer"' in res.data

    def test_consumables_page_has_filter_chips(self, app_client, db):
        """耗材管理页面包含筛选标签(all/color/mono/warning)"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        assert b'data-filter="all"' in res.data
        assert b'data-filter="color"' in res.data
        assert b'data-filter="mono"' in res.data
        assert b'data-filter="warning"' in res.data

    def test_consumables_page_injects_printer_data(self, app_client, db):
        """耗材管理页面注入打印机耗材 JSON 数据供 JS 使用"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        assert b'data-printer-consumables-json' in res.data


class TestPrintersConsumablesAPI:
    """打印机耗材聚合 API — 按打印机分组返回耗材数据"""

    def _seed_printers_with_consumables(self, client, db):
        seed_test_data(db)
        login_admin(client)
        # 彩色打印机
        color_res = client.post("/api/assets", json={
            "name": "HP Color LaserJet M479", "category": "printer",
            "brand": "HP", "model": "M479fdw",
        })
        color_id = color_res.get_json()["id"]
        # 黑白打印机
        mono_res = client.post("/api/assets", json={
            "name": "Brother HL-L2325D", "category": "printer",
            "brand": "Brother", "model": "HL-L2325D",
        })
        mono_id = mono_res.get_json()["id"]
        # 标签打印机（不应出现在聚合结果中）
        label_res = client.post("/api/assets", json={
            "name": "Zebra ZD420", "category": "printer",
            "brand": "Zebra", "model": "ZD420",
        })
        label_id = label_res.get_json()["id"]

        # 彩色打印机耗材
        for color_name in ["black", "cyan", "magenta", "yellow"]:
            client.post("/api/consumables", json={
                "name": f"{color_name} toner", "type": "toner",
                "color": color_name, "stock": 5, "threshold": 2,
                "asset_id": color_id, "current_price": 340.0,
                "installed_at": "2026-05-01",
            })
        # 黑白打印机耗材（仅黑色）
        client.post("/api/consumables", json={
            "name": "black toner", "type": "toner",
            "color": "black", "stock": 1, "threshold": 2,
            "asset_id": mono_id, "current_price": 220.0,
            "installed_at": "2026-04-15",
        })
        # 标签打印机通过 _is_label_printer() 按名称排除，不需要耗材 slot
        return color_id, mono_id, label_id

    def test_printers_consumables_includes_printer_assets_without_slots(self, app_client, db):
        """打印机资产即使还没有耗材 slot，也应自动出现在聚合结果中。"""
        seed_test_data(db)
        login_admin(app_client)
        printer_res = app_client.post("/api/assets", json={
            "name": "Canon 新增打印机", "category": "printer",
            "brand": "Canon", "model": "LBP-2900",
        })
        printer_id = printer_res.get_json()["id"]
        label_res = app_client.post("/api/assets", json={
            "name": "Argox 标签打印机", "category": "printer",
            "brand": "Argox", "model": "OS-214Plus",
        })
        label_id = label_res.get_json()["id"]

        res = app_client.get("/api/printers/consumables")

        assert res.status_code == 200
        printers = res.get_json()["printers"]
        by_id = {p["asset_id"]: p for p in printers}
        assert printer_id in by_id
        assert label_id not in by_id
        printer = by_id[printer_id]
        assert printer["consumables"] == []
        assert printer["total_slots"] == 0
        assert printer["has_warning"] is False
        assert printer["printer_type"] == "unconfigured"

    def test_printers_consumables_endpoint_exists(self, app_client, db):
        """GET /api/printers/consumables 返回 200"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/printers/consumables")
        assert res.status_code == 200

    def test_printers_consumables_requires_admin(self, app_client, db):
        """GET /api/printers/consumables 需管理员权限"""
        seed_test_data(db)
        login_employee(app_client)
        res = app_client.get("/api/printers/consumables")
        assert res.status_code == 403

    def test_printers_consumables_groups_by_printer(self, app_client, db):
        """返回数据按打印机分组，每台打印机包含 consumables 列表"""
        color_id, mono_id, label_id = self._seed_printers_with_consumables(app_client, db)
        res = app_client.get("/api/printers/consumables")
        data = res.get_json()
        printers = data["printers"]
        # 标签打印机不应出现
        printer_ids = [p["asset_id"] for p in printers]
        assert label_id not in printer_ids
        # 彩色和黑白打印机应出现
        assert color_id in printer_ids
        assert mono_id in printer_ids

    def test_printers_consumables_color_printer_has_four_slots(self, app_client, db):
        """彩色打印机应包含四个颜色槽位"""
        color_id, mono_id, _ = self._seed_printers_with_consumables(app_client, db)
        res = app_client.get("/api/printers/consumables")
        data = res.get_json()
        color_printer = next(p for p in data["printers"] if p["asset_id"] == color_id)
        assert color_printer["printer_type"] == "color"
        assert len(color_printer["consumables"]) == 4
        colors = [c["color"] for c in color_printer["consumables"]]
        assert "black" in colors
        assert "cyan" in colors
        assert "magenta" in colors
        assert "yellow" in colors

    def test_printers_consumables_mono_printer_has_black_slot(self, app_client, db):
        """黑白打印机应只包含黑色槽位"""
        _, mono_id, _ = self._seed_printers_with_consumables(app_client, db)
        res = app_client.get("/api/printers/consumables")
        data = res.get_json()
        mono_printer = next(p for p in data["printers"] if p["asset_id"] == mono_id)
        assert mono_printer["printer_type"] == "mono"
        assert len(mono_printer["consumables"]) == 1
        assert mono_printer["consumables"][0]["color"] == "black"

    def test_printers_consumables_includes_replacement_history(self, app_client, db):
        """每个耗材槽位应包含 recent_replacements 历史"""
        color_id, _, _ = self._seed_printers_with_consumables(app_client, db)
        # 获取第一个耗材 ID 做一次更换
        c_res = app_client.get("/api/consumables")
        first_c = next(c for c in c_res.get_json()["consumables"] if c["asset_id"] == color_id)
        app_client.post(f"/api/consumables/{first_c['id']}/replace", json={
            "replaced_at": "2026-05-15", "new_installed_at": "2026-05-15",
            "new_price": 350.0, "use_stock": False, "reason": "用尽",
        })
        res = app_client.get("/api/printers/consumables")
        data = res.get_json()
        color_printer = next(p for p in data["printers"] if p["asset_id"] == color_id)
        replaced_slot = next(
            c for c in color_printer["consumables"]
            if c["id"] == first_c["id"] and len(c.get("recent_replacements", [])) > 0
        )
        assert replaced_slot is not None

    def test_printers_consumables_has_warning_flag(self, app_client, db):
        """库存低于阈值的打印机应标记 warning"""
        _, mono_id, _ = self._seed_printers_with_consumables(app_client, db)
        res = app_client.get("/api/printers/consumables")
        data = res.get_json()
        mono_printer = next(p for p in data["printers"] if p["asset_id"] == mono_id)
        # 黑白打印机库存 1, 阈值 2, 应该有 warning
        assert mono_printer["has_warning"] is True

    def test_printers_consumables_filter_by_type(self, app_client, db):
        """支持按 printer_type=color|mono 筛选"""
        color_id, mono_id, _ = self._seed_printers_with_consumables(app_client, db)
        # 只查彩色
        res = app_client.get("/api/printers/consumables?printer_type=color")
        data = res.get_json()
        printer_ids = [p["asset_id"] for p in data["printers"]]
        assert color_id in printer_ids
        assert mono_id not in printer_ids
        # 只查黑白
        res = app_client.get("/api/printers/consumables?printer_type=mono")
        data = res.get_json()
        printer_ids = [p["asset_id"] for p in data["printers"]]
        assert mono_id in printer_ids
        assert color_id not in printer_ids

    def test_printers_consumables_filter_warning_only(self, app_client, db):
        """支持 warning=1 筛选只返回有低库存告警的打印机"""
        color_id, mono_id, _ = self._seed_printers_with_consumables(app_client, db)
        res = app_client.get("/api/printers/consumables?warning=1")
        data = res.get_json()
        printer_ids = [p["asset_id"] for p in data["printers"]]
        # 彩色打印机全部库存 5, 阈值 2, 无告警
        assert color_id not in printer_ids
        # 黑白打印机库存 1, 阈值 2, 有告警
        assert mono_id in printer_ids

    def test_printers_consumables_printer_shape(self, app_client, db):
        """每台打印机返回标准字段结构"""
        color_id, _, _ = self._seed_printers_with_consumables(app_client, db)
        res = app_client.get("/api/printers/consumables")
        data = res.get_json()
        printer = next(p for p in data["printers"] if p["asset_id"] == color_id)
        for key in ["asset_id", "asset_tag", "printer_name", "printer_type",
                     "brand", "model", "consumables", "has_warning",
                     "total_slots", "low_stock_count", "recent_replacement_count"]:
            assert key in printer, f"missing key: {key}"

    def test_printers_consumables_slot_shape(self, app_client, db):
        """每个耗材槽位返回标准字段结构"""
        color_id, _, _ = self._seed_printers_with_consumables(app_client, db)
        res = app_client.get("/api/printers/consumables")
        data = res.get_json()
        printer = next(p for p in data["printers"] if p["asset_id"] == color_id)
        slot = printer["consumables"][0]
        for key in ["id", "name", "color", "stock", "threshold", "current_price",
                     "installed_at", "usage_days", "estimated_daily_cost",
                     "is_low_stock", "recent_replacements"]:
            assert key in slot, f"missing key in slot: {key}"


class TestConsumablesPageDataShape:
    """Regression: /consumables page-injected JSON must use canonical slot fields
    matching /api/printers/consumables, and color/mono inference must work."""

    def _seed_printers(self, client, db):
        seed_test_data(db)
        login_admin(client)
        # Color printer with 4 slots
        color_res = client.post("/api/assets", json={
            "name": "HP Color LaserJet M479", "category": "printer",
            "brand": "HP", "model": "M479fdw",
        })
        color_id = color_res.get_json()["id"]
        for c in ["black", "cyan", "magenta", "yellow"]:
            client.post("/api/consumables", json={
                "name": f"{c} toner", "type": "toner",
                "color": c, "stock": 5, "threshold": 2,
                "asset_id": color_id, "current_price": 340.0,
                "installed_at": "2026-05-01",
            })
        # Mono printer with only black
        mono_res = client.post("/api/assets", json={
            "name": "Brother HL-L2325D", "category": "printer",
            "brand": "Brother", "model": "HL-L2325D",
        })
        mono_id = mono_res.get_json()["id"]
        client.post("/api/consumables", json={
            "name": "black toner", "type": "toner",
            "color": "black", "stock": 1, "threshold": 2,
            "asset_id": mono_id, "current_price": 220.0,
            "installed_at": "2026-04-15",
        })
        return color_id, mono_id

    def test_page_json_includes_printer_assets_without_slots(self, app_client, db):
        """耗材页面注入数据应包含刚新增、尚未配置耗材 slot 的普通打印机。"""
        seed_test_data(db)
        login_admin(app_client)
        printer_res = app_client.post("/api/assets", json={
            "name": "Canon 新增打印机", "category": "printer",
            "brand": "Canon", "model": "LBP-2900",
        })
        printer_id = printer_res.get_json()["id"]

        res = app_client.get("/consumables")

        assert res.status_code == 200
        html = res.data.decode("utf-8")
        import json, re
        m = re.search(
            r'<script[^>]*data-printer-consumables-json[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        assert m, "printer-consumables-json script tag not found"
        printers = json.loads(m.group(1).strip())
        printer = next((p for p in printers if p["asset_id"] == printer_id), None)
        assert printer, f"Printer {printer_id} not found in injected JSON"
        assert printer["consumables"] == []
        assert printer["total_slots"] == 0
        assert printer["printer_type"] == "unconfigured"

    def test_page_has_add_consumable_hook_for_selected_printer(self, app_client, db):
        """页面应提供可为当前打印机新增耗材的稳定交互钩子。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "openCreateForPrinter" in html
        assert "添加墨粉" in html

    def test_page_json_slots_have_canonical_fields(self, app_client, db):
        """Page-injected JSON slot objects must have id/name/stock/threshold/color/current_price
        (not c_id/c_name/c_stock etc.)"""
        color_id, _ = self._seed_printers(app_client, db)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        # Extract JSON from <script type="application/json" data-printer-consumables-json>
        import json, re
        m = re.search(
            r'<script[^>]*data-printer-consumables-json[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        assert m, "printer-consumables-json script tag not found"
        printers = json.loads(m.group(1).strip())
        color_printer = next((p for p in printers if p["asset_id"] == color_id), None)
        assert color_printer, f"Color printer {color_id} not found in injected JSON"
        slot = color_printer["consumables"][0]
        # Canonical field names (the JS drawer reads slot.id, slot.name, slot.stock, etc.)
        for key in ["id", "name", "stock", "threshold", "color", "current_price",
                     "type", "model", "installed_at", "unit", "notes"]:
            assert key in slot, f"slot missing canonical key '{key}'; has keys: {sorted(slot.keys())}"
        # Must NOT have c_* prefixed keys
        c_keys = [k for k in slot if k.startswith("c_")]
        assert not c_keys, f"slot has c_* prefixed keys that JS drawer can't read: {c_keys}"

    def test_color_printer_page_card_type(self, app_client, db):
        """A printer with cyan/magenta/yellow consumables must render
        data-printer-type='color' in the /consumables page."""
        color_id, mono_id = self._seed_printers(app_client, db)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        # The color printer card must have data-printer-type="color"
        assert f'data-printer-type="color"' in html, \
            "color printer card missing data-printer-type=\"color\""
        # The mono printer card must have data-printer-type="mono"
        assert f'data-printer-type="mono"' in html, \
            "mono printer card missing data-printer-type=\"mono\""

    def test_malicious_printer_name_no_script_injection(self, app_client, db):
        """A printer name containing </script> must NOT break the JSON script tag.
        The injected JSON must parse correctly and the page must remain valid."""
        seed_test_data(db)
        login_admin(app_client)
        malicious_name = 'test</script><img src=x onerror=alert(1)>'
        res = app_client.post("/api/assets", json={
            "name": malicious_name, "category": "printer",
            "brand": "Test", "model": "X1",
        })
        pid = res.get_json()["id"]
        app_client.post("/api/consumables", json={
            "name": "toner", "type": "toner", "color": "black",
            "stock": 2, "threshold": 1, "asset_id": pid,
        })
        page = app_client.get("/consumables")
        assert page.status_code == 200
        html = page.data.decode("utf-8")
        import json, re
        m = re.search(
            r'<script[^>]*data-printer-consumables-json[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        assert m, "printer-consumables-json script tag not found"
        # The raw literal "</script>" must NOT appear inside the JSON content
        # (Jinja tojson escapes forward slashes as \/)
        json_text = m.group(1).strip()
        assert "</script>" not in json_text, \
            "Raw </script> found in injected JSON — XSS injection vulnerability"
        # JSON must parse successfully
        printers = json.loads(json_text)
        found = next((p for p in printers if p["asset_id"] == pid), None)
        assert found, "Malicious-name printer not found in injected JSON"
        # The name should be preserved but safely encoded
        assert "<img" not in json_text, "<img tag leaked into JSON"

    def test_drawer_uses_createElement_not_innerHTML_concat(self, app_client, db):
        """The renderDrawer JS should use createElement/textContent for dynamic fields,
        not innerHTML string concatenation with DB-origin data.
        We check that the template doesn't build slot card HTML via innerHTML +=."""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        # Slot rendering should not use innerHTML with dynamic slot fields
        # Specifically: slot.id, slot.color, slot.name, slot.stock etc. should not be
        # directly concatenated into innerHTML strings
        import re
        # Find the slot rendering block - check that it doesn't use
        # innerHTML += patterns with slot.* fields
        # We look for the pattern: html += ... slot. ...
        # This is a heuristic check: the drawer should build DOM elements, not concat HTML
        slot_innerhtml_patterns = re.findall(
            r'html\s*\+=\s*.*?slot\.(id|color|name|stock|threshold)',
            html,
        )
        assert not slot_innerhtml_patterns, \
            f"renderDrawer uses innerHTML concatenation with slot fields: {slot_innerhtml_patterns}"


class TestPrinterTypeAndTonerScope:
    """printer_type field on asset + toner-only scope + mono/color color rules."""

    # ---- 1. Database schema: asset.printer_type column ----

    def test_new_db_has_printer_type_column(self, db):
        """全新数据库 asset 表应包含 printer_type 列。"""
        with db.get_conn() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(asset)").fetchall()]
        assert "printer_type" in cols

    def test_legacy_db_upgrade_adds_printer_type_column(self, legacy_mvp_db):
        """旧库升级后 asset 表应有 printer_type 列。"""
        legacy_mvp_db.upgrade_db()
        with legacy_mvp_db.get_conn() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(asset)").fetchall()]
        assert "printer_type" in cols

    def test_printer_type_upgrade_idempotent(self, legacy_mvp_db):
        """重复升级不报错，printer_type 列仍唯一存在。"""
        legacy_mvp_db.upgrade_db()
        legacy_mvp_db.upgrade_db()
        with legacy_mvp_db.get_conn() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(asset)").fetchall()]
        assert cols.count("printer_type") == 1

    # ---- 2. Asset API: printer_type on create/update ----

    def test_create_printer_asset_with_printer_type_mono(self, app_client, db):
        """创建打印机资产时可指定 printer_type=mono。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={
            "name": "HP LaserJet", "category": "printer",
            "brand": "HP", "model": "M404dn", "printer_type": "mono",
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data["printer_type"] == "mono"

    def test_create_printer_asset_with_printer_type_color(self, app_client, db):
        """创建打印机资产时可指定 printer_type=color。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={
            "name": "HP Color M479", "category": "printer",
            "brand": "HP", "model": "M479fdw", "printer_type": "color",
        })
        assert res.status_code == 201
        assert res.get_json()["printer_type"] == "color"

    def test_create_printer_asset_default_printer_type_is_null(self, app_client, db):
        """创建打印机资产不传 printer_type 时默认为 None。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={
            "name": "HP LaserJet", "category": "printer",
        })
        assert res.status_code == 201
        assert res.get_json().get("printer_type") is None

    def test_create_non_printer_asset_printer_type_is_null(self, app_client, db):
        """非打印机资产 printer_type 应为 None。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={
            "name": "ThinkPad", "category": "computer",
        })
        assert res.status_code == 201
        assert res.get_json().get("printer_type") is None

    def test_create_printer_asset_invalid_printer_type_returns_400(self, app_client, db):
        """创建打印机资产时非法 printer_type 应返回 400。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/assets", json={
            "name": "Bad Printer", "category": "printer",
            "printer_type": "three_d",
        })
        assert res.status_code == 400

    def test_update_printer_asset_printer_type(self, app_client, db):
        """更新打印机资产的 printer_type。"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={
            "name": "HP LaserJet", "category": "printer",
            "printer_type": "mono",
        })
        asset_id = create_res.get_json()["id"]
        res = app_client.put(f"/api/assets/{asset_id}", json={
            "printer_type": "color",
        })
        assert res.status_code == 200
        assert res.get_json()["printer_type"] == "color"

    def test_update_printer_type_invalid_returns_400(self, app_client, db):
        """更新打印机 printer_type 为非法值应返回 400。"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={
            "name": "HP LaserJet", "category": "printer",
        })
        asset_id = create_res.get_json()["id"]
        res = app_client.put(f"/api/assets/{asset_id}", json={
            "printer_type": "invalid",
        })
        assert res.status_code == 400

    def test_update_asset_category_and_printer_type_together(self, app_client, db):
        """同次更新 category=printer 与 printer_type 应按新类别校验。"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={
            "name": "Future Printer", "category": "computer",
        })
        asset_id = create_res.get_json()["id"]
        res = app_client.put(f"/api/assets/{asset_id}", json={
            "category": "printer",
            "printer_type": "mono",
        })
        assert res.status_code == 200
        assert res.get_json()["category"] == "printer"
        assert res.get_json()["printer_type"] == "mono"

    def test_update_printer_to_non_printer_clears_printer_type(self, app_client, db):
        """打印机改为非打印机时应清空 printer_type，避免旧值残留。"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/assets", json={
            "name": "HP LaserJet", "category": "printer", "printer_type": "mono",
        })
        asset_id = create_res.get_json()["id"]
        res = app_client.put(f"/api/assets/{asset_id}", json={"category": "computer"})
        assert res.status_code == 200
        assert res.get_json()["category"] == "computer"
        assert res.get_json()["printer_type"] is None

    # ---- 3. Toner-only constraints: type fixed to toner, model enum ----

    def test_create_consumable_defaults_type_to_toner(self, app_client, db):
        """创建耗材不传 type 时默认为 toner。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "stock": 3,
        })
        assert res.status_code == 201
        assert res.get_json()["type"] == "toner"

    def test_create_consumable_rejects_non_toner_type(self, app_client, db):
        """创建耗材传非 toner type 应返回 400。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "打印纸", "type": "paper", "stock": 10,
        })
        assert res.status_code == 400
        assert "toner" in res.get_json()["error"]

    def test_create_consumable_explicit_toner_succeeds(self, app_client, db):
        """显式传 type=toner 应成功。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "stock": 3,
        })
        assert res.status_code == 201
        assert res.get_json()["type"] == "toner"

    def test_update_consumable_rejects_non_toner_type(self, app_client, db):
        """更新耗材 type 为非 toner 应返回 400。"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "stock": 3,
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={"type": "ink"})
        assert res.status_code == 400

    def test_create_consumable_model_valid_values(self, app_client, db):
        """创建耗材 model 为"原装"或"国产"应成功。"""
        seed_test_data(db)
        login_admin(app_client)
        res1 = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "model": "原装", "stock": 3,
        })
        assert res1.status_code == 201
        assert res1.get_json()["model"] == "原装"

        res2 = app_client.post("/api/consumables", json={
            "name": "青色墨粉", "type": "toner", "model": "国产", "stock": 2,
        })
        assert res2.status_code == 201
        assert res2.get_json()["model"] == "国产"

    def test_create_consumable_invalid_model_returns_400(self, app_client, db):
        """创建耗材 model 为非法值应返回 400。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "model": "TN-K", "stock": 3,
        })
        assert res.status_code == 400
        assert "model" in res.get_json()["error"].lower() or "型号" in res.get_json()["error"]

    def test_create_consumable_model_optional(self, app_client, db):
        """创建耗材不传 model 时应成功（model 为 None）。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "stock": 3,
        })
        assert res.status_code == 201
        assert res.get_json().get("model") is None

    def test_update_consumable_invalid_model_returns_400(self, app_client, db):
        """更新耗材 model 为非法值应返回 400。"""
        seed_test_data(db)
        login_admin(app_client)
        create_res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "stock": 3,
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={"model": "BAD-MODEL"})
        assert res.status_code == 400

    # ---- 4. Mono/color printer toner color rules ----

    def test_mono_printer_rejects_color_toner_on_create(self, app_client, db):
        """黑白打印机不允许创建彩色墨粉。"""
        seed_test_data(db)
        login_admin(app_client)
        printer_res = app_client.post("/api/assets", json={
            "name": "HP LaserJet", "category": "printer",
            "printer_type": "mono",
        })
        printer_id = printer_res.get_json()["id"]
        res = app_client.post("/api/consumables", json={
            "name": "青色墨粉", "type": "toner", "color": "cyan",
            "stock": 3, "asset_id": printer_id,
        })
        assert res.status_code == 400

    def test_mono_printer_allows_black_toner(self, app_client, db):
        """黑白打印机允许创建黑色墨粉。"""
        seed_test_data(db)
        login_admin(app_client)
        printer_res = app_client.post("/api/assets", json={
            "name": "HP LaserJet", "category": "printer",
            "printer_type": "mono",
        })
        printer_id = printer_res.get_json()["id"]
        res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "color": "black",
            "stock": 3, "asset_id": printer_id,
        })
        assert res.status_code == 201

    def test_color_printer_allows_all_cmyk_toners(self, app_client, db):
        """彩色打印机允许创建黑/青/品红/黄墨粉。"""
        seed_test_data(db)
        login_admin(app_client)
        printer_res = app_client.post("/api/assets", json={
            "name": "HP Color M479", "category": "printer",
            "printer_type": "color",
        })
        printer_id = printer_res.get_json()["id"]
        for color in ["black", "cyan", "magenta", "yellow"]:
            res = app_client.post("/api/consumables", json={
                "name": f"{color} toner", "type": "toner", "color": color,
                "stock": 3, "asset_id": printer_id,
            })
            assert res.status_code == 201, f"color={color} should succeed"

    def test_mono_printer_rejects_color_toner_on_update(self, app_client, db):
        """更新墨粉时黑白打印机不允许改为彩色。"""
        seed_test_data(db)
        login_admin(app_client)
        printer_res = app_client.post("/api/assets", json={
            "name": "HP LaserJet", "category": "printer",
            "printer_type": "mono",
        })
        printer_id = printer_res.get_json()["id"]
        create_res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "color": "black",
            "stock": 3, "asset_id": printer_id,
        })
        cid = create_res.get_json()["id"]
        res = app_client.put(f"/api/consumables/{cid}", json={"color": "cyan"})
        assert res.status_code == 400

    def test_unconfigured_printer_allows_black_by_default(self, app_client, db):
        """未配置 printer_type 的打印机默认允许黑色墨粉。"""
        seed_test_data(db)
        login_admin(app_client)
        printer_res = app_client.post("/api/assets", json={
            "name": "Unknown Printer", "category": "printer",
        })
        printer_id = printer_res.get_json()["id"]
        res = app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "color": "black",
            "stock": 3, "asset_id": printer_id,
        })
        assert res.status_code == 201

    def test_printers_consumables_uses_explicit_printer_type(self, app_client, db):
        """聚合 API 优先使用 asset.printer_type 而不是推断。"""
        seed_test_data(db)
        login_admin(app_client)
        # 创建一台 printer_type=color 的打印机但只有 black slot
        printer_res = app_client.post("/api/assets", json={
            "name": "Color Printer", "category": "printer",
            "printer_type": "color",
        })
        printer_id = printer_res.get_json()["id"]
        app_client.post("/api/consumables", json={
            "name": "黑色墨粉", "type": "toner", "color": "black",
            "stock": 3, "asset_id": printer_id,
        })
        res = app_client.get("/api/printers/consumables")
        printer = next(p for p in res.get_json()["printers"] if p["asset_id"] == printer_id)
        # 显式 color 应该是 "color"，推断应为 "mono"
        assert printer["printer_type"] == "color"

    # ---- 5. Aggregation API only shows toner slots ----

    def test_printers_consumables_only_shows_toner_slots(self, app_client, db):
        """聚合 API 只返回 toner 类型的 slot（不返回历史 ribbon/paper）。"""
        seed_test_data(db)
        login_admin(app_client)
        printer_res = app_client.post("/api/assets", json={
            "name": "Test Printer", "category": "printer",
            "printer_type": "mono",
        })
        printer_id = printer_res.get_json()["id"]
        # Create a toner via API (should work)
        app_client.post("/api/consumables", json={
            "name": "Black Toner", "type": "toner", "color": "black",
            "stock": 3, "asset_id": printer_id,
        })
        # Manually insert a ribbon record (legacy data) into DB
        db_path = db.db_path
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO printer_consumable (name, type, stock, threshold, asset_id) "
                "VALUES ('Legacy Ribbon', 'ribbon', 5, 1, ?)",
                (printer_id,),
            )
        res = app_client.get("/api/printers/consumables")
        printer = next(p for p in res.get_json()["printers"] if p["asset_id"] == printer_id)
        for slot in printer["consumables"]:
            assert slot["type"] == "toner"

    # ---- 6. Page wording: 墨粉管理 ----

    def test_consumables_page_title_is_toner_management(self, app_client, db):
        """/consumables 页面标题应包含"墨粉管理"而非"耗材管理"。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        html = res.data.decode("utf-8")
        assert "墨粉管理" in html
        assert "耗材管理" not in html

    def test_consumables_page_add_button_says_toner(self, app_client, db):
        """页面新增按钮应为"新增墨粉"而非"新增耗材"。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        html = res.data.decode("utf-8")
        assert "新增墨粉" in html
        assert "新增耗材" not in html

    def test_consumables_page_replace_button_says_replace_toner(self, app_client, db):
        """页面更替按钮应为"更换墨粉"。"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/consumables")
        html = res.data.decode("utf-8")
        assert "更换墨粉" in html


class TestUsersPage:
    def test_users_page_accessible(self, app_client, db):
        """用户管理页面对管理员可访问"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/users")
        assert res.status_code == 200
        assert b"users" in res.data

    def test_users_page_requires_admin(self, app_client, db):
        """用户管理页面需管理员权限"""
        seed_test_data(db)
        login_employee(app_client)
        res = app_client.get("/users")
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]

    def test_users_page_has_page_hook(self, app_client, db):
        """用户管理页面包含 data-page-title 持久钩子"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/users")
        assert res.status_code == 200
        assert b'data-page-title="users"' in res.data

    def test_users_page_has_modal_hooks(self, app_client, db):
        """用户管理页面包含弹窗持久钩子"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/users")
        assert res.status_code == 200
        assert b'data-modal="user-form"' in res.data
        assert b'data-modal="reset-password"' in res.data


class TestCSSAssets:
    def test_static_css_has_balanced_rule_blocks(self):
        """style.css 规则块花括号应平衡，防止语法错误导致后续规则被忽略"""
        from pathlib import Path
        css = Path(__file__).parent.parent / "static" / "style.css"
        assert css.exists(), "static/style.css not found"
        text = css.read_text(encoding="utf-8")
        balance = 0
        for i, ch in enumerate(text):
            if ch == "{":
                balance += 1
            elif ch == "}":
                balance -= 1
            assert balance >= 0, f"extra closing brace at byte {i}"
        assert balance == 0, f"unbalanced braces: {balance} unclosed blocks"


class TestHealthEndpoint:
    def test_health_ok(self, app_client, db):
        """健康检查端点返回 200"""
        res = app_client.get("/api/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "ok"
        assert data["db"] == "connected"


class TestErrorPages:
    def test_404_page(self, app_client, db):
        """不存在的页面返回 404 HTML"""
        res = app_client.get("/nonexistent-page")
        assert res.status_code == 404
        assert b"404" in res.data
        assert "页面未找到" in res.data.decode("utf-8")

    def test_404_api_still_json(self, app_client, db):
        """API 路由不存在的资源返回 JSON 404"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/assets/99999")
        assert res.status_code == 404
        assert res.content_type.startswith("application/json")


class TestEmployeeImportTemplate:
    def test_template_download(self, app_client, db):
        """员工导入模板下载返回 CSV"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/employees/import/template")
        assert res.status_code == 200
        assert "text/csv" in res.content_type
        assert res.headers["Content-Disposition"].startswith("attachment")
        text = res.data.decode("utf-8-sig")
        assert "name" in text
        assert "department" in text

    def test_template_requires_admin(self, app_client, db):
        """模板下载需要管理员权限"""
        seed_test_data(db)
        login_employee(app_client)
        res = app_client.get("/api/employees/import/template")
        assert res.status_code == 403


class TestActivityExport:
    def test_activity_export(self, app_client, db):
        """操作记录导出返回 CSV"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/activity/export")
        assert res.status_code == 200
        assert "text/csv" in res.content_type
        text = res.data.decode("utf-8-sig")
        assert "时间" in text
        assert "操作人" in text
        assert "登录" in text

    def test_activity_export_with_filter(self, app_client, db):
        """操作记录导出支持按操作类型筛选"""
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/activity/export?action=login")
        assert res.status_code == 200
        text = res.data.decode("utf-8-sig")
        assert "登录" in text

    def test_activity_export_requires_admin(self, app_client, db):
        """操作记录导出需要管理员权限"""
        seed_test_data(db)
        login_employee(a