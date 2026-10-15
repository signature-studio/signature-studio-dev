# ildsp (`block24360_PE.bin`) vtable 経由の実体 closure (10 export)

親: #161 (T-SH-15)。ildsp の規模調査 (§1–§3) は `REPORT.md` (§2 の closure は `.pdata` 基準の下限)、GeneralPitchShifter の vtable の静的抽出 (`REPORT.md` §4) とは別の測定。本文書の節番号 §4.x は分離前の REPORT §4 のまま。

再現: `FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_closure.py` と `python3 tools/shared/scripts/ildsp_closure_check.py tools/shared/work/raw/ildsp_closure.json`。

## 4. vtable 経由の実体 closure (#161 本 run・測定 commit は §4.6)

### 結論
- REPORT.md §2 の closure (`.pdata` 基準・CreateInstance の直接 call/jmp 先) は、**深さ 1 では 10/10 で vtable の slot 先を含まない**。CreateInstance は wrapper の vtable を置くだけで、slot 先を直接呼ばない。
- 推移閉包 (`.pdata` の無い先を含む) では、**3 件で slot 先と重なる**: LowFreqEnhancer (slot 先 0x17bdd0)・Limiter (0x169150)・Transmitter (0x1a6a30・0x1a7990)。
- vtable 経由で数えると 10 export 全てで実体に届く。最小は **GeneralPitchShifter** (45 関数・1,347 命令)。次点は Transmitter (55 関数・2,315 命令) だが、closure 内の vcall 形 `call [reg+disp]` が 60 件あり dispatch 先が未確定のまま残るため、子の対象にしない。vcall 1 件の **WaveformColouring** (70 関数・2,757 命令・SIMD 23.8%) を子 #2484 とする。instance の lift 単位は「CreateInstance + vtable slot 先の到達集合」とする。
- 誤差の向き: 間接 call の先は含まない (下限側)。`.pdata` の無い先の範囲は近似 (§4.1 手順 4) で、上限側に偏りうる。

### 1. 再現と手順
```
FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_closure.py
FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_closure_check.py tools/shared/work/raw/ildsp_closure.json
```
- `ildsp_closure.py`:
  1. CreateInstance (と直接 tail jmp 先) から `lea reg,[rip+X]` の直後 4 命令以内の `mov qword ptr [r],reg` を探し、X を wrapper の vtable とする。
  2. vtable の先頭から .text 内を指すポインタを slot とし、.text 外を指す所で打ち切る。
  3. slot 先が thunk (`mov rcx,[rcx+8]` で始まり直接 jmp で終わる) なら jmp 先を実体とする。
  4. 実体から直接 call / 直接 jmp を辿る。辿り先が `.pdata` に無ければ、その先頭を関数とし、次の `.pdata` 先頭までを範囲とする (近似)。同じ関数範囲内の jmp (内部分岐) は関数として数えない。
  5. 命令数・SIMD 比・間接 call 数は、到達関数の命令開始アドレスの**和集合**で数える (範囲の重なりを二重計上しない)。
  6. CreateInstance 単体 (同じ規則) と slot 先の到達集合の和集合を出す。
- `ildsp_closure_check.py`: JSON の関数集合 (`function_rvas`) の範囲を GNU objdump で逆アセンブルし、命令開始アドレス (RVA) の集合を capstone の集合と比べる。命令ごとに SIMD・間接 call の判定も比べ、JSON の数値と再計算値の一致も見る。既知の差分 (§4.3) 以外は非 0 で終了する。
- 実測 (測定 commit で 3 回): `ildsp_closure.py` real 0.401 / 0.404 / 0.405 s (測定後の load 0.03、4 core)。stdout と JSON は 3 回とも `cmp` で完全一致。`ildsp_closure_check.py` real 1.85 s、`ALL OK` (rc 0)。入力 `block24360_PE.bin` sha256 f4b23b0f…。
- ネガティブ確認: JSON の GeneralPitchShifter の命令数を 1 増やすと `MISMATCH`・rc 1 (検算が件数の改変を検出することを確認)。

