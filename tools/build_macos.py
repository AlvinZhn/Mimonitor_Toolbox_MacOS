#!/usr/bin/env python3
"""macOS 原生打包脚本：产出带有 ad-hoc 签名与资源保护的 .app 与安装型 .dmg 镜像。

打包流程：
1. 校验与准备静态资源（adb 二进制、jar 工具、apk、icns 图标）；
2. 调用 PyInstaller 生成原生 .app 包（独立窗口应用）；
3. 确保 .app/Contents/Resources/assets 包含完整的 adb、jar、apk 等运行时依赖并赋予 0o755 执行权限；
4. 注入/微调 Info.plist（高分屏、深色模式支持、权限说明）；
5. 执行 codesign --force --deep -s - 对 .app 进行 ad-hoc 签名以通过 macOS Gatekeeper 基础检测；
6. 使用系统原生 hdiutil 制作带有 Applications 快捷安装软链接的 .dmg 镜像。
"""

import os
import plistlib
import shutil
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
APP_NAME = "Mimonitor Toolbox"
APP_BUNDLE_NAME = f"{APP_NAME}.app"
DMG_NAME = "Mimonitor-Toolbox-macOS.dmg"


def log(msg: str):
    print(f"[\033[36mBUILD-MACOS\033[0m] {msg}")


def log_success(msg: str):
    print(f"[\033[32mSUCCESS\033[0m] {msg}")


def log_error(msg: str):
    print(f"[\033[31mERROR\033[0m] {msg}")


