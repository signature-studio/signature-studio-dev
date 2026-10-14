# ildsp (`block24360_PE.bin`) 規模調査

自動生成ではない。再現コマンドは下記。親: #161 (T-SH-15) / 本件: #791 (T-SH-19)。

既知類型との関係: 該当なし (逆アセンブルによる規模計測のみ。lift 未実施。DEFECTS.md の類型には当たらない)。

## 再現

```
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/scripts/ildsp_survey.py
```

- 入力: `$FL_WIN64_DIR/extracted/block24360_PE.bin` (win64 PE, 4,197,376 B)
- 依存: `capstone`・`pefile` (`uv venv` + `uv pip install capstone pefile`)
- 出力: 表を標準出力へ、JSON を `tools/shared/work/raw/ildsp_survey.json` (gitignore)
- 所要: 実測 `real 0m3.620s` (Python 3.14 / capstone 5.0.7 / pefile 2024.8.26、入力 sha256 f4b23b0f…、HEAD 検証時)

## 1. 全体 (実測)

| 項目 | 実測 |
|---|---:|
| `.text` 命令数 (線形走査・仮想サイズ) | 362,280 |
| `.pdata` 関数数 (生データ読み) | 2,622 |
| 直接 call / 間接 call | 5,898 / 848 |
| 間接 call 比 | 12.6% |
| `IPPCODE` 命令数 | 129,192 |
| `IPPCODE` SIMD 比 | 70.0% |
| `.text` SIMD 比 | 48.68% (176,373 / 362,280) |

上表は script 出力 (JSON: `text_instructions` 362280 / `simd_ratio` 0.4868 / `ippcode_instructions` 129192) と一致する。同一入力 (sha256 f4b23b0f…) で 2 回実行し JSON が完全一致 (`cmp` で確認) したため決定的。旧 REPORT の 362,277 / 129,188 は script で再現しなかった (下記未解決を参照)。

### 未解決: `.text` SIMD 比の定義

旧 libreverb REPORT §6 にあった 111,346 (30.7%) を再現する定義は見つからなかった。試した定義と件数:

- `xmm`/`ymm`/`zmm` を含む全命令: 176,373
- 同上から GPR↔XMM の move を除外: 168,168 / 140,996 (スカラー ss/sd を除外)
- `simd_stats.py` の分類 (avx512 / avx_256 / avx_128 / sse_packed / sse_scalar): 176,373 (`sse_other` 除く 175,346)
- `.pdata` 関数の範囲に限定: 260,600 / 464,542 (56.1%)
- packed 演算のみ (`*ps`/`*pd`): 125,570

いずれも 111,346 とは一致しない。REPORT の値の出典 (別の母集団・別の定義) を特定できていない。定義を推測で作ることはしない。**起票先: #161 継続 (REPORT §6 の SIMD 比の出典を確認)**。

## 2. export 単位 closure 規模表

closure = export entry の関数 (`.pdata` 境界) から、直接 call と直接 jmp (別関数への tail) を辿った到達集合。間接 call は辿らず件数のみ数える。

| export | entry | 関数数 | 命令数 | SIMD 比 | 直接 call | 間接 call | 間接比 |
|---|---|---:|---:|---:|---:|---:|---:|
| GeneralPitchShifter_CreateInstance | 0x1aa290 | 8 | 238 | 8.8% | 14 | 4 | 22.2% |
| LimiterLite_CreateInstance | 0x1aa540 | 10 | 417 | 5.0% | 18 | 5 | 21.7% |
| Limiter_CreateInstance | 0x1aafd0 | 11 | 858 | 8.5% | 67 | 5 | 6.9% |
| LowFreqEnhancer_CreateInstance | 0x1ab3d0 | 140 | 10,307 | 4.2% | 540 | 61 | 10.2% |
| PSOLA_CreateInstance | 0x1ab540 | 8 | 238 | 8.8% | 14 | 4 | 22.2% |
| Shimmer_CreateInstance | 0x1ab810 | 44 | 1,765 | 2.3% | 155 | 37 | 19.3% |
| StereoEnhancer_CreateInstance | 0x1abca0 | 139 | 9,925 | 4.0% | 501 | 61 | 10.8% |
| TransientLooper_CreateInstance | 0x1abe00 | 9 | 289 | 0.0% | 24 | 6 | 20.0% |
| Transmitter_CreateInstance | 0x1ac260 | 12 | 1,020 | 8.9% | 101 | 64 | 38.8% |
| WaveformColouring_CreateInstance | 0x1ac470 | 10 | 762 | 27.4% | 17 | 4 | 19.1% |

