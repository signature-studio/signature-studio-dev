# REPORT_2275 — NODATA_BODY 対照と HEAD での getmem −4 の再測定 (#2275 = [M11-N147], 親 #2212)

## 0. 結論

- 測定 commit: **`aa647a2ac`** (測定に使ったコードを変えた最後の commit。pad の並びを `g_dest_n`・`g_rec_*` と一致させた)。生値は `table_2275.tsv`・`addr_2275.txt` に tracked。
- **測定 commit `aa647a2ac` では getmem −4 が再現しなかった**。測定した 7 構成 (A_default・R0_rtOFF・C_noren・NODATA・NODATA_BODY・PRE64・PRE4096) は全て getmem **2008**・fastmm_getmem_impl 2091・ok/trap/clobber 873/21/0。REPORT_2212 の R0・NODATA・既定の 2012 (と PRE64 の 2006) はこの測定 commit では出ない。
- **HEAD (`556413937`) の値は未測定**。本 run では素材が無く IR を作り直せなかった (§10)。HEAD と測定 commit の差分は 0 ではない (§9)。本書の数値は、特に断らない限り測定 commit の値である。
- 入力が変わっている (測定 commit で): IR md5 は REPORT_2212 の `baa100ff` から `423c347e` に変わった (全構成で同一)。ldfix の F3c は 36 から 46 に変わった。既定の基準も 870/24/0 から 873/21/0 に変わった。main 側の IR 生成の変更 (dade5b85 から e695e9f3f までの範囲) が入力を変えたと見ている。どの commit かは未特定 (§7)。本 PR は既定の出力を変えない (§5)。
- 受入条件への対応 (§6):
  1. 関数本体の書込みを残し静的データだけ外す構成: NODATA_BODY を n=3 (直列・foreground) で測った。結果 2008 (= C_noren)。ただし −4 が測定 commit に無いため、データ由来か本体由来かは判定できない。
  2. heap 開始位置と後続 static の関係: `__heap_base` は map に出ない。静的領域の終端 (`.bss` の VA + 大きさ) を代理に使った。PRE64 (+0x40)・PRE4096 (+0x1000) で終端は動くが、getmem は 2008 のまま。
  3. 既定の基準: 測定 commit の既定は 873/21/0 (REPORT_2212 の 870/24/0 とは違う)。基準の数値を変えた原因と採否は PM 判断 (§5)。本 PR は既定の rt.o の前処理出力を変えない (§5)。
  4. 測定 commit と差分: §9 (差分は 0 ではない)。HEAD の再測定は未実施 (§10)。
  5. 関数のみ残してデータ無しの対照: NODATA_BODY (n=3) で測った。R0 との分離は、R0 も測定 commit で 2008 のため意味を失った (§4)。
- 未解決は §7。

## 1. 追加した対照 (既定 0・既定の build は従来と同一)

- `tools/m11/m11_rt.c`: `M11_RT_NODATA_BODY=1` を追加 (`#if M11_INSTR_413060` の内側・既定 0)。
  - `m11_dest_obs` の本体は残す (dest の読出し・指紋 `dh`/`dn` の更新・rec の 4 フィールドの計算と store)。状態は呼出しごとの `volatile` スタック変数に置く (store・load の命令は残る)。
  - 静的データ `g_dest_h`・`g_dest_n`・`g_rec_*` は外し、同じ大きさの pad を置く: `g_pad_nd_h` (8 B, `.data`)・`g_pad_nd_n` (8 B)・`g_pad_nd_rec[2048]` (16384 B, `.bss`)。
  - エクスポート (`m11_dest_rec` 等) は NODATA と同じ定数を返す。
  - 元の `m11_dest_obs` (`#else` 側) との差分 (静的データを外した結果): (1) 元の `if (k < M11_DEST_REC_MAX)` (rec store の 512 件制限) が無く、rec の store は呼出しごとのスタック変数への store で毎回行う。(2) 指紋 `dh`・`dn` は呼出しごとに初期化される (呼出しをまたいで累積しない)。(3) 元の `M11_RT_EMPTY`・`M11_NEG_413060`・`M11_DEST_READ`・`M11_DEST_GUARD` の分岐は NODATA_BODY 版に無い (既定の構成では無効)。受入 1 の「本体の書込みを残す」の解釈はこの差分を前提にする。
- `tools/m11/m11_build.sh`: CF に `-DM11_RT_NODATA_BODY=${M11_RT_NODATA_BODY:-0}` を追加。stamp は 1 のときだけ `-nodatabody1` を付ける (既定 0 は従来と同一)。
- `tools/m11/trap_triage/repro_1952_rt_mech.sh`: NODATA_BODY 構成を追加。addr 出力に `[sec]` (`.data`・`.bss` の VA+大きさ) を追加。

