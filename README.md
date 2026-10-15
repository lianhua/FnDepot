# FnDepot 应用源 — 自动同步上游 .fpk（V2 源）

把 GitHub 上别人已经打包好的飞牛 fnOS `.fpk` 应用，通过 **FnDepot 去中心化应用源**分发。NAS 上装 FnDepot 商店并添加本仓库后，NAS 会每天自动同步：上游发新 release → GitHub Actions 自动下载 fpk、更新索引 → 商店提示更新，点一下升级。

当前收录：**柠檬音乐 lemon-music**（上游 [jia070310/lemon-muisc](https://github.com/jia070310/lemon-muisc)，MIT 协议，作者 jia070310）

## 目录结构

```
FnDepot/                          ← 仓库名必须是 FnDepot（Public，大小写敏感）
├── fnpack.json                   ← V2 格式应用源索引（Actions 自动维护）
├── .github/workflows/
│   └── sync-release.yml          ← 每天定时同步上游 release
└── assets/
    ├── ICON.PNG / ICON_256.PNG   ← 从上游 fpk 自动提取
    └── lemon-music-<版本>-<架构>.fpk   ← 自动下载，只保留最新版
```

本源采用 **V2 格式**（`schema_version: "2"`），按架构分别给下载地址，客户端自动挑选匹配当前设备架构的包：

```json
"packages": {
  "x86": { "download_url": "...", "sha256": "...", "size": 5515619 },
  "arm": { "download_url": "...", "sha256": "...", "size": 5515623 }
}
```

客户端选择顺序：`packages.x86` → `packages.all` 回退（arm 设备同理），因此 x86 和 ARM NAS 都能正确安装。`sha256` 会由客户端强制校验。

## 使用者怎么装（NAS 侧）

1. 官方应用商店 → 手动安装 → 上传 **FnDepot 商店** 的 fpk（装完桌面出现商店图标）
2. 打开 FnDepot → 源管理 → 添加源 → 填 `https://github.com/lianhua/FnDepot`
3. 同步完成 → 出现「柠檬音乐」→ 点安装
4. 商店里开启**自动源同步**（或装「任务计划」应用，cron `0 */12 * * *`）
5. GitHub 访问不畅就在商店里配加速地址，如 `https://gh-proxy.com`

> ⚠️ V2 格式需要 **FnDepot 客户端 v0.0.7 以上**，旧版客户端只能读 V1。

## 维护者怎么改（一般不需要）

想加新应用或换上游，改 `.github/workflows/sync-release.yml` 的三个变量：

| 变量 | 说明 |
|---|---|
| `UPSTREAM_REPO` | 上游仓库 `owner/repo` |
| `APP_NAME` | 应用 ID，**必须与上游 FPK manifest 里的 `appname` 完全一致**（大小写敏感） |
| `FPK_ARCHS` | 要同步的架构，空格分隔，如 `"x86 arm"` 或 `"x86"` |

改完在 `fnpack.json` 里补一个对应条目（键名 = `APP_NAME`，`releases` 初始写 `{"0.0.0": {"updated_at": "...", "packages": {}}}`），然后手动触发一次 workflow，它会自动抓取真实元数据、下载 fpk、算 sha256、填好索引。

## 这个源做了什么自动化

每天 UTC 18:00（北京时间 02:00）：

1. 读上游 `releases/latest`，取 tag 作为版本号（自动去 `v` 前缀）
2. 与源内版本比对，一致就跳过，不一致才动手
3. 按 `FPK_ARCHS` 下载各架构 fpk 到 `assets/`
4. 解包任一 fpk，从 `manifest` 提取 `display_name` / `desc` / `service_port` / `os_min_version` 和图标
5. 计算 sha256 与字节数，写进 `fnpack.json` 的 `releases.<版本>.packages`
6. 删除旧版本安装包（仓库只留最新版，不会无限膨胀）
7. 自动 commit 并 push

## 注意事项

- **上游 release 必须带 .fpk 资产**，且文件名带架构后缀（如 `-x86.fpk` / `-arm.fpk`），否则同步不到
- **版本号一致性**：以 release tag 为准；tag 不带 `v` 前缀也能正确处理
- **`APP_NAME` 必须等于上游 manifest 的 `appname`**，写错会导致客户端找不到对应条目
- **下载走本仓库 raw**，而不是直接指向上游 release——这样国内可以配 GitHub 加速，稳定性更好；代价是每次更新要把 fpk 存进仓库
- **先自测再分发**：x86 和 ARM NAS 上分别装一次，确认包选择和安装正常
