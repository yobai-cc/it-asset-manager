# 耗材管理 UI Kanban 验收计划

## 目标

继续验收 it-asset-manager 的耗材管理 UI，重点是 `/consumables` 的浏览器交互和“打印机卡片”体验，并验证用户新增的打印机资产是否能按 `category=printer` 自动出现在耗材管理页面。

本轮先做计划，不直接创建/调度 Kanban 卡片，不改代码。

## 当前上下文

项目路径：`/home/yobai/it-asset-manager`

已知当前实现：

- `/consumables` 页面由 `server.py:220` 的 `consumables_page()` 渲染。
- 当前页面查询使用：`FROM asset a INNER JOIN printer_consumable pc ON pc.asset_id = a.id WHERE a.category = 'printer'`。
- 这意味着：只有已经有关联耗材记录的打印机才会出现在卡片列表；“刚添加但还没有耗材 slot 的打印机”不会出现。
- 用户期望是：只要资产分类是打印机，就应该自动出现在耗材管理页面；耗材 slot 可以后续在该打印机卡片内新增。
- 前端模板：`templates/admin/consumables.html`，当前已有：
  - 打印机卡片列表
  - 彩色 / 黑白 / 告警筛选
  - 点击卡片打开右侧详情
  - 新增/编辑耗材、库存调整、更替耗材、更替历史等弹窗逻辑
- 现有测试在上一轮验证为：`158 passed`。

## 产品验收口径

### 必须满足

1. 打印机资产自动出现
   - 在资产台账中创建 `category=printer` 的资产后，不需要先创建耗材，该打印机也应出现在 `/consumables` 打印机卡片列表。
   - 标签打印机仍不纳入耗材管理（按现有 `_is_label_printer()` 逻辑过滤）。

2. 打印机卡片体验
   - 每台打印机是一张卡片，用户点击卡片进入该打印机的耗材详情。
   - 没有耗材 slot 的打印机也应有合理空状态和“添加耗材/初始化槽位”的入口，而不是让右侧详情空白或报错。
   - 彩色/黑白分类应清晰；如果没有 slot 数据，不能误导显示“四个槽位均可用/黑色耗材正常”。

3. 浏览器交互
   - 登录管理员后访问 `/consumables` 无 JS 错误。
   - 点击卡片、筛选 chip、打开/关闭弹窗、创建耗材、调整库存、更替耗材、查看历史等关键交互可用。
   - 用户数据（资产名、备注、耗材名等）不能通过 `innerHTML` 直接注入造成 XSS 风险。

4. 数据/API 一致性
   - 页面 SSR 数据与相关 API 数据形状一致，特别是打印机聚合数据。
   - 如果存在 `/api/printers/consumables` 或计划补齐该聚合 API，应保证它也返回无耗材 slot 的打印机。

5. 回归验证
   - 完整测试：`.venv/bin/python -m pytest tests/ -q`
   - 静态差分检查：`git diff --check`
   - 浏览器 smoke：真实打开 `/consumables` 完成交互检查。

## 建议 Kanban 最小 DAG

使用 Kanban 是合理的：这是一个多阶段 UI 验收 + 可能需要工程修复 + 复核的任务，适合 durable handoff 和飞书进展。

### Card 1：浏览器验收与缺陷清单

Assignee：`gpt-worker`

技能：`kanban-acceptance-sop`、`dogfood`

性质：只读验收，不改文件。

目标：

- 启动或复用本地 Flask 服务。
- 管理员登录。
- 用浏览器实际访问 `/consumables`。
- 创建一个普通打印机资产（`category=printer`）和一个标签打印机资产作为对照。
- 验证普通打印机是否自动出现在耗材管理页面。
- 验证没有耗材 slot 的打印机卡片、详情空状态、添加耗材入口是否合理。
- 验证筛选 chip、卡片点击、弹窗、库存调整、更替、历史查看。
- 检查浏览器 console。
- 输出 PASS / NEEDS_CHANGES，若 NEEDS_CHANGES，列出具体缺陷、复现步骤、截图/console 证据、建议修复方向。

验收重点：

- 用户最关心的“添加打印机资产后自动出现”必须作为首要检查。
- 不把工程缺陷交给用户决策；若有明确 bug，后续自动创建修复卡。

