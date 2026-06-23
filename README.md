# IT 资产管理系统

轻量级 IT 固定资产管理追踪系统，面向 IT 管理员和普通员工。

**Python Flask + SQLite + 原生 JS/CSS** — 无前端框架，无构建步骤，开箱即用。

> **当前版本：v1.4** · [下载 tar.gz](https://github.com/yobai-cc/it-asset-manager/releases/download/v1.4/it-asset-manager-v1.4.tar.gz) · [查看全部 Release](https://github.com/yobai-cc/it-asset-manager/releases)

## 功能概览

- **资产全生命周期**：入库 → 分配 → 归还 → 转移 → 维修 → 报废，完整事件时间线
- **回收站**：软删除/恢复/永久删除，恢复时自动处理持有人停用和维修记录
- **标签打印**：60×40mm QR 资产标签，适配热转印打印机，支持 Logo、可配置字段、批量打印
- **移动端扫码**：摄像头扫码查询资产信息，公开页只展示最小必要字段
- **员工花名册**：员工信息管理，支持 CSV 批量导入
- **员工自助**：移动端友好的资产查看、申请提交
- **打印机墨粉管理**：以打印机为中心的墨粉 slot 管理，报废/删除打印机自动解绑耗材，库存告警、更替历史、日均成本
- **CSV 导入导出**：兼容 Excel/BarTender，导入支持行级错误返回
- **操作记录**：所有关键变更自动写入日志
- **用户管理**：角色权限、密码哈希存储、删除保护
- **API 鉴权**：admin-only 资产列表，员工限看自己持有资产，分配/转移拒绝停用员工

## 资产编码规则

资产标签号（asset_tag）是每项资产的唯一标识，格式为 **`{分类缩写}-{年份}-{序号}`**，由系统在创建资产时自动生成。

### 格式定义

```
PC-2026-0001
│   │    └── 4 位序号（同分类同年递增，0001–9999）
│   └────── 入库年份
└────────── 分类缩写（2–3 位大写字母）
```

### 分类缩写

| 分类 | 缩写 | 示例 |
|------|------|------|
| 电脑 | `PC` | PC-2026-0001 |
| 显示器 | `MON` | MON-2026-0001 |
| 手机 | `PH` | PH-2026-0001 |
| 平板 | `TAB` | TAB-2026-0001 |
| 打印机 | `PRN` | PRN-2026-0001 |
| 服务器 | `SRV` | SRV-2026-0001 |
| 网络设备 | `NET` | NET-2026-0001 |
| 防火墙 | `FW` | FW-2026-0001 |
| 交换机 | `SW` | SW-2026-0001 |

### 编码原则

- **一次生成，终身不变**：编码在资产入库时自动生成，后续分配、转移、维修、报废等所有操作均不改变编码
- **不复用**：即使资产被软删除或永久删除，其编号不会被重新分配给新资产，避免历史记录混淆
- **年份归档**：序号按年份独立计数，同年同分类从 0001 起；跨年后重新从 0001 开始
- **人类可读**：看到编码即可判断资产类型和入库年份，便于线下盘点和口头沟通
- **QR 关联**：标签上的二维码内容为 `{base_url}/scan/{id}`，扫码直接跳转资产详情

### 示例

```
PC-2026-0001    → 2026 年入库的第 1 台电脑
PRN-2026-0003   → 2026 年入库的第 3 台打印机
FW-2025-0002    → 2025 年入库的第 2 台防火墙（跨年序号独立）
```

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
| 测试 | pytest（306 测试用例） |

## 页面一览

### 管理员

| 页面 | 路由 | 说明 |
|------|------|------|
| 仪表盘 | `/dashboard` | 统计卡片、分类分布、保修提醒、最近事件 |
| 资产台账 | `/assets` | 搜索、筛选、分页、详情抽屉、批量标签、CSV 导出/导入、回收站 |
| 资产详情 | `/assets/:id` | 基本信息、生命周期时间线、维修记录、恢复/永久删除 |
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
├── android/               # Android 客户端规划与 API 合约（P0 文档）
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
