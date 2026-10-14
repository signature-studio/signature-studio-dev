# REPORT_2212 — rt.o の静的データ配置と関数有無の対照 (#2212 = [M11-N145], 親 #1952)

## 0. 結論

- 測定 commit: **`129a9c6a`** (測定に使ったコードを変えた最後の commit。main 取り込み merge。`dade5b85` 以降の差分は `tools/m11/ldfix/` の監査・triage スクリプトと報告で、この commit の `tools/m11` (trap_triage 除く) 全体で測り直した。§7)。下の表 (§2) は `129a9c6a` で測った n=3 (計 30 セル) の値で、生値は `table_2212.tsv`・`addr_2212.txt` に tracked。
- **受入条件 1 (リンク後の実アドレス)**: 測定済み (§3)。`g_dest_h` は **全構成で `10250f20`** で、PRE64・PRE4096 でも動かない。pad は `.bss` 上で `g_rec_h` の後ろに置かれ、`g_dest_h` より前には入らない。
- **受入条件 2 (関数のみ・データ無しの対照)**: **部分達成**。NODATA は getmem **2012** (R0_rtOFF と同じ)・survey 870/24/0 で、C_noren の 2008 から動く。ただし NODATA は関数本体の書き込み (`g_dest_h`・`g_rec_*`) も消しているため、「関数のみ (本体そのまま)」の対照にはなっていない (§4)。
- **受入条件 3 (n=3 の決定性)**: 達成。`129a9c6a` で全 10 構成 × 3 回 (30 セル) を測り、IR md5・undefined・ok/trap/clobber・getmem・fastmm_getmem_impl・実アドレスが全セルで一致した (§2・`table_2212.tsv`・`addr_2212.txt`)。
- **受入条件 4**: 既定 (A_default) は全 3 回 870/24/0・getmem 2012 で、変えていない。
- **機序は未確定**: PRE64 と PRE4096 は両方 `g_dest_h` が同じ位置で、結果だけ違う (2006 と 2008)。「`g_dest_h` のアドレスが変わるから」では説明できない (§4)。

## 1. 追加した対照 (既定 0・既定の build は従来と同一)

- `tools/m11/m11_rt.c`: `M11_RT_NODATA=1` を追加。`m11_dest_obs` の本体は残す (`dest` を volatile で読むだけ・`g_dest_h`・`g_rec_*`・`g_dest_n` への書き込みなし)。エクスポートは定数を返す。
- `tools/m11/m11_build.sh`: `M11_LINK_MAP=<path>` で wasm-ld の map を出す (未指定なら従来どおり)。`-DM11_RT_NODATA` を追加し、stamp は knob 0 のとき従来と同一。
- `tools/m11/trap_triage/repro_1952_rt_mech.sh`: NODATA 構成を追加。各構成の map を `work/split_1952/map_<tag>.txt` に残し、`addr.txt` に実アドレスを出す。

## 2. 測定

測定 commit `129a9c6a`・直列・foreground・`FL_WIN64_DIR` (`[WIN64]`・`fl-win64` を展開) 設定・`work-m11` (`[WORK-M11]`) を repo 直下で展開 (`tar --zstd -xf` は `tools/m11/work/` を含むため repo ルートで行う) し、`m11_gen_ir2.sh` で IR を再生成 (ldfix: F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=36 errors=0。REPORT_1952 と一致)。`[EMSDK]` は `toolchain-emsdk` 素材 (emcc 配置を確認) を使用。

- IR 再生成 `m11_gen_ir2.sh`: rc=0・所要 49.97 秒 (`time` real 実測)。
- n=3 (`repro_1952_rt_mech.sh 3`): rc=0・所要 18 分 18.6 秒 (`time` real 実測)。
- 前回の測定 commit `dade5b85`・前々回の `6d59918b`・`8b00eecd` の表と、本測定の 30 セルは全行一致した (IR md5・undefined・ok/trap/clobber・getmem・fastmm・実アドレス)。`table.tsv` は tracked の `table_2212.tsv` と `diff` 出力が空、`addr.txt` は行頭の `[split_1952][addr] ` を除くと `addr_2212.txt` と `diff` 出力が空だった。

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

上表は 3 回とも同じ値 (30 セル中、全セル一致)。生値は `trap_triage/table_2212.tsv` (30 行: 構成・回・IR md5・undefined・g_dest_h offset・ok・trap・clobber・getmem・fastmm_getmem_impl) に tracked。実アドレスは `trap_triage/addr_2212.txt` (30 行・各セルの symbol VA)。map の全行は載せない (必要行は §3)。`map_<tag>.txt` は gitignore の `work/split_1952/` に残る。

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
| 関数本体 (書き込み) を残し static data だけ外す対照。NODATA の 2012 がデータ由来か本体由来かの確定 (受入条件 2 の残り) | 機序の確定 | #2275 ([M11-N147]) |
| heap 開始位置・後続 static (`g_slots` 等) のアドレスと getmem の関係 | PRE64・PRE4096 の差 (2006 と 2008) の機序 | #2275 ([M11-N147]) |
| (解消済み) 現 HEAD での再測定 (10 構成 × n=3) と 30 セルの生値の tracked 化 | — | — |

## 6. 再現

