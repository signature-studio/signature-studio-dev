# REPORT 付録: MX-57 (#4928) FH3 try 関数の RVA と scopes 表の生成

本体 `REPORT_MX6.md` の上限のため、MX-57 の測定をここに置く。受入 1 (SjLj 形の pad 呼出し) の lift 配線の前段。

## 1. 生成物

- `dsp/scripts/mx57_fh3_scopes.py <pe> <out.json>`: FH3 親関数ごとに、try 関数の RVA・try map の scope (`kind` は pType の RVA、catch-all は 2)・unwind map の scope (kind 0) を出す。規則は C 側 `tools/shimx/src/seh_fh3.c` の `shimx_fh3_scopes` / `shimx_fh3_unwind_scopes` と同じ (IP 区間 [ip[i], ip[i+1])・上限 maxState / nTry / nIP 0x1000・nCatch 0x100・IP 昇順違反は棄却)。
- funclet の RVA は `mx39_funclet_reach.fh3_funclets_capped` を使い、lift 側の pad resolver 対応表に渡せる形にする。

## 2. 実測 (実 PE)

- 素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` を `$RUNNER_TEMP/massivex-mx57` に展開し、`parse_setup_headers.py` → `extract_massivex.py <exe> <w> key` で `extracted/VST3/Massive X.vst3` (PE32+ x64 DLL) を得た。
- 測定 commit: 本 PR の commit (`mx57_fh3_scopes.py` を追加した commit)。
- `python3 mx57_fh3_scopes.py "<Massive X.vst3>" scopes.json`: exit 0・**6.8 s**・load 0.97 0.53 0.21。
  - FH3 親関数 **13,748** (棄却 633)。try 関数 (try_scopes ≥ 1) **1,630**。
  - try scope **7,322**・unwind scope (kind 0) **361,275**。
  - funclet 持ち親 13,255。範囲の逆転 (end ≤ begin) 0 件。
- 既存値との差: REPORT_APPENDIX_3776 の FH3 親は 13,525・棄却 355 (上限のみ)。本スクリプトは棄却を FuncInfo 読取不能 (C 側と同じく上限超過・IP 昇順違反を含む) で数えるため母数が異なる。差の原因は未切り分け (受入 1 の次の手で確認する)。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 生成表の C 側 `shimx_fh3_scopes` との照合 (同一 FuncInfo に対する出力一致) | 合成入力のみで検証済み | #4928 |
| 棄却 633 件 (3776 の 355 との差) の内訳 | 母数の説明が未確定 | #4928 |
| lift 側の配線 (try 関数入口の `ShxSehFrame` 登録・pad resolver 登録)・通し e2e | funclet は lift されるが呼べない | #4928 |
