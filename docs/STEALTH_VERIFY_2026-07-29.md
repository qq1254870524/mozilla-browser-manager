# 浏览器伪装验证报告

- 版本: `1.10.2-v10.2`
- 总评: **通过**（3/3）
- 耗时: 20.23s

| 引擎 | 补丁 | 伪装 | 关键项 | webdriver | 时区 | 语言 | 出口IP | 国家 |
|------|------|------|--------|-----------|------|------|--------|------|
| pw_chromium | patchright | ✅ | 8/8 | False | Asia/Tokyo | ja-JP | 203.10.99.42 | JP |
| camoufox | patchright | ✅ | 8/8 | None | Asia/Tokyo | ja-JP | 203.10.99.42 | JP |
| pw_chromium | rebrowser | ✅ | 8/8 | None | Asia/Tokyo | ja-JP | 203.10.99.42 | JP |

## 判定标准（关键项）
- `navigator.webdriver` 为 false/undefined
- 无自动化全局残留（cdc_/__playwright/__selenium 等）
- 时区/语言与 Profile 环境包一致
- UA 存在且不含 Headless
- 出口 IP 国家与 expected_country 一致（走代理时）
- 诊断：proxy/dns/webrtc 通过

原始数据: `tmp/verify_stealth_live.json`
API: `POST /api/stealth/profiles/{id}/probe`
