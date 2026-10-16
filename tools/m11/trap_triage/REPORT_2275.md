# REPORT_2275 — NODATA_BODY 対照と HEAD での getmem −4 の再測定 (#2275 = [M11-N147], 親 #2212)

## 0. 結論

- 測定 commit: **`aa647a2ac`** (測定に使ったコードを変えた最後の commit。pad の並びを `g_dest_n`・`g_rec_*` と一致させた)。生値は `table_2275.tsv`・`addr_2275.txt` に tracked。HEAD の生値は `table_2275_head.tsv`・`addr_2275_head.txt` に tracked。
- **測定 commit `aa647a2ac` では getmem −4 が再現しなかった**。測定した 7 構成 (A_default・R0_rtOFF・C_noren・NODATA・NODATA_BODY・PRE64・PRE4096) は全て getmem **2008**・fastmm_getmem_impl 2091・ok/trap/clobber 873/21/0。REPORT_2212 の R0・NODATA・既定の 2012 (と PRE64 の 2006) はこの測定 commit では出ない。
- **HEAD の値は §10 で実測した** (測定した HEAD `bb8aaf1d5`。tools/m11 のコードは `e3dc956f9` と同じで、`m11_rt.c` の 290 行目のコメント 1 行だけが違う): 7 構成 (13 セル) が全て 873/21/0・getmem 2008。R0_rtOFF も 2008 のため、HEAD でも −4 は再現しない。本書の §0・§3 の数値は、特に断らない限り測定 commit (`aa647a2ac`) の値である。
- 入力が変わっている (測定 commit で): IR md5 は REPORT_2212 の `baa100ff` から `423c347e` に変わった (全構成で同一)。ldfix の F3c は 36 から 46 に変わった。既定の基準も 870/24/0 から 873/21/0 に変わった。main 側の IR 生成の変更 (dade5b85 から e695e9f3f までの範囲) が入力を変えたと見ている。どの commit かは未特定 (§7)。本 PR は既定の出力を変えない (§5)。
- 受入条件への対応 (§6):
  1. 関数本体の書込みを残し静的データだけ外す構成: NODATA_BODY を n=3 (直列・foreground) で測った。結果 2008 (= C_noren)。ただし −4 が測定 commit に無いため、データ由来か本体由来かは判定できない。
  2. heap 開始位置と後続 static の関係: `__heap_base` は map に出ない。静的領域の終端 (`.bss` の VA + 大きさ) を代理に使った。PRE64 (+0x40)・PRE4096 (+0x1000) で終端は動くが、getmem は 2008 のまま。
  3. 既定の基準: 測定 commit の既定は 873/21/0 (REPORT_2212 の 870/24/0 とは違う)。基準の数値を変えた原因と採否は PM 判断 (§5)。本 PR は既定の rt.o の前処理出力を変えない (§5)。
  4. 測定 commit と差分: §9 (差分は 0 ではない)。HEAD の再測定は §10 で実施 (全構成 getmem 2008・§3 と一致)。
  5. 関数のみ残してデータ無しの対照: NODATA_BODY (n=3) で測った。R0 との分離は、R0 も測定 commit で 2008 のため意味を失った (§4)。
- 未解決は §7。

## 1. 追加した対照 (既定 0・既定の build は従来と同一)

