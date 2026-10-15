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

### 4.5 間接 call 4 件の到達 (#3250 / T-SH-54・部分達成)
- 結論: 間接 call 4 件 (`0x1aedf6`・`0x1aee04`・`0x1aee4a`・`0x1b6f6c`) は、この実験では到達しなかった (hook 0 件)。到達しない根拠ではない。到達条件 (`0x1b6ea0` の戻り値) と trap 化か stub 化かの判断は保留し、子 #4230 に移す。測定の正本は `REPORT_APPENDIX_3250.md`。

間接 call 4 件の到達 (T-SH-103 / #4230): 既定入力では発火せず、3 件は alloc 失敗注入でだけ発火し、`0x1aedf6` は注入でも未発火 (詳細は `REPORT_APPENDIX_4230.md`・未解決は [T-SH-111] #4289)。

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

### 7. CreateInstance の native 実行 (#2528 / T-SH-38・#3249 slot 役割・#4116 slot 3 引数・#4117 slot 0)
- 結論・測定値・表: `REPORT_APPENDIX_3249.md` (§7 の全文を分割移動)。受入 1・4 は #2528 で満たして `Closes`。受入 2 (slot 役割) は #3249、受入 3 は #3250。非 null メンバでの slot 0 (#4154) の実測は `REPORT_APPENDIX_3249.md` §7.3.1。

### 7.1 slot 3 (0x162f90) が上書きする `+0xc4`・`+0x114` の依存 (T-SH-131 / #5070・部分達成)
- 測定 commit: `8e920869e` (コードを変えた最後の commit。以後の差分は本節の文と REPORT_APPENDIX_3216.md・seh_reach.py・unlifted_reach.py 等の測定外のみ。測定経路 (`tools/shared/scripts/`・`ildsp_native.c`・`ildsp_native_check.py`) は差分 0)。逆アセンブルと書込み元の列挙は `tools/shared/scripts/ildsp_field_writers.py` (`dis` / `writers` / `const`)。素材 fl-win64 (`26.1.7.5653`)・`block24360_PE.bin`・`ildsp_native_check.py` ALL OK。
- 静的に確定したこと:
  1. `0x16340e` は `[this+i*4+0xc4] ← [this+0x44]`、`0x16341c` は `[this+i*4+0x114] ← [this+0x44]` (`i = [this+0x68]`)。slot 3 の中で `[+0x44]` は読むだけで書かない。この 2 命令は `0x162f90` の全経路で通るわけではなく、`0x163252`・`0x1632d2` の `jge` が `0x163423` へ飛ぶ経路では飛ばされる。
  2. `+0xc4[i]`・`+0x114[i]` の値は、呼び出し前に外から与えた値ではなく `[this+0x44]` の値で決まる (書かれる経路では上書きされる)。
  3. `[this+0x44]` の書込み元は `.text` 全体で 4 箇所。`0x1620cc` は create ではなく **slot 1 (`0x161fc0`) の内部** (issue 本文の「create 側」は誤り): `[this+0x44] = cvttss2si([this+8] × f)`、`f` は PE の定数 `0x3e09d0` (float32 −421.7265)。`[this+8]` は slot 1 の引数 xmm1 を `0x161fcf` で書いたもの。よって `+0x44` は外から渡す xmm1 (slot 1 の float 引数) に依存する。他の 3 箇所 (`0x1627e7`・`0x1629e2`・`0x162cfb`) は slot 2 の case 内部で、入力は未確定 (slot 2 の xmm2 等に依存すると見られるが未確認)。
  4. 単独の slot 3 (`--slot 3 0 --s3-bufs`) では `[+0x44]` は create 直後の 0 のまま、`+0xc4`・`+0x114` が書かれる (rc 0)。
- 実機の確認 (`ildsp_native`・`timeout 15`): 前提なしの `--slot 3 V --s3-bufs` は rdx=1・2・0xe で `0x1634bb` が SIGSEGV (rc 98・rdx=0x80000000)。SIGSEGV 直前の `xmm0`・`xmm1` は −nan。`0x163487` の `divss xmm1, xmm0` の除数 `[+0xc4][i]` と被除数 `[+0x114][i]` は、`0x16340e`・`0x16341c` が `[+0x44]` (= 0) から書いた 0 で、0/0 → NaN → `cvttss2si` が `0x80000000` を返す。
- 受入 (#5071・T-SH-132): `[+0x44]` を slot 1 の xmm1=1.0 の後の値 `trunc(1.0 × −421.7265) = −421` にすると、rdx=1・2・0xe で SIGSEGV が消え rc 0 になる。前提の設定は (a) `--pre-slot 1` を slot 3 の直前で走らせる (b) `+0x44 = −421` を直接置く、の 2 通りで同じ結果。(a) は前 run (#5070 の PR) で「pre-slot 1 でも SIGSEGV が残る」と書いたが、`--pre-slot` は `k == 0` のときしか走っておらず、slot 3 の前段初期化は効いていなかった測定不備だった。修正済み (`ildsp_native.c`)。
- 測定 commit: `c07919c78` (`ildsp_native.c` の変更を含む最後の commit)。`ildsp_native_check.py` ALL OK (rc 0・0.21 秒)。`--slot 3 V --s3-bufs` (`timeout 15`・単独プロセス) を V=0・1・2・3 で各 n=6 (V=0 は n=1)。V=1・2・3 は 18 回全て rc 0・`segv_rip` 0 件・`alarm_rip` 0 件・`s3_out last=0.250000`。load 0.11 (測定前の `uptime`)。
- 未確定 (受入 2 の残り): 上の前提は harness が直接置いた値で、実 object の create→slot 1→slot 3 の経路で同じ値になるかは未確認。`[+0x204]`・`[+0x208]`・`[+0x258]`・`[+0x260]` 等の別入力が NaN に寄与し得るかも、この測定では分離していない。
- slot 2 の `[+0x44]` 書込み 3 箇所の入力 (逆アセンブル・ジャンプテーブル `0x162f54` の case 対応。`0x161fc0` 閉包内):
  - 定数: `0x3e02a0` = float32 0.001 (PE の `.rdata` を RVA で直接読んだ値。`0x1627d6`・`0x1629d1`・`0x162cea` の `mulss` が次命令基準でこの RVA を指す)。`0x3e09d0` = −421.7265 (slot 1 の `0x1620cc`)。
  - `0x1627e7` は case 1 (rdx=1, `0x1627d6`) から入る。`xmm6 = xmm2` (`0x16278b`) を `× 0.001 × [+0x8]` して trunc する (`0x1627d6`〜`0x1627e3`)。`[+0x44] = trunc(xmm2 × 0.001 × [+0x8])`。入力は slot 2 の引数 xmm2 と、slot 1 の `0x161fcf` が書いた `[+0x8]`。
  - `0x1629e2` は case 11 (rdx=11, `0x1628c8`) から入る。`xmm7 = xmm2 × 0.0416… + 0.5` (`0x1628c8`〜`0x1628e4`) を `[+0x48]` に書く。`[+0x4c]`・`[+0x50]` は `0x162939`〜`0x162984` で書かれる。`xmm7 < 0.5` (`0x162937`〜) では xmm7 から、`xmm7 ≥ 0.5` (`jae 0x16295d`) では xmm6 (= xmm2) から作る。`[+0x58] = (xmm5 × [+0x50] + xmm4 × [+0x4c]) × 133.73 + 2.27` (`xmm5 = [+0x54]`・`xmm4 = 1 − xmm5`)。最後に `× 0.001 × [+0x8]` を trunc して `[+0x44]` へ (`0x1629d1`〜`0x1629de`)。`[+0x54]` は create の `0x3f000000` か case 12 の `0x162c08` が書いた xmm2。
  - `0x162cfb` は case 12 (rdx=12, `0x162bf0`) から入る。`xmm7 = [+0x48]` (`0x162bf0`)。`[+0x4c]`・`[+0x50]` は xmm7 から `0x162c00`〜`0x162cab` で作る。`xmm6 = xmm2` (`0x16278b`) は `0x162c08` で `[+0x54]` に書かれ、`0x162cc1` で入力として読まれる (`call 0x1c83b0` は `movdqa xmm6` で復元して返るので xmm6 は保たれる)。`xmm1 = (xmm6 × [+0x50] + (1 − xmm6) × [+0x4c]) × 133.73 + 2.27` を `[+0x58]` に書き (`0x162cc1`〜`0x162ce5`)、`× 0.001 × [+0x8]` を trunc して `[+0x44]` へ (`0x162cea`〜`0x162cfb`)。入力は xmm2 (`xmm6`)、`[+0x48]` (`xmm7`・create の `0x3f000000` か case 11 の `0x1628ec` が書いた値)、`[+0x50]`・`[+0x4c]` (xmm7 から作る) と `[+0x8]`。
  - まとめ: `[+0x44]` の値は、外から渡す slot 1 の xmm1 (→ `[+0x8]`) と slot 2 の xmm2、および create 直後の定数と前の slot 2 呼出しの状態で決まる。`[+0xc4][i]`・`[+0x114][i]` はその値で上書きされる。
- 未確定 (#5070 の範囲外・受入 2 の残り): `0x1634bb` の NaN 由来 `0x80000000` の出所 (`0x163487`〜の `[+0x204]`・`[+0x208]`・`[+0x258]`・`[+0x260]` 等)。起票先: #5071 [T-SH-132] (親 #4178)。

### 8. 0x161fc0 閉包の間接 call / jmp (T-SH-70 #3346)
- 結論: 閉包の間接 call / jmp の宛先は、静的に確定する IAT と、実行時の `rax` で決まる CFG/XFG dispatch に分かれる。後者は trap 化する (実装は [T-SH-65] #3318・[T-SH-61] #3299)。正本は `REPORT_APPENDIX_3346.md`。

