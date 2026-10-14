# liftlib #3145 — `ott_outhash` の JSON 失敗の切り分け (部分達成)

- 親: #3067 (元の症状は `REPORT_APPENDIX_3067.md` §3.2)。担当 dir: `tools/liftlib/`。
- 基点: `origin/main` `8d8d0e6a`。前提 PR: #3098 (#3067 の repmap 修正) は **未 merge**。本件の変更は `p1_legacy.py` に触れないので競合しない。
- **測定 commit (コードを変えた最後の commit)**: `5f426e03` (`fix(liftlib): report ott_outhash failure details and parse its JSON line (#3145)`)。
  差分 0 行の確認: `git diff 5f426e03 HEAD -- tools/liftlib/liftlib tools/liftlib/tests` (本 PR で以後 code は変えていない)。

## 1. 環境 (実測)

- `$ARTIFACTS_DIR` に実在: `fl-win64.tar.zst`・`work-m6-ott.tar.zst`。`tools/m10/work/ott_m10.cjs` (+ `.wasm`) と `tools/m6/work/ott.drc.ll` 等は作業ツリーに既にある。
- **不足 (liftlib 生成 module を作れない)**: `analysis-ott-binaries` (`OTT_vst2_win64.dll`。`ott.run` の `Image(DLL)` で読む。`$ARTIFACTS_DIR` に無い) と `toolchain-emsdk` (既定の emsdk 配置 `EMSDK_DIR` が無く `emcc` が無い)。
- よって `ott_auto_none` の `ott_gen.cjs` は作れず、失敗した module 側の挙動は再現できなかった。

## 2. 切り分けの結果

| 試行 | 結果 (実測) |
|---|---|
| 参照 `tools/m10/work/ott_m10.cjs` で `node ott_outhash.mjs` (node v22.23.3) | rc=0・**0.58 s**・42 組 (f0 21 組) の JSON を stdout に出力 |
| 存在しない cjs を `OTT_CJS` に渡す | rc=1・stdout 空・stderr 先頭 `Error [ERR_MODULE_NOT_FOUND]: Cannot find module ...` |
| 旧版 (`json.loads(r.stdout)`) で上の空 stdout を読む | `Expecting value: line 1 column 1 (char 0)` だけが残る (#3067 §3.2 と同じ形) |

- 症状 (stdout が JSON でない) は「module が出力前に終了して stdout が空」か「stdout に JSON 以外が混じる」で起きる。どちらかは、liftlib 生成 module を実行しないと判別できない (未切り分け)。
- 候補の例: `m6_rt` / `m8_rt` の fail-fast は `fprintf(stderr)` の後に `abort()` する (`tools/m6/m6_rt.c:32`・`tools/m8/m8_rt.c:20`)。stdout は空のまま終わるので、症状と一致する。outhash の [0x248]=1 経路 (未初期化読み) で到達し得る、と推定。**推定 (未検証)**。新しい `outhash_json` の例外に stderr 先頭が残るので、次の実測で判別できる。
- #3067 §3.2 の「約 7 分/module」は、参照 module の本 run 実測 (0.58 s) と合わない。出所 (CAB-238 の liftlib 生成 module か) は未確認。

## 3. 変更

- `tools/liftlib/liftlib/recipes/ott.py`: `outhash_json(r)` を追加。stdout の**最後の JSON 行**を読む。JSON が無ければ rc・stdout 先頭 200 字・stderr 先頭 400 字を例外に残す。`error=` の切り詰めを 200 → 600 字。成功経路の値は変えない。
- `tools/liftlib/tests/test_unit.py`: T27 を追加 (混在行の JSON 読取・JSON 無しの例外内容を固定)。実行: `python3 -c "import sys; sys.path.insert(0,'tests'); import test_unit as T; T.t18(); T.t27()"` → T18 ok・T27 ok。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| liftlib 生成 `ott_gen.cjs` の outhash 実行と、失敗の原因特定 (受入 1 の残り) | SHA 突合 (42 組・f0 21 組) が未判定 | #3145 (open のまま。素材追加で再起動) |
| 必要素材 `analysis-ott-binaries` (OTT DLL) と `toolchain-emsdk` (emcc) | `ott.run` が起動できない | #3145 (`oc_artifacts:` に追加して再起動) |
| 修正後 HEAD (#3098 merge 後) での SHA 再測定と、`REPORT_APPENDIX_3067.md` §3.2 の未判定欄の更新 | #3098 が未 merge のため、このブランチには §3.2 の付録が無い | #3145 (#3098 merge 後に実施) |
| 基準 (`--auto none` の 42/42) の差し替え | PM 判断事項 (issue 本文の受入条件 3) | PM |
