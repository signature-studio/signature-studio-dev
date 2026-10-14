# REPORT_APPENDIX_2203 — unit 158 の j=12 が読む 2 区間の OFF/ON 比較 (#2203, 親 #2152)

測定 commit: **`da002968`** (コードを変えた最後の commit = 計測 script から repo 外絶対パスを外した commit)。計装の追加は `99ca61b2`。最終測定はこの commit の状態で再実行した (§3)。`99ca61b2` で取った値と全出力は一致した。HEAD からこの commit までのコード差分は 0 (§5)。

## 1. 結論 (受入条件 1〜4)

- **受入 1 (ON の 2 区間の値)**: 達成。ON で j=12 の `function_412c20` 呼出し前後の値を記録した。2 区間 A (`0xfa5108`〜`0xfa5c68`)・B (`0x11e69b0`〜`0x11e6b98`) の指紋 (FNV-1a 64) と `0x11e6a2c` の 4B (`w`) を出力。j=12 は pre A=`bb2881295caef8e7`・post A=`2684a2f3765b4e72`、B=`9ddaad939734f7ba`・w=`0x4b0` (B と w は pre/post で不変)。
- **受入 2 (値差と ok/trap の因果の判定)**: 2 区間の値差は **ok/trap を変えない**。計装なし (clean) の unit 158 は ON/OFF とも ok。分類は次のとおり。
  - A 区間の差: j=12 の `len` 差 (OFF=0 / ON=1) の**下流**。ON だけ `412c20` (確保) が走り、その後 A の指紋が変わる。読出し値の差ではない。
  - j=12 の `len` 差 (0 vs 1): **意味的差** (推定)。呼出し元で決まる `len` が j<12 の状態差から変わる。伝播経路は未追跡 (§6 (a))。
  - ON だけ trap する件 (entry 指紋を入れた観測版): **観測副作用**。同じ観測を入れた OFF は ok (§3 表 1)。
- **受入 3 (OFF の dest 値の直接記録と 1 対 1 比較)**: 達成。OFF (lift 版 IR) の entry 出力 (`[d413060]`) を取った。j=0〜16 の dest は ON と全件一致。`len` は j=12 だけ不一致 (OFF 0 / ON 1)。
- **受入 4 (決定性・所要・load)**: 達成。4 構成 (clean ON/OFF・dest-build ON/OFF) すべてで同一 build の 2 回の出力が `cmp` 一致。node 1 回の所要は 363〜377 ms。dest 実行の開始時 load は 0.27〜0.78 (4 core)。最終測定の所要は dest 2 構成が 107 秒 (build 3 回 + 実行 4 回)、clean 2 構成が 46 秒 (build 2 回 + 実行 4 回)。

## 2. 計装 (読取りのみ・値と分岐は不変)

- `tools/m11/m11_ov.c`: `m11_pd2118_in` (entry の dest/len と 2 区間の指紋・`w`)・`m11_pd2118_pre`/`m11_pd2118_post` (`len>0` の `412c20` 呼出し前後)。`M11_PRINT_DEST_2118=1` のときだけ有効。
- OFF (lift 版 `function_413060`): `tools/m11/trap_triage/dest_2203.py` が `boot_final3.ll` に同名の呼出しを挿入する (本体の値・分岐は変えない)。ON は C 版 `function_413060` に同じ呼出しを入れた。
- 実行: `bash trap_triage/dest_2203.sh <off|on> <out>` (build → 同一 build で 2 回実行 → `cmp`)。runner は `trap_triage/run_dest_2203.mjs` (`unit 0,1,158`)。
- clean は `M11_OV_413060={0,1} M11_INSTR_413060=0 M11_DEST_READ=1 bash m11_build.sh` の後に runner を実行 (計装なし)。

## 3. 実測 (測定 commit `da002968`・HEAD で再現)

表 1: unit 0・1・158 の結果と決定性 (`da002968`・IR は `m11_gen_ir2.sh` 再生成後・`ldfix errors=0`)。

| 構成 | 計装 | unit 0 | unit 1 | unit 158 | 2 回の出力 | 1 回の所要 (node) |
|---|---|---|---|---|---|--:|
| clean OFF (`M11_OV_413060=0`) | なし | ok | ok | ok | 一致 | 371 / 377 ms |
| clean ON (`M11_OV_413060=1`) | なし | ok | ok | ok | 一致 | 377 / 363 ms |
| dest-build OFF | entry 指紋 + dest (IR 挿入) | ok | ok | ok | 一致 | 368 / 376 ms |
| dest-build ON | entry 指紋 + dest + j=12 pre/post (C 版) | ok | ok | **trap: memory access out of bounds** (entry 17 件目の後) | 一致 | 372 / 370 ms |

