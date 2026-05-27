"""IT 资产管理 MVP — Flask 应用"""
import csv
import io
import json
import os
from datetime import date, datetime
from flask import Flask, g, jsonify, request, render_template, redirect, url_for, session, Response
from werkzeug.security import check_password_hash
from models import (
    Database, VALID_CATEGORIES, VALID_STATUSES, STATE_TRANSITIONS,
    log_activity, get_categories_meta, LABEL_FIELDS_DEFAULT,
    LABEL_FIELD_OPTIONS, LABEL_FIELDS_MAX, LABEL_FIXED_FIELDS,
    VALID_ROLES, VALID_CONSUMABLE_TYPES, VALID_PRINTER_TYPES,
    VALID_TONER_COLORS, VALID_TONER_MODELS,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

DB_PATH = os.environ.get("DB_PATH", "it_asset.db")


def get_db():
    if "db" not in g:
        g.db = Database(DB_PATH)
    return g.db


@app.teardown_appcontext
def close_db(exc):
    pass  # Database uses per-request connections


def _parse_positive_int_arg(name, default, max_value=None):
    """解析分页参数，非数字或小于 1 时返回 400 响应。"""
    raw = request.args.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, (jsonify({"error": f"{name} 必须是正整数"}), 400)
    if value < 1:
        return None, (jsonify({"error": f"{name} 必须是正整数"}), 400)
    if max_value is not None:
        value = min(value, max_value)
    return value, None


def _parse_iso_date(value, field_name):
    if not value:
        return None, None
    try:
        return date.fromisoformat(value), None
    except (TypeError, ValueError):
        return None, (jsonify({"error": f"{field_name} 必须是 YYYY-MM-DD 日期"}), 400)


def _employee_id_for_user(user):
    return user.get("employee_id") if isinstance(user, dict) else user["employee_id"]


def _clean_optional_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _validate_non_negative_int(data, field_name, required=False):
    """验证字段是非负整数，返回 (value, error_response)"""
    val = data.get(field_name)
    if val is None:
        if required:
            return None, (jsonify({"error": f"缺少必填字段: {field_name}"}), 400)
        return None, None
    if isinstance(val, bool) or not isinstance(val, int):
        return None, (jsonify({"error": f"{field_name} 必须是整数"}), 400)
    if val < 0:
        return None, (jsonify({"error": f"{field_name} 不能为负数"}), 400)
    return val, None


def _validate_non_negative_number(data, field_name, allow_none=True):
    """验证字段是非负数字（int 或 float），返回 (value, error_response)"""
    val = data.get(field_name)
    if val is None:
        return None, None
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None, (jsonify({"error": f"{field_name} 必须是数字"}), 400)
    if val < 0:
        return None, (jsonify({"error": f"{field_name} 不能为负数"}), 400)
    return val, None


def _validate_printer_asset_id(conn, asset_id):
    """验证 asset_id 对应的资产存在且为打印机。返回 (ok, error_response)"""
    if asset_id is None:
        return True, None
    row = conn.execute("SELECT category FROM asset WHERE id = ?", (asset_id,)).fetchone()
    if not row:
        return False, (jsonify({"error": "关联资产不存在"}), 400)
    if row["category"] != "printer":
        return False, (jsonify({"error": "耗材只能关联打印机类资产"}), 400)
    return True, None


def _consumable_usage_fields(row):
    data = dict(row)
    installed_at = data.get("installed_at")
    usage_days = None
    estimated_daily_cost = None
    if installed_at:
        try:
            usage_days = max((date.today() - date.fromisoformat(installed_at)).days, 1)
        except ValueError:
            usage_days = None
    price = data.get("current_price")
    if usage_days and price is not None:
        estimated_daily_cost = round(float(price) / usage_days, 2)
    data["usage_days"] = usage_days
    data["estimated_daily_cost"] = estimated_daily_cost
    return data


def _select_consumable_with_printer(conn, consumable_id):
    return conn.execute(
        """SELECT pc.*, a.asset_tag as printer_tag, a.name as printer_name
           FROM printer_consumable pc
           LEFT JOIN asset a ON pc.asset_id = a.id
           WHERE pc.id = ?""", (consumable_id,),
    ).fetchone()


# ---- 认证辅助 ----

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM \"user\" WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def require_role(*roles):
    user = current_user()
    if not user or user["role"] not in roles:
        return None
    return user


# ---- 页面路由 ----

@app.route("/")
def index():
    user = current_user()
    if not user:
        return redirect(url_for("login_page"))
    if user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("my_assets"))


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/dashboard")
def admin_dashboard():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/dashboard.html", user=user)


@app.route("/assets")
def asset_list_page():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/assets.html", user=user)


@app.route("/assets/new")
def asset_new_page():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/asset_form.html", user=user, asset=None)


@app.route("/assets/<int:asset_id>")
def asset_detail_page(asset_id):
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/asset_detail.html", user=user, asset_id=asset_id)


@app.route("/assets/<int:asset_id>/edit")
def asset_edit_page(asset_id):
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/asset_form.html", user=user, asset_id=asset_id)


@app.route("/assets/<int:asset_id>/label")
def asset_label_page(asset_id):
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/label.html", user=user, asset_id=asset_id)


@app.route("/applications")
def applications_page():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/applications.html", user=user)


@app.route("/maintenance")
def maintenance_page():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/maintenance.html", user=user)


@app.route("/consumables")
def consumables_page():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    # Fetch printer-consumables data for server-side rendering
    db = get_db()
    printers_data = []
    with db.get_conn() as conn:
        rows = conn.execute("""
            SELECT a.id as asset_id, a.asset_tag, a.name as printer_name,
                   a.brand, a.model, a.printer_type,
                   pc.id as c_id, pc.name as c_name, pc.type as c_type,
                   pc.stock as c_stock, pc.threshold as c_threshold,
                   pc.color as c_color, pc.model as c_model,
                   pc.current_price as c_current_price,
                   pc.installed_at as c_installed_at,
                   pc.unit as c_unit, pc.notes as c_notes
            FROM asset a
            LEFT JOIN printer_consumable pc ON pc.asset_id = a.id AND pc.type = 'toner'
            WHERE a.category = 'printer'
            ORDER BY a.id, pc.id
        """).fetchall()
        printers_map = {}
        for r in rows:
            aid = r["asset_id"]
            if aid not in printers_map:
                printers_map[aid] = {
                    "asset_id": aid,
                    "asset_tag": r["asset_tag"],
                    "printer_name": r["printer_name"],
                    "brand": r["brand"],
                    "model": r["model"],
                    "printer_type_db": r["printer_type"],
                    "_consumables_raw": [],
                }
            # Use canonical field names (same shape as /api/printers/consumables)
            if r["c_id"] is not None:
                printers_map[aid]["_consumables_raw"].append({
                    "id": r["c_id"],
                    "name": r["c_name"],
                    "type": r["c_type"],
                    "stock": r["c_stock"],
                    "threshold": r["c_threshold"],
                    "color": r["c_color"],
                    "model": r["c_model"],
                    "current_price": r["c_current_price"],
                    "installed_at": r["c_installed_at"],
                    "unit": r["c_unit"],
                    "notes": r["c_notes"],
                    "asset_id": aid,
                    "printer_tag": r["asset_tag"],
                    "printer_name": r["printer_name"],
                })

        for p in printers_map.values():
            if _is_label_printer(p["printer_name"], p["brand"], p["model"]):
                continue
            raw = p["_consumables_raw"]
            # Use explicit printer_type if set, otherwise infer from consumables
            explicit_pt = p.get("printer_type_db")
            if explicit_pt in VALID_PRINTER_TYPES:
                printer_type = explicit_pt
            else:
                printer_type = _infer_printer_type(raw)
            slots = []
            low_stock_count = 0
            for c in raw:
                enriched = _consumable_usage_fields(dict(c))
                is_low = c["stock"] <= c["threshold"] and c["threshold"] > 0
                enriched["is_low_stock"] = is_low
                if is_low:
                    low_stock_count += 1
                enriched["recent_replacements"] = []
                slots.append(enriched)
            printers_data.append({
                "asset_id": p["asset_id"],
                "asset_tag": p["asset_tag"],
                "printer_name": p["printer_name"],
                "printer_type": printer_type,
                "brand": p["brand"],
                "model": p["model"],
                "consumables": slots,
                "has_warning": low_stock_count > 0,
                "total_slots": len(slots),
                "low_stock_count": low_stock_count,
            })
    return render_template("admin/consumables.html", user=user,
                           printers_data=printers_data)


@app.route("/users")
def users_page():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/users.html", user=user)


@app.route("/employees")
def employees_page():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/employees.html", user=user)


# ---- 员工自助页面 ----

@app.route("/my/assets")
def my_assets():
    user = current_user()
    if not user:
        return redirect(url_for("login_page"))
    return render_template("employee/my_assets.html", user=user)


@app.route("/my/assets/<int:asset_id>")
def my_asset_detail(asset_id):
    user = current_user()
    if not user:
        return redirect(url_for("login_page"))
    return render_template("employee/asset_detail.html", user=user, asset_id=asset_id)


@app.route("/my/applications")
def my_applications():
    user = current_user()
    if not user:
        return redirect(url_for("login_page"))
    return render_template("employee/applications.html", user=user)


@app.route("/my/applications/new")
def my_application_new():
    user = current_user()
    if not user:
        return redirect(url_for("login_page"))
    return render_template("employee/application_form.html", user=user)


# ---- API: 认证 ----

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    employee_id = data.get("employee_id", "")
    password = data.get("password", "")
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM "user" WHERE employee_id = ?', (employee_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "用户不存在"}), 401
        user = dict(row)
        # 兼容哈希密码和明文密码（迁移期间）
        if user["password_hash"]:
            if "$" in user["password_hash"]:
                if not check_password_hash(user["password_hash"], password):
                    return jsonify({"error": "密码错误"}), 401
            elif user["password_hash"] != password:
                return jsonify({"error": "密码错误"}), 401
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        log_activity(conn, user["id"], "login", "user", user["id"], f"用户 {employee_id} 登录")
        return jsonify({"user": _user_dict(user)})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
