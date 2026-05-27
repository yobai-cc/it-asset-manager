# IT 资产管理系统 — 前端设计需求稿

> 版本：v1.1 | 更新日期：2026-05-25
> 基于当前 Flask + Jinja2 + vanilla JS 实现整理，覆盖资产、标签、扫码、墨粉管理、用户管理等页面与 API。

---

## 1. 项目背景

IT 固定资产追踪管理系统，服务两类用户：

| 角色 | 核心场景 | 使用设备 |
|------|---------|---------|
| IT 管理员 | 资产全生命周期管理、审批、统计、标签打印、墨粉维护、用户管理 | 桌面为主 |
| 普通员工 | 查看名下资产、提交领用申请、扫码查看公开资产摘要 | 桌面 + 移动 |

特殊场景：管理员使用热转印打印机 + BarTender 打印 60×40mm 资产标签；移动端可扫码查看公开资产摘要。

### 技术约束

- 无前端框架，vanilla JS + Jinja2。
- 无构建步骤，无 npm。
- Flask + SQLite + Caddy 反代。
- 目标浏览器：Chrome 90+、Safari 15+、Edge 90+。
- 前端动态渲染数据库字段时优先使用 `textContent` / DOM 构造，避免把用户可控字段直接拼入 `innerHTML`。

---

## 2. 设计语言

### 色彩体系

主色：
- `--color-primary: #2563eb`
- `--color-primary-dark: #1d4ed8`

功能色：
- `--color-success: #10b981`
- `--color-warning: #f59e0b`
- `--color-danger: #ef4444`
- `--color-info: #3b82f6`

中性色：
- `--color-bg-main: #f8fafc`
- `--color-bg-card: #ffffff`
- `--color-border: #e2e8f0`
- `--color-text-main: #0f172a`
- `--color-text-muted: #64748b`

### 分类色

- computer: `#2563eb`
- monitor: `#7c3aed`
- phone: `#059669`
- tablet: `#d97706`
- printer: `#dc2626`
- server: `#475569`
- network: `#0891b2`
- firewall: `#be185d`
- switch: `#65a30d`

---

## 3. 页面与交互原则

### 管理端 App Shell

- 管理员页面统一使用 `base.html` 的 `.app-container`。
- 左侧 200px 展开侧边栏，菜单显示图标 + 中文文字。
- 顶部 header 显示页面信息和用户操作。
- 主内容区域使用卡片、表格、详情抽屉组合。
- 全局右侧 `.detail-drawer` 用于资产快速详情。

### 员工与公开页面

- 员工自助页和公开扫码页使用轻量壳，不强套管理端侧边栏。
- 移动端优先展示卡片、扫码入口和明确错误提示。
- 摄像头权限拒绝、启动失败、手动输入为空、资产不存在时，应给普通用户可理解的提示。

### 安全渲染

- 资产字段、备注、人员名、公开扫码页内容优先使用 `textContent` / `createElement`。
- 不要把数据库字段直接拼进 `innerHTML`。
- 公开扫码接口只返回最小必要字段，不能复用管理端 `/api/assets` 列表接口。

---

## 4. 页面路由清单

### 管理员页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/dashboard` | 仪表盘 | 统计卡片、趋势图、分类分布、保修提醒、最近事件 |
| `/assets` | 资产台账 | 状态 Tabs、搜索/筛选、分页、右侧详情抽屉、批量标签、CSV 导入导出 |
| `/assets/new` | 新增资产 | 表单创建，自动生成 asset_tag |
| `/assets/<id>` | 资产详情 | 基本信息、生命周期、维修记录、操作按钮 |
| `/assets/<id>/edit` | 编辑资产 | 资产字段编辑 |
| `/assets/<id>/label` | 标签打印 | 60×40mm QR 标签页 |
| `/applications` | 申请审核 | 管理员批准/驳回员工申请 |
| `/maintenance` | 维修总览 | 待处理/维修中/已完成维修记录 |
| `/consumables` | 墨粉管理 | 打印机卡片、墨粉 slot、库存告警、更替历史 |
| `/users` | 用户管理 | 用户 CRUD、角色、密码重置、删除保护 |
| `/settings` | 系统设置 | Logo、标签字段、QR base URL |
| `/activity` | 操作记录 | activity_log 列表 |

### 员工页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/my/assets` | 我的资产 | 名下资产卡片、移动端扫码入口 |
| `/my/assets/<id>` | 资产详情 | 员工视角只读详情和时间线 |
| `/my/applications` | 我的申请 | 申请历史状态 |
| `/my/applications/new` | 提交申请 | 选择资产类别并填写理由 |

### 公共页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | 登录 | 工号 + 密码 |
| `/scan` | 摄像头扫码 | html5-qrcode 后摄扫描 + 手动输入 |
| `/scan/<id>` | 扫码落地页 | 公开资产摘要，最小字段集 |

---

## 5. 重点页面设计要求

### 5.1 资产台账 `/assets`