## 2. 測定の条件

- 素材: `fl-win64` を `[WIN64]` の展開先 (`FL_WIN64_DIR`) に展開 (5.7 秒)。`work-m11` を worktree の `tools/m11/work` に展開 (2.4 秒)。`[EMSDK]` (`docs/REFERENCES.md` §4) は測定 run で展開済み (記録による)。版は pin の 6.0.12 (`tools/m1/flags.sh`)。測定時の `emcc --version` は保存していない。
- IR 再生成 `m11_gen_ir2.sh`: rc=0・所要 50.2 秒。ldfix 行: `F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=46 errors=0` (REPORT_2212 は F3c=36)。
- n=3 は直列・foreground・単発。所要 (`time` real): C_noren の n=3 と NODATA_BODY の n=3 を含む 6 セル 3 分 30.8 秒。ただし NODATA_BODY の行は pad の並びが未修正の版で、§3 では採らない。修正後の NODATA_BODY n=3 (3 セル) は 1 分 45.0 秒。残りの 5 セル (A_default・R0_rtOFF・NODATA・PRE64・PRE4096、各 n=1) は 3 分 2.9 秒。
- uptime (01:28 UTC): load average 1 分平均 0.36・5 分 0.79・15 分 0.64 (4 vCPU)。

## 3. 測定値 (測定 commit `aa647a2ac`)

| 構成 | 回数 | IR md5 | undefined | ok/trap/clobber | getmem | fastmm_getmem_impl |
|---|--:|---|--:|--:|--:|--:|
| A_default | 1 | 423c347e | 0 | 873/21/0 | 2008 | 2091 |
| C_noren | 3 | 423c347e | 0 | 873/21/0 | 2008 | 2091 |
| R0_rtOFF | 1 | 423c347e | 0 | 873/21/0 | 2008 | 2091 |
| PRE64 | 1 | 423c347e | 0 | 873/21/0 | 2008 | 2091 |
| PRE4096 | 1 | 423c347e | 0 | 873/21/0 | 2008 | 2091 |
| NODATA | 1 | 423c347e | 0 | 873/21/0 | 2008 | 2091 |
| NODATA_BODY | 3 | 423c347e | 0 | 873/21/0 | 2008 | 2091 |

- 上表は全セル一致。生値は `trap_triage/table_2275.tsv` (11 行)、実アドレスは `trap_triage/addr_2275.txt` (11 行)。
- R1 は今回の対象外 (issue の受入条件に無い)。

## 4. リンク後の実アドレスと静的領域 (addr_2275.txt より)

| 構成 | `.data` (VA+大きさ) | `.bss` (VA+大きさ) | g_dest_h / g_pad_nd_h | g_dest_n / g_pad_nd_n | g_rec_st / g_pad_nd_rec | その他 |
|---|---|---|---|---|---|---|
| C_noren (n=3) | 10250ff0+1ac | 10251740+53df4 | 10251028 | 1029d588 | 1029d590 | — |
| NODATA_BODY (n=3) | 10250ff0+1ac | 10251740+53df4 | 10251028 (pad) | 1029d588 (pad) | 1029d590 (pad) | 静的データ名は無い |
| PRE64 | 10250ff0+1ac | 10251740+53e34 | 10251028 | 1029d588 | 1029d590 | g_pad_pre 102a1590 |
| PRE4096 | 10250ff0+1ac | 10251740+54df4 | 10251028 | 1029d588 | 1029d590 | g_pad_pre 102a1590 |
| A_default・R0・NODATA | 10250ff0+19c | 10251730+4fdf4 | (なし) | (なし) | (なし) | 名前付き状態が無い |

- NODATA_BODY の `.data`・`.bss` の VA と大きさは C_noren と完全に一致し、pad の各アドレスは元の変数の位置と一致する。この並びの一致が「静的領域の大きさ・並びは動かさない」という条件の根拠。
- PRE64 は `.bss` の大きさが C_noren より 0x40 大きく、PRE4096 は 0x1000 大きい (`g_pad_pre` の大きさ)。
- A_default・R0・NODATA は `.bss` が C_noren より 0x4000 小さく (`g_rec_*` の 4 × 4096 B)、`.data` が 0x10 小さい。これは rt.o の名前付き状態が無い分。
- `llvm-nm`・map は `__heap_base` を出さない。heap の直接の開始位置は測れていない (§7)。

## 5. 既定の変化と本 PR の影響

