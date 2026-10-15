# REPORT_APPENDIX_3748 (WIN-39 #3748)

親 #3478 の子。受入 1「Halt0 を起こす例外の種別と発生 IR 箇所の特定」を扱う。受入 2 (停止の解消) と受入 3 (`CS-INIT 0x12bd390`) は子 #4011 [WIN-42] と #4012 [WIN-43] に移した。

## 1. 結論

- **例外の種別**: Delphi の interface cast (`_IntfCast` 相当) の失敗。`function_41a800` が `RunError 23` (`mov cl,0x17; call 0x4096d0`) を呼び、Halt0 になる。
- **発生 IR 箇所** (実測・IR 突合): `tools/m11/work/boot_final3.ll` の `function_41a800` (行 160876〜160915)。Halt の判定は `%7 = trunc(%4)` (`%4` = `ptrtoint arg3` = IID ポインタ `0x8494fc`) で、`%8 = icmp eq %7, 0` の分岐。非 0 なので必ず Halt する。
- **直接原因 (推定を含む)**: 機械語では判定は `call [rax]` (vtable[0]・VA `0x41a840`) の戻り値 `eax` で決まる。生 RetDec 出力 (`boot0.drc.ll` 行 27893〜27925) にこの呼出しが無く、代わりに IID ポインタの値が判定に使われている。RetDec がメモリ間接 call を脱落させた類型で、`docs/DEFECTS.md` の D15 (「stage-0 がメモリ間接 call を丸ごと欠落させる」) と同じ。
- **実機での挙動 (推定)**: 機械語を読む限り、この IID は obj の class の interface table の entry 3 に実在し (§4)、`GetInterface` は成功 (`S_OK`) を返すはず。したがって実機では Halt しないと推定する。実機で動かして確かめてはいない。

## 2. 測定の組

- 測定 commit: `8aa1bdc78` (現 head・再測定を実施)。`git diff 8f36af762 8aa1bdc78 -- tools/gui/flengine` は 18 ファイル・1589 行 (main 取り込み分を含む)。
- **現 head `8aa1bdc78` で再測定し、§3 の値と同じ** (取り込み前の `8f36af762` の値と一致)。下の §5 実験 A も現 head の IR で再確認した。
- 素材: `$ARTIFACTS_DIR` の 4 本 (`fl-win64`・`toolchain-emsdk`・`toolchain-retdec`・`work-m11`) を展開した。`fl-win64` は一時展開先 (`FL_WIN64_DIR` に指定)、`toolchain-retdec` は一時展開先の `retdec/` (`RETDEC_ROOT` に指定して使う)、`toolchain-emsdk` は [EMSDK] の runner 既存物を emsdk_env で読み込んで使った (展開物は使っていない)、`work-m11` は `tools/m11/work/` (repo 直下・gitignore)。
- **apt-mingw が必要だった**: `build.sh` は `tools/gui/gen_api.py` が `x86_64-w64-mingw32-gcc -aux-info` を呼ぶため、runner に `gcc-mingw-w64-x86-64` を `sudo apt-get install` で入れた (WORKFLOW §11 の `apt-mingw` 経路)。旧 REPORT の「GUI build は不要」は現 runner では成り立たない (本節で訂正)。
- 再生成 (REPORT_APPENDIX_3478 §2 の手順 1〜4 と同じ順・現 head `8aa1bdc78`): lift boot5 (`ir5 OK 2686 行`・rc 0) → `m11_wndseed.sh` (rc 0・閉包 1212・WNDCLASS-CHECK PASS・3 分 28 秒) → `m11_build.sh` (rc 0・signature mismatch 0・30 秒) → `tools/gui/flengine/build.sh` (rc 0・mismatch 0・undefined 0・duplicate 0・24 秒・`emcc` は emsdk_env の読込後)。`ir_conditions.json` の `ir_sha256` = `5aa8f1e9…`・`ldfix`/`qstore`/`ld108`/`ld115`/`r8b` = applied。
- **build の出力名の注意**: `build.sh` は `m11_gui.cjs` 固定で出すため、`-g1` と `-g2` を続けて作ると後の build が前を上書きする。本測定は各 build の直後に別名 (`m11_gui_g1.cjs` / `m11_gui_g2.cjs`) へ退避した。`-g2` は `build.sh` の `-g1`→`-g2` の sed 複製 (`tools/gui/flengine/` に一時的に置いて実行後に削除・コミットしない)。
- `m11_wndseed.sh` は追跡ファイル `tools/m11/results/wndclass_scan.json` を書き換えた。本 PR ではコミットせず、`git checkout --` で戻した。
- 測定: `node tools/gui/flengine/run.mjs --wasm m11_gui_g1.cjs` (0.63 秒・rc 0) と `node tools/gui/flengine/boot_halt_probe.mjs --wasm m11_gui_g2.cjs` (0.52 秒・rc 0)。

