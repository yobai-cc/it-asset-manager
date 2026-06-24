# 开发约定

## 代码风格

### Python

- Flask 单文件架构，所有路由在 `server.py`
- 原生 SQL，不使用 ORM
- 私有辅助函数前缀 `_`（如 `_asset_dict`, `_get_asset_for_update`）
- 常量全大写，集中在 `models.py`（如 `VALID_CATEGORIES`, `STATE_TRANSITIONS`）
- 分页参数复用 `_parse_positive_int_arg()`，不直接 `int(request.args...)`
- 设置写入需记 activity_log 时，用 `db.set_config(key, value, conn=conn)` 确保同事务

### JavaScript

- 原生 JS，无框架、无构建步骤
- 用 `textContent` / `createElement` 渲染数据，避免 `innerHTML` 拼接（防 XSS）
- 表格行用事件代理，不给每个动态 `<tr>` 单独绑定监听器
- API 调用统一走 `apiFetch()`，不直接 `fetch()`
- 分类显示需定义 `catIcons` / `catColors` / `catLabels` 三个映射

### CSS

- Design Tokens 变量体系（`--color-primary`, `--space-2`, `--radius-medium`）
- 状态徽章：`.badge-instock`(蓝) / `.badge-assigned`(绿) / `.badge-maintenance`(橙) / `.badge-scrapped`(红)
- 移动端隐藏：`.mobile-only { display: none }` + `@media (max-width: 768px) { display: block !important }`
- 打印隐藏用 `display: none`（不用 `visibility: hidden`）

## 错误响应与鉴权约定

### 错误响应

- 所有 JSON 错误统一用 `api_error(message, status=400)`，返回 `{"error": message}` + HTTP 码
- 不要手写 `return jsonify({"error": ...}), <码>`；`jsonify()` 仅用于成功响应
- `api_error()` 是唯一手写 `jsonify({"error": ...})` 的位置（在它的实现内部）
- DB/校验辅助层（如 `_get_asset_for_update`）不要返回 `(json_response, status)` 元组——抛 `ApiError(message, status)`，由全局 `@app.errorhandler(ApiError)` 统一转 `api_error()`。handler 正常路径用 `api_error()` 显式返回，辅助层用 `ApiError` 抛出

### 鉴权装饰器

- `@login_required`：要求已登录（任意角色）。失败时 API 返回 `api_error("未登录", 401)`、页面重定向到 `/login`
- `@admin_required`：要求 admin 角色；**未登录或非 admin 都算失败**，API 返回 `api_error("权限不足", 403)`、页面重定向 `/login`（保持原行为——未登录也是 403，不是 401）
- 装饰器把当前用户写入 `g.user`；handler 首行 `user = g.user` 即可，沿用原 `user["id"]` 等写法
- 装饰器写在 `@app.route(...)` 与 `def` 之间：

  ```python
  @app.route("/api/assets", methods=["POST"])
  @admin_required
  def api_assets_create():
      user = g.user
      ...
  ```

- 新端点必须用装饰器鉴权，不要在 handler 内手写鉴权分支
- `current_user()` 保留，供需要自定义可见性校验的场景（如按持有人过滤）使用

### DB 连接装饰器

- `@with_conn`：handler 首参即 DB 连接 `conn`，省去 `db = get_db()` + `with db.get_conn() as conn:` 样板。复用 `Database.get_conn()` 的事务语义（成功 commit / 异常 rollback，含被 `@app.errorhandler(ApiError)` 捕获的异常），与原内联 `with` 行为一致
- 写在鉴权装饰器之下、`def` 之上（最内层），保证鉴权失败时不打开连接：

  ```python
  @app.route("/api/assets/<int:asset_id>/return", methods=["POST"])
  @admin_required
  @with_conn
  def api_return(conn, asset_id):
      user = g.user
      ...conn.execute(...)...
  ```

- handler 内还需要 `Database` 对象（如 `db.set_config(conn=conn)`、`db.get_config()`）时，保留 `db = get_db()`
- 例外（保持内联 `with db.get_conn()`）：`current_user()`（helper，由鉴权装饰器调用）、`api_health`（try/except 捕获连接失败转 503，依赖 `with` 在函数体内）

