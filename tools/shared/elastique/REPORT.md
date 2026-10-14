# tools/shared/elastique REPORT — élastique 2.2.15 (win `elastique_x64.dll`) の静的 IPP 入口の実測と lift 前提 (T-SH-10 / #152)

> 正本: `tools/shared/elastique/REPORT.md`。方針は `docs/DECISIONS.md` D20 (所有者限定 tier・side module)、分類の事実は `tools/shared/REPORT.md` §0・§5。

日付: 2026-10-14 / 担当: #152 実装 run / 測定 commit: `7cf85980` (スクリプトを変えた最後の commit。以後の差分は本ファイルのみ)
再現: `python3 tools/shared/elastique/scripts/elastique_facts.py` (入力 `tools/shared/work/win/elastique_x64.dll`。素材は `docs/REFERENCES.md` `[WIN64]` の `extracted/block24357_PE.bin` を `fl-win64` から `tar --zstd -xf` で展開して改名)。依存は capstone のみ。出力は `tools/shared/work/elastique/facts.json` (gitignore)。

## 0. 結論 (先出し)

| 項目 | 結論 (実測) |
|---|---|
| 判断 (PM, D20) | élastique は所有者限定 tier (運用形態 B) でのみ lift。公開 tier には載せない。FL 本体と別の side module、ビルドフラグ 1 つで除外。lift 対象は win 版 + 自前 IPP (#38) |
| 対象 DLL | `elastique_x64.dll` 4,997,632 B・PE32+ (x64)・export 15 (`*_CreateInstance` ほか) |
| 静的 IPP | 節 `IPPCODE` vsize 979,394 B (pdata 関数 919)。**IPP の動的 import は無い** (IAT は KERNEL32 77・WS2_32 2 のみ) |
| IPP への入口 | `.text` の線形走査で IPPCODE への直接 call/jmp **810 箇所・入口 197 個** (pdata 範囲だけなら 763 箇所・182 個) |
| 入口集合は閉じているか | 計測の範囲で閉じている: IPPCODE から外への直接 call 0、`.text` → IPPCODE の RIP 相対参照 0、絶対 8 バイトポインタ 0 |
| D20 の停止条件 | 未発動 (置換不能の根拠は見つからない)。ただし **197 入口の IPP API 名は未同定** (シンボル無し) |
| 完了範囲 | 測定と置換可否の判定まで。RetDec lift と side module ビルドは未着手 → 子 T-SH-40 (入口同定・#2613) / T-SH-41 (lift + side module・#2614) |

## 1. 測定 (`scripts/elastique_facts.py`・commit `7cf85980`)

### 1.1 節

| 節 | VA | vsize (B) | 注 |
|---|---|---|---|
| `.text` | 0x1000 | 3,106,128 | élastique 本体 |
| `IPPCODE` | 0x2f8000 | 979,394 | 静的 IPP (win のみ。symbol 無し) |
| `.rdata` | 0x3e8000 | 814,484 | |
| `.data` | 0x4af000 | 22,128 | |
| `.pdata` | 0x4b5000 | 65,700 | 関数 5,475 (`.text` 4,556 / `IPPCODE` 919) |
| `IPPDATA` | 0x4c6000 | 2,560 | IPP の定数 (IPP 内から参照) |

### 1.2 import / export

- KERNEL32.dll 77 名: CRT 起動・SEH (`RtlCaptureContext`・`RtlUnwindEx` 等)・TLS・スレッド同期 (`CriticalSection`・`Event`)・ヒープ (`HeapAlloc` 系)・ファイル列挙 (`FindFirstFileExW` 等)・動的読込 (`LoadLibraryExW`・`GetProcAddress`)・コードページ変換。
- WS2_32.dll 2 名: 序数 8・14 (pefile の序数表では `htonl`・`ntohl`)。
- export 15: `Auftakt_CreateInstance`・`Auftakt_CreateInstance2`・`Declicker_CreateInstance`・`Denoiser_CreateInstance`・`ElAllocator_SetFunctions`・`ElProDirect_CreateInstance`・`ElProV3Direct_CreateInstance`・`ElProV3_CreateInstance`・`ElPro_CreateInstance`・`ElResampleSource_CreateInstance`・`ElResampleSource_GetBuildDate`・`ElResampleSource_GetVersion`・`Metering_CreateInstance`・`SolPitchAn_CreateInstance`・`SolPitchAn_CreatePitchMarks`。

### 1.3 IPP への呼出グラフ

| 測定 | 値 | 方法 |
|---|---|---|
| `.text` → IPPCODE の直接 call/jmp (pdata 関数内) | 763 箇所・入口 182 個 (呼出元 171 関数) | pdata 範囲を逆アセンブル |
| 同 (線形走査、pdata 外を含む) | 810 箇所・入口 197 個 | `.text` 全体を線形走査 |
| うち pdata 外にしか現れない入口 | 15 個 | 線形走査の差 |
| 入口関数サイズ (pdata 基準、入口 181 個) | min 15 / median 479 / max 10,456 / 合計 254,089 B | pdata の関数長 |
| IPPCODE → 外への直接 call/jmp | 0 | 線形走査 |
| IPPCODE 内の間接分岐 | call reg 69・jmp reg 102 (計 171) | 逆アセンブル |
| `.text` の間接分岐 | call mem 2,180・call reg 193・jmp reg 113・jmp mem 44 (計 2,530) | 同 (内訳は未計測。IPP 宛ての証拠は下記の 0 件) |
| `.text` → IPPCODE の RIP 相対参照 | 0 (pdata 基準・線形の両方) | 逆アセンブル |
| 絶対 8 バイトポインタで IPPCODE を指す値 (IPPCODE・`.rdata`・`.data`・`.pdata`) | 0 | 数値走査 |
| IPPCODE 内の RIP 相対参照 (IPPCODE 宛) | 158 | 逆アセンブル |
| `ipp*` 形式の文字列 | 0 (節名 `IPPCODE`・`IPPDATA` の 2 件のみ) | 文字列走査 |

## 2. 解釈

1. **入口は閉じている (計測の範囲)**: IPP 機能への到達は、`.text` からの直接 call/jmp (入口 197) と IPP 内部の間接分岐だけに見える。`.text` の間接分岐 2,530 件が IPPCODE を指す証拠は、絶対ポインタ・RIP 相対参照のいずれも 0 件。ただし実行時に計算した関数ポインタ経由の到達は静的には閉じられない (未確認、子 T-SH-40 (#2613) で確認)。
2. **IPP 節は自己完結**: IPPCODE から外への直接 call は 0、IAT への呼出も見えない。入口 197 を自前実装で同名 API に差し替えれば、IPP 節を丸ごと外せる構造になっている。
3. **API 名が無い**: `ipp*` 文字列は 0 件。どの入口がどの `ipps*`・`ippi*` かは未確定。同定の材料は (a) FL 同梱 `dsp_ippv2` (export 名あり・`tools/ipp` の 239 API) との本体照合、(b) 入口の入出力を実行して比べる差分試験の 2 通り。
4. **外部 import**: KERNEL32 77 件は IPP とは別の作業で、wasm の host 境界への置換が要る (子 T-SH-41 (#2614) の範囲)。
5. **pdata 外の入口 15 個**: `.text` 先頭付近の 0x30 間隔の thunk 群などに IPP 呼出がある。線形走査は命令境界を誤る (データを命令として読む) おそれがあるため、入口の最終確定は T-SH-40 で行う。

## 3. D20 の停止条件 (「置換できない場合は理由を報告して停止」) の評価

- 現時点: 置換対象は 197 入口に閉じ、IPP 節の外への依存は無い。**置換不能の根拠は見つからない**。
- 未確定: 入口のうち `tools/ipp` (239 API) に対応が無いものの数。T-SH-40 で確定し、対応の無い入口が 1 件でも残れば、その入口ごとに理由を報告して停止する (D20)。

## 4. 所有者限定 tier と side module (D20 の適用・子 T-SH-41 (#2614) の前提)

- élastique は公開 tier に載せない。release guard の deny-list への 5 成分の追加は D11 に従い PM が手元で行う (本 run は触らない)。
- FL 本体と別の side module としてビルドし、ビルドフラグ 1 つで除外できる構成にする (フラグ名は T-SH-41 で定める)。
- 運用の根拠: 運用形態 B (限定公開・非頒布、`docs/LEGAL.md` §6.0)。法的助言ではない (D20)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 197 入口の IPP API 同定と `tools/ipp` への対応 (停止条件の判定を含む) | 置換できる入口数が確定しない | 子 T-SH-40 (#2613) |
| `.text` 本体の RetDec lift (4,556 関数) と KERNEL32 77 件の host 置換、side module の構成・除外フラグ | élastique の機能が wasm に無い | 子 T-SH-41 (#2614) |
| 実行時に作る関数ポインタ経由の IPP 到達 | 静的測定では閉じていない | 子 T-SH-40 (#2613) の検証項目 |
| release guard deny-list への élastique 追加 | 公開 tier への混入を機械検査できない | PM (D11・手元作業) |
| mac 版 (`elastique_x64.dylib`、Accelerate 依存の扱い) | 本 REPORT は win 版のみ | PM 既定 (win 版) のため対象外 |

## 6. 検証

- 実行: `python3 tools/shared/elastique/scripts/elastique_facts.py` (測定 commit `7cf85980`・4 core・開始時 load 0.15・所要 10.0 s・最大 RSS 約 50 MB・PASS = 例外なく終了し facts.json を出力)。
- 測定 commit からの差分: `git diff 7cf85980 HEAD -- tools/shared/elastique/scripts` の出力は空 (本 REPORT は scripts の外)。
