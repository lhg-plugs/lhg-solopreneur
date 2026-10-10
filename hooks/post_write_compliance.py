#!/usr/bin/env python3
"""lhg-solopreneur 硬门②（警告级，不拦截）：写定价/商业文档时，若出现
支付、税务、收入承诺等敏感表述却没有合规声明，提醒补一句通用合规声明。

触发：PostToolUse / Write|Edit。只做提醒，永远 exit 0、不拦截写入。

逃生方式：LHG_SOLO_HOOKS_OFF=1（环境变量）可关闭本提醒；
或 /plugin disable lhg-solopreneur 停用整个插件。
零第三方依赖。
"""

import json
import os
import re
import sys

SENSITIVE_RES = [
    re.compile(r"税务|发票|报税|纳税|公司注册|营业执照"),
    re.compile(r"收款|提现|结算"),
    re.compile(r"月入|年入|躺赚|被动收入|保证.*收入"),
    re.compile(r"订阅|自动续费"),
]
COMPLIANCE_RES = [
    re.compile(r"以当地法规为准|咨询专业人士|非税务建议|不构成法律建议"
               r"|请咨询会计师|请咨询律师|合规"),
    re.compile(r"不构成承诺|因人而异|不保证|仅供参考"),
]


def main() -> int:
    if os.environ.get("LHG_SOLO_HOOKS_OFF") == "1":
        return 0

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or ""
    if not file_path.endswith((".md", ".markdown", ".txt")):
        return 0

    content = tool_input.get("content") or tool_input.get("new_string") or ""
    if not content:
        return 0

    sensitive = any(r.search(content) for r in SENSITIVE_RES)
    if not sensitive:
        return 0
    if any(r.search(content) for r in COMPLIANCE_RES):
        return 0  # 已有合规声明，不提醒

    msg = (
        "合规提醒（lhg-solopreneur）：%s 出现了支付/税务/收入承诺类表述，"
        "但没看到合规声明。\n"
        "建议加一句通用声明，例如：「支付与税务合规因国家/地区而异，"
        "请以当地法规为准，必要时咨询专业人士。」\n"
        "关闭本提醒：export LHG_SOLO_HOOKS_OFF=1（当前会话有效）。"
    ) % file_path
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
