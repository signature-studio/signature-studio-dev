# REPORT_2275 — NODATA_BODY 対照と HEAD での getmem −4 の再測定 (#2275 = [M11-N147], 親 #2212)

## 0. 結論

- 測定 commit: **`aa647a2ac`** (測定に使ったコードを変えた最後の commit。pad の並びを `g_dest_n`・`g_rec_*` と一致させた)。生値は `table_2275.tsv`・`addr_2275.txt` に tracked。
- **現 HEAD では getmem −4 が再現しなかった**。測定した 7 構成 (A_default・R0_rtOFF・C_noren・NODATA・NODATA_BODY・PRE64・PRE4096) は全て getmem **2008**・fastmm_getmem_impl 2091・ok/trap/clobber 873/21/0。REPORT_2212 の R0・NODATA・既定の 2012 (と PRE64 の 2006) は現 HEAD では出ない。
- 入力が変わっている: IR md5 は REPORT_2212 の `baa100ff` から `423c347e` に変わった (全構成で同一)。ldfix の F3c は 36 から 46 に変わった。既定の基準も 870/24/0 から 873/21/0 に変わった。これは main 側の IR 生成の変更による (§5。本 PR は既定の出力を変えない)。
- 受入条件への対応 (§6):
  1. 関数本体の書込みを残し静的データだけ外す構成: NODATA_BODY を n=3 (直列・foreground) で測った。結果 2008 (= C_noren)。ただし −4 が現 HEAD に無いため、データ由来か本体由来かは判定できない。
  2. heap 開始位置と後続 static の関係: `__heap_base` は map に出ない。静的領域の終端 (`.bss` の VA + 大きさ) を代理に使った。PRE64 (+0x40)・PRE4096 (+0x1000) で終端は動くが、getmem は 2008 のまま。
  3. 既定の基準: 現 HEAD の既定は 873/21/0 (REPORT_2212 の 870/24/0 とは違う)。本 PR は既定の rt.o の前処理出力を変えない (§5)。
  4. 測定 commit と差分: §0・§7。
  5. 関数のみ残してデータ無しの対照: NODATA_BODY (n=3) で測った。R0 との分離は、R0 も現 HEAD で 2008 のため意味を失った (§4)。
- 未解決は §7。

## 1. 追加した対照 (既定 0・既定の build は従来と同一)

- `tools/m11/m11_rt.c`: `M11_RT_NODATA_BODY=1` を追加 (`#if M11_INSTR_413060` の内側・既定 0)。
  - `m11_dest_obs` の本体は残す (dest の読出し・指紋 `dh`/`dn` の更新・rec の 4 フィールドの計算と store)。状態は呼出しごとの `volatile` スタック変数に置く (store・load の命令は残る)。
  - 静的データ `g_dest_h`・`g_dest_n`・`g_rec_*` は外し、同じ大きさの pad を置く: `g_pad_nd_h` (8 B, `.data`)・`g_pad_nd_n` (8 B)・`g_pad_nd_rec[2048]` (16384 B, `.bss`)。
  - エクスポート (`m11_dest_rec` 等) は NODATA と同じ定数を返す。
- `tools/m11/m11_build.sh`: CF に `-DM11_RT_NODATA_BODY=${M11_RT_NODATA_BODY:-0}` を追加。stamp は 1 のときだけ `-nodatabody1` を付ける (既定 0 は従来と同一)。
- `tools/m11/trap_triage/repro_1952_rt_mech.sh`: NODATA_BODY 構成を追加。addr 出力に `[sec]` (`.data`・`.bss` の VA+大きさ) を追加。

## 2. 測定の条件

- 素材: `fl-win64` を `[WIN64]` の展開先 (`FL_WIN64_DIR`) に展開 (5.7 秒)。`work-m11` を worktree の `tools/m11/work` に展開 (2.4 秒)。`[EMSDK]` は `[EMSDK]` (展開済み)。
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
- 本 PR が既定の出力を変えないことの確認: `emcc -E -P` で既定フラグ (`-DM11_LB_BASE=0 -DM11_INSTR_413060=0 -DM11_OV_CLASSCREATE=0`) の `m11_rt.c` を、origin/main 版と現版で前処理し比べた。1300 行で完全一致。CF に増えた `-DM11_RT_NODATA_BODY=0` は既定値で、生成コードに影響しない。stamp も 0 のとき従来と同一。
- IR が変わった commit は未特定 (dade5b85 から e695e9f3f までの main 側の変更。§7)。

## 6. 受入条件の判定

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| 1. 関数本体の書込みを残し static data だけ外す構成を n=3 で測る | 測定済み・機序は判定不能 | NODATA_BODY n=3 = 2008 (C_noren と同じ)。−4 が現 HEAD に無い (§4) |
| 2. heap 開始位置・後続 static と getmem の関係 | 部分達成 | 静的終端の代理で測った。PRE64 (+0x40)・PRE4096 (+0x1000) でも 2008。heap 開始位置の直接測定は無い (`__heap_base` が map に無い) |
| 3. 既定の基準は変えない | 本 PR では変えない | 既定の前処理出力は同一 (§5)。ただし現 HEAD の既定は 873/21/0 で 870/24/0 とは違う |
| 4. 測定 commit と差分を REPORT に添える | 達成 | §0・§8 |
| 5. 関数のみ残してデータ無しの対照 (R0 との分離) | 測定済み・分離は無意味になった | NODATA_BODY n=3 = 2008。R0 も現 HEAD で 2008 |

## 7. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 現 HEAD で −4 が消えた原因。dade5b85 から e695e9f3f までの main 側の変更 (IR md5 `baa100ff`→`423c347e`・ldfix F3c 36→46) のどれが効いたか未特定 | REPORT_1701・1952・2212 の「rt.o の計測 flag が −4 を生む」が現 HEAD で成り立つか未確認 | #2275 (本 issue に残す。PM 判断) |
| 受入条件 1・2・5 の機序判定 (データ由来か本体由来か、heap 開始位置) | −4 が現 HEAD に無いため判定不能。heap 開始位置は `__heap_base` の直接測定が無い | #2275 |

## 8. 再現

- `bash tools/m11/trap_triage/repro_1952_rt_mech.sh [N] [CONFIG...]` (CONFIG に `NODATA_BODY` を追加)。表は `work/split_1952/table.tsv`、実アドレスは `work/split_1952/addr.txt` (gitignore)。tracked 版は `table_2275.tsv`・`addr_2275.txt`。
- 前提: `FL_WIN64_DIR` = `[WIN64]` (`fl-win64` を展開し、`m11_build.sh` と `m11_gen_ir2.sh` で同じ値を使う。IR は PE のパスを記録する)・`work/` が `m11_gen_ir2.sh` 生成済み・`[EMSDK]` 配置済み。
- 素材: `oc_artifacts: fl-win64 work-m11 toolchain-emsdk` (`docs/WORKFLOW.md` §11)。

## 9. 測定 commit からの差分

- 測定 commit: `aa647a2ac` (pad を `g_dest_n`・`g_rec_*` と同じ並びにした版)。この commit の `tools/m11` で §3 の表を測った。
- 前回の版 `bf11784ec` (pad 修正前) の NODATA_BODY 行は、静的領域の並びが C_noren と 8 B・0x10 B ずれていたため採らない (§4 の結果で置き換えた)。
- `git diff aa647a2ac HEAD -- tools/m11 ':!tools/m11/trap_triage'` の出力は空 (本 REPORT と生値 tsv・addr は `trap_triage` 配下)。
