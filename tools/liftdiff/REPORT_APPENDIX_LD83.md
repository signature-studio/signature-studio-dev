# liftdiff REPORT 付録: LD-83 (#2192) wasm 側の site trace (IR の conditional br・import call) と native 1801c5e84 の je・HeapFree の対応

親 issue #1907 (LD-68)。前提は `REPORT_APPENDIX_LD68.md` §4・§5、`REPORT_APPENDIX_LD57.md` §3、`REPORT_APPENDIX_LD67.md` (計装の方式)。

## 結論

- 受入条件 1 (方式の決定と実装) は**部分達成**。方式は「IR 側の site 記録」: block 内の conditional br と import call の直前に volatile store を入れ、block VA・種別・block 内の順番・br の条件値を記録する。
  全命令の VA は RetDec IR に無い (`tools/ott/work/ott.ll` に命令単位の VA 注記は 0 件、`dec_label_pc_` は block 先頭の 1943 件のみ)。命令単位の完全な trace は未達で、子 #2801 (LD-131) に切り出す。
- 既定 build との差 0: `results/ld67/compare_blk.py` の 12 case で `cases=12 diff=0` (測定 commit `0913730a` で 2 回)。block 件数は LD-67 と一致 (27・4・287・6・42・43・304・10)。
- 受入条件 2 (1c0b6f・1c0b82 の wasm 側の位置) は **site 単位で対応付けた**。vm0 の `1c0b6c` の br は 5 回とも native の `je` (1c0b6f) の成立・不成立と一致し、HeapFree の call site は 1 回で native (vm0) の 1 回と一致する。
- u16 は wasm 側で `1c0b71` の HeapFree call site の直後に `wasm_trap` する。原因は shim の `block_ok` が不正ポインタを読むこと (§5)。trap より後の block は取れないため、受入 3 の後続 block の対応は未達。子 #2802 (LD-132) に切り出す。
- 残り 5 関数 (受入の範囲外) は #2193 (LD-84)。

## 1. 測定条件

- 測定 commit: `0913730a` (`feat(liftdiff): record wasm br and import-call sites in IR block trace (Refs #2192)`。コード差分の最終 commit)。HEAD での再測定はこの commit で行った。
- 測定 runner: 4 vCPU。load average (測定時) 0.03 / 0.15 / 0.11 (`uptime` 19:25:50 UTC)。
- 素材: `work-m6-ott` (`tools/ott/work/ott.ll`・`tools/m6/work`)・`work-liftdiff` (`tools/liftdiff/work/ott_old`)・`plugins-ott` と `analysis-ott-binaries` (環境変数 `PLUGINS_DIR` で指定。`[ANALYSIS-DIR]` 配下)・`toolchain-emsdk` (`[EMSDK]`)。`fl-win64` は本測定では展開していない (run に不要だった)。
- build: `python3 ldlib/build_wasm.py targets/ott_old_site.json --force` (rc 0・5.9 s・`sig_mismatch` 0・`undefined` 0)。
- run: `python3 liftdiff.py run targets/ott_old_site.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --nobuild --notrace --json <out>`。既定版は `targets/ott_old.json` で同じ引数 (各 5.5 s)。
- 比較: `python3 results/ld67/compare_blk.py work/ld83/head_def_r<k>.json work/ld83/head_site_r<k>.json` (`k`=1,2)。両方 `cases=12 diff=0`。

## 2. 方式 (site trace)

`ldlib/irtool.py` の `instrument(..., sites=True)` (target の `site_trace: true`・`targets/ott_old_site.json`)。block 入口の記録 (LD-64 の `ld_blk_arr`) に、次の 2 種を追加で同じ配列へ volatile store する。値は 64 bit で、wasm 側の `ld_blk` の出力 (`blk` の `0x..` 列) にそのまま入る。

| 記録点 | IR 上の位置 | 値 |
|---|---|---|
| block 入口 (LD-64) | `dec_label_pc_<VA>:` の直後 | VA (33 bit) |
| conditional br | `br i1 %c, label ...` の直前 | `1<<62 \| 1<<56 \| ord<<40 \| cond<<39 \| VA & 0xffffffff` |
| import call | `call ... @<declare 名>` (`SKIP_DECL` 以外) の直前 | `1<<62 \| 2<<56 \| ord<<40 \| VA & 0xffffffff` |

- `ord` は同じ block 内の site の通し番号 (0 始まり。block 入口で 0 に戻る)。`cond` は br の条件の真偽 (1 = 真。`br i1 %c, label %A, label %B` は真のとき A へ行く)。
- VA は下位 32 bit だけを残す。復元は `0x100000000 | 値`。

方式の判断: RetDec 由来の IR に命令の VA が無いため、命令単位の VA を残すには RetDec 側の変更が要る (D5 の RetDec 路線で新規作業になる)。その代わり、native の `je` は IR の conditional br、native の `call [IAT]` は IR の import call に 1 対 1 で対応する。本付録の対応は、この**構造上の対応**による (IR の block 1c0b6c は `icmp eq %arg1, 0` と `br` で、native の `test rcx,rcx` と `je 1c0ba8` に対応する。block 1c0b71 は HeapFree の call を 1 つだけ持ち、native の `1c0b71`〜`1c0b8c` の範囲にある `call [IAT]` (`1c0b82`) に対応する)。

