# SHX-T61 (#5855): callee `function_4483f0` の計装 (`fix_shx_t61`・既定 OFF)

## 1. 結論

- 計装の基盤を入れた。`M11_FIX_SHX_T61=1` のときだけ callee `function_4483f0` の入口に呼出し回数と `this+0x4c`・`this+0x48` を `@fx61_buf` へ書く。既定 OFF で、既定 IR は変わらない (`shx_t61=not-applied`)。
- 本 run で親の外側 loop 入口の計装 (§6b・`fix_shx_t61b`・既定 OFF) を入れた。入口は上限 10 の下で 100001 回通過し、添字 `-32.0`・`-32.2` は 1 のまま (記録で確認)。
- 受入 1 (hang の機序の確定) は未達。前 run の ON では実 boot が rc 124 (hang) し、hang 後に `@fx61_buf` を読む経路が無かった (trap 方式より前の状態)。hang 位置は未確定。
- trap 方式 (§5) は、前 run の実測で hang の前に記録を読めることを確認した (fix run では再現していない・再現は未確認)。ON の値は §5 の表が正本。
- §3.1・§3.3 は前 run の実測である。本 run (fix) では lift 素材 (`tools/m11/work/boot*.lift.ll`) が無く、IR を再生成できなかった (§3.2)。

## 2. 測定条件

- 測定 commit: `b07e20aaf` (本 run でコードを変えた最後の commit)。
- 差分 0 の証跡 (fix run・HEAD で確認。測定経路 = 計装・IR 生成・build・trace のコードは測定 commit から変わっていない):

```
$ git diff b07e20aaf HEAD -- tools/m11/ldfix/fix_shx_t61.py tools/m11/shimx_link tools/m11/m11_gen_ir2.sh tools/m11/m11_build.sh tools/m11/m11_lift.sh ':!tools/m11/shimx_link/REPORT*' | wc -l
0
```

- 注: `tools/m11` 全体では、`main` の取り込み (merge) により測定 commit から HEAD まで別 PR のコード (`ldfix/depth_4498.py` 等 7 ファイル) が入っている。これらは測定経路から参照されない (`grep` で確認)。

- 素材: `fl-win64` (`$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`) を本 run で展開。`work-m11` は本 run の artifacts 配置先 (`docs/WORKFLOW.md` §11 の `work-m11`) に無い。
- §5 の IR の出所: 記録が無い。PR 本文と REPORT の既存記述のどこにも、§5 の trap 実測に使った IR の生成元 (生成スクリプト・素材の版・`ir_sha256`) が書かれていない。生成物 (`work/`) と lift 素材は fix run の環境に無く、再生成には RetDec が要る (D5 で新規作業は不可)。よって fix run では §5 の表を再現できなかった。
- 負荷 (前 run): 1 分平均 0.99〜1.00 (nproc 4)。

## 3. 実測

### 3.1 既定 OFF の IR (前 run の実測)

| 項目 | 結果 |
|---|---|
| `m11_gen_ir2.sh` (既定) | rc 0 |
| `work/boot_final.ll` の `fx61` 件数 | 0 件 |
| `ir_conditions.json` | `shx_t61=not-applied` |
| `ir_sha256` (先頭 16 桁) | `b202c157a80807f2…` |

全文の `ir_sha256` は前 run の PR 本文に無く、本 run でも再生成できないため未記録。

### 3.2 前 run の再現 (失敗・fix run でも同じ)

- `m11_gen_ir2.sh` (既定・FL_WIN64_DIR を展開先に設定): rc 1。`work/boot0.lift.ll` が無い (`m11_merge.py` が FileNotFoundError)。fix run でも同じ rc 1 を確認した。
- 原因: lift 素材 `boot0〜5.lift.ll` を含む `work-m11` が fix run に配置されていない。fix run の artifacts 配置先は `fl-win64.tar.zst` のみ。`boot*.lift.ll` の再生成は RetDec を使うため、新規の作業としては行わない (D5)。
- よって fix run では §3.1 の `ir_sha256` 全文と `fx61` 件数を再確認できなかった。

