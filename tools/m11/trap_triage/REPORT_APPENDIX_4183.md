# #4183 付録: 923 の obj (0x10bd3960) の書込み候補 (unit 830・880) の呼出し元と同一性 (2026-10-15, n=1)

正本は `REPORT_APPENDIX_3823.md`。本付録は #4183 (`[M11-N209]`、親 #3823) の測定の全文。

## 1. 結論

- **受入 1 (同一性の判定)**: 部分達成。判定は「入口の引数からは同一性を確定できない」。unit 830 の `function_10c7cd0` の入口引数は `0` (obj ではない)、unit 880 の `function_125da90` の入口引数は `0xe5b1c0` (obj ではない)。両関数が書込む宛先 `0x10bd3960`〜`0x10bd397f` は、入口の引数から直接来ていない。宛先は関数内部で別に作られている。
- **受入 2 (呼出し鎖)**: 未達。静的呼出し元は §3 のとおり列挙したが、unit 830・880 で実際に走った呼出し経路は実測していない。
- **受入 3 (同一なら呼出し鎖、同一でないなら 923 の obj の遡り)**: 未達。どちらにも判定できず、遡りも未実施。
- 923 の `function_410b10` の入口 `obj` は unit 923 で `0x10bd3960` (実測、§2)。

## 2. 測定 (測定 commit `573088a23` = origin/main、コード変更は本 PR の追加分のみ)

素材 fl-win64・toolchain-retdec・toolchain-emsdk・work-m11 を `$RUNNER_TEMP/ws4183` に展開 (`FL_WIN64_DIR`・`RETDEC_ROOT`・`EMSDK_HOME` をそこに向けた)。

| 工程 | 結果 | 所要 |
|---|---|---|
| `m11_gen_ir2.sh` (IR 作り直し。`ir_conditions.json` が無く既存 `watch_obj_3823.sh` が失敗したため) | rc=0 (`boot_final.ll` 490761 行) | 51.4 秒 |
| `watch_obj_3823.sh` (store 監視、既存) | rc=0 / `[aw]` 66 件 (REPORT_APPENDIX_3823 §2 と一致) | 89.2 秒 |
| `entry_obj_4183.sh` (入口計装、新規) | rc=0 / `[ob]` 37 件 / unit 923 は trap | 57.7 秒 |

load average は工程中 0.3〜1.0。

### 2-1. 書込み (store 計装、既存と同じ)

unit 830 (`function_10c7cd0`・site 4015) と unit 880 (`function_125da90`・site 6778) は、いずれも `0x10bd3960`〜`0x10bd397f` の 32 B を 1 バイトずつ 0 にする (各 32 件)。REPORT_APPENDIX_3823 §2 と一致。

### 2-2. 入口の第 1 引数 (entry 計装、新規)

計装は `trap_triage/entry_obj_4183.py` が `boot_final3.ll` の対象関数の先頭に `m11_entry(第1引数, site)` を 1 件入れる (IR の値・分岐は不変)。8 関数 (`ob_sites.json`)。

| unit | 関数 | 第 1 引数 | 備考 |
|---|---|---|---|
| 830 | `function_10d50d0` (site 900002) | `0` | |
| 830 | `function_10c7cd0` (site 900001) | `0` | 書込み候補 (store 計装の site 4015) |
| 880 | `function_1263540` (site 900004) | `0` | |
| 880 | `function_125da90` (site 900003) | `0xe5b1c0` | 書込み候補 (store 計装の site 6778) |
| 923 | `function_4fb910` (site 900008) | `0xf6b900` | REPORT_APPENDIX_3823 §3 の local0 と一致 |
| 923 | `function_410730` (site 900006) | `0x10bd3960` | 923 の obj (trap 直前の呼出し) |
| 923 | trap | | |

`function_410b10` (site 900007) は、unit 923 の trap までの入口で hit していない。410730 の入口は hit している。trap は `function_410b10` の OOB 命令で起きるので、410b10 の入口計装が効いていないか、入口が trap の前に通っていない。本測定では判定できない (未確認)。

同じ番地 `0x10bd3960` は、unit 101・291・296・304・555 で `function_410730` の入口 obj として多数使われている。つまり 0x10bd3960 は全 unit で同じ種類の「obj」として使われ、途中の unit で別オブジェクトになる。

### 2-3. 判定

- unit 830・880 の書込み先 `0x10bd3960` は、両関数の入口引数 (`0` と `0xe5b1c0`) と一致しない。したがって「書込み先 = 入口の obj」ではない。
- 宛先の `0x10bd3960` は関数内部で作られる。その生成元 (どの load・どの計算で作られるか) は本測定では未確定。
- 923 の obj 同一性は、unit 830・880 の時点で「`0x10bd3960` が同じオブジェクトを指すか」を判定する必要がある。入口引数からは判定できないため、関数内の宛先計算を追う必要がある。

## 3. 静的な呼出し元 (IR)

`work/boot_final3.ll` の直接 call (間接 call は含まない)。

| 関数 | 直接呼出し元 |
|---|---|
| `function_10c7cd0` | `function_10d50d0` (1 件) |
| `function_125da90` | `function_1263540`・`function_1264050` (各 1 件) |
| `function_10d50d0` | 直接の IR 呼出し元なし (`m11_tr_` 経由のみ) |
| `function_1264050` | `function_12652c0` (1 件) |
| `function_1263540` | 直接の IR 呼出し元なし (`m11_tr_` 経由のみ) |
| `function_410b10` | `function_410730`・`function_410a50`・`function_410bc0`・`function_447860`・`function_4a23d0`・`function_505db0`・`function_5062e0`・`function_50b870` |
| `function_410730` | `function_44ac70`・`function_466950`・`function_466af0`・`function_467910`・`function_4fb1f0`・`function_4fb6e0`・`function_4fb780`・`function_4fb830` (ほか) |
| `function_4fb910` | `function_136c660`・`function_5de960`・`function_623840`・`function_832660`・`function_846130`・`function_883140`・`function_bf2500` |

呼出し鎖の推定 `function_1263540`・`function_1264050`・`function_10d50d0` のうち、`function_10d50d0` は `function_10c7cd0` の呼出し元で、`function_1263540`・`function_1264050` は `function_125da90` の呼出し元。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 830・880 で `0x10bd3960` を作る関数内の宛先計算 (どの load・計算で `[obj]` を作るか) | 受入 1 の同一性判定・923 の OOB の除去 | #4183 (継続。部分達成) |
| unit 830・880 で実際に走った呼出し経路 (`function_10d50d0`・`function_1263540`・`function_1264050` の入口) | 受入 2 | #4183 (継続) |
| 基点 unit JSON との突合 (受入 3・回帰 0) | 回帰 0 の確認 | #3823 の PR 本文の未解決表 |
