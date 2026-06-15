# 改动历史

## 2026-06-15：v1.4 移动端交互与前端安全修复

- 全局交互：新增移动端友好的 toast、确认框和输入框，替换多处原生 `alert/prompt`，让删除、恢复、永久删除和密码修改反馈更一致。
- 资产抽屉：标签 Logo/字段配置改为异步补充，不再阻塞资产详情首屏；配置加载失败可在后续重试，并加请求序号避免快速切换资产时旧请求覆盖新内容。
- 标签预览：资产抽屉统一读取 `/api/settings/logo` 和 `/api/settings/label`，保持与单标签、批量标签和设置页一致。
- 员工自助：提交申请成功后显示 toast 并延迟跳转，同时禁用提交按钮和本地防重复提交，避免重复申请。
- 员工页面安全渲染：我的申请和员工资产详情从 `innerHTML` 拼接改为 DOM 构造，用户可控字段全部走 `textContent`。
- 移动端布局：我的申请表格增加横向滚动容器；我的资产页标题和入口文案改为中文，返回按钮恢复为稳定的 `/` 导航。
- 扫码页：移除未使用的扫码结果渲染函数，保留现有扫码/手输标签跳转流程。
- 测试：`.venv/bin/python -m pytest tests/ -q` → 306 passed。

## 2026-05-26：标签打印优化、资产台账与抽屉 UI 重构

### 标签打印优化
- 打印尺寸修复：标签内容从 60×40mm 缩小为 58×38mm + 1mm 安全边距，解决打印时内容溢出到第二页和触碰纸张边缘的问题。
- 单位体系统一：标签内所有元素（Logo 11mm、标题 3.8mm、标签号 2.8mm、数字编号 7mm、QR 20mm）统一使用 mm 单位，不再混用 px。
- 打印 CSS 修复：从 `visibility: hidden` 方案改为 `display: none` / `display: contents`，避免隐藏元素占空间导致布局问题。
- `@media print` 中强制 `html, body { margin: 0; padding: 0; width: 100%; height: 100% }`。

### 资产台账 UI 重构（按 Gemini demo 实现）
- 工具栏：`.asset-toolbar` → `.toolbar`，状态筛选 `.status-tabs` → `.filter-tabs` / `.tab-btn`，类别筛选改为 `.category-select`，搜索框改为 `.search-wrapper` / `.search-input`。
- 表格：`.asset-data-table` → `.ledger-table`，列宽微调，新增 `.tag-link`、`.opt-link`、`.status-badge` 样式。
- 分页：改为 `.pagination-wrapper` > `.pagination-row` + `.pagination-info` 结构。
- 批量操作栏：新增 `.batch-info`、`.btn-batch-action` 样式类。

### 详情抽屉重构
- 抽屉结构从直接 padding 改为 `.drawer-body` 子容器滚动，新增 `.drawer-icon-banner`（48px emoji 横幅替代 CSS 绘制显示器）、`.drawer-tools`（4 列 grid 按钮组）、`.info-mini-grid` / `.info-mini-card`（双列属性卡片）、`.mini-timeline`（简洁时间线）、`.label-preview-box`（虚线框标签预览）。
- 旧类名保留为兼容别名（`.drawer-toolbar`、`.drawer-meta-grid` 等），不影响其他页面。

### 墨粉管理增强
- Tab 导航：墨粉总览 / 更换历史 / 成本分析三个 Tab 页签。
- 更换历史：新增 `GET /api/consumables/replacements` 全局更换记录 API（支持按打印机/颜色/日期范围筛选）。
- 成本分析：新增 `GET /api/consumables/cost-summary` 聚合成本 API（总花费/更换次数/加权日均/按打印机汇总/月度趋势）。
- 墨粉自动命名：`POST /api/consumables` 的 `name` 字段改为可选，未提供时自动生成 `{打印机名} - {颜色中文}`。
- 黑白打印机颜色锁定：`openCreateForPrinter()` 根据 `printer_type` 自动锁定颜色选项。

### 测试
- `.venv/bin/python -m pytest tests/ -q` → 192 passed。

## 2026-05-25：墨粉管理、用户管理与文档同步

本轮把文档同步到当前未提交实现，重点覆盖打印机墨粉管理和用户管理：