- `tools/m11/m11_rt.c`: `M11_RT_NODATA_BODY=1` を追加 (`#if M11_INSTR_413060` の内側・既定 0)。
  - `m11_dest_obs` の本体は残す (dest の読出し・指紋 `dh`/`dn` の更新・rec の 4 フィールドの計算と store)。状態は呼出しごとの `volatile` スタック変数に置く (store・load の命令は残る)。
  - 静的データ `g_dest_h`・`g_dest_n`・`g_rec_*` は外し、同じ大きさの pad を置く: `g_pad_nd_h` (8 B, `.data`)・`g_pad_nd_n` (8 B)・`g_pad_nd_rec[2048]` (16384 B, `.bss`)。
  - エクスポート (`m11_dest_rec` 等) は NODATA と同じ定数を返す。
  - 元の `m11_dest_obs` (`#else` 側) との差分 (静的データを外した結果): (1) 元の `if (k < M11_DEST_REC_MAX)` (rec store の 512 件制限) が無く、rec の store は呼出しごとのスタック変数への store で毎回行う。(2) 指紋 `dh`・`dn` は呼出しごとに初期化される (呼出しをまたいで累積しない)。(3) 元の `M11_RT_EMPTY`・`M11_NEG_413060`・`M11_DEST_GUARD` の分岐は NODATA_BODY 版に無い。この 3 つは既定 0 で、既定の構成では元の版でも無効。`M11_DEST_READ` は既定 1 で、NODATA_BODY 版に分岐が無いため、`M11_DEST_READ=0` の切り分けには使えない (元の版では 0 で読出しを止める)。受入 1 の「本体の書込みを残す」の解釈はこの差分を前提にする。
- `tools/m11/m11_build.sh`: CF に `-DM11_RT_NODATA_BODY=${M11_RT_NODATA_BODY:-0}` を追加。stamp は 1 のときだけ `-nodatabody1` を付ける (既定 0 は従来と同一)。
- `tools/m11/trap_triage/repro_1952_rt_mech.sh`: NODATA_BODY 構成を追加。addr 出力に `[sec]` (`.data`・`.bss` の VA+大きさ) を追加。

## 2. 測定の条件

- 素材: `fl-win64` を `[WIN64]` の展開先 (`FL_WIN64_DIR`) に展開 (5.7 秒)。`work-m11` を worktree の `tools/m11/work` に展開 (2.4 秒)。`[EMSDK]` は `m11_build.sh` が固定の場所の `emsdk_env.sh` を読む (環境変数の上書きは無い。展開先の絶対パスは本書に書かず、`docs/REFERENCES.md` のエントリで参照する)。版は pin の 6.0.12 (`tools/m1/flags.sh`)。測定 commit の run の `emcc --version` は保存していない (§10 の再測定では `6.0.12 (5488e0871d46)`)。
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
- 本 PR が既定の出力を変えないことの確認 (round 1 の run で実施。測定 run の「emcc で 1300 行一致」は出力を保存していないため再現できない):
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
| 4. 測定 commit と差分を REPORT に添える | 添付済み (§9)。HEAD の再測定を §10 で実施 (全構成一致) | §0・§9・§10 |
| 5. 関数のみ残してデータ無しの対照 (R0 との分離) | 測定済み・分離は無意味になった | NODATA_BODY n=3 = 2008。R0 も測定 commit で 2008 |

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 測定 commit で −4 が消えた原因。dade5b85 から e695e9f3f までの main 側の変更 (IR md5 `baa100ff`→`423c347e`・ldfix F3c 36→46) のどれが効いたか未特定 | REPORT_1701・1952・2212 の「rt.o の計測 flag が −4 を生む」が HEAD で成り立つか未確認 | #2275 (本 issue に残す。PM 判断) |
| 受入条件 1・2・5 の機序判定 (データ由来か本体由来か、heap 開始位置) | −4 が測定 commit に無いため判定不能。heap 開始位置は `__heap_base` の直接測定が無い | #2275 |
| IR md5 が測定 commit (`423c347e`) と HEAD (`8b4461e0`) で違う (ldfix F3c は両方 46)。違いの原因 (IR の内容か生成の非決定性か) は未確認 | IR の同一性を測定 commit の値で言えない。getmem の値は両方で 2008 | #2275 (PM 判断。§10) |

## 8. 再現

