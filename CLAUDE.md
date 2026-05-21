# IT 资产管理系统 — 开发文档

## 项目概况

IT 固定资产管理追踪系统，面向 IT 管理员和普通员工。

- **技术栈**：Python Flask 3.1 + SQLite（原生 SQL）+ Jinja2 + 原生 JS + CSS
- **无前端框架**：纯 vanilla JS，无构建步骤
- **部署**：Flask 5000 端口 → Caddy 反向代理 9090 端口（10.18.0.68:9090）
- **规模**：server.py ~1320 行，models.py ~300 行，61 个测试
- **标签打印**：立象 Argox 热转印打印机 + BarTender + 60×40mm 亚银纸（Logo + 资产信息 + QR，无一维码）

## 快速启动

```bash
pip install -r requirements.txt    # Flask, qrcode, Pillow, pytest
python3 init_db.py                  # 初始化 DB + 种子数据（会清空旧数据）
python3 server.py                   # 启动 http://0.0.0.0:5000
```

**演示账号**：

| 角色 | 工号 | 密码 |
|------|------|------|
| 管理员 | `admin` | `admin123` |
| 员工 | `emp001` | `emp001` |
| 员工 | `emp002` | `emp002` |
| 员工 | `emp003` | `emp003` |

**运行测试**：`.venv/bin/python -m pytest tests/ -q`

---

## 文件结构

```
it-asset-manager/
├── server.py              # Flask 应用：所有路由 + API（单文件，~1320 行）
├── models.py              # 数据模型、常量、Schema SQL、工具函数
├── init_db.py             # 数据库初始化 + 种子数据
├── requirements.txt       # Flask, qrcode, Pillow, pytest
├── it_asset.db            # SQLite 数据库文件（运行时生成）
├── static/
│   ├── style.css          # 前端重构样式：Design Tokens、App Shell、抽屉、标签预览、移动端卡片
│   └── uploads/           # 企业 Logo 上传目录
├── templates/
│   ├── base.html          # 管理端 App Shell、全局详情抽屉、apiFetch()
│   ├── login.html         # 登录页
│   ├── scan.html          # QR 扫码落地页（移动端，独立页面）
│   ├── scan_camera.html   # 摄像头扫码页（html5-qrcode 库）
│   ├── admin/
│   │   ├── dashboard.html # 仪表盘（5连指标卡 + SVG趋势图 + Donut图 + 最近事件）
│   │   ├── assets.html    # 资产台账（状态Tabs、现代表格、右侧详情抽屉、批量标签、导出CSV、批量导入）
│   │   ├── asset_detail.html # 资产详情（时间线 + 操作按钮）
│   │   ├── asset_form.html   # 新增/编辑资产表单
│   │   ├── label.html     # 标签打印页（60×40mm，Logo + 字段 + QR，无一维码）
│   │   ├── applications.html # 申请审核
│   │   ├── maintenance.html  # 维修总览
│   │   ├── settings.html  # 系统设置（Logo、标签字段、QR地址）
│   │   └── activity.html  # 操作记录
│   └── employee/
│       ├── my_assets.html       # 我的资产（移动端卡片 + 分类色条 + 扫码FAB）
│       ├── asset_detail.html    # 资产只读详情
│       ├── applications.html    # 我的申请
│       └── application_form.html # 提交申请
└── tests/
    └── test_api.py        # 61 个自动化测试
```

---

## 数据库设计

### 表结构（7 张表）

