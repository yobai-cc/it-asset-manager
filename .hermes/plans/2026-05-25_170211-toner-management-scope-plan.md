# 墨粉管理改造计划

## 目标

把当前“耗材管理”收窄为“墨粉管理”：

1. UI 与文案从“耗材管理”改为“墨粉管理”。
2. 业务对象从多类型耗材收窄为墨粉，不再让用户选择硒鼓/墨盒/鼓组件/纸张/碳带/其他。
3. 当前表单里的“型号”字段改为二选一：`原装` / `国产`。
4. 黑白打印机只能看到、填写黑色墨粉；彩色打印机可维护黑 / 青 / 品红 / 黄墨粉。
5. 保留现有“以打印机为中心”的交互：打印机卡片 → 进入该打印机的墨粉详情 → 添加/更替/库存调整。
6. 标签打印机继续不进入此模块。

本轮先做 plan，不改代码，不创建 Kanban。

## 当前实现背景

当前项目路径：`/home/yobai/it-asset-manager`

近期已实现：

- 普通 `category=printer` 资产即使没有任何 slot，也会进入 `/consumables` 页面和 `/api/printers/consumables` 聚合结果。
- 无 slot 打印机返回 `printer_type='unconfigured'`、`consumables=[]`。
- 页面提供“添加耗材”入口，能默认关联当前打印机。
- 标签打印机通过 `_is_label_printer()` 过滤。

当前模型仍叫：

- 数据表：`printer_consumable`
- API：`/api/consumables`、`/api/printers/consumables`
- 页面路由：`/consumables`
- 模板：`templates/admin/consumables.html`

建议这轮只改用户可见语义和业务约束，暂不重命名数据库表/API/路由，避免大范围迁移和兼容成本。也就是说内部仍可沿用 `printer_consumable`，但 UI、文档、校验、测试都把它当作“墨粉 slot”。

## 产品口径

### 1. 模块命名

用户可见：

- “耗材管理” → “墨粉管理”
- “新增耗材” → “新增墨粉”
- “更替耗材” → “更换墨粉”
- “耗材槽位” → “墨粉槽位”
- “当前耗材槽位” → “当前墨粉槽位”
- “添加耗材” → “添加墨粉”

内部代码命名是否改：

- 短期不改路由 `/consumables` 和 API `/api/consumables`，避免模板、测试、文档和历史兼容大范围变更。
- 如果后续用户明确希望 URL 也变成 `/toners` 或 `/toner-management`，再单独做迁移/兼容跳转。

### 2. 墨粉类型收窄

当前 `printer_consumable.type` 有 `toner/ink/drum/paper/ribbon/other`。

建议短期策略：

- 新建/编辑接口统一把 `type` 固定为 `toner`。
- 前端隐藏或移除“类型”下拉，不再让用户选择耗材类型。
- 后端对新增/编辑：
  - 若不传 `type`，默认 `toner`。
  - 若传非 `toner`，返回 400，错误文案例如：“墨粉管理只支持 toner 类型”。
- 历史非 toner 数据：暂不删除，聚合页面/API 可只展示 `type='toner'` 的记录；普通列表 `/api/consumables` 是否过滤需谨慎。

建议本轮范围：

- `/consumables` 页面和 `/api/printers/consumables` 聚合只展示墨粉 slot。
- `/api/consumables` 创建/更新限制为 toner。
- 若旧库里已有 paper/ribbon 记录，它们不会影响打印机墨粉视图。

### 3. “型号”改成“原装/国产”

当前字段：`printer_consumable.model`，自由文本，例如 `TN-K`。

用户要求“型号改成二选一：原装/国产”。这里建议将现有 `model` 字段继续复用为来源/类型枚举，值用中文：

- `原装`
- `国产`

原因：

- 不做数据库迁移也能满足需求。
- 当前字段名虽然叫 `model`，但可在 UI 上显示为“类型/来源”。
- 若以后要同时保留“具体型号”和“原装/国产”，再新增字段，如 `supply_source` 或 `toner_kind`。