### 3.3 ON 計装 (`M11_FIX_SHX_T40=1 M11_FIX_SHX_T61=1`・前 run の実測)

| 段階 | 結果 |
|---|---|
| IR 生成 (`m11_gen_ir2.sh`) | rc 0 (42 秒)。`fx61` は 15 行 |
| build (`m11_build.sh`) | rc 0・signature mismatch 0・undefined 0 |
| trace build (`shimx_link/build.sh --trace --soft`) | rc 0・signature mismatch 0・undefined 0・duplicate 0 |
| 実 boot (`run_trace.mjs`・上限 150 s) | rc 124 (hang)。stdout・stderr・trace ファイルとも出力なし |
| 実 boot + `SXT_PRINT=1 M11_TRACE=1` | rc 124。`[m11][VA-stack]` の wasm スタックのみ。`function_4483f0` の呼出し回数は出ない |

### 3.4 trace 分岐の確認

`shimx_link/build.sh` の分岐は `grep -q '^@fx61_buf' "$GEN/boot_trace.ll"` で判定する。`gen_link.py` は `@fx61_buf` を `__sxt_` に改名しないため、この grep で検出できる (前 run のレビューで確認済み)。

## 4. 試行で分かったこと

- `printf` を計装に使うと、`m11_winstubs.c` の `printf` stub と型が衝突してビルドが落ちた。
- `sx_t61_rec` (IR から C の関数を呼ぶ形) も `genstubs` が生成する stub と名前が衝突し、リンクが落ちた (`gui_stubs_*.c`・`trace_wrap.c`)。IR の `declare` は stub 化されるため、IR から C を呼ぶ形は使えない。
- そこで IR 側は `@fx61_buf` (global) に書き、C 側は読み出し関数だけを持つ形にした。リンクは通った。
- hang 中は `run_trace.mjs` が JS に制御を戻さないため、前 run の計装 (trap なし) では `fx61_buf` を読めなかった。trap 方式 (§5) で読めるようになった。

## 5. 読み出し経路 (trap 方式・前 run の実測、fix run で未再現)

測定 run = 測定 commit `b07e20aaf` の run。IR の生成元は未記録 (§2)。

- hang の前に記録を読むため、呼出し回数が `FX61_LIMIT` (既定 100000) を超えたら IR の `unreachable` で trap させる (`fix_shx_t61.py`)。trap は wasm 例外として JS に戻るため、`run_trace.mjs` は `_fx61_count` / `_fx61_self` / `_fx61_c4c` / `_fx61_c48` を読んで run.json の `fx61` に入れる (`build.sh` は計装の IR のときだけ export する)。
- 実測 (commit は測定 commit `b07e20aaf`。ON = `M11_FIX_SHX_T40=1 M11_FIX_SHX_T61=1`・trace_soft):

| `FX61_LIMIT` | 結果 | `count` (呼出し回数) | `c4c` (this+0x4c) | `c48` (this+0x48) | 所要 |
|---|---|---|---|---|---|
| 0 | trap (unreachable) | 1 | 1 | 0 | 未計測 |
| 1 | trap | 2 | 2 | 1 | 未計測 |
| 2 | trap | 3 | 3 | 2 | 未計測 |
| 3 | trap | 4 | 4 | 3 | 未計測 |
| 5 | trap | 6 | 6 | 5 | 未計測 |
| 100000 (既定) | trap | 100001 | 100001 | 100000 | 0.25 s (`time` の real。run_trace.mjs 単体) |

- 読み取り: callee は呼ばれるたびに `this+0x4c`・`+0x48` を 1 ずつ増やし、`this` (`fx61_self`) は全呼出しで同じ値 (親の `%stack_var_-104` alloca)。これは callee が親の alloca を書換えていることを実行で示す。
- 負荷: 実行 0.25 秒 (上限まで hang しない)。前 run の hang (rc 124・100 s 以上) とは挙動が違う。前 run で hang と見えたのは、trap しない版で制御が戻らなかったためと推測する (未確認)。

