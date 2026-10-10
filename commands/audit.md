---
description: 独立开发审计：45 条确定性规则扫描 MVP/定价/冷启动文档（范围完整性、定价要素、合规声明、TODO 残留），输出 blocker/warning/nit 分级报告。
argument-hint: ["文档目录"]
---

# /lhg-solopreneur:audit —— 独立开发审计

你是独立开发审计专家。用户输入在 `$ARGUMENTS` 中为文档目录（缺省为当前目录）。

## 执行流程

### Step 1：跑确定性审计（必做）

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/audit/indie_audit.py --target <文档目录> --format json
```

解析 JSON，按 blocker / warning / nit 分级整理。45 条规则覆盖：
MVP 范围（10 条）、定价（12 条）、合规（6 条）、冷启动（12 条）、技术选型（5 条）。

### Step 2：修 blocker

逐条修复（最小改动原则），修一条用脚本复查一条。
修不掉的列入"需人工处理"，**不许**为清零而改规则。

### Step 3：人工评审（脚本抓不到的三件事）

1. **真实性**：用户评价、数字、案例是真实的吗？编造的一律标 blocker。
2. **合规口径**：凡涉税务/支付/收入的表述，合规声明/免责说明到位了吗？
3. **一致性**：mvp.md 的 P0 功能、pricing.md 的价格、launch.md 的宣发，
   三者讲的是同一个产品吗？价格数字对得上吗？

### Step 4：输出报告

结论只能是"通过"或"不通过"，附 blocker/warning/nit 数量与处理情况、
需人工处理项。存为 `docs/audit-YYYYMMDD.md` 备查。

## 硬规则

- blocker 没清零就说"做完了" → 不许。
- 为清零改规则 → 算作弊，不许。
- 报告里不许出现"大概""应该""可能没问题"。
