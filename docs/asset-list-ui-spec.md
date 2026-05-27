# 资产台账页面 UI 设计需求稿

## 页面概述

IT 资产管理系统的资产台账页（`/assets`），面向 IT 管理员，是系统中最核心的高频页面。用于浏览、搜索、筛选所有 IT 固定资产，支持批量操作（打印标签、导出 CSV）、批量导入、以及点击行打开右侧详情抽屉。

**技术约束**：纯 HTML + CSS + Vanilla JS，无前端框架，无构建步骤。页面在管理端 App Shell 中渲染（左侧 200px 侧边栏 + 顶部 70px header），主内容区纵向滚动。

---

## 设计令牌

```css
--color-primary: #2563eb;     --color-primary-dark: #1d4ed8;
--color-success: #10b981;     --color-warning: #f59e0b;
--color-danger: #ef4444;      --color-info: #3b82f6;
--color-bg-main: #f8fafc;     --color-bg-card: #ffffff;
--color-text-main: #0f172a;   --color-text-muted: #64748b;
--color-border: #e2e8f0;      --color-border-light: #f1f5f9;
--radius-medium: 8px;         --radius-strong: 16px;
--shadow-soft: 0 1px 3px rgba(15,23,42,0.05);
--shadow-card: 0 4px 20px -2px rgba(15,23,42,0.04), 0 2px 6px -1px rgba(15,23,42,0.02);

/* 字体层级 */
--fs-page-title: 28px;   /* 页面标题 */
--fs-section-title: 18px; /* 区块标题 */
--fs-card-title: 16px;   /* 卡片标题 */
--fs-body: 14px;         /* 正文/表格/按钮 */
--fs-meta: 13px;         /* 辅助说明 */
--fs-small: 12px;        /* 徽章/标签/时间戳 */
```

**状态色**：
- 库存 in_stock：蓝 `rgba(59,130,246,0.12)` + `#3b82f6`
- 在用 assigned：绿 `rgba(16,185,129,0.12)` + `#10b981`
- 维修中 maintenance：橙 `rgba(245,158,11,0.12)` + `#f59e0b`
- 已报废 scrapped：红 `rgba(239,68,68,0.12)` + `#ef4444`

**分类色**（用于分类徽章和图标背景）：
```
computer: #2563eb    monitor: #7c3aed    phone: #059669
tablet: #d97706      printer: #ef4444    server: #475569
network: #0891b2     firewall: #be185d   switch: #65a30d
```

---

## 页面布局

```
┌────────────────────────────────────────────────────────────────────┐
│  资产台账                              [批量导入] [导出CSV] [新增资产] │  ← 页面头部
│  管理所有固定资产，点击行查看详情                                      │
├────────────────────────────────────────────────────────────────────┤
│ [全部] [在用] [库存] [维修中] [已报废]  类别:[▼全部]  [🔍 搜索...      ]│  ← 工具栏
├────────────────────────────────────────────────────────────────────┤
│ ☐ │ 标签号        │ 资产              │ 类别  │ 状态 │ 持有人 │ 位置     │  ← 表头
│   │               │ 品牌·型号·SN       │       │      │       │          │
├───┼───────────────┼───────────────────┼───────┼──────┼───────┼──────────┤
│ ☐ │ PC-2026-0001  │ ThinkPad T14s...  │ 电脑  │ 在用 │ 张三  │ 工位A-101│  ← 数据行
│   │               │ Lenovo·T14s·SN..  │       │      │       │          │
│ ☐ │ PC-2026-0002  │ MacBook Pro 14    │ 电脑  │ 在用 │ 李四  │ 工位B-205│
│   │               │ Apple·M3 Pro·SN.. │       │      │       │          │
│ ☐ │ MON-2026-0001 │ DELL U2723QE      │显示器 │ 在用 │ 张三  │ 工位A-101│
│   │               │ DELL·U2723QE·SN.. │       │      │       │          │
├────────────────────────────────────────────────────────────────────┤
│              [上一页] [1] [2] [3] [下一页]                          │  ← 分页
│                    第 1-15 条，共 11 条                              │
└────────────────────────────────────────────────────────────────────┘
```

点击数据行时，从右侧滑出详情抽屉（400px 宽），不离开当前页面。

---

## 各区块详细设计

### 1. 页面头部（page-header）

**容器**：flex 横排，左右对齐，`margin-bottom: 24px`

**左侧**：
- 页面标题 `h1`：`font-size: 28px`（`--fs-page-title`），`font-weight: 800`
- 副标题 `p`：`font-size: 13px`（`--fs-meta`），`color: --color-text-muted`，`margin-top: 8px`

