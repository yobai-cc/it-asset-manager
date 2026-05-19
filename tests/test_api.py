"""IT 资产管理 MVP — 自动化测试

覆盖：资产 CRUD、生命周期事件、维修记录、申请流程、标签/二维码生成
"""
import os
import sys
import json
import tempfile
import pytest

# 确保项目目录在 path 中
sys.path.insert(0, os.path.dirname(__file__))

from models import Database


# ---- Fixtures ----

@pytest.fixture
def db():
    """每个测试一个临时数据库"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    database.init_db()
    yield database
    os.unlink(path)


@pytest.fixture
def app_client(db, monkeypatch):
    """Flask 测试客户端"""
    os.environ["DB_PATH"] = db.db_path
    monkeypatch.setenv("DB_PATH", db.db_path)

    import importlib
    import server as srv
    importlib.reload(srv)
    srv.DB_PATH = db.db_path
    srv.app.config["TESTING"] = True
    srv.app.config["SECRET_KEY"] = "test-secret"

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

    def test_qr_nonexistent_asset(self, app_client, db):
        seed_test_data(db)
        login_admin(app_client)
        res = app_client.get("/api/assets/9999/qr")
        assert res.status_code == 404


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
