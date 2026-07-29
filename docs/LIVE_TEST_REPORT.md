# LIVE_TEST_REPORT — 打开程序全功能实测

更新时间: 2026-07-29T03:58:02
版本: **1.10.1-v10.1**
管理台: http://127.0.0.1:17888/ （已用浏览器打开并点选侧栏）
客户端入口: `python -m mozilla_manager.client` / `cli client`（pywebview 原生窗 / tk 回退）

## 总结果

| 项 | 结果 |
|----|------|
| 全功能 API 矩阵 | **105/105 PASS** |
| 失败 | **0** |
| compliance | 86/86 |
| launch 自动 rebind | **ok + rebound → JP Asia/Tokyo** 出口 `203.10.99.34` |
| Chromium 全链路 | 42/42 |
| Camoufox | 3/3 |
| ops/v10 工具箱 | 31/31 |

## 分组明细

- **ui**: 5 ok / 0 fail
- **system**: 10 ok / 0 fail
- **nodes**: 11 ok / 0 fail
- **profile-chromium**: 42 ok / 0 fail
- **camoufox**: 3 ok / 0 fail
- **ops-v10**: 31 ok / 0 fail
- **cleanup**: 3 ok / 0 fail


## UI 侧栏点选（已操作）

1. 环境管理 `profiles`
2. 分组管理 `groups`
3. 代理管理 `proxies`
4. 订阅/节点 `subs`
5. 系统诊断 `doctor`
6. v10.1 工具箱 `tools`

截图: `tmp/ui_home.png` `tmp/ui_groups.png`

## 覆盖功能（节选）

- Profile CRUD / 绑节点 / 扩展 / 标签 / 隐私 / 隐身 / 虚拟媒体
- 启动 + **自动 rebind** + 检测页 + 诊断 + egress
- Cookie 导入导出 / failover 切换 / 录制时间线
- 快照 / 会话备份 / 时间旅行 / 登录巡检
- 导出 zip / 增量 / 迁移包 / RPA 运行
- 锁定防启动 / 解锁
- Camoufox 无代理 +（矩阵含）双引擎
- 订阅节点收藏推荐 / mihomo / 模板包 112
- 通知 / 任务 / 审计 / watchdog / fleet / vault / backup / reports / totp / batch / turnstile

## 产物

- `tmp/e2e_all_features.json`
- `logs/e2e_all_features.out`
- `docs/LIVE_TEST_REPORT.md`