表 2: unit 158 の `function_413060` 呼出し (entry 0 始まり・dest-build の出力)。entry 0〜11 は dest・len・A・B・w が OFF/ON で全件一致。B は entry 0 の呼出し後に一度だけ変わり (`160c3baea1fede5a`→`9ddaad939734f7ba`)、以後は両者で不変 (`w`=`0x4b0` は全件不変)。

| entry | 項目 | OFF | ON |
|---|---|---|---|
| 12 | dest / len | `0x10a9f978` / **0** | `0x10a9f978` / **1** |
| 12 | A (entry) | `bb2881295caef8e7` | `bb2881295caef8e7` (一致) |
| 12 | `412c20` 前後 | 呼ばれない (`len≤0` 経路) | pre A=`bb2881295caef8e7` → post A=`2684a2f3765b4e72` (B・w 不変) |
| 13 | dest / len | `0x10a9f788` / 59 | `0x10a9f788` / 59 |
| 13 | A (entry) | `bb2881295caef8e7` | **`494d8c9191dc6407`** (差は j=12 の確保の後) |

- len=59 の呼出し (entry 1・3・6・13) の `412c20` 前後の A 変化は、j=12 より前では OFF/ON で一致 (例: entry 1 は pre `a1544bbd8afa443e` → post `7f760d1028bc36b8`)。
- ON の entry 17 (dest `0x10aa0810`) の後で unit 158 が trap する。OFF は同じ entry を経て 28 件すべて呼び、ok で終わる。

## 4. 判定 (受入 2)

| 区分 | 判定 | 根拠 |
|---|---|---|
| 2 区間の読出し値 (`412c20` が読む `0x11e6a2c`) | 差なし (ON で常に `0x4b0`) | 表 2 (entry 12 の pre/post・全 entry の w) |
| A 区間の差 | **j=12 の len 差の下流** (意味的差の帰結・ビルド差ではない) | ON だけ `412c20` が走り、post で A が変わる。OFF は走らない |
| j=12 の len 差 (0 vs 1) | **意味的差 (推定)** | 413060 の C 版 (D4 修正) と lift 版の差が状態を変え、呼出し元の `len` が変わったと読む。伝播経路は未追跡 |
| ON の entry-trap | **観測副作用** | 同じ観測を入れた OFF は ok。clean (計装なし) は ON/OFF とも ok |
| ok/trap への影響 | **なし** (clean で判定) | 表 1 の clean 行 (ON/OFF とも 0・1・158 = ok) |

- `REPORT_APPENDIX_944` §5.3 の「単独実行 (`SV_ONLY=158`) では 5 構成すべてで trap」(#2003 の撤回) とは別条件の観測である: 本付録は `0,1,158` の連続実行で、観測版の ON だけが trap する。
- 2 区間の値差を理由に ok/trap が変わるとは、本測定では言えない。

## 5. コード差分 (受入 4・規約 6)

- 測定 commit `da002968` から HEAD までのコード範囲の差分は 0 行 (`git diff da002968 HEAD -- tools/m11/m11_ov.c tools/m11/trap_triage/dest_2203.py tools/m11/trap_triage/dest_2203.sh tools/m11/trap_triage/run_dest_2203.mjs` は空。以後の commit は docs のみ)。
- 再測定は不要 (測定 commit で実行した)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) j=12 の `len` 0→1 の上流: どの状態差が呼出し元の `len` を変えるか (D4 修正の伝播経路) | 意味的差の確定 (REPORT_944 §4 (a)) | #2152 (親) |
| (b) A 区間の書込み元 (`412c20` 呼出し後に A が変わる。IR の store 計装 (`watch_range_2118`) では捕捉されていない: C 側・intrinsic の可能性) | 2 区間の値差の機構 | #2152 (親) |
| (c) entry 指紋で ON の unit 158 だけが trap する機構 (観測副作用の機構) | 観測版の解釈 (判定は clean で行った) | #2152 (親) |

## 7. 旧値との差 (記録のみ・判定には使わない)

- §3 の j=12 の dest は `0x10a9f978` (entry 指紋版)。`REPORT_APPENDIX_2152` §3 の `0x10a9e0b8` とは異なる。同じ `len=1` である。build の差 (pre/post 版では `0x10a9f958`) でもヒープ位置が変わる。dest は `len` と合わせて OFF/ON を比べた。
- pre/post だけの版 (entry 指紋を入れない版) では ON の unit 158 も ok だった。その版の出力は残していない。
