# IT 资产管理系统 — 开发文档

## 项目概况

IT 固定资产管理追踪系统，面向 IT 管理员和普通员工。

- **技术栈**：Python Flask 3.1 + SQLite（原生 SQL）+ Jinja2 + 原生 JS + CSS
- **无前端框架**：纯 vanilla JS，无构建步骤
- **部署**：Flask 5000 端口 → Caddy 反向代理 9090 端口（10.18.0.68:9090）
- **规模**：server.py ~2222 行，models.py ~389 行，192 个测试
- **标签打印**：立象 Argox 热转印打印机 + 60×40mm 亚银纸，浏览器直接打印（Logo + 资产信息 + QR）

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
├── server.py              # Flask 应用：所有路由 + API（单文件，~2134 行）
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
│   │   ├── label.html     # 标签打印页（60×40mm，Logo + 字段 + QR）
│   │   ├── applications.html # 申请审核
│   │   ├── maintenance.html  # 维修总览
│   │   ├── consumables.html  # 墨粉管理（打印机墨粉 CRUD + 库存调整）
│   │   ├── users.html        # 用户管理（创建/编辑/角色/密码重置）
│   │   ├── settings.html  # 系统设置（Logo、标签字段、QR地址）
│   │   └── activity.html  # 操作记录
│   └── employee/
│       ├── my_assets.html       # 我的资产（移动端卡片 + 分类色条 + 扫码FAB）
│       ├── asset_detail.html    # 资产只读详情
│       ├── applications.html    # 我的申请
│       └── application_form.html # 提交申请
└── tests/
    └── test_api.py        # 192 个自动化测试