**右侧操作按钮组**（`.page-actions`）：
- 三个按钮水平排列，`gap: 8px`
- "批量导入"：白底灰边（`.btn-secondary`）
- "导出CSV"：白底灰边
- "新增资产"：蓝底白字（`.btn-primary`），最突出

**按钮通用样式**：
- `height: 36px`，`padding: 0 16px`，`font-size: 14px`（`--fs-body`），`font-weight: 600`
- `border-radius: 8px`，`border: 1px solid --color-border`
- 主按钮：`background: --color-primary`，`color: #fff`
- 次按钮：`background: #fff`，hover 时 `border-color: --color-primary`

### 2. 工具栏（toolbar）

**容器**：白底卡片，`border-radius: 16px`，`border: 1px solid --color-border-light`，`padding: 16px`，`margin-bottom: 24px`，`box-shadow: --shadow-card`

**布局**：flex 横排，左右两端对齐，`gap: 16px`，内容换行时自动 wrap

**左侧 — 状态筛选 Tabs + 类别下拉**：
- 状态 Tabs：
  - 容器：`display: flex`，`gap: 4px`，`padding: 4px`，`background: --color-bg-main`，`border: 1px solid --color-border`，`border-radius: 16px`
  - 每个Tab：`height: 36px`，`padding: 0 16px`，`border-radius: 8px`，透明背景
  - 激活态：`background: #fff`，`box-shadow: 0 1px 3px rgba(0,0,0,0.08)`，`color: --color-text-main`，`font-weight: 700`
  - 非激活：`color: --color-text-muted`，hover 时 `color: --color-text-main`
  - 五个Tab：全部 / 在用 / 库存 / 维修中 / 已报废

- 类别下拉（`<select>`）：
  - 与 Tabs 之间 `gap: 12px`
  - `height: 36px`，`padding: 0 12px`，`border: 1px solid --color-border`，`border-radius: 8px`

**右侧 — 搜索框**：
- `<input type="text">`，`width: 280px`，`height: 36px`
- `padding: 0 12px 0 36px`（左侧留出搜索图标空间）
- `border: 1px solid --color-border`，`border-radius: 8px`
- placeholder：`"搜索标签号、名称、序列号..."`
- 左侧搜索图标（🔍 或 SVG 放大镜），`position: absolute` 定位在 input 内左侧 `12px`
- 回车键触发搜索

### 3. 表格

**外层容器**（`.table-shell`）：`background: #fff`，`border: 1px solid --color-border-light`，`border-radius: 16px`，`box-shadow: --shadow-card`，`overflow: hidden`

**表头**（`<thead>`）：
- 背景：`--color-bg-main`（`#f8fafc`）
- 文字：`font-size: 13px`（`--fs-meta`），`font-weight: 600`，`color: --color-text-muted`，`text-transform: none`
- 单元格：`padding: 12px 16px`
- 底部：`border-bottom: 1px solid --color-border`

**数据行**（`<tbody><tr>`）：
- 高度约 56px，`padding: 12px 16px`
- 鼠标悬浮：`background: --color-border-light`（`#f1f5f9`）
- 点击行（非链接/按钮区域）时打开右侧详情抽屉
- 底部分割线：`border-bottom: 1px solid --color-border-light`
- 最后一行无底线

**列定义**（8列，`table-layout: fixed`）：

| 列宽 | 列名 | 内容说明 |
|------|------|---------|
| 40px | ☐ | 复选框，用于批量选择 |
| 12% | 标签号 | 蓝色链接，点击跳转详情页 |
| 24% | 资产 | **两行结构**：上行资产名（粗体），下行品牌·型号·SN（灰色小字 12px） |
| 10% | 类别 | 彩色分类徽章（圆角 4px，小字 12px，分类色文字+浅色背景） |
| 8% | 状态 | 状态徽章（圆角胶囊，对应状态色） |
| 10% | 持有人 | 人名，无持有人时显示"-" |
| 10% | 位置 | 位置文本，溢出省略 |
| 14% | 操作 | "详情"链接 + "标签"链接（target=_blank） |

**空状态**：
- 居中显示，`padding: 48px 16px`
- 图标（📂 或 📋）+ 文字"暂无匹配的资产"
- 提示"尝试调整筛选条件，或点击「新增资产」添加"

### 4. 批量操作栏（batch-bar）

- 当表格中存在复选框时显示，贴在表格上方
- 蓝底（`--color-primary`）白字，`border-radius: 8px`，`padding: 8px 16px`
- 左侧：选中数量提示"3 项已选"（未选中时显示"请先勾选资产"）
- 右侧：[批量打印标签] 按钮（未选中时 disabled）

### 5. 分页

