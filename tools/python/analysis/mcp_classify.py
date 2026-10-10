#!/usr/bin/env python3
"""mcp_tools.json (静的解析) + tool_coverage.json (wasm 実行実測) から 48 tools の分類表を作る。
分類:
  A  local-flapi : 公開 flapi モジュール (channels/mixer/transport/plugins/playlist/ui/midi) のみ。FLEngine の flapi 実装だけで完結
  B  local-ilmcp : FL 内部専用モジュール ilmcp.* (PluginDB/Browser/PRScript 等) に依存。ローカル完結だが FLEngine 側に実装が必要
  U  local-ui    : ilmcp の tutorial/highlight (Gopher UI 付随)。ローカル完結だが優先度低
  X  対象外      : 外部通信 (クラウド/LLM) を要するもの。MCPTools.pyc 内には 0 件 (net 系 import 皆無)
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
mcp = json.load(open(f"{HERE}/mcp/mcp_tools.json"))
cov = {t["name"]: t for t in json.load(open(f"{HERE}/mcp/tool_coverage.json"))["tools"]}

NET_IMPORTS = {"socket", "http", "urllib", "ssl", "requests", "asyncio", "websocket", "xmlrpc", "ftplib", "smtplib"}

UI_ONLY = {"ilmcp.showHighlight", "ilmcp.getHighlightNames"}
rows = []
for t in mcp["tools"]:
    apis = set(t["api_calls_transitive"])
    il = {a for a in apis if a.startswith("ilmcp.")}
    if not il:
        cls = "A"
    elif il <= UI_ONLY:
        cls = "U"
    else:
        cls = "B"
    c = cov.get(t["name"], {})
    rows.append({"name": t["name"], "class": cls, "params": [p["name"] for p in t["params"]],
                 "flapi": sorted(apis - il - {"midi.PIM_None"}), "ilmcp": sorted(il),
                 "wasm_run": c.get("status"), "observed_calls": c.get("api_calls", [])})

by = {}
for r in rows:
    by.setdefault(r["class"], []).append(r["name"])
arity = {}
for r in rows:
    for x in r["observed_calls"]:
        n, a = x.rsplit("/", 1)
        arity.setdefault(n, set()).add(int(a))
res = {"total": len(rows), "counts": {k: len(v) for k, v in sorted(by.items())}, "classes": by,
       "network_imports_in_pyc": sorted(NET_IMPORTS & set(mcp["imports"])),
       "pyc_imports": mcp["imports"],
       "api_arity_observed": {k: sorted(v) for k, v in sorted(arity.items())}, "tools": rows}
json.dump(res, open(f"{HERE}/mcp/mcp_classification.json", "w"), indent=1, ensure_ascii=False)

L = ["# MCPTools.pyc (FL 26.1.7 System/Tools/MCP) 48 tools — 分類と FL API 呼出面\n",
     f"A local-flapi **{len(by.get('A', []))}** / B local-ilmcp **{len(by.get('B', []))}** / U local-ui(Gopher 付随) **{len(by.get('U', []))}** / X 対象外(外部通信) **0**\n",
     "wasm 実行: 全 tool を wasm CPython(Worker)+モック FLEngine 上で実行 → " +
     f"{sum(1 for r in rows if r['wasm_run']=='ok')}/{len(rows)} ok\n",
     "| # | tool | 引数 | 分類 | FL API (推移閉包) | ilmcp |", "|---|---|---|---|---|---|"]
for i, r in enumerate(rows, 1):
    L.append(f"| {i} | `{r['name']}` | {', '.join(r['params']) or '—'} | {r['class']} | {', '.join(r['flapi']) or '—'} | {', '.join(x.split('.')[1] for x in r['ilmcp']) or '—'} |")
open(f"{HERE}/mcp/MCP_TOOLS.md", "w").write("\n".join(L) + "\n")
print(json.dumps(res["counts"]), len(rows))