## 3. 測定結果 (HEAD = `0913730a`・r1 と r2 の blk 列は全 case で一致)

| 関数 | pattern | 既定 outcome | 計装 outcome | 判定 | blocks | sites | 計 |
|---|---|---|---|---|---|---|---|
| 1ab1d0 | vm0 / u16 | equal | equal | SAME | 0 | 0 | 0 |
| 1ab258 | vm0 / u16 | equal | equal | SAME | 0 | 0 | 0 |
| 1c5e84 | vm0 | diff | diff | SAME | 27 | 22 | 49 |
| 1c5e84 | u16 | wasm_trap | wasm_trap | SAME | 4 | 3 | 7 |
| 1c621c | vm0 | diff | diff | SAME | 287 | 189 | 476 |
| 1c621c | u16 | wasm_trap | wasm_trap | SAME | 6 | 4 | 10 |
| 1c682c | vm0 | diff | diff | SAME | 42 | 39 | 81 |
| 1c682c | u16 | diff | diff | SAME | 43 | 40 | 83 |
| 1c69cc | vm0 | diff | diff | SAME | 304 | 204 | 508 |
| 1c69cc | u16 | wasm_trap | wasm_trap | SAME | 10 | 7 | 17 |

`cases=12 diff=0`。blocks の列は LD-67 §4 の値と一致し、block 記録は変わっていない。

## 4. 1c0b6f (je) と 1c0b82 (HeapFree) の wasm 側の位置 (1801c5e84)

記号: `Bxxx` = block 入口、`Jxxx.k=c` = site の br (`k` = ord、`c` = cond)、`Cxxx.k` = site の import call。`xxx` は VA の下 20 bit。

- **vm0** (全 49 件のうち `1c0b6c` の br): cond = `[0, 1, 1, 1, 1]`。native (LD-57 §3) の `rcx` は `[1720f3000 (je 不成立), 0, 0, 0, 0]` で、`je` の成立 (`rcx=0`) は cond=1 と一致する。
- **vm0 の HeapFree**: `1c0b71` の call site (`C0b71.0`) は 1 回。native (vm0) の `KERNEL32!HeapFree` も 1 回。
  - 直後の `J0b71.1=0` で HeapFree の戻りは偽 (`1c0b8c` へ)。
- 先頭の列 (vm0): `B1c5e84 J5e84.0=0 B1c5eb8 B1c0b6c J0b6c.0=0 B1c0b71 C0b71.0 J0b71.1=0 B1c0b8c B1bafb0 B1c20c8 C20c8.0 J20c8.1=1 …`
- **u16** (全 7 件): `B1c5e84 J5e84.0=0 B1c5eb8 B1c0b6c J0b6c.0=0 B1c0b71 C0b71.0` → `wasm_trap`。
  - `1c0b6c` の br は cond=0 (`je` 不成立) で、native (u16) の 1 回目と一致する (`rcx=1400000001`)。
  - native は HeapFree を 5 回呼んで処理を続ける (LD-57 §3)。wasm は最初の HeapFree の呼出しで trap する。
  - site は値を持たないため、wasm 側が HeapFree へ渡した値は記録していない。

## 5. u16 の trap の原因 (診断・既存 run の trap 文字列)

- trap 文字列: `memory access out of bounds @ ld_wasm.wasm.block_ok < ld_wasm.wasm.HeapFree < ld_wasm.wasm.function_1801c0b6c`。
- `tools/shim/src/heap.c` の `block_ok(user)` は `raw_of(user)` の `magic` を読むだけで、`user` が wasm linear memory の範囲内かを確かめない。u16 の native では `rcx` に非ポインタの値が入る (1 回目 `0x1400000001`、2 回目以降は UTF-16 の文字列値 `0x530020004c0046` など。LD-57 §3)。これが HeapFree の第 3 引数 (解放対象) として渡ると、wasm では線形メモリ (初期 905969664 バイト) の外を読んで trap する。wasm 側で渡った値は site trace に載せていないため、値そのものは未確認。
- native の HeapFree は不正ポインタに対して FALSE を返し、処理を続ける。wasm の shim は `block_ok` で FALSE を返す設計なので、範囲検査が無いことが差の原因と読める。lift の欠陥ではなく shim の検査漏れ。
- shim は全 target 共通のため、修正は本付録の範囲外 (子 #2802)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 命令単位の完全な trace (RetDec IR に命令の VA が無い。方式は RetDec 側の変更か x64c の別経路かの PM 判断が要る) | site 単位でしか native 命令と対応しない。受入 1 の残り | #2801 (LD-131) |
| shim の `block_ok` が範囲外ポインタで trap する件 (u16 の trap 後の後続 block が取れない) | u16 の 1c0b71 以降の対応が未取得。受入 3 の残り | #2802 (LD-132) |
| 残り 5 関数の native 対応 | 受入の範囲外 | #2193 (LD-84) |

## 7. 測定 commit と差分

- 測定 commit: `0913730a`。
- `git diff 0913730a HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/targets tools/liftdiff/results tools/shim tools/ott/rt tools/m6` の出力は 0 件 (本付録を含む以後の commit は REPORT と `docs/DOC_MAP.md` のみ)。