def api_me():
    user = current_user()
    if not user:
        return jsonify({"error": "未登录"}), 401
    return jsonify({"user": _user_dict(user)})


# ---- API: 仪表盘统计 ----

@app.route("/api/stats")
def api_stats():
    db = get_db()
    with db.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM asset").fetchone()["c"]
        by_status = {}
        for row in conn.execute("SELECT status, COUNT(*) as c FROM asset GROUP BY status"):
            by_status[row["status"]] = row["c"]
        by_category = {}
        for row in conn.execute("SELECT category, COUNT(*) as c FROM asset GROUP BY category"):
            by_category[row["category"]] = row["c"]
        recent_events = []
        for row in conn.execute(
            """SELECT le.*, u.name as operator_name, a.asset_tag, a.name as asset_name
               FROM lifecycle_event le
               JOIN "user" u ON le.operator_id = u.id
               JOIN asset a ON le.asset_id = a.id
               ORDER BY le.created_at DESC LIMIT 10"""
        ):
            recent_events.append(dict(row))
        warranty_expiring = [_asset_dict(r) for r in conn.execute(
            """SELECT a.*, e.name as holder_name FROM asset a
               LEFT JOIN employee e ON a.current_holder_id = e.id
               WHERE a.warranty_date IS NOT NULL AND a.status != 'scrapped'
                 AND a.warranty_date <= date('now', '+30 days') AND a.warranty_date >= date('now')
               ORDER BY a.warranty_date""").fetchall()]
        warranty_expired = [_asset_dict(r) for r in conn.execute(
            """SELECT a.*, e.name as holder_name FROM asset a
               LEFT JOIN employee e ON a.current_holder_id = e.id
               WHERE a.warranty_date IS NOT NULL AND a.status != 'scrapped'
                 AND a.warranty_date < date('now')
               ORDER BY a.warranty_date""").fetchall()]
    return jsonify({
        "total": total,
        "in_stock": by_status.get("in_stock", 0),
        "assigned": by_status.get("assigned", 0),
        "maintenance": by_status.get("maintenance", 0),
        "scrapped": by_status.get("scrapped", 0),
        "by_category": by_category,
        "recent_events": recent_events,
        "warranty_expiring": warranty_expiring,
        "warranty_expired": warranty_expired,
    })


# ---- API: 批量导入 ----

@app.route("/api/assets/import", methods=["POST"])
def api_assets_import():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    if "file" not in request.files:
        return jsonify({"error": "未上传文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "文件名为空"}), 400

    raw = f.read().decode("utf-8-sig")  # utf-8-sig 自动处理 BOM
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        return jsonify({"error": "CSV 文件为空"}), 400

    required_cols = {"name", "category"}
    missing = required_cols - set(reader.fieldnames)
    if missing:
        return jsonify({"error": f"缺少必填列: {', '.join(missing)}"}), 400

    db = get_db()
    success = 0
    errors = []
    with db.get_conn() as conn:
        for i, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            category = (row.get("category") or "").strip()
            status = (row.get("status") or "").strip() or "in_stock"
            if not name or not category:
                errors.append({"row": i, "error": "名称或分类为空"})
                continue
            if category not in VALID_CATEGORIES:
                errors.append({"row": i, "error": f"无效分类: {category}"})
                continue
            if status not in VALID_STATUSES:
                errors.append({"row": i, "error": f"无效状态: {status}"})
                continue
            try:
                asset_tag = db.generate_asset_tag(conn, category)
                conn.execute(
                    """INSERT INTO asset (asset_tag, name, category, brand, model, serial_number,
                       status, location, purchase_date, purchase_price, notes, warranty_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        asset_tag, name, category,
                        (row.get("brand") or "").strip() or None,
                        (row.get("model") or "").strip() or None,
                        (row.get("serial_number") or "").strip() or None,
                        status,
                        (row.get("location") or "").strip() or None,
                        (row.get("purchase_date") or "").strip() or None,
                        row.get("purchase_price") or None,
                        (row.get("notes") or "").strip() or None,
                        (row.get("warranty_date") or "").strip() or None,
                    ),
                )
                asset_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, notes)
                       VALUES (?, 'stock_in', ?, ?)""",
                    (asset_id, user["id"], "批量导入"),
                )
                success += 1
            except Exception as e:
                errors.append({"row": i, "error": str(e)})
        if success > 0:
            log_activity(conn, user["id"], "import_csv", "asset", None,
                         f"导入 {success} 条资产，失败 {len(errors)} 条")

    return jsonify({"success": success, "errors": errors, "total": success + len(errors)})


# ---- API: 资产 CRUD ----

@app.route("/api/assets", methods=["GET"])
def api_assets_list():
    db = get_db()
    category = request.args.get("category")
    status = request.args.get("status")
    search = request.args.get("search")
    page, error = _parse_positive_int_arg("page", 1)
    if error:
        return error
    limit, error = _parse_positive_int_arg("limit", 20, max_value=200)
    if error:
        return error
    offset = (page - 1) * limit

    where_clauses = []
    params = []
    if category:
        where_clauses.append("a.category = ?")
        params.append(category)
    if status:
        where_clauses.append("a.status = ?")
        params.append(status)
    if search:
        where_clauses.append("(a.asset_tag LIKE ? OR a.name LIKE ? OR a.serial_number LIKE ? OR a.brand LIKE ?)")
        params.extend([f"%{search}%"] * 4)

    where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with db.get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) as c FROM asset a{where}", params).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT a.*, e.name as holder_name, e.department as holder_dept
                FROM asset a LEFT JOIN employee e ON a.current_holder_id = e.id
                {where} ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        assets = [_asset_dict(r) for r in rows]

    return jsonify({"total": total, "page": page, "limit": limit, "assets": assets})


@app.route("/api/assets", methods=["POST"])
def api_assets_create():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    required = ["name", "category"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"缺少必填字段: {f}"}), 400
    if data["category"] not in VALID_CATEGORIES:
        return jsonify({"error": f"无效的分类: {data['category']}"}), 400

    # Validate printer_type for printer assets
    printer_type = data.get("printer_type")
    if printer_type is not None:
        if data["category"] != "printer":
            return jsonify({"error": "printer_type 仅适用于打印机类资产"}), 400
        if printer_type not in VALID_PRINTER_TYPES:
            return jsonify({"error": f"无效的打印机类型: {printer_type}，可选: {', '.join(VALID_PRINTER_TYPES)}"}), 400

    db = get_db()
    with db.get_conn() as conn:
        asset_tag = db.generate_asset_tag(conn, data["category"])
        cursor = conn.execute(
            """INSERT INTO asset (asset_tag, name, category, brand, model, serial_number,
               status, location, purchase_date, purchase_price, notes, warranty_date, printer_type)
               VALUES (?, ?, ?, ?, ?, ?, 'in_stock', ?, ?, ?, ?, ?, ?)""",
            (
                asset_tag, data["name"], data["category"],
                data.get("brand"), data.get("model"), data.get("serial_number"),
                data.get("location"), data.get("purchase_date"), data.get("purchase_price"),
                data.get("notes"), data.get("warranty_date"), printer_type,
            ),
        )
        asset_id = cursor.lastrowid
        # 记录入库事件
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, notes)
               VALUES (?, 'stock_in', ?, ?)""",
            (asset_id, user["id"], data.get("notes")),
        )
        log_activity(conn, user["id"], "create_asset", "asset", asset_id, f"创建资产 {asset_tag}")
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
    return jsonify(_asset_dict(row)), 201


@app.route("/api/assets/<int:asset_id>", methods=["GET"])
def api_assets_get(asset_id):
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT a.*, e.name as holder_name, e.department as holder_dept
               FROM asset a LEFT JOIN employee e ON a.current_holder_id = e.id
               WHERE a.id = ?""",
            (asset_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "资产不存在"}), 404
        events = [dict(r) for r in conn.execute(
            """SELECT le.*, u.name as operator_name
               FROM lifecycle_event le JOIN "user" u ON le.operator_id = u.id
               WHERE le.asset_id = ? ORDER BY le.created_at""",
            (asset_id,),
        ).fetchall()]
        maintenance = [dict(r) for r in conn.execute(
            """SELECT mr.*, u.name as reporter_name
               FROM maintenance_record mr JOIN "user" u ON mr.reported_by = u.id
               WHERE mr.asset_id = ? ORDER BY mr.created_at DESC""",
            (asset_id,),
        ).fetchall()]
    result = _asset_dict(row)
    result["events"] = events
    result["maintenance_records"] = maintenance
    return jsonify(result)