### 2. 結果 (10 export・実測)
| export | vtable (RVA) | slot 数 | thunk | 関数数 (`.pdata` 無し) | 命令数 | SIMD 比 | 間接 call | 間接比 | CreateInstance 単体 命令数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GeneralPitchShifter | 0x3dfcf8 | 6 | 3 | 45 (16) | 1,347 | 4.0% | 10 | 8.8% | 961 |
| LimiterLite | 0x3dfd80 | 15 | 1 | 89 (31) | 4,008 | 26.8% | 24 | 12.5% | 1,140 |
| Limiter | 0x3dff40 | 22 | 5 | 94 (34) | 3,115 | 10.1% | 20 | 9.2% | 1,627 |
| LowFreqEnhancer | 0x3dfff8 | 6 | 3 | 219 (54) | 13,685 | 6.8% | 82 | 11.6% | 13,018 |
| PSOLA | 0x3e0030 | 6 | 3 | 82 (29) | 4,601 | 21.4% | 18 | 8.2% | 961 |
| Shimmer | 0x3e0068 | 11 | 6 | 121 (29) | 6,601 | 28.0% | 57 | 13.4% | 2,612 |
| StereoEnhancer | 0x3e00c8 | 6 | 3 | 220 (55) | 13,190 | 6.9% | 82 | 12.5% | 12,658 |
| TransientLooper | 0x3e0100 | 9 | 4 | 227 (57) | 14,168 | 7.3% | 83 | 11.4% | 1,016 |
| Transmitter | 0x3e0150 | 11 | 5 | 55 (20) | 2,315 | 5.1% | 70 | 21.6% | 1,747 |
| WaveformColouring | 0x3e01b0 | 6 | 0 | 70 (22) | 2,757 | 23.8% | 19 | 11.1% | 2,145 |

- 命令数・関数数は CreateInstance の closure と slot 先 closure の和集合 (重複は 1 回)。「CreateInstance 単体」は同じ規則で CreateInstance だけから辿った値で、REPORT.md §2 の値 (`.pdata` のみ) とは規則が違う。GeneralPitchShifter の CreateInstance 単体は 36 関数・961 命令 (JSON の `entry_only`)。
- 前版 (測定 commit b8f8a0f7・`.pdata` の無い先を捨てていた版) の値 (例: GPS 15 関数・473 命令) は下限で、本表で置き換える。
- 指摘の試算との差: 間接 call 数は 4 export とも一致。関数数は GeneralPitchShifter・WaveformColouring・Transmitter が一致し、LowFreqEnhancer だけ試算 249 に対し 219。試算の命令数は、重なる範囲を二重計上していた分だけ大きい (GPS 1,364 → 1,347、WC 2,803 → 2,757、Transmitter 2,362 → 2,315)。LowFreqEnhancer は `.pdata` の無い範囲内の内部 jmp 先 30 件を、試算が関数として数えていたため (本版は数えない)。

### 3. 検算 (objdump との照合)
- 検算は関数集合 (JSON の `function_rvas`) と範囲定義を `ildsp_closure.py` と**共有する**。検算するのは命令の復号と集計 (数・SIMD・間接 call) だけで、closure の辿り方 (`.pdata` の無い先の扱い) は検算しない。closure の取りこぼしは本スクリプトでは検出できない。§2 (`ildsp_survey.py`) も同じ `.pdata` 基準で、同じ下限の注記が付く。
- 結果: 10 件中 9 件は命令開始アドレスの集合が完全一致し、SIMD・間接 call の判定も一致した。TransientLooper は 1 件の既知差分 (下記) のみ。判定は `ALL OK` (rc 0)。
- 既知差分 (TransientLooper・RVA `0x191c29` の 1 件のみ): 関数 `0x190fa0` (範囲 0x190fa0–0x191c80) の `0x191c20` 付近に switch 用の 4 byte RVA 表 (`cd 10 19 00 49 11 19 00 c5 11 19 00`) が埋まる。
  - `0x191c1f` の `add ch,cl` (`00 cd`) は両者とも同じ位置から復号され、`cd` (0x191c20) は命令として現れない。
  - `0x191c28` の `c5 11 19` は不正な VEX 接頭辞。capstone はここで復号できず 1 byte (0x191c28) を飛ばし、`0x191c29` から `adc dword ptr [rcx], ebx` を 1 件として数える。
  - objdump は `0x191c28` を `(bad)` として 3 byte を 1 行で消費し、`0x191c29` を命令として出さない。
  - `ildsp_closure_check.py` の `KNOWN_DATA_IN_CODE` はこの RVA との完全一致のみを許す。件数の比較だけでは相殺する差を見逃すため使わない。
