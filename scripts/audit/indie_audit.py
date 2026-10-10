#!/usr/bin/env python3
"""lhg-solopreneur 确定性独立开发审计：45 条规则，零第三方依赖。

扫描目标目录中的 Markdown 文档（约定文件名：mvp.md / pricing.md / launch.md，
或标题含"mvp/范围/定价/冷启动/上线"），检查 MVP 范围完整性、定价页必备要素、
冷启动素材清单、TODO 残留、支付/税务合规声明；输出 JSON 与人类可读报告；
有 blocker 时以 exit code 2 退出（供 hooks 与 CI 使用）。

用法：
    python3 indie_audit.py --target <目录> [--format json|text] [--fail-on blocker|warning|nit]

规则文案均为本项目原创（"独立开发一人公司从想法到冷启动"的方法论思路受
whawkinsiv/solo-founder-superpowers、wasp-lang/open-saas、latent-spaces/brag
等开源项目启发，未复制任何第三方原文案与代码；详见仓库 ATTRIBUTION.md）。
"""

import argparse
import json
import os
import re
import sys

VERSION = "1.0.0"
TOOL = "lhg-solopreneur/indie-audit"

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", "dist", "build", "vendor",
    ".claude-plugin", "scripts", "hooks", "fixtures",
}
SCAN_EXTS = {".md", ".markdown", ".txt"}

PLACEHOLDERS = ("TODO", "TBD", "XXX", "待填", "待补充", "[待", "lorem", "Lorem",
                "{{", "}}")
# 合规声明：出现即视为已尽提醒义务的表述
COMPLIANCE_PHRASES = ("以当地法规为准", "咨询专业人士", "非税务建议",
                      "不构成法律建议", "请咨询会计师", "请咨询律师", "合规")
INCOME_DISCLAIMERS = ("不构成承诺", "因人而异", "结果因人而异", "不保证",
                      "仅供参考", "历史不代表未来")


class Finding:
    __slots__ = ("rule_id", "severity", "category", "title", "file", "line",
                 "snippet", "detail")

    def __init__(self, rule_id, severity, category, title, file, line,
                 snippet, detail):
        self.rule_id = rule_id
        self.severity = severity
        self.category = category
        self.title = title
        self.file = file
        self.line = line
        self.snippet = snippet
        self.detail = detail

    def to_dict(self):
        return {
            "rule_id": self.rule_id, "severity": self.severity,
            "category": self.category, "title": self.title,
            "file": self.file, "line": self.line,
            "snippet": self.snippet, "detail": self.detail,
        }


def collect_files(target):
    out = []
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            _, ext = os.path.splitext(f)
            if ext.lower() in SCAN_EXTS:
                out.append(os.path.join(root, f))
    return sorted(out)


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def doc_kind(path, text):
    """识别文档类型：mvp / pricing / launch / other。"""
    base = os.path.basename(path).lower()
    head = "\n".join(text.split("\n")[:5])
    if "mvp" in base or "范围" in head or "MVP" in head:
        return "mvp"
    if "pricing" in base or "定价" in head:
        return "pricing"
    if "launch" in base or "冷启动" in head or "上线" in head:
        return "launch"
    return "other"


RULES = []
_RULE_BY_ID = {}


def rule(rule_id, severity, category, title, detail):
    def deco(fn):
        r = {"id": rule_id, "severity": severity, "category": category,
             "title": title, "detail": detail}
        _RULE_BY_ID[rule_id] = r
        r["check"] = fn
        RULES.append(r)
        return fn
    return deco


def _mk(rule_id, path, line, snippet):
    r = _RULE_BY_ID[rule_id]
    return Finding(r["id"], r["severity"], r["category"], r["title"],
                   path, line, snippet[:160], r["detail"])


def _line_hits(rule_id, lines, text, path, pattern, flags=0):
    rx = re.compile(pattern, flags)
    return [_mk(rule_id, path, i + 1, lines[i].strip())
            for i, ln in enumerate(lines) if rx.search(ln)]


def _doc_hits(rule_id, docs, kinds, pattern, flags=0):
    """在指定类型文档全文中找命中（每文档至多一条）。"""
    rx = re.compile(pattern, flags)
    hits = []
    for kind, path, text, lines in docs:
        if kind in kinds and rx.search(text):
            m = rx.search(text)
            ln = text[:m.start()].count("\n") + 1
            hits.append(_mk(rule_id, path, ln, m.group(0)))
    return hits