@app.route("/api/assets/<int:asset_id>", methods=["PUT"])
def api_assets_update(asset_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
        if not row:
            return jsonify({"error": "资产不存在"}), 404
        current = dict(row)
        effective_category = data.get("category", current["category"])
        if "category" in data and effective_category not in VALID_CATEGORIES:
            return jsonify({"error": f"无效的分类: {effective_category}"}), 400
        fields = []
        params = []
        for col in ["name", "brand", "model", "serial_number", "location",
                     "purchase_date", "purchase_price", "notes", "category", "warranty_date"]:
            if col in data:
                fields.append(f"{col} = ?")
                params.append(data[col])
        # printer_type validation
        if "printer_type" in data:
            pt = data["printer_type"]
            if effective_category != "printer":
                return jsonify({"error": "printer_type 仅适用于打印机类资产"}), 400
            if pt is not None and pt not in VALID_PRINTER_TYPES:
                return jsonify({"error": f"无效的打印机类型: {pt}，可选: {', '.join(VALID_PRINTER_TYPES)}"}), 400
            fields.append("printer_type = ?")
            params.append(pt)
        elif "category" in data and effective_category != "printer" and current.get("printer_type") is not None:
            fields.append("printer_type = ?")
            params.append(None)
        if fields:
            fields.append("updated_at = CURRENT_TIMESTAMP")
            conn.execute(f"UPDATE asset SET {', '.join(fields)} WHERE id = ?",
                         params + [asset_id])
            log_activity(conn, user["id"], "update_asset", "asset", asset_id,
                         f"更新字段: {', '.join(fields)}")
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
    return jsonify(_asset_dict(row))


@app.route("/api/assets/<int:asset_id>", methods=["DELETE"])
def api_assets_delete(asset_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
        if not row:
            return jsonify({"error": "资产不存在"}), 404
        if dict(row)["status"] != "in_stock":
            return jsonify({"error": "只能删除库存中的资产"}), 400
        log_activity(conn, user["id"], "delete_asset", "asset", asset_id, f"删除资产 {dict(row)['asset_tag']}")
        conn.execute("DELETE FROM lifecycle_event WHERE asset_id = ?", (asset_id,))
        conn.execute("DELETE FROM maintenance_record WHERE asset_id = ?", (asset_id,))
        conn.execute("DELETE FROM asset WHERE id = ?", (asset_id,))
    return jsonify({"ok": True})


# ---- API: 生命周期操作 ----

@app.route("/api/assets/<int:asset_id>/assign", methods=["POST"])
def api_assign(asset_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    target_employee_id = data.get("target_employee_id")
    if not target_employee_id:
        return jsonify({"error": "缺少 target_employee_id"}), 400
    db = get_db()
    with db.get_conn() as conn:
        asset = _get_asset_for_update(conn, asset_id, "assign")
        if isinstance(asset, tuple):
            return asset
        emp = conn.execute("SELECT id FROM employee WHERE id = ?", (target_employee_id,)).fetchone()
        if not emp:
            return jsonify({"error": "员工不存在"}), 400
        conn.execute(
            "UPDATE asset SET status = 'assigned', current_holder_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (target_employee_id, asset_id),
        )
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, target_user_id, target_employee_id, notes)
               VALUES (?, 'assign', ?, ?, ?, ?)""",
            (asset_id, user["id"], None, target_employee_id, data.get("notes")),
        )
        log_activity(conn, user["id"], "assign", "asset", asset_id, f"分配给员工ID {target_employee_id}")
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
    return jsonify(_asset_dict(row))


@app.route("/api/assets/<int:asset_id>/return", methods=["POST"])
def api_return(asset_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    db = get_db()
    with db.get_conn() as conn:
        asset = _get_asset_for_update(conn, asset_id, "return")
        if isinstance(asset, tuple):
            return asset
        conn.execute(
            "UPDATE asset SET status = 'in_stock', current_holder_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (asset_id,),
        )
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, from_location, notes)
               VALUES (?, 'return', ?, ?, ?)""",
            (asset_id, user["id"], asset["location"], data.get("notes")),
        )
        log_activity(conn, user["id"], "return", "asset", asset_id, "归还资产")
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
    return jsonify(_asset_dict(row))


@app.route("/api/assets/<int:asset_id>/transfer", methods=["POST"])
def api_transfer(asset_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    target_employee_id = data.get("target_employee_id")
    if not target_employee_id:
        return jsonify({"error": "缺少 target_employee_id"}), 400
    db = get_db()
    with db.get_conn() as conn:
        asset = _get_asset_for_update(conn, asset_id, "transfer")
        if isinstance(asset, tuple):
            return asset
        emp = conn.execute("SELECT id FROM employee WHERE id = ?", (target_employee_id,)).fetchone()
        if not emp:
            return jsonify({"error": "员工不存在"}), 400
        conn.execute(
            "UPDATE asset SET current_holder_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (target_employee_id, asset_id),
        )
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, target_user_id, target_employee_id, notes)
               VALUES (?, 'transfer', ?, ?, ?, ?)""",
            (asset_id, user["id"], None, target_employee_id, data.get("notes")),
        )
        log_activity(conn, user["id"], "transfer", "asset", asset_id, f"转移给员工ID {target_employee_id}")
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
    return jsonify(_asset_dict(row))


@app.route("/api/assets/<int:asset_id>/maintenance", methods=["POST"])
def api_maintenance_start(asset_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    if not data.get("description"):
        return jsonify({"error": "缺少故障描述"}), 400
    db = get_db()
    with db.get_conn() as conn:
        asset = _get_asset_for_update(conn, asset_id, "maintenance_start")
        if isinstance(asset, tuple):
            return asset
        conn.execute(
            "UPDATE asset SET status = 'maintenance', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (asset_id,),
        )
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, notes)
               VALUES (?, 'maintenance_start', ?, ?)""",
            (asset_id, user["id"], data.get("description")),
        )
        cursor = conn.execute(
            """INSERT INTO maintenance_record (asset_id, reported_by, description, status)
               VALUES (?, ?, ?, 'in_progress')""",
            (asset_id, user["id"], data["description"]),
        )
        record_id = cursor.lastrowid
        log_activity(conn, user["id"], "maintenance_start", "asset", asset_id, data.get("description"))
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
    result = _asset_dict(row)
    result["maintenance_record_id"] = record_id
    return jsonify(result)


@app.route("/api/assets/<int:asset_id>/maintenance/<int:record_id>/resolve", methods=["POST"])
def api_maintenance_resolve(asset_id, record_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    return_to_stock = data.get("return_to_stock", False)
    db = get_db()
    with db.get_conn() as conn:
        asset = _get_asset_for_update(conn, asset_id, "maintenance_end")
        if isinstance(asset, tuple):
            return asset
        record = conn.execute(
            "SELECT * FROM maintenance_record WHERE id = ? AND asset_id = ?",
            (record_id, asset_id),
        ).fetchone()
        if not record:
            return jsonify({"error": "维修记录不存在"}), 404
        conn.execute(
            """UPDATE maintenance_record SET status = 'resolved', cost = ?, repair_notes = ?,
               resolved_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (data.get("cost"), data.get("repair_notes"), record_id),
        )
        if return_to_stock:
            new_status = "in_stock"
            new_holder = None
        else:
            new_status = "assigned"
            new_holder = asset["current_holder_id"]
        conn.execute(
            "UPDATE asset SET status = ?, current_holder_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, new_holder, asset_id),
        )
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, notes)
               VALUES (?, 'maintenance_end', ?, ?)""",
            (asset_id, user["id"], data.get("repair_notes")),
        )
        log_activity(conn, user["id"], "maintenance_end", "asset", asset_id, data.get("repair_notes"))
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
    return jsonify(_asset_dict(row))


@app.route("/api/assets/<int:asset_id>/scrap", methods=["POST"])
def api_scrap(asset_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    db = get_db()
    with db.get_conn() as conn:
        asset = _get_asset_for_update(conn, asset_id, "scrap")
        if isinstance(asset, tuple):
            return asset
        conn.execute(
            "UPDATE asset SET status = 'scrapped', current_holder_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (asset_id,),
        )
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, notes)
               VALUES (?, 'scrap', ?, ?)""",
            (asset_id, user["id"], data.get("notes")),
        )
        log_activity(conn, user["id"], "scrap", "asset", asset_id, data.get("notes"))
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
    return jsonify(_asset_dict(row))


# ---- API: 生命周期事件 ----

@app.route("/api/assets/<int:asset_id>/events")
def api_asset_events(asset_id):
    db = get_db()
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT le.*, u.name as operator_name, e.name as target_employee_name
               FROM lifecycle_event le
               JOIN "user" u ON le.operator_id = u.id
               LEFT JOIN employee e ON le.target_employee_id = e.id
               WHERE le.asset_id = ? ORDER BY le.created_at""",
            (asset_id,),
        ).fetchall()
    return jsonify({"events": [dict(r) for r in rows]})


# ---- API: 维修记录 ----

@app.route("/api/maintenance")
def api_maintenance_list():
    db = get_db()
    status = request.args.get("status")
    with db.get_conn() as conn:
        q = """SELECT mr.*, a.asset_tag, a.name as asset_name, u.name as reporter_name
               FROM maintenance_record mr
               JOIN asset a ON mr.asset_id = a.id
               JOIN "user" u ON mr.reported_by = u.id"""
        params = []
        if status:
            q += " WHERE mr.status = ?"
            params.append(status)
        q += " ORDER BY mr.created_at DESC"
        rows = conn.execute(q, params).fetchall()
    return jsonify({"records": [dict(r) for r in rows]})


@app.route("/api/assets/<int:asset_id>/maintenance")
def api_asset_maintenance(asset_id):
    db = get_db()
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT mr.*, u.name as reporter_name
               FROM maintenance_record mr JOIN "user" u ON mr.reported_by = u.id
               WHERE mr.asset_id = ? ORDER BY mr.created_at DESC""",
            (asset_id,),
        ).fetchall()
    return jsonify({"records": [dict(r) for r in rows]})


# ---- API: 资产申请 ----

@app.route("/api/applications", methods=["GET"])
def api_applications_list():
    db = get_db()
    status = request.args.get("status")
    user = current_user()
    with db.get_conn() as conn:
        q = """SELECT aa.*, u.name as applicant_name, u.department as applicant_dept,
               a.name as admin_name
               FROM asset_application aa
               JOIN "user" u ON aa.applicant_id = u.id
               LEFT JOIN "user" a ON aa.admin_id = a.id"""
        params = []
        clauses = []
        if status:
            clauses.append("aa.status = ?")
            params.append(status)
        if user and user["role"] == "employee":
            clauses.append("aa.applicant_id = ?")
            params.append(user["id"])
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY aa.created_at DESC"
        rows = conn.execute(q, params).fetchall()
    return jsonify({"applications": [dict(r) for r in rows]})


@app.route("/api/applications", methods=["POST"])
def api_applications_create():
    user = current_user()
    if not user:
        return jsonify({"error": "未登录"}), 401
    data = request.get_json() or {}
    if not data.get("reason"):
        return jsonify({"error": "缺少申请理由"}), 400
    db = get_db()
    with db.get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO asset_application (applicant_id, asset_category, reason)
               VALUES (?, ?, ?)""",
            (user["id"], data.get("asset_category"), data["reason"]),
        )
        app_id = cursor.lastrowid
        row = conn.execute(
            """SELECT aa.*, u.name as applicant_name FROM asset_application aa
               JOIN "user" u ON aa.applicant_id = u.id WHERE aa.id = ?""",
            (app_id,),
        ).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/applications/<int:app_id>/approve", methods=["PUT"])