- 旧版の説明 (「`int 0x10` 等として 1 件数え、objdump は数えない」) は誤りだった。
- 末尾 jmp の内訳 (§4.4 の表) は、同じ関数集合を objdump で走査して数えた値を `[tail]` 行に出す。判定には使わない (参考値)。

### 4. 間接 call の内訳 (lift の障害)
- 定義: **間接 call** = 即値でない `call` (`call [mem]`・`call reg`)。`call [rip+X]` で X が IAT (import) なら「IAT」、IAT 外の画像内ポインタなら「画像内関数ポインタ」。`call [reg+disp]` は vcall。末尾 jmp は間接 call に数えない (下の表 (参考))。
- 末尾 jmp (即値でない `jmp`) の分類: `jmp [rip+X]` は IAT か画像内ポインタ、`jmp reg` は reg、`jmp [reg+disp]` は vcall 形 (tail call)、`jmp [base+idx*8]` は switch 表の間接 jmp (tail call ではない) で、別の列にする。
- 件数の出典: 間接 call の件数は capstone と objdump の一致 (§4.3)。末尾 jmp の件数は `ildsp_closure_check.py` の `[tail]` 行 (objdump の出力から数えた値)。例 (RVA。objdump の `# 0x180268140` は ImageBase 0x180000000 を足した絶対アドレス): GeneralPitchShifter の 0x1b932c `jmp QWORD PTR [rip+0xaee0d]` (参照先 RVA 0x268140 = IAT)、LimiterLite の 0x1aaba7 `jmp QWORD PTR [rax+0x10]` (vcall 形)、PSOLA の 0x101e `jmp QWORD PTR [r10+rax*8]` (switch 形)。

| export | 間接 call 計 | IAT | 画像内関数ポインタ | vcall | call reg |
|---|---:|---:|---:|---:|---:|
| GeneralPitchShifter | 10 | 8 | 2 | 0 | 0 |
| LimiterLite | 24 | 16 | 2 | 5 | 1 |
| Limiter | 20 | 16 | 2 | 1 | 1 |
| LowFreqEnhancer | 82 | 68 | 8 | 4 | 2 |
| PSOLA | 18 | 16 | 2 | 0 | 0 |
| Shimmer | 57 | 45 | 8 | 0 | 4 |
| StereoEnhancer | 82 | 68 | 8 | 4 | 2 |
| TransientLooper | 83 | 68 | 8 | 5 | 2 |
| Transmitter | 70 | 8 | 2 | 60 | 0 |
| WaveformColouring | 19 | 16 | 2 | 1 | 0 |

(参考) 末尾 jmp の件数 (`[tail]` 行と同じ):

| export | 末尾 jmp: IAT | 画像内ポインタ | reg | vcall 形 `[reg+disp]` | switch 形 `[base+idx*8]` |
|---|---:|---:|---:|---:|---:|
| GeneralPitchShifter | 4 | 0 | 1 | 0 | 0 |
| LimiterLite | 5 | 1 | 3 | 2 | 0 |
| Limiter | 5 | 1 | 1 | 2 | 0 |
| LowFreqEnhancer | 12 | 2 | 7 | 2 | 0 |
| PSOLA | 5 | 1 | 2 | 0 | 5 |
| Shimmer | 6 | 2 | 1 | 0 | 0 |
| StereoEnhancer | 12 | 2 | 5 | 2 | 0 |
| TransientLooper | 12 | 2 | 7 | 1 | 0 |
| Transmitter | 4 | 0 | 1 | 0 | 0 |
| WaveformColouring | 5 | 1 | 1 | 0 | 0 |

