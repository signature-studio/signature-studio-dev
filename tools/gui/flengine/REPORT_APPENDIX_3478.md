# REPORT_APPENDIX_3478 (WIN-26 #3478)

親 #3353 (WIN-22) の受入 1「boot が init 1675 (`InitializeCriticalSection(0x12bd390)`) に届かない原因の特定」。窓の鎖 #3478 → #2904 → #2716 → #2717 の先頭。

## 1. 結論

- boot が init 1675 に届かないのは、**`InitUnits` (`function_4120c0`) が unit 114 (0 起算) の Init 実行中に Halt0 に入り、残りの unit を実行せずに抜けるため**。停止 unit の Init は `function_623840` (VA `0x623840`)。init 1675 は `function_1266a60` で、unit 882 (0 起算) の Init (FInit は `function_12669a0`・1676) に当たる。unit 882 は停止より後なので呼ばれない。
- `dllmain_done True` は **InitUnits の完走ではない**。InitUnits は trace の `[m11][unit 115/942]` (index0 114) の Init 中に Halt0 に入り、残りの unit を実行せずに抜けた (`function_412770` → JS 例外 `m11_dllmain_done` による脱出)。ここで「111/942 unit で中断」とは書かない: `init_count` 111 は別カウンタ (`tools/m11/m11_rt.c:148-158`) で、停止位置は trace の unit 番号で示す。`tools/m11/m11_ov.c:445` の「DllMain attach 完走」は Halt0 を DllMain の完了として扱う設計上の呼び名で、本 REPORT の「完走ではない」とは別の意味 (コードの注釈は本 PR で変えていない)。REPORT_APPENDIX_3353 §1・§3-1・§9-1 の「boot は完走する」は誤り (§5 で訂正)。
- Halt0 の直接条件は §3-3 (`[0x11f7110] != 0` と第 3 引数 `0x8494fc` の非 0)。実機で同じ経路が Halt しないかは**未判定**。子 issue に起票 (§7)。

## 2. 測定の組

- 測定 commit: `9a5767521` (origin/main)。本 PR の変更はツール 1 本 (`tools/gui/flengine/boot_halt_probe.mjs`) と REPORT のみで、boot の経路は変えていない。
- 素材: fl-win64 (`extracted/block00031_PE.bin`)・work-m11 (boot0〜4 の lift と m11 の既存 work)・toolchain-retdec (`RETDEC`)・toolchain-emsdk (`[EMSDK]`)。
- 再生成の手順 (work-m11 の IR は boot5・boot6 を含まないため、現 main で作り直した。すべて `tools/` の既存スクリプト):
  1. `bash tools/m11/m11_lift.sh m11_extra_ranges5.txt boot5 600` (9.8 秒・ir5 OK 2686 行)
  2. `bash tools/m11/m11_wndseed.sh` (boot6 lift・閉包 1212 関数・gen_ir2・WNDCLASS-CHECK PASS・3 分 35 秒)
  3. `bash tools/m11/m11_build.sh` (31.8 秒・signature mismatch 0)
  4. `bash tools/gui/flengine/build.sh` (24.8 秒・`m11_gui.cjs`)。`-g2` の診断 build は `build.sh` の `-g1`→`-g2` の sed 複製 (`cfi_boot7.sh` と同じ・コミットしない)
  5. `node tools/gui/flengine/run.mjs --wasm <m11_gui.cjs>` (0.37 秒)
  6. `node tools/gui/flengine/boot_halt_probe.mjs --wasm <-g2 の m11_gui.cjs> --out <json>` (0.5 秒)
- 注意: `m11_wndseed.sh` は追跡ファイル `tools/m11/results/wndclass_scan.json` を書き換える。本 PR ではコミットせず、`git checkout --` で戻した。
- 負の対照 (素材の旧 IR): 素材の `boot_final3.ll` (boot5・boot6 無し) で作った GUI build は `units_run 17 / init_count 18 / threw "memory access out of bounds"`。boot5・boot6 を入れて初めて `units_run 110` になる。

## 3. 結果 (`boot_halt_probe.mjs`・-g2 build)