def api_applications_approve(app_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM asset_application WHERE id = ?", (app_id,)).fetchone()
        if not row:
            return jsonify({"error": "申请不存在"}), 404
        if dict(row)["status"] != "pending":
            return jsonify({"error": "申请已被处理"}), 400
        conn.execute(
            """UPDATE asset_application SET status = 'approved', admin_id = ?,
               admin_notes = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (user["id"], data.get("admin_notes"), app_id),
        )
        log_activity(conn, user["id"], "approve_application", "application", app_id, data.get("admin_notes"))
        row = conn.execute(
            """SELECT aa.*, u.name as applicant_name FROM asset_application aa
               JOIN "user" u ON aa.applicant_id = u.id WHERE aa.id = ?""",
            (app_id,),
        ).fetchone()
    return jsonify(dict(row))


@app.route("/api/applications/<int:app_id>/reject", methods=["PUT"])
def api_applications_reject(app_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM asset_application WHERE id = ?", (app_id,)).fetchone()
        if not row:
            return jsonify({"error": "申请不存在"}), 404
        if dict(row)["status"] != "pending":
            return jsonify({"error": "申请已被处理"}), 400
        conn.execute(
            """UPDATE asset_application SET status = 'rejected', admin_id = ?,
               admin_notes = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (user["id"], data.get("admin_notes"), app_id),
        )
        log_activity(conn, user["id"], "reject_application", "application", app_id, data.get("admin_notes"))
        row = conn.execute(
            """SELECT aa.*, u.name as applicant_name FROM asset_application aa
               JOIN "user" u ON aa.applicant_id = u.id WHERE aa.id = ?""",
            (app_id,),
        ).fetchone()
    return jsonify(dict(row))


# ---- API: 员工自助 ----

@app.route("/api/my/assets")
def api_my_assets():
    user = current_user()
    if not user:
        return jsonify({"error": "未登录"}), 401
    db = get_db()
    search = request.args.get("search")
    with db.get_conn() as conn:
        emp = conn.execute("SELECT id FROM employee WHERE employee_id = ?", (_employee_id_for_user(user),)).fetchone()
        if not emp:
            return jsonify({"assets": []})
        q = """SELECT a.*, e.name as holder_name FROM asset a
               LEFT JOIN employee e ON a.current_holder_id = e.id
               WHERE a.current_holder_id = ?"""
        params = [emp["id"]]
        if search:
            q += " AND (a.asset_tag LIKE ? OR a.name LIKE ?)"
            params.extend([f"%{search}%"] * 2)
        q += " ORDER BY a.created_at DESC"
        rows = conn.execute(q, params).fetchall()
    return jsonify({"assets": [_asset_dict(r) for r in rows]})


@app.route("/api/my/applications")
def api_my_applications():
    user = current_user()
    if not user:
        return jsonify({"error": "未登录"}), 401
    db = get_db()
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT aa.*, a.name as admin_name FROM asset_application aa
               LEFT JOIN "user" a ON aa.admin_id = a.id
               WHERE aa.applicant_id = ? ORDER BY aa.created_at DESC""",
            (user["id"],),
        ).fetchall()
    return jsonify({"applications": [dict(r) for r in rows]})


@app.route("/api/my/applications", methods=["POST"])
def api_my_applications_create():
    user = current_user()
    if not user:
        return jsonify({"error": "未登录"}), 401
    data = request.get_json() or {}
    if not data.get("reason"):
        return jsonify({"error": "缺少申请理由"}), 400
    db = get_db()
    with db.get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO asset_application (applicant_id, asset_category, reason)
               VALUES (?, ?, ?)""",
            (user["id"], data.get("asset_category"), data["reason"]),
        )
        app_id = cursor.lastrowid
        row = conn.execute(
            """SELECT aa.*, u.name as applicant_name FROM asset_application aa
               JOIN "user" u ON aa.applicant_id = u.id WHERE aa.id = ?""",
            (app_id,),
        ).fetchone()
    return jsonify(dict(row)), 201

# ---- API: 标签 / 二维码 ----

@app.route("/api/assets/<int:asset_id>/qr")
def api_asset_qr(asset_id):
    import io
    import qrcode
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
        if not row:
            return jsonify({"error": "资产不存在"}), 404
    host = request.host_url.rstrip("/")
    qr_base = get_db().get_config("qr_base_url", host)
    qr_url = f"{qr_base}/scan/{asset_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    from flask import send_file
    return send_file(buf, mimetype="image/png")


@app.route("/api/batch-labels", methods=["POST"])
def api_batch_labels():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    asset_ids = data.get("asset_ids", [])
    if not asset_ids:
        return jsonify({"error": "未选择资产"}), 400
    if not isinstance(asset_ids, list):
        return jsonify({"error": "asset_ids 必须是数组"}), 400
    try:
        asset_ids = [int(aid) for aid in asset_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "asset_ids 必须是数字 ID 数组"}), 400
    if len(set(asset_ids)) != len(asset_ids):
        return jsonify({"error": "asset_ids 不能重复"}), 400
    db = get_db()
    with db.get_conn() as conn:
        placeholders = ",".join("?" * len(asset_ids))
        rows = conn.execute(
            f"SELECT * FROM asset WHERE id IN ({placeholders})", asset_ids
        ).fetchall()
        found_ids = {row["id"] for row in rows}
        missing_ids = [aid for aid in asset_ids if aid not in found_ids]
        if missing_ids:
            return jsonify({"error": f"资产不存在: {', '.join(map(str, missing_ids))}"}), 400
        assets_by_id = {row["id"]: _asset_dict(row) for row in rows}
        assets = [assets_by_id[aid] for aid in asset_ids]
        # 记录打印事件
        for aid in asset_ids:
            conn.execute(
                """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, notes)
                   VALUES (?, 'label_print', ?, '批量打印标签')""",
                (aid, user["id"]),
            )
            log_activity(conn, user["id"], "label_print", "asset", aid, "批量打印标签")
    return jsonify({"assets": assets})


# ---- 辅助函数 ----

def _get_asset_for_update(conn, asset_id, event_type):
    """获取资产并校验状态转换合法性，返回 (asset_dict) 或 (json_response, status_code)"""
    row = conn.execute("SELECT * FROM asset WHERE id = ?", (asset_id,)).fetchone()
    if not row:
        return jsonify({"error": "资产不存在"}), 404
    asset = dict(row)
    allowed = STATE_TRANSITIONS.get(asset["status"], [])
    if event_type not in allowed:
        return jsonify({"error": f"当前状态 '{asset['status']}' 不允许执行 '{event_type}' 操作"}), 400
    return asset


def _user_dict(row):
    return {
        "id": row["id"], "employee_id": row["employee_id"], "name": row["name"],
        "department": row["department"], "phone": row["phone"], "email": row["email"],
        "role": row["role"],
    }


def _asset_dict(row):
    d = dict(row)
    d.pop("password_hash", None)
    return d


def _public_asset_dict(row):
    return {
        "id": row["id"],
        "asset_tag": row["asset_tag"],
        "name": row["name"],
        "category": row["category"],
        "status": row["status"],
    }


# ---- API: 分类元数据 ----

@app.route("/api/categories")
def api_categories():
    return jsonify({"categories": get_categories_meta()})


# ---- API: 标签配置 ----

def _label_settings_payload(fields):
    return {
        "fields": fields,
        "options": [
            {"key": key, **meta}
            for key, meta in LABEL_FIELD_OPTIONS.items()
        ],
        "fixed_fields": LABEL_FIXED_FIELDS,
        "max_fields": LABEL_FIELDS_MAX,
    }


def _normalize_label_fields(raw_fields):
    if not isinstance(raw_fields, list):
        return LABEL_FIELDS_DEFAULT
    fields = []
    for field in raw_fields:
        if field in LABEL_FIELD_OPTIONS and field not in fields:
            fields.append(field)
        if len(fields) >= LABEL_FIELDS_MAX:
            break
    if fields:
        return fields
    return [] if not raw_fields else LABEL_FIELDS_DEFAULT


@app.route("/api/settings/label", methods=["GET"])
def api_label_settings():
    db = get_db()
    raw = db.get_config("label_fields")
    fields = LABEL_FIELDS_DEFAULT
    if raw:
        try:
            loaded = json.loads(raw)
            fields = _normalize_label_fields(loaded)
        except json.JSONDecodeError:
            fields = LABEL_FIELDS_DEFAULT
    return jsonify(_label_settings_payload(fields))


@app.route("/api/settings/label", methods=["PUT"])
def api_label_settings_update():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    fields = data.get("fields", [])
    if not isinstance(fields, list):
        return jsonify({"error": "fields 必须是数组"}), 400
    fields = _normalize_label_fields(fields)
    db = get_db()
    with db.get_conn() as conn:
        db.set_config("label_fields", json.dumps(fields), conn=conn)
        log_activity(conn, user["id"], "update_settings", "config", None, f"标签字段: {', '.join(fields)}")
    return jsonify(_label_settings_payload(fields))


# ---- API: QR 基础地址 ----

@app.route("/api/settings/qr-base-url", methods=["GET"])
def api_qr_base_url():
    db = get_db()
    url = db.get_config("qr_base_url", request.host_url.rstrip("/"))
    return jsonify({"qr_base_url": url})


@app.route("/api/settings/qr-base-url", methods=["PUT"])
def api_qr_base_url_update():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    url = data.get("url", "").rstrip("/")
    if not url:
        return jsonify({"error": "URL 不能为空"}), 400
    db = get_db()
    with db.get_conn() as conn:
        db.set_config("qr_base_url", url, conn=conn)
        log_activity(conn, user["id"], "update_settings", "config", None, f"QR 地址: {url}")
    return jsonify({"qr_base_url": url})


# ---- API: Logo 上传 ----

@app.route("/api/settings/logo", methods=["GET"])
def api_logo():
    db = get_db()
    logo = db.get_config("company_logo", "")
    return jsonify({"logo": logo})