- 墨粉管理：新增 `printer_consumable` 和 `consumable_replacement`，采用以打印机为中心的轻量 slot 模型，支持颜色/型号/当前价格/安装日期/库存阈值、库存调整、更替历史、使用天数和日均成本。
- 打印机聚合视图：新增 `/api/printers/consumables`，按打印机分组返回墨粉 slot，支持彩色/黑白筛选和低库存筛选，并排除标签打印机。
- 墨粉管理页面：新增 `/consumables` 与 `templates/admin/consumables.html`，采用打印机卡片 + 详情面板布局。
- 用户管理：新增 `/users` 与 `templates/admin/users.html`，支持用户创建、编辑、角色调整、密码重置和删除。
- 用户安全保护：删除用户时服务端保护不能删自己、不能删最后一个管理员、不能删仍持有未归还资产的用户；用户 API 不暴露 `password_hash`。
- 资产列表易用性：补充空状态、批量标签禁用提示、分页范围说明、CSV 导入说明等约定。
- 文档：更新 `README.md`、`CLAUDE.md`、`docs/frontend-design-spec.md` 与本 CHANGELOG，使页面/API/测试数量与当前代码一致。
- 验证：`.venv/bin/python -m pytest tests/ -q` → 158 passed。

## 2026-05-21：文本对齐、标签打印与侧边栏展开

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

## 2026-05-21：前端重构与标签修复说明

本轮按 UI 设计稿完成管理端前端重构，并修复标签/Logo 问题：

- 全局壳：`base.html` 管理端改为 `.app-container` Grid 布局，左侧 200px 展开侧边栏（图标+文字菜单项）、顶部 header、主内容区、全局右侧 `.detail-drawer`；员工和公开页面保留轻量壳。
- 样式令牌：`style.css` 新增 `--color-*`、`--space-*`、`--radius-*`、`--shadow-*` Design Tokens，并保留旧变量别名兼容未重构页面。
- Dashboard：`templates/admin/dashboard.html` 改为 5 连 `.metric-card`、原生 SVG sparkline、趋势图和 Donut 图，不引入重型前端库。
- 资产台账：`templates/admin/assets.html` 改为状态 Tabs、无垂直线 `.asset-data-table`、搜索/筛选工具栏、行点击事件代理打开右侧详情抽屉。
- 详情抽屉：`base.html` 内 `openAssetDetailDrawer(id)` 使用 `/api/assets/<id>`，安全 DOM 构造资产信息、工具栏、元数据、生命周期时间线和标签预览。
- 员工资产页：`templates/employee/my_assets.html` 改为移动端卡片、分类色条和底部扫码 FAB。
- 标签设计：单标签、批量标签、设置页预览、资产抽屉预览统一为 60mm×40mm 的 Logo + 资产信息 + 数字编号 + QR。
- Logo 修复：修复 `POST /api/settings/logo` 中 `_os.abspath` 拼写错误；上传后路径保存为 `/static/uploads/company_logo.*`，设置页预览、单标签页、批量标签和抽屉预览都会读取显示。
- 打印修复：`templates/admin/label.html` 的 `@media print` 显示 `#labelContent`，避免父容器隐藏导致打印空白。
- 测试：新增企业 Logo 上传回归测试。当前验证：`.venv/bin/python -m pytest tests/ -q` → 61 passed；headless Chromium 检查 `/dashboard`、`/assets`、`/settings`、资产抽屉、`/my/assets` 关键 DOM 正常。

## 2026-05-21：Code Review 修复说明

本轮按计划评审结果做了偏功能/维护性的修复，目的是避免增强功能在新装、异常参数或部分失败时出现 500/静默不一致：

- 新装初始化：`SCHEMA` 已包含 `asset.warranty_date`、`activity_log`、`app_config`；`init_db.py`/`server.py` 对全新 DB 只依赖 `SCHEMA`，对已有 DB 才调用 `upgrade_db()` 补旧结构。
- 分页参数：`/api/assets`、`/api/activity` 改用 `_parse_positive_int_arg()`，非数字、小于 1 的 page/limit 返回 400；limit 上限 200。
- 标签设置：`GET /api/settings/label` 对损坏 JSON 回退默认 `['name']`；`PUT` 校验 fields 必须是数组。
- 配置事务：`Database.set_config()` 支持传入现有 `conn`；标签字段、QR base URL、Logo 上传的配置写入与 `activity_log` 保持同事务。
- 批量标签：`POST /api/batch-labels` 现在校验 `asset_ids` 必须是非重复数字数组，任一资产不存在返回 400，不再静默漏打或触发外键 500。
- CSV 导出：Response mimetype 改为 `text/csv`，避免 Flask 自动 charset 与手写 charset 重复；仍保留 UTF-8 BOM。
- 标签页权限：`/assets/<id>/label` 明确为 admin 页面，员工访问重定向登录页。
- 测试：新增增强回归测试，覆盖 init_db 新装、旧 MVP schema 迁移、upgrade_db 幂等/密码迁移、坏 label_fields JSON、分页非法参数、配置事务、CSV Content-Type、标签页权限、批量标签缺失资产。验证：`.venv/bin/python -m pytest tests/ -q` → 57 passed。