本轮实现：

- 前端表单：`型号` input 改成 select，label 改为“墨粉类型”或“来源”，选项为 `原装` / `国产`。
- 后端校验：`model` 若存在，必须是 `原装` 或 `国产`。
- API 响应字段仍叫 `model`，显示文案解释为墨粉类型。
- 测试覆盖非法 `model` 返回 400。

开放点：用户说“型号改成二选一”，更直译可把 label 保持“型号”，选项“原装/国产”。我建议 UI label 用“墨粉类型”，但如果希望完全按用户措辞，可用“型号”。

### 4. 黑白 / 彩色打印机可见槽位

规则：

- 黑白打印机：只能看到/填写黑色墨粉。
- 彩色打印机：可看到/填写黑、青、品红、黄。
- 未配置打印机：当前系统无明确打印机颜色属性，只能从已有墨粉颜色推断。无 slot 时应显示“待配置”，并在新增墨粉时需要用户选择彩色/黑白的初始化方式，或默认先按黑白处理。

短期可执行方案：

A. 已有 slot 的打印机

- `_infer_printer_type()` 仍按颜色推断：出现 cyan/magenta/yellow 即彩色，否则黑白。
- 黑白打印机详情只显示黑色 slot。
- 新增/编辑时，如果当前打印机已推断为 mono，则颜色字段只能是 black。
- 如果尝试给 mono 打印机新增 cyan/magenta/yellow，后端拒绝或前端不显示这些选项。

B. 无 slot 的打印机

有两个产品选择：

推荐默认：先作为“待配置”，添加墨粉时默认只显示“黑色”；如果用户添加青/品红/黄之一，则这台打印机转为彩色。

更严格方案：在无 slot 打印机详情里先要求选择“黑白打印机 / 彩色打印机”，再生成可填写颜色。这个需要额外状态字段或一次性初始化动作，范围更大。

本轮建议采用推荐默认：

- 无 slot 打印机卡片显示“待配置”。
- 添加墨粉入口默认选黑色。
- 前端仍可提供“彩色机：添加青/品红/黄”的入口，但这会和“黑白打印机只能看到黑白墨粉”产生歧义，因为系统不知道它是不是黑白。
- 如果用户明确认为资产本身应有“彩色/黑白”属性，则下一步应给打印机资产增加 `printer_type` 字段；本轮不建议在没有数据字段的情况下硬猜。

更稳妥的最小实现：

- 已推断为 mono 的打印机：只允许 black。
- 已推断为 color 的打印机：允许 black/cyan/magenta/yellow。
- unconfigured 的打印机：新增墨粉时只默认 black，同时 UI 留出“配置为彩色打印机”的后续按钮（本轮可不做）。

### 5. 表单交互

新增/编辑墨粉弹窗建议字段：

- 名称：可保留，但默认可根据颜色生成，如“黑色墨粉”。
- 颜色：select，不再自由输入。
  - black：黑色
  - cyan：青色
  - magenta：品红
  - yellow：黄色
- 墨粉类型/型号：select，二选一：原装 / 国产。
- 库存数量
- 预警阈值
- 当前价格
- 安装日期
- 备注
- 关联打印机：保持隐藏或只读默认关联当前打印机，减少用户误选。

黑白打印机表单：

- 颜色 select 只显示 black。
- 如果已有黑色 slot，新增时可提示“黑色墨粉已存在，建议编辑/更换现有 slot”，避免重复黑色 slot。

彩色打印机表单：

- 颜色 select 显示黑/青/品红/黄。
- 如果某颜色已存在，可在选项中禁用或提示已有。

## 技术实施计划

### Phase 1：测试先行

新增/更新测试文件：`tests/test_api.py`

建议新增测试：

1. API 创建墨粉默认 type 为 toner