@app.route("/api/settings/logo", methods=["POST"])
def api_logo_upload():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    if "file" not in request.files:
        return jsonify({"error": "未上传文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "文件名为空"}), 400
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp"}
    import os as _os
    ext = _os.path.splitext(f.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"error": f"不支持的格式 {ext}，仅支持 {', '.join(allowed)}"}), 400
    save_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "static", "uploads")
    _os.makedirs(save_dir, exist_ok=True)
    save_path = _os.path.join(save_dir, "company_logo" + ext)
    f.save(save_path)
    logo_url = f"/static/uploads/company_logo{ext}"
    db = get_db()
    with db.get_conn() as conn:
        db.set_config("company_logo", logo_url, conn=conn)
        log_activity(conn, user["id"], "update_settings", "config", None, "上传企业Logo")
    return jsonify({"logo": logo_url})


@app.route("/api/settings/logo", methods=["DELETE"])
def api_logo_delete():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    logo = db.get_config("company_logo", "")
    if logo:
        import os as _os
        file_path = _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)), logo.lstrip("/")
        )
        if _os.path.exists(file_path):
            _os.unlink(file_path)
    db.set_config("company_logo", "")
    return jsonify({"ok": True})


# ---- API: CSV 导出 ----

@app.route("/api/assets/export")
def api_assets_export():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    category = request.args.get("category")
    status = request.args.get("status")
    search = request.args.get("search")
    asset_ids = request.args.get("ids")

    where_clauses = []
    params = []
    if category:
        where_clauses.append("a.category = ?")
        params.append(category)
    if status:
        where_clauses.append("a.status = ?")
        params.append(status)
    if search:
        where_clauses.append("(a.asset_tag LIKE ? OR a.name LIKE ? OR a.serial_number LIKE ? OR a.brand LIKE ?)")
        params.extend([f"%{search}%"] * 4)
    if asset_ids:
        id_list = [int(x) for x in asset_ids.split(",") if x.strip().isdigit()]
        if id_list:
            placeholders = ",".join("?" * len(id_list))
            where_clauses.append(f"a.id IN ({placeholders})")
            params.extend(id_list)

    where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    db = get_db()
    qr_base = db.get_config("qr_base_url", request.host_url.rstrip("/"))

    with db.get_conn() as conn:
        rows = conn.execute(
            f"""SELECT a.*, e.name as holder_name, e.department as holder_dept
                FROM asset a LEFT JOIN employee e ON a.current_holder_id = e.id
                {where} ORDER BY a.asset_tag""",
            params,
        ).fetchall()

        log_activity(conn, user["id"], "export_csv", "asset", None,
                     f"导出 {len(rows)} 条资产")

    output = io.StringIO()
    output.write('﻿')  # UTF-8 BOM，确保 Excel/BarTender 正确识别中文
    writer = csv.writer(output)
    writer.writerow([
        "asset_tag", "name", "category", "brand", "model",
        "serial_number", "status", "holder_name", "location",
        "purchase_date", "purchase_price", "warranty_date", "qr_url",
    ])
    for row in rows:
        a = dict(row)
        writer.writerow([
            a["asset_tag"], a["name"], a["category"], a["brand"], a["model"],
            a["serial_number"], a["status"], a.get("holder_name", ""),
            a["location"], a["purchase_date"], a["purchase_price"],
            a.get("warranty_date", ""), f"{qr_base}/scan/{a['id']}",
        ])

    return Response(
        output.getvalue().encode("utf-8"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=assets_export.csv"},
    )


# ---- API: 操作记录 ----

@app.route("/api/activity")
def api_activity():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    action = request.args.get("action")
    page, error = _parse_positive_int_arg("page", 1)
    if error:
        return error
    limit, error = _parse_positive_int_arg("limit", 30, max_value=200)
    if error:
        return error
    offset = (page - 1) * limit

    where_clauses = []
    params = []
    if action:
        where_clauses.append("al.action = ?")
        params.append(action)

    where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with db.get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) as c FROM activity_log al{where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT al.*, u.name as user_name
                FROM activity_log al LEFT JOIN "user" u ON al.user_id = u.id
                {where} ORDER BY al.created_at DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    return jsonify({"total": total, "page": page, "logs": [dict(r) for r in rows]})


# ---- API: 公开资产信息（扫码用）----

@app.route("/api/public/asset/<int:asset_id>")
def api_public_asset(asset_id):
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT id, asset_tag, name, category, status
               FROM asset
               WHERE id = ?""",
            (asset_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "资产不存在"}), 404
    return jsonify(_public_asset_dict(row))


@app.route("/api/public/asset-lookup")
def api_public_asset_lookup():
    asset_tag = (request.args.get("asset_tag") or request.args.get("tag") or "").strip()
    if not asset_tag:
        return jsonify({"error": "缺少 asset_tag"}), 400
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT id, asset_tag, name, category, status
               FROM asset
               WHERE asset_tag = ? COLLATE NOCASE""",
            (asset_tag,),
        ).fetchone()
        if not row:
            return jsonify({"error": "资产不存在"}), 404
    return jsonify(_public_asset_dict(row))


# ---- 页面路由：新功能 ----

@app.route("/settings")
def settings_page():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/settings.html", user=user)


@app.route("/activity")
def activity_page():
    user = require_role("admin")
    if not user:
        return redirect(url_for("login_page"))
    return render_template("admin/activity.html", user=user)


@app.route("/scan")
def scan_camera_page():
    user = current_user()
    return render_template("scan_camera.html", user=user)


@app.route("/scan/<int:asset_id>")
def scan_page(asset_id):
    return render_template("scan.html", asset_id=asset_id)


# ---- API: 打印机耗材管理 ----

@app.route("/api/consumables", methods=["GET"])
def api_consumables_list():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    ctype = request.args.get("type")
    asset_id = request.args.get("asset_id")
    low_stock = request.args.get("low_stock", "").lower() == "true"

    where_clauses = []
    params = []
    if ctype:
        where_clauses.append("pc.type = ?")
        params.append(ctype)
    if asset_id:
        try:
            asset_id_int = int(asset_id)
        except ValueError:
            return jsonify({"error": "asset_id 必须是整数"}), 400
        where_clauses.append("pc.asset_id = ?")
        params.append(asset_id_int)
    if low_stock:
        where_clauses.append("pc.stock <= pc.threshold")

    where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with db.get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) as c FROM printer_consumable pc{where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT pc.*, a.asset_tag as printer_tag, a.name as printer_name
                FROM printer_consumable pc
                LEFT JOIN asset a ON pc.asset_id = a.id
                {where} ORDER BY pc.created_at DESC""",
            params,
        ).fetchall()
        consumables = [_consumable_usage_fields(r) for r in rows]
    return jsonify({"total": total, "consumables": consumables})


@app.route("/api/consumables", methods=["POST"])
def api_consumables_create():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}

    ctype = data.get("type", "toner")
    if ctype != "toner":
        return jsonify({"error": f"墨粉管理只支持 toner 类型，收到: {ctype}"}), 400

    # Validate model (toner source: 原装/国产)
    cmodel = data.get("model")
    if cmodel is not None and cmodel not in VALID_TONER_MODELS:
        return jsonify({"error": f"无效的墨粉型号: {cmodel}，可选: {', '.join(VALID_TONER_MODELS)}"}), 400

    stock, err = _validate_non_negative_int(data, "stock")
    if err:
        return err
    threshold, err = _validate_non_negative_int(data, "threshold")
    if err:
        return err
    price, err = _validate_non_negative_number(data, "current_price")
    if err:
        return err
    installed_at_raw = data.get("installed_at")
    if installed_at_raw is not None:
        _, date_err = _parse_iso_date(installed_at_raw, "installed_at")
        if date_err:
            return date_err

    asset_id = data.get("asset_id")

    # Validate color for toner
    color = data.get("color")
    if color is not None and color not in VALID_TONER_COLORS:
        return jsonify({"error": f"无效的墨粉颜色: {color}，可选: {', '.join(VALID_TONER_COLORS)}"}), 400

    db = get_db()
    with db.get_conn() as conn:
        ok, err = _validate_printer_asset_id(conn, asset_id)
        if not ok:
            return err
        # Validate color against printer type
        if asset_id is not None and color is not None and color != "black":
            ok, err = _validate_toner_color_for_printer(conn, asset_id, color)
            if not ok:
                return err

        # Auto-generate name if not provided: "打印机名 - 颜色"
        name = data.get("name", "").strip()
        if not name:
            printer_row = conn.execute("SELECT name FROM asset WHERE id = ?", (asset_id,)).fetchone() if asset_id else None
            printer_name = printer_row["name"] if printer_row else "未知打印机"
            color_label = _TONER_COLOR_LABELS.get(color, color or "未知")
            name = f"{printer_name} - {color_label}"

        cursor = conn.execute(
            """INSERT INTO printer_consumable
               (name, type, stock, threshold, asset_id, unit, color, model, current_price, installed_at, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name, ctype,
                stock if stock is not None else 0, threshold if threshold is not None else 0,
                asset_id, data.get("unit", "个"),
                color, data.get("model"), price if price is not None else data.get("current_price"),
                data.get("installed_at"), data.get("notes"),
            ),
        )
        cid = cursor.lastrowid
        log_activity(conn, user["id"], "create_consumable", "consumable", cid,
                     f"创建耗材 {name}")
        row = conn.execute(
            """SELECT pc.*, a.asset_tag as printer_tag, a.name as printer_name
               FROM printer_consumable pc
               LEFT JOIN asset a ON pc.asset_id = a.id
               WHERE pc.id = ?""", (cid,),
        ).fetchone()
    return jsonify(_consumable_usage_fields(row)), 201