### Card 2：修复耗材管理 UI/数据聚合缺陷（条件卡）

只有 Card 1 发现 must-fix 时创建。

Assignee：`glm-worker`

技能：`test-driven-development`、`systematic-debugging`

目标：

- 修复 `/consumables` 数据源，使所有 `category=printer` 且非标签打印机的资产都出现在页面上，即使尚无 `printer_consumable` 行。
- 保持耗材 slot 模型轻量，不扩展成采购/FIFO/供应商系统。
- 为无 slot 打印机提供清晰空状态和新增耗材入口。
- 修复浏览器验收发现的交互/JS/样式问题。
- 添加或更新测试，覆盖：
  - 无耗材 slot 的打印机出现在 `/consumables` 或聚合 API 中；
  - 标签打印机被排除；
  - 有耗材 slot 的打印机仍正常显示；
  - 关键 API 不破坏现有耗材创建/调整/更替逻辑。

可能涉及文件：

- `server.py`
  - `consumables_page()` 的 SQL 可能需要从 `INNER JOIN` 改为 `LEFT JOIN`，并正确处理 `pc.id IS NULL`。
  - 若已有或补齐 `/api/printers/consumables`，保持同一聚合逻辑。
- `templates/admin/consumables.html`
  - 无 slot 打印机的卡片文案、详情空状态、添加耗材入口。
  - 点击卡片后应能默认关联当前打印机打开新增耗材弹窗。
- `tests/test_api.py`
  - 增加服务端聚合/页面数据相关回归测试。
- `static/style.css`
  - 如需优化卡片/空状态/按钮体验，才改。

验证命令：

```bash
.venv/bin/python -m pytest tests/ -q
git diff --check
```

### Card 3：复验与最终验收

Assignee：`gpt-worker`

技能：`kanban-acceptance-sop`、`dogfood`

依赖：Card 2（如果创建了修复卡）；如果 Card 1 直接 PASS，则可由 default 直接总结，不需要 Card 3。

目标：

- 读取修复 diff 和测试结果。
- 重新浏览器打开 `/consumables`。
- 复现用户路径：新增打印机资产 → 进入耗材管理 → 自动出现打印机卡片 → 点击卡片 → 添加耗材 → 卡片/详情更新。
- 验证标签打印机排除、彩色/黑白筛选、告警筛选、console clean。
- 输出最终 PASS / NEEDS_CHANGES。
- 如仍有 must-fix，继续 fix-loop，不问用户处理明显工程缺陷。

## 推荐执行顺序

1. 由 default 创建 Card 1，并订阅飞书通知。
2. Card 1 完成后，default/gpt-worker 读取实时 `show/runs/log`。
3. 如果 Card 1 PASS：default 发送飞书完成摘要并向用户总结。
4. 如果 Card 1 NEEDS_CHANGES：立即创建 Card 2 给 `glm-worker`，订阅飞书，不把明确工程缺陷交给用户。
5. Card 2 完成后创建/重跑 Card 3。
6. Card 3 PASS 后，发送单次最终飞书完成通知，包含：改动文件、测试结果、浏览器验收结论、预览/访问方式。

## 需要特别防止的坑

- 不要只看 API 测试，必须用浏览器真实打开 `/consumables`。
- 不要只验证已有耗材的打印机；必须验证“新打印机，无耗材 slot”场景。
- 不要把标签打印机纳入耗材管理。
- 不要因为没有 slot 就把彩色机显示为“四个槽位均可用”。
- 不要在没有主动 follow-up 机制的情况下说“我会等它完成”；如果需要持续跟进，应当创建轮询/cron 或在当前回合检查到完成/超时。

## 开放问题

当前实现可能无法从资产字段准确判断彩色/黑白打印机，尤其是无耗材 slot 时。默认建议：

- 短期：无 slot 打印机显示为“待配置”或“未配置耗材”，避免误判彩色/黑白。
- 中期：如果用户需要更准确分类，再考虑给打印机资产增加可选属性或在耗材页面提供“初始化彩色/黑白槽位”的动作。

这个问题不阻塞本轮验收；本轮首要目标是“按分类自动出现”。
