#!/usr/bin/env python3
"""lhg-solopreneur 硬门①：上线发布前跑确定性审计，有 blocker 则拦截。

触发：PreToolUse / Bash。脚本先判断本次 Bash 命令是否包含上线口令
`solo-go-live`（由 /lhg-solopreneur:launch 的最后一步给出，用户确认上线时
在任意命令中带上该口令，例如 `echo solo-go-live`），不是则 0 开销直接放行；
是则运行插件自带的 indie_audit.py。

逃生方式（按推荐度排序）：
  1. 修掉 blocker 后重新发布（推荐）。
  2. 紧急情况：LHG_SOLO_HOOKS_OFF=1 <你的发布命令>（单次豁免本次 hook）。
  3. /plugin disable lhg-solopreneur（整个插件停用，hooks 不再触发）。

设计原则：脚本内部出错（找不到审计脚本、超时等）时 fail-open 直接放行，
不因插件自身故障骚扰用户；真正的门禁在 /lhg-solopreneur:audit。
零第三方依赖。
"""

import json
import os
import re
import subprocess
import sys

AUDIT_TIMEOUT = 60
GO_LIVE_RE = re.compile(r"solo-go-live")


def main() -> int:
    # 逃生开关
    if os.environ.get("LHG_SOLO_HOOKS_OFF") == "1":
        return 0

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # 输入解析失败：fail-open

    tool_input = payload.get("tool_input", {}) or {}
    command = tool_input.get("command", "") or ""

    # 非上线口令：快速放行
    if not GO_LIVE_RE.search(command):
        return 0

    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    audit_script = os.path.join(plugin_root, "scripts", "audit",
                                "indie_audit.py")
    if not os.path.isfile(audit_script):
        return 0  # 审计脚本缺失：fail-open，不拦截用户

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    try:
        proc = subprocess.run(
            [sys.executable, audit_script, "--target", project_dir,
             "--format", "json"],
            capture_output=True,
            text=True,
            timeout=AUDIT_TIMEOUT,
        )
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except Exception:
        return 0  # 脚本失败：fail-open

    blockers = [f for f in data.get("findings", [])
                if f.get("severity") == "blocker"]
    if not blockers:
        return 0

    lines = [
        "上线被 lhg-solopreneur 硬门拦截：审计发现 %d 个 blocker（上线后会出事"
        "的问题），修完再发布。" % len(blockers),
        "",
    ]
    for f in blockers[:10]:
        lines.append(
            "- [%s] %s:%s %s"
            % (f.get("rule_id"), f.get("file"), f.get("line"), f.get("title"))
        )
    if len(blockers) > 10:
        lines.append("…另有 %d 个，完整清单请跑 /lhg-solopreneur:audit"
                     % (len(blockers) - 10))
    lines += [
        "",
        "修复方式：运行 /lhg-solopreneur:audit 按报告逐条修复；",
        "紧急豁免（单次）：LHG_SOLO_HOOKS_OFF=1 <你的发布命令>",
    ]
    reason = "\n".join(lines)

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
