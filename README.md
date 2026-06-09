# IT 资产管理系统

轻量级 IT 固定资产管理追踪系统，面向 IT 管理员和普通员工。

当前实现已从早期 MVP 扩展为可用的单机版管理系统：资产全生命周期、标签打印、扫码查询、CSV 导入导出、操作记录、用户管理，以及以打印机为中心的墨粉 slot 管理。

## 功能概览

- **资产管理**：资产台账（编号、类别、品牌、型号、序列号、状态、归属人/部门、位置、保修日期）。
- **生命周期追踪**：入库 → 分配/领用 → 归还 → 转移 → 维修 → 报废，完整事件时间线。
- **维修记录**：故障描述、维修状态、费用、维修备注。
- **员工自助**：移动端友好的资产查看、申请提交。
- **标签打印**：60×40mm QR 资产标签，支持 Logo、可配置字段、浏览器打印和批量打印。
- **扫码查询**：移动端摄像头扫码页和公开资产摘要页；匿名流只展示最小必要字段。
- **CSV 导入导出**：导出带 UTF-8 BOM，兼容 Excel/BarTender；导入支持行级错误返回。
- **操作记录**：资产、生命周期、审批、设置、导出等关键变更写入 activity_log。
- **用户管理**：管理员可创建/编辑用户、重置密码、删除用户；服务端保护最后管理员、自删除和仍持有资产的用户。
- **打印机墨粉管理**：以打印机为中心管理墨粉 slot、库存阈值、安装日期、当前价格、更替历史和日均成本。

## 技术栈

- **后端**：Python Flask 3.1 + SQLite（原生 SQL）
- **前端**：Jinja2 + 响应式 HTML + CSS + 原生 JavaScript
- **二维码**：Python `qrcode` + Pillow
- **测试**：pytest
- **构建**：无前端框架、无 npm、无构建步骤

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据库并填充演示数据（会清空旧数据）
python3 init_db.py

# 3. 启动服务
python3 server.py
```

浏览器访问 http://localhost:5000

## 演示账号

| 角色 | 工号 | 密码 | 说明 |
|------|------|------|------|
| 管理员 | `admin` | `admin123` | 完整管理权限 |
| 员工 | `emp001` | `emp001` | 张三（研发部） |
| 员工 | `emp002` | `emp002` | 李四（市场部） |
| 员工 | `emp003` | `emp003` | 王五（财务部） |

## 运行测试

```bash
.venv/bin/python -m pytest tests/ -q
```

当前测试规模：202 个 pytest 测试。

## 生产部署

### 安装

```bash
cd /home/yobai/it-asset-manager
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python init_db.py          # 首次初始化数据库
```

### 使用 Gunicorn 运行（推荐）

```bash
.venv/bin/gunicorn -c gunicorn.conf.py "server:app"
```

### 使用 systemd 管理

```bash
sudo cp contrib/it-asset-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now it-asset-manager
sudo systemctl status it-asset-manager
```

### Caddy 反向代理

```
http://your-server:9090 {
    reverse_proxy 127.0.0.1:5000
}
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | Flask 会话密钥，不设置则自动生成并保存到 `.secret_key` | 自动生成 |
| `DB_PATH` | SQLite 数据库文件路径 | `it_asset.db` |
| `FLASK_DEBUG` | 开发模式（`1`/`true`/`yes`），仅用于 `python server.py` 启动 | 关闭 |

## 页面说明

### 管理员页面

| 页面 | 路由 | 说明 |
|------|------|------|
| 仪表盘 | `/dashboard` | 统计卡片、分类分布、保修提醒、最近事件 |
| 资产列表 | `/assets` | 搜索、筛选、分页、右侧详情抽屉、批量标签、CSV 导出/导入 |
| 新增资产 | `/assets/new` | 表单创建，自动生成标签号 |
| 资产详情 | `/assets/:id` | 基本信息、生命周期时间线、维修记录、操作按钮 |
| 编辑资产 | `/assets/:id/edit` | 编辑资产信息 |
| 标签打印 | `/assets/:id/label` | 60×40mm QR 标签打印页 |
| 申请审核 | `/applications` | 查看、批准、驳回员工申请 |
| 维修总览 | `/maintenance` | 维修记录列表 |
| 墨粉管理 | `/consumables` | 打印机卡片、墨粉 slot、库存告警、更替历史 |
| 用户管理 | `/users` | 创建/编辑用户、角色、密码重置、删除保护 |
| 系统设置 | `/settings` | Logo、标签字段、QR 地址配置 |
| 操作记录 | `/activity` | activity_log 查询 |

