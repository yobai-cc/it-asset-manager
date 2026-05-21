# IT 资产管理系统 — 前端设计需求稿

> 版本：v1.0 | 日期：2026-05-21
> 基于当前已实现功能整理，覆盖全部页面路由和 API。

---

## 1. 项目背景

IT 固定资产追踪管理系统，服务两类用户：

| 角色 | 核心场景 | 使用设备 |
|------|---------|---------|
| IT 管理员 | 资产全生命周期管理、审批、统计、标签打印 | 桌面为主 |
| 普通员工 | 查看名下资产、提交领用申请 | 桌面 + 移动 |

特殊场景：管理员使用热转印打印机 + BarTender 打印 60×40mm 资产标签；移动端可扫码查看资产公开信息。

### 技术约束

- 无前端框架，vanilla JS + Jinja2
- 无构建步骤，无 npm
- Flask + Caddy 反代
- 目标浏览器：Chrome 90+、Safari 15+、Edge 90+

---

## 2. 设计语言

### 色彩体系

主色：
- `--primary: #2563eb`
- `--primary-dark: #1d4ed8`

功能色：
- `--success: #16a34a`
- `--warning: #d97706`
- `--danger: #dc2626`

中性色：
- `--bg: #f8fafc`
- `--card: #ffffff`
- `--border: #e2e8f0`
- `--text: #1e293b`
- `--text-muted: #64748b`

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

### 桌面端

- 以表格、卡片、详情页为主
- 资产列表支持筛选、分页、导出、批量标签
- 资产详情页展示生命周期和维修记录

### 移动端

- `/scan` 提供摄像头扫码入口
- `/scan/<id>` 展示公开资产摘要
- 员工扫码后只看到必要公开信息和登录入口

---

## 4. 路由清单

### 管理员页面

- `/dashboard`
- `/assets`
- `/assets/new`
- `/assets/<id>`
- `/assets/<id>/edit`
- `/assets/<id>/label`
- `/applications`
- `/maintenance`
- `/settings`
- `/activity`

### 员工页面

- `/my/assets`
- `/my/assets/<id>`
- `/my/applications`
- `/my/applications/new`

### 公共页面

- `/login`
- `/scan`
- `/scan/<id>`

---

## 5. API 约定

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

---

## 6. 关键实现规则

### 安全渲染

- 资产字段、标签字段、公开扫码页内容必须使用 `textContent` 或安全 DOM 构造
- 避免把数据库字段直接拼进 `innerHTML`
- 公共页面只展示最小必要字段

### CSV 导入

- 必填列：`name`、`category`
- `status` 必须校验是否属于 `VALID_STATUSES`
- 非法行要返回行级错误并跳过

### 标签打印

- 标签尺寸 60mm × 40mm
- 左侧 Logo + 标签号 + 字段，右侧 QR 码
- 单标签和批量标签保持一致的渲染逻辑

---

## 7. 开发注意事项

- 新增分类时，需同步更新分类名、图标、颜色、前缀
- 新增变更型 API 时，成功后应记录 activity_log
- 设置类写入若同时记录日志，应使用同一事务
- 公共扫码页面要优先考虑匿名用户能看到的最小数据集

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