## 3. 結果 (`boot_halt_probe.mjs`・-g2 build)

| 項目 | 値 |
|---|---|
| `units_total` / `units_run` / `init_count` / `icall_miss` | 942 / 110 / 111 / 4 |
| `longjmp_halt0` | true |
| 停止 unit (0 起算) | 114 (VA `0x623840`) |
| init 1675 の到達 | 未到達 (停止 unit 114 < 882) |

- `run.mjs` (-g1・現 head `8aa1bdc78`): `dllmain_done True`・`boot_threw None`・`boot_failfast None`・`units_run 110`・`init_count 111`・`reach 26 / impl 26 / stub 0`・`icall_miss 4`・`failfast_count 0`・`CreateWindowExW` 1 回 (到達)。
- `boot_halt_probe.mjs` (-g2・現 head): `units_run 110`・停止 unit 114 (`0x623840`)・`longjmp_halt0 true`・`halt_intf` の `arg3_in_table: true` (entry 3)・`hit: true` (entry 3)。取り込み前 (`8f36af762`) と同じ値。
- REPORT_APPENDIX_3478 §4 の `units_run 110 / 109` の差: 本 run でも **110 を再現** (3478 と同じ)。109 (3353 の測定) は再現せず、原因は未確認のまま (本件の範囲外)。

### 3-1. 停止までの呼出し鎖 (-g2)

`m11_boot_enter` → `entry_point` → `function_41d8f0` → `m11_InitLib` → `function_4120c0` → `m11_icall` → `m11_tr_function_623840` → `function_623840` → `function_620cd0` → `function_867710` → `function_86b9a0` → `function_8494c0` → `function_41a800` → `function_4096d0` → `function_4096b0` → `function_412a40` → `function_4128b0` → `function_412770` (longjmp)。

### 3-2. `function_8494c0` と `function_41a800` の機械語 (VA)

- `8494e9`: `call 0x41a800`。引数は rcx = `&[rbx]` (Dest)・rdx = `[0x15f7110]` (Source = obj `0x10c5c468`)・r8 = `0x8494fc` (IID ポインタ)。
- `41a840`: `call QWORD PTR [rax]` (`rax` = Source の vtable。Source の 1 番目の slot = vtable[0])。`41a842`: `test eax,eax`。`41a844`: `je 41a853`。`41a846`: `mov cl,0x17; call 0x4096d0` (RunError 23)。
- vtable[0] は `0x4467ac` (wasm)。中身は `48 83 c1 b8` (`add rcx,-0x48`) `e9 …` (`jmp 0x41c180`)。
- `0x41c180` (QueryInterface 本体): `sub rsp,0x28; call 0x40fcf0; test al,al; je 41c191; xor eax,eax; jmp; mov eax,0x80004002 (E_NOINTERFACE)`。戻り値 `al` は `GetInterface` の成否。

### 3-3. lift 後の IR (`boot_final3.ll`)

- `function_41a800` (行 160876〜160915): 呼出し `call [rax]` が無い。`%7 = trunc(%4)`・`%8 = icmp eq i32 %7, 0` で分岐し、`%4` は arg3 (IID ポインタ)。
- 生 RetDec 出力 (`boot0.drc.ll` 行 27893〜27925) も同じ形。RetDec の段階で脱落している。
- `function_40fcf0` (行 147483〜147540): AddRef の `call QWORD [rax+8]` (機械語 `40fd3a`) が無い (空ブロック: `store i64 %spec.select` だけ)。`D15` の同じ類型。

## 4. QueryInterface 経路の実測 (halt 時点の memory・probe の `halt_intf`)