IAT 名の内訳 (件数):
- GeneralPitchShifter (8): GetLastError 2・HeapAlloc 2・HeapFree 1・RaiseException 1・RtlPcToFileHeader 1・SetLastError 1
- LimiterLite・Limiter・PSOLA・WaveformColouring (各 16): GetCurrentProcess 1・GetLastError 2・HeapAlloc 2・HeapFree 1・IsProcessorFeaturePresent 1・RaiseException 2・RtlCaptureContext 1・RtlLookupFunctionEntry 1・RtlPcToFileHeader 1・RtlVirtualUnwind 1・SetLastError 1・SetUnhandledExceptionFilter 1・UnhandledExceptionFilter 1 (SEH・unwind 系を含む)
- Transmitter (8): GetLastError 2・HeapAlloc 2・HeapFree 1・RaiseException 1・RtlPcToFileHeader 1・SetLastError 1
- Shimmer (45): GetLastError 7・SetLastError 5・GetCurrentProcess 3・IsProcessorFeaturePresent 3・他 SEH・unwind・ファイル系を含む 27 件
- LowFreqEnhancer・StereoEnhancer・TransientLooper (各 68): GetLastError 16・WriteFile 6・SetLastError 5・GetCurrentProcess 3・IsProcessorFeaturePresent 3・他 35 件 (ファイル・コンソール・LoadLibrary 系を含む)

画像内関数ポインタ (IAT 外) の先:
- `0x268260` (先 0x1cb5e0): 呼び出し元 `0x1aedf6` (helper `0x1aedc0` 内)。10 export 全ての closure に含まれる。
- `0x268268` (先 0x1cb600): 呼び出し元 `0x1b6f6c` (helper `0x1b6f4c` 内)。10 export 全ての closure に含まれる。加えて LowFreqEnhancer・StereoEnhancer・Shimmer・TransientLooper の closure に、helper 外の 6 箇所 (`0x1b3357`・`0x1b6fd8`・`0x1b700f`・`0x1b729d`・`0x1b748e`・`0x1b7bdb`) がある。

その他:
- helper `0x1aedc0` の間接 call は 3 件 (`0x1aedf6`→画像内 `0x268260`、`0x1aee04`→IAT `0x268088` RtlPcToFileHeader、`0x1aee4a`→IAT `0x268090` RaiseException)。10 export 全てに含まれる。
- IAT `0x268050` (SetUnhandledExceptionFilter) は helper `0x1aedc0` からは呼ばれない。`0x1ad63f` (Limiter 系・SE・TL・WC 等) と `0x1b320b` (LFE・Shimmer・SE・TL) から呼ばれる。
- vcall `call [reg+disp]`: Transmitter 60 件、LimiterLite 5・TransientLooper 5 件ほか。WaveformColouring の 1 件は `0x1a9e2b: call qword ptr [rax+0x18]` (関数 `0x1a9e10`)。
- `call reg`: Shimmer 4 件、LowFreqEnhancer・StereoEnhancer・TransientLooper 各 2 件、LimiterLite・Limiter 各 1 件。

### 5. 起票 (子 issue)
| 子 | 対象 | 規模 (本節の数値) |
|---|---|---|
| [T-SH-36] #2483 | GeneralPitchShifter_CreateInstance の instance lift | 45 関数・1,347 命令・間接 10 (IAT 8・画像内関数ポインタ 2) |
| [T-SH-37] #2484 | WaveformColouring_CreateInstance の instance lift | 70 関数・2,757 命令・SIMD 23.8%・間接 19 (IAT 16・画像内関数ポインタ 2・vcall 1) |
| [T-SH-38] #2528 | GeneralPitchShifter の CreateInstance vtable の native 確定と間接 call の到達実測 | 間接 call 4 件 (helper 0x1aedc0 の 3 件・0x1b6f4c の 1 件)。slot 役割は本 REPORT に未記載 |
| [T-SH-39] #2529 | GeneralPitchShifter の CreateInstance closure の lift と native 差分テスト | CreateInstance 単体 961 命令・vtable 込み 45 関数・1,347 命令 (§4.2 の GPS 行) |