@app.route("/api/consumables/<int:consumable_id>", methods=["GET"])
def api_consumables_get(consumable_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT pc.*, a.asset_tag as printer_tag, a.name as printer_name
               FROM printer_consumable pc
               LEFT JOIN asset a ON pc.asset_id = a.id
               WHERE pc.id = ?""", (consumable_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "耗材不存在"}), 404
    return jsonify(_consumable_usage_fields(row))


@app.route("/api/consumables/<int:consumable_id>", methods=["PUT"])
def api_consumables_update(consumable_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}

    # Validate type if provided — only toner allowed
    if "type" in data and data["type"] != "toner":
        return jsonify({"error": f"墨粉管理只支持 toner 类型，收到: {data['type']}"}), 400

    # Validate model if provided
    if "model" in data and data["model"] is not None and data["model"] not in VALID_TONER_MODELS:
        return jsonify({"error": f"无效的墨粉型号: {data['model']}，可选: {', '.join(VALID_TONER_MODELS)}"}), 400

    # Validate color if provided
    if "color" in data and data["color"] is not None and data["color"] not in VALID_TONER_COLORS:
        return jsonify({"error": f"无效的墨粉颜色: {data['color']}，可选: {', '.join(VALID_TONER_COLORS)}"}), 400

    # Validate numeric fields
    for field in ["stock", "threshold"]:
        if field in data:
            val, err = _validate_non_negative_int(data, field)
            if err:
                return err
    if "current_price" in data:
        val, err = _validate_non_negative_number(data, "current_price")
        if err:
            return err
    if "installed_at" in data:
        _, date_err = _parse_iso_date(data["installed_at"], "installed_at")
        if date_err:
            return date_err

    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM printer_consumable WHERE id = ?", (consumable_id,)).fetchone()
        if not row:
            return jsonify({"error": "耗材不存在"}), 404

        # Validate asset_id if provided
        if "asset_id" in data:
            ok, err = _validate_printer_asset_id(conn, data["asset_id"])
            if not ok:
                return err

        # Validate color against printer type (for updates that change color)
        if "color" in data and data["color"] is not None and data["color"] != "black":
            effective_asset_id = data.get("asset_id", dict(row).get("asset_id"))
            if effective_asset_id is not None:
                ok, err = _validate_toner_color_for_printer(conn, effective_asset_id, data["color"])
                if not ok:
                    return err

        fields = []
        params = []
        for col in ["name", "type", "stock", "threshold", "asset_id", "unit", "color", "model", "current_price", "installed_at", "notes"]:
            if col in data:
                fields.append(f"{col} = ?")
                params.append(data[col])
        if fields:
            conn.execute(
                f"UPDATE printer_consumable SET {', '.join(fields)} WHERE id = ?",
                params + [consumable_id],
            )
            log_activity(conn, user["id"], "update_consumable", "consumable", consumable_id,
                         f"更新字段: {', '.join(fields)}")
        row = conn.execute(
            """SELECT pc.*, a.asset_tag as printer_tag, a.name as printer_name
               FROM printer_consumable pc
               LEFT JOIN asset a ON pc.asset_id = a.id
               WHERE pc.id = ?""", (consumable_id,),
        ).fetchone()
    return jsonify(_consumable_usage_fields(row))


@app.route("/api/consumables/<int:consumable_id>", methods=["DELETE"])
def api_consumables_delete(consumable_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM printer_consumable WHERE id = ?", (consumable_id,)).fetchone()
        if not row:
            return jsonify({"error": "耗材不存在"}), 404
        log_activity(conn, user["id"], "delete_consumable", "consumable", consumable_id,
                     f"删除耗材 {dict(row)['name']}")
        conn.execute("DELETE FROM printer_consumable WHERE id = ?", (consumable_id,))
    return jsonify({"ok": True})


@app.route("/api/consumables/<int:consumable_id>/adjust", methods=["POST"])
def api_consumables_adjust(consumable_id):
    """库存调整：delta 正数加库存，负数减库存"""
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    delta = data.get("delta")
    if delta is None or not isinstance(delta, int):
        return jsonify({"error": "delta 必须是整数"}), 400
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM printer_consumable WHERE id = ?", (consumable_id,)).fetchone()
        if not row:
            return jsonify({"error": "耗材不存在"}), 404
        new_stock = dict(row)["stock"] + delta
        if new_stock < 0:
            return jsonify({"error": "库存不能低于 0"}), 400
        conn.execute(
            "UPDATE printer_consumable SET stock = ? WHERE id = ?",
            (new_stock, consumable_id),
        )
        log_activity(conn, user["id"], "adjust_stock", "consumable", consumable_id,
                     f"库存调整: {dict(row)['stock']} -> {new_stock} (delta={delta})")
        row = conn.execute(
            """SELECT pc.*, a.asset_tag as printer_tag, a.name as printer_name
               FROM printer_consumable pc
               LEFT JOIN asset a ON pc.asset_id = a.id
               WHERE pc.id = ?""", (consumable_id,),
        ).fetchone()
    return jsonify(_consumable_usage_fields(row))


@app.route("/api/consumables/<int:consumable_id>/replace", methods=["POST"])
def api_consumables_replace(consumable_id):
    """更替当前耗材：归档旧周期，重置当前价格/安装日期，可选扣减备用库存。"""
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    replaced_at = data.get("replaced_at") or date.today().isoformat()
    new_installed_at = data.get("new_installed_at") or replaced_at
    replaced_date, error = _parse_iso_date(replaced_at, "replaced_at")
    if error:
        return error
    new_installed_date, error = _parse_iso_date(new_installed_at, "new_installed_at")
    if error:
        return error

    # Validate new_price if provided
    new_price_raw = data.get("new_price")
    if new_price_raw is not None:
        new_price_val, price_err = _validate_non_negative_number(data, "new_price")
        if price_err:
            return price_err

    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM printer_consumable WHERE id = ?", (consumable_id,)).fetchone()
        if not row:
            return jsonify({"error": "耗材不存在"}), 404
        consumable = dict(row)
        if data.get("use_stock") and consumable["stock"] <= 0:
            return jsonify({"error": "备用库存不足，不能从库存取用"}), 400

        old_installed_at = consumable.get("installed_at")
        old_installed_date, error = _parse_iso_date(old_installed_at, "installed_at")
        if error:
            return error
        usage_days = 1
        if old_installed_date:
            usage_days = max((replaced_date - old_installed_date).days, 1)
        price = consumable.get("current_price")
        daily_cost = round(float(price) / usage_days, 2) if price is not None else None
        new_price = data.get("new_price")
        new_stock = consumable["stock"] - 1 if data.get("use_stock") else consumable["stock"]

        cursor = conn.execute(
            """INSERT INTO consumable_replacement
               (consumable_id, asset_id_snapshot, consumable_name_snapshot,
                old_installed_at, replaced_at, usage_days, price, daily_cost,
                new_installed_at, new_price, reason, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                consumable_id, consumable.get("asset_id"), consumable.get("name"),
                old_installed_at, replaced_at, usage_days, price, daily_cost,
                new_installed_at, new_price, data.get("reason"), data.get("notes"),
            ),
        )
        replacement_id = cursor.lastrowid
        conn.execute(
            """UPDATE printer_consumable
               SET installed_at = ?, current_price = ?, stock = ?
               WHERE id = ?""",
            (new_installed_date.isoformat(), new_price, new_stock, consumable_id),
        )
        log_activity(conn, user["id"], "replace_consumable", "consumable", consumable_id,
                     f"更替耗材 {consumable.get('name')}，旧周期 {usage_days} 天")
        replacement = conn.execute(
            "SELECT * FROM consumable_replacement WHERE id = ?", (replacement_id,)
        ).fetchone()
        updated = _select_consumable_with_printer(conn, consumable_id)
    return jsonify({
        "replacement": dict(replacement),
        "consumable": _consumable_usage_fields(updated),
    })


@app.route("/api/consumables/<int:consumable_id>/replacements", methods=["GET"])
def api_consumables_replacements(consumable_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT id FROM printer_consumable WHERE id = ?", (consumable_id,)).fetchone()
        if not row:
            return jsonify({"error": "耗材不存在"}), 404
        rows = conn.execute(
            """SELECT * FROM consumable_replacement
               WHERE consumable_id = ? ORDER BY replaced_at DESC, id DESC""",
            (consumable_id,),
        ).fetchall()
    replacements = [dict(r) for r in rows]
    return jsonify({"total": len(replacements), "replacements": replacements})


@app.route("/api/consumables/replacements", methods=["GET"])
def api_all_replacements():
    """全局更换历史，支持按打印机/颜色/日期范围筛选和分页。"""
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403

    page, err = _parse_positive_int_arg("page", 1)
    if err:
        return err
    per_page, err = _parse_positive_int_arg("per_page", 20, max_value=200)
    if err:
        return err

    printer_id_raw = request.args.get("printer_id")
    printer_id = int(printer_id_raw) if printer_id_raw else None
    color = request.args.get("color")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    if color and color not in VALID_TONER_COLORS:
        return jsonify({"error": f"无效颜色: {color}"}), 400

    where_clauses = []
    params = []
    if printer_id:
        where_clauses.append("pc.asset_id = ?")
        params.append(printer_id)
    if color:
        where_clauses.append("pc.color = ?")
        params.append(color)
    if date_from:
        where_clauses.append("cr.replaced_at >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("cr.replaced_at <= ?")
        params.append(date_to)

    where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    db = get_db()
    with db.get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) as c FROM consumable_replacement cr JOIN printer_consumable pc ON cr.consumable_id = pc.id{where}",
            params,
        ).fetchone()["c"]
        rows = conn.execute(
            f"""SELECT cr.*, pc.color as toner_color, pc.asset_id,
                a.name as printer_name, a.asset_tag as printer_tag
                FROM consumable_replacement cr
                JOIN printer_consumable pc ON cr.consumable_id = pc.id
                LEFT JOIN asset a ON pc.asset_id = a.id
                {where}
                ORDER BY cr.replaced_at DESC, cr.id DESC
                LIMIT ? OFFSET ?""",
            params + [per_page, (page - 1) * per_page],
        ).fetchall()
    replacements = [dict(r) for r in rows]
    return jsonify({"total": total, "page": page, "per_page": per_page, "replacements": replacements})