```
user                 资产申请（asset_application）
├── id PK               ├── id PK
├── employee_id UNIQUE  ├── applicant_id → user
├── name                ├── asset_category
├── department          ├── reason
├── phone               ├── status [pending|approved|rejected|fulfilled]
├── email               ├── admin_id → user
├── role [admin|employee]├── admin_notes
├── password_hash       └── approved_at
└── created_at
                     activity_log
asset                ├── id PK
├── id PK            ├── user_id
├── asset_tag UNIQUE ├── action
├── name             ├── target_type
├── category         ├── target_id
├── brand/model      ├── detail
├── serial_number    └── created_at
├── status [见下方状态机]
├── current_holder_id → user   app_config
├── location         ├── key PK（如 label_fields, qr_base_url, company_logo）
├── purchase_date    └── value（JSON 或纯文本）
├── purchase_price
├── warranty_date
├── notes
└── created_at / updated_at

lifecycle_event                    maintenance_record
├── id PK                          ├── id PK
├── asset_id → asset               ├── asset_id → asset
├── event_type [见状态机]           ├── reported_by → user
├── operator_id → user             ├── description
├── target_user_id → user          ├── status [pending|in_progress|resolved]
├── from_location / to_location    ├── cost
├── notes                          ├── repair_notes
└── created_at                     ├── resolved_at
                                   └── created_at
```

### 资产状态机

```
in_stock ──assign──> assigned ──return──> in_stock
    │                  │
    │                  ├──transfer──> assigned（持有人变更）
    │                  ├──maintenance_start──> maintenance
    │                  └──scrap──> scrapped
    │                                     │
    └──scrap──> scrapped          maintenance_end──> assigned | in_stock
                                        │
                                        └──scrap──> scrapped
```

`scrapped` 是终态，不可逆。

### 数据库升级

- `SCHEMA` 是唯一的新装完整结构，必须直接包含当前所有表和列：`asset.warranty_date`、`activity_log`、`app_config` 都在这里。
- `upgrade_db()` 只负责旧 SQLite 文件补齐：执行 `LEGACY_MIGRATION_SCHEMA` 补建旧 MVP 缺失表，用 `PRAGMA table_info(asset)` 判断后添加 `warranty_date`，并把存量明文密码迁移为 Werkzeug 哈希。
- `init_db.py` 和 `server.py` 会先执行 `init_db()`；只有目标 DB 文件已存在时才执行 `upgrade_db()`。全新安装不依赖临时迁移补丁，旧库仍可自动补齐。
- **升级必须幂等**：重复执行不报错，不丢旧数据，不二次哈希密码。
- 旧库兼容必须有专门测试：`legacy_mvp_db` fixture 手工创建旧 MVP schema（没有 `warranty_date`、`activity_log`、`app_config`，用户密码为明文），再验证升级和 Flask 登录。

---

## 常量体系（models.py）

所有分类、状态、事件类型的合法值都在 models.py 定义：

| 常量 | 用途 | 值 |
|------|------|-----|
| `CATEGORY_PREFIX` | 资产标签号前缀 | computer→PC, monitor→MON, ... |
| `CATEGORY_NAMES` | 中文显示名 | computer→电脑, ... |
| `CATEGORY_ICONS` | emoji 图标 | computer→💻, ... |
| `CATEGORY_COLORS` | 色值 | computer→#2563eb, ... |
| `VALID_CATEGORIES` | 9 种分类 | computer, monitor, phone, tablet, printer, server, network, firewall, switch |
| `VALID_STATUSES` | 4 种状态 | in_stock, assigned, maintenance, scrapped |
| `STATE_TRANSITIONS` | 状态→允许事件映射 | in_stock→[stock_in, assign, scrap], ... |
| `LABEL_FIELD_OPTIONS` | 标签可选字段 | name, serial_number, holder, location, brand, model |
| `LABEL_FIELDS_DEFAULT` | 标签默认字段 | ["name"] |

**新增分类时**：需同时更新 PREFIX、NAMES、ICONS、COLORS 四个字典。

---

## 路由清单

### 页面路由（18 条）

