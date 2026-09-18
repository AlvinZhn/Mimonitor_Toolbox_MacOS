#!/usr/bin/env python3
"""通用 CI/CD Webhook 通知与报警推送脚本。

规范与数据格式：
- 读取环境变量 PUSH_WEBHOOK_URL；若未配置则打印日志并安全退出 (exit 0)，绝不中断 CI 流程；
- 仅使用 Python 标准库（urllib.request / json / os / sys / argparse），无第三方依赖；
- 发送 POST application/json 请求，Payload 结构：
  {
    "title": "...",
    "description": "...",
    "content": "..."
  }
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def send_webhook(title: str, description: str, content: str) -> bool:
    webhook_url = os.environ.get("PUSH_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("[NOTIFY] 未配置 PUSH_WEBHOOK_URL 环境变量，安全跳过 Webhook 推送。")
        return True

    payload = {
        "title": title.strip(),
        "description": description.strip(),
        "content": content.strip(),
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Mimonitor-Toolbox-CI-Notifier/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            print(f"[NOTIFY] Webhook 推送成功 (HTTP {status}): {body[:120]}")
            return True
    except urllib.error.HTTPError as exc:
        print(f"[NOTIFY] Webhook 请求返回 HTTP 错误: {exc.code} {exc.reason}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[NOTIFY] Webhook 发送发生网络或其它异常: {exc}", file=sys.stderr)
        return False


def build_release_success_msg(args) -> tuple[str, str, str]:
    ver = args.version or "最新版"
    if not ver.startswith("v") and ver != "最新版":
        ver = f"v{ver}"
    commit = (args.commit or "")[:8]
    rel_url = args.release_url or ""
    run_url = args.run_url or ""

    title = f"【发布成功】Mimonitor Toolbox {ver}"
    desc = "跨平台 Release 产物自动化构建完成"
    content = (
        f"版本号: {ver}\n"
        f"平台架构: macOS (ARM64/Universal DMG) + Windows (x64 Exe / Inno Setup)\n"
        f"关联提交: {commit}\n"
        f"发布地址: {rel_url}\n"
        f"构建日志: {run_url}\n\n"
        f"包含产物清单:\n"
        f"- Mimonitor-Toolbox-{ver}-macOS.dmg\n"
        f"- MonitorToolbox.exe (单文件独立版)\n"
        f"- MonitorToolbox-portable.zip (绿色便携版)\n"
        f"- MonitorToolbox-Setup.exe (安装引导程序)"
    )
    return title, desc, content


def build_build_failure_msg(args) -> tuple[str, str, str]:
    job = args.job or "CI/CD 流水线任务"
    commit = (args.commit or "")[:8]
    ref = args.ref or ""
    run_url = args.run_url or ""
    err = args.error_msg or "编译步骤或测试门禁执行异常"

    title = f"【紧急报警】需人工接入排查：{job} 构建失败"
    desc = "GitHub Actions 流水线异常中断"
    content = (
        f"失败任务: {job}\n"
        f"分支/标签: {ref}\n"
        f"关联提交: {commit}\n"
        f"异常信息: {err}\n"
        f"直达日志: {run_url}\n\n"
        f"⚠️ 请维护者及时前往 GitHub Actions 排查构建日志并定位问题！"
    )
    return title, desc, content


def build_upstream_sync_msg(args) -> tuple[str, str, str]:
    behind = args.behind_count or "多"
    pr_url = args.pr_url or "https://github.com"
    run_url = args.run_url or ""

    title = "【检测到上游原版新更新】"
    desc = "Mimonitor_Toolbox 自动同步"
    content = (
        f"检测到上游原作者仓库 (YiHoooong/Mimonitor_Toolbox:master) 存在新提交 (领先 {behind} 个提交)。\n"
        f"分支已自动抓取上游更新并创建同步 Pull Request：\n"
        f"PR 地址: {pr_url}\n"
        f"工作流运行记录: {run_url}\n\n"
        f"请维护者前往 GitHub 进行代码审查与冲突核验后合并。"
    )
    return title, desc, content


def build_sync_failure_msg(args) -> tuple[str, str, str]:
    err = args.error_msg or "上游代码拉取或合并发生冲突"
    run_url = args.run_url or ""

    title = "【紧急报警】需人工接入排查：上游同步合并冲突告警"
    desc = "自动合并中断"
    content = (
        f"检测到上游有新提交但在自动化拉取或合并时发生冲突或错误，无法自动完成合并。\n"
        f"错误详情: {err}\n"
        f"直达日志: {run_url}\n\n"
        f"⚠️ 请维护者手动执行 git fetch upstream 并人工介入解决代码冲突！"
    )
    return title, desc, content


def main():
    parser = argparse.ArgumentParser(description="Mimonitor Toolbox CI Webhook 通知脚本")
    parser.add_argument(
        "--event",
        choices=["release_success", "build_failure", "upstream_sync", "sync_failure", "custom"],
        default="custom",
        help="通知事件类型",
    )
    parser.add_argument("--version", help="版本号 (如 v3.0.0)")
    parser.add_argument("--commit", help="Commit SHA 哈希")
    parser.add_argument("--ref", help="分支或 Tag 引用名")
    parser.add_argument("--job", help="执行失败的 Job 名称")
    parser.add_argument("--pr-url", help="Pull Request 链接")
    parser.add_argument("--behind-count", help="上游领先提交数")
    parser.add_argument("--run-url", help="GitHub Actions Run 直达链接")
    parser.add_argument("--release-url", help="Release 链接")
    parser.add_argument("--error-msg", help="错误简述")
    parser.add_argument("--title", help="自定义标题")
    parser.add_argument("--description", help="自定义描述")
    parser.add_argument("--content", help="自定义消息正文")

    args = parser.parse_args()

    if args.event == "release_success":
        title, desc, content = build_release_success_msg(args)
    elif args.event == "build_failure":
        title, desc, content = build_build_failure_msg(args)
    elif args.event == "upstream_sync":
        title, desc, content = build_upstream_sync_msg(args)
    elif args.event == "sync_failure":
        title, desc, content = build_sync_failure_msg(args)
    else:
        title = args.title or "【CI 通知】Mimonitor Toolbox"
        desc = args.description or "GitHub Actions 任务提醒"
        content = args.content or "无附加消息正文"

    # 执行发送（严禁抛出异常中断 CI）
    send_webhook(title, desc, content)


if __name__ == "__main__":
    main()