### 员工自助页面（移动端响应式）

| 页面 | 路由 | 说明 |
|------|------|------|
| 我的资产 | `/my/assets` | 名下资产卡片列表，移动端扫码入口 |
| 资产详情 | `/my/assets/:id` | 只读详情 + 时间线 |
| 我的申请 | `/my/applications` | 历史申请状态 |
| 提交申请 | `/my/applications/new` | 新建资产申请 |

### 公开页面

| 页面 | 路由 | 说明 |
|------|------|------|
| 登录 | `/login` | 工号 + 密码登录 |
| 摄像头扫码 | `/scan` | html5-qrcode 调用后置摄像头，也支持手动输入资产编号 |
| 资产扫码落地页 | `/scan/:id` | 匿名公开资产摘要，最小字段集 |

## 标签打印说明

1. 在资产详情、资产列表或批量标签入口点击「标签」。
2. 标签尺寸固定为 60mm × 40mm，适配热转印标签纸。
3. 标签内容为 Logo + 资产信息 + 数字编号 + QR 码。
4. 标签字段、Logo、QR base URL 可在设置页配置。
5. CSV 导出中的 QR URL 使用配置的 base URL + `/scan/{id}`，便于 BarTender 或外部流程使用。

## 墨粉管理说明

墨粉模块采用轻量 slot 模型，服务打印机维护场景。

- 一台打印机可关联多个 `printer_consumable` slot，例如黑/青/品红/黄墨粉。
- 墨粉记录当前 slot 状态：颜色、墨粉型号、当前价格、安装日期、库存、阈值。
- 更替操作会写入 `consumable_replacement` 历史，归档旧周期价格、使用天数、日均成本，并更新当前 slot。
- `use_stock=true` 时从库存扣 1；库存不足返回 400。
- `/api/printers/consumables` 按打印机聚合返回墨粉 slot，支持彩色/黑白筛选、低库存筛选，并排除标签打印机。

## 项目结构

```text
it-asset-manager/
├── server.py                 # Flask 应用：页面路由 + JSON/CSV/API
├── models.py                 # 常量、SQLite schema、Database 封装、迁移
├── init_db.py                # 数据库初始化 + 演示种子数据
├── requirements.txt          # Flask, gunicorn, qrcode, Pillow, pytest
├── it_asset.db               # SQLite 数据库文件（运行时生成）
├── CLAUDE.md                 # 当前最完整的开发/维护文档
├── CHANGELOG.md              # 改动历史
├── IT_ASSET_MVP_SPEC.md      # 早期 MVP 规格，作为历史参考
├── docs/
│   └── frontend-design-spec.md
├── static/
│   ├── style.css             # Design Tokens、App Shell、表格、标签、墨粉管理 UI、移动端样式
│   └── uploads/              # 企业 Logo 上传目录
├── templates/
│   ├── base.html             # 管理端 App Shell、全局详情抽屉、apiFetch()
│   ├── login.html
│   ├── scan.html
│   ├── scan_camera.html
│   ├── admin/
│   │   ├── dashboard.html
│   │   ├── assets.html
│   │   ├── asset_detail.html
│   │   ├── asset_form.html
│   │   ├── label.html
│   │   ├── applications.html
│   │   ├── maintenance.html
│   │   ├── consumables.html
│   │   ├── users.html
│   │   ├── settings.html
│   │   └── activity.html
│   └── employee/
│       ├── my_assets.html
│       ├── asset_detail.html
│       ├── applications.html
│       └── application_form.html
└── tests/
    └── test_api.py           # 202+ 个自动化测试
```

## API 端点

### 认证

- `POST /api/login` — 登录
- `POST /api/logout` — 退出
- `GET /api/me` — 当前用户信息

### 资产

