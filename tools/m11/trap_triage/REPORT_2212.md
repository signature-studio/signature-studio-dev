# REPORT_2212 — rt.o の静的データ配置と関数有無の対照 (#2212 = [M11-N145], 親 #1952)

## 0. 結論

- 測定 commit: **`16f4f199`** (測定に使ったコードを変えた最後の commit。n=3 は HEAD `16f4f199` で再測定した)。
- **受入条件 1 (リンク後の実アドレス)**: 測定済み (§3)。`g_dest_h` は **全構成で `10250f20`** で、PRE64・PRE4096 でも動かない。pad は `.bss` 上で `g_rec_h` の後ろに置かれ、`g_dest_h` より前には入らない。
- **受入条件 2 (関数のみ・データ無しの対照)**: **部分達成**。NODATA は getmem **2012** (R0_rtOFF と同じ)・survey 870/24/0 で、C_noren の 2008 から動く。ただし NODATA は関数本体の書き込み (`g_dest_h`・`g_rec_*`) も消しているため、「関数のみ (本体そのまま)」の対照にはなっていない (§4)。
- **受入条件 3 (n=3 の決定性)**: 全 10 構成 × 3 回で、ok/trap/clobber・getmem・fastmm_getmem_impl・IR md5 がすべて一致。
- **受入条件 4**: 既定 (A_default) は全 3 回 870/24/0・getmem 2012 で、変えていない。
- **機序は未確定**: PRE64 と PRE4096 は両方 `g_dest_h` が同じ位置で、結果だけ違う (2006 と 2008)。「`g_dest_h` のアドレスが変わるから」では説明できない (§4)。

## 1. 追加した対照 (既定 0・既定の build は従来と同一)

- `tools/m11/m11_rt.c`: `M11_RT_NODATA=1` を追加。`m11_dest_obs` の本体は残す (`dest` を volatile で読むだけ・`g_dest_h`・`g_rec_*`・`g_dest_n` への書き込みなし)。エクスポートは定数を返す。
- `tools/m11/m11_build.sh`: `M11_LINK_MAP=<path>` で wasm-ld の map を出す (未指定なら従来どおり)。`-DM11_RT_NODATA` を追加し、stamp は knob 0 のとき従来と同一。
- `tools/m11/trap_triage/repro_1952_rt_mech.sh`: NODATA 構成を追加。各構成の map を `work/split_1952/map_<tag>.txt` に残し、`addr.txt` に実アドレスを出す。

## 2. 測定

測定 commit `16f4f199`・直列・foreground・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`work-m11` を展開して `m11_gen_ir2.sh` で IR を再生成 (ldfix: F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 errors=0。REPORT_1952 と一致)。

- n=3 (HEAD `16f4f199`): 所要 15 分 34 秒 (`time` 実測)・開始時 load 0.85・4 vCPU。
- n=1 (HEAD `16f4f199`): 所要 5 分 11 秒 (`time` 実測)・開始時 load 0.35。
- n=3 の前 (変更を commit する前の同内容): 所要 15 分 26 秒。表は下の n=3 と一致。

| 構成 | IR md5 | undefined | ok/trap/clobber | getmem | fastmm_getmem_impl | g_dest_h 実アドレス |
|---|---|--:|--:|--:|--:|---|
| A_default | baa100ff | 0 | 870/24/0 | 2012 | 2096 | (計測なし) |
| C_noren | baa100ff | 0 | 870/24/0 | 2008 | 2091 | 10250f20 |
| R0_rtOFF | baa100ff | 0 | 870/24/0 | 2012 | 2096 | (計測なし) |
| R1_rtON | baa100ff | 0 | 870/24/0 | 2008 | 2091 | 10250f20 |
| PRE64 | baa100ff | 0 | **872/22/0** | **2006** | 2089 | 10250f20 |
| PRE4096 | baa100ff | 0 | 870/24/0 | 2008 | 2091 | 10250f20 |
| POST64 | baa100ff | 0 | **872/22/0** | **2006** | 2089 | 10250f20 |
| POST4096 | baa100ff | 0 | 870/24/0 | 2008 | 2091 | 10250f20 |
| EMPTY | baa100ff | 0 | 870/24/0 | 2008 | 2091 | 10250f20 |
| NODATA | baa100ff | 0 | 870/24/0 | **2012** | 2096 | (データ無し) |

