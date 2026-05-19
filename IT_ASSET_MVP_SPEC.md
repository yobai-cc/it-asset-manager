# IT 资产管理 MVP — 实现规格

## 1. 项目概况与角色

| 角色 | 能力 |
|------|------|
| **IT 管理员 (admin)** | 资产 CRUD、生命周期管理、审批申请、维修跟踪、标签打印 |
| **普通员工 (employee)** | 查看名下资产、提交申领/归还申请、查看个人信息 |

认证 MVP 阶段可简化为本地用户 + 简单密码或纯 localStorage 选择角色（生产才上 SSO）。

---

## 2. 数据模型

### 2.1 资产 (Asset)

```
asset
├── id                  INTEGER PK AUTOINCREMENT
├── asset_tag           TEXT UNIQUE NOT NULL    -- 资产标签号, e.g. PC-2026-0001
├── name                TEXT NOT NULL           -- 资产名称/型号描述
├── category            TEXT NOT NULL           -- computer|monitor|phone|tablet|printer|server|network|firewall|switch
├── brand               TEXT
├── model               TEXT
├── serial_number       TEXT UNIQUE
├── status              TEXT NOT NULL DEFAULT 'in_stock'
│                       -- in_stock | assigned | maintenance | scrapped
├── current_holder_id   INTEGER REFERENCES user(id)   -- NULL 当 in_stock
├── location            TEXT           -- 存放位置(仓库/机房/工位号)
├── purchase_date       DATE
├── purchase_price      REAL
├── notes               TEXT
├── created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
├── updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
```

### 2.2 用户 (User)

```
user
├── id                  INTEGER PK AUTOINCREMENT
├── employee_id         TEXT UNIQUE NOT NULL    -- 工号
├── name                TEXT NOT NULL
├── department          TEXT                    -- 部门
├── phone               TEXT
├── email               TEXT
├── role                TEXT NOT NULL DEFAULT 'employee'
│                       -- admin | employee
├── password_hash       TEXT                    -- MVP 可暂缺, 用 localStorage 兜底
├── created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
```

### 2.3 生命周期事件 (LifecycleEvent)

```
lifecycle_event
├── id                  INTEGER PK AUTOINCREMENT
├── asset_id            INTEGER NOT NULL REFERENCES asset(id)
├── event_type          TEXT NOT NULL
│                       -- stock_in | assign | return | transfer
│                       -- maintenance_start | maintenance_end
│                       -- scrap | label_print
├── operator_id         INTEGER NOT NULL REFERENCES user(id)   -- 谁操作的
├── target_user_id      INTEGER REFERENCES user(id)            -- 领用人/接收人
├── from_location       TEXT
├── to_location         TEXT
├── notes               TEXT
├── created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
```

**用途**：所有状态变化落一条事件，前端直接渲染「生命周期时间线」。

### 2.4 维修记录 (MaintenanceRecord)

```
maintenance_record
├── id                  INTEGER PK AUTOINCREMENT
├── asset_id            INTEGER NOT NULL REFERENCES asset(id)
├── reported_by         INTEGER NOT NULL REFERENCES user(id)   -- 报修人
├── description         TEXT NOT NULL                          -- 故障描述
├── status              TEXT NOT NULL DEFAULT 'pending'
│                       -- pending | in_progress | resolved
├── cost                REAL                                   -- 维修费用
├── repair_notes        TEXT                                   -- 维修备注
├── resolved_at         DATETIME
├── created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
```

### 2.5 资产申请 (AssetApplication)

```
asset_application
├── id                  INTEGER PK AUTOINCREMENT
├── applicant_id        INTEGER NOT NULL REFERENCES user(id)
├── asset_category      TEXT                       -- 申请的资产类别
├── reason              TEXT NOT NULL              -- 申请理由
├── status              TEXT NOT NULL DEFAULT 'pending'
│                       -- pending | approved | rejected | fulfilled
├── admin_id            INTEGER REFERENCES user(id)           -- 审批人
├── admin_notes         TEXT                                  -- 审批备注
├── approved_at         DATETIME
├── created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
```

---

## 3. 业务状态与生命周期

### 状态机

```
  ┌──────────┐
  │ in_stock │◄────────────┐
  └────┬─────┘             │
       │ assign            │ return
       ▼                   │
  ┌──────────┐     ┌───────────┐
  │ assigned │────►│ in_stock  │
  └────┬─────┘     └───────────┘
       │ transfer
       ▼
  ┌──────────┐
  │ assigned │  (持有人变更)
  └────┬─────┘
       │ maintenance_start
       ▼
  ┌────────────┐
  │maintenance │──maintenance_end──► assigned OR in_stock
  └─────┬──────┘
        │ scrap
        ▼
   ┌─────────┐
   │scrapped │  (终态)
   └─────────┘
```