| 路径 | 角色 | 模板 |
|------|------|------|
| `/` | 自动跳转 | — |
| `/login` | 公开 | login.html |
| `/dashboard` | admin | admin/dashboard.html |
| `/assets` | admin | admin/assets.html |
| `/assets/new` | admin | admin/asset_form.html |
| `/assets/<id>` | admin | admin/asset_detail.html |
| `/assets/<id>/edit` | admin | admin/asset_form.html |
| `/assets/<id>/label` | admin | admin/label.html |
| `/applications` | admin | admin/applications.html |
| `/maintenance` | admin | admin/maintenance.html |
| `/settings` | admin | admin/settings.html |
| `/activity` | admin | admin/activity.html |
| `/scan` | 公开 | scan_camera.html |
| `/scan/<id>` | 公开 | scan.html |
| `/my/assets` | employee | employee/my_assets.html |
| `/my/assets/<id>` | employee | employee/asset_detail.html |
| `/my/applications` | employee | employee/applications.html |
| `/my/applications/new` | employee | employee/application_form.html |

### API 路由（34 条）

**认证**：`POST /api/login`、`POST /api/logout`、`GET /api/me`

**资产 CRUD**：`GET/POST /api/assets`、`GET/PUT/DELETE /api/assets/<id>`

**生命周期**：`POST /api/assets/<id>/assign|return|transfer|maintenance|scrap`
　　　　　`POST /api/assets/<id>/maintenance/<rid>/resolve`
　　　　　`GET /api/assets/<id>/events`

**维修**：`GET /api/maintenance`、`GET /api/assets/<id>/maintenance`

**申请**：`GET/POST /api/applications`、`PUT /api/applications/<id>/approve|reject`

**员工自助**：`GET /api/my/assets`、`GET/POST /api/my/applications`

**统计**：`GET /api/stats`（含 warranty_expiring/expired）

**用户**：`GET /api/users`

**标签**：`GET /api/assets/<id>/qr`、`POST /api/batch-labels`

**分类**：`GET /api/categories`

**设置**：`GET/PUT /api/settings/label`、`GET/PUT /api/settings/qr-base-url`
　　　　 `GET/POST/DELETE /api/settings/logo`

**导出**：`GET /api/assets/export`（CSV，带 UTF-8 BOM）

**导入**：`POST /api/assets/import`（CSV 批量导入，返回 success/errors/total）

**操作记录**：`GET /api/activity`

**公开**：`GET /api/public/asset/<id>`（扫码页用，无需认证）

- 公开扫码相关页面只展示最小必要字段，匿名流不得复用 `/api/assets` 列表接口或暴露持有人/部门等敏感数据。
- 前端渲染数据库内容时优先使用 textContent / createElement；避免把资产字段直接拼进 innerHTML。

---

## 前端约定

### 管理端 App Shell

- 管理员页面统一走 `base.html` 中的 `.app-container`：左侧 200px 展开侧边栏（图标+文字）、顶部 70px header、可滚动 `.main-content`、全局右侧 `.detail-drawer`。
- 普通员工和公开扫码页走轻量壳 `.simple-shell`，不要强行套管理端侧边栏。
- `/assets` 台账行点击通过 `#asset-table-body` 事件代理打开 `openAssetDetailDrawer(id)`，不要给每个动态 `<tr>` 单独绑定监听器。
- 抽屉内容使用 `/api/assets/<id>` 获取完整详情，动态字段用 `textContent`/DOM 节点构造；不要把资产名称、备注、人员名直接拼进 `innerHTML`。

### 共享函数（base.html）

```javascript
apiFetch(url, options)  // 统一 fetch 封装，自动 JSON + 错误弹窗
```

### JS 中的分类映射

每个用到分类显示的模板都需要定义（或复用）以下映射：
```javascript
const catIcons = {computer:'💻', monitor:'🖥️', ...};
const catColors = {computer:'#2563eb', monitor:'#7c3aed', ...};
const catLabels = {computer:'电脑', monitor:'显示器', ...};
```

### CSS 变量 / Design Tokens

```css
--color-primary: #2563eb;       --color-primary-dark: #1d4ed8;
--color-success: #10b981;       --color-warning: #f59e0b;
--color-danger: #ef4444;        --color-info: #3b82f6;
--color-bg-main: #f8fafc;       --color-bg-card: #ffffff;
--color-text-main: #0f172a;     --color-text-muted: #64748b;
--color-border: #e2e8f0;        --color-border-light: #f1f5f9;
--space-1: 8px;                 --space-2: 16px;
--space-3: 24px;                --space-4: 32px;
--radius-soft: 4px;             --radius-medium: 8px;
--radius-strong: 16px;
```