- 既定 (A_default) は 873/21/0 で、REPORT_2212 の 870/24/0 と違う。IR md5 も `baa100ff` から `423c347e` に変わった。F3c も 36 から 46 に変わった。入力 IR が変わったことが原因。
- 本 PR が既定の出力を変えないことの確認 (この run で再実施。測定 run の「emcc で 1300 行一致」は出力を保存していないため再現できない):
  既定フラグ `-DM11_LB_BASE=0 -DM11_INSTR_413060=0 -DM11_OV_CLASSCREATE=0` で `m11_rt.c` を origin/main 版 (`6aeb2b74b`) と HEAD 版 (CF どおり `-DM11_RT_NODATA_BODY=0` を付ける) に前処理し、md5 で比べた。
  ```
  D="$(mktemp -d)"; mkdir -p "$D/stub/emscripten"
  printf '#define EMSCRIPTEN_KEEPALIVE\n' > "$D/stub/emscripten.h"; : > "$D/stub/emscripten/stack.h"
  git show 6aeb2b74b:tools/m11/m11_rt.c > "$D/main_rt.c"; cp tools/m11/m11_rt.c "$D/head_rt.c"
  F="-DM11_LB_BASE=0 -DM11_INSTR_413060=0 -DM11_OV_CLASSCREATE=0"
  cd tools/m11 && gcc -E -P $F -I"$D/stub" -I. "$D/main_rt.c" | md5sum; gcc -E -P $F -DM11_RT_NODATA_BODY=0 -I"$D/stub" -I. "$D/head_rt.c" | md5sum
  ```
  結果: 両版とも 1132 行・md5 `9e726bc579a5fcc109c81e7719132022` (`cmp` で完全一致)。
  注: この run には emcc が無いため `gcc -E -P` で代替した。`emscripten.h`・`emscripten/stack.h` は空の stub で置き換えた。`__EMSCRIPTEN__` 等は定義されないので emcc の出力とは行数が違う。比較の条件 (同じ前処理器・同じフラグで両版を比べる) は同じ。
- CF に増えた `-DM11_RT_NODATA_BODY=0` は既定値で、生成コードに影響しない。stamp も 0 のとき従来と同一。
- 既定の基準 (受入 3「既定の基準 (870/24/0) は変えない」) の PM 判断の記録: 文字どおりには満たさない。測定した既定は 873/21/0 に変わった (IR md5 `baa100ff`→`423c347e`・F3c 36→46)。変化の原因は main 側の IR 生成の変更と見ているが、どの commit かは未特定 (§7)。本 PR は既定の出力を変えていない (上の前処理)。新しい基準 (HEAD の A_default) は §10 の再測定の値で記録する。据え置くか差し替えるかは PM が判断する。
- IR が変わった commit は未特定 (dade5b85 から e695e9f3f までの main 側の変更。§7)。

## 6. 受入条件の判定

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| 1. 関数本体の書込みを残し static data だけ外す構成を n=3 で測る | 測定済み・機序は判定不能 | NODATA_BODY n=3 = 2008 (C_noren と同じ)。−4 が測定 commit に無い (§4) |
| 2. heap 開始位置・後続 static と getmem の関係 | 部分達成 | 静的終端の代理で測った。PRE64 (+0x40)・PRE4096 (+0x1000) でも 2008。heap 開始位置の直接測定は無い (`__heap_base` が map に無い) |
| 3. 既定の基準は変えない | 本 PR では変えない | 既定の前処理出力は同一 (§5)。ただし測定 commit の既定は 873/21/0 で 870/24/0 とは違う (§5) |
| 4. 測定 commit と差分を REPORT に添える | 添付済み (§9)。差分は 0 ではないため HEAD の再測定が要る (§10・未了) | §0・§9・§10 |
| 5. 関数のみ残してデータ無しの対照 (R0 との分離) | 測定済み・分離は無意味になった | NODATA_BODY n=3 = 2008。R0 も測定 commit で 2008 |

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 測定 commit で −4 が消えた原因。dade5b85 から e695e9f3f までの main 側の変更 (IR md5 `baa100ff`→`423c347e`・ldfix F3c 36→46) のどれが効いたか未特定 | REPORT_1701・1952・2212 の「rt.o の計測 flag が −4 を生む」が HEAD で成り立つか未確認 | #2275 (本 issue に残す。PM 判断) |
| 受入条件 1・2・5 の機序判定 (データ由来か本体由来か、heap 開始位置) | −4 が測定 commit に無いため判定不能。heap 開始位置は `__heap_base` の直接測定が無い | #2275 |
| HEAD (`556413937`) での再測定 (WORKFLOW §6)。差分 23 files (§9) があり、測定値は HEAD の値ではない | §0・§3・§6 の値は測定 commit の値。HEAD で −4 が有るか無いかは未確認 | この PR で未了 (差し戻し中。子 issue にしない。§10) |

## 8. 再現