| 項目 | 値 |
|---|---|
| Source (obj) | `0x10c5c468` (`[0x11f7110]`) |
| Self (thunk の `add rcx,-0x48` 後) | `0x10c5c420` |
| VMT (`[Self]`) | `0x446b00` |
| interface table (`[VMT-0xc0]`) | `0x446940`・件数 5 |
| 第 3 引数 IID | `{B0FC9353-5F0E-11D3-A3B9-00C04F79AD3A}` |
| 一致する entry | **entry 3** (IOffset 80 = `0x50`・VTable `0x4468a8`) |

- `GetInterfaceEntry` (`0x40fd90`): table の 40 バイト (`0x28`) の entry を先頭から比べ、IID 16 バイトの一致で返す。entry 3 は一致する (probe の `arg3_in_table: true`)。
- 機械語上は、一致すれば `Obj = Self + 80` (非 0)・`AddRef`・`setne al` で `al = 1`。QueryInterface は 0 (`S_OK`) を返す。これが実機の挙動の推定 (§1)。

## 5. 実験 (コミットしない・work 内のみ)

- 実験 A (現 head `8aa1bdc78` で再確認): `boot_final3.ll` の `function_40fd90` (行 147575) の `icmp eq i64 %11, %arg2` を `load i64 [arg2]` との比較に直した (機械語 `cmp r11,[r9]` の逆参照を復元)。これは main の `b585af9f0` (`pass_m2s_fn40fd90_iid`) と同じ書換えだが、main の既定は `a06acf466` で `M11_M2S=1` の gate の下 OFF のため、既定の IR には入らない。`build.sh` (-g1・-g2) は通った。結果は **動かず** (`dllmain_done True`・`units_run 110`・`CreateWindowExW` 到達・停止 unit 114 (`0x623840`)・同じ呼出し鎖・`halt_intf` の `hit: true` は entry 3)。
- 実験の IR は既定に戻した (`iid0` 0 件を確認)。`m11_build.sh` は再実行していない。
- 解釈: 比較の欠陥 (`function_40fd90`・D15 とは別の脱落) は実在するが、`function_41a800` が vtable の呼出しを持たないため、QueryInterface の結果は今も使われていない。両方直して初めて効くので、子 #4011 と #4012 に分けた。
- 実験の IR は元に戻した (`boot_final3.ll` は `m11_build.sh` 再生成前のものに戻し、`grep -c iidlo12` は 0)。

## 6. 製品 KPI (起動・GUI)

- 前 (`f4e471170` の再生成 IR): `units_run 110 / init_count 111 / Halt0 at unit 114 / reach 26 impl 26`。
- 後 (現 head `8aa1bdc78`・再測定): 同じ値 (`units_run 110 / init_count 111 / Halt0 at unit 114 / reach 26 impl 26`)。本 PR は挙動を変えていない (probe の表示項目を増やしただけ)。
- 最初のウィンドウ: `run.mjs` の到達表で `CreateWindowExW` が 1 回到達する (本 PR での変更なし)。実 FL の起動と `e2e.sh` は動かしていない。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_41a800`・`function_40fcf0` の vtable 呼出しの脱落 (D15 類型)。QueryInterface 本体 `0x41c180` が closure の外 | 停止が解消しない。unit 114 で Halt0 が続く | #4011 [WIN-42] |
| `function_40fd90` の IID 比較の先頭 8 バイトの逆参照の脱落 (`icmp eq i64 %11, %arg2`)。main の `b585af9f0` は同じ書換えを `M11_M2S=1` の gate の下に入れており、既定 OFF (`a06acf466`)。実験 A で効果が無いことは確認済み。同形の別箇所 1 件 (`boot_final3.ll` 行 214667 付近) は未分類 | GetInterface が IID で一致しない (IInterface 以外)。既定 IR では未修正 | #4012 は PR #4020 (`8fbb0e9eb`) で close 済み。残りは #4011 の受入に含める (本 PR で子は起票しない) |
| 停止解消後の unit 882 (`function_1266a60`) の到達と CS 登録 (`CS-INIT 0x12bd390`) | 未測定 | #4011 の受入 3 |
| `init_count` 111 と init 列 (`inits_text.txt`) の行番号の対応 | 未測定。停止位置 (unit 114) の特定には不要 | #3478 の未解決 (本件の範囲外) |
| `units_run` 109 (3353) と 110 (3478・本 run) の差 | 本 run では 110 を再現。109 の原因は未確認 | #3478 の未解決 (本件の範囲外) |