```

---

## 数据库设计

### 表结构（9 张表）

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

打印机墨粉（printer_consumable）        activity_log
├── id PK                              ├── id PK
├── name                               ├── user_id
├── type [固定 toner]                   ├── action
├── stock                              ├── target_type
├── threshold                          ├── target_id
├── asset_id → asset（关联打印机）      ├── detail
├── unit（默认"个"）                    └── created_at
├── color（墨粉颜色，如 black/cyan/magenta/yellow）
├── model（墨粉型号：原装/国产）
├── current_price（当前价格）
├── installed_at（当前安装日期）
├── notes
└── created_at

墨粉更替历史（consumable_replacement）
├── id PK
├── consumable_id → printer_consumable
├── asset_id_snapshot
├── consumable_name_snapshot
├── old_installed_at
├── replaced_at
├── usage_days（使用天数，最小 1）
├── price（旧周期价格）
├── daily_cost（日均成本，price/usage_days 保留 2 位）
├── new_installed_at
├── new_price
├── reason
├── notes
└── created_at

asset
├── id PK            ├── user_id
├── asset_tag UNIQUE ├── action
├── name             ├── target_type
├── category         ├── target_id
├── brand/model      ├── detail
├── serial_number    └── created_at
├── status [见下方状态机]
├── printer_type [mono|color|NULL]（仅打印机资产）
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
| `LABEL_FIELD_OPTIONS` | 标签可选字段 | name, serial_number, brand, model, holder, location |
| `LABEL_FIELDS_DEFAULT` | 标签默认字段 | ["name", "serial_number"] |
| `LABEL_FIELDS_MAX` | 标签最多辅助字段数 | 3 |
| `LABEL_FIXED_FIELDS` | 标签固定字段 | asset_tag, numeric_id, qr |
| `VALID_CONSUMABLE_TYPES` | 耗材类型（历史值，仅 toner 可创建/更新） | toner, ink, drum, paper, ribbon, other |
| `VALID_PRINTER_TYPES` | 打印机类型 | mono, color |
| `VALID_TONER_COLORS` | 墨粉颜色 | black, cyan, magenta, yellow |
| `VALID_TONER_MODELS` | 墨粉型号（原装/国产） | 原装, 国产 |

**新增分类时**：需同时更新 PREFIX、NAMES、ICONS、COLORS 四个字典。

---

## 路由清单

### 页面路由（20 条）

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
| `/consumables` | admin | admin/consumables.html |
| `/users` | admin | admin/users.html |
| `/settings` | admin | admin/settings.html |
| `/activity` | admin | admin/activity.html |
| `/scan` | 公开 | scan_camera.html |
| `/scan/<id>` | 公开 | scan.html |
| `/my/assets` | employee | employee/my_assets.html |
| `/my/assets/<id>` | employee | employee/asset_detail.html |
| `/my/applications` | employee | employee/applications.html |
| `/my/applications/new` | employee | employee/application_form.html |

### API 路由（55 条）

**认证**：`POST /api/login`、`POST /api/logout`、`GET /api/me`

**资产 CRUD**：`GET/POST /api/assets`、`GET/PUT/DELETE /api/assets/<id>`

**生命周期**：`POST /api/assets/<id>/assign|return|transfer|maintenance|scrap`
　　　　　`POST /api/assets/<id>/maintenance/<rid>/resolve`
　　　　　`GET /api/assets/<id>/events`

**维修**：`GET /api/maintenance`、`GET /api/assets/<id>/maintenance`

**申请**：`GET/POST /api/applications`、`PUT /api/applications/<id>/approve|reject`

**员工自助**：`GET /api/my/assets`、`GET/POST /api/my/applications`

**统计**：`GET /api/stats`（含 warranty_expiring/expired）

**用户**：`GET /api/users`、`POST /api/users`、`GET /api/users/<id>`、`PUT /api/users/<id>`、`DELETE /api/users/<id>`、`POST /api/users/<id>/reset-password`

**耗材**：`GET /api/consumables`、`POST /api/consumables`、`GET/PUT/DELETE /api/consumables/<id>`、`POST /api/consumables/<id>/adjust`、`POST /api/consumables/<id>/replace`、`GET /api/consumables/<id>/replacements`、`GET /api/printers/consumables`

**标签**：`GET /api/assets/<id>/qr`、`POST /api/batch-labels`

**分类**：`GET /api/categories`

**设置**：`GET/PUT /api/settings/label`、`GET/PUT /api/settings/qr-base-url`
　　　　 `GET/POST/DELETE /api/settings/logo`

`GET /api/settings/label` 返回 `{fields, options, fixed_fields, max_fields}`：`fields` 是已选择辅助字段；`options` 是可选字段元数据（label/group/volatile）；`fixed_fields` 固定为资产标签号、数字编号、QR；`max_fields` 当前为 3。`PUT /api/settings/label` 会去重、过滤非法字段并最多保留 3 个，空数组表示只打印固定字段。

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

### 资产列表易用性

- 资产列表没有匹配数据时显示 `.empty-state` 空状态，不要只留空表格。
- 批量标签栏在当前页有资产时保持可见：未勾选时提示“请先勾选资产”并禁用按钮，勾选后显示“N 项已选”。
- 分页区域除页码外要显示 `.pagination-info` 范围说明（如“第 1-15 条，共 42 条”）。
- CSV 导入弹窗需说明 UTF-8 编码、必填列 `name`/`category`、常用可选列，并建议先导出 CSV 作为参考。

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

- **物理标签**：60mm × 40mm 亚银纸，立象 Argox 热转印打印机，浏览器直接打印（不经过 BarTender）。
- **打印尺寸**：`@page { size: 60mm 40mm; margin: 0 }`，打印态标签盒为 57.6×37.6mm + 四周 1.1mm 安全边距，外部占用 59.8×39.8mm，避免浏览器/驱动舍入误差导致空白第二页。
- **单位体系**：标签内所有元素（Logo、字体、QR 码、间距）统一使用 mm 单位，不混用 px，确保与纸张物理尺寸精确对应。
- 当前标签设计包含 Logo（11mm）、资产名称（3.8mm 字号）/标签号（2.8mm）/可选字段、数字编号（7mm 字号）、QR 码（20mm）。
- 固定打印项：资产标签号、数字编号、QR。辅助字段默认 `name` + `serial_number`，最多 3 个；`holder`/`location` 是易过期动态字段，设置页作为高级字段提示，优先建议扫码查看实时信息。
- 打印页、设置页和预览文案保持”60×40mm QR 标签”的一致表述。
- Logo 存储在 `static/uploads/company_logo.*`，路径记录在 app_config
- Logo 上传接口是 `POST /api/settings/logo`，保存目录必须用 `os.path.abspath(__file__)` 推导项目根路径；这里曾因 `_os.abspath` 拼写错误导致上传失败。
- 标签字段可通过设置页配置，单标签、批量标签、设置页预览、资产抽屉预览都应读取 `/api/settings/logo` 和 `/api/settings/label`
- **打印 CSS 要点**：
  - 用 `display: none` 隐藏非打印元素（不要用 `visibility: hidden`，会占空间导致布局问题）
  - 用 `display: contents` 解除预览外框容器对打印布局的影响
  - `html, body` 在 `@media print` 中必须 `margin: 0; padding: 0; width: auto; height: auto; overflow: hidden`，不要恢复 `height: 100%`，否则 Chromium 会生成空白第二页

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
- 摄像头权限拒绝、启动失败、手动输入为空、手动输入查不到资产时，应给出面向普通员工的具体提示，不要只报技术错误。
- 移动端仪表盘和"我的资产"页有扫码入口卡片（`.stat-scan` + `.mobile-only` CSS 模式）
- 桌面端隐藏扫码入口：`.mobile-only { display: none }` + `@media (max-width: 768px) { display: block !important }`

### 操作记录

- `log_activity(conn, user_id, action, target_type, target_id, detail)` 在已有连接中执行
- 所有变更 API（CRUD + 生命周期 + 审批 + 设置修改 + 导出）都埋了记录

### 墨粉管理（轻量 slot 模型）

- **设计定位**：轻量 slot，专用于打印机墨粉（toner）的当前状态跟踪和更替历史记录。
- **墨粉范围约束**：`type` 固定为 `toner`，API 拒绝其他类型（ink/drum/paper/ribbon/other）；`model` 限定为 `原装` 或 `国产`。
- **打印机类型**：`asset.printer_type` 字段（`mono`/`color`）决定允许的墨粉颜色：`mono` 仅允许黑色，`color` 允许黑/青/品/黄四色。
- `/consumables` 和 `GET /api/printers/consumables` 以 `asset.category='printer'` 为主数据源：普通打印机资产即使尚未配置耗材 slot，也会出现在墨粉管理；标签打印机会按 `_is_label_printer()` 过滤。
- 未配置 slot 的打印机返回 `printer_type='unconfigured'`、`consumables=[]`，前端显示待配置状态，并提供为当前打印机新增墨粉的入口。
- 一台打印机可有多个 `printer_consumable` 行（黑/青/品/黄各一支墨粉等），各自独立跟踪。
- `printer_consumable` 记录当前 slot 状态：`color`、`model`、`current_price`、`installed_at`、`stock`、`threshold`。
- `consumable_replacement` 记录更替历史：归档旧周期快照（价格、安装日期、使用天数、日均成本）+ 新周期参数。
- `POST /api/consumables/<id>/replace`：创建一条 replacement 记录，计算 `usage_days=max(replaced_at - old_installed_at, 1)` 和 `daily_cost=price/usage_days`（保留 2 位），更新当前 slot 的 `installed_at` 和 `current_price`，可选 `use_stock=true` 扣减库存 -1。
- `use_stock=true` 且 `stock <= 0` 时返回 400。
- 更替只影响该耗材行，不影响同一打印机的其他耗材。
- 列表/详情响应自动计算 `usage_days` 和 `estimated_daily_cost`（服务端 `_consumable_usage_fields()` 辅助函数）。
- 前端 `consumables.html` 提供更换墨粉弹窗（更换日期、新价格、库存取用、原因、备注）和历史弹窗。

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
- 设置页预览和资产抽屉预览复用 `base.html` 的 `createPhysicalLabel(asset, qrSrc, options)`；若上传了 Logo，传 `options.logoUrl`；字段配置通过 `options.fields` 传入
- **布局结构**：`.label-header`（Logo 11mm + `.label-meta-tags` 文字区）+ `.label-footer-zone`（数字编号 7mm + QR 20mm）
- **打印时标签缩小为 57.6×37.6mm**：`@media print` 中 `.physical-label`/`.label-card` 设为 `width: 57.6mm; height: 37.6mm; margin: 1.1mm`，四周安全边距防止溢出和空白第二页
- 如需更多字段，追加到 `.label-meta-tags`/`.label-text` 内；辅助字段必须受 `LABEL_FIELDS_MAX=3` 限制，保持内容不溢出
- **XSS 防护**：批量标签 `buildPrintLabel()` 用 `escapePrintText()` 转义资产字段；单标签 `label.html` 用 `textContent` 写入

### 用户管理

- `DELETE /api/users/<id>` 有三层保护：不能删自己（400）、不能删最后一个管理员（400）、不能删持有未归还资产的用户（400）。
- 用户创建/编辑/密码重置均通过管理端 API，密码使用 `werkzeug.security` 哈希存储。
- API 响应不暴露 `password_hash` 字段。

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
