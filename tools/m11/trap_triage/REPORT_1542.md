# REPORT_1542 — 計測 build の getmem −4 (既定 2012 / 計測 OFF 2008) の帰属 (#1542 = [M11-N100], 親 #1352)

## 0. 結論

- 測定 commit: **`47e4a846`** (コードを変えた最後の commit。変更は `tools/m11/m11_post.py`・`tools/m11/m11_build.sh` の計測専用分岐のみ)。
- 既定 build (計測なし) の survey は HEAD で **870/24/0・getmem 2012** (`repro_1352.sh` と一致)。計測 OFF 系は全構成で **870/24/0** を保ち、受入の基準 (870/24/0) は変わらない。
- **−4 は post の 3 点 (probe 呼出し・wrapper 改名・`m11_dest_obs` 宣言) のどれにも帰属しなかった。** 3 点のいずれを除いても getmem は 2008 のまま (B・D)。さらに、3 点すべてを外して IR を既定と同一 (md5 `baa100ff…`) にした build でも 2008 (C) のため、3 点の組合せでも −4 は消えない。
- −4 は、IR を既定と同一にしても `M11_INSTR_413060=1` の build (C) で現れる。IR は同一 (C の `boot_final3.ll` と A の md5 が一致) なので、**推定**: 差は IR 以外、すなわち計測 flag の C 側への影響 (`ov.o`・`rt.o`・EXPORTS のいずれか) による。IR 以外の差を消去した推論であり、C 側への影響を直接観測したものではない。
- C 側のどの部分が −4 を生むかは**未切り分け**。C 側だけを既定に戻した対照 (`rt.o` だけ・`ov.o` だけ差し替え) は本 run では未実施 (`m11_build.sh` は C 側の計測 flag を個別に切り替える変数を持たない)。
- 各数値は **n=1** (単発)。getmem の決定性 (反復で同値か) は本 run では未確認。決定性の確認は `repro_1542_split.sh 3` で行う (§4)。

## 1. 測定 (測定 commit `47e4a846`・直列・単発・foreground)

素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`)・`work-m11` (`tools/m11/work/`)・`toolchain-emsdk`・`toolchain-retdec`。`m11_gen_ir2.sh` で `ir_conditions.json` を生成 (ldfix F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 F4=10 errors=0)。生成した IR の `ir_sha256` は `08c7b646…` で、REPORT_1352 の `2c68ceae…` とは一致しない (IR 指紋は生成ごとに変わるという REPORT_1352 §4 の既知事項と整合。ldfix の件数は一致)。

**`repro_1352.sh` の実測は `7fc1088f` での 1 回 (1 分 54 秒・load 0.63〜0.97) のみ**。現 HEAD `22d4a2eb` では測っていない (`22d4a2eb` の `repro_1352.sh` PASS という記録は取り消し)。`22d4a2eb` と `7fc1088f` の差は `tools/m11` では空 (`git diff 7fc1088f 22d4a2eb -- tools/m11` は 0 行 = 差分は docs のみ) だが、再現の正本はあくまで実測値である。

**未実施 (本 run の素材不足)**: 下表の C・D の所要時間、A〜D の n≥3、`repro_1352.sh` の `22d4a2eb` での再測定。この run には `work-m11`・`toolchain-*` が無く、`m11_build.sh` は実行できなかった。

**変種の効果の確認 (本 run では未実施。確認コマンドのみ記す)**: post 出力 `work/boot_final3.ll` で、各変種ごとに次を grep する (件数は build 後に測って記入する):
- `noprobe`: `grep -c 'call void @m11_probe(i32 8)' work/boot_final3.ll` → 0 件であること
- `nodecl`: `grep -c 'm11_dest_obs' work/boot_final3.ll` → 0 件であること (宣言・呼出しとも)
- `noren`: `grep -c 'define weak .*@function_413060(' work/boot_final3.ll` で wrapper (`define weak` + `__lifted` 呼出し) が無く、`grep -c 'function_413060__lifted' work/boot_final3.ll` が 0 件であること

PR 本文の「変種の効果の確認済み」は、上記件数を本 run で取ったものではない。確認は未了として扱う。

各行は build (`m11_build.sh`) → survey (`m11_survey.mjs`) の 1 組。env は `M11_OV_413060=0 M11_NEG_413060=0` 固定。

| 構成 | post 計測 flag | 変種 | boot_final3.ll md5 | ok | trap | clobber | getmem | fastmm_getmem_impl | 判定 |
|---|---|---|---|--:|--:|--:|--:|--:|---|
| A 既定 | OFF | — | `baa100ff…` | 870 | 24 | 0 | **2012** | 2096 | 870/24/0 一致 |
| B noprobe | ON | `noprobe` (wrapper の `m11_probe(8)` を除去) | `e4bce794…` | 870 | 24 | 0 | 2008 | 2091 | 870/24/0 一致 |
| C noren | ON | `noren` (413060 を wrapper 化せず本体のまま) | `baa100ff…` (A と同一) | 870 | 24 | 0 | 2008 | 2091 | 870/24/0 一致 |
| D nodecl | ON | `nodecl` (`m11_dest_obs` の宣言・呼出しを除去) | `3a2f0a01…` | 870 | 24 | 0 | 2008 | 2091 | 870/24/0 一致 |

所要 (実測): A は build + survey で 34.8 秒、B は 39.2 秒 (`time` で計測)。C・D は `time` を付けず未計測。

参照: 変更前の HEAD `7fc1088f` で `repro_1352.sh` を測ったときの `instr_off` (計測 ON・probe あり・dest 読出しあり) は getmem 2008・870/24/0 (`work/repro_1352/survey_instr_off.out`)。`47e4a846` では同じ `repro_1352.sh` の計測 ON 行 (probe あり) は再測していない (B・C・D で代替)。本 commit の変更は計測 OFF の出力を変えない (A の boot_final3.ll md5 が `7fc1088f` の既定 build と一致 = `baa100ff…`)。

## 2. 解釈

- **3 点は単独でも組合せでも −4 を作らない**: B (probe 呼出しだけ除去) も D (宣言だけ除去) も 2008。C は 3 点すべてを外し IR を既定と同一に戻したが、なお 2008。よって −4 は post の 3 点に由来しない。
- **IR は同一なのに差が出る**: C の `boot_final3.ll` は A と md5 一致。**推定**: 差は IR 以外、すなわち計測 flag の C 側への影響 (`rt.o` が計測の実体 (`m11_dest_obs`・`g_dest_h`) を持つ・EXPORTS の追加・`ov.o` の計測分岐) に限られる。
- `ov.o` について: `m11_ov.c` の `function_413060` 本体 (probe 呼出し `m11_probe(8)` と `m11_dest_obs(dest)` を含む) は `#if M11_OV_CLASSCREATE || M11_OV_413060` の内側にあり、測定条件 (`M11_OV_413060=0`・`M11_OV_CLASSCREATE=0`) では本体はコンパイルされない。したがって「`ov.o` が `function_413060` 本体に probe を入れる」は**本 run では確認されていない** (ソースの `#if` 条件からの推定)。`ov.o` の `M11_INSTR_413060` 分岐が実際に何を生むかは `nm`/`objdump` で `.o` を見て未確認。
- **IR 同一・計測 flag のみ違う A と C の比較**: 同じ `baa100ff…` の IR で getmem が 2012 (A, flag OFF) と 2008 (C, flag ON)。IR を揃えた上での差なので、計測 flag の C 側への影響が −4 の候補 (推定)。ただし flag が C のどこに効くかは §3 の未解決。
- 過去の survey 判定 (ok/trap/clobber) は全構成で同一のため、−4 は判定には出ない (元の 871/23 とは別事象)。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| C 側の計測 flag のうち、−4 を生む部分の切り分け (`ov.o` の `function_413060` 本体 / `rt.o` の計測実体 / EXPORTS のどれか) | 計測 build の getmem 計数が既定と 4 ずれる。survey 判定には出ない | #1701 ([M11-N116]) |
| 既定 2012 と計測 OFF 2008 の差の**意味** (実行の差か、計数の差か) | `fastmm_getmem_impl` も 2096 → 2091 で同方向にずれる。FastMM の入口計数が減っているのか未確認 | #1701 ([M11-N116]) |