`style.css` 仍保留 `--primary`、`--bg`、`--card` 等旧变量别名，兼容未重构页面。

状态徽章色：`.badge-instock`（蓝）、`.badge-assigned`（绿）、`.badge-maintenance`（橙）、`.badge-scrapped`（红）

---

## 关键实现细节

### 认证与密码

- session-based，Flask 原生 session
- 密码用 `werkzeug.security` 哈希存储
- 登录兼容明文和哈希密码（用 `$` in password_hash 判断类型）
- `upgrade_db()` 自动迁移存量明文密码为哈希

### 标签打印

- 尺寸 60mm × 40mm，`.physical-label-preview` 保持 6:4 比例。
- 当前标签设计只有 Logo、资产名称/标签号/字段、数字编号、QR 码；**没有一维码**，不要再添加 `barcode`、`label-body-barcode`、`barcode-mock-lines` 等结构。
- Logo 存储在 `static/uploads/company_logo.*`，路径记录在 app_config
- Logo 上传接口是 `POST /api/settings/logo`，保存目录必须用 `os.path.abspath(__file__)` 推导项目根路径；这里曾因 `_os.abspath` 拼写错误导致上传失败。
- 标签字段可通过设置页配置，单标签、批量标签、设置页预览、资产抽屉预览都应读取 `/api/settings/logo` 和 `/api/settings/label`
- `@media print` 隐藏非打印元素，适配热转印打印机

### CSV 导出

- 带 UTF-8 BOM（`EF BB BF`），确保 Excel/BarTender 正确识别中文
- QR URL 使用可配置的 base_url + `/scan/{id}`
- 支持按筛选条件或指定 ID 导出

### CSV 批量导入

- `POST /api/assets/import` 接受 multipart CSV 文件
- 必填列：`name`、`category`（英文值）
- 自动生成 asset_tag，初始状态为 `in_stock`，创建 `stock_in` 生命周期事件
- 返回 `{success, errors[], total}`，errors 包含行号和错误信息
- 导入时必须校验 `status` 是否属于 `VALID_STATUSES`；非法状态要跳过该行并返回行级错误。
- 导入弹窗在资产列表页，格式与导出 CSV 一致
- 编码读取 `utf-8-sig`（兼容有 BOM 和无 BOM 的 CSV）

### QR 码

- 内容指向 `/scan/{id}`（移动端友好页面）
- base_url 可配置，默认用 request.host_url

### 移动端扫码

- `/scan` 页面：使用 html5-qrcode 库（CDN），调用后置摄像头扫描 QR 码
- 识别后跳转到对应资产扫码落地页 `/scan/<id>`
- 支持 `facingMode: "environment"` 优先使用后摄
- 移动端仪表盘和"我的资产"页有扫码入口卡片（`.stat-scan` + `.mobile-only` CSS 模式）
- 桌面端隐藏扫码入口：`.mobile-only { display: none }` + `@media (max-width: 768px) { display: block !important }`

### 操作记录

- `log_activity(conn, user_id, action, target_type, target_id, detail)` 在已有连接中执行
- 所有变更 API（CRUD + 生命周期 + 审批 + 设置修改 + 导出）都埋了记录

---

## 开发注意事项

### 改数据库

1. 先更新 `SCHEMA`，保证新装数据库一次 `init_db()` 就是完整当前结构。
2. 如果要兼容已有旧库，再在 `upgrade_db()` 中添加幂等补丁：新增表放进 `LEGACY_MIGRATION_SCHEMA`，新增列用 `PRAGMA table_info` 检查后 `ALTER TABLE`。
3. 种子数据同步更新 `init_db.py`，但不要让新装依赖 `upgrade_db()` 才能 seed 成功。
4. 测试分两类：普通 `db` fixture 覆盖当前库 API 行为；旧库迁移必须新增专门旧 schema fixture/测试，避免被 `init_db()+upgrade_db()` 掩盖。