- `GET /api/assets` — 资产列表（支持 category/status/search/page/limit）
- `POST /api/assets` — 新增资产
- `GET /api/assets/:id` — 资产详情（含事件+维修记录）
- `PUT /api/assets/:id` — 编辑资产
- `DELETE /api/assets/:id` — 删除（仅 in_stock 状态）
- `GET /api/assets/export` — CSV 导出
- `POST /api/assets/import` — CSV 批量导入

### 生命周期

- `POST /api/assets/:id/assign` — 分配
- `POST /api/assets/:id/return` — 归还
- `POST /api/assets/:id/transfer` — 转移
- `POST /api/assets/:id/maintenance` — 送修
- `POST /api/assets/:id/maintenance/:rid/resolve` — 维修完成
- `POST /api/assets/:id/scrap` — 报废
- `GET /api/assets/:id/events` — 生命周期事件

### 维修

- `GET /api/maintenance` — 维修记录列表
- `GET /api/assets/:id/maintenance` — 指定资产维修记录

### 申请

- `GET /api/applications` — 全部申请
- `POST /api/applications` — 管理端创建申请
- `PUT /api/applications/:id/approve` — 批准
- `PUT /api/applications/:id/reject` — 驳回

### 员工自助

- `GET /api/my/assets` — 名下资产
- `GET /api/my/applications` — 我的申请
- `POST /api/my/applications` — 提交申请

### 统计、分类、操作记录

- `GET /api/stats` — 仪表盘统计数据（含保修即将到期/已过期）
- `GET /api/categories` — 分类元数据
- `GET /api/activity` — 操作记录列表
- `GET /api/activity/export` — 操作记录 CSV 导出（支持 `?action=` 筛选）

### 标签与设置

- `GET /api/assets/:id/qr` — 二维码 PNG 图片
- `POST /api/batch-labels` — 批量标签数据
- `GET/PUT /api/settings/label` — 标签字段配置
- `GET/PUT /api/settings/qr-base-url` — QR base URL 配置
- `GET/POST/DELETE /api/settings/logo` — 企业 Logo 配置

### 墨粉管理

- `GET /api/consumables` — 墨粉列表
- `POST /api/consumables` — 新建墨粉 slot
- `GET/PUT/DELETE /api/consumables/:id` — 查看、编辑、删除墨粉 slot
- `POST /api/consumables/:id/adjust` — 库存调整
- `POST /api/consumables/:id/replace` — 墨粉更替并记录历史
- `GET /api/consumables/:id/replacements` — 更替历史
- `GET /api/printers/consumables` — 按打印机聚合的墨粉视图

### 用户管理

- `GET /api/users` — 用户列表
- `POST /api/users` — 创建用户
- `GET /api/users/:id` — 用户详情
- `PUT /api/users/:id` — 编辑用户
- `POST /api/users/:id/reset-password` — 重置密码
- `DELETE /api/users/:id` — 删除用户（含服务端保护）

### 员工管理

- `GET /api/employees` — 员工列表
- `POST /api/employees` — 新增员工
- `PUT /api/employees/:id` — 编辑员工
- `DELETE /api/employees/:id` — 删除员工
- `POST /api/employees/import` — CSV 批量导入
- `GET /api/employees/import/template` — CSV 导入模板下载

### 公开扫码

- `GET /api/public/asset/:id` — 公开资产摘要
- `GET /api/public/asset-lookup?asset_tag=...` — 按资产编号查公开资产

### 系统运维

- `GET /api/health` — 健康检查（无需认证）

## 数据库和迁移约定

- `models.py` 中的 `SCHEMA` 是全新安装的完整当前结构。
- `upgrade_db()` 只负责旧 SQLite 文件幂等补齐，不应成为新装依赖。
- 新增表必须同时进入 `SCHEMA` 和旧库迁移逻辑；新增列需用 `PRAGMA table_info` 判断后 `ALTER TABLE`。
- 旧库兼容要有专门测试 fixture，避免被当前 schema 初始化路径掩盖。
- 密码存储使用 Werkzeug hash，旧明文密码由 `upgrade_db()` 自动迁移。

## 已知限制

- 认证为 session + 本地用户，生产环境可接 SSO/LDAP。
- 单级审批，无复杂审批流。
- 无采购/合同管理。
- 无资产自动发现/网络扫描。
- 中文界面，未国际化。
- 当前启动方式支持 Gunicorn + systemd 生产部署，开发模式用 `python3 server.py`。
