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
        for table in ["consumable_replacement", "printer_consumable", "activity_log", "app_config", "asset_application", "maintenance_record", "lifecycle_event", "asset", "user", "employee"]:
            conn.execute(f"DELETE FROM {table}")
        conn.executescript("DELETE FROM sqlite_sequence")

        # 员工名单
        employees = [
            ("admin", "管理员", "IT部"),
            ("emp001", "张三", "研发部"),
            ("emp002", "李四", "市场部"),
            ("emp003", "王五", "财务部"),
        ]
        for emp in employees:
            conn.execute(
                "INSERT INTO employee (employee_id, name, department) VALUES (?, ?, ?)",
                emp,
            )

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
            ("PRN-2026-0002", "Canon imageCLASS MF743Cdw", "printer", "Canon", "MF743Cdw", "SN-CAN-001", "assigned", 1, "市场部", "2025-12-01", 4299.00, "彩色打印", "2027-12-01"),
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
            (1, "stock_in", 1, None, None, None, "仓库", "入库"),
            (1, "assign", 1, 2, 2, None, "工位A-101", "分配给张三"),
            (2, "stock_in", 1, None, None, None, "仓库", "入库"),
            (2, "assign", 1, 3, 3, None, "工位B-205", "分配给李四"),
            (3, "stock_in", 1, None, None, None, "仓库", "入库"),
            (3, "assign", 1, 2, 2, None, "工位A-101", "分配给张三"),
            (8, "stock_in", 1, None, None, None, "仓库", "入库"),
            (8, "assign", 1, 1, 1, None, "IT部", "分配给管理员"),
            (8, "maintenance_start", 1, None, None, None, "维修", "键盘故障"),
            (10, "stock_in", 1, None, None, None, "仓库", "入库"),
            (10, "assign", 1, 2, 2, None, "工位", "分配给张三"),
            (10, "scrap", 1, None, None, None, "报废", "屏幕碎裂"),
        ]
        for e in events:
            conn.execute(
                """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, target_user_id, target_employee_id,
                   from_location, to_location, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
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

        # 打印机类型
        conn.execute("UPDATE asset SET printer_type = 'mono' WHERE asset_tag = 'PRN-2026-0001'")
        conn.execute("UPDATE asset SET printer_type = 'color' WHERE asset_tag = 'PRN-2026-0002'")
        printer_ids = {
            row["asset_tag"]: row["id"]
            for row in conn.execute(
                "SELECT id, asset_tag FROM asset WHERE asset_tag IN (?, ?)",
                ("PRN-2026-0001", "PRN-2026-0002"),
            ).fetchall()
        }
        hp_printer_id = printer_ids["PRN-2026-0001"]
        canon_printer_id = printer_ids["PRN-2026-0002"]

        # 墨粉槽位
        # 黑白打印机：一支黑色墨粉
        conn.execute(
            """INSERT INTO printer_consumable (name, type, stock, threshold, asset_id, unit, color, model, current_price, installed_at, notes)
               VALUES ('HP LaserJet Pro - 黑色', 'toner', 2, 1, ?, '个', 'black', '原装', 320.00, '2026-04-26', NULL)""",
            (hp_printer_id,),
        )
        # 彩色打印机：黑/青/品/黄四色
        conn.execute(
            """INSERT INTO printer_consumable (name, type, stock, threshold, asset_id, unit, color, model, current_price, installed_at, notes)
               VALUES ('Canon MF743Cdw - 黑色', 'toner', 3, 1, ?, '个', 'black', '原装', 420.00, '2026-04-10', NULL)""",
            (canon_printer_id,),
        )
        conn.execute(
            """INSERT INTO printer_consumable (name, type, stock, threshold, asset_id, unit, color, model, current_price, installed_at, notes)
               VALUES ('Canon MF743Cdw - 青色', 'toner', 1, 1, ?, '个', 'cyan', '国产', 280.00, '2026-03-15', NULL)""",
            (canon_printer_id,),
        )
        conn.execute(
            """INSERT INTO printer_consumable (name, type, stock, threshold, asset_id, unit, color, model, current_price, installed_at, notes)
               VALUES ('Canon MF743Cdw - 品红', 'toner', 2, 1, ?, '个', 'magenta', '国产', 280.00, '2026-04-01', NULL)""",
            (canon_printer_id,),
        )
        conn.execute(
            """INSERT INTO printer_consumable (name, type, stock, threshold, asset_id, unit, color, model, current_price, installed_at, notes)
               VALUES ('Canon MF743Cdw - 黄色', 'toner', 0, 1, ?, '个', 'yellow', '国产', 280.00, '2026-03-01', '低库存预警')""",
            (canon_printer_id,),
        )

        # 更替历史：黑白打印机黑色墨粉 (consumable_id=1) 的旧周期
        conn.execute(
            """INSERT INTO consumable_replacement (consumable_id, asset_id_snapshot, consumable_name_snapshot,
               old_installed_at, replaced_at, usage_days, price, daily_cost, new_installed_at, new_price, reason, notes)
               VALUES (1, ?, 'HP LaserJet Pro - 黑色', '2025-11-10', '2026-04-26', 167, 320.00, 1.92, '2026-04-26', 320.00, '用尽', '首次更换')""",
            (hp_printer_id,),
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