- `bash tools/m11/trap_triage/repro_1952_rt_mech.sh [N] [CONFIG...]` (CONFIG に `NODATA_BODY` を追加)。表は `work/split_1952/table.tsv`、実アドレスは `work/split_1952/addr.txt` (gitignore)。tracked 版は測定 commit `table_2275.tsv`・`addr_2275.txt`、HEAD 版は `table_2275_head.tsv`・`addr_2275_head.txt`。
- 前提: `FL_WIN64_DIR` = `[WIN64]` (`fl-win64` を展開し、`m11_build.sh` と `m11_gen_ir2.sh` で同じ値を使う。IR は PE のパスを記録する)・`work/` が `m11_gen_ir2.sh` 生成済み・`[EMSDK]` 配置済み。
- 素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11` (`docs/WORKFLOW.md` §11)。HEAD で実行した手順は §10。

## 9. 測定 commit からの差分

- 測定 commit: `aa647a2ac` (pad を `g_dest_n`・`g_rec_*` と同じ並びにした版)。この commit の `tools/m11` で §3 の表を測った。
- 前回の版 `bf11784ec` (pad 修正前) の NODATA_BODY 行は、静的領域の並びが C_noren と 8 B・0x10 B ずれていたため採らない (§4 の結果で置き換えた)。
- 差分 (`aa647a2ac` → 確認時の HEAD `bb8aaf1d5`。`trap_triage` を除く。コマンド: `git diff --stat aa647a2ac HEAD -- tools/m11 ':(exclude)tools/m11/trap_triage'`)。以前の「出力は空」は merge 前の commit の結果で、HEAD には当てはまらない。

```
 tools/m11/REPORT_APPENDIX_3188.md        |  75 ++++++++++++
 tools/m11/REPORT_APPENDIX_3229.md        |  47 ++++++++
 tools/m11/REPORT_N3172.md                |  90 +++++++++++++++
 tools/m11/REPORT_N3325.md                | 106 +++++++++++++++++
 tools/m11/REPORT_N403.md                 |  43 +------
 tools/m11/ldfix/REPORT_2447.md           |   7 +-
 tools/m11/ldfix/REPORT_2527.md           |  98 ++++++++++++++++
 tools/m11/ldfix/REPORT_2660.md           |  44 +++++++
 tools/m11/ldfix/REPORT_3328.md           | 110 ++++++++++++++++++
 tools/m11/ldfix/REPORT_3372.md           | 188 ++++++++++++++++++++++++++++++
 tools/m11/ldfix/REPORT_3426.md           |  94 +++++++++++++++
 tools/m11/ldfix/fix_ld115.py             |   4 +-
 tools/m11/ldfix/fix_ld116.py             |   4 +-
 tools/m11/ldfix/fix_site_3372.py         | 192 +++++++++++++++++++++++++++++++
 tools/m11/ldfix/ld115_e2e.sh             | 141 ++++++++++++++++++-----
 tools/m11/ldfix/ld116_e2e.sh             |   8 +-
 tools/m11/ldfix/ldfix.py                 |  10 +-
 tools/m11/ldfix/ldfix_e2e.sh             |   3 +
 tools/m11/ldfix/scan_spill_deref_3328.py | 157 +++++++++++++++++++++++++
 tools/m11/ldfix/verify_abi_3426.py       | 185 +++++++++++++++++++++++++++++
 tools/m11/m11_build.sh                   |  20 +++-
 tools/m11/m11_e2e.sh                     |   3 +-
 tools/m11/m11_gen_ir2.sh                 |  13 ++-
 tools/m11/m11_ghidra_dll.sh              |  64 +++++++++++
 tools/m11/m11_lb_ir_fn_diff_3188.py      |  67 +++++++++++
 tools/m11/m11_ov.c                       |  50 +++++++-
 tools/m11/m11_post.py                    |  12 +-
 tools/m11/m11_ptrcheck.mjs               |   2 +-
 tools/m11/m11_rt.c                       |   2 +-
 tools/m11/m11_tolerant.mjs               |  11 +-
 30 files changed, 1758 insertions(+), 92 deletions(-)