### 加新 API 端点

1. 如果是变更操作，在成功后调用 `log_activity()`
2. 需要认证用 `current_user()` 或 `require_role()`
3. 返回 JSON 用 `jsonify()`，CSV 用 `Response()`
4. 分页参数不要直接 `int(request.args...)`；复用 `_parse_positive_int_arg()`，非法参数返回 400，避免 500
5. 设置写入若还要记录 activity_log，使用 `db.set_config(key, value, conn=conn)`，确保配置与日志在同一事务中提交/回滚

### 加新页面

1. 加页面路由（`render_template`）
2. 管理员页面放 `templates/admin/`，员工页面放 `templates/employee/`
3. 管理员页面 `{% extends "base.html" %}`
4. 如需分类显示，JS 中加入 catIcons/catColors/catLabels 映射

### 标签渲染

- `templates/admin/label.html`（单标签）和 `assets.html` 中的 `batchPrintLabels()` 必须保持同步
- 两者都从 `/api/settings/label` 和 `/api/settings/logo` 读取配置
- 设置页预览和资产抽屉预览复用 `base.html` 的 `createPhysicalLabel(asset, qrSrc, options)`；若上传了 Logo，传 `options.logoUrl`
- 布局结构：`.label-header`（Logo + 名称/标签号/字段）+ `.label-footer-zone`（数字编号 + QR）
- 禁止恢复一维码或模拟条形码；如需更多字段，只追加到 `.label-meta-tags` 内，保持 60mm×40mm 内不溢出

### 2026-05-21 review 修复说明

本轮按计划评审结果做了偏功能/维护性的修复，目的是避免增强功能在新装、异常参数或部分失败时出现 500/静默不一致：

- 新装初始化：`SCHEMA` 已包含 `asset.warranty_date`、`activity_log`、`app_config`；`init_db.py`/`server.py` 对全新 DB 只依赖 `SCHEMA`，对已有 DB 才调用 `upgrade_db()` 补旧结构。
- 分页参数：`/api/assets`、`/api/activity` 改用 `_parse_positive_int_arg()`，非数字、小于 1 的 page/limit 返回 400；limit 上限 200。
- 标签设置：`GET /api/settings/label` 对损坏 JSON 回退默认 `['name']`；`PUT` 校验 fields 必须是数组。
- 配置事务：`Database.set_config()` 支持传入现有 `conn`；标签字段、QR base URL、Logo 上传的配置写入与 `activity_log` 保持同事务。
- 批量标签：`POST /api/batch-labels` 现在校验 `asset_ids` 必须是非重复数字数组，任一资产不存在返回 400，不再静默漏打或触发外键 500。
- CSV 导出：Response mimetype 改为 `text/csv`，避免 Flask 自动 charset 与手写 charset 重复；仍保留 UTF-8 BOM。
- 标签页权限：`/assets/<id>/label` 明确为 admin 页面，员工访问重定向登录页。
- 测试：新增增强回归测试，覆盖 init_db 新装、旧 MVP schema 迁移、upgrade_db 幂等/密码迁移、坏 label_fields JSON、分页非法参数、配置事务、CSV Content-Type、标签页权限、批量标签缺失资产。该轮当时验证：`.venv/bin/python -m pytest tests/ -q` → 57 passed；当前完整测试见下方前端重构记录。

### 2026-05-21 前端重构与标签修复说明

本轮按 UI 设计稿完成管理端前端重构，并修复标签/Logo 问题：

