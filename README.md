# IT 资产管理系统

轻量级 IT 固定资产管理追踪系统，面向 IT 管理员和普通员工。

**Python Flask + SQLite + 原生 JS/CSS** — 无前端框架，无构建步骤，开箱即用。

## 功能概览

- **资产全生命周期**：入库 → 分配 → 归还 → 转移 → 维修 → 报废，完整事件时间线
- **标签打印**：60×40mm QR 资产标签，适配热转印打印机，支持 Logo、可配置字段、批量打印
- **移动端扫码**：摄像头扫码查询资产信息，公开页只展示最小必要字段
- **员工花名册**：员工信息管理，支持 CSV 批量导入
- **员工自助**：移动端友好的资产查看、申请提交
- **打印机墨粉管理**：以打印机为中心的墨粉 slot 管理，库存告警、更替历史、日均成本
- **CSV 导入导出**：兼容 Excel/BarTender，导入支持行级错误返回
- **操作记录**：所有关键变更自动写入日志
- **用户管理**：角色权限、密码哈希存储、删除保护

## 快速开始

### 一键部署（生产环境推荐）

```bash
# 下载解压后执行
sudo ./deploy.sh

# 自定义端口
sudo ./deploy.sh --port 9090

# 从 GitHub 克隆部署
sudo ./deploy.sh --clone https://github.com/yobai-cc/it-asset-manager.git
```

脚本自动完成：环境检查 → venv + 依赖 → 数据库初始化 → systemd 服务 → 健康检查。

### 开发模式

```bash
pip install -r requirements.txt    # 安装依赖
python3 init_db.py                  # 初始化 DB + 演示数据
python3 server.py                   # 启动 http://0.0.0.0:5000
```

## 演示账号

| 角色 | 工号 | 密码 |
|------|------|------|
| 管理员 | `admin` | `admin123` |
| 员工 | `emp001` | `emp001` |
| 员工 | `emp002` | `emp002` |
| 员工 | `emp003` | `emp003` |

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python Flask 3.1 + SQLite（原生 SQL） |
| 前端 | Jinja2 + 原生 HTML/CSS/JS |
| 二维码 | Python `qrcode` + Pillow |
| 生产部署 | Gunicorn + systemd |
| 测试 | pytest（202+ 测试用例） |

## 页面一览

### 管理员

| 页面 | 路由 | 说明 |
|------|------|------|
| 仪表盘 | `/dashboard` | 统计卡片、分类分布、保修提醒、最近事件 |
| 资产台账 | `/assets` | 搜索、筛选、分页、详情抽屉、批量标签、CSV 导出/导入 |
| 资产详情 | `/assets/:id` | 基本信息、生命周期时间线、维修记录 |
| 标签打印 | `/assets/:id/label` | 60×40mm QR 标签 |
| 申请审核 | `/applications` | 批准、驳回员工申请 |
| 维修总览 | `/maintenance` | 维修记录列表 |
| 墨粉管理 | `/consumables` | 打印机卡片、墨粉 slot、库存告警、更替历史 |
| 员工管理 | `/employees` | 员工花名册、CSV 导入 |
| 用户管理 | `/users` | 创建/编辑/密码重置/删除保护 |
| 系统设置 | `/settings` | Logo、标签字段、QR 地址 |
| 操作记录 | `/activity` | 操作日志查询与导出 |

### 员工自助（移动端响应式）

| 页面 | 路由 |
|------|------|
| 我的资产 | `/my/assets` |
| 资产详情 | `/my/assets/:id` |
| 我的申请 | `/my/applications` |
| 提交申请 | `/my/applications/new` |

### 公开页面

| 页面 | 路由 | 说明 |
|------|------|------|
| 摄像头扫码 | `/scan` | html5-qrcode 后置摄像头扫码 |
| 扫码落地页 | `/scan/:id` | 匿名公开资产摘要 |
| 登录 | `/login` | 工号 + 密码 |

## 项目结构

```
it-asset-manager/
├── server.py              # Flask 应用（页面路由 + API）
├── models.py              # 数据模型、常量、Schema
├── init_db.py             # 数据库初始化 + 演示数据
├── deploy.sh              # 一键部署脚本
├── requirements.txt       # Python 依赖
├── gunicorn.conf.py       # Gunicorn 配置
├── static/
│   ├── style.css          # 全局样式（Design Token 体系）
│   └── uploads/           # Logo 上传目录
├── templates/
│   ├── base.html          # 管理端 App Shell
│   ├── admin/             # 管理员页面
│   └── employee/          # 员工页面
├── contrib/
│   └── it-asset-manager.service  # systemd 模板
└── tests/
    └── test_api.py        # 自动化测试
```

## 生产部署

详见 [DEPLOY.md](DEPLOY.md)，或直接使用一键部署脚本：

```bash
sudo ./deploy.sh --help
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | Flask 会话密钥 | 自动生成并保存到 `.secret_key` |
| `DB_PATH` | SQLite 数据库路径 | `it_asset.db` |
| `FLASK_DEBUG` | 开发模式 | 关闭 |

## 运行测试

```bash
python -m pytest tests/ -q
```

## 文档

| 文档 | 内容 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | 完整开发文档（路由、数据库、前端约定） |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构设计 |
| [DEPLOY.md](DEPLOY.md) | 部署指南 |
| [CONVENTIONS.md](CONVENTIONS.md) | 编码规范 |
| [CHANGELOG.md](CHANGELOG.md) | 改动历史 |

## License

MIT