上の 10 構成は各 3 回とも同じ値だった (n=3・HEAD `16f4f199`)。

## 3. リンク後の実アドレス (wasm 上の VA・map から)

| 構成 | g_dest_h | g_rec_st | g_rec_h | 追加のデータ |
|---|---|---|---|---|
| C_noren | 10250f20 | 1029ba70 | 1029ea70 | (なし) |
| PRE64 | 10250f20 | 1029ba70 | 1029ea70 | g_pad_pre 1029fa70 (0x40 B)。後続 g_slots が 1029fab0 へ動く |
| PRE4096 | 10250f20 | 1029ba70 | 1029ea70 | g_pad_pre 1029fa70 (0x1000 B)。g_slots が 102a0a70 へ動く |
| POST64 | 10250f20 | 1029ba70 | 1029ea70 | g_pad_post 1029fa70 |
| POST4096 | 10250f20 | 1029ba70 | 1029ea70 | g_pad_post 1029fa70 |
| EMPTY | 10250f20 | 1029ba60 | 1029ea60 | g_dest_n 1029fa60 (並びが変わる) |

- `g_dest_h` は全構成で同じ VA (`.data` 内)。pad は `.bss` 内で `g_rec_h` の後ろ (`1029fa70`) に入り、`g_dest_h` の前には入らない (`g_dest_h` は `.data`、pad は `.bss` で別セクション)。
- PRE64 と PRE4096 で `g_dest_h` は動かないのに結果が違う (2006 と 2008)。pad の後ろのデータ (`g_slots`) の位置は PRE64 と PRE4096 で違うので、その位置 (あるいは後続データ・heap 開始位置) が効いている可能性がある。**未確定** (§4)。
- `llvm-nm` は linked wasm の static data シンボル (`g_dest_h` 等) を出さない。実アドレスは map からしか取れない。

## 4. 解釈

- **帰属 (REPORT_1701・REPORT_1952 から継続)**: −4 は rt.o の計測 flag に由来する (R0 2012 / R1 2008)。
- **関数の本体は無関係** (EMPTY 2008 = C_noren)。
- **NODATA (2012) は R0 と同じ値**。データを外すと計測 ON でも 2012 に戻る。ただし NODATA は `m11_dest_obs` の stores (`g_dest_h`・`g_rec_*`) を消しているので、「データ無し」と「関数本体の変更」が混ざっている。EMPTY は本体を空にした対照で 2008 だったので、本体の変更だけでは 2012 にならない。この 2 つを合わせると「`g_dest_h` 等への書き込みを含む関数本体」か「その static data」のどちらかが 2008 を生むことになるが、区別はこの測定では出来ていない (**未確定**)。
- **pad の効き方は配置ではなく後続データの位置**: `g_dest_h` は動かず、PRE・POST で `.bss` 上の後続 (`g_slots` 等) が動く。PRE64 と POST64 は 2006、PRE4096 と POST4096 は 2008 で、pad の量に比例しない (REPORT_1952 と同じ)。アドレス由来の値 (heap 開始位置の丸め等) の仮説は残るが、heap 開始位置は未測定。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 関数本体 (書き込み) を残し static data だけ外す対照。NODATA の 2012 がデータ由来か本体由来かの確定 (受入条件 2 の残り) | 機序の確定 | #2212 (本 issue に残す。Refs) |
| heap 開始位置・後続 static (`g_slots` 等) のアドレスと getmem の関係 | PRE64・PRE4096 の差 (2006 と 2008) の機序 | #2212 (本 issue に残す。Refs) |

## 6. 再現

- `bash tools/m11/trap_triage/repro_1952_rt_mech.sh [N] [CONFIG...]` (N = 反復回数・既定 1。`NODATA` を含む 10 構成)。表は `work/split_1952/table.tsv`、実アドレスは `work/split_1952/addr.txt`、map は `work/split_1952/map_<tag>.txt` (すべて gitignore)。
- 前提: `work/` が `m11_gen_ir2.sh` 生成済み・`FL_WIN64_DIR` 設定済み・[EMSDK] (`/opt/emsdk`) 配置済み。

## 7. 測定 commit からの差分

測定 commit `16f4f199` = 測定時の HEAD。本 REPORT を追加した後の差分は REPORT 自体のみ。
`git diff 16f4f199 HEAD -- tools/m11 ':!tools/m11/trap_triage/REPORT_2212.md'` の出力は空。
