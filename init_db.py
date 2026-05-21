"""IT 资产管理 MVP — 数据库初始化 + 种子数据"""
import os
import sys
from models import Database
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get("DB_PATH", "it_asset.db")


def seed(db):
    """插入演示数据"""
    with db.get_conn() as conn:
        # 清空旧数据
        for table in ["activity_log", "app_config", "asset_application", "maintenance_record", "lifecycle_event", "asset", "user"]:
            conn.execute(f"DELETE FROM {table}")
        conn.executescript("DELETE FROM sqlite_sequence")

        # 用户
        users = [
            ("admin", "管理员", "IT部", "", "admin@company.com", "admin", "admin123"),
            ("emp001", "张三", "研发部", "13800000001", "zhangsan@company.com", "employee", "emp001"),
            ("emp002", "李四", "市场部", "13800000002", "lisi@company.com", "employee", "emp002"),
            ("emp003", "王五", "财务部", "13800000003", "wangwu@company.com", "employee", "emp003"),
        ]
        for u in users:
            conn.execute(
                """INSERT INTO "user" (employee_id, name, department, phone, email, role, password_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (u[0], u[1], u[2], u[3], u[4], u[5], generate_password_hash(u[6])),
            )

        # 资产（含 warranty_date）
        assets = [
            ("PC-2026-0001", "ThinkPad T14s Gen 4", "computer", "Lenovo", "T14s Gen 4", "SN-LNV-001", "assigned", 2, "工位A-101", "2026-01-15", 6999.00, "研发主力机", "2029-01-15"),
            ("PC-2026-0002", "MacBook Pro 14", "computer", "Apple", "M3 Pro 14", "SN-APL-001", "assigned", 3, "工位B-205", "2026-02-01", 14999.00, "设计用", "2029-02-01"),
            ("MON-2026-0001", "DELL U2723QE", "monitor", "DELL", "U2723QE", "SN-DL-001", "assigned", 2, "工位A-101", "2026-01-15", 3299.00, "", "2029-01-15"),
            ("PH-2026-0001", "iPhone 15 Pro", "phone", "Apple", "A3101", "SN-IPH-001", "in_stock", None, "仓库", "2026-01-20", 8999.00, "备机", "2027-01-20"),
            ("PRN-2026-0001", "HP LaserJet Pro", "printer", "HP", "M404dn", "SN-HP-001", "assigned", 1, "IT部办公区", "2025-11-10", 2499.00, "共享打印机", "2026-06-15"),
            ("SRV-2026-0001", "Dell PowerEdge R740", "server", "Dell", "R740", "SN-DL-SRV-001", "assigned", 1, "机房A-01号柜", "2025-06-15", 45000.00, "主服务器", "2025-12-15"),
            ("NET-2026-0001", "Cisco C9300", "network", "Cisco", "C9300-48T", "SN-CSC-001", "assigned", 1, "机房A-02号柜", "2025-06-15", 28000.00, "核心交换", "2025-12-15"),
            ("PC-2026-0003", "HP EliteBook 840", "computer", "HP", "840 G10", "SN-HP-002", "maintenance", 1, "维修中", "2025-09-01", 5999.00, "键盘故障送修", "2026-06-20"),
            ("FW-2026-0001", "FortiGate 100F", "firewall", "Fortinet", "FG-100F", "SN-FGT-001", "assigned", 1, "机房A-01号柜", "2025-06-15", 35000.00, "边界防火墙", "2025-12-15"),
            ("TAB-2026-0001", "iPad Air M2", "tablet", "Apple", "A2906", "SN-IPD-001", "scrapped", None, "已报废", "2025-03-20", 4799.00, "屏幕碎裂报废", None),
        ]
        for a in assets:
            conn.execute(
                """INSERT INTO asset (asset_tag, name, category, brand, model, serial_number,
                   status, current_holder_id, location, purchase_date, purchase_price, notes, warranty_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                a,
            )

        # 生命周期事件
        events = [
            (1, "stock_in", 1, None, None, "仓库", "入库"),
            (1, "assign", 1, 2, None, "工位A-101", "分配给张三"),
            (2, "stock_in", 1, None, None, "仓库", "入库"),
            (2, "assign", 1, 3, None, "工位B-205", "分配给王五→改为李四"),
            (3, "stock_in", 1, None, None, "仓库", "入库"),
            (3, "assign", 1, 2, None, "工位A-101", "分配给张三"),
            (8, "stock_in", 1, None, None, "仓库", "入库"),
            (8, "assign", 1, 1, None, "IT部", "分配给管理员"),
            (8, "maintenance_start", 1, None, None, "维修", "键盘故障"),
            (10, "stock_in", 1, None, None, "仓库", "入库"),
            (10, "assign", 1, 2, None, "工位", "分配给张三"),
            (10, "scrap", 1, None, None, "报废", "屏幕碎裂"),
        ]
        for e in events:
            conn.execute(
                """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, target_user_id,
                   from_location, to_location, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                e,
            )

        # 维修记录
        conn.execute(
            """INSERT INTO maintenance_record (asset_id, reported_by, description, status, cost, repair_notes)
               VALUES (8, 1, '键盘按键无响应', 'in_progress', NULL, NULL)""",
        )

        # 资产申请
        conn.execute(
            """INSERT INTO asset_application (applicant_id, asset_category, reason, status, admin_id, admin_notes)
               VALUES (2, 'computer', '开发需要高性能笔记本', 'approved', 1, '已安排采购')""",
        )
        conn.execute(
            """INSERT INTO asset_application (applicant_id, asset_category, reason, status)
               VALUES (3, 'monitor', '需要外接显示器提高效率', 'pending')""",
        )


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    db_existed = os.path.exists(db_path)
    db = Database(db_path)
    db.init_db()
    if db_existed:
        db.upgrade_db()
    seed(db)
    print(f"数据库已初始化并填充种子数据: {db_path}")


if __name__ == "__main__":
    main()