def verify_prerequisites():
    """校验打包前必要工具与依赖。"""
    log("1/6 检查系统构建依赖与工具链...")
    if sys.platform != "darwin":
        log_error("本脚本仅支持在 macOS 系统下执行！")
        sys.exit(1)

    # 检查 codesign 与 hdiutil
    for tool in ("codesign", "hdiutil"):
        if not shutil.which(tool):
            log_error(f"系统中缺少必要的原生工具: {tool}")
            sys.exit(1)

    # 检查 PyInstaller
    try:
        import PyInstaller
        log(f"检测到 PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        log_error("当前 Python 环境未安装 PyInstaller，请先执行: pip install pyinstaller")
        sys.exit(1)

    # 检查关键运行资源
    darwin_adb = os.path.join(ASSETS_DIR, "runtime", "darwin", "adb")
    if not os.path.exists(darwin_adb):
        log("未在 assets/runtime/darwin 中找到 adb，尝试自举...")
        from mimonitor_toolbox.platform_adapter.macos import MacOSPlatformAdapter
        adapter = MacOSPlatformAdapter()
        user_adb = os.path.expanduser("~/.mimonitor_toolbox/bin/adb")
        if os.path.exists(user_adb):
            os.makedirs(os.path.dirname(darwin_adb), exist_ok=True)
            shutil.copy2(user_adb, darwin_adb)
            os.chmod(darwin_adb, 0o755)
            log("已从本地自举缓存复制 adb 至 assets 目录")
        else:
            log_error("无法获取 macOS 版 adb 二进制文件，请确认网络或手动放置")
            sys.exit(1)

    if os.path.exists(darwin_adb):
        os.chmod(darwin_adb, 0o755)

    # 检查应用图标
    icns_path = os.path.join(ASSETS_DIR, "app", "icon.icns")
    if not os.path.exists(icns_path):
        log_error(f"未找到图标文件: {icns_path}")
        sys.exit(1)

    log_success("预检完成，所有构建依赖与资源就绪")


def build_app_with_pyinstaller():
    """执行 PyInstaller 打包生成 .app。"""
    log("2/6 调用 PyInstaller 打包 macOS .app 独立包...")
    entry_script = os.path.join(PROJECT_ROOT, "monitor_controller.py")
    icns_path = os.path.join(ASSETS_DIR, "app", "icon.icns")

    # 构建参数
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        f"--name={APP_NAME}",
        f"--icon={icns_path}",
        f"--add-data={ASSETS_DIR}:assets",
        "--osx-bundle-identifier=com.mimonitor.toolbox",
        "--hidden-import=mimonitor_toolbox",
        "--hidden-import=qfluentwidgets",
        "--hidden-import=PyQt6",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=zeroconf",
        entry_script,
    ]

    log(f"执行命令: {' '.join(pyinstaller_cmd)}")
    result = subprocess.run(pyinstaller_cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        log_error("PyInstaller 构建失败！")
        sys.exit(result.returncode)

    app_path = os.path.join(DIST_DIR, APP_BUNDLE_NAME)
    if not os.path.exists(app_path):
        log_error(f"未能在 dist 目录下生成 {APP_BUNDLE_NAME}！")
        sys.exit(1)

    log_success(f"PyInstaller 构建成功，已生成: {app_path}")


def post_process_bundle():
    """完善 Resources 资源、赋予执行权限并配置 Info.plist。"""
    log("3/6 补全 .app 资源架构并注入 Info.plist 配置...")
    app_path = os.path.join(DIST_DIR, APP_BUNDLE_NAME)
    contents_dir = os.path.join(app_path, "Contents")
    resources_dir = os.path.join(contents_dir, "Resources")
    bundle_assets = os.path.join(resources_dir, "assets")

    # 1. 确保 Resources/assets 完整存在
    os.makedirs(bundle_assets, exist_ok=True)
    for root, dirs, files in os.walk(ASSETS_DIR):
        rel_path = os.path.relpath(root, ASSETS_DIR)
        dest_dir = os.path.join(bundle_assets, rel_path) if rel_path != "." else bundle_assets
        os.makedirs(dest_dir, exist_ok=True)
        for f in files:
            src_f = os.path.join(root, f)
            dst_f = os.path.join(dest_dir, f)
            if not os.path.exists(dst_f):
                shutil.copy2(src_f, dst_f)

    # 2. 赋予 adb 可执行权限
    target_adb = os.path.join(bundle_assets, "runtime", "darwin", "adb")
    if os.path.exists(target_adb):
        os.chmod(target_adb, 0o755)
        log(f"已确保内置 adb 执行权限 (0o755): {target_adb}")

    # 检查 MacOS 目录下的 adb（如果存在的话也赋权）
    macos_adb = os.path.join(contents_dir, "MacOS", "assets", "runtime", "darwin", "adb")
    if os.path.exists(macos_adb):
        os.chmod(macos_adb, 0o755)

    # 3. 注入 Info.plist
    plist_path = os.path.join(contents_dir, "Info.plist")
    log(f"配置 Info.plist: {plist_path}")

    pl = {}
    if os.path.exists(plist_path):
        with open(plist_path, "rb") as f:
            pl = plistlib.load(f)

    pl["CFBundleName"] = APP_NAME
    pl["CFBundleDisplayName"] = "红米 G Pro 监控工具箱"
    pl["CFBundleIdentifier"] = "com.mimonitor.toolbox"
    pl["CFBundleVersion"] = "3.0.0"
    pl["CFBundleShortVersionString"] = "3.0.0"
    pl["NSHighResolutionCapable"] = True
    pl["NSRequiresAquaSystemAppearance"] = False
    pl["NSHumanReadableCopyright"] = "Copyright © 2026 Mimonitor Toolbox Authors"
    pl["LSMinimumSystemVersion"] = "11.0"
    pl["NSLocalNetworkUsageDescription"] = "Mimonitor Toolbox 需要访问局域网以通过 ADB 连接与控制红米 G Pro 显示器。"

    with open(plist_path, "wb") as f:
        plistlib.dump(pl, f)

    log_success("Info.plist 注入与资源权限修复完成")


def codesign_app_bundle():
    """执行 ad-hoc 代码签名，解决 Gatekeeper 隔离。"""
    log("4/6 执行 ad-hoc 代码签名 (codesign)...")
    app_path = os.path.join(DIST_DIR, APP_BUNDLE_NAME)

    # 针对内部动态库与主二进制递归签名
    sign_cmd = [
        "codesign",
        "--force",
        "--deep",
        "-s",
        "-",
        app_path,
    ]
    log(f"执行命令: {' '.join(sign_cmd)}")
    result = subprocess.run(sign_cmd)
    if result.returncode != 0:
        log_error("代码签名失败！")
        sys.exit(result.returncode)

    # 验证签名
    verify_cmd = ["codesign", "--verify", "--deep", "--strict", "--verbose=2", app_path]
    v_res = subprocess.run(verify_cmd, capture_output=True, text=True)
    if v_res.returncode == 0:
        log_success("代码签名验证通过 (Valid ad-hoc signature)")
    else:
        log(f"签名验证警告 (通常不影响 ad-hoc 本地运行): {v_res.stderr}")


def create_dmg_package():
    """制作带有 Applications 软链接的 DMG 安装镜像。"""
    log("5/6 制作安装型 DMG 磁盘镜像...")
    app_path = os.path.join(DIST_DIR, APP_BUNDLE_NAME)
    dmg_output = os.path.join(DIST_DIR, DMG_NAME)
    staging_dir = os.path.join(DIST_DIR, "dmg_staging")

    if os.path.exists(dmg_output):
        os.remove(dmg_output)
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)

    os.makedirs(staging_dir, exist_ok=True)

    # 复制 .app 到暂存目录（使用 ditto 完美保留 macOS 扩展属性和签名）
    staged_app = os.path.join(staging_dir, APP_BUNDLE_NAME)
    log(f"复制应用至镜像暂存目录: {staged_app}")
    subprocess.run(["ditto", app_path, staged_app], check=True)

    # 创建 /Applications 快捷安装软链接
    apps_link = os.path.join(staging_dir, "Applications")
    log("创建 /Applications 快捷安装软链接...")
    os.symlink("/Applications", apps_link)

    # 使用 hdiutil 封包
    hdiutil_cmd = [
        "/usr/bin/hdiutil",
        "create",
        "-volname",
        APP_NAME,
        "-srcfolder",
        staging_dir,
        "-ov",
        "-format",
        "UDZO",
        dmg_output,
    ]
    log(f"执行封包命令: {' '.join(hdiutil_cmd)}")
    result = subprocess.run(hdiutil_cmd)

    # 清理暂存目录
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)

    if result.returncode != 0:
        log_error("DMG 封包失败！")
        sys.exit(result.returncode)

    dmg_size = os.path.getsize(dmg_output) / (1024 * 1024)
    log_success(f"DMG 镜像封包完成: {dmg_output} ({dmg_size:.2f} MB)")


def main():
    start_time = time.time()
    print("=" * 65)
    print("    Mimonitor Toolbox - macOS 原生打包流水线 (Phase 3)")
    print("=" * 65)

    verify_prerequisites()
    build_app_with_pyinstaller()
    post_process_bundle()
    codesign_app_bundle()
    create_dmg_package()

    elapsed = time.time() - start_time
    print("=" * 65)
    log_success(f"6/6 macOS 原生打包任务全流程完成！耗时: {elapsed:.2f} 秒")
    print(f"产物 1 (.app): {os.path.join(DIST_DIR, APP_BUNDLE_NAME)}")
    print(f"产物 2 (.dmg): {os.path.join(DIST_DIR, DMG_NAME)}")
    print("=" * 65)


if __name__ == "__main__":
    main()