```

差分は 0 ではない。main 取り込みで入った IR 生成・build の変更 (`m11_build.sh`・`m11_gen_ir2.sh`・`m11_post.py`・`m11_ov.c`・`ldfix/`) が測定経路に含まれる。`m11_rt.c` の差分は 290 行目のコメント 1 行 (#2275 round 5 の修正) で、測定経路には入らない。HEAD での再測定は §10。

## 10. HEAD の再測定 (実施)

- 測定した HEAD: `bb8aaf1d5` (`m11_rt.c` の 290 行目のコメントを直した commit)。その後の commit は REPORT_2275.md と DOC_MAP.md だけを変え、tools/m11 のコードは変えない。tools/m11 のコードは `e3dc956f9` と同じで、違うのは `m11_rt.c` の 290 行目のコメント 1 行だけ (下の差分証跡)。`e3dc956f9` は origin/main `517b95da3` を取り込んだ merge。競合は `tools/m11/m11_build.sh` の CF 行 1 箇所で、origin/main の `-DM11_PROBE_2400` と本ブランチの `-DM11_RT_NODATA_BODY` を両方残して解消した。
- 前の HEAD `3daa45491` でも同じ手順を実行し、13 セルが同一だった (round 4 の run)。
- 素材 (この再測定): `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開し `FL_WIN64_DIR` に設定。`work-m11` を `tools/m11/work/` に展開。`toolchain-retdec`・`toolchain-emsdk` の tarball は展開せず、既存の `[RETDEC]`・`[EMSDK]` を使った (`m11_build.sh` は `[EMSDK]` を固定の場所から読む)。`emcc --version` = `6.0.12 (5488e0871d46)`。
- IR 再生成 `m11_gen_ir2.sh`: rc=0・51.7 秒。ldfix 行: `F1=902 F1v=4 F2=30 F3a=3 F3b=5 F3c=46 F3d=0 F4=10 errors=0`。`ir_conditions.json` の `ldfix`・`ld108`・`ld115` は applied。`ir_sha256` は `12dde126…`。
- repro: `bash tools/m11/trap_triage/repro_1952_rt_mech.sh 3 A_default C_noren NODATA_BODY` (rc=0・6 分 7.7 秒) と `... 1 R0_rtOFF NODATA PRE64 PRE4096` (rc=0・2 分 20.7 秒)。直列・foreground。n=3 の開始時の load average 1 分平均 0.54。

| 構成 | 回数 | boot_final3.ll md5 | undefined symbol | ok/trap/clobber | getmem | fastmm_getmem_impl |
|---|--:|---|--:|--:|--:|--:|
| A_default | 3 | 8b4461e0 | 0 | 873/21/0 | 2008 | 2091 |
| C_noren | 3 | 8b4461e0 | 0 | 873/21/0 | 2008 | 2091 |
| NODATA_BODY | 3 | 8b4461e0 | 0 | 873/21/0 | 2008 | 2091 |
| R0_rtOFF | 1 | 8b4461e0 | 0 | 873/21/0 | 2008 | 2091 |
| NODATA | 1 | 8b4461e0 | 0 | 873/21/0 | 2008 | 2091 |
| PRE64 | 1 | 8b4461e0 | 0 | 873/21/0 | 2008 | 2091 |
| PRE4096 | 1 | 8b4461e0 | 0 | 873/21/0 | 2008 | 2091 |