## 数据库变更流程

1. 更新 `SCHEMA` 常量 — 保证新装 `init_db()` 就是完整结构
2. 旧库兼容：在 `upgrade_db()` 添加幂等补丁
   - 新增表 → 放入 `LEGACY_MIGRATION_SCHEMA`
   - 新增列 → `PRAGMA table_info` 检查后 `ALTER TABLE`
3. 种子数据同步 `init_db.py`，不依赖 `upgrade_db()` 才能 seed
4. 测试分两类：
   - 普通 `db` fixture — 覆盖当前库 API 行为
   - 旧库迁移 — `legacy_mvp_db` fixture 手工创建旧 schema，验证升级

**升级必须幂等**：重复执行不报错、不丢数据、不二次哈希密码。

## 新增功能清单

### 新增 API 端点

1. 鉴权用 `@admin_required` / `@login_required` 装饰器（用户写入 `g.user`），不要在 handler 内手写鉴权分支
2. DB 访问用 `@with_conn`（handler 首参 `conn`），不要手写 `db = get_db()` + `with db.get_conn() as conn:`
3. JSON 错误响应用 `api_error(message, status)`，成功响应用 `jsonify()`，CSV 用 `Response()`
4. 变更操作成功后调用 `log_activity()`

### 新增页面

1. 管理员页面放 `templates/admin/`，`{% extends "base.html" %}`
2. 员工页面放 `templates/employee/`
3. 侧边栏菜单在 `base.html` 添加，使用 `icon-*` CSS 图标类

### 新增分类

需同时更新 `CATEGORY_PREFIX`、`CATEGORY_NAMES`、`CATEGORY_ICONS`、`CATEGORY_COLORS` 四个字典。

## 标签打印同步

`label.html`（单标签）和 `assets.html` 中的 `batchPrintLabels()` 必须保持布局一致：
- 都从 `/api/settings/label` 和 `/api/settings/logo` 读取配置
- 设置页预览和资产抽屉预览复用 `base.html` 的 `createPhysicalLabel()`
- 字段配置通过 `options.fields` 传入，受 `LABEL_FIELDS_MAX=3` 限制

## 测试约定

- 所有测试在 `tests/test_api.py`，使用 Flask test client
- `seed_test_data(db)` 插入基础数据（先 employee 再 user）
- `login_admin(client)` / `login_employee(client)` 快捷登录
- 旧库迁移用 `legacy_mvp_db` fixture，不复用普通 `db` fixture

## 安全

- 密码用 `werkzeug.security` 哈希存储
- API 响应不暴露 `password_hash` 字段
- 前端渲染用 `textContent` / `createElement`，不用 `innerHTML` 拼接
- 公开扫码页只展示最小必要字段，不暴露持有人/部门等敏感数据

## 软删除 / 回收站约定

- 在册视图统一过滤 `deleted_at IS NULL`，回收站视图过滤 `deleted_at IS NOT NULL`
- 软删除不是普通 status，而是在册/回收站两个视图层的分隔
- 恢复时检查原持有人状态：inactive → 自动 in_stock + 清空持有人 + 关闭进行中维修记录
- 已删除资产详情页只显示恢复/永久删除按钮，不显示常规操作

## 打印机 / 耗材隔离约定

- 报废打印机（`status = 'scrapped'`）：自动解绑耗材，不可再绑定，不出现在墨粉管理视图
- 已删除打印机（`deleted_at IS NOT NULL`）：保留耗材关联（方便恢复），但不可新绑定、不出现在墨粉管理视图
- 永久删除打印机：耗材不删除，解绑为未绑定库存并记 notes 和 activity_log
- `_validate_printer_asset_id()` 检查打印机存在、为打印机、未删除、未报废
- `_check_printer_operational()` 检查绑定打印机可运营（用于更换等操作）
- 耗材响应标记不可用打印机：`printer_unavailable_reason = 'deleted' | 'scrapped'`，清除显示名/标签号
- 分配/转移拒绝 `status != 'active'` 的员工