- 居中排列，`margin-top: 24px`
- 页码按钮：`min-width: 40px`，`height: 40px`，`border: 1px solid --color-border`，`border-radius: 8px`
- 当前页：`background: --color-primary`，`color: #fff`，`border-color: --color-primary`
- 非当前页：白底，hover 时 `border-color: --color-primary`
- "上一页"/"下一页"文字按钮
- 下方分页信息：`font-size: 13px`，`color: --color-text-muted`，`text-align: center`，`margin-top: 4px`
  - 格式："第 1-15 条，共 42 条"

### 6. 详情抽屉（右侧滑出，400px）

**容器**：
- `position: absolute`，`right: 0`，`top: 0`，`width: 400px`，`height: 100%`
- 白底，`border-left: 1px solid --color-border`，`box-shadow: -4px 0 16px rgba(0,0,0,0.08)`
- `transform: translateX(100%)` → `.is-open` 时 `translateX(0)`，`transition: 0.3s ease`
- `overflow-y: auto`，`padding: 24px`
- `z-index: 100`

**头部**：
- 标签号（eyebrow）：蓝字小号 `12px`，粗体
- 资产名称：`font-size: 22px`，粗体
- 关闭按钮（×）：右上角

**资产图标区**：
- 高度 120px，圆角 16px，浅灰背景
- 居中显示分类 emoji 图标（大号，如 💻 🖥️ 📱 等）

**操作工具栏**：
- 四个按钮：[编辑] [操作/领用] [标签] [删除]
- 删除按钮：仅库存状态可用，其他状态 disabled

**信息网格**（双列）：
- 8 个字段卡片：类别 / 品牌 / 型号 / 序列号 / 持有人 / 位置 / 购入日期 / 保修到期
- 每个卡片：`border: 1px solid --color-border-light`，`border-radius: 8px`，`padding: 8px`
- 标签：灰色小字 12px
- 值：正文 13px

**生命周期时间线**：
- 区块标题"生命周期"
- 纵向时间线，左侧竖线 + 圆点，事件按时间倒序
- 事件名称 + 日期·操作人

**标签预览**：
- 区块标题"标签预览"
- 缩略的 60×40mm 标签卡片预览

### 7. 批量导入弹窗

- 遮罩 + 居中白卡，`max-width: 520px`，`border-radius: 16px`
- 标题"批量导入资产"
- 说明文字（灰色）：编码 UTF-8，必填列 name/category，可选列等
- 文件上传 input
- [开始导入] + [取消] 按钮
- 导入完成后显示结果：成功 N 条，失败 N 条（如有失败，列表展示行号+错误信息）

---

## 分类/状态映射（JS 中使用）

```javascript
const statusLabels = {in_stock:'库存', assigned:'在用', maintenance:'维修中', scrapped:'已报废'};
const statusClasses = {in_stock:'badge-instock', assigned:'badge-assigned', maintenance:'badge-maintenance', scrapped:'badge-scrapped'};
const catLabels = {computer:'电脑', monitor:'显示器', phone:'手机', tablet:'平板', printer:'打印机', server:'服务器', network:'网络设备', firewall:'防火墙', switch:'交换机'};
const catColors = {computer:'#2563eb', monitor:'#7c3aed', phone:'#059669', tablet:'#d97706', printer:'#ef4444', server:'#475569', network:'#0891b2', firewall:'#be185d', switch:'#65a30d'};
const catIcons = {computer:'💻', monitor:'🖥️', phone:'📱', tablet:'📋', printer:'🖨️', server:'🗄️', network:'🌐', firewall:'🛡️', switch:'🔀'};
```

---

## API 数据结构

`GET /api/assets?page=1&limit=15&status=assigned&category=computer&search=ThinkPad`

```json
{
  "total": 11,
  "page": 1,
  "limit": 15,
  "assets": [
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
      "created_at": "2026-05-26 05:10:39",
      "updated_at": "2026-05-26 05:10:39"
    }
  ]
}
```

抽屉详情 API：`GET /api/assets/<id>` 返回完整详情（含 `events` 和 `maintenance_records`，结构与资产详情页 API 一致）。

---

## 交付要求

1. **单文件 HTML**：CSS 和 JS 写在同一个 `.html` 文件中，可直接在浏览器打开预览
2. **使用模拟数据**：用上方 API JSON 数据硬编码在 JS 中，不需要真实 API 调用
3. **需要实现的交互**：
   - 状态 Tab 切换（视觉切换即可，不需要真正过滤数据）
   - 搜索框（视觉展示即可）
   - 点击表格行打开/关闭右侧详情抽屉（需要 JS 动画）
   - 关闭抽屉按钮
   - 全选/单选复选框联动批量操作栏
   - 分页按钮视觉状态
4. **不需要实现**：批量导入弹窗、CSV 导出、真实 API 调用、标签打印
5. **响应式**：768px 以下表格可横向滚动或改为卡片布局
6. **中文界面**
