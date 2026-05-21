# 改动历史

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
- 标签设计：单标签、批量标签、设置页预览、资产抽屉预览统一为 60mm×40mm 的 Logo + 资产信息 + 数字编号 + QR；明确移除一维码/模拟条码。
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
