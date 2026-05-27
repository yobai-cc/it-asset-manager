# 资产详情页 UI 设计需求稿

## 页面概述

IT 资产管理系统的资产详情页（`/assets/<id>`），面向 IT 管理员，用于查看单台 IT 资产的完整信息、执行生命周期操作（分配/归还/转移/送修/报废）、查看历史时间线和维修记录。

**技术约束**：纯 HTML + CSS + Vanilla JS，无前端框架，无构建步骤。所有内容通过 JS 调用 `/api/assets/<id>` 动态渲染。

---

## 设计令牌（必须使用）

```css
--color-primary: #2563eb;
--color-primary-dark: #1d4ed8;
--color-success: #10b981;
--color-warning: #f59e0b;
--color-danger: #ef4444;
--color-info: #3b82f6;
--color-bg-main: #f8fafc;
--color-bg-card: #ffffff;
--color-text-main: #0f172a;
--color-text-muted: #64748b;
--color-border: #e2e8f0;
--color-border-light: #f1f5f9;
--space-1: 8px;  --space-2: 16px;  --space-3: 24px;  --space-4: 32px;
--radius-soft: 4px;  --radius-medium: 8px;  --radius-strong: 16px;
--shadow-soft: 0 2px 8px rgba(15,23,42,0.06);
```

**状态徽章色**：
- `in_stock`（库存）：蓝底 `rgba(59,130,246,0.12)` + 蓝字 `#3b82f6`
- `assigned`（在用）：绿底 `rgba(16,185,129,0.12)` + 绿字 `#10b981`
- `maintenance`（维修中）：橙底 `rgba(245,158,11,0.12)` + 橙字 `#f59e0b`
- `scrapped`（已报废）：红底 `rgba(239,68,68,0.12)` + 红字 `#ef4444`

---

## 页面布局（整体结构）

页面在管理端 App Shell 中渲染（左侧 200px 侧边栏 + 顶部 70px header）。主内容区为纵向滚动布局，建议最大宽度 960px 居中。