- 最小: GeneralPitchShifter と PSOLA が同率 238 命令 (8 関数)。両者のバイト列は一致しない (sha1 713ff04f… / 0391d052…)。
- 規模の大きい 2 つ (LowFreqEnhancer 10,307 / StereoEnhancer 9,925 命令) は 140 / 139 関数。残り 8 件は 8〜44 関数。
- closure は間接 call を辿らないため、実到達はこの表より大きい可能性がある。
- **下限**: 本表の closure は `.pdata` の関数だけを辿り、`.pdata` の無い直接 call/jmp 先 (leaf 関数等) を捨てる。`ildsp_survey.py` も同じ定義のため、数値は下限。`.pdata` の無い先を含めた値は §4 (`ildsp_vtable.py`) を参照。
- 注意: `.pdata` 先頭でない entry は `owner()` で含む関数の先頭に正規化してから辿る。export の 10 件はすべて `.pdata` 先頭に一致した。

## 3. 次の子 issue の起票案 (PM が起票)

(本節の数値は §2 の下限値。規模の正本は §4 で、子 issue の規模は §4.5 に従う)

最小 instance は **PSOLA_CreateInstance** (または GeneralPitchShifter_CreateInstance)。どちらも 238 命令・8 関数で、lift と差分テストの初回対象に向く。ただし closure の間接 call 比が 22.2% あるため、間接 call の解決方法 (テーブル or 実行時 dispatch) を先に決める必要がある。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.text` SIMD 比 30.7% の定義・出典 | 旧 libreverb REPORT §6 の数値が再現できない | #161 継続 |
| 旧 REPORT 値 (362,277 / 129,188 / 10,305) の出典 | 現 script では再現しない (決定的な出力は 362,280 / 129,192 / 10,307)。旧値は別の版・別の script 状態の産物と推定するが未確認 | #161 継続 (旧値の出典確認) |
| closure の間接 call 先の解決 | 表の命令数は下限 | 起票案 (PSOLA lift) で扱う |
| ildsp の lift 本体 | #161 後半未達 | #161 継続 |

## 4. vtable 経由の実体 closure (#161 本 run・測定 commit は §4.6)

### 結論
- §2 の closure (`.pdata` 基準・CreateInstance の直接 call/jmp 先) は、**深さ 1 では 10/10 で vtable の slot 先を含まない**。CreateInstance は wrapper の vtable を置くだけで、slot 先を直接呼ばない。
- 推移閉包 (`.pdata` の無い先を含む) では、**3 件で slot 先と重なる**: LowFreqEnhancer (slot 先 0x17bdd0)・Limiter (0x169150)・Transmitter (0x1a6a30・0x1a7990)。
- vtable 経由で数えると 10 export 全てで実体に届く。最小は **GeneralPitchShifter** (45 関数・1,347 命令)、次点 WaveformColouring (70 関数・2,757 命令・SIMD 23.8%)。instance の lift 単位は「CreateInstance + vtable slot 先の到達集合」とする。
- 誤差の向き: 間接 call の先は含まない (下限側)。`.pdata` の無い先の範囲は近似 (§4.1 手順 4) で、上限側に偏りうる。

### 1. 再現と手順
```
FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_vtable.py
FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_vtable_check.py tools/shared/work/raw/ildsp_vtable.json
```
- `ildsp_vtable.py`:
  1. CreateInstance (と直接 tail jmp 先) から `lea reg,[rip+X]` の直後 4 命令以内の `mov qword ptr [r],reg` を探し、X を wrapper の vtable とする。
  2. vtable の先頭から .text 内を指すポインタを slot とし、.text 外を指す所で打ち切る。
  3. slot 先が thunk (`mov rcx,[rcx+8]` で始まり直接 jmp で終わる) なら jmp 先を実体とする。
  4. 実体から直接 call / 直接 jmp を辿る。辿り先が `.pdata` に無ければ、その先頭を関数とし、次の `.pdata` 先頭までを範囲とする (近似)。同じ関数範囲内の jmp (内部分岐) は関数として数えない。
  5. 命令数・SIMD 比・間接 call 数は、到達関数の命令開始アドレスの**和集合**で数える (範囲の重なりを二重計上しない)。
  6. CreateInstance 単体 (同じ規則) と slot 先の到達集合の和集合を出す。
- `ildsp_vtable_check.py`: JSON の関数集合 (`function_rvas`) の範囲を GNU objdump で逆アセンブルし、命令開始アドレス (RVA) の集合を capstone の集合と比べる。命令ごとに SIMD・間接 call の判定も比べ、JSON の数値と再計算値の一致も見る。既知の差分 (§4.3) 以外は非 0 で終了する。
- 実測 (測定 commit で 3 回): `ildsp_vtable.py` real 0.401 / 0.404 / 0.405 s (測定後の load 0.03、4 core)。stdout と JSON は 3 回とも `cmp` で完全一致。`ildsp_vtable_check.py` real 1.85 s、`ALL OK` (rc 0)。入力 `block24360_PE.bin` sha256 f4b23b0f…。
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

- 命令数・関数数は CreateInstance の closure と slot 先 closure の和集合 (重複は 1 回)。「CreateInstance 単体」は同じ規則で CreateInstance だけから辿った値で、§2 の値 (`.pdata` のみ) とは規則が違う。
- 前版 (測定 commit b8f8a0f7・`.pdata` の無い先を捨てていた版) の値 (例: GPS 15 関数・473 命令) は下限で、本表で置き換える。
- 指摘の試算との差: 間接 call 数は 4 export とも一致。関数数は GeneralPitchShifter・WaveformColouring・Transmitter が一致し、LowFreqEnhancer だけ試算 249 に対し 219。試算の命令数は、重なる範囲を二重計上していた分だけ大きい (GPS 1,364 → 1,347、WC 2,803 → 2,757、Transmitter 2,362 → 2,315)。LowFreqEnhancer は `.pdata` の無い範囲内の内部 jmp 先 30 件を、試算が関数として数えていたため (本版は数えない)。

### 3. 検算 (objdump との照合)
- 検算は関数集合 (JSON の `function_rvas`) と範囲定義を `ildsp_vtable.py` と**共有する**。検算するのは命令の復号と集計 (数・SIMD・間接 call) だけで、closure の辿り方 (`.pdata` の無い先の扱い) は検算しない。closure の取りこぼしは本スクリプトでは検出できない。§2 (`ildsp_survey.py`) も同じ `.pdata` 基準で、同じ下限の注記が付く。
- 結果: 10 件中 9 件は命令開始アドレスの集合が完全一致し、SIMD・間接 call の判定も一致した。TransientLooper は 1 件の既知差分 (下記) のみ。判定は `ALL OK` (rc 0)。
- 既知差分 (TransientLooper・RVA `0x191c29` の 1 件のみ): 関数 `0x190fa0` (範囲 0x190fa0–0x191c80) の `0x191c20` 付近に switch 用の 4 byte RVA 表 (`cd 10 19 00 49 11 19 00 c5 11 19 00`) が埋まる。
  - `0x191c1f` の `add ch,cl` (`00 cd`) は両者とも同じ位置から復号され、`cd` (0x191c20) は命令として現れない。
  - `0x191c28` の `c5 11 19` は不正な VEX 接頭辞。capstone はここで復号できず 1 byte (0x191c28) を飛ばし、`0x191c29` から `adc dword ptr [rcx], ebx` を 1 件として数える。
  - objdump は `0x191c28` を `(bad)` として 3 byte を 1 行で消費し、`0x191c29` を命令として出さない。
  - `ildsp_vtable_check.py` の `KNOWN_DATA_IN_CODE` はこの RVA との完全一致のみを許す。件数の比較だけでは相殺する差を見逃すため使わない。
- 旧版の説明 (「`int 0x10` 等として 1 件数え、objdump は数えない」) は誤りだった。

### 4. 間接 call の内訳 (lift の障害)
- 定義: **間接 call** = 即値でない `call` (`call [mem]`・`call reg`)。`call [rip+X]` で X が IAT (import) なら「IAT」、IAT 外の画像内ポインタなら「画像内関数ポインタ」。`call [reg+disp]` は vcall。末尾の `jmp [mem]`・`jmp reg` (tail call) は数えず、参考列に件数を示す。

| export | 間接 call 計 | IAT | 画像内関数ポインタ | vcall | call reg | (参考) 末尾 jmp: IAT / reg / vcall |
|---|---:|---:|---:|---:|---:|---|
| GeneralPitchShifter | 10 | 8 | 2 | 0 | 0 | 4 / 1 / 0 |
| LimiterLite | 24 | 16 | 2 | 5 | 1 | 6 / 3 / 2 |
| Limiter | 20 | 16 | 2 | 1 | 1 | 6 / 1 / 2 |
| LowFreqEnhancer | 82 | 68 | 8 | 4 | 2 | 14 / 7 / 2 |
| PSOLA | 18 | 16 | 2 | 0 | 0 | 6 / 2 / 5 |
| Shimmer | 57 | 45 | 8 | 0 | 4 | 8 / 1 / 0 |
| StereoEnhancer | 82 | 68 | 8 | 4 | 2 | 14 / 5 / 2 |
| TransientLooper | 83 | 68 | 8 | 5 | 2 | 14 / 7 / 1 |
| Transmitter | 70 | 8 | 2 | 60 | 0 | 4 / 1 / 0 |
| WaveformColouring | 19 | 16 | 2 | 1 | 0 | 6 / 1 / 0 |

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

残り 8 instance は子を順次起票する (#161 に残す)。

### 6. 測定 commit と差分の証跡
- 測定 commit: `fa5eb8a8` (`tools/shared/scripts` の最後のコード変更)。上記 §1・§2・§3 の実測はこの commit の内容で行った。
- 本 REPORT の commit 以降の `git diff fa5eb8a8 HEAD -- tools/shared/scripts` は空 (差分 0)。よって再測定は不要。

### 検証範囲 / 範囲外
- 範囲: 静的な vtable 解析・逆アセンブルによる計数 (capstone と objdump)。
- 範囲外: ① 実行時の vtable 使用 (host 側がどの slot をどの順で呼ぶか) ② 間接 call 先の確定 ③ lift と差分テスト (未実施) ④ §1 の SIMD 比 30.7% の出典 (未解決のまま)。

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 画像内関数ポインタ `0x268260` (→ 0x1cb5e0) と `0x268268` (→ 0x1cb600) の先の中身と、例外送出 path か否か | 10 export 全ての closure に含まれる。trap 化か stub 化かの判断 | [T-SH-36] #2483 の初手 |
| IAT 呼び出し (GetLastError 等 8〜68 件/instance) の扱い | instance ごとの lift 規模 | 各子 issue |
| 各 slot が Process / Reset / dtor のどれか (host の呼び方) | 差分テストの入出力の定義 | [T-SH-36] #2483 (GPS で確定し流用) |
| vcall の先 (Transmitter 60 件・WaveformColouring `0x1a9e2b`) | Transmitter の lift 規模、WaveformColouring の lift | [T-SH-37] #2484 (`0x1a9e2b`)。Transmitter は未起票 → #161 |
| `.pdata` の無い先の範囲の近似 (次の `.pdata` 先頭まで) | 命令数は上限側に偏りうる | #161 |
| 残り 8 instance の lift | #161 後半 | #161 (子を順次起票) |
| §1 の SIMD 比 30.7% の出典 | 旧 REPORT 値の再現 | #161 |
