#!/usr/bin/env python3
"""
FnDepot 源同步脚本

从 sources.json 读取每个应用的上游仓库，按 release 下载各架构 fpk，
解包 manifest 提取元数据，计算 sha256，更新 fnpack.json（V2 格式）。

设计要点：
- 上游映射放在 sources.json，fnpack.json 保持纯 V2 规范（避免自定义字段引起校验问题）
- 只保留每个应用的最新版本安装包，仓库不会无限膨胀
- 幂等：版本一致则跳过；下载/校验失败则抛错退出，不写入半成品
"""
import hashlib
import json
import os
import re
import sys
import tarfile
import urllib.request

API = "https://api.github.com/repos/{repo}/releases/latest"
RAW_BASE = os.environ.get(
    "RAW_BASE", "https://raw.githubusercontent.com/lianhua/FnDepot/main"
)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fndepot-sync"})
    # GitHub API 请求带认证（未认证限 60 次/小时）；release 资产下载是重定向直链，不带
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def parse_version(tag: str) -> str:
    """从 tag 提取纯版本号，如 v1.2.17.7 -> 1.2.17.7"""
    m = re.search(r"\d+(?:\.\d+)*", tag)
    if not m:
        raise ValueError(f"无法从 tag 解析版本号: {tag}")
    return m.group(0)


def read_manifest(fpk_path: str):
    """从 fpk 中提取 manifest 字典和两个图标"""
    meta, icons = {}, {}
    with tarfile.open(fpk_path, "r:gz") as t:
        f = t.extractfile("manifest")
        if f is None:
            raise ValueError("fpk 内没有 manifest")
        for line in f.read().decode("utf-8", "replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                meta[k.strip()] = v.strip()
        for icon in ("ICON.PNG", "ICON_256.PNG"):
            f = t.extractfile(icon)
            if f:
                icons[icon] = f.read()
    return meta, icons


def find_asset(rel: dict, app_id: str, ver: str, arch: str, cfg: dict):
    """按上游资产文件名模板找下载链接。

    不同上游包名格式不一致，用 asset_name 模板描述（占位符 {ver}/{arch}）。
    未配置时默认 {app_id}-{ver}-{arch}.fpk（与 lemon-music 等通用命名一致）。
    """
    pattern = cfg.get("asset_name", "{app_id}-{ver}-{arch}.fpk")
    target = pattern.format(app_id=app_id, ver=ver, arch=arch)
    for a in rel.get("assets", []):
        if a["name"] == target:
            return a["browser_download_url"], target
    return None, target


def sync_app(app_id: str, cfg: dict, index: dict) -> bool:
    """同步单个应用，返回是否发生变更"""
    repo = cfg["repo"]
    archs = cfg.get("archs", ["x86"])
    print(f"=== {app_id} <- {repo} ===")

    rel = json.loads(fetch(API.format(repo=repo)).decode("utf-8"))
    ver = parse_version(rel["tag_name"])
    node = index["apps"].get(app_id)
    if node is None:
        print(f"  fnpack.json 中没有 {app_id} 条目，跳过")
        return False
    current = list(node.get("releases", {}).keys())
    if current == [ver]:
        print(f"  已是最新版本 {ver}，跳过")
        return False

    # 每个应用一个顶层目录（目录名 = 应用 ID），路径用纯正斜杠拼接，
    # 避免 Windows 上 os.path.join 产生反斜杠污染 fnpack.json 的 URL
    app_assets = app_id
    os.makedirs(app_assets, exist_ok=True)
    packages, sample = {}, None
    for arch in archs:
        url, target = find_asset(rel, app_id, ver, arch, cfg)
        if not url:
            print(f"  [{arch}] 上游 release 没有匹配资产（期望文件名 {target}）")
            continue
        data = fetch(url)
        path = f"{app_assets}/{app_id}-{ver}-{arch}.fpk"
        with open(path, "wb") as f:
            f.write(data)
        packages[arch] = {
            "download_url": f"{RAW_BASE}/{path}",
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }
        print(f"  [{arch}] {len(data):,} bytes  sha256={packages[arch]['sha256'][:16]}...")
        if sample is None:
            sample = path

    if not packages:
        raise RuntimeError(f"{app_id}: 没有下载到任何架构的 fpk，请检查 arches 配置")

    meta, icons = read_manifest(sample)
    for name, data in icons.items():
        with open(f"{app_assets}/{name}", "wb") as f:
            f.write(data)

    # manifest 里的 appname 是 fnOS 实际注册的应用 ID；索引键名是我们给源的命名。
    # 多数上游两者相同（如 lemon-music），但 workbuddy-fnos 内部叫 fnwb.workbuddy。
    # 这里不再硬卡（否则直接跳过该应用），改为提示，由分发者决定是否统一。
    if meta.get("appname", app_id) != app_id:
        print(f"  [提示] fpk 内部 appname={meta.get('appname')} 与索引键名 {app_id} 不同"
              f" —— fnOS 将以 {meta.get('appname')} 注册，源内显示为 {app_id}")

    node["display_name"] = meta.get("display_name", node.get("display_name", ""))
    if meta.get("desc"):
        node["desc"] = " ".join(meta["desc"].split())
    node["service_port"] = meta.get("service_port", "")
    node["os_min_version"] = meta.get("os_min_version", "")
    node["icon_url"] = f"{RAW_BASE}/{app_assets}/ICON.PNG"
    node["releases"] = {
        ver: {
            "updated_at": rel.get("published_at", ""),
            "os_min_version": meta.get("os_min_version", ""),
            "packages": packages,
        }
    }
    print(f"  版本更新: {'/'.join(current) or '无'} -> {ver}")

    # 清理本应用的旧版本包（每个应用在自己的子目录里清理，互不干扰）
    keep = {f"{app_id}-{ver}-{arch}.fpk" for arch in packages}
    for fn in sorted(os.listdir(app_assets)):
        if fn.endswith(".fpk") and fn not in keep:
            os.remove(os.path.join(app_assets, fn))
            print(f"  清理旧包: {fn}")
    return True


def main() -> int:
    os.chdir(ROOT)
    with open("sources.json", encoding="utf-8") as f:
        sources = json.load(f)
    with open("fnpack.json", encoding="utf-8") as f:
        index = json.load(f)

    changed = False
    for app_id, cfg in sources["apps"].items():
        try:
            changed |= sync_app(app_id, cfg, index)
        except Exception as e:                      # 单个应用失败不影响其他
            print(f"!! {app_id} 同步失败: {e}", file=sys.stderr)

    if changed:
        with open("fnpack.json", "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        print("fnpack.json 已更新")
    else:
        print("无需变更")
    return 0


if __name__ == "__main__":
    sys.exit(main())