| 項目 | 値 |
|---|---|
| `units_total` / `units_run` / `init_count` / `icall_miss` | 942 / 110 / 111 / 4 |
| `longjmp_halt0` (Halt0 → JS 例外 `m11_dllmain_done`) | true |
| 停止 unit (0 起算) | 114 (trace の `[m11][unit 115/942]`) |
| 停止 unit の Init VA | `0x623840` (`function_623840`) |
| init 1675 (`function_1266a60`) | unit 882 (0 起算) の Init。`arr1[882]` 直読み `0x1266a60` / FInit `0x12669a0` |
| init 1675 の到達 | **未到達** (停止 unit 114 < 882) |

- `run.mjs` (同じ build): `dllmain_done True`・`boot_threw None`・`boot_failfast None`・`reach 26 / impl 26 / stub 0`・`icall_miss 4`・`failfast_count 0`。
- trace の unit 値 (`init=0x223840` 等) は VA から `0x400000` を引いた値。`arr1` の直読み (`0x623840`) と一致する。

### 3-1. 停止までの呼出し鎖 (-g2 の JS スタック・Halt0 の直前)

`m11_boot_enter` → `entry_point` → `function_41d8f0` → `m11_InitLib` → `function_4120c0` (InitUnits) → `m11_icall` → `m11_tr_function_623840` → **`function_623840`** (unit 114 の Init) → `function_620cd0` → `function_867710` → `function_86b9a0` → `function_8494c0` → `function_41a800` → `function_4096d0` → `function_4096b0` → `function_412a40` → `function_4128b0` → `function_412770` (longjmp → `m11_dllmain_done`)

