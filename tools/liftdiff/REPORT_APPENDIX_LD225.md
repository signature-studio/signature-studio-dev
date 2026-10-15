# LD-225 (#4561): sample:800 の集合に 691dd0 (OBJ_PATTERNS の VA) を入れる

親: #4264 (LD-207)。前段: `REPORT_APPENDIX_LD207.md` §4 (691dd0 は sample:800 の集合に入らない)。

測定 commit: `1327bc530` (コードを変えた最後の commit。検証 HEAD = 測定 commit)。

## 1. 結論

- 集合の拡張方法: **closure の定義は変えず、sample の抽出条件を変えた。** `sample:N` は従来どおり `random.Random(1).sample(closure, N)` の N 件を使い、その集合に `ldlib/cases.py` の `OBJ_PATTERNS` の VA (現在は 691dd0 だけ) を足す (`liftdiff.sample_vas`)。
- 集合の大きさ: 800 → **801**。素の抽出 800 件は変わらない (691dd0 だけが増える)。
- batch の実測 (sample:800): **一致 360 / 不一致 235 / 実行不能 206**。LD-207 時点の 360 / 234 / 206 から、不一致 +1 (691dd0 の追加分) のみ。
- 691dd0 の batch 上の verdict: **`mismatch`** (タグ `callee_divergence`・confidence medium)。`classify.verdict` は case に 1 つでも `diff` / `wasm_trap` があれば `mismatch` にするため、この `mismatch` は `vmo` の `diff` で決まる。他の 11 pattern は `native_fault`・`both_fault`・`hang` で、`mismatch` の根拠にはならない。`vmo` の `diff` の原因は #4524 (LD-222) の範囲で、本 PR では追及しない。

## 2. 実測

- e2e: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/liftdiff/liftdiff_e2e.sh --m11-only` → **exit 0・`LIFTDIFF_E2E PASS`・`wall 179s`**。開始時 load 0.29 (10:25:58)・終了直後 4.36 (10:28:57)。sample 段の batch は `111s` (801 件、12 shard)。
- 単体: `tests/test_ld225_sample_vmo.py` PASS (`rc=0`)。ネガコン: `sample_vas` の OBJ_PATTERNS 合併を外す (`pass`) と `AssertionError: sample:800 に 691dd0 が入る` で `rc=1` (実測)。
- 単体: `tests/test_ld207_obj_pattern.py` PASS (`rc=0`)。
- 再現の前提: `bash tools/m11/m11_gen_ir2.sh` を `FL_WIN64_DIR` 付きで実行して `ir_conditions.json` を作り直した (`gen_rc=0`)。
- コード差分 (測定 commit `1327bc530` → HEAD): コード (`*.md` 以外) は 0 行 (`git diff 1327bc530 HEAD -- tools/liftdiff ':!*.md'` の出力は 0 行)。差分は本付録の commit `6ac337895` の文書のみ (`git diff 1327bc530 HEAD --stat -- tools/liftdiff` は `REPORT_APPENDIX_LD225.md` の 1 ファイル)。
- 製品 KPI (FLEngine 起動・最初のウィンドウ): 本 PR は起動・GUI に関わらないため書かない。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `vmo` の `diff` の原因 (heap 差・ret `native=0x1`/`wasm=0x0`) | 691dd0 の一致 / 不一致は未確定 | #4524 ([LD-222]) |

注記: sample:800 の集合は本 PR 以降 801 件になる。過去の sample:800 の数値 (LD-207 時点の 360/234/206 など) は 800 件の集合での値で、691dd0 の 1 件分 (不一致 +1) だけ直接比較がずれる。
