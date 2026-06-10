# 架构文档

## 整体架构

```
浏览器 ──HTTP──> Flask (server.py)
                      │
                      ├── 页面路由 → Jinja2 模板渲染
                      ├── API 路由 → JSON 响应
                      └── Database (models.py) → SQLite 文件
```

单进程、单文件 Flask 应用，所有路由和业务逻辑在 `server.py` 中。`models.py` 提供数据库封装和常量定义。无微服务、无消息队列。

## 数据库设计

SQLite 文件 `it_asset.db`，10 张表：

```
employee (员工花名册)
├── id PK
├── employee_id TEXT UNIQUE (兼容字段，非前端主展示字段)
├── name NOT NULL
├── department
├── status [active|inactive]
├── notes
├── created_at
└── updated_at

user (系统登录账号)
├── id PK
├── employee_id TEXT UNIQUE NOT NULL
├── name NOT NULL
├── department
├── phone
├── email
├── role [admin|employee]
├── password_hash
└── created_at

asset (资产台账)
├── id PK
├── asset_tag UNIQUE NOT NULL
├── name / category / brand / model / serial_number
├── status [in_stock|assigned|maintenance|scrapped]
├── current_holder_id → employee
├── location / purchase_date / purchase_price / warranty_date
├── printer_type [mono|color|NULL]
├── deleted_at / deleted_by / delete_reason / delete_snapshot（软删除）
└── created_at / updated_at

lifecycle_event (生命周期事件)
├── id PK
├── asset_id → asset
├── event_type [stock_in|assign|return|transfer|maintenance_start|maintenance_end|scrap|label_print]
├── operator_id → user (谁操作)
├── target_user_id → user (旧字段，兼容保留)
├── target_employee_id → employee (资产分配/转移目标)
├── from_location / to_location
└── created_at

maintenance_record (维修记录)
├── id PK
├── asset_id → asset
├── reported_by → user
├── description / status / cost / repair_notes / resolved_at
└── created_at

asset_application (资产申请)
├── id PK
├── applicant_id → user
├── asset_category / reason / status [pending|approved|rejected|fulfilled]
├── admin_id → user / admin_notes / approved_at
└── created_at

printer_consumable (墨粉槽位)
├── id PK
├── name / type [toner] / stock / threshold
├── asset_id → asset (关联打印机)
├── color / model / current_price / installed_at
└── created_at

consumable_replacement (墨粉更换历史)
├── id PK
├── consumable_id → printer_consumable
├── old_installed_at / replaced_at / usage_days / price / daily_cost
├── new_installed_at / new_price / reason / notes
└── created_at

activity_log (操作审计)
├── id PK
├── user_id / action / target_type / target_id / detail
└── created_at

app_config (系统配置 KV)
├── key PK
└── value (JSON 或纯文本)
```

### 资产状态机

```
in_stock ──assign──> assigned ──return──> in_stock
    │                  │
    │                  ├──transfer──> assigned
    │                  ├──maintenance_start──> maintenance
    │                  └──scrap──> scrapped
    │
    └──scrap──> scrapped

maintenance ──maintenance_end──> assigned | in_stock
    └──scrap──> scrapped
```

`scrapped` 是终态，不可逆。

### 软删除 / 回收站

`deleted_at IS NOT NULL` 的资产进入回收站，不是普通 status 值。在册视图（全部/在用/库存/维修中/已报废）统一过滤 `deleted_at IS NULL`。

- 软删除：非库存资产需填写原因，原状态/持有人保存在 `delete_snapshot`
- 恢复：原持有人已停用 → 自动恢复为 in_stock + 清空持有人 + 关闭进行中维修记录
- 永久删除：需 `confirm: "DELETE"`，打印机关联耗材自动解绑
- 批量操作：batch-delete、batch-restore、batch-purge

### 数据库迁移

- `SCHEMA` 常量：新装完整结构，`init_db()` 直接执行
- `upgrade_db()`：旧库幂等补齐，检测缺失表/列后 ALTER TABLE
- `init_db.py`：先 `init_db()` 再种子数据，新装不依赖 `upgrade_db()`

## 路由结构

### 页面路由（22 条）