- 全 13 セル (n=3 の 3 構成 9 行・n=1 の 4 構成 4 行) が同一。生の表は `table_2275_head.tsv` (ヘッダ無し・13 行)、実アドレスは `addr_2275_head.txt` (13 行)。本 commit の実測 (`work/split_1952/table.tsv`・`addr.txt`) と全行一致 (`diff` の出力は空)。
- 静的領域 (`.data`・`.bss` の VA と大きさ、pad の位置) は §4 と同一 (`addr_2275_head.txt` で確認)。
- 前処理: 既定フラグで `bb8aaf1d5` の `m11_rt.c` を `gcc -E -P` で前処理した md5 は `9e726bc5…` で、origin/main `4517825a2` の `m11_rt.c` と一致する。IR の md5 (`8b4461e0`) は前の HEAD と同じ。
- 差分 0 の証跡 (WORKFLOW §6): `git diff --stat e3dc956f9 bb8aaf1d5 -- tools/m11 ':(exclude)tools/m11/trap_triage/*_2275*'` の出力は `tools/m11/m11_rt.c | 2 +-` の 1 行だけ (コメント 1 行の変更)。除外しているのは本書と 2275 の生値 (`table_2275*.tsv`・`addr_2275*.txt`)。コードは変わっていないため、上の再測定の値は HEAD の値である。
- 結論:
  - **HEAD でも getmem −4 は再現しない**。R0_rtOFF (rt.o の計測 OFF) も 2008 で、REPORT_2212 の 2012 は出ない。「rt.o の計測 flag が −4 を生む」は HEAD でも成り立たない。
  - 受入 1・2・5 の機序は、−4 が無いため HEAD でも判定できない (§6 のまま)。
  - 既定 (A_default) は HEAD でも 873/21/0 で、§5 の既定の変化は HEAD でも同じ。
  - IR md5 は HEAD `8b4461e0`・測定 commit `423c347e` で違う。F3c は両方 46。違いの原因は未確認 (§7)。
- 本 PR の KPI: `tools/m11` の計測 knob のみ。起動・GUI に関わらないため、KPI は書かない。

### 10.1 f195a93a9 での C_noren / NODATA_BODY の計測 (#5945)

