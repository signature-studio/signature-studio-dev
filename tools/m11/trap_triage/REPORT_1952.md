# REPORT_1952 — rt.o の計測 flag が getmem −4 を生む機序の切り分け (#1952 = [M11-N129], 親 #1701)

## 0. 結論

- 測定 commit: **`b263a087`** (測定時にコードを変えた最後の commit)。HEAD も同じ commit で、n=1 を HEAD で再測定し、n=3 の表と全セル一致 (§3)。
- **rt.o のコード本体は −4 に効かない**: `m11_dest_obs` の本体だけ空にした構成 (EMPTY) は 2008 (計測 ON と同じ)。
- **rt.o の静的データ領域に手を入れると getmem が動く**: 静的 pad を `g_dest_h` の前 (PRE64) または後ろ (POST64) に 64 B 入れると getmem が **2006** に落ち、survey 判定も **872/22/0** に変わる。pad を 4096 B にすると動かない (PRE4096・POST4096 は 2008 / 870/24/0)。量に比例して単調に動くのではない。
- 機序の有力仮説: rt.o の静的データの**サイズ・アラインメント依存**による、アドレス由来の値の変化。**未確定**。リンク後の実アドレスは未測定で、関数のみ (データ無し) の対照も未実施 (→ 子 #2212, §5)。
- 既定の基準 (870/24/0) は変えていない。A_default は全 3 回で 870/24/0・getmem 2012。

## 1. 追加した対照 knob (既定 0。既定の build の出力は従来と同一)

`tools/m11/m11_rt.c` (`M11_INSTR_413060` 有効時のみ):

- `M11_RT_PADPRE=N`: `g_dest_h` の前に N B の静的 pad (配置と量が動く)
- `M11_RT_PADPOST=N`: `g_rec_*` の後に N B の静的 pad (量だけ動く。`g_dest_h` の配置は動かない)
- `M11_RT_EMPTY=1`: `m11_dest_obs` の本体だけ空にする (関数・静的データは残す)

`tools/m11/m11_build.sh`: 上の 3 つを `-D` で渡し、`rt.o` の cache stamp (`S_NEG`) に含める (knob が 0 のときの stamp 文字列は従来と同一)。既定の IR md5 は全構成で `baa100ff` (REPORT_1701 と一致) で、knob 未指定の build は従来と同じ。

## 2. 切り分けの定義

`tools/m11/trap_triage/repro_1952_rt_mech.sh`。基準は C_noren (計測 ON・IR 既定同一。REPORT_1701 の C と同じ)。

| 構成 | 内容 |
|---|---|
| A_default | 計測 OFF (既定) |
| C_noren | 計測 ON・IR 既定同一 (基準) |
| R0_rtOFF | C + rt.o 計測 OFF (データ・関数・EXPORTS を外す。REPORT_1701 と同じ) |
| R1_rtON | A + rt.o だけ計測 ON |
| PRE64 / PRE4096 | C + `g_dest_h` の前に 64 B / 4096 B の pad |
| POST64 / POST4096 | C + `g_rec_*` の後に 64 B / 4096 B の pad |
| EMPTY | C + `m11_dest_obs` の本体だけ空 |

## 3. 測定

**n=3 (測定 commit `b263a087`・直列・単発・foreground)**: 4 vCPU・開始時 load 0.78。所要 12 分 15 秒 (`time` 実測)。素材: `fl-win64`→`$RUNNER_TEMP/fl-win64`、`work-m11`→`tools/m11/work/` (展開後 `m11_gen_ir2.sh` で IR 再生成: ldfix=applied・F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 errors=0、REPORT_1701 と一致)、`toolchain-emsdk`→[EMSDK]。

| 構成 | boot_final3.ll md5 | undefined symbol | ok/trap/clobber | getmem | fastmm_getmem_impl |
|---|---|--:|--:|--:|--:|
| A_default (3 回とも同じ) | baa100ff | 0 | 870/24/0 | 2012 | 2096 |
| C_noren (3 回とも同じ) | baa100ff | 0 | 870/24/0 | 2008 | 2091 |
| R0_rtOFF (3 回とも同じ) | baa100ff | 0 | 870/24/0 | 2012 | 2096 |
| R1_rtON (3 回とも同じ) | baa100ff | 0 | 870/24/0 | 2008 | 2091 |
| PRE64 (3 回とも同じ) | baa100ff | 0 | **872/22/0** | **2006** | 2089 |
| PRE4096 (3 回とも同じ) | baa100ff | 0 | 870/24/0 | 2008 | 2091 |
| POST64 (3 回とも同じ) | baa100ff | 0 | **872/22/0** | **2006** | 2089 |
| POST4096 (3 回とも同じ) | baa100ff | 0 | 870/24/0 | 2008 | 2091 |
| EMPTY (3 回とも同じ) | baa100ff | 0 | 870/24/0 | 2008 | 2091 |

**HEAD `b263a087` で n=1 再測定** (同じ commit。所要 3 分 58 秒・開始時 load 1.06): 上表の 1 回目と全セル一致。

## 4. 解釈

- **帰属 (REPORT_1701 から継続)**: −4 は rt.o の計測 flag に帰属する (R0 で 2012、R1 で 2008)。
- **コード本体は無関係**: EMPTY (関数と静的データは残し、本体だけ空) は 2008。C_noren と一致。
- **静的データ領域が効く**: PRE64・POST64 で getmem が 2006 に動く。pad を 4096 B にすると動かない。したがって「データを増やすと単調に変わる」ではない。アラインメントや実アドレス由来の値 (ヒープ開始位置の丸めなど) が効いている可能性がある (仮説)。
- **survey 判定も動く**: PRE64・POST64 は 872/22/0 で、既定の基準 870/24/0 と違う。REPORT_1701 §3 の「survey 判定には出ない」は、R0・R1・EMPTY 等の測定した構成に限った話で、データ配置を変えると判定まで動く。
- **未確定**: (a) リンク後の実アドレス (`g_dest_h`・`g_rec_*`・pad) は未測定。`llvm-nm` の値は rt.o の object 内の位置で、リンク後の値ではない。(b) 関数のみ残してデータ無しの対照は未実施 (R0 は関数・データ・EXPORTS を同時に外している)。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| リンク後の実アドレスの測定 (配置仮説の確定) と、関数のみ (データ無し) の対照 | 機序 (配置か関数の有無か) の確定。受入条件 1 の残り | #2212 ([M11-N145]) |
| PRE64・POST64 で survey 判定 (872/22/0) が動く理由 | 既定 build も同種の影響を受けるか | #2212 ([M11-N145]) |

## 6. 再現

- `bash tools/m11/trap_triage/repro_1952_rt_mech.sh [N] [CONFIG...]` (N = 反復回数・既定 1。CONFIG で一部だけ実行)。出力は `work/split_1952/table.tsv` (gitignore)。
- 前提: `work/` が `m11_gen_ir2.sh` 生成済み・`FL_WIN64_DIR` 設定済み・[EMSDK] 配置済み。

## 7. 測定 commit からの差分

測定 commit `b263a087` = HEAD のため、コード差分は 0 (本 REPORT の追加と issue 範囲の縮小のみ)。`git diff b263a087 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_1952.md'` の出力は空。