- `bash tools/m11/trap_triage/repro_1952_rt_mech.sh [N] [CONFIG...]` (N = 反復回数・既定 1。`NODATA` を含む 10 構成)。表は `work/split_1952/table.tsv`、実アドレスは `work/split_1952/addr.txt`、map は `work/split_1952/map_<tag>.txt` (すべて gitignore)。tracked 版は `table_2212.tsv`・`addr_2212.txt`。
- 前提: `work/` が `m11_gen_ir2.sh` 生成済み・`FL_WIN64_DIR` 設定済み・[EMSDK] 配置済み (エントリ ID は `docs/REFERENCES.md`)。
- 素材: `oc_artifacts: fl-win64 work-m11 toolchain-emsdk` (`docs/WORKFLOW.md` §11)。

## 7. 測定 commit からの差分

測定 commit は `129a9c6a` (§0)。この commit の `tools/m11` で §2 の表を測った。前回の測定 commit は `dade5b85`、その前は `6d59918b`、さらに前は `8b00eecd`。

`6d59918b` から `dade5b85` までの差分 (3 回目の main 取り込みで入った分。測定 build の入力になるものを含む):

```
git diff 6d59918b dade5b85 --shortstat -- tools/m11 ':!tools/m11/trap_triage'
 10 files changed, 575 insertions(+), 28 deletions(-)
git diff 6d59918b dade5b85 --stat -- tools/m11 ':!tools/m11/trap_triage' ':!tools/m11/ldfix'
 tools/m11/REPORT_APPENDIX_2163.md | 68 +++++++++++++++++++++++++++++++++++++++
 tools/m11/REPORT_N1415.md         | 22 +++++++------
 tools/m11/m11_build.sh            |  6 ++--
 tools/m11/m11_ov.c                | 20 ++++++++++++
 tools/m11/m11_post.py             |  7 +++-
git diff 6d59918b dade5b85 --stat -- tools/m11/m11_rt.c tools/m11/m11_gen_ir2.sh tools/m11/ldfix/ldfix.py tools/m11/ldfix/ldmach.py tools/m11/ldfix/ldframe.py
(出力は空)
```

- `tools/m11/m11_build.sh`: main 由来の `-DM11_INSTR_60A270`・`-DM11_PRINT_DEST_2118` が `CF` に入った。競合はこの `CF=` 行のみ (と `docs/DOC_MAP.md` の索引表)。main の 2 つのフラグを残し、本 PR の `-DM11_RT_NODATA` を行末に足して解消した。
- `tools/m11/m11_ov.c`・`tools/m11/m11_post.py`: `M11_INSTR_60A270`・`M11_PRINT_DEST_2118` の計測コード (既定 0 では無効)。`m11_rt.c`・IR の生成経路 (`m11_gen_ir2.sh`・`ldfix.py`・`ldmach.py`・`ldframe.py`) は変わっていない。
- `dade5b85` で全 30 セルを測り直し、`6d59918b`・`8b00eecd` の値と全行一致した (§2)。

`8b00eecd` から `6d59918b` までの差分 (2 回目の main 取り込み): `m11_build.sh` (`-DM11_INSTR_40F960`・#1317) と `m11_ov.c` (`M11_INSTR_40F960`、既定 0) のみが ldfix 以外の変更で、`m11_rt.c` は変わらない。

前々回の測定 commit `7d3e5cad` から `8b00eecd` までの差分 (`8b00eecd` の main 取り込みで入った分):

```
git diff 7d3e5cad 8b00eecd --shortstat -- tools/m11 ':!tools/m11/trap_triage'
 22 files changed, 1264 insertions(+), 9 deletions(-)
git diff 7d3e5cad 8b00eecd --stat -- tools/m11/m11_rt.c tools/m11/m11_build.sh
 tools/m11/m11_build.sh |  4 ++--
 tools/m11/m11_rt.c     | 14 +++++++++++++-
```

- `tools/m11/m11_rt.c`: main 由来の `M11_DEST_GUARD` (#1547) を追加。既定 0 では `#if M11_DEST_GUARD` の分岐は無効だが、`unsigned long long k = g_dest_n;` の読出しが volatile な `dest` の読出しより前に移る。このため `rt.o` の機械語は変わりうるので、`8b00eecd` で全 30 セルを測り直し、`7d3e5cad` の値と全行一致した。
- `tools/m11/m11_build.sh`: `CF` に `-DM11_DEST_GUARD=${M11_DEST_GUARD:-0}` を追加。stamp は `M11_DEST_GUARD` 非 0 のときだけ `-guard` を付け、既定 0 では従来と同じ値。

測定 commit `129a9c6a` から現 HEAD までの `tools/m11` のうち trap_triage を除く差分は 0 行 (`git diff 129a9c6a HEAD -- tools/m11 ':!tools/m11/trap_triage'` の出力は空)。この commit 以前の `dade5b85` から `129a9c6a` までの差分 (測定前の main 取り込み 2 回。`ldfix` のみ) は次のとおり。

```
git diff dade5b85 129a9c6a --shortstat -- tools/m11 ':!tools/m11/trap_triage'
 9 files changed, 576 insertions(+), 34 deletions(-)
```

9 files は `tools/m11/ldfix/` の監査・triage スクリプト (`audit_lsf.py`・`audit_lsf_disp.py`・`ld111_e2e.sh`・`negctl_484.sh`・`triage_ld111.py`) と報告・results で、IR 再生成が呼ぶ `ldfix.py`・`ldmach.py`・`ldframe.py` は変わっていない。差分を含む `129a9c6a` で 30 セルを測り直し、`dade5b85` の値と全行一致した。後続の commit は REPORT・索引 (`docs/DOC_MAP.md`) の文書のみを変え、測定 build の入力は変えていない。