def _missing_doc(rule_id, docs, kinds):
    if not any(k in kinds for k, _, _, _ in docs):
        return [_mk(rule_id, "<target>", 0,
                     "未找到 %s 文档" % "/".join(kinds))]
    return []


# ================================================================ MVP 范围

@rule("SOLO-MVP-001", "blocker", "MVP范围", "缺 MVP 范围文档",
      "约定文件名含 mvp（如 mvp.md），或标题含「MVP/范围」。没有范围文档，"
      "2 周上线就是空话。")
def r_mvp_001(lines, text, path, ctx):
    return _missing_doc("SOLO-MVP-001", ctx["docs"], ("mvp",))


@rule("SOLO-MVP-002", "blocker", "MVP范围", "无「不做/二期」清单",
      "MVP 文档没有明确的不做清单（不做/二期/砍掉/延后/v2/范围外），"
      "范围蔓延几乎必然发生。")
def r_mvp_002(lines, text, path, ctx):
    mvp_docs = [d for d in ctx["docs"] if d[0] == "mvp"]
    if not mvp_docs:
        return []
    if _doc_hits("SOLO-MVP-002", ctx["docs"], ("mvp",),
                 r"不做|二期|砍掉|延后|\bv2\b|未来再做|范围外|明确不做"):
        return []
    _, p, t, _ = mvp_docs[0]
    return [_mk("SOLO-MVP-002", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-MVP-003", "blocker", "MVP范围", "TODO/占位符残留",
      "文档中还有 TODO/TBD/XXX/待填/待补充/lorem 等占位符，说明范围还没定稿。")
def r_mvp_003(lines, text, path, ctx):
    hits = []
    for kind, p, t, lns in ctx["docs"]:
        if kind != "mvp":
            continue
        for pat in PLACEHOLDERS:
            hits += _line_hits("SOLO-MVP-003", lns, t, p, re.escape(pat))
    return hits


@rule("SOLO-MVP-004", "warning", "MVP范围", "功能未分优先级",
      "功能清单没有 P0/P1/优先级/核心/必做分级，一人公司容易眉毛胡子一把抓。")
def r_mvp_004(lines, text, path, ctx):
    if not any(k == "mvp" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-MVP-004", ctx["docs"], ("mvp",),
                 r"P0|P1|优先级|核心功能|必做|首先|第一批"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "mvp")
    return [_mk("SOLO-MVP-004", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-MVP-005", "warning", "MVP范围", "无工期/上线时间",
      "没有 2 周倒排的工期（周/天/里程碑/上线日期），MVP 容易无限延期。")
def r_mvp_005(lines, text, path, ctx):
    if not any(k == "mvp" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-MVP-005", ctx["docs"], ("mvp",),
                 r"第\d+[周天]|里程碑|上线日期|截止|两周|2周|倒排"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "mvp")
    return [_mk("SOLO-MVP-005", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-MVP-006", "warning", "MVP范围", "缺验收标准",
      "没有验收标准（验收/完成标准/Definition of Done），不知道什么算做完。")
def r_mvp_006(lines, text, path, ctx):
    if not any(k == "mvp" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-MVP-006", ctx["docs"], ("mvp",),
                 r"验收|完成标准|Definition of Done|\bDoD\b|算做完"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "mvp")
    return [_mk("SOLO-MVP-006", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-MVP-007", "warning", "MVP范围", "缺目标用户一句话",
      "没有一句话讲清目标用户（目标用户/用户画像/谁用），产品容易做给空气看。")
def r_mvp_007(lines, text, path, ctx):
    if not any(k == "mvp" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-MVP-007", ctx["docs"], ("mvp",),
                 r"目标用户|用户画像|谁用|面向.*用户|给.*用的"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "mvp")
    return [_mk("SOLO-MVP-007", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-MVP-008", "warning", "MVP范围", "缺成功指标",
      "没有成功指标（指标/转化/留存/DAU/北极星），上线后不知道算不算成。")
def r_mvp_008(lines, text, path, ctx):
    if not any(k == "mvp" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-MVP-008", ctx["docs"], ("mvp",),
                 r"指标|转化率|留存|DAU|北极星|成功标准"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "mvp")
    return [_mk("SOLO-MVP-008", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-MVP-009", "warning", "MVP范围", "缺风险/依赖项",
      "没有风险与依赖（风险/依赖/阻塞/卡点），一人公司最怕单点卡死无人替。")
def r_mvp_009(lines, text, path, ctx):
    if not any(k == "mvp" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-MVP-009", ctx["docs"], ("mvp",),
                 r"风险|依赖|阻塞|卡点|单点"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "mvp")
    return [_mk("SOLO-MVP-009", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-MVP-010", "nit", "MVP范围", "MVP 文档过薄",
      "MVP 文档不足 30 行，信息量可能不够支撑一次 2 周冲刺。")
def r_mvp_010(lines, text, path, ctx):
    for kind, p, t, lns in ctx["docs"]:
        if kind == "mvp" and len(lns) < 30:
            return [_mk("SOLO-MVP-010", p, 1, "共 %d 行" % len(lns))]
    return []


# ================================================================ 定价

@rule("SOLO-PRC-001", "blocker", "定价", "缺定价文档",
      "约定文件名含 pricing/定价（如 pricing.md）。定价是独立开发的生命线，"
      "不能拍脑袋。")
def r_prc_001(lines, text, path, ctx):
    return _missing_doc("SOLO-PRC-001", ctx["docs"], ("pricing",))


@rule("SOLO-PRC-002", "blocker", "定价", "无具体价格数字",
      "定价文档里没有具体价格（¥/$/元+数字），等于没定价。")
def r_prc_002(lines, text, path, ctx):
    if not any(k == "pricing" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-PRC-002", ctx["docs"], ("pricing",),
                 r"[¥$]\s*\d|\d+\s*元|USD\s*\d|美元\s*\d"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "pricing")
    return [_mk("SOLO-PRC-002", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-PRC-003", "blocker", "定价", "订阅制未声明可随时取消",
      "提到订阅/月付/年付/包月却没写「可随时取消」，这是订阅产品最基本的"
      "信任条款，缺失会引发退款纠纷。")
def r_prc_003(lines, text, path, ctx):
    hits = []
    for kind, p, t, lns in ctx["docs"]:
        if kind != "pricing":
            continue
        if re.search(r"订阅|月付|年付|包月|按月|按年", t) and \
                not re.search(r"取消|随时退订", t):
            hits.append(_mk("SOLO-PRC-003", p, 1, "订阅制缺取消条款"))
    return hits


@rule("SOLO-PRC-004", "blocker", "定价", "无退款政策",
      "定价文档没写退款政策（退款/无理由），付费转化和纠纷处理都会吃亏。")
def r_prc_004(lines, text, path, ctx):
    if not any(k == "pricing" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-PRC-004", ctx["docs"], ("pricing",),
                 r"退款|无理由|退款政策"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "pricing")
    return [_mk("SOLO-PRC-004", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-PRC-005", "warning", "定价", "单一定价档无对比锚定",
      "只有一个价格且无对比/推荐/最受欢迎等锚定，用户缺乏决策参照。")
def r_prc_005(lines, text, path, ctx):
    for kind, p, t, lns in ctx["docs"]:
        if kind != "pricing":
            continue
        prices = re.findall(r"[¥$]\s*\d+|\d+\s*元", t)
        if len(set(prices)) <= 1 and \
                not re.search(r"对比|推荐|最受欢迎|锚定|两档|三档|套餐", t):
            return [_mk("SOLO-PRC-005", p, 1, "仅一档价格且无锚定")]
    return []


@rule("SOLO-PRC-006", "warning", "定价", "缺免费档/试用说明",
      "没有免费版或试用（免费/试用/trial），冷启动获客会少一个低门槛入口。")
def r_prc_006(lines, text, path, ctx):
    if not any(k == "pricing" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-PRC-006", ctx["docs"], ("pricing",),
                 r"免费|试用|\btrial\b|免费版|体验版"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "pricing")
    return [_mk("SOLO-PRC-006", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-PRC-007", "warning", "定价", "缺目标人群说明",
      "定价没写清楚适合谁（适合/目标用户/谁适合），用户会对号入座困难。")
def r_prc_007(lines, text, path, ctx):
    if not any(k == "pricing" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-PRC-007", ctx["docs"], ("pricing",),
                 r"适合|目标用户|谁适合|面向"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "pricing")
    return [_mk("SOLO-PRC-007", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-PRC-008", "warning", "定价", "缺支付方式说明",
      "没写支付方式（支付/付款/信用卡/支付宝/微信支付/Stripe/PayPal），"
      "用户会担心付不了款。")
def r_prc_008(lines, text, path, ctx):
    if not any(k == "pricing" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-PRC-008", ctx["docs"], ("pricing",),
                 r"支付|付款|信用卡|支付宝|微信支付|Stripe|PayPal"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "pricing")
    return [_mk("SOLO-PRC-008", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-PRC-009", "warning", "定价", "缺竞品对标",
      "定价没有竞品对标（竞品/对标/同类产品），价格是贵是便宜没有参照系。")
def r_prc_009(lines, text, path, ctx):
    if not any(k == "pricing" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-PRC-009", ctx["docs"], ("pricing",),
                 r"竞品|对标|同类产品|市面"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "pricing")
    return [_mk("SOLO-PRC-009", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-PRC-010", "nit", "定价", "定价页缺 FAQ",
      "定价页没有 FAQ/常见问题，用户下单前的疑虑没地方消除。")
def r_prc_010(lines, text, path, ctx):
    if not any(k == "pricing" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-PRC-010", ctx["docs"], ("pricing",), r"FAQ|常见问题"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "pricing")
    return [_mk("SOLO-PRC-010", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-PRC-011", "warning", "定价", "价格未标计费周期",
      "有价格数字但没写计费周期（/月//年/月付/年付/一次性/买断），用户会困惑。")
def r_prc_011(lines, text, path, ctx):
    for kind, p, t, lns in ctx["docs"]:
        if kind != "pricing":
            continue
        if re.search(r"[¥$]\s*\d|\d+\s*元", t) and \
                not re.search(r"/月|/年|月付|年付|一次性|买断|终身|per month|/mo", t):
            return [_mk("SOLO-PRC-011", p, 1, "价格缺计费周期")]
    return []


@rule("SOLO-PRC-012", "warning", "定价", "自动续费未说明",
      "提到自动续费却没写续费提醒/到期通知，用户被「背刺」续费会引发投诉。")
def r_prc_012(lines, text, path, ctx):
    for kind, p, t, lns in ctx["docs"]:
        if kind != "pricing":
            continue
        if re.search(r"自动续费", t) and \
                not re.search(r"续费提醒|到期通知|续费说明|提前.*通知", t):
            return [_mk("SOLO-PRC-012", p, 1, "自动续费缺提醒说明")]
    return []


# ================================================================ 合规

def _has_compliance(t):
    return any(p in t for p in COMPLIANCE_PHRASES)


@rule("SOLO-CMP-001", "blocker", "合规", "税务/注册表述缺合规声明",
      "文档提到税务/发票/公司/注册/营业执照，却没有任何「以当地法规为准」/"
      "「咨询专业人士」类合规声明。本插件只给通用框架，不做具体税务法律建议。")
def r_cmp_001(lines, text, path, ctx):
    hits = []
    for kind, p, t, lns in ctx["docs"]:
        if re.search(r"税务|发票|公司注册|营业执照|报税|纳税", t) and \
                not _has_compliance(t):
            hits.append(_mk("SOLO-CMP-001", p, 1, "涉税务/注册表述无合规声明"))
    return hits


@rule("SOLO-CMP-002", "blocker", "合规", "支付/收款表述缺合规提醒",
      "文档提到支付/收款/提现/结算，却没有支付合规提醒。支付合规因国家而异，"
      "须以当地法规为准。")
def r_cmp_002(lines, text, path, ctx):
    hits = []
    for kind, p, t, lns in ctx["docs"]:
        if re.search(r"收款|提现|结算|资金.*账户", t) and \
                not _has_compliance(t):
            hits.append(_mk("SOLO-CMP-002", p, 1, "涉支付/收款表述无合规提醒"))
    return hits


@rule("SOLO-CMP-003", "blocker", "合规", "收入承诺缺免责说明",
      "出现月入/年入/躺赚/被动收入/保证收入等表述，却无「不构成承诺」/"
      "「因人而异」类免责说明，容易构成误导。")
def r_cmp_003(lines, text, path, ctx):
    hits = []
    for kind, p, t, lns in ctx["docs"]:
        if re.search(r"月入|年入|躺赚|被动收入|保证.*收入|\d+\s*万.*收入", t) and \
                not any(p in t for p in INCOME_DISCLAIMERS):
            hits.append(_mk("SOLO-CMP-003", p, 1, "收入表述无免责说明"))
    return hits


@rule("SOLO-CMP-004", "warning", "合规", "订阅自动续费缺到期提示",
      "订阅制文档提到自动续费但没写到期/续费提示，用户体验与合规都有风险。")
def r_cmp_004(lines, text, path, ctx):
    # 与 PRC-012 同源但面向全部文档；为避免重复计分，仅在非 pricing 文档触发
    hits = []
    for kind, p, t, lns in ctx["docs"]:
        if kind == "pricing":
            continue
        if re.search(r"自动续费", t) and \
                not re.search(r"续费提醒|到期通知|续费说明", t):
            hits.append(_mk("SOLO-CMP-004", p, 1, "自动续费缺到期提示"))
    return hits


@rule("SOLO-CMP-005", "warning", "合规", "收集用户数据缺隐私说明",
      "提到收集用户数据/邮箱/手机号/隐私，却没有隐私说明，用户信任会打折。")
def r_cmp_005(lines, text, path, ctx):
    hits = []
    for kind, p, t, lns in ctx["docs"]:
        if re.search(r"用户数据|收集.*邮箱|手机号|隐私", t) and \
                not re.search(r"隐私|数据安全|不会.*泄露|加密存储", t):
            hits.append(_mk("SOLO-CMP-005", p, 1, "涉用户数据无隐私说明"))
    return hits


@rule("SOLO-CMP-006", "nit", "合规", "全文档无「合规」二字",
      "整套文档没有任何合规相关表述，建议至少加一句通用合规声明。")
def r_cmp_006(lines, text, path, ctx):
    all_text = "\n".join(t for _, _, t, _ in ctx["docs"])
    if ctx["docs"] and not _has_compliance(all_text):
        return [_mk("SOLO-CMP-006", "<target>", 0, "无合规表述")]
    return []


# ================================================================ 冷启动

@rule("SOLO-LCH-001", "blocker", "冷启动", "缺冷启动文档",
      "约定文件名含 launch/冷启动（如 launch.md）。没有冷启动计划，"
      "产品上线等于裸奔。")
def r_lch_001(lines, text, path, ctx):
    return _missing_doc("SOLO-LCH-001", ctx["docs"], ("launch",))


@rule("SOLO-LCH-002", "warning", "冷启动", "无社媒文案",
      "冷启动文档没有推文/社媒文案（推文/社媒/X /微博/thread），"
      "上线当天没有可直接发的弹药。")
def r_lch_002(lines, text, path, ctx):
    if not any(k == "launch" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-LCH-002", ctx["docs"], ("launch",),
                 r"推文|社媒|X\s|微博|thread|朋友圈"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "launch")
    return [_mk("SOLO-LCH-002", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-LCH-003", "warning", "冷启动", "无 Product Hunt 文案",
      "没有 Product Hunt 发布文案，出海冷启动少了一个高权重渠道。")
def r_lch_003(lines, text, path, ctx):
    if not any(k == "launch" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-LCH-003", ctx["docs"], ("launch",),
                 r"Product Hunt|ProductHunt|\bPH\b"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "launch")
    return [_mk("SOLO-LCH-003", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-LCH-004", "warning", "冷启动", "落地页大纲缺 CTA",
      "落地页大纲没有行动号召（CTA/立即/免费开始/开始使用/注册），"
      "流量来了也接不住。")
def r_lch_004(lines, text, path, ctx):
    if not any(k == "launch" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-LCH-004", ctx["docs"], ("launch",),
                 r"CTA|立即|免费开始|开始使用|注册|预约|购买"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "launch")
    return [_mk("SOLO-LCH-004", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-LCH-005", "warning", "冷启动", "缺上线首日清单",
      "没有上线首日执行清单（首日/上线当天/checklist），上线当天容易手忙脚乱。")
def r_lch_005(lines, text, path, ctx):
    if not any(k == "launch" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-LCH-005", ctx["docs"], ("launch",),
                 r"首日|上线当天|checklist|执行清单|时间表"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "launch")
    return [_mk("SOLO-LCH-005", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-LCH-006", "warning", "冷启动", "缺评论区预置回复/FAQ",
      "没有评论区预置回复或 FAQ（评论/回复话术/FAQ/常见问题），"
      "上线后的第一波提问会措手不及。")
def r_lch_006(lines, text, path, ctx):
    if not any(k == "launch" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-LCH-006", ctx["docs"], ("launch",),
                 r"评论|回复话术|FAQ|常见问题"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "launch")
    return [_mk("SOLO-LCH-006", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-LCH-007", "warning", "冷启动", "缺 7 天运营/复盘计划",
      "没有上线后 7 天运营与复盘计划（复盘/第N天/运营计划/数据回收），"
      "冷启动容易「上线即巅峰」。")
def r_lch_007(lines, text, path, ctx):
    if not any(k == "launch" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-LCH-007", ctx["docs"], ("launch",),
                 r"复盘|第\d+天|运营计划|数据回收|留存"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "launch")
    return [_mk("SOLO-LCH-007", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-LCH-008", "nit", "冷启动", "缺多渠道分发清单",
      "没有多渠道分发清单（渠道/Reddit/V2EX/即刻/Hacker News/分发），"
      "别把鸡蛋放在一个渠道里。")
def r_lch_008(lines, text, path, ctx):
    if not any(k == "launch" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-LCH-008", ctx["docs"], ("launch",),
                 r"渠道|Reddit|V2EX|即刻|Hacker News|分发|社区"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "launch")
    return [_mk("SOLO-LCH-008", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-LCH-009", "warning", "冷启动", "缺上线前自查清单",
      "没有上线前自查（冒烟/自测/上线前检查），带着 bug 上线很伤口碑。")
def r_lch_009(lines, text, path, ctx):
    if not any(k == "launch" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-LCH-009", ctx["docs"], ("launch",),
                 r"冒烟|自测|上线前|检查清单|回归"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "launch")
    return [_mk("SOLO-LCH-009", p, 1, t.split("\n")[0][:60])]


@rule("SOLO-LCH-010", "warning", "冷启动", "宣发含绝对化承诺",
      "宣发文案出现保证/必赚/第一/颠覆/革命等绝对化表述，却无「内测中」/"
      "「可能」等限定词，容易翻车。")
def r_lch_010(lines, text, path, ctx):
    hits = []
    for kind, p, t, lns in ctx["docs"]:
        if kind != "launch":
            continue
        if re.search(r"保证|必赚|第一|颠覆|革命|最强", t) and \
                not re.search(r"内测|可能|努力|目标是|之一", t):
            hits.append(_mk("SOLO-LCH-010", p, 1, "绝对化宣发无限定"))
    return hits


@rule("SOLO-LCH-011", "blocker", "冷启动", "TODO/占位符残留",
      "冷启动文档中还有 TODO/TBD/XXX/待填等占位符，素材还没写完就别上线。")
def r_lch_011(lines, text, path, ctx):
    hits = []
    for kind, p, t, lns in ctx["docs"]:
        if kind != "launch":
            continue
        for pat in PLACEHOLDERS:
            hits += _line_hits("SOLO-LCH-011", lns, t, p, re.escape(pat))
    return hits


@rule("SOLO-LCH-012", "warning", "冷启动", "缺演示素材规划",
      "没有演示素材规划（演示/视频/demo/录屏/截图），纯文字 launch 转化率偏低。")
def r_lch_012(lines, text, path, ctx):
    if not any(k == "launch" for k, _, _, _ in ctx["docs"]):
        return []
    if _doc_hits("SOLO-LCH-012", ctx["docs"], ("launch",),
                 r"演示|视频|\bdemo\b|录屏|截图|GIF"):
        return []
    k, p, t, lns = next(d for d in ctx["docs"] if d[0] == "launch")
    return [_mk("SOLO-LCH-012", p, 1, t.split("\n")[0][:60])]


# ================================================================ 技术选型

@rule("SOLO-TEC-001", "warning", "技术选型", "缺技术选型说明",
      "文档完全没提技术选型（技术栈/选型/框架），一人公司选错栈代价很高。")
def r_tec_001(lines, text, path, ctx):
    all_text = "\n".join(t for _, _, t, _ in ctx["docs"])
    if ctx["docs"] and not re.search(r"技术栈|选型|框架|前后端|数据库", all_text):
        return [_mk("SOLO-TEC-001", "<target>", 0, "无技术选型表述")]
    return []


@rule("SOLO-TEC-002", "warning", "技术选型", "选型无理由",
      "提了技术栈却没写为什么选它（因为/理由/选择原因/权衡），"
      "选型容易变成跟风。")
def r_tec_002(lines, text, path, ctx):
    all_text = "\n".join(t for _, _, t, _ in ctx["docs"])
    if re.search(r"技术栈|选型", all_text) and \
            not re.search(r"因为|理由|选择原因|权衡|考虑到", all_text):
        return [_mk("SOLO-TEC-002", "<target>", 0, "选型缺理由")]
    return []


@rule("SOLO-TEC-003", "warning", "技术选型", "无成本估算",
      "没做成本估算（成本/费用/预算/服务器费用），一人公司现金流要自己扛。")
def r_tec_003(lines, text, path, ctx):
    all_text = "\n".join(t for _, _, t, _ in ctx["docs"])
    if ctx["docs"] and not re.search(r"成本|费用|预算", all_text):
        return [_mk("SOLO-TEC-003", "<target>", 0, "无成本估算")]
    return []


@rule("SOLO-TEC-004", "warning", "技术选型", "无部署方案",
      "没写部署方案（部署/上线/Vercel/服务器/域名），做完不知道往哪放。")
def r_tec_004(lines, text, path, ctx):
    all_text = "\n".join(t for _, _, t, _ in ctx["docs"])
    if ctx["docs"] and not re.search(r"部署|Vercel|服务器|域名|托管", all_text):
        return [_mk("SOLO-TEC-004", "<target>", 0, "无部署方案")]
    return []


@rule("SOLO-TEC-005", "nit", "技术选型", "无备选方案",
      "选型没有备选（备选/替代方案/Plan B），主方案卡住时没有退路。")
def r_tec_005(lines, text, path, ctx):
    all_text = "\n".join(t for _, _, t, _ in ctx["docs"])
    if re.search(r"技术栈|选型", all_text) and \
            not re.search(r"备选|替代方案|Plan B|退路", all_text):
        return [_mk("SOLO-TEC-005", "<target>", 0, "选型无备选")]
    return []


# ================================================================ 主流程

def run_audit(target):
    files = collect_files(target)
    docs = []
    for p in files:
        text = read_text(p)
        docs.append((doc_kind(p, text), p, text, text.split("\n")))
    ctx = {"docs": docs}
    findings = []
    for r in RULES:
        try:
            for kind, p, text, lines in docs:
                findings.extend(r["check"](lines, text, p, ctx))
            # 无文档时的 missing-doc 规则：用空上下文再跑一次（只跑一次）
            if not docs:
                findings.extend(r["check"]([], "", "<target>", ctx))
        except Exception:
            continue  # 单条规则出错不影响整体
    # 去重（同一规则同一文件同一行只保留一条）
    seen, uniq = set(), []
    for f in findings:
        key = (f.rule_id, f.file, f.line)
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    order = {"blocker": 0, "warning": 1, "nit": 2}
    uniq.sort(key=lambda f: (order.get(f.severity, 3), f.rule_id, f.file))
    return {
        "tool": TOOL,
        "version": VERSION,
        "target": os.path.abspath(target),
        "summary": {
            "rules_run": len(RULES),
            "files_scanned": len(files),
            "blocker": sum(1 for f in uniq if f.severity == "blocker"),
            "warning": sum(1 for f in uniq if f.severity == "warning"),
            "nit": sum(1 for f in uniq if f.severity == "nit"),
        },
        "findings": [f.to_dict() for f in uniq],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="lhg-solopreneur 确定性独立开发审计")
    ap.add_argument("--target", required=True, help="要扫描的目录")
    ap.add_argument("--format", default="text", choices=("json", "text"))
    ap.add_argument("--fail-on", default="blocker",
                    choices=("blocker", "warning", "nit"))
    args = ap.parse_args(argv)

    data = run_audit(args.target)
    if args.format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        s = data["summary"]
        print("indie-audit v%s  扫描 %d 个文件，%d 条规则" %
              (VERSION, s["files_scanned"], s["rules_run"]))
        print("blocker=%d warning=%d nit=%d" %
              (s["blocker"], s["warning"], s["nit"]))
        for f in data["findings"]:
            print("[%s][%s] %s:%s %s" %
                  (f["severity"], f["rule_id"], f["file"], f["line"],
                   f["title"]))
            print("    %s" % f["detail"][:120])

    sev_order = {"blocker": 0, "warning": 1, "nit": 2}
    threshold = sev_order[args.fail_on]
    worst = min([sev_order[f["severity"]] for f in data["findings"]],
                default=99)
    return 2 if worst <= threshold else 0


if __name__ == "__main__":
    sys.exit(main())