- 全局壳：`base.html` 管理端改为 `.app-container` Grid 布局，左侧 200px 展开侧边栏（图标+文字菜单项）、顶部 header、主内容区、全局右侧 `.detail-drawer`；员工和公开页面保留轻量壳。
- 样式令牌：`style.css` 新增 `--color-*`、`--space-*`、`--radius-*`、`--shadow-*` Design Tokens，并保留旧变量别名兼容未重构页面。
- Dashboard：`templates/admin/dashboard.html` 改为 5 连 `.metric-card`、原生 SVG sparkline、趋势图和 Donut 图，不引入重型前端库。
- 资产台账：`templates/admin/assets.html` 改为状态 Tabs、无垂直线 `.asset-data-table`、搜索/筛选工具栏、行点击事件代理打开右侧详情抽屉。
- 详情抽屉：`base.html` 内 `openAssetDetailDrawer(id)` 使用 `/api/assets/<id>`，安全 DOM 构造资产信息、工具栏、元数据、生命周期时间线和标签预览。
- 员工资产页：`templates/employee/my_assets.html` 改为移动端卡片、分类色条和底部扫码 FAB。
- 标签设计：单标签、批量标签、设置页预览、资产抽屉预览统一为 60mm×40mm 的 Logo + 资产信息 + 数字编号 + QR；明确移除一维码/模拟条码。
- Logo 修复：修复 `POST /api/settings/logo` 中 `_os.abspath` 拼写错误；上传后路径保存为 `/static/uploads/company_logo.*`，设置页预览、单标签页、批量标签和抽屉预览都会读取显示。
- 打印修复：`templates/admin/label.html` 的 `@media print` 显示 `#labelContent`，避免父容器隐藏导致打印空白。
- 测试：新增企业 Logo 上传回归测试。当前验证：`.venv/bin/python -m pytest tests/ -q` → 61 passed；headless Chromium 检查 `/dashboard`、`/assets`、`/settings`、资产抽屉、`/my/assets` 关键 DOM 正常。

### 2026-05-21 文本对齐、标签打印与侧边栏展开

本轮修复前端 UI 问题：

- 侧边栏从 80px 纯图标改为 200px 展开式，菜单项显示图标+中文文字标签，品牌区域增加"IT 资产管理"文字。
- 仪表盘保修提醒：从两个独立 `<table>` 合并为单个表格 + `table-layout: fixed` + `<colgroup>`，解决了"即将到期"和"已过期"两部分文本不对齐的问题。
- 仪表盘最近事件表、资产台账表、操作记录表均增加 `table-layout: fixed` + `<colgroup>` 固定列宽，所有行文本严格纵向对齐。
- 全局 `.table td` 增加 `overflow: hidden; text-overflow: ellipsis; white-space: nowrap`（资产名称单元格例外保留换行）。
- 资产台账状态 Tabs 从英文（All/In-Use/Stock/Repair/Scrapped）改为中文（全部/在用/库存/维修中/已报废）。
- 资产详情页从 `innerHTML` 拼接改为安全 DOM 构造（`textContent`），消除 XSS 风险。
- 标签打印页 `@media print` 从 `display:none/flex` 切换方案改为 `visibility:hidden/visible`，修复了打印时文字元素被错误设为 flex 容器导致的布局崩坏。
- 标签容器移除 `overflow: hidden`，padding 从 8px 改为 3mm 更贴合物理尺寸。
- 抽屉内标签预览（`.is-compact`）增加完整子元素尺寸适配。
- 设置页标签预览中的自定义字段显示字段标签前缀（如"位置: 工位A-101"而非仅"工位A-101"）。

---

## 部署

```bash
# Caddy 配置（/etc/caddy/Caddyfile）
http://10.18.0.68:9090 {
    reverse_proxy 127.0.0.1:5000
}

# UFW 防火墙
sudo ufw allow 9090/tcp

# 启动（开发模式）
cd /home/yobai/it-asset-manager
python3 server.py

# 启动（生产建议用 systemd + gunicorn）
```

---

## 已知限制

- 认证为 session + 哈希密码，生产环境应接 SSO/LDAP
- 单级审批，无审批流
- 无采购/合同管理
- 无资产自动发现
- 中文界面，未国际化
- Flask 开发服务器，生产应用 Gunicorn
