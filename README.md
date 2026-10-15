# FnDepot 应用源 — 上游现成 .fpk 自动同步

把 GitHub 上别人已经打包好的飞牛 fnOS `.fpk` 应用，通过 **FnDepot 去中心化应用源**分发。NAS 上装 FnDepot 商店并添加你的仓库后，每天自动同步：上游发新 release → Actions 自动下载 fpk、更新索引 → 商店提示更新，点一下升级。

## 目录结构

```
FnDepot/                        ← 仓库名必须是 FnDepot（Public，大小写敏感）
├── fnpack.json                 ← 应用源索引（Actions 自动更新 version/download_url）
├── .github/workflows/
│   └── sync-release.yml        ← 每天定时同步上游 release
└── myapp/                      ← 应用产物目录
    ├── ICON.PNG                ← 64x64，Actions 会自动用 fpk 里的图标覆盖
    ├── ICON_256.PNG            ← 256x256
    └── myapp.fpk               ← Actions 自动下载，勿手改
```

## 上手步骤

### 1. 建仓库

GitHub 新建 **Public** 仓库，**仓库名必须是 `FnDepot`**（FnDepot 客户端靠这个名字识别源）。把本目录整个推上去：

```bash
git init && git add . && git commit -m "init"
git branch -M main
git remote add origin https://github.com/lianhua/FnDepot.git
git push -u origin main
```

### 2. 改两处

| 文件 | 改什么 |
|---|---|
| `.github/workflows/sync-release.yml` | `UPSTREAM_REPO` 填上游 `owner/repo`；`APP_NAME` 填应用 ID；多架构时 `FPK_MATCH`（如 `x86.fpk`） |
| `fnpack.json` | 键名改成应用 ID（须与 `APP_NAME` 一致）；填 `display_name`、`desc`、`labels`，以及上游作者的 `author`/`author_url`/`bug_report_url` |

图标不用管——同步时会从 fpk 里自动提取；想自定义就先往 `myapp/` 放 `ICON.PNG`/`ICON_256.PNG`，下次同步会被上游图标覆盖（要么用 fpk 里的，要么自己改 `sync-release.yml`）。

### 3. 手动跑一次验证

仓库页面 → Actions → `sync-release-fpk` → Run workflow。跑完确认 `myapp/myapp.fpk` 生成、fnpack.json 的 version 变成上游 tag。

> 新仓库的定时 cron 可能不触发，先手动跑一次“激活”。

### 4. NAS 侧加源

1. 官方应用商店 → 手动安装 → 上传 **FnDepot 商店** 的 fpk（装完桌面出现商店图标）
2. 打开 FnDepot → 源管理 → 添加源 → 填 `https://github.com/lianhua/FnDepot`
3. 同步完成 → 应用出现 → 点安装
4. 商店里开启**自动源同步**（或装“任务计划”应用，cron `0 */12 * * *`）
5. GitHub 访问不畅就在商店里配加速地址，如 `https://gh-proxy.com`

## 注意事项

- **上游 release 必须带 .fpk 资产**。只在仓库目录里放 fpk、或挂在第三方页面，workflow 的 assets 查找会失败
- **版本号一致性**：fnpack.json 的 `version` 必须等于上游 release tag（自动去掉 `v` 前缀），否则会反复重复下载
- **展示信息会被覆盖**：`display_name`、`desc`、图标每次同步都从 fpk 内 manifest 重新提取，手填值只在解不出来时保留
- **多架构**：release 里有多个 fpk（x86 / arm）时用 `FPK_MATCH` 筛选；两个都要就加两个 job 各下一个，fnpack.json 用 `arch_diff` 给不同架构不同 download_url（键名以你 NAS 上客户端版本为准）
- **多应用**：每个应用一个 job + fnpack.json 一条 + 仓库一个应用目录（复制 `myapp/` 改名即可）
- **先自测再分发**：安装 → 启动 → 停止 → 卸载 → 重装，完整走一遍再给别人用