- `bash tools/m11/trap_triage/repro_1952_rt_mech.sh [N] [CONFIG...]` (CONFIG に `NODATA_BODY` を追加)。表は `work/split_1952/table.tsv`、実アドレスは `work/split_1952/addr.txt` (gitignore)。tracked 版は `table_2275.tsv`・`addr_2275.txt`。
- 前提: `FL_WIN64_DIR` = `[WIN64]` (`fl-win64` を展開し、`m11_build.sh` と `m11_gen_ir2.sh` で同じ値を使う。IR は PE のパスを記録する)・`work/` が `m11_gen_ir2.sh` 生成済み・`[EMSDK]` 配置済み。
- 素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11` (`docs/WORKFLOW.md` §11)。本 run では `toolchain-retdec`・`toolchain-emsdk`・`work-m11` が無く実行できなかった (§10)。

## 9. 測定 commit からの差分

- 測定 commit: `aa647a2ac` (pad を `g_dest_n`・`g_rec_*` と同じ並びにした版)。この commit の `tools/m11` で §3 の表を測った。
- 前回の版 `bf11784ec` (pad 修正前) の NODATA_BODY 行は、静的領域の並びが C_noren と 8 B・0x10 B ずれていたため採らない (§4 の結果で置き換えた)。
- 差分 (HEAD `556413937`・`trap_triage` を除く)。以前の「出力は空」は merge 前の commit の結果で、HEAD には当てはまらない。

```
 tools/m11/REPORT_APPENDIX_3188.md        |  75 +++++++++++++
 tools/m11/REPORT_APPENDIX_3229.md        |  47 ++++++++
 tools/m11/REPORT_N3172.md                |  90 +++++++++++++++
 tools/m11/REPORT_N3325.md                | 106 ++++++++++++++++++
 tools/m11/REPORT_N403.md                 |  43 +------
 tools/m11/ldfix/REPORT_2447.md           |   7 +-
 tools/m11/ldfix/REPORT_2527.md           |  98 ++++++++++++++++
 tools/m11/ldfix/REPORT_3328.md           | 110 ++++++++++++++++++
 tools/m11/ldfix/REPORT_3426.md           |  94 ++++++++++++++++
 tools/m11/ldfix/fix_ld115.py             |   4 +-
 tools/m11/ldfix/fix_ld116.py             |   4 +-
 tools/m11/ldfix/ld115_e2e.sh             | 141 ++++++++++++++++++-----
 tools/m11/ldfix/ld116_e2e.sh             |   8 +-
 tools/m11/ldfix/scan_spill_deref_3328.py | 157 ++++++++++++++++++++++++++
 tools/m11/ldfix/verify_abi_3426.py       | 185 +++++++++++++++++++++++++++++++
 tools/m11/m11_build.sh                   |  14 ++-
 tools/m11/m11_e2e.sh                     |   3 +-
 tools/m11/m11_gen_ir2.sh                 |  13 ++-
 tools/m11/m11_ghidra_dll.sh              |  64 +++++++++++
 tools/m11/m11_lb_ir_fn_diff_3188.py      |  67 +++++++++++
 tools/m11/m11_ov.c                       |  32 ++++++
 tools/m11/m11_post.py                    |  12 +-
 tools/m11/m11_tolerant.mjs               |  11 +-
 23 files changed, 1302 insertions(+), 83 deletions(-)
```

差分は 0 ではない。main 取り込みで入った IR 生成・build の変更 (`m11_build.sh`・`m11_gen_ir2.sh`・`m11_post.py`・`m11_ov.c`・`ldfix/`) が測定経路に含まれる。HEAD での再測定は §10。

## 10. HEAD (`556413937`) の再測定 — 未実施 (この run)

- 本 run の `$ARTIFACTS_DIR` には `fl-win64.tar.zst` だけがあり、`toolchain-retdec`・`toolchain-emsdk`・`work-m11` は無かった (`ls` で確認)。PR 本文に `oc_artifacts` 行が無かったため、素材は取得されていない。`tools/m11/work/` も無く、`m11_gen_ir2.sh` の lift 段 (RetDec) を実行できなかった。このため HEAD の IR (md5・ldfix・ld115) も repro の値も測れていない。
- 次の run で行うこと (素材を指定した run): `bash tools/m11/m11_gen_ir2.sh` → `work/ir_conditions.json` で `ldfix=applied`・`ld115=applied` を確認 → `bash tools/m11/trap_triage/repro_1952_rt_mech.sh` (A_default・C_noren・NODATA_BODY は n=3、残り (R0_rtOFF・NODATA・PRE64・PRE4096) は n=1。直列・foreground)。得た値で §0・§3・§6 を HEAD の値に差し替え、§9 の差分と合わせて書く。
- この段階では、HEAD で −4 が消えたとも残るとも書かない。