@app.route("/api/consumables/cost-summary", methods=["GET"])
def api_cost_summary():
    """耗材成本汇总：总花费、更换次数、按打印机明细、按月趋势。"""
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403

    db = get_db()
    with db.get_conn() as conn:
        # Overall totals
        agg = conn.execute("""
            SELECT COUNT(*) as total_replacements,
                   COALESCE(SUM(price), 0) as total_cost,
                   COALESCE(SUM(price) * 1.0 / NULLIF(SUM(usage_days), 0), 0) as avg_daily_cost
            FROM consumable_replacement
        """).fetchone()

        # By printer
        by_printer_rows = conn.execute("""
            SELECT a.id as printer_id, a.name as printer_name, a.asset_tag,
                   COUNT(*) as replacement_count,
                   COALESCE(SUM(cr.price), 0) as total_cost,
                   COALESCE(SUM(cr.price) * 1.0 / NULLIF(SUM(cr.usage_days), 0), 0) as avg_daily_cost
            FROM consumable_replacement cr
            JOIN printer_consumable pc ON cr.consumable_id = pc.id
            LEFT JOIN asset a ON pc.asset_id = a.id
            GROUP BY a.id
            ORDER BY total_cost DESC
        """).fetchall()

        # Monthly trend (last 12 months)
        monthly_rows = conn.execute("""
            SELECT strftime('%Y-%m', replaced_at) as month,
                   COUNT(*) as count,
                   COALESCE(SUM(price), 0) as cost
            FROM consumable_replacement
            WHERE replaced_at >= date('now', '-12 months')
            GROUP BY strftime('%Y-%m', replaced_at)
            ORDER BY month
        """).fetchall()

    return jsonify({
        "total_cost": round(agg["total_cost"], 2),
        "total_replacements": agg["total_replacements"],
        "avg_daily_cost": round(agg["avg_daily_cost"], 2),
        "by_printer": [dict(r) for r in by_printer_rows],
        "monthly": [dict(r) for r in monthly_rows],
    })


# ---- API: 打印机耗材聚合 (printer-centric view) ----

# Brand/model keywords that identify label printers
_LABEL_PRINTER_KEYWORDS = ("label", "标签", "zebra", "argox", "tsc", "godex", "saturn", "postek", "cab", "honeywell", "datamax", "sato", "intermec", "pronto")

_TONER_COLOR_LABELS = {"black": "黑色", "cyan": "青色", "magenta": "品红", "yellow": "黄色"}


def _is_label_printer(name, brand, model):
    """Heuristic: detect label printers by brand/model/name keywords."""
    text = " ".join(filter(None, [name, brand, model])).lower()
    return any(kw in text for kw in _LABEL_PRINTER_KEYWORDS)


def _get_printer_type(conn, asset_id, consumables_rows=None):
    """Get printer type from explicit asset.printer_type, falling back to inference from consumables."""
    row = conn.execute("SELECT printer_type FROM asset WHERE id = ?", (asset_id,)).fetchone()
    if row and row["printer_type"] in VALID_PRINTER_TYPES:
        return row["printer_type"]
    # Fallback: infer from existing toner slots
    if consumables_rows is not None:
        return _infer_printer_type(consumables_rows)
    return "unconfigured"


def _validate_toner_color_for_printer(conn, asset_id, color):
    """Validate that color toner is allowed for this printer.
    Returns (ok, error_response)."""
    printer_type = _get_printer_type(conn, asset_id)
    if printer_type == "mono":
        return False, (jsonify({"error": "黑白打印机不允许彩色墨粉"}), 400)
    # color or unconfigured: allow (unconfigured defaults to allowing black only in UI,
    # but API lets it through since the user might be setting up a color printer)
    return True, None


def _infer_printer_type(consumables_rows):
    """Infer color/mono from the colors of consumables associated with a printer."""
    if not consumables_rows:
        return "unconfigured"
    colors = {c.get("color") for c in consumables_rows if c.get("color")}
    if colors & {"cyan", "magenta", "yellow"}:
        return "color"
    return "mono"


@app.route("/api/printers/consumables", methods=["GET"])
def api_printers_consumables():
    """打印机耗材聚合视图：按打印机分组返回耗材数据，排除标签打印机。

    Query params:
      printer_type: "color" | "mono" — 按打印机类型筛选
      warning: "1" — 仅返回有低库存告警的打印机
    """
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403

    printer_type_filter = request.args.get("printer_type")
    warning_only = request.args.get("warning") == "1"

    db = get_db()
    with db.get_conn() as conn:
        # Get all printers with their consumables (toner only)
        rows = conn.execute("""
            SELECT a.id as asset_id, a.asset_tag, a.name as printer_name,
                   a.brand, a.model, a.printer_type,
                   pc.id as c_id, pc.name as c_name, pc.type as c_type,
                   pc.stock as c_stock, pc.threshold as c_threshold,
                   pc.color as c_color, pc.model as c_model,
                   pc.current_price as c_current_price,
                   pc.installed_at as c_installed_at,
                   pc.unit as c_unit, pc.notes as c_notes
            FROM asset a
            LEFT JOIN printer_consumable pc ON pc.asset_id = a.id AND pc.type = 'toner'
            WHERE a.category = 'printer'
            ORDER BY a.id, pc.id
        """).fetchall()

        # Group by printer
        printers_map = {}
        for r in rows:
            aid = r["asset_id"]
            if aid not in printers_map:
                printers_map[aid] = {
                    "asset_id": aid,
                    "asset_tag": r["asset_tag"],
                    "printer_name": r["printer_name"],
                    "brand": r["brand"],
                    "model": r["model"],
                    "printer_type_db": r["printer_type"],
                    "_consumables_raw": [],
                }
            if r["c_id"] is not None:
                printers_map[aid]["_consumables_raw"].append({
                    "id": r["c_id"],
                    "name": r["c_name"],
                    "type": r["c_type"],
                    "stock": r["c_stock"],
                    "threshold": r["c_threshold"],
                    "color": r["c_color"],
                    "model": r["c_model"],
                    "current_price": r["c_current_price"],
                    "installed_at": r["c_installed_at"],
                    "unit": r["c_unit"],
                    "notes": r["c_notes"],
                })

        # Build final printer list
        printers = []
        for p in printers_map.values():
            # Skip label printers
            if _is_label_printer(p["printer_name"], p["brand"], p["model"]):
                continue

            raw_consumables = p["_consumables_raw"]
            # Use explicit printer_type if set, otherwise infer from consumables
            explicit_pt = p.get("printer_type_db")
            if explicit_pt in VALID_PRINTER_TYPES:
                printer_type = explicit_pt
            else:
                printer_type = _infer_printer_type(raw_consumables)

            # Apply printer_type filter
            if printer_type_filter and printer_type != printer_type_filter:
                continue

            # Build enriched consumable slots
            slots = []
            low_stock_count = 0
            total_replacements = 0
            for c in raw_consumables:
                enriched = _consumable_usage_fields({
                    "id": c["id"], "name": c["name"], "type": c["type"],
                    "stock": c["stock"], "threshold": c["threshold"],
                    "color": c["color"], "model": c["model"],
                    "current_price": c["current_price"],
                    "installed_at": c["installed_at"],
                    "unit": c["unit"], "notes": c["notes"],
                    "asset_id": p["asset_id"],
                    "printer_tag": p["asset_tag"],
                    "printer_name": p["printer_name"],
                })
                is_low = c["stock"] <= c["threshold"] and c["threshold"] > 0
                enriched["is_low_stock"] = is_low
                if is_low:
                    low_stock_count += 1

                # Get recent replacements for this consumable
                recent = conn.execute(
                    """SELECT * FROM consumable_replacement
                       WHERE consumable_id = ? ORDER BY replaced_at DESC LIMIT 5""",
                    (c["id"],),
                ).fetchall()
                enriched["recent_replacements"] = [dict(r) for r in recent]
                total_replacements += len(recent)

                slots.append(enriched)

            has_warning = low_stock_count > 0

            # Apply warning filter
            if warning_only and not has_warning:
                continue

            printers.append({
                "asset_id": p["asset_id"],
                "asset_tag": p["asset_tag"],
                "printer_name": p["printer_name"],
                "printer_type": printer_type,
                "brand": p["brand"],
                "model": p["model"],
                "consumables": slots,
                "has_warning": has_warning,
                "total_slots": len(slots),
                "low_stock_count": low_stock_count,
                "recent_replacement_count": total_replacements,
            })

    return jsonify({"printers": printers})


# ---- API: 员工管理 ----

@app.route("/api/employees", methods=["GET"])
def api_employees():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    search = request.args.get("search")
    status = request.args.get("status", "active")
    db = get_db()
    with db.get_conn() as conn:
        q = """SELECT e.*, COUNT(a.id) as asset_count
               FROM employee e LEFT JOIN asset a ON a.current_holder_id = e.id"""
        params = []
        where = []
        if status != "all":
            if status not in ("active", "inactive"):
                return jsonify({"error": "员工状态无效"}), 400
            where.append("e.status = ?")
            params.append(status)
        if search:
            where.append("(e.name LIKE ? OR e.department LIKE ?)")
            params.extend([f"%{search}%"] * 2)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " GROUP BY e.id ORDER BY e.name"
        rows = conn.execute(q, params).fetchall()
    return jsonify({"employees": [dict(r) for r in rows]})


@app.route("/api/employees", methods=["POST"])
def api_employees_create():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "缺少员工姓名"}), 400
    department = _clean_optional_text(data.get("department"))
    notes = _clean_optional_text(data.get("notes"))
    db = get_db()
    with db.get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO employee (name, department, notes)
               VALUES (?, ?, ?)""",
            (name, department, notes),
        )
        emp_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM employee WHERE id = ?", (emp_id,)).fetchone()
        log_activity(conn, user["id"], "create_employee", "employee", emp_id, f"新增员工 {name}")
    return jsonify(dict(row)), 201


@app.route("/api/employees/<int:emp_id>", methods=["PUT"])
def api_employees_update(emp_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM employee WHERE id = ?", (emp_id,)).fetchone()
        if not row:
            return jsonify({"error": "员工不存在"}), 404
        name = (data.get("name", row["name"]) or "").strip()
        if not name:
            return jsonify({"error": "缺少员工姓名"}), 400
        department = _clean_optional_text(data.get("department", row["department"]))
        notes = _clean_optional_text(data.get("notes", row["notes"]))
        status = data.get("status", row["status"])
        if status not in ("active", "inactive"):
            return jsonify({"error": "员工状态无效"}), 400
        conn.execute(
            """UPDATE employee
               SET name = ?, department = ?, notes = ?, status = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (name, department, notes, status, emp_id),
        )
        log_activity(conn, user["id"], "update_employee", "employee", emp_id, f"更新员工 {name}")
        row = conn.execute("SELECT * FROM employee WHERE id = ?", (emp_id,)).fetchone()
    return jsonify(dict(row))


