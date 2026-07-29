# 断点续传 + 全通道测速

「下载依赖」三大组件均走 `scripts/netfetch.py`：

1. **并行测速全部镜像**（快→慢排序）
2. **选最快通道下载**
3. 大文件自动 **多线程分片**（支持 Range 时）
4. 中断后续传（`.part` / `.parts/`）
5. 某通道过慢（默认 <120KB/s 持续 15s）自动切换下一条并续传

| 组件 | 脚本 |
|------|------|
| Chromium | `scripts/fetch_chromium.py` |
| Camoufox | `scripts/fetch_camoufox.py` |
| mihomo | `install_all_deps` → netfetch |

手动只测速：
```bash
python scripts/netfetch.py --github --probe-only 'https://github.com/daijro/camoufox/releases/download/v152.0.4-beta.28/camoufox-152.0.4-beta.28-win.x86_64.zip'
```