| 路径 | 角色 | 说明 |
|------|------|------|
| `/` | 自动跳转 | 按 role 跳转 dashboard 或 my/assets |
| `/login` | 公开 | 登录页 |
| `/dashboard` | admin | 仪表盘 |
| `/assets`, `/assets/new`, `/assets/<id>`, `/assets/<id>/edit`, `/assets/<id>/label` | admin | 资产台账 CRUD |
| `/applications` | admin | 申请审核 |
| `/maintenance` | admin | 维修总览 |
| `/consumables` | admin | 墨粉管理 |
| `/employees` | admin | 员工管理 |
| `/users` | admin | 用户管理 |
| `/settings` | admin | 系统设置 |
| `/activity` | admin | 操作记录 |
| `/scan`, `/scan/<id>` | 公开 | 扫码页面 |
| `/my/assets`, `/my/assets/<id>` | employee | 员工资产（保留的自助页） |
| `/my/applications`, `/my/applications/new` | employee | 员工申请（保留的自助页） |

### API 路由（92 条）

按功能分组：

- **认证**：login, logout, me
- **资产 CRUD**：列表(分页/搜索/筛选)、创建、详情、更新、删除
- **软删除/回收站**：batch-delete, restore, batch-restore, purge, batch-purge
- **生命周期**：assign, return, transfer, maintenance_start, maintenance_end, scrap, events
- **维修**：列表、资产维修记录
- **申请**：列表、创建、审批(approve/reject)
- **员工自助**：my/assets, my/applications（保留）
- **员工管理**：列表、创建、更新、删除、批量导入
- **用户管理**：列表、创建、详情、更新、删除、重置密码
- **耗材**：CRUD、库存调整、更换、更换历史、打印机耗材聚合、成本汇总
- **标签**：QR 生成、批量标签
- **分类**：分类元数据
- **设置**：标签字段、QR 地址、Logo 上传
- **导出/导入**：CSV 导出、CSV 批量导入
- **操作记录**：活动日志、活动日志导出
- **公开**：扫码资产信息

## 认证流程

```
POST /api/login {employee_id, password}
  → 查 user 表 (employee_id 匹配)
  → 校验密码 (支持明文兼容 + Werkzeug 哈希)
  → session["user_id"] = user.id
  → 后续请求通过 current_user() 读取 session
```

- `current_user()` — 返回当前登录用户 dict 或 None
- `require_role("admin")` — 要求指定角色，不满足返回 None
- 密码迁移：`upgrade_db()` 自动将明文密码转为哈希

### 资产 API 鉴权

| 接口 | 未登录 | admin | employee |
|------|--------|-------|----------|
| `GET /api/assets` | 403 | 200（全部，含回收站） | 403 |
| `GET /api/assets/<id>` | 401 | 200（全部） | 仅自己持有且未删除 |
| `GET /api/assets/<id>/events` | 401 | 同上 | 同上 |
| `GET /api/assets/<id>/maintenance` | 401 | 同上 | 同上 |
| `GET /api/maintenance` | 403 | 200（排除已删除） | 403 |
| `POST .../assign`、`POST .../transfer` | 403 | 200（拒绝停用员工） | 403 |

`_get_visible_asset(conn, asset_id, user)` 统一处理资产可见性校验。

## 前端架构

### 管理端 App Shell (base.html)

```
.app-container
├── aside.app-sidebar (200px, 可折叠)
├── .app-main-wrapper
│   ├── header.main-header (搜索 + 用户操作)
│   └── main.main-content
└── .detail-drawer (右侧抽屉)
```

### 员工端

`.simple-shell` 轻量壳，无侧边栏。

### 关键共享函数

```javascript
apiFetch(url, options)  // 统一 fetch，自动 JSON + 错误弹窗
```

### 标签打印

- 物理尺寸：60mm × 40mm 亚银纸
- CSS：`@page { size: 60mm 40mm; margin: 0 }`
- 布局：Logo(11mm) + 字段区 + 数字编号(7mm) + QR(20mm)
- 打印态：57.6×37.6mm + 1.1mm 安全边距
- 单标签 (`label.html`) 和批量标签 (`assets.html`) 保持同步