- 子 issue は 4 件で、`docs/WORKFLOW.md` §3 の上限 (1 PR あたり 3 件) を 1 件超える。#2528 と #2529 のどちらを残すかは **PM の判断待ち**。
- #2528・#2529 は親 #2483 (T-SH-36) の子。残り 8 instance は子を順次起票する (#161 に残す)。

### 6. 測定 commit と差分の証跡
- 測定 commit: `a409596f` (main との merge commit。`ildsp_closure.py`・`ildsp_closure_check.py` は、`fdd82f2c` の `ildsp_vtable.py`・`ildsp_vtable_check.py` を名前だけ変えたもの。出力は改名前と cmp 一致)。§4.1 の実測と §4.2 の表は `fa5eb8a8` 以降 closure の計算に変更が無い。§4.4 の末尾 jmp の表と検算は `fdd82f2c` 以降の `[tail]` 行で測定した。
- 本 REPORT の commit 以降の `git diff a409596f HEAD -- tools/shared/scripts` は空 (差分 0)。HEAD での再実行結果は PR 本文に記載する。

### 検証範囲 / 範囲外
- 範囲: 静的な vtable 解析・逆アセンブルによる計数 (capstone と objdump)。
- 範囲外: ① 実行時の vtable 使用 (host 側がどの slot をどの順で呼ぶか) ② 間接 call 先の確定 ③ lift と差分テスト (未実施) ④ REPORT.md §1 の SIMD 比 30.7% の出典 (未解決のまま)。

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 画像内関数ポインタ `0x268260` (→ 0x1cb5e0) と `0x268268` (→ 0x1cb600) の先の中身と、例外送出 path か否か | 10 export 全ての closure に含まれる。trap 化か stub 化かの判断 | [T-SH-36] #2483 の初手 |
| IAT 呼び出し (GetLastError 等 8〜68 件/instance) の扱い | instance ごとの lift 規模 | 各子 issue |
| 各 slot が Process / Reset / dtor のどれか (host の呼び方) | 差分テストの入出力の定義 | [T-SH-53] #3249 (GPS で確定し流用) |
| vcall の先 (Transmitter 60 件・WaveformColouring `0x1a9e2b`) | Transmitter の lift 規模、WaveformColouring の lift | [T-SH-37] #2484 (`0x1a9e2b`)。Transmitter は未起票 → #161 |
| `.pdata` の無い先の範囲の近似 (次の `.pdata` 先頭まで) | 命令数は上限側に偏りうる | #161 |
| 残り 8 instance の lift | #161 後半 | #161 (子を順次起票) |
| GPS CreateInstance 単体の命令数: 本節 961 命令 (closure の和集合)、`REPORT.md` §4-5 は 924 命令 (同じ 36 関数)。計算規則の差の有無は未確認 | §4.2 と §4-5 のどちらを正にするか | #161 (PM 判断) |
| REPORT.md §1 の SIMD 比 30.7% の出典 | 旧 REPORT 値の再現 | #161 |

