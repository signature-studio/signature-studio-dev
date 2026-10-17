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
- 修正後 (上限判定の揃え直し) の測定: **未実施**。修正 commit の時点で `plugins-massivex` が実行環境に無かった。上記の値は修正前の数値であり、修正後の HEAD とは一致しない。修正後は try 側の棄却数 (633) と try 関数数 (1,630) が変わりうる。
- 修正前の値との差: REPORT_APPENDIX_3776 の FH3 親は 13,525・棄却 355 (上限のみ)。母数の差の原因は未切り分け。
- 次の run で `oc_artifacts: fl-win64 plugins-massivex` を指定し、修正 commit = 測定 commit で再測定して本節を更新する。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正後 HEAD での再測定 (上記 2 節) | 本付録の数値は修正前 | #4928 |
| 生成表の C 側 `shimx_fh3_scopes` との照合 (同一 FuncInfo に対する出力一致) | 合成入力のみで検証済み | #4928 |
| 棄却 633 件 (3776 の 355 との差) の内訳 | 母数の説明が未確定 | #4928 |
| lift 側の配線 (try 関数入口の `ShxSehFrame` 登録・pad resolver 登録)・通し e2e | funclet は lift されるが呼べない | #4928 |