- 測定 commit: **`f195a93a9`** (= origin/main の merge #5651)。`tools/m11` のコードは変えていない (`git diff f195a93a9 -- tools/m11` は本節の追記だけ)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開して `FL_WIN64_DIR` に設定。`work-m11` を `tools/m11/work/` に展開。`toolchain-emsdk` は展開せず runner の `[EMSDK]` を使った (`emcc` = `6.0.12 (5488e0871d46)` = pin)。`toolchain-retdec` は展開せず `[RETDEC]` を使った。
- IR 再生成: `m11_gen_ir2.sh` rc=0・43.8 秒 (`work/ir_conditions.json` の `ldfix` 有り)。
- 計測: `bash tools/m11/trap_triage/repro_1952_rt_mech.sh 3 C_noren NODATA_BODY` (rc=0・直列・foreground・2 分 40.9 秒)。開始時 load average 1 分 1.33。

| 構成 | 回数 | boot_final3.ll md5 | undefined symbol | ok/trap/clobber | getmem | fastmm_getmem_impl |
|---|--:|---|--:|--:|--:|--:|
| C_noren | 3 | e5023e8e | 0 | 873/21/0 | **2017** | 2095 |
| NODATA_BODY | 3 | e5023e8e | 0 | 873/21/0 | **2017** | 2095 |

- 結論 (受入 1): **f195a93a9 では getmem は 2017** (C_noren・NODATA_BODY とも n=3 で同一)。2008 ではない。前の run (#5665) の「全構成 2017」と一致し、同じ commit では再現する。
- 「2017 と 2008 のどちらか」の差は、commit 間の IR の差として見える: f195a93a9 の IR md5 は `e5023e8e`、bb8aaf1d5 (§10 の HEAD) は `8b4461e0`。同じ runner 上で bb8aaf1d5 を測り直してはいない (§10 は別 run)。よって runner 依存かどうかは未確定。runner 依存を確かめるには、同じ runner で bb8aaf1d5 と f195a93a9 を並べて測る必要がある (未実施)。
- NODATA_BODY (静的データを無くした構成) も 2017。静的データを外しても値が変わらないので、この 2017 は静的データの配置ではなく、関数本体または IR の側から来ている可能性が高い。ただし A_default 等は f195a93a9 で未測定のため、判定は保留。
- 生値: `table_2275_f195.tsv` (6 行・ヘッダ無し)、`addr_2275_f195.txt` (6 行)。`.data`・`.bss` の VA と大きさは C_noren と NODATA_BODY で同一 (`.data=10250ff0+1ac`・`.bss=10251740+53df4`)。
- 既定値 (870/24/0) は変えていない。

## 11. 測定の決定性 (#5955 = [M11-N281], 親 #5946)

- 測定 commit: **`32c1f5d9c`** (origin/main。`tools/m11` のコードは変えていない。本節は REPORT の追記のみ)。`git diff 32c1f5d9c HEAD -- tools/m11` の差分は本節の追記だけ (コード差分 0)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開して `FL_WIN64_DIR` に設定。`work-m11` を worktree の `tools/m11/work/` に展開。`m11_gen_ir2.sh` rc=0・52.9 秒 (ldfix applied)。`[EMSDK]` は runner の `/opt/emsdk` (pin 6.0.12)。
- 手順: `bash trap_triage/repro_1952_rt_mech.sh 3 A_default C_noren` (直列・foreground・rc=0・計 3 分 18 秒。内訳は C_noren 1 分 42.3 秒・A_default 1 分 35.8 秒)。開始時 load average 1 分平均 0.88 (4 vCPU)。
- 測定した 6 セル:

| 構成 | 回数 | boot_final3.ll md5 | undefined symbol | ok/trap/clobber | getmem | fastmm_getmem_impl |
|---|--:|---|--:|--:|--:|--:|
| A_default | 3 | e5023e8e | 0 | 873/21/0 | 2017 | 2095 |
| C_noren | 3 | e5023e8e | 0 | 873/21/0 | 2017 | 2095 |

- 同一 IR・同一構成の 3 回で、getmem・survey 出力 (全行)・link map の md5 が一致した (`map_*_r*.txt` は構成ごとに 1 種類、`ir_*_r*.ll` は全 6 本が同一)。survey の出力も 3 回で同一。
- 候補の切り分け: (a) survey の乱数 — `m11_survey.mjs` に乱数は無い (`Date.now` は `M11_SURVEY_PROGRESS=1` の進捗ログだけ)。(b) link 順序 — map の md5 が 3 回で一致し、順序は変わっていない。(c) 並列 load — 本節の 6 セルは全て直列で、並列 load は測っていない (未確認)。
- 2006/2012 の分岐は、本 run では再現しなかった。IR md5 `4c792075` は repo (`tools/`) のどこにも記録されておらず、この IR も再生成できていない (本 run の IR は `e5023e8e`)。よって issue の「同一 IR `4c792075` で 2006 と 2012」は、本 run の入力では確かめられない。
- 本 run の値は 2017。これは §10.1 (`f195a93a9`・`e5023e8e`) と一致し、§10 (`bb8aaf1d5`・`8b4461e0`・2008) とは違う。同じ runner 上で `bb8aaf1d5` と `32c1f5d9c` を並べて測ってはいないので、commit 差か runner 差かは未確定。
- 決定性の判定基準 (受入 2): **同一 commit・同一 IR md5・直列 foreground で、`repro_1952_rt_mech.sh` の getmem が n=3 で一致すること**。本 run では満たした (2017 × 3)。bisect の判定はこの値を基準にする。
- 既定の基準 (受入 3): 変えていない。ただし本 run の既定 (A_default) は 873/21/0・getmem 2017 で、§0 の 870/24/0 や §10 の 2008 とは違う。基準の差し替えは PM 判断 (§5)。
- 生値: `table_2275_5955.tsv` (6 行・ヘッダ無し)、`addr_2275_5955.txt` (6 行)。
- 未解決 (#5955 に残す): (1) 2006/2012 の分岐の再現 (IR `4c792075` の再生成、または `bb8aaf1d5`・`f195a93a9` を同一 runner で並べて測る)。(2) 並列 load での決定性 (未測定)。(3) 本 run の 2017 と §10 の 2008 の差の原因 (commit か runner か)。