**允许的状态转换**：
| 当前状态 | 可进行事件 |
|----------|-----------|
| in_stock | stock_in → 补充数量无意义(in_stock), assign, scrap |
| assigned | return, transfer, maintenance_start, scrap |
| maintenance | maintenance_end(resolved → assigned 或 in_stock), scrap |
| scrapped | 无（终态，仅可编辑备注） |

### 事件→状态映射

| 事件 | 触发后 asset.status |
|------|-------------------|
| stock_in | in_stock |
| assign | assigned |
| return | in_stock |
| transfer | assigned (持有人变更) |
| maintenance_start | maintenance |
| maintenance_end | assigned (如果原持有人还在) 或 in_stock |
| scrap | scrapped |
| label_print | 状态不变（仅记录） |

---

## 4. 页面清单

### 4.1 管理员页面

| # | 页面 | 路由 | 说明 |
|---|------|------|------|
| P1 | 仪表盘 | `/` | 卡片统计：总资产 / 在用 / 库存 / 维修中 / 报废；按分类分布图；最新事件 |
| P2 | 资产列表 | `/assets` | 表格：标签号+名称+类别+状态+持有人+位置；搜索/筛选(category/status)；分页；批量操作入口 |
| P3 | 资产详情 | `/assets/:id` | 基本信息编辑区 + 生命周期时间线 + 维修记录 + 操作按钮区 |
| P4 | 新增资产 | `/assets/new` | 表单：类别/品牌/型号/序列号/购入日期/价格/位置/备注；自动生成 asset_tag |
| P5 | 标签打印 | `/assets/:id/label` | 显示标签预览：asset_tag + name + QR码；CSS @media print 直接打印 |
| P6 | 申请审核 | `/applications` | 待审批列表；点击可批准/驳回（带备注） |
| P7 | 维修总览 | `/maintenance` | 维修中/待处理的 asset 一览 |

### 4.2 员工自助页面

| # | 页面 | 路由 | 说明 |
|---|------|------|------|
| P8 | 我的资产 | `/my/assets` | 当前名下资产列表，支持搜索 |
| P9 | 资产详情 | `/my/assets/:id` | 只读详情 + 时间线 |
| P10 | 我的申请 | `/my/applications` | 历史申请及状态 |
| P11 | 提交申请 | `/my/applications/new` | 选择类别 + 填写理由 |

### 4.3 移动端

- 所有员工页面 (P8-P11) 使用响应式 CSS，手机端也能友好操作
- 申请列表和提交是核心移动场景
- 管理员页面的资产查看 (`/assets`) 也做响应式适配，可使用

---

## 5. API/路由设计

采用 RESTful JSON API，前缀 `/api/`。前端静态页面通过 fetch 调用。

### 5.1 认证 (MVP 简化)

```
POST   /api/login                    ← body: { employee_id, password } → token
POST   /api/logout
GET    /api/me                       ← 当前用户信息
```

MVP 不强制执行 JWT 鉴权——可直接用 session 或 localStorage 存用户角色。

### 5.2 资产

```
GET    /api/assets                   ← 列表(query: category, status, search, page, limit)
POST   /api/assets                   ← 新增
GET    /api/assets/:id               ← 详情
PUT    /api/assets/:id               ← 编辑
DELETE /api/assets/:id               ← 删除(仅 in_stock 可删)
```

### 5.3 生命周期操作

```
POST   /api/assets/:id/assign        ← { target_user_id, notes }
POST   /api/assets/:id/return        ← { notes }
POST   /api/assets/:id/transfer      ← { target_user_id, notes }
POST   /api/assets/:id/maintenance   ← { description }
POST   /api/assets/:id/maintenance/:record_id/resolve  ← { cost, repair_notes, return_to_stock: bool }
POST   /api/assets/:id/scrap         ← { notes }
```

### 5.4 生命周期事件查询

```
GET    /api/assets/:id/events        ← 该资产的全部生命周期事件(时间线)
```

### 5.5 维修记录

```
GET    /api/maintenance              ← 全部维修记录列表(query: status)
GET    /api/assets/:id/maintenance   ← 指定资产的维修记录
```

### 5.6 资产申请

```
GET    /api/applications             ← 全部申请(admin, query: status)
POST   /api/applications             ← 提交申请
PUT    /api/applications/:id/approve ← { admin_notes }
PUT    /api/applications/:id/reject  ← { admin_notes }
```

### 5.7 员工自助

```
GET    /api/my/assets                ← 当前用户名下资产
GET    /api/my/applications
POST   /api/my/applications          ← { asset_category, reason }
```

### 5.8 标签相关

```
GET    /api/assets/:id/label         ← 返回标签页面(HTML, @media print)
GET    /api/assets/:id/qr            ← 返回二维码图片(PNG/raw image)
```

### 5.9 仪表盘统计

```
GET    /api/stats                    ← { total, in_stock, assigned, maintenance, scrapped, by_category }
```

---

## 6. 标签打印功能规格

**必要功能（验收硬性条件）**：