### 7. CreateInstance の native 実行 (#2528 / T-SH-38・受入 1・4 を満たして `Closes`。受入 2 → #3249、受入 3 → #3250)
- 測定 commit: `8f643a8c` (ハーネス `tools/shared/scripts/ildsp_native.c`・照合 `ildsp_native_check.py`)。`b0aa27b3` からの変更は、stdout の行バッファ化、呼び出し前の `call` 行 (実験ごとの wrapper を出す)、checker の timeout 処理のみ。`git diff 8f643a8c HEAD -- tools/shared/scripts` の出力は空 (差分 0)。round 2 の再測定は、同じコードの HEAD `551da801` からビルドした `ildsp_native` で行った。
- 方式: `block24360_PE.bin` を ImageBase 0x180000000 に VA 通りに敷設 (`ott_native.c` と同じ方式、MAP_FIXED_NOREPLACE)。IAT 73 件のうち 7 件 (GetProcessHeap・HeapAlloc・HeapFree・GetLastError・SetLastError・RtlPcToFileHeader・RaiseException) を ms_abi の C 関数で実装し、残りは名前を記録して 0 を返す thunk (実行時に呼ばれた件数を出力)。HeapAlloc は 0x50000000 から bump で確保 (0 埋め)。`CreateInstance` は MS x64 の関数ポインタで直接呼ぶ。CRT の DllMain・TLS・SEH は走らせない。
- 実行形: **単独** = `ildsp_native <PE> --slot K V` (1 プロセス 1 実験。create の後に slot を 1 回呼ぶ)。**全件** = `ildsp_native <PE>` (同一プロセスで slot 1〜5 を順に呼ぶ。実験ごとに create を呼び直すので、ヒープの確保位置が進む)。
- 照合 (create のみ・`--slot 0 0`): wrapper 0x50000000 → vptr `0x1803dfcf8` (= vtable VA、一致)。`ildsp_native_check.py` は ALL OK (rc 0)。ネガティブコントロール (`--neg-lea`): vptr `0x1803dfd00`、`--neg` は FAIL (rc 1)。
- 測定条件 (round 2・本表の値): ASLR 有効・既定の環境変数・load average 0.2〜1.5 (4 vCPU の runner)。各プロセスは `timeout 15` で囲み、rc 124 = 15 秒で timeout (hang)、rc 139 = SIGSEGV。単独 14 件を各 n=6 (計 84 プロセス)、全件を n=6。

単独実行の表 (1 プロセス 1 実験・n=6):

| slot | rdx | rc (n=6) | rax (完走時) | 変更範囲 (完走時) | 間接 call 4 件の hook |
|---|---|---|---|---|---|
| 1 | 0 | 0 ×5・124 ×1 | 0x50001620 (5/5) | 33 range ×4・34 range ×1 (2 種) | 0 件 |
| 1 | 1 | 0 ×5・124 ×1 | 0x50001620 (5/5) | 33 range ×4・34 range ×1 (2 種) | 0 件 |
| 1 | 2 | 0 ×3・124 ×3 | 0x50001620 (3/3) | 33 range ×3 (1 種) | 0 件 |
| 1 | 0xe | 0 ×1・124 ×5 | 0x50001620 (1/1) | 33 range ×1 (1 種) | 0 件 |
| 2 | 0 | 0 ×6 | 0 | `[0x31+1, 0x6e+2]` 6/6 (2 range) | 0 件 |
| 2 | 1 | 0 ×6 | 0 | なし 6/6 | 0 件 |
| 2 | 2 | 0 ×6 | 2 | `[0x35+1]` 6/6 (1 range) | 0 件 |
| 2 | 0xe | 0 ×6 | 0 | なし 6/6 | 0 件 |
| 3 | 0 | 0 ×6 | 0x2e | なし 6/6 | 0 件 |
| 3 | 1 | 139 ×6 | call 内で SIGSEGV | — | — |
| 3 | 2 | 139 ×6 | call 内で SIGSEGV | — | — |
| 3 | 0xe | 139 ×6 | call 内で SIGSEGV | — | — |
| 4 | 内部オブジェクト (0x50000320) | 0 ×6 | 0x35 | なし 6/6 | 0 件 |
| 5 | 0 | 0 ×6 | 0 | なし 6/6 | 0 件 |