### 3b. 子 issue

残件は「C 側の計測 flag のどの部分が −4 を生むか」の切り分けで、C 側の `rt.o`・`ov.o` を個別に差し替える対照が必要。1 run に収まらないため #1701 ([M11-N116]) として分離した (受入条件・必要素材を本文に記載)。

## 4. 再現

- 3 点の切り分け (本 REPORT の A〜D): `tools/m11/m11_build.sh` の変種 `M11_PROBE_VARIANT` (`noprobe` / `noren` / `nodecl`) と `M11_INSTR_413060=1` を指定して build → `m11_survey.mjs` を直列実行。`M11_PROBE_VARIANT` は `M11_INSTR_413060=1` のときだけ有効 (それ以外は `m11_post.py` が exit する)。
- 既定と計測 OFF の基準: `bash tools/m11/trap_triage/repro_1352.sh` (判定 `PASS`)。
- 作業ディレクトリは `tools/m11/`。`work/` は `m11_gen_ir2.sh` で生成する (`work-m11` 展開後に実行。`work-m11` 同梱の `work/` は `m11_gen_ir2.sh` で作り直し済み)。
- **A〜D の表を 1 コマンドで再現するドライバ**: `bash tools/m11/trap_triage/repro_1542_split.sh [N]` (N = 反復回数・既定 1)。`A_default`・`B_noprobe`・`C_noren`・`D_nodecl` を直列に build → survey し、`work/split_1542/table.tsv` に `構成 / 回 / IR md5 / ok / trap / clobber / getmem / fastmm_getmem_impl` を出す。`work/split_1542/ir_*.ll` に各 IR を残す。n≥3 の min–max は `N=3` で取り、`table.tsv` を集計する。
- 本 run では `work-m11` が無く未実行 (ドライバの構文確認 `bash -n` のみ)。§1 の表の数値は REPORT 作成時点の測定 (当時の `work/split_1542/survey_*.out`。本 run の `work/` には無い) からの転記で、このドライバ経由の再測定ではない。ドライバでの再測定は `work-m11` 付きの run で行う。
- `repro_1352.sh` の再測定は本 run では未実施 (§1 参照)。