@app.route("/api/employees/<int:emp_id>", methods=["DELETE"])
def api_employees_delete(emp_id):
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json(silent=True) or {}
    move_assets_to_stock = bool(data.get("move_assets_to_stock"))
    stock_location = (data.get("stock_location") or "库房").strip() or "库房"
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM employee WHERE id = ?", (emp_id,)).fetchone()
        if not row:
            return jsonify({"error": "员工不存在"}), 404
        assets = conn.execute(
            """SELECT id FROM asset
               WHERE current_holder_id = ? AND status != 'scrapped'""",
            (emp_id,),
        ).fetchall()
        if assets and not move_assets_to_stock:
            return jsonify({
                "error": f"该员工持有 {len(assets)} 件资产，请先转入库房",
                "asset_count": len(assets),
                "requires_asset_transfer": True,
            }), 400
        moved_asset_ids = []
        for asset in assets:
            moved_asset_ids.append(asset["id"])
            conn.execute(
                """UPDATE asset
                   SET status = 'in_stock', current_holder_id = NULL, location = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (stock_location, asset["id"]),
            )
            conn.execute(
                """INSERT INTO lifecycle_event
                   (asset_id, event_type, operator_id, target_employee_id, to_location, notes)
                   VALUES (?, 'return', ?, ?, ?, ?)""",
                (asset["id"], user["id"], emp_id, stock_location, f"员工停用，资产转入{stock_location}"),
            )
            log_activity(conn, user["id"], "return", "asset", asset["id"],
                         f"员工 {row['name']} 停用，资产转入{stock_location}")
        conn.execute(
            "UPDATE employee SET status = 'inactive', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (emp_id,),
        )
        log_activity(conn, user["id"], "deactivate_employee", "employee", emp_id,
                     f"停用员工 {row['name']}，转入库房资产 {len(moved_asset_ids)} 件")
        updated = conn.execute("SELECT * FROM employee WHERE id = ?", (emp_id,)).fetchone()
    return jsonify({"ok": True, "employee": dict(updated), "moved_asset_ids": moved_asset_ids})


@app.route("/api/employees/import", methods=["POST"])
def api_employees_import():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    if "file" not in request.files:
        return jsonify({"error": "未上传文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "文件名为空"}), 400

    raw = f.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        return jsonify({"error": "CSV 文件为空"}), 400

    required_cols = {"name"}
    missing = required_cols - set(reader.fieldnames)
    if missing:
        return jsonify({"error": f"缺少必填列: {', '.join(missing)}"}), 400

    db = get_db()
    created = 0
    updated = 0
    errors = []
    with db.get_conn() as conn:
        for i, row in enumerate(reader, start=2):
            system_id_raw = (row.get("system_id") or "").strip()
            name = (row.get("name") or "").strip()
            department = (row.get("department") or "").strip() or None
            notes = (row.get("notes") or "").strip() or None
            if not name:
                errors.append({"row": i, "error": "姓名为空"})
                continue
            if system_id_raw:
                try:
                    system_id = int(system_id_raw)
                except ValueError:
                    errors.append({"row": i, "error": "system_id 必须是数字"})
                    continue
                existing = conn.execute("SELECT * FROM employee WHERE id = ?", (system_id,)).fetchone()
                if not existing:
                    errors.append({"row": i, "error": f"system_id 不存在: {system_id}"})
                    continue
                conn.execute(
                    """UPDATE employee
                       SET name = ?, department = ?, notes = ?, status = 'active',
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (name, department, notes, system_id),
                )
                updated += 1
                continue

            matches = conn.execute(
                """SELECT id FROM employee
                   WHERE name = ?
                     AND COALESCE(department, '') = COALESCE(?, '')""",
                (name, department),
            ).fetchall()
            if len(matches) == 1:
                conn.execute(
                    """UPDATE employee
                       SET name = ?, department = ?, notes = ?, status = 'active',
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (name, department, notes, matches[0]["id"]),
                )
                updated += 1
            elif len(matches) > 1:
                errors.append({"row": i, "error": f"姓名和部门匹配到多个员工，需提供 system_id: {name}"})
            else:
                conn.execute(
                    "INSERT INTO employee (name, department, notes) VALUES (?, ?, ?)",
                    (name, department, notes),
                )
                created += 1
        if created or updated:
            log_activity(conn, user["id"], "import_employees", "employee", None,
                         f"导入员工：新增 {created}，更新 {updated}，失败 {len(errors)} 条")

    success = created + updated
    return jsonify({
        "success": success,
        "created": created,
        "updated": updated,
        "errors": errors,
        "total": success + len(errors),
    })


# ---- API: 管理员用户管理 ----

@app.route("/api/users", methods=["GET"])
def api_users():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT id, employee_id, name, department, phone, email, role, created_at FROM "user" ORDER BY name'
        ).fetchall()
    return jsonify({"users": [dict(r) for r in rows]})


@app.route("/api/users", methods=["POST"])
def api_users_create():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    for field in ["employee_id", "name", "password"]:
        if not data.get(field):
            return jsonify({"error": f"缺少必填字段: {field}"}), 400
    role = data.get("role", "employee")
    if role not in VALID_ROLES:
        return jsonify({"error": f"无效角色: {role}"}), 400

    from werkzeug.security import generate_password_hash
    password_hash = generate_password_hash(data["password"])

    db = get_db()
    try:
        with db.get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO "user" (employee_id, name, department, phone, email, role, password_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["employee_id"], data["name"],
                    data.get("department"), data.get("phone"),
                    data.get("email"), role, password_hash,
                ),
            )
            uid = cursor.lastrowid
            log_activity(conn, user["id"], "create_user", "user", uid,
                         f"创建用户 {data['employee_id']}")
            row = conn.execute(
                'SELECT id, employee_id, name, department, phone, email, role, created_at FROM "user" WHERE id = ?',
                (uid,),
            ).fetchone()
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return jsonify({"error": f"工号已存在: {data['employee_id']}"}), 400
        raise
    return jsonify(dict(row)), 201


@app.route("/api/users/<int:user_id>", methods=["GET"])
def api_users_get(user_id):
    admin = require_role("admin")
    if not admin:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute(
            'SELECT id, employee_id, name, department, phone, email, role, created_at FROM "user" WHERE id = ?',
            (user_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "用户不存在"}), 404
    return jsonify(dict(row))


@app.route("/api/users/<int:user_id>", methods=["PUT"])
def api_users_update(user_id):
    admin = require_role("admin")
    if not admin:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    if "role" in data and data["role"] not in VALID_ROLES:
        return jsonify({"error": f"无效角色: {data['role']}"}), 400
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute('SELECT * FROM "user" WHERE id = ?', (user_id,)).fetchone()
        if not row:
            return jsonify({"error": "用户不存在"}), 404

        # Admin lockout protection: prevent downgrading last admin or self
        if "role" in data and data["role"] != "admin":
            target = dict(row)
            if target.get("role") == "admin":
                # Check if this is self-downgrade
                if user_id == admin["id"]:
                    return jsonify({"error": "不能降低自己的管理员角色"}), 400
                # Check if this is the last admin
                admin_count = conn.execute(
                    'SELECT COUNT(*) as c FROM "user" WHERE role = "admin"'
                ).fetchone()["c"]
                if admin_count <= 1:
                    return jsonify({"error": "不能降级系统最后一个管理员"}), 400

        fields = []
        params = []
        for col in ["name", "department", "phone", "email", "role"]:
            if col in data:
                fields.append(f"{col} = ?")
                params.append(data[col])
        if fields:
            conn.execute(
                f'UPDATE "user" SET {", ".join(fields)} WHERE id = ?',
                params + [user_id],
            )
            log_activity(conn, admin["id"], "update_user", "user", user_id,
                         f"更新字段: {', '.join(fields)}")
        row = conn.execute(
            'SELECT id, employee_id, name, department, phone, email, role, created_at FROM "user" WHERE id = ?',
            (user_id,),
        ).fetchone()
    return jsonify(dict(row))


@app.route("/api/users/<int:user_id>/reset-password", methods=["POST"])
def api_users_reset_password(user_id):
    admin = require_role("admin")
    if not admin:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    new_password = data.get("new_password", "")
    if not new_password:
        return jsonify({"error": "密码不能为空"}), 400

    from werkzeug.security import generate_password_hash
    password_hash = generate_password_hash(new_password)

    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute('SELECT * FROM "user" WHERE id = ?', (user_id,)).fetchone()
        if not row:
            return jsonify({"error": "用户不存在"}), 404
        conn.execute(
            'UPDATE "user" SET password_hash = ? WHERE id = ?',
            (password_hash, user_id),
        )
        log_activity(conn, admin["id"], "reset_password", "user", user_id,
                     f"重置用户 {dict(row)['employee_id']} 密码")
    return jsonify({"ok": True})


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
def api_users_delete(user_id):
    admin = require_role("admin")
    if not admin:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    with db.get_conn() as conn:
        row = conn.execute('SELECT * FROM "user" WHERE id = ?', (user_id,)).fetchone()
        if not row:
            return jsonify({"error": "用户不存在"}), 404
        target = dict(row)
        is_self = user_id == admin["id"]
        is_last_admin = False
        if target.get("role") == "admin":
            admin_count = conn.execute(
                'SELECT COUNT(*) as c FROM "user" WHERE role = "admin"'
            ).fetchone()["c"]
            if admin_count <= 1:
                is_last_admin = True
        if is_self and is_last_admin:
            return jsonify({"error": "不能删除自己（也是系统最后一个管理员）"}), 400
        if is_last_admin:
            return jsonify({"error": "不能删除系统最后一个管理员"}), 400
        if is_self:
            return jsonify({"error": "不能删除自己"}), 400
        log_activity(conn, admin["id"], "delete_user", "user", user_id,
                     f"删除用户 {dict(row)['employee_id']}")
        conn.execute('DELETE FROM "user" WHERE id = ?', (user_id,))
    return jsonify({"ok": True})


if __name__ == "__main__":
    db_existed = os.path.exists(DB_PATH)
    db = Database(DB_PATH)
    db.init_db()
    if db_existed:
        db.upgrade_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
