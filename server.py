"""IT 资产管理 MVP — Flask 应用"""
import csv
import io
import json
import os
from flask import Flask, g, jsonify, request, render_template, redirect, url_for, session, Response
from werkzeug.security import check_password_hash
from models import (
    Database, VALID_CATEGORIES, VALID_STATUSES, STATE_TRANSITIONS,
    log_activity, get_categories_meta, LABEL_FIELDS_DEFAULT,
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
            """SELECT a.*, u.name as holder_name FROM asset a
               LEFT JOIN "user" u ON a.current_holder_id = u.id
               WHERE a.warranty_date IS NOT NULL AND a.status != 'scrapped'
                 AND a.warranty_date <= date('now', '+30 days') AND a.warranty_date >= date('now')
               ORDER BY a.warranty_date""").fetchall()]
        warranty_expired = [_asset_dict(r) for r in conn.execute(
            """SELECT a.*, u.name as holder_name FROM asset a
               LEFT JOIN "user" u ON a.current_holder_id = u.id
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
            f"""SELECT a.*, u.name as holder_name, u.department as holder_dept
                FROM asset a LEFT JOIN "user" u ON a.current_holder_id = u.id
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

    db = get_db()
    with db.get_conn() as conn:
        asset_tag = db.generate_asset_tag(conn, data["category"])
        cursor = conn.execute(
            """INSERT INTO asset (asset_tag, name, category, brand, model, serial_number,
               status, location, purchase_date, purchase_price, notes, warranty_date)
               VALUES (?, ?, ?, ?, ?, ?, 'in_stock', ?, ?, ?, ?, ?)""",
            (
                asset_tag, data["name"], data["category"],
                data.get("brand"), data.get("model"), data.get("serial_number"),
                data.get("location"), data.get("purchase_date"), data.get("purchase_price"),
                data.get("notes"), data.get("warranty_date"),
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
            """SELECT a.*, u.name as holder_name, u.department as holder_dept
               FROM asset a LEFT JOIN "user" u ON a.current_holder_id = u.id
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
        fields = []
        params = []
        for col in ["name", "brand", "model", "serial_number", "location",
                     "purchase_date", "purchase_price", "notes", "category", "warranty_date"]:
            if col in data:
                fields.append(f"{col} = ?")
                params.append(data[col])
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
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        return jsonify({"error": "缺少 target_user_id"}), 400
    db = get_db()
    with db.get_conn() as conn:
        asset = _get_asset_for_update(conn, asset_id, "assign")
        if isinstance(asset, tuple):
            return asset
        conn.execute(
            "UPDATE asset SET status = 'assigned', current_holder_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (target_user_id, asset_id),
        )
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, target_user_id, notes)
               VALUES (?, 'assign', ?, ?, ?)""",
            (asset_id, user["id"], target_user_id, data.get("notes")),
        )
        log_activity(conn, user["id"], "assign", "asset", asset_id, f"分配给用户ID {target_user_id}")
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
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        return jsonify({"error": "缺少 target_user_id"}), 400
    db = get_db()
    with db.get_conn() as conn:
        asset = _get_asset_for_update(conn, asset_id, "transfer")
        if isinstance(asset, tuple):
            return asset
        old_holder = asset["current_holder_id"]
        conn.execute(
            "UPDATE asset SET current_holder_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (target_user_id, asset_id),
        )
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, target_user_id, notes)
               VALUES (?, 'transfer', ?, ?, ?)""",
            (asset_id, user["id"], target_user_id, data.get("notes")),
        )
        log_activity(conn, user["id"], "transfer", "asset", asset_id, f"转移给用户ID {target_user_id}")
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
            """SELECT le.*, u.name as operator_name, tu.name as target_user_name
               FROM lifecycle_event le
               JOIN "user" u ON le.operator_id = u.id
               LEFT JOIN "user" tu ON le.target_user_id = tu.id
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
        q = """SELECT a.*, u.name as holder_name FROM asset a
               LEFT JOIN "user" u ON a.current_holder_id = u.id
               WHERE a.current_holder_id = ?"""
        params = [user["id"]]
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


# ---- API: 用户列表 ----

@app.route("/api/users")
def api_users():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    db = get_db()
    with db.get_conn() as conn:
        rows = conn.execute('SELECT id, employee_id, name, department, role FROM "user" ORDER BY name').fetchall()
    return jsonify({"users": [dict(r) for r in rows]})


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

@app.route("/api/settings/label", methods=["GET"])
def api_label_settings():
    db = get_db()
    raw = db.get_config("label_fields")
    fields = LABEL_FIELDS_DEFAULT
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                from models import LABEL_FIELD_OPTIONS
                fields = [f for f in loaded if f in LABEL_FIELD_OPTIONS] or LABEL_FIELDS_DEFAULT
        except json.JSONDecodeError:
            fields = LABEL_FIELDS_DEFAULT
    return jsonify({"fields": fields})


@app.route("/api/settings/label", methods=["PUT"])
def api_label_settings_update():
    user = require_role("admin")
    if not user:
        return jsonify({"error": "权限不足"}), 403
    data = request.get_json() or {}
    from models import LABEL_FIELD_OPTIONS
    fields = data.get("fields", [])
    if not isinstance(fields, list):
        return jsonify({"error": "fields 必须是数组"}), 400
    fields = [f for f in fields if f in LABEL_FIELD_OPTIONS]
    db = get_db()
    with db.get_conn() as conn:
        db.set_config("label_fields", json.dumps(fields), conn=conn)
        log_activity(conn, user["id"], "update_settings", "config", None, f"标签字段: {', '.join(fields)}")
    return jsonify({"fields": fields})


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
    save_dir = _os.path.join(_os.path.dirname(_os.abspath(__file__)), "static", "uploads")
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
            f"""SELECT a.*, u.name as holder_name, u.department as holder_dept
                FROM asset a LEFT JOIN "user" u ON a.current_holder_id = u.id
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


if __name__ == "__main__":
    db_existed = os.path.exists(DB_PATH)
    db = Database(DB_PATH)
    db.init_db()
    if db_existed:
        db.upgrade_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