1. 每个资产创建后自动生成唯一 `asset_tag`（格式建议：`{分类缩写}-{年份}-{4位序号}`，如 `PC-2026-0001`）
2. 标签页包含：资产名称、asset_tag、二维码（编码为资产详情页 URL 或 asset_id）
3. 浏览器端生成二维码（qrcode.js 或 Python qrcode 库），CSS @media print 适配标准标签贴纸尺寸（建议 60mm×40mm 或 1.5"×1"）
4. 支持批量打印（选择多条后统一生成标签页）

**二维码内容建议**：
```
https://{host}/assets/{asset_id}
```
扫描后直接打开资产详情页（管理员）或只读详情（员工）。

---

## 7. 技术实现建议

### MVP 推荐技术栈

| 层 | 推荐 | 理由 |
|----|------|------|
| **后端** | Python Flask (轻量, 单文件/少文件) | 用户已有 UY-NB-Meter 的 Flask 经验, server.py 单文件模式可复用 |
| 备选 | Node.js + Express | 前后端统一 JS 生态 |
| **数据库** | SQLite | 零配置, 单文件 DB, MVP 无需 PostgreSQL |
| **前端** | HTML + CSS + JS (Responsive) + Vite | 无构建复杂度, 移动响应式用 CSS media query |
| 备选 | Vue 3 CDN 模式 | 组件化但无需 webpack |
| **二维码** | [`qrcode` Python库](https://pypi.org/project/qrcode/) 或 qrcode.js | 两者都成熟, 选哪个取决于生成端 |
| **打印** | CSS `@media print` + `page-break` | 零依赖, 直接浏览器打印 |

### 项目结构

```
it-asset-manager/
├── server.py                 # Flask 应用（含所有路由）
├── models.py                 # SQLAlchemy ORM 模型（或 raw SQL）
├── templates/
│   ├── base.html             # 公共布局
│   ├── admin/                # 管理页面
│   │   ├── dashboard.html
│   │   ├── assets.html
│   │   ├── asset_detail.html
│   │   ├── asset_form.html
│   │   ├── label.html
│   │   ├── applications.html
│   │   └── maintenance.html
│   └── employee/
│       ├── my_assets.html
│       ├── asset_detail.html
│       └── applications.html
├── static/
│   ├── style.css             # 响应式 + 打印样式
│   └── qrcode.min.js         # 前端二维码生成(如采用前端方案)
├── init_db.py                # DB 初始化 + seed 数据
└── requirements.txt
```

### 种子 (Seed) 数据

`init_db.py` 应创建：
- 1 个 admin 用户 (admin / admin123)
- 2-3 个员工用户 (员工A/员工B/员工C)
- 5-10 条演示资产（各状态分布）
- 2-3 条生命周期事件
- 1 条演示申请

---

## 8. 验收标准

| # | 检查项 | 验证方式 |
|---|--------|---------|
| AC1 | admin 登录后可看到仪表盘统计 | 页面加载 `/` |
| AC2 | 资产列表可搜索、筛选、分页 | 输入搜索词, 切换 category/status |
| AC3 | 新增资产 → 自动生成 asset_tag → 资产出现在列表 | 提交表单后验证新条目 |
| AC4 | 点击资产 → 详情页含时间线 | 页面显示所有生命周期事件 |
| AC5 | 领用操作 → 状态变 assigned → 持有人更新 | POST assign → GET asset 验证 |
| AC6 | 归还操作 → 状态变 in_stock → 持有人清空 | POST return → 验证 |
| AC7 | 转移操作 → 持有人变更 (状态仍 assigned) | POST transfer → 验证 |
| AC8 | 维修操作 → 状态变 maintenance → 维修记录生成 | POST maintenance → 验证 |
| AC9 | 维修完成 → 可选归还库存或回到原持有人 | resolve → 验证 |
| AC10 | 报废 → 状态变 scrapped (终态) | POST scrap → 验证 |
| AC11 | 标签页显示 asset_tag + name + QR码 | 打开 `/assets/:id/label` 预览 |
| AC12 | 标签可浏览器打印（CSS @media print） | 按 Ctrl+P, 预览无导航元素 |
| AC13 | 员工资产申请 → 提交 → admin 看到 → 批准/驳回 | 完整流程端到端 |
| AC14 | 员工查看名下资产（响应式） | 手机浏览器缩小/模拟器测试 |
| AC15 | git 项目完整可运行: `pip install -r requirements.txt && python init_db.py && python server.py` | 从头克隆测试 |

---

## 9. 非目标（明确不做）

- 大型 CMDB / 自动发现
- 复杂审批流（多级审批 / 自定义审批链）
- 采购 / 合同 / 供应商管理
- SSO / LDAP 集成（MVP 阶段先本地用户）
- 资产自动发现 / 网络扫描
- 实时推送 / WebSocket
- 详细权限体系（仅 admin / employee 两级）
- 国际化