```
┌─────────────────────────────────────────────┐
│ ← 返回资产列表                               │  ← 面包屑/返回链接
├─────────────────────────────────────────────┤
│ 🖥️ ThinkPad T14s Gen 4    [在用]           │  ← 资产头部卡片
│ PC-2026-0001 · 电脑 · Lenovo T14s Gen 4     │
│                                             │
│ [分配] [归还] [转移] [送修] [报废] [打印标签] [编辑] │  ← 操作栏
├─────────────────────────────────────────────┤
│ ┌──────────────────┐ ┌──────────────────┐   │
│ │   基本信息        │ │  持有人 & 位置    │   │  ← 双栏信息卡
│ │   类别/品牌/型号   │ │  当前持有人      │   │
│ │   序列号/价格     │ │  位置/部门       │   │
│ │   购入/保修       │ │                  │   │
│ └──────────────────┘ └──────────────────┘   │
├─────────────────────────────────────────────┤
│ ┌──────────────────────────────────────┐    │
│ │  生命周期时间线                        │    │  ← 时间线卡片
│ │  ● 2026-05-26 管理员 分配给张三       │    │
│ │  ● 2026-05-26 管理员 入库             │    │
│ └──────────────────────────────────────┘    │
├─────────────────────────────────────────────┤
│ ┌──────────────────────────────────────┐    │
│ │  维修记录                             │    │  ← 维修记录卡
│ │  (表格 or 空状态)                     │    │
│ └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

---

## 各区块详细设计

### 1. 顶部返回导航

- 左上角一个文字链接 "← 返回资产列表"，链接到 `/assets`
- 颜色 `--color-text-muted`，hover 时 `--color-primary`
- 不需要完整的面包屑，一个返回链接即可

### 2. 资产头部卡片

**容器**：白色卡片背景（`--color-bg-card`），`border-radius: 16px`，`box-shadow`，`padding: 24px`，`margin-bottom: 24px`

**内容**：
- 第一行：分类图标 + 资产名称（大标题 24px 粗体） + 状态徽章（右上角）
  - 分类图标用 emoji：`computer→💻, monitor→🖥️, phone→📱, tablet→📋, printer→🖨️, server→🗄️, network→🌐, firewall→🛡️, switch🔀`
  - 状态徽章：圆角胶囊形（`border-radius: 999px`），对应状态色
- 第二行：资产标签号 · 中文分类名 · 品牌型号（小字 `--color-text-muted`，14px）
- 第三行（如有）：备注（灰色斜体，14px）

**示例数据**：
```
💻 ThinkPad T14s Gen 4                              [在用]
PC-2026-0001 · 电脑 · Lenovo T14s Gen 4
研发主力机
```

### 3. 操作栏

- 紧贴头部卡片下方，水平排列按钮组，`gap: 8px`，`margin-bottom: 24px`
- 按钮根据当前资产状态动态显示：
  - `in_stock`：[分配(主色)] [报废(红色)] [打印标签] [编辑]
  - `assigned`：[归还] [转移] [送修(橙色)] [报废(红色)] [打印标签] [编辑]
  - `maintenance`：[维修完成(主色)] [报废(红色)] [打印标签] [编辑]
  - `scrapped`：[打印标签] [编辑]
- 按钮样式：
  - 主操作按钮：蓝底白字（`--color-primary`），圆角 8px，`padding: 8px 16px`
  - 危险操作按钮：红底白字（`--color-danger`）
  - 普通按钮：白底灰边（`border: 1px solid --color-border`），hover 时蓝边
  - 打印标签按钮：`target="_blank"` 打开新窗口

### 4. 信息区（双栏）

**布局**：两列等宽（`grid-template-columns: 1fr 1fr`），`gap: 16px`，`margin-bottom: 24px`

**左卡 — 基本信息**：
- 卡片样式同头部（白底、圆角 16px、阴影）
- 标题"基本信息"（16px 粗体），下方分隔线
- 表格布局（两列：标签列宽 120px + 值列），无边框，行间用浅灰底边线分隔
- 字段：
  | 标签 | 值 |
  |------|-----|
  | 类别 | 💻 电脑 |
  | 品牌 | Lenovo |
  | 型号 | T14s Gen 4 |
  | 序列号 | SN-LNV-001 |
  | 购入日期 | 2026-01-15 |
  | 购入价格 | ¥6,999.00 |
  | 保修到期 | 2029-01-15（如已过期则显示红色"已过期"徽章） |

**右卡 — 持有人 & 位置**：
- 标题"持有人 & 位置"
- 字段：
  | 标签 | 值 |
  |------|-----|
  | 当前持有人 | 张三 |
  | 所属部门 | 研发部 |
  | 存放位置 | 工位A-101 |
- 若持有人为空（库存状态），显示"仓库 / 暂无持有人"（灰色）
- 位置信息下方可加一个小的地图图标或定位图标（仅装饰）

### 5. 生命周期时间线

**卡片容器**：同上卡片样式

**标题**："生命周期时间线"（16px 粗体），右侧显示事件总数

**时间线样式**：
- 纵向排列，左侧有一条 2px 宽的竖线（`--color-border`）贯穿
- 每个事件节点：
  - 左侧：一个小圆点（12px），位于竖线上
    - 默认灰色边框
    - `assign` 事件：绿色圆点
    - `maintenance_start` 事件：橙色圆点
    - `scrap` 事件：红色圆点
    - `stock_in` 事件：蓝色圆点
  - 右侧内容：
    - 第一行：事件名称（粗体 14px），如"分配"、"入库"、"归还"
    - 第二行：日期 + 操作人，灰色小字，如"2026-01-15 · 管理员"
    - 第三行（如有备注）：备注内容，灰色斜体
- 事件按时间倒序排列（最新在上）

**事件名称映射**：
```
stock_in → 入库, assign → 分配, return → 归还, transfer → 转移
maintenance_start → 送修, maintenance_end → 维修完成, scrap → 报废, label_print → 打印标签
```

**空状态**：灰色文字"暂无生命周期事件"

### 6. 维修记录

**卡片容器**：同上卡片样式

**标题**："维修记录"（16px 粗体）

**有记录时**：表格展示
| 列 | 说明 |
|----|------|
| 日期 | 创建日期 |
| 描述 | 故障描述 |
| 状态 | 待处理 / 进行中 / 已完成（对应状态色徽章） |
| 费用 | 维修费用（空时显示"-"） |
| 备注 | 维修备注 |

**空状态**：灰色文字"暂无维修记录"

---

## 操作弹窗设计

所有操作弹窗共用 `.modal` 基础样式（全屏半透明黑色遮罩 + 居中白色卡片，`border-radius: 16px`，`max-width: 480px`，`padding: 24px`）。

- 弹窗标题：18px 粗体
- 表单字段间 `gap: 16px`
- 底部操作按钮右对齐
- 点击遮罩关闭弹窗
- 危险操作（报废）的确认按钮为红色

---

## API 数据结构

`GET /api/assets/<id>` 返回的 JSON：

```json
{
  "id": 1,
  "asset_tag": "PC-2026-0001",
  "name": "ThinkPad T14s Gen 4",
  "category": "computer",
  "brand": "Lenovo",
  "model": "T14s Gen 4",
  "serial_number": "SN-LNV-001",
  "status": "assigned",
  "current_holder_id": 2,
  "holder_name": "张三",
  "holder_dept": "研发部",
  "location": "工位A-101",
  "purchase_date": "2026-01-15",
  "purchase_price": 6999.0,
  "warranty_date": "2029-01-15",
  "notes": "研发主力机",
  "printer_type": null,
  "created_at": "2026-05-26 05:10:39",
  "updated_at": "2026-05-26 05:10:39",
  "events": [
    {
      "id": 1, "event_type": "stock_in",
      "operator_id": 1, "operator_name": "管理员",
      "target_user_id": null,
      "from_location": null, "to_location": "仓库",
      "notes": "入库", "created_at": "2026-05-26 05:10:39"
    },
    {
      "id": 2, "event_type": "assign",
      "operator_id": 1, "operator_name": "管理员",
      "target_user_id": 2,
      "from_location": null, "to_location": "工位A-101",
      "notes": "分配给张三", "created_at": "2026-05-26 05:10:39"
    }
  ],
  "maintenance_records": []
}
```

---

## JS 中的分类/状态映射

```javascript
const catLabels = {computer:'电脑',monitor:'显示器',phone:'手机',tablet:'平板',printer:'打印机',server:'服务器',network:'网络设备',firewall:'防火墙',switch:'交换机'};
const catIcons = {computer:'💻',monitor:'🖥️',phone:'📱',tablet:'📋',printer:'🖨️',server:'🗄️',network:'🌐',firewall:'🛡️',switch:'🔀'};
const statusLabels = {in_stock:'库存',assigned:'在用',maintenance:'维修中',scrapped:'已报废'};
const eventNames = {stock_in:'入库',assign:'分配',return:'归还',transfer:'转移',maintenance_start:'送修',maintenance_end:'维修完成',scrap:'报废',label_print:'打印标签'};
```

---

## 交付要求

1. **单文件 HTML**：将 CSS 和 JS 写在同一个 `.html` 文件中，可直接在浏览器中打开预览
2. **使用模拟数据**：用上方提供的 API JSON 数据硬编码在 JS 中，不需要真实 API 调用
3. **不需要实现弹窗交互**：只做页面主内容的静态/动态渲染，操作按钮只做视觉展示不需要绑定事件
4. **响应式**：在 960px+ 宽度下双栏信息区，768px 以下单栏
5. **中文界面**