## 6. 静的な読み (親 IR の loop 条件)

- 親 `function_448490` の外側 loop は `dec_label_pc_4484f4` の `-32` (SSA の `stack_var_-32.0.reload` / `stack_var_-32.2.reload`) で進み、`dec_label_pc_448731` で `%9` (`[arg2-4]` の値) と比べる。
- callee `function_4483f0` が書く `this+0x48`・`+0x4c` は、この loop 条件 (`%9`・`%12`) の入力に入っていない。callee の書換えは親の SSA 変数に届かない。
- 静的にはこれが、`+0x4c` 初期 store で callee の書換えが loop を抜けさせない理由と整合する。ただし loop が抜けない具体的な分岐は未確定。

## 6b. 親の外側 loop 入口の計装 (`fix_shx_t61b`・本 run・既定 OFF)

- 計装: `M11_FIX_SHX_T61B=1` のときだけ親 `function_448490` の外側 loop 入口 `dec_label_pc_4484f4` に入る。入口の通過回数・上限 `%9` (下位 32 bit)・添字 `-32.0`・`-32.2` を `@fx61b_buf` へ書き、回数が `FX61B_LIMIT` (既定 100000) を超えたら trap。記録の load・store だけで分岐は変えない。
- 既定 OFF: `ir_sha256` 先頭 `b202c157a80807f2`・`shx_t61b=not-applied`・実 boot `units_run=17`・`dllmain_done=true`・`va_calls=2`・`icall_ok=24`・`icall_miss=1`・`boot_rc="1"`・`longjmp_hit=1` (REPORT_SHX-T28 §7 と一致)。
- ON (`M11_FIX_SHX_T40=1 M11_FIX_SHX_T61B=1`・既定 LIMIT): IR 生成 rc 0 (`fx61b` 14 行)・build rc 0・trace build rc 0 (`mismatch=0 undefined=0 duplicate=0`)。実 boot は trap で終わり、0.5 s 未満。

| LIMIT | 入口の通過回数 `count` | `lim` (%9) | `idx` (-32.0) | `idx2` (-32.2) | 所要 |
|---|---|---|---|---|---|
| 3 | 4 (trap) | 10 | 1 | — (計装前) | 0.52 s |
| 100000 (既定) | 100001 (trap) | 10 | 1 | 1 | 0.52 s |

- 読み取り: 入口は上限 10 の下で 100001 回通過し、添字 `-32.0`・`-32.2` は 1 のまま変わらない。外側 loop の続行判定 `%106 = icmp slt %9, %105` (`dec_label_pc_448731`) は、`-32.2`=1 < `%9`=10 で真になり、loop が続く。
- 分かったこと: 外側 loop の添字 (`-32.0` / `-32.2`) が 1 から進まないことが、入口の記録で確かめられた。ただし、添字が進まない分岐 (`dec_label_pc_448681`・`448669`・`44870f` のどれを通るか) は未記録のため、hang の分岐は未確定。
- 注意 (計装の作り方): `m11_build.sh` は `FX61B_LIMIT` を stamp に含めない。LIMIT を変えたら `work/boot_final3.ll`・`work/shimx_link/boot_hn.ll`・`boot_fixed.ll` を消してから `m11_gen_ir2.sh` → `m11_build.sh` → `build.sh --trace --soft` の順で作り直す (本 run の LIMIT=3 と 100000 の実測はこの手順)。

## 7. 未解決

- hang の位置 (どの分岐で親の loop が抜けないか) は未確定。§6b で外側 loop の入口と添字は記録できた。次段は、親 loop 内の分岐 (`dec_label_pc_448669`・`dec_label_pc_448681`・`dec_label_pc_44870f`・`dec_label_pc_448731`) ごとに通過回数を同じ方式で記録すること。
- 修復 ON の hang の機序 (#5846 受入 1 の続き)。起票先: #5855 (受入 1 の続き)。#5846 の現タイトル (「(#4121 残件)」) とは対応しないため、#5846 へは追記しない。