- POST `/api/consumables` 不传 type。
- 期望返回 201，响应 `type == 'toner'`。

2. API 拒绝非 toner 类型

- POST `/api/consumables` 传 `type='paper'`。
- 期望 400。

3. API 限制 model 二选一

- `model='原装'` / `model='国产'` 可成功。
- `model='TN-K'` 返回 400。

4. 聚合视图只返回墨粉 slot

- 给打印机创建 toner 和 ribbon/paper。
- GET `/api/printers/consumables` 只返回 toner。

5. 黑白打印机不允许新增彩色墨粉

- 创建只有 black slot 的打印机。
- 再尝试新增 cyan slot。
- 期望 400，或至少聚合视图不显示 cyan。

这个测试要注意：当前系统对打印机彩色/黑白没有资产字段，仅靠已有 slot 推断。因此测试应基于“已有 black 且无彩色 slot 的打印机被视为 mono”。

6. 彩色打印机允许四种颜色

- 创建 black/cyan/magenta/yellow。
- 聚合视图仍推断为 color。

7. 页面文案

- `/consumables` 页面包含“墨粉管理”。
- 不再包含关键旧文案：“耗材管理”“新增耗材”“更替耗材”。
- 表单包含“原装”“国产”。

### Phase 2：后端约束

文件：`server.py`

改动点：

1. 增加常量（可在 server.py 或 models.py）：

```python
VALID_TONER_COLORS = ["black", "cyan", "magenta", "yellow"]
VALID_TONER_MODELS = ["原装", "国产"]
```

2. 创建/更新接口

- `api_consumables_create()`：
  - `ctype = data.get("type", "toner")`
  - 非 toner 返回 400。
  - 校验 `color` 必须为合法颜色；默认 black。
  - 校验 `model` 必须为 `原装` / `国产`；可考虑默认 `国产` 或要求必填。
- `api_consumables_update()`：
  - 同样限制 type/model/color。

3. 打印机颜色限制

新增辅助函数：

```python
def _infer_printer_type_for_asset(conn, asset_id): ...
def _validate_toner_color_for_printer(conn, asset_id, color): ...
```

逻辑：

- 如果目标打印机已有 cyan/magenta/yellow slot，则允许全部四种颜色。
- 如果目标打印机没有彩色 slot，但已有 black slot，则视为 mono，仅允许 black。
- 如果目标打印机无 slot，默认允许 black。
- 如后续要显式配置彩色机，再扩展。

4. 聚合 API

- `/api/printers/consumables` SQL 或分组逻辑只纳入 `pc.type = 'toner'` 的 slot。
- 仍用 LEFT JOIN 保证无 slot 打印机出现。
- 注意 SQL 条件不能把 LEFT JOIN 退化成 INNER JOIN：过滤 toner 应写在 JOIN 条件里，例如：

```sql
LEFT JOIN printer_consumable pc
  ON pc.asset_id = a.id AND pc.type = 'toner'
```

5. `/consumables` 页面 SSR 数据

同样把 toner 过滤写在 LEFT JOIN ON 条件中。

### Phase 3：前端 UI 改造

文件：`templates/admin/consumables.html`

改动点：

1. 页面标题/副标题/卡片/弹窗文案改为墨粉管理。
2. 类型下拉移除或隐藏，提交时固定 `type: 'toner'`。
3. 颜色 input 改 select：

```html
<select id="cColor" name="color">
  <option value="black">黑色</option>
  <option value="cyan">青色</option>
  <option value="magenta">品红</option>
  <option value="yellow">黄色</option>
</select>
```

4. 型号 input 改 select：

```html
<select id="cModel" name="model">
  <option value="原装">原装</option>
  <option value="国产">国产</option>
</select>
```

5. 根据当前打印机类型限制颜色选项：

- renderDrawer 时保存 selected printer。
- openCreateForPrinter(assetId) 时根据 printer.printer_type 设置颜色选项。
- mono/unconfigured 默认只给 black。
- color 给四种颜色。

