# REPORT 付録: MX-57 (#4928) FH3 try 関数の RVA と scopes 表の生成

本体 `REPORT_MX6.md` の上限のため、MX-57 の測定をここに置く。受入 1 (SjLj 形の pad 呼出し) の lift 配線の前段。

## 1. 生成物

- `dsp/scripts/mx57_fh3_scopes.py <pe> <out.json>`: FH3 親関数ごとに、try 関数の RVA・try map の scope (`kind` は pType の RVA、catch-all は 2)・unwind map の scope (kind 0) を出す。
- 上限判定は C 側と揃える (`tools/shimx/src/seh_fh3.c`):
  - try 表 (`shimx_fh3_scopes`): n_try / n_ip / nCatch の上限と IP 昇順違反で棄却する。maxState では棄却しない。
  - unwind 表 (`shimx_fh3_unwind_scopes`): maxState / n_ip の上限と IP 昇順違反で棄却する。try 表は残し、unwind 表だけ空にして `unwind_rejected` に数える。
- funclet の RVA は `mx39_funclet_reach.fh3_funclets_capped` を使い、lift 側の pad resolver 対応表に渡せる形にする。

## 2. 測定の状態

- 素材: `plugins-massivex` の `Native Instruments Massive X v1.7.1.exe` を `$RUNNER_TEMP/massivex-mx57` に展開し、`parse_setup_headers.py` → `extract_massivex.py <exe> <w> key` で `extracted/VST3/Massive X.vst3` (PE32+ x64 DLL) を得た。
- 修正前の測定: commit `24c4a4c6b` (`mx57_fh3_scopes.py` を追加した commit)。`python3 mx57_fh3_scopes.py "<Massive X.vst3>" scopes.json` で exit 0。FH3 親 13,748 (棄却 633)・try 関数 1,630・try scope 7,322・unwind scope 361,275・範囲逆転 0 件。時間と load は測定ログが残っていないため確定できない (本文と付録で値が食い違っていた。付録にも本文にも残さない)。
- 修正後の測定 (測定 commit `41cb36e87` = HEAD): 素材 `plugins-massivex` (`Massive X.vst3` md5 `622993e7…`・95,356,824 B) を `git archive 41cb36e87 tools/targets/massivex/dsp/scripts` で取り出したスクリプトで実行。exit 0。FH3 親 13,748 (棄却 633)・unwind 棄却 0・try 関数 1,630・try scope 7,322・unwind scope 361,275。修正前 (`24c4a4c6b`) と同値。所要 6.8 s (実測・load avg 1 分値 0.88 → 0.89)。
- 修正前の値との差: REPORT_APPENDIX_3776 の FH3 親は 13,525・棄却 355 (上限のみ)。母数の差の原因は未切り分け。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 生成表の C 側 `shimx_fh3_scopes` との照合 (同一 FuncInfo に対する出力一致) | 合成入力のみで検証済み | #4928 |
| 棄却 633 件 (3776 の 355 との差) の内訳 | 母数の説明が未確定 | #4928 |
| lift 側の配線 (try 関数入口の `ShxSehFrame` 登録・pad resolver 登録)・通し e2e | funclet は lift されるが呼べない | #4928 |
