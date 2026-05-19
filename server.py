"""IT 资产管理 MVP — Flask 应用"""
import os
from flask import Flask, g, jsonify, request, render_template, redirect, url_for, session
from models import Database

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
    user = current_user()
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
        # MVP: 简单密码验证 (password_hash 存明文)
        if user["password_hash"] and user["password_hash"] != password:
            return jsonify({"error": "密码错误"}), 401
        session["user_id"] = user["id"]
        session["role"] = user["role"]
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
    return jsonify({
        "total": total,
        "in_stock": by_status.get("in_stock", 0),
        "assigned": by_status.get("assigned", 0),
        "maintenance": by_status.get("maintenance", 0),
        "scrapped": by_status.get("scrapped", 0),
        "by_category": by_category,
        "recent_events": recent_events,
    })


# ---- API: 资产 CRUD ----

@app.route("/api/assets", methods=["GET"])
def api_assets_list():
    db = get_db()
    category = request.args.get("category")
    status = request.args.get("status")
    search = request.args.get("search")
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
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
               status, location, purchase_date, purchase_price, notes)
               VALUES (?, ?, ?, ?, ?, ?, 'in_stock', ?, ?, ?, ?)""",
            (
                asset_tag, data["name"], data["category"],
                data.get("brand"), data.get("model"), data.get("serial_number"),
                data.get("location"), data.get("purchase_date"), data.get("purchase_price"),
                data.get("notes"),
            ),
        )
        asset_id = cursor.lastrowid
        # 记录入库事件
        conn.execute(
            """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, notes)
               VALUES (?, 'stock_in', ?, ?)""",
            (asset_id, user["id"], data.get("notes")),
        )
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
                     "purchase_date", "purchase_price", "notes", "category"]:
            if col in data:
                fields.append(f"{col} = ?")
                params.append(data[col])
        if fields:
            fields.append("updated_at = CURRENT_TIMESTAMP")
            conn.execute(f"UPDATE asset SET {', '.join(fields)} WHERE id = ?",
                         params + [asset_id])
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
    qr_url = f"{host}/assets/{asset_id}"
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
    db = get_db()
    with db.get_conn() as conn:
        placeholders = ",".join("?" * len(asset_ids))
        rows = conn.execute(
            f"SELECT * FROM asset WHERE id IN ({placeholders})", asset_ids
        ).fetchall()
        assets = [_asset_dict(r) for r in rows]
        # 记录打印事件
        for aid in asset_ids:
            conn.execute(
                """INSERT INTO lifecycle_event (asset_id, event_type, operator_id, notes)
                   VALUES (?, 'label_print', ?, '批量打印标签')""",
                (aid, user["id"]),
            )
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


# 导入常量供路由使用
from models import VALID_CATEGORIES, STATE_TRANSITIONS

if __name__ == "__main__":
    db = Database(DB_PATH)
    db.init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
