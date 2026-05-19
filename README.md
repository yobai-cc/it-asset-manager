# IT 资产管理系统 MVP

轻量级 IT 固定资产管理追踪系统，面向 IT 管理员和普通员工。

## 功能概览

- **资产管理**：资产台帐（编号、类型、品牌、型号、序列号、状态、归属人/部门、位置）
- **生命周期追踪**：入库 → 分配/领用 → 归还 → 转移 → 维修 → 报废，完整事件时间线
- **维修记录**：故障描述、维修状态、费用、维修备注
- **员工自助**：移动端友好的资产查看、申请提交
- **标签打印**：带二维码的资产标签，支持浏览器直接打印和批量打印
- **搜索筛选**：按类别、状态、关键词搜索资产
- **两类角色**：管理员（完整 CRUD + 生命周期操作）和员工（自助查看 + 申请）

## 技术栈

- **后端**：Python Flask + SQLite
- **前端**：响应式 HTML + CSS + 原生 JavaScript
- **二维码**：Python `qrcode` 库
- **测试**：pytest

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据库并填充演示数据
python3 init_db.py

# 3. 启动服务
python3 server.py
```

浏览器访问 http://localhost:5000

## 演示账号

| 角色 | 工号 | 密码 | 说明 |
|------|------|------|------|
| 管理员 | `admin` | `admin123` | 完整管理权限 |
| 员工 | `emp001` | `emp001` | 张三 (研发部) |
| 员工 | `emp002` | `emp002` | 李四 (市场部) |
| 员工 | `emp003` | `emp003` | 王五 (财务部) |

## 运行测试

```bash
python3 -m pytest tests/ -v
```

## 页面说明

### 管理员页面
| 页面 | 路由 | 说明 |
|------|------|------|
| 仪表盘 | `/dashboard` | 统计卡片 + 分类分布 + 最近事件 |
| 资产列表 | `/assets` | 搜索、筛选、分页、批量打印标签 |
| 新增资产 | `/assets/new` | 表单创建，自动生成标签号 |
| 资产详情 | `/assets/:id` | 基本信息 + 生命周期时间线 + 维修记录 + 操作按钮 |
| 编辑资产 | `/assets/:id/edit` | 编辑资产信息 |
| 标签打印 | `/assets/:id/label` | 带二维码的打印标签页 |
| 申请审核 | `/applications` | 查看/批准/驳回员工申请 |
| 维修总览 | `/maintenance` | 维修记录列表 |

### 员工自助页面（移动端响应式）
| 页面 | 路由 | 说明 |
|------|------|------|
| 我的资产 | `/my/assets` | 名下资产卡片列表 |
| 资产详情 | `/my/assets/:id` | 只读详情 + 时间线 |
| 我的申请 | `/my/applications` | 历史申请状态 |
| 提交申请 | `/my/applications/new` | 新建资产申请 |

## 标签打印说明

1. 在资产详情或资产列表点击「标签」按钮
2. 打开标签预览页面，包含资产标签号、名称和二维码
3. 点击「打印标签」按钮（或 Ctrl+P）直接打印
4. 标签尺寸适配 60mm × 40mm 标签贴纸
5. 支持批量打印：在资产列表勾选多项 → 点击「批量打印标签」
6. 二维码扫描后打开资产详情页

## 项目结构

```
it-asset-manager/
├── server.py              # Flask 应用（所有路由和 API）
├── models.py              # 数据模型和数据库操作
├── init_db.py             # 数据库初始化 + 种子数据
├── requirements.txt       # Python 依赖
├── tests/
│   └── test_api.py        # 自动化测试（47 个用例）
├── templates/
│   ├── base.html          # 公共布局
│   ├── login.html         # 登录页
│   ├── admin/             # 管理员页面
│   │   ├── dashboard.html
│   │   ├── assets.html
│   │   ├── asset_detail.html
│   │   ├── asset_form.html
│   │   ├── label.html
│   │   ├── applications.html
│   │   └── maintenance.html
│   └── employee/          # 员工自助页面
│       ├── my_assets.html
│       ├── asset_detail.html
│       ├── applications.html
│       └── application_form.html
├── static/
│   └── style.css          # 响应式样式 + 打印样式
└── IT_ASSET_MVP_SPEC.md   # 完整实现规格文档
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
- `PUT /api/applications/:id/approve` — 批准
- `PUT /api/applications/:id/reject` — 驳回

### 员工自助
- `GET /api/my/assets` — 名下资产
- `GET /api/my/applications` — 我的申请
- `POST /api/my/applications` — 提交申请

### 标签
- `GET /api/assets/:id/qr` — 二维码 PNG 图片
- `POST /api/batch-labels` — 批量标签数据

### 统计
- `GET /api/stats` — 仪表盘统计数据

## 已知限制

- MVP 认证方案为 session + 简单密码，生产环境需替换为 SSO/LDAP
- 无审批流（仅单级审批）
- 无采购/合同管理
- 无资产自动发现/网络扫描
- 无国际化（中文界面）
