# REPORT_1542 — 計測 build の getmem −4 (既定 2012 / 計測 OFF 2008) の帰属 (#1542 = [M11-N100], 親 #1352)

## 0. 結論

- 測定 commit: **`d015e210`** (現 head。このコミットで IR 生成から全て再実行した)。
- 既定 build (A・計測 OFF) は getmem **2012**、計測 ON の build (B・C・D) は全て **2008**。n=3 で全構成とも値が一定 (min–max は全て同値)。
- 既定 build (計測なし) の survey は `repro_1352.sh` の 3 回 (`d015e210`) で **870/24/0・getmem 2012**、計測 ON の OFF 系 (dest 読出しあり・なし) は全 3 回で **870/24/0・getmem 2008**。
- −4 は post の 3 点 (probe 呼出し・wrapper 改名・`m11_dest_obs` 宣言) のどれにも帰属しなかった。3 点のいずれを除いても getmem は 2008 のまま (B・D)。3 点すべてを外して IR を既定と同一 (md5 `baa100ff…`) にした build でも 2008 (C) のため、3 点の組合せでも −4 は消えない。
- −4 は、IR を既定と同一にしても `M11_INSTR_413060=1` の build (C) で現れる。IR は同一 (C の `boot_final3.ll` と A の md5 が一致) なので、**推定**: 差は IR 以外、すなわち計測 flag の C 側への影響 (`ov.o`・`rt.o`・EXPORTS のいずれか) による。IR 以外の差を消去した推論であり、C 側への影響を直接観測したものではない。
- C 側のどの部分が −4 を生むかは**未切り分け**。C 側だけを既定に戻した対照 (`rt.o` だけ・`ov.o` だけ差し替え) は未実施 (`m11_build.sh` は C 側の計測 flag を個別に切り替える変数を持たない)。→ #1701。

## 1. 測定 (測定 commit `d015e210`・直列・単発の繰返し n=3・foreground)

**実行環境** (2026-10-14 の GitHub Actions run。runner 4 vCPU、ディスク空き 76G):
- 素材: `fl-win64` → `$RUNNER_TEMP/extracted/` (`FL_WIN64_DIR=$RUNNER_TEMP`)、`work-m11` → `tools/m11/work/` (展開後 `m11_gen_ir2.sh` で作り直し)、`toolchain-emsdk` → [EMSDK]、`toolchain-retdec` → [RETDEC] (展開先は `docs/REFERENCES.md` §4 の [EMSDK]・[RETDEC])。
- IR 生成: `bash m11_gen_ir2.sh` (48 秒)。`ir_conditions.json`: `ldfix=applied`・`qstore=not-applied`・`ir_sha256=08c7b646…` (REPORT_1352・§1 旧記録と一致)。ldfix 件数: F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 F4=10 errors=0 (旧記録と一致)。
- 負荷: `uptime` で load 0.76〜1.03 (測定前後)。

**`repro_1542_split.sh 3` の実測** (全 12 行。`work/split_1542/table.tsv`・総所要 7 分 24 秒):

| 構成 | 回 | boot_final3.ll md5 | ok | trap | clobber | getmem | fastmm_getmem_impl |
|---|---|---|--:|--:|--:|--:|--:|
| A 既定 (計測 OFF) | 1/2/3 | `baa100ff…` | 870 | 24 | 0 | **2012 / 2012 / 2012** | 2096 |
| B noprobe | 1/2/3 | `e4bce794…` | 870 | 24 | 0 | **2008 / 2008 / 2008** | 2091 |
| C noren | 1/2/3 | `baa100ff…` (A と同一) | 870 | 24 | 0 | **2008 / 2008 / 2008** | 2091 |
| D nodecl | 1/2/3 | `3a2f0a01…` | 870 | 24 | 0 | **2008 / 2008 / 2008** | 2091 |

- A・B・C・D とも n=3 の min–max は同値 (A=2012、B/C/D=2008)。決定性は確認済み。
- 所要: ドライバ全体 (12 行の build + survey) は 7 分 24 秒。行ごとの所要は未計測 (ドライバは行単位で時間を取っていない)。

**変種の効果の確認** (上の build の `work/split_1542/ir_<構成>_r1.ll`、grep 件数):

| 変種 | 確認内容 | 件数 | 期待 | 判定 |
|---|---|--:|---|---|
| B noprobe | `call void @m11_probe(i32 8)` | 0 | 0 | 一致 |
| D nodecl | `m11_dest_obs` (宣言・呼出し) | 0 | 0 | 一致 |
| D nodecl | `call void @m11_probe(i32 8)` (probe は残す) | 1 | 1 | 一致 |
| C noren | `function_413060__lifted` 参照 | 0 | 0 (wrapper 無し) | 一致 (A と同じ件数) |
| B noprobe | `m11_dest_obs` (dest 読出しは残す) | 2 | 2 | 一致 |

注: C noren は `define weak i64 @function_413060(...)` が 1 件あるが、これは本体そのもの (wrapper ではない)。wrapper の有無は `__lifted` 参照数で判定する。

**`repro_1352.sh` (現 head `d015e210`・3 回・各回で default / instr_off / instr_off_noread の 3 構成)**:

| 回 | default getmem | instr_off getmem (dest 読出しあり) | instr_off_noread getmem (dest 読出しなし) | 判定 |
|---|--:|--:|--:|---|
| 1 | 2012 | 2008 | 2008 | PASS (870/24/0 一致) |
| 2 | 2012 | 2008 | 2008 | PASS |
| 3 | 2012 | 2008 | 2008 | PASS |

- 所要: 1 回あたり 1 分 45 秒〜1 分 57 秒。
- 旧記録 (`7fc1088f` の 1 回・1 分 54 秒・load 0.63〜0.97) は、現 head の 3 回と同じ判定 (PASS)。`22d4a2eb` での PASS 記録は測っていないため取り消し済み。