6. Slot 展示文案

- `COLOR_LABELS` 保留黑/青/品红/黄。
- `TYPE_LABELS` 不再需要多类型耗材；可删除或只保留 toner。
- “当前耗材槽位”等改为“当前墨粉槽位”。

### Phase 4：文档同步

文件：

- `CLAUDE.md`
- `README.md`
- `docs/frontend-design-spec.md`
- `CHANGELOG.md`

同步内容：

- 模块名“墨粉管理”。
- 业务范围：只管理打印机墨粉。
- `model` 字段用户语义：原装/国产。
- 黑白打印机只维护黑色墨粉；彩色打印机维护 CMYK。
- 测试数更新。

仍遵守用户文档偏好：文档写当前能力和稳定约定，不写“非目标/禁止/不要恢复”之类纠偏口号。

## 预计修改文件

必改：

- `/home/yobai/it-asset-manager/server.py`
- `/home/yobai/it-asset-manager/templates/admin/consumables.html`
- `/home/yobai/it-asset-manager/tests/test_api.py`
- `/home/yobai/it-asset-manager/CLAUDE.md`

可能改：

- `/home/yobai/it-asset-manager/README.md`
- `/home/yobai/it-asset-manager/docs/frontend-design-spec.md`
- `/home/yobai/it-asset-manager/CHANGELOG.md`
- `/home/yobai/it-asset-manager/static/style.css`（如 select/空状态需要样式微调）

## 验证计划

### 自动化测试

目标测试：

```bash
.venv/bin/python -m pytest tests/test_api.py::TestConsumablesAPI tests/test_api.py::TestPrintersConsumablesAPI tests/test_api.py::TestConsumablesPageDataShape -q
```

全量测试：

```bash
.venv/bin/python -m pytest tests/ -q
```

差分检查：

```bash
git diff --check
```

### 手动/浏览器验收（实现后）

1. 登录管理员。
2. 新增一台普通打印机资产。
3. 打开 `/consumables`：页面应显示“墨粉管理”，该打印机出现为“待配置”。
4. 点击打印机卡片，打开详情。
5. 点击“添加墨粉”：
   - 默认关联当前打印机。
   - 类型不可选或固定墨粉。
   - 型号/来源只有“原装/国产”。
   - 黑白/未配置打印机默认只显示黑色。
6. 创建黑色墨粉后，卡片显示黑色墨粉信息。
7. 对该黑白打印机尝试添加青色墨粉，前端不可选；如果绕过前端调用 API，后端返回 400。
8. 创建彩色打印机场景，验证黑/青/品红/黄可管理。

## 风险和取舍

1. “黑白/彩色打印机”的来源不明确

当前资产模型没有打印机颜色属性。用已有 slot 反推是短期可行方案，但无 slot 的打印机无法准确知道彩色/黑白。

建议本轮采用：无 slot 默认按黑白配置，只允许黑色；如果用户希望新彩色打印机第一次就能添加 CMYK，则下一轮需要给打印机资产增加“打印机类型：黑白/彩色”字段，或者在墨粉管理中增加“配置为彩色机”的动作。

2. `model` 字段语义变化

数据库列名仍是 `model`，但用户语义从“具体型号”变成“原装/国产”。短期最小改动可接受；长期如果需要同时记录具体型号，应新增字段。

3. 历史非 toner 数据

旧数据可能存在 paper/ribbon/ink 等。建议不删除，聚合页面只展示 toner；如用户确认这些历史数据无价值，再做迁移清理。

## 建议执行方式

如果用户确认这个 plan，下一步按 TDD 直接实现：

1. 先写失败测试。
2. 跑目标测试确认失败。
3. 修改后端校验和聚合 SQL。
4. 修改前端表单和文案。
5. 跑目标测试、全量测试、diff check。
6. 必要时再用浏览器验收 `/consumables`。