- 状态 Tabs 使用中文：全部、在用、库存、维修中、已报废。
- 表格行点击通过 `#asset-table-body` 事件代理打开 `openAssetDetailDrawer(id)`。
- 无匹配数据时显示 `.empty-state`，不要只留空表格。
- 批量标签栏在当前页有资产时保持可见：未勾选时提示“请先勾选资产”并禁用按钮，勾选后显示“N 项已选”。
- 分页区域除页码外显示 `.pagination-info` 范围说明，例如“第 1-15 条，共 42 条”。
- CSV 导入弹窗说明 UTF-8 编码、必填列 `name`/`category`、常用可选列，并建议先导出 CSV 作为参考。

### 5.2 标签打印

- 标签尺寸固定为 60mm × 40mm。
- 标签结构：Logo + 资产名称/标签号/自定义字段 + 数字编号 + QR。
- 单标签页、批量标签、设置页预览、资产抽屉预览应保持同一视觉结构。
- 标签字段来自 `/api/settings/label`，Logo 来自 `/api/settings/logo`。
- 打印 CSS 需要确保非打印 UI 隐藏，标签内容保持物理比例和边距。

### 5.3 墨粉管理 `/consumables`

设计定位：以打印机为中心的轻量墨粉 slot 管理。

- 首页优先展示打印机卡片，而不是单纯的墨粉表格。
- 彩色机和黑白机分别处理；标签打印机不纳入墨粉管理模块。
- 打印机卡片展示：资产编号、名称、品牌/型号、彩色/黑白、slot 数、低库存告警。
- 点选打印机后展示其墨粉 slot：颜色、墨粉型号、库存、阈值、当前价格、安装日期、使用天数、估算日均成本。
- 支持新增/编辑墨粉、库存调整、更替墨粉、查看更替历史。
- 更替墨粉应能选择是否从库存取用；库存不足时显示明确错误。

### 5.4 用户管理 `/users`

- 用户列表展示工号、姓名、部门、联系方式、角色、创建时间。
- 支持创建用户、编辑基本信息、调整角色、重置密码、删除用户。
- 删除保护必须来自服务端，而不只是前端禁用：
  - 不能删除自己。
  - 不能删除最后一个管理员。
  - 不能删除仍持有未归还资产的用户。
- API 响应不显示 `password_hash`。

### 5.5 公开扫码页

- `/scan` 优先调用后置摄像头。
- 手动输入支持资产编号查找。
- 错误提示要面向普通员工，例如“未找到该资产，请确认标签编号是否输入完整”。
- `/scan/<id>` 只展示公开字段，不能展示持有人部门等敏感信息。

---

## 6. API 约定

### 公开扫码相关

- `GET /api/public/asset/<id>`
- `GET /api/public/asset-lookup?asset_tag=...`

说明：公开扫码流只返回最小必要字段，不复用 `/api/assets` 列表接口。

### 资产与生命周期

- `GET/POST /api/assets`
- `GET/PUT/DELETE /api/assets/<id>`
- `POST /api/assets/<id>/assign|return|transfer|maintenance|scrap`
- `POST /api/assets/<id>/maintenance/<rid>/resolve`
- `GET /api/assets/<id>/events`

### 标签、设置、导出

- `GET /api/assets/<id>/qr`
- `POST /api/batch-labels`
- `GET/PUT /api/settings/label`
- `GET/PUT /api/settings/qr-base-url`
- `GET/POST/DELETE /api/settings/logo`
- `GET /api/assets/export`
- `POST /api/assets/import`

### 墨粉管理

- `GET /api/consumables`
- `POST /api/consumables`
- `GET/PUT/DELETE /api/consumables/<id>`
- `POST /api/consumables/<id>/adjust`
- `POST /api/consumables/<id>/replace`
- `GET /api/consumables/<id>/replacements`
- `GET /api/printers/consumables`

### 用户管理

- `GET /api/users`
- `POST /api/users`
- `GET /api/users/<id>`
- `PUT /api/users/<id>`
- `POST /api/users/<id>/reset-password`
- `DELETE /api/users/<id>`

---

## 7. 开发注意事项

- 新增分类时，需同步更新分类名、图标、颜色、前缀。
- 新增变更型 API 时，成功后应记录 `activity_log`。
- 设置类写入若同时记录日志，应使用同一事务。
- 公共扫码页面要优先考虑匿名用户能看到的最小数据集。
- 改动数据库时，`SCHEMA` 必须是新装完整结构；旧库补齐放入幂等迁移并配套测试。
- 前端新增动态渲染优先使用安全 DOM API。
- 提交前运行 `.venv/bin/python -m pytest tests/ -q`。

---

## 8. 当前状态说明

当前实现已覆盖：

- 资产 CRUD
- 生命周期管理
- 维修记录
- 申请审核
- 标签打印
- QR 扫码
- CSV 导入/导出
- 操作记录
- Logo 上传
- 标签字段配置
- 公共扫码最小信息页
- 用户管理
- 打印机墨粉 slot 管理
- 墨粉更替历史和日均成本估算

当前测试规模：158 个 pytest 测试。