- 全件実行 (同一プロセス・n=6): rc 124 が 3 回 (slot 1 v0 の call 内で hang)、rc 139 が 3 回 (slot 3 v1 の call 内で SIGSEGV)。slot 4・5 には届かない。完走した slot の値: slot 2 v0 `[0x31+1, 0x6e+2]` 3/3・slot 2 v2 `[0x35+1]` 3/3・slot 3 v0 rax 0x2e 3/3。全件の slot 1 v0 は、完走 3 回の rax が wrapper+0x1350・+0x1310・+0x166aa0 (range 数 34・34・29) で、単独と一致しない (注 1)。
- レビュー側の再現 (PR #3210 の review。別環境。本 round では再現していない): 単独 slot 1 v0 hang 0/4、slot 2 v0 `[0x6e+2]` 8/8、slot 2 v2 `changed=[]` 2/2 (単独 1・全件 1)、全件 slot 2 v0 `[0x30+4, 0x6e+2]` 2/2、全件 slot 1 v0 hang 2/6・slot 3 v1 SIGSEGV 4/6。
- 注:
  1. slot 1 の rax: round 1 の「単独・全件とも rax は wrapper+0x1310」は、全件では成り立たない。単独 14 件の完走はすべて wrapper+0x1310 (0x50001620) だが、全件の完走 3 件は wrapper+0x1350・+0x1310・+0x166aa0。slot 1 の内部確保量が実行ごとに違う可能性があるが、未確認。
  2. slot 2 v0 の変更範囲: round 1 の 3 range (`[0x30+1, 0x32+1, 0x6e+2]`)・レビュー時の単独 `[0x31+2, 0x6e+2]` は、round 2 では再現しなかった (単独 6/6・全件 3/3 で `[0x31+1, 0x6e+2]`)。レビュー環境では `[0x6e+2]` (単独 8/8) と `[0x30+4, 0x6e+2]` (全件 2/2) だった。環境差の原因は未確認。
  3. 間接 call 4 件: 単独の完走 56 件 (slot 1 14・slot 2 24・slot 3 v0 6・slot 4 6・slot 5 6) と全件の完走経路で hook 0 件。0 件は「この実験の範囲で到達しなかった」の意味で、到達しない根拠ではない。どの入力が helper 0x1aedc0 / 0x1b6f4c に入るかは未確定。
  4. ASLR 無効 (`setarch x86_64 -R`) と空の環境 (`env -i`) は、round 1 の実装者測定 (ASLR 無効 6/6 hang、`env -i` 6 回中 1 回 hang、変更範囲は `[0x31+1, 0x6e+2]`) のみ。round 2 では再測定しておらず、review も再現していない (未検証)。
- slot 1 の hang: 単独 24 回中 10 回 (rdx ごと 1/6・1/6・3/6・5/6)、全件 6 回中 3 回。round 1 は 16 回中 9 回で、通算は 40 回中 19 回。レビュー側の 0/4 (単独) とは食い違う。hang の位置は未特定。仮説 (未検証): 未初期化値・スタック位置・環境変数長に依存する分岐。負荷の影響は未検証。
- 未実施: slot 0 (dtor・解放を伴う)。

未解決 (受入 1・4 の範囲外):

| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot 1–3・5 の役割 (どの method か・引数の意味。呼び出し規約) | 受入 2 | [T-SH-53] #3249 |
| 間接 call 4 件 (0x1aedf6・0x1aee04・0x1aee4a・0x1b6f6c) の到達条件と扱い | 受入 3 | [T-SH-54] #3250 |
| slot 0 (dtor) は未実行 | 受入 2 の一部 | [T-SH-53] #3249 |
| slot 1 の hang (単独 10/24・全件 3/6。原因未確認) | slot 1 の結果を単独で採れない | 追跡 issue なし (PM 判断: 子の起票要否) |
| slot 3 (rdx=1・2・0xe) の SIGSEGV (単独 18/18・全件 3/3。原因未確認) | slot 3 の入力の扱い。全件は slot 4・5 に届かない | 追跡 issue なし (PM 判断: 子の起票要否) |
| slot 2 v0 の変更範囲の環境差 (実装者環境 `[0x31+1, 0x6e+2]`、レビュー環境 `[0x6e+2]`・`[0x30+4, 0x6e+2]`。原因未確認) | 差分テストの入出力の定義 | 追跡 issue なし (PM 判断: 子の起票要否) |
| slot 1 の全件での rax・変更範囲のばらつき (注 1) | slot 1 の出力の定義 | 追跡 issue なし (PM 判断: 子の起票要否) |
