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
- 注意: `.pdata` 先頭でない entry は `owner()` で含む関数の先頭に正規化してから辿る。export の 10 件はすべて `.pdata` 先頭に一致した。

## 3. 次の子 issue の起票案 (PM が起票)

最小 instance は **PSOLA_CreateInstance** (または GeneralPitchShifter_CreateInstance)。どちらも 238 命令・8 関数で、lift と差分テストの初回対象に向く。ただし closure の間接 call 比が 22.2% あるため、間接 call の解決方法 (テーブル or 実行時 dispatch) を先に決める必要がある。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.text` SIMD 比 30.7% の定義・出典 | 旧 libreverb REPORT §6 の数値が再現できない | #161 継続 |
| 旧 REPORT 値 (362,277 / 129,188 / 10,305) の出典 | 現 script では再現しない (決定的な出力は 362,280 / 129,192 / 10,307)。旧値は別の版・別の script 状態の産物と推定するが未確認 | #161 継続 (旧値の出典確認) |
| closure の間接 call 先の解決 | 表の命令数は下限 | 起票案 (PSOLA lift) で扱う |
| ildsp の lift 本体 | #161 後半未達 | #161 継続 |

## 4. vtable 経由の実体 closure (#161 本 run・検証起点 b8f8a0f7)

### 結論
§2 の closure (CreateInstance とその直接 call/jmp 先) は**実体を含まない**。PSOLA の CreateInstance (0x1ab540–0x1ab58f) は、wrapper の vtable を格納し alloc / memset を呼ぶだけで、vtable の slot 先を呼ばない (逆アセ確認)。DSP 本体は vtable の slot 先にある。vtable 経由で数えると 10 export 全てで実体に届く。最小は **GeneralPitchShifter** (15 関数・473 命令)。instance の lift 単位は「CreateInstance + vtable slot 先の到達集合」とする。

### 1. 再現 (1 コマンドずつ・FL_WIN64_DIR は fl-win64 展開先)
```
FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_vtable.py
FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_vtable_check.py tools/shared/work/raw/ildsp_vtable.json
```
- 手順 (`ildsp_vtable.py`): (1) CreateInstance (と直接 tail jmp 先) から `lea reg,[rip+X]` の直後 4 命令以内の `mov qword ptr [r],reg` を探し、X を wrapper の vtable とする。(2) vtable の先頭から、.text 内を指すポインタを slot とし、.text 外のポインタで打ち切る。(3) slot 先が `mov rcx,[rcx+8]` で始まり直接 `jmp` で終わる thunk なら、jmp 先を実体とする。(4) CreateInstance と全 slot 先の到達集合 (`ildsp_survey.py` と同じ closure 定義) の和集合を数える。
- 検算 (`ildsp_vtable_check.py`): GNU objdump (別の逆アセンブラ) で同じ関数範囲 (.pdata 終端) を `--start-address/--stop-address` 付きで再計数し、命令数・間接 call 数・SIMD 比を照合する。
- 実測: `ildsp_vtable.py` real 0.35 / 0.34 / 0.34 s (3 回、load 0.08–0.11、4 core)。`ildsp_vtable_check.py` real 1.25 s。3 回の stdout は `cmp` で完全一致 (決定的)。入力 sha256 f4b23b0f… (HEAD 検証時)。

### 2. 結果 (10 export・実測)
| export | vtable (RVA) | slot 数 | thunk | 関数数 | 命令数 | SIMD 比 | 間接 call | 間接比 | (参考) §2 の CreateInstance 単体 命令数 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GeneralPitchShifter | 0x3dfcf8 | 6 | 3 | 15 | 473 | 11.4% | 4 | 15.4% | 238 |
| LimiterLite | 0x3dfd80 | 15 | 1 | 66 | 3,430 | 28.7% | 23 | 12.2% | 417 |
| Limiter | 0x3dff40 | 22 | 5 | 71 | 2,938 | 10.1% | 19 | 8.9% | 858 |
| LowFreqEnhancer | 0x3dfff8 | 6 | 3 | 146 | 10,974 | 4.1% | 63 | 9.6% | 10,307 |
| PSOLA | 0x3e0030 | 6 | 3 | 52 | 3,980 | 24.1% | 17 | 8.1% | 238 |
| Shimmer | 0x3e0068 | 11 | 6 | 76 | 5,134 | 27.7% | 39 | 10.2% | 1,765 |
| StereoEnhancer | 0x3e00c8 | 6 | 3 | 146 | 10,457 | 4.0% | 63 | 10.5% | 9,925 |
| TransientLooper | 0x3e0100 | 9 | 4 | 153 | 11,456 | 5.0% | 64 | 9.5% | 289 |
| Transmitter | 0x3e0150 | 11 | 5 | 22 | 1,520 | 7.8% | 64 | 27.0% | 1,020 |
| WaveformColouring | 0x3e01b0 | 6 | 0 | 18 | 1,356 | 46.1% | 5 | 11.4% | 762 |

- 命令数・関数数は、CreateInstance の closure と slot 先 closure の和集合 (重複は 1 回)。
- 検出: 10 件とも vtable を検出 (初版は 7 件。格納命令の探索幅が狭く、3 件を取りこぼした。探索幅を広げ、CreateInstance が直接 jmp する先も探すよう直して 10/10)。
- 最小: GeneralPitchShifter (473 命令・15 関数)。次点 WaveformColouring (1,356 命令・18 関数・SIMD 46.1%)。
- 数値の定義の注意: 「命令数」は線形走査 (capstone) の件数で、データ埋め込み分を含む (下記 3)。「間接 call」は即値でない call 件数 (vtable 呼び出し・IAT・関数ポインタ表を含む)。

### 3. 検算 (objdump との照合)
- `ildsp_vtable_check.py`: 10 件中 9 件が命令数・間接 call 数・SIMD 比とも一致 (ALL OK は既知差分 1 件を含めて成立)。
- 既知差分 1 件: TransientLooper で capstone 11,456 / objdump 11,455。差は関数 0x190fa0 (範囲 0x190fa0–0x191c80) 内の 0x191c20 付近。ここは 4 byte の RVA 表 (`cd 10 19 00 49 11 19 00 c5 11 19 00 …`、昇順) で、switch 系のジャンプテーブルがコード中に埋め込まれている。capstone はこれを `int 0x10` 等として 1 件数え、objdump は数えない。`KNOWN_DATA_IN_CODE` に列挙し、他の差分は非 0 終了にしている。
- 集計 (検算): `ildsp_vtable_check.py` は `(bad)`・`.byte` 行を数えない (capstone が復号できないバイトを数えないことに合わせた)。

### 4. 間接 call の内訳 (lift の障害)
- 全 10 件の間接 call は 2 系統。
  - (a) 共通の例外送出 helper: `0x1aedc0` (定数 `0xe06d7363` = MSVC の C++ 例外コード。`RaiseException`・`RtlPcToFileHeader` を IAT (0x268090・0x268088) 経由で `call qword ptr [rip+X]`。先頭でも image 内の関数ポインタ 0x268260 → 0x1cb5e0 を呼ぶ)、`0x1b6f4c` (関数ポインタ 0x268268 → 0x1cb600)。GeneralPitchShifter の間接 call 4 件は全て (a)。WaveformColouring の間接 call 5 件のうち 4 件も (a)。
  - (b) instance 固有の virtual dispatch: WaveformColouring の `0x1a9e2b: call qword ptr [rax+0x18]` (fn 0x1a9e10)、sub-object の vtable 経由。1 件。
- (a) の到達経路 (正常系で通るか) は**未確認**。例外送出の path なら trap 化の根拠が要る。`0x268260` 先の関数 0x1cb5e0 の中身も未確認。子 issue の初手で確認する。
- IAT (0x268050–0x268240 の 73 件、KERNEL32 の未束縛エントリ。ファイル上は IMAGE_IMPORT_BY_NAME の RVA) のうち、0x268050 (SetUnhandledExceptionFilter)・0x268088 (RtlPcToFileHeader)・0x268090 (RaiseException) を (a) が使う。0x268260・0x268268 は IAT の外で、image 内の関数を指す。

### 5. 起票 (子 issue・本 PR で 2 件)
| 子 | 対象 | 規模 (本節の数値) |
|---|---|---|
| [T-SH-36] | GeneralPitchShifter_CreateInstance の instance lift | 15 関数・473 命令・間接 4 (a) |
| [T-SH-37] | WaveformColouring_CreateInstance の instance lift | 18 関数・1,356 命令・間接 5 ((a) 4 + (b) 1) |
残り 8 instance は子を順次起票する (#161 に残す)。

### 検証範囲 / 範囲外
- 範囲: 静的な vtable 解析・逆アセンブルによる計数 (capstone と objdump)。
- 範囲外: ① 実行時の vtable 使用 (host 側がどの slot をどの順で呼ぶか) ② 間接 call 先の確定 ③ lift と差分テスト (未実施) ④ §1 の SIMD 比 30.7% の出典 (未解決のまま)。

### 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) helper `0x1aedc0`・`0x1b6f4c` の到達経路と、関数ポインタ 0x268260 → 0x1cb5e0 の中身 | 間接 call 4 件 (全 instance 共通) の扱い (trap 化か stub 化か) | [T-SH-36] の初手 |
| (b) `0x1a9e2b` の virtual dispatch 先 (sub-object の vtable) | WaveformColouring の lift | [T-SH-37] |
| 各 slot が Process / Reset / dtor のどれか (host の呼び方) | 差分テストの入出力の定義 | [T-SH-36] (GPS で確定し、他 instance の初手に流用) |
| 残り 8 instance の lift | #161 後半 | #161 (子を順次起票) |
| §1 の SIMD 比 30.7% の出典 | 旧 REPORT 値の再現 | #161 |
