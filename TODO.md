# 待办事项

## 近期优化

- [x] 生产部署改用 gunicorn + systemd，替代 Flask 开发服务器
- [x] 员工批量导入增加 CSV 下载模板功能
- [x] 操作记录导出
- [x] 资产软删除 / 回收站（恢复、永久删除、批量操作）
- [x] 资产 API 鉴权收紧（admin-only 列表、employee 只看自己）
- [x] 打印机报废自动解绑耗材、墨粉管理视图隔离
- [x] 用户自助修改密码（`POST /api/change-password`，校验旧密码）
- [x] Android 客户端 P0：规划与 API 合约基线（`android/docs/`）
- [ ] 认证接入 SSO / LDAP，替代 session + 密码
- [ ] 状态机扩展：允许 in_stock → maintenance（库房设备直接送修）

## 功能规划

- [ ] 多级审批流（当前仅单级审批）
- [ ] 采购/合同管理模块
- [ ] 资产自动发现（网络扫描）
- [ ] 员工停用/恢复历史视图
- [ ] 资产到期/保修到期邮件通知
- [ ] 盘点模块（后端）：新增 `inventory_session` / `inventory_scan` 表 + 会话、批量扫码、差异报告 API（当前仅扫码核验，无持久化盘点会话）
- [x] 操作记录导出

## 技术改进

- [ ] 国际化（当前仅中文界面）
- [ ] API 接口加分页统一封装，减少重复代码
- [ ] 前端抽取公共组件（表格、弹窗、分页）减少模板重复
- [x] SQLite WAL 模式提升并发读性能

## Android 客户端

P0（规划与 API 合约）已完成，见 `android/docs/`。P1 为实际工程实现，管理员现场端优先；员工自助暂缓。

- [ ] P1：Kotlin + Jetpack Compose 工程，Retrofit + 持久化 CookieJar 复用 Flask session
- [ ] P1：服务器地址配置 + 健康检查 + 登录 + `/api/me` 角色路由
- [ ] P1：扫码（CameraX + ML Kit）解析 `/scan/<id>`，匿名查询走 `/api/public/asset*`
- [ ] P1：管理员现场闭环——入库、编辑、分配、移交、归还、送修/维修完成、报废、回收站
- [ ] P1：轻量盘点核验（扫码 + 详情 + 可选改位置/备注）
- [ ] P1（后端增强，非阻塞）：移动端 bootstrap/capabilities 接口（`/api/mobile/bootstrap`、`/api/mobile/capabilities`）减少多次请求
- [ ] P2：完整盘点会话、差异报告、离线扫码队列（需后端新增表与接口）

## 已知限制

- session + 密码认证，无 SSO/LDAP
- 单级审批，无审批流
- 无采购/合同管理
- 无资产自动发现
- 中文界面，未国际化
- 员工花名册和系统账号保持分离，后续如需关联可增加绑定关系，不强制合并
- 当前状态机不允许 in_stock → maintenance（库房设备不能直接送修，需先分配再送修）

## 业务确认点

- 当前状态机仅允许 `assigned → maintenance`，不允许 `in_stock → maintenance`。如果实际存在库房坏设备直接送修的场景，需要补一条流转。