- 停止 unit の trace 直前の出来事 (順番どおり): `GlobalAddAtomW` stub (0 を返す)・`GetCurrentThread` stub (0 を返す)・`VirtualAlloc` 125.3 MB (#19・#20・#21 の 3 回・`live` 538.4 MB)・`GetMem` (icall `0xf960`) の反復・Halt0。
- 同じ unit (`0x223840` = `function_623840`) は `tools/m11/ldfix/REPORT_942.md` §2 の表に `halt0` として既出 (本 PR の測定と同じ unit)。

### 3-2. 停止の直接原因の候補を潰した実験 (commit しない)

- 実験 1: `work/m11_winstubs.c` の `GlobalAddAtomW` を `0xC001`、`GetCurrentThread` を `(void*)-2` (擬似ハンドル) に変えて再 build・再実行。結果は同じ (`units_run 110 / init 111 / Halt0` at unit 114・同じ呼出し列)。**この 2 つの stub の戻り値は停止の直接原因ではない** (実測)。元の stub に戻して測定を確定した。

### 3-3. Halt の直接条件 (機械語 と IR の突き合わせ)

- 停止 unit の呼出し鎖の要所は `function_8494c0` (`VA 0x8494c0`)。機械語: `mov qword [rbx],0`・`call 0x849480`・`mov rdx,[rip+0xdadc2e]` (= グローバル `0x11f7110`)・`lea r8,[rip+0x13]` (= `0x8494fc`・非 0 の定数)・`call 0x41a800`。
- `function_41a800` (IR `dec_label_pc_41a800`・機械語 `0x41a800` を capstone で確認): Delphi の interface cast の形。第 2 引数 (obj) が非 0 のとき `call [obj]` (vtable[0] = QueryInterface 相当) を第 3 引数 (IID 相当の `0x8494fc`) で呼び、戻り値 `eax != 0` なら `mov cl,0x17; call 0x4096d0` (RunError 23 相当・Halt)。`eax == 0` なら成功。`0x8494fc` はコード領域内 (`ret` の直後) を指す。実機でも同じ IID を読むかは未検証。
- グローバル `0x11f7110` は `function_849480` が書く。`[0x11f7110] == 0` のときだけ `function_8495c0(0x446b00, 1)` の結果 (非 0 なら +72) を格納する。`function_8495c0` は通常 obj を返す。
- よって、この unit で `[0x11f7110] != 0` になった時点で Halt は必然になる。実機で同じ経路が Halt しないなら、(a) グローバルが実機では 0 のまま (書込み側の差)、または (b) `function_41a800` の分岐の読みが誤り (lift 欠陥) のどちらか。**未判定**。子 #3748 の受入 1 で切り分ける。

### 3-4. Halt 時点のメモリ (停止後に wasm メモリを読んだ実測・`vt.mjs` 相当の一回限りの読取り)

- `[0x11f7110]` = obj `0x10c5c468` (heap)。obj の vtable = VA `0x446878`、vtable[0] = VA `0x4467ac` (コード・先頭は `call 0x4133f0` で、IID 比較を行う QueryInterface の形ではない)。
- `0x8494fc` (`function_41a800` の第 3 引数) の 16 バイトは `8b 48 08 e8 6c 9d c1 ff 48 8b 45 20 c6 40 1d 01` (コードのバイト列で、GUID ではない)。
- よって「第 3 引数が GUID へのポインタ」という読みは当たらない可能性が高い。実機で同じ値が渡るかは未検証。Halt の判定条件の読みを子 #3748 で詰める。

## 4. 考察 (推定を含む)

- 直接の原因: unit 114 の Init 内で発生した例外 (種別未特定) が Halt0 に届き、`InitUnits` の while ループが抜ける。その後の unit 115〜941 は呼ばれず、unit 882 の Init (init 1675) も呼ばれない。CS `0x12bd390` が登録されない → CFI が `EnterCriticalSection` で `CS-MISS` する (REPORT_APPENDIX_3353 §3-3 と整合)。
- 推定: 停止の前の `VirtualAlloc` 125 MB の反復 (live 538 MB) と `GetMem` の増加が、例外の材料になっている可能性。検証していない。
- 数値の差: 本測定の `units_run 110 / icall_miss 4` は REPORT_APPENDIX_3353 の `109 / 7` と一致しない。再生成 IR の差と推定するが、原因は未確認 (同じ停止点 unit 114・init 111 は一致)。

## 5. 訂正 (REPORT_APPENDIX_3353)

- 3353 §1・§3-1・§9-1 の「boot は完走する」「boot の経路は boot7 を含まない既定の IR と同じ」は、`dllmain_done True` を完走と読んだ誤り。実際は unit 114 の Halt0 脱出 (本節 §1)。
- 3353 の CS 計装の結論 (`0x12bd390` の `CS-INIT` は 0 件・CFI は `CS-MISS`) は本測定でも同じで、変わらない。
- 3353 の本文は履歴として残し、本節で訂正する。

## 6. 製品 KPI (起動・GUI)

- 前 (origin/main `9a5767521` の再生成 IR): `units_run 110 / init_count 111 / Halt0 at unit 114 / reach 26 impl 26`。
- 後 (本 PR): 挙動は変えていない (ツールと REPORT のみ)。同じ値。
- 最初のウィンドウ: 本 PR では確認していない (`CreateWindowExW` の到達は run.mjs の GUI-REACH の表で見るのみ)。動かしていないもの: 実 FL の起動・e2e.sh。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| Halt0 を起こした例外の種別と発生箇所 (unit 114 `function_623840` → `function_41a800` 以降・VirtualAlloc 125 MB と GetMem の関係) | init 1675 (CS 登録) に届かない。CFI は `CS-MISS` のまま | [WIN-39] (子 issue・親 #3478) |
| 停止解消後の unit 882 (`function_1266a60`) の到達と CS 登録 (`CS-INIT 0x12bd390`) | 未測定 | [WIN-39] の受入 |
| `units_run` 110 と 109 の差 (再生成 IR) | 測定の同一性の説明が未了 | 本 PR の §4 (未確認) |
| `init_count` 111 と init 列の行番号 (`inits_text.txt`) の対応 | 未測定 (本測定は停止 unit の trace だけを記録し、`init_count` の増分を init 列へ対応づけていない)。`init_count` は IR の init prologue で増える別カウンタ (`tools/m11/m11_rt.c:148-158`) で、停止 unit (index0 114) の添字とは別の数え方。111・1675 の関係は未確認。停止位置の特定 (unit 114) には不要 | [WIN-39] #3748 (受入 1 の残り) |