**`tools/m11` の差分** (`git diff --stat 47e4a846 HEAD -- tools/m11`・測定 commit `47e4a846` から PR head まで。HEAD は `d015e210` 以降に REPORT のみを追加する):

```
 tools/m11/REPORT_N15.md                   |  20 ++++
 tools/m11/REPORT_N1532.md                 | 121 ++++++++++++++++++++++++
 tools/m11/ldfix/REPORT_1168.md            |  24 ++++-
 tools/m11/ldfix/REPORT_1324.md            | 152 ++++++++++++++++++++++++++
 tools/m11/ldfix/gate_5c44b0_1324.py       |  40 ++++++++
 tools/m11/ldfix/ldfix.py                  |  38 +++++++-
 tools/m11/ldfix/origin_probe_1324.py      |  27 ++++++
 tools/m11/ldfix/survey_d17_multiload.py   | 128 +++++++++++++++++++++++++
 tools/m11/rtl/REPORT.md                   |  12 ++-
 tools/m11/trap_triage/REPORT_1317.md      |  53 +++++++++++
 tools/m11/trap_triage/REPORT_1542.md      |  66 +++++++++++++
 tools/m11/trap_triage/REPORT_881.md       |  60 +++++++++++-
 tools/m11/trap_triage/REPORT_882.md       |  10 ++
 tools/m11/trap_triage/probe1507_listB.mjs |  32 +++++++
 tools/m11/trap_triage/repro_1542_split.sh |  46 +++++++++
 15 files changed, 815 insertions(+), 14 deletions(-)
```

- `ldfix/ldfix.py` は +33/−5 (`git diff --numstat`)。IR は変わっていない (`ir_sha256=08c7b646…` が旧記録と一致、A〜D の IR md5 も旧記録と一致)。
- 測定に使ったコード (`m11_post.py`・`m11_build.sh`・`m11_survey.mjs`・`m11_gen_ir2.sh`・`m11_cond.py`・`m11_ov.c`・`m11_rt.c`) は `47e4a846` から HEAD まで差分 0 (`git diff 47e4a846 HEAD -- <上記ファイル>` が空)。
- 差分の大半は main 取り込み (`88a13a92`) 由来。`ldfix` の変更は IR 生成を変えていないことを上の md5 で確認した。

## 2. 解釈

- **3 点は単独でも組合せでも −4 を作らない**: B (probe 呼出しだけ除去) も D (宣言だけ除去) も 2008。C は 3 点すべてを外し IR を既定と同一に戻したが、なお 2008。よって −4 は post の 3 点に由来しない。
- **IR は同一なのに差が出る**: C の `boot_final3.ll` は A と md5 一致。**推定**: 差は IR 以外、すなわち計測 flag の C 側への影響 (`rt.o` が計測の実体 (`m11_dest_obs`・`g_dest_h`) を持つ・EXPORTS の追加・`ov.o` の計測分岐) に限られる。
- `ov.o` について: `m11_ov.c` の `function_413060` 本体 (probe 呼出し `m11_probe(8)` と `m11_dest_obs(dest)` を含む) は `#if M11_OV_CLASSCREATE || M11_OV_413060` の内側にあり、測定条件 (`M11_OV_413060=0`・`M11_OV_CLASSCREATE=0`) では本体はコンパイルされない。したがって「`ov.o` が `function_413060` 本体に probe を入れる」は**未確認** (ソースの `#if` 条件からの推定。`.o` の `nm`/`objdump` 確認は未実施)。
- **IR 同一・計測 flag のみ違う A と C の比較**: 同じ `baa100ff…` の IR で getmem が 2012 (A, flag OFF) と 2008 (C, flag ON)。n=3 で再現。IR を揃えた上での差なので、計測 flag の C 側への影響が −4 の候補 (推定)。
- 過去の survey 判定 (ok/trap/clobber) は全構成で同一のため、−4 は判定には出ない (元の 871/23 とは別事象)。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| C 側の計測 flag のうち、−4 を生む部分の切り分け (`ov.o` の `function_413060` 本体 / `rt.o` の計測実体 / EXPORTS のどれか) | 計測 build の getmem 計数が既定と 4 ずれる。survey 判定には出ない | #1701 ([M11-N116]) |
| 既定 2012 と計測 OFF 2008 の差の**意味** (実行の差か、計数の差か) | `fastmm_getmem_impl` も 2096 → 2091 で同方向にずれる。FastMM の入口計数が減っているのか未確認 | #1701 ([M11-N116]) |

### 3b. 子 issue

残件は「C 側の計測 flag のどの部分が −4 を生むか」の切り分けで、C 側の `rt.o`・`ov.o` を個別に差し替える対照が必要。1 run に収まらないため #1701 ([M11-N116]) として分離した。

## 4. 再現

- A〜D の表 (n 回): `bash tools/m11/trap_triage/repro_1542_split.sh [N]` (N = 反復回数・既定 1)。`work/split_1542/table.tsv` に出力。前提は `m11_gen_ir2.sh` 実行済み・`FL_WIN64_DIR` 設定済み・[EMSDK]・[RETDEC] 配置済み。
- 既定と計測 OFF の基準: `bash tools/m11/trap_triage/repro_1352.sh` (判定 `PASS`)。
- 変種: `M11_PROBE_VARIANT` (`noprobe` / `noren` / `nodecl`) は `M11_INSTR_413060=1` のときだけ有効 (それ以外は `m11_post.py` が exit)。
- 作業ディレクトリは `tools/m11/`。`work/` は `m11_gen_ir2.sh` で生成する (`work-m11` 展開後に実行)。
