# tools/shared/elastique REPORT — élastique 2.2.15 (win `elastique_x64.dll`) の静的 IPP 入口と dispatch 層の実測 (T-SH-10 / #152)

> 正本: `tools/shared/elastique/REPORT.md`。方針は `docs/DECISIONS.md` D20 (所有者限定 tier・side module)、分類の事実は `tools/shared/REPORT.md` §0・§5。

既知類型との関係 (DEFECTS.md): 該当 — D9 (jumptable 型の間接分岐) と同型の表 dispatch (`jmp [r10+rax*8]`)、D15 (メモリ間接分岐の欠落) と D11・D14 (表の絶対 VA・可変索引の窓) は lift 段の確認対象。線形走査の IPPCODE 内データ誤デコード (外向き 32 件) は既存 ID に該当なし。

日付: 2026-10-14 / 担当: #152 fix run (review 5520905288 の差し戻し対応) / 測定 commit: 既存 `7cf85980` (`scripts/elastique_facts.py`、以後変更なし)・追補 `a27c04e5` (`scripts/elastique_dispatch.py`)
再現: `python3 tools/shared/elastique/scripts/elastique_facts.py` と `python3 tools/shared/elastique/scripts/elastique_dispatch.py` (入力 `tools/shared/work/win/elastique_x64.dll`。素材は `docs/REFERENCES.md` `[WIN64]` の `extracted/block24357_PE.bin` を `fl-win64` から `tar --zstd -xf` で展開して改名)。依存は capstone のみ。出力は `tools/shared/work/elastique/` (gitignore)。

## 0. 結論 (先出し)

| 項目 | 結論 (実測) |
|---|---|
| 判断 (PM, D20) | élastique は所有者限定 tier (運用形態 B) でのみ lift。公開 tier には載せない。FL 本体と別の side module、ビルドフラグ 1 つで除外。lift 対象は win 版 + 自前 IPP (#38) |
| 対象 DLL | `elastique_x64.dll` 4,997,632 B・PE32+ (x64)・export 15 (`*_CreateInstance` ほか) |
| 静的 IPP | 節 `IPPCODE` vsize 979,394 B (pdata 関数 919)。**IPP の動的 import は無い** (IAT は KERNEL32 77・WS2_32 2 のみ) |
| IPPCODE への直接入口 | `.text` → IPPCODE の直接 call/jmp: **線形走査 810 箇所・入口 197 個** / pdata 範囲内のみ 763 箇所・入口 182 個 (測定方法を §1.3 に明記) |
| dispatch 層 (新規) | `.text` に thunk 33 本 (`call` 初期化スタブ → 索引 `[0x1804afc54]` → `jmp [表+索引*8]`)。表の飛び先は **198 スロット・distinct 186 件、全て `.text`** (IPPCODE 直接は 0)。186 件のうち 59 件が IPPCODE へ直接 call/jmp を持つ (§2) |
| IPPCODE の外部依存 | **0 ではない**。線形走査で外向き直接分岐 33 件 (イメージ外 32 = 誤デコードとみなす / `.text` 1 = 初期化スタブ `0x1803e71b0` → `0x1800010a0`) |
| 入口集合は閉じているか | **閉じていない (静的に示せない)**。thunk 頭 33 本は、直接 call/jmp・RIP 相対・即値・絶対値のいずれでも参照されない (§2.4)。到達元は実行時計算の経路と推定 (未確定) |
| D20 の停止条件 | 未発動 (置換不能の根拠は見つからない)。ただし dispatch 層の `.text` 関数 186 件 (2 段目以降を含めると 251 件) の IPP API 同定は未了 → #2613 |
| 完了範囲 | 測定と置換可否の一次判定まで。RetDec lift と side module ビルドは未着手 → 子 T-SH-40 (入口同定・#2613) / T-SH-41 (lift + side module・#2614) |

## 1. 測定

### 1.1 節

| 節 | VA | vsize (B) | 注 |
|---|---|---|---|
| `.text` | 0x1000 | 3,106,128 | élastique 本体 (dispatch thunk・表の飛び先を含む) |
| `IPPCODE` | 0x2f8000 | 979,394 | 静的 IPP (win のみ。symbol 無し) |
| `.rdata` | 0x3e8000 | 814,484 | |
| `.data` | 0x4af000 | 22,128 | dispatch 索引・枠・表 |
| `.pdata` | 0x4b5000 | 65,700 | 関数 5,475 (`.text` 4,556 / `IPPCODE` 919) |
| `IPPDATA` | 0x4c6000 | 2,560 | IPP の定数 (IPP 内から参照) |

### 1.2 import / export

- KERNEL32.dll 77 名: CRT 起動・SEH・TLS・スレッド同期・ヒープ (`HeapAlloc` 系)・ファイル列挙・動的読込 (`LoadLibraryExW`・`GetProcAddress`)・コードページ変換。
- WS2_32.dll 2 名: 序数 8・14 (`htonl`・`ntohl`)。
- export 15: `Auftakt_CreateInstance`・`Auftakt_CreateInstance2`・`Declicker_CreateInstance`・`Denoiser_CreateInstance`・`ElAllocator_SetFunctions`・`ElProDirect_CreateInstance`・`ElProV3Direct_CreateInstance`・`ElProV3_CreateInstance`・`ElPro_CreateInstance`・`ElResampleSource_CreateInstance`・`ElResampleSource_GetBuildDate`・`ElResampleSource_GetVersion`・`Metering_CreateInstance`・`SolPitchAn_CreateInstance`・`SolPitchAn_CreatePitchMarks`。

### 1.3 IPP への呼出し・分岐 (測定方法ごとにラベル)

「pdata」= `.pdata` の関数範囲内だけを逆アセンブル。「線形」= 節全体を先頭から線形走査 (不正命令は 1 byte 飛ばす・objdump と同じ方式)。

| 測定 | 値 | 方法 |
|---|---|---|
| `.text` → IPPCODE の直接 call/jmp | pdata 基準 763 箇所・入口 182 個 / 線形 810 箇所・入口 197 個 | pdata / 線形 |
| 入口 182 の内訳 (pdata 基準) | 関数先頭 181 個 + pdata 範囲外 1 個 (`0x1802f8030`。どの pdata 範囲にも入らない IPPCODE 内の位置。レビューの「途中」は本測定では範囲外) | pdata 範囲判定 |
| 線形 197 の内訳 | pdata 先頭 195 個 + 非先頭 2 個 (`0x1802f8030`・初期化スタブ `0x1803e71b0`)。pdata 外にしか現れない入口 15 個 (うち `0x1803e71b0` を含む) | 線形 − pdata |
| IPPCODE → 外への直接 call/jmp | pdata 基準 **0** / 線形 **33** (内訳: イメージ外 32・`.text` 1 = `0x1803e71b0` → `0x1800010a0`。33 件とも送り元は pdata 外) | pdata / 線形 |
| IPPCODE 内の間接分岐 | pdata 基準: call reg 69・jmp reg 102 (計 171) / 線形: call reg 72・jmp reg 102・jmp mem 12 (計 186) | 同上 |
| IPPCODE 内の RIP 相対参照 (IPPCODE 宛) | pdata 基準 158 / 線形 170 | 同上 |
| `.text` 内の間接分岐 | call mem 2,180・call reg 193・jmp reg 113・jmp mem 44 (計 2,530。pdata 基準・`facts.json`) | pdata 基準 |
| `.text` → IPPCODE の RIP 相対参照 | 0 (pdata 基準・線形の両方) | 逆アセンブル |
| 絶対 8 バイト値が IPPCODE を指す | 0 (IPPCODE・`.rdata`・`.data`・`.pdata` の 8 バイト走査) | 数値走査 |
| `.reloc` DIR64 の照合 (陽性対照つき) | 4,103 件。指す先: IPPCODE **0** / `.text` 3,086 (陽性対照) / `.rdata` 978 / `.data` 39 | `.reloc` 全件 |
| `ipp*` 形式の文字列 | 大文字小文字を区別しない `strings -a -n 4 \| grep -i ipp` は **5 行**: `IPPCODE`・`IPPDATA`・`@IPPDATA`・`` `IPPCODE ``・RTTI `.?AVCzplfFFTIPP@@` (FFT が IPP 由来であることを示唆)。大文字小文字を区別する `^ipp` は 0 | 文字列走査 |

## 2. dispatch 層 (`scripts/elastique_dispatch.py`・測定 commit `a27c04e5`)

### 2.1 構造

- **thunk 33 本**: 頭は `0x180001800` + 0x30 × k (k = 0〜31) と `0x1801bad00`。形は `call 0x1803e71b0` (IPPCODE 内・非 pdata の初期化スタブ: push×4 → `call 0x1800010a0` → pop×4 → ret) → `movsxd rax,[0x1804afc54]` → `lea r10,[表]` → `jmp [r10+rax*8]`。
- **索引 `[0x1804afc54]`** (dword。ファイル上の初期値 −1): 書込みは `.text` の 2 箇所のみ。`0x1800010bb` (`mov …, 0`・失敗経路) と `0x1800010e6` (`mov …, edx`・edx は CPU 判定関数 `0x1800015a0` が out 引数 (rdi = `[rsp+0x28]`) へ書いた値)。`0x1800015a0` が out へ書く即値は 0〜5 (13 箇所)。**索引の値域 = {0,…,5}** (6 種の CPU クラス。6 は未対応で null)。
- **0x1800010a0** (`.text`): 初期化。判定失敗の経路は先に索引 0 を書いてから共通経路 `0x1800010ca` へ落ちる。共通経路は `0x1800015a0` を呼び、最後に `[索引] = edx` を書いてから戻る。つまり thunk が索引を読む前に、必ず索引を書き直す。
- **枠 (record)**: 1 つの IPP 関数ごとに 8 qword。`枠 = B − 8` (B は表の先頭) に thunk 頭 (再配置される絶対ポインタ)、`B+0〜+5` = CPU クラス 0〜5 の実装、`B+6` = 0、`B+7` = 次の枠。32 本は `0x1804afc60 + 0x40 × k` に連続。最後の 1 本 (`0x1801bad00`・枠 `0x1804b08c0`) は `B+6` が非 0 (`0x1801bb1c0`) で、32 本の配置と合わない別群 (索引値域 0〜5 では `B+6` は到達しない)。
- 表の参照: `lea r10,[rip+表]` が 33 箇所 (`.text`)。

### 2.2 表の全エントリ (レビュー (c)・索引値域 0〜5 の到達分)

thunk `0x180001800` (枠 `0x1804afc60`・表 `0x1804afc68`):

| 索引 | 飛び先 | 節 | pdata | IPPCODE への直接 call/jmp | 本体の直接分岐先 (2 段目) |
|---|---|---|---|---|---|
| 0〜5 (6 クラス同一) | `0x180001e00` | `.text` | 範囲外 | 0 | `0x1802840e0` (`.text`・pdata 先頭・IPPCODE 直接 0) |
| 6 | 0 (null) | – | – | – | – |
| (7 = 次の枠) | `0x180001830` (thunk 頭) | – | – | – | – |

thunk `0x180001830` (枠 `0x1804afca0`・表 `0x1804afca8`):

| 索引 | 飛び先 | 節 | pdata | IPPCODE への直接 call/jmp | 本体の直接分岐先 (2 段目) |
|---|---|---|---|---|---|
| 0〜5 (6 クラス同一) | `0x180001e20` | `.text` | 範囲外 | 0 | `0x180284120` (`.text`・pdata 範囲外・IPPCODE 直接 0) |
| 6 | 0 (null) | – | – | – | – |
| (7 = 次の枠) | `0x180001860` (thunk 頭) | – | – | – | – |

`0x180001e00` は `test ecx,ecx; jle; cmp ecx,0x7fffffff; jbe` で ecx の範囲を検査し、範囲内なら `jmp 0x1802840e0` (tail jump)、範囲外なら `xor eax,eax; ret`。`0x1802840e0` の本体の処理内容は未同定 (引数検査後に確保を行うとレビューが読んでいる。推定・未検証)。

### 2.3 33 本の集計

- 1 段目: 198 スロット (33 本 × 索引 0〜5) → distinct **186 件**、全て `.text`、IPPCODE 0。
  - pdata 先頭 167 件 (IPPCODE へ直接 call/jmp あり **59** / なし 108)、pdata 範囲外 19 件 (なし)。
  - 6 クラスの飛び先が全て同一の thunk は 2 本、5 種 2 本、6 種 29 本。
- 2 段目 (1 段目の本体内の直接 call/jmp 先。同一関数内の分岐先を含む): distinct **251 件**、全て `.text`。pdata 先頭 87 (IPPCODE 直接あり 22) / pdata 途中 99 (同 23) / pdata 範囲外 65 (同 10)。IPPCODE 直接ありは計 55 件。

### 2.4 thunk 頭への参照 (入口の静的な見え方)

- thunk 頭 33 本 (`0x180001800`・… `0x1801bad00`) への参照: 直接 call/jmp **0**、RIP 相対 **0**、即値 **0** (`elastique_dispatch.py` の計数)。`.rdata`・`.pdata`・`IPPDATA`・`_RDATA` の 8 バイト走査で thunk 頭の値 **0** (スクリプト外の一回限りの走査)。
- 枠 33 個 (`.data`) を指す参照: RIP 相対 **0** (計数)、枠のアドレスを値に持つ 8 バイト **0** (一回限りの走査)。枠の中身 (thunk 頭) は `.reloc` の DIR64 33 件 (`dir64_at_slots` = `dir64_value_is_thunk_head` = 33) で再配置される絶対値として存在する。
- `call 0x1803e71b0` (初期化スタブ) の呼出しは `.text` の thunk 33 本からのみ (IPPCODE 内の呼出し 0)。
- 結論: thunk 頭への到達は**静的には見えない**。実行時に計算したアドレス経由で到達すると推定 (未確定。検証は #2613)。

## 3. 解釈 (差し戻し後の結論)

1. **IPPCODE の 197 入口だけでは IPP 機能の入口を尽くさない**。`.text` の dispatch 表の飛び先は 186 件 (全て `.text`) で、そのうち 59 件が IPPCODE へ直接 call/jmp を持つ。IPP 相当の実装は IPPCODE の外 (`.text`) にもある。
2. **IPPCODE は外部依存 0 ではない**。線形走査の外向き直接分岐 33 件のうち、32 件は飛び先がイメージ外 (例: `0x1803dfc26 → 0x161ae316a`) で、データの誤デコードとみなす。残る 1 件は初期化スタブ `0x1803e71b0` (pdata 外) から `.text` の `0x1800010a0` (索引を書く関数・pdata 先頭) への呼出し。IPPCODE と `.text` は双方向に結ばれている。
3. **「自己完結」「丸ごと外せる」「依存 0」は成り立たない** (撤回)。IPPCODE だけを差し替えても、索引の書込み・dispatch 表・`.text` の 186 関数が残る。
4. **入口集合は静的に閉じていない**。thunk 頭 33 本の到達元が静的に見えない (§2.4)。「閉じている」と書いていた前版の記述は撤回する。
5. D20 の停止条件は未発動のまま (置換不能の根拠は見つからない)。ただし dispatch 層の `.text` 関数 186 件 (2 段目 251 件) の同定と、thunk 頭の到達元の確認が済むまで、置換対象の件数は確定しない → #2613。

## 4. D20 の停止条件 (「置換できない場合は理由を報告して停止」) の評価

- 現時点: 置換不能の根拠は見つからない (IPP 相当の実装は IPPCODE と `.text` の両方にある)。
- 未確定: (a) IPPCODE 直接の 197 入口と dispatch 表の 186 関数のうち、`tools/ipp` (239 API) に対応が無いものの数。(b) thunk 頭 33 本の到達元。いずれも T-SH-40 (#2613) で確定し、対応の無いものが残れば、その入口ごとに理由を報告して停止する (D20)。

## 5. 所有者限定 tier と side module (D20 の適用・子 T-SH-41 (#2614) の前提)

- élastique は公開 tier に載せない。release guard の deny-list への追加は D11 に従い PM が手元で行う (本 run は触らない)。
- FL 本体と別の side module としてビルドし、ビルドフラグ 1 つで除外できる構成にする (フラグ名は T-SH-41 で定める)。
- 運用の根拠: 運用形態 B (限定公開・非頒布、`docs/LEGAL.md` §6.0)。法的助言ではない (D20)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| IPPCODE 直接の入口 197 と dispatch 表の関数 186 (2 段目 251 を含む) の IPP API 同定と `tools/ipp` への対応 (D20 停止条件の判定を含む) | 置換できる入口数が確定しない | 子 T-SH-40 (#2613) |
| dispatch 表経由で到達する `.text` 内の IPP 相当関数の同定 (上記 186 件の内訳と IPPCODE 直接 call を持つ 59 件) | 置換対象が過小になりうる | 子 T-SH-40 (#2613)。受入条件へ issue コメントで追記 |
| thunk 頭 33 本の到達元 (実行時に計算されるアドレスの経路・枠の参照元) | 入口集合が静的に閉じない | 子 T-SH-42 (#2643・実行時到達の動的確認。既存の受入条件) |
| `.text` 本体の RetDec lift (4,556 関数)・KERNEL32 77 件の host 置換・side module の構成・除外フラグ | élastique の機能が wasm に無い | 子 T-SH-41 (#2614) |
| release guard deny-list への élastique 追加 | 公開 tier への混入を機械検査できない | PM (D11・手元作業) |
| mac 版 (`elastique_x64.dylib`、Accelerate 依存の扱い) | 本 REPORT は win 版のみ | 対象外。縮小後の親 #152 の範囲外のため、親 issue に残す (mac 版の扱いは親で判断) |

## 7. 検証

- 測定 commit と差分 (WORKFLOW §6):
  - `scripts/elastique_facts.py`: 測定 commit `7cf85980`。`git diff 7cf85980 HEAD -- tools/shared/elastique/scripts/elastique_facts.py` の出力は空 (0 行)。
  - `scripts/elastique_dispatch.py`: 測定 commit `a27c04e5` (追補の最終版)。`git diff a27c04e5 HEAD -- tools/shared/elastique/scripts` の出力は本 REPORT の commit 時点で空 (`scripts` の変更は無い)。
- 実行時間 (4 core・n=3・所要は実測の real):
  - `elastique_facts.py`: 16.6 s / 17.1 s / 16.8 s (min 16.6、max 17.1)。開始時 load average (1 分) 0.20 / 0.38 / 0.56。
  - `elastique_dispatch.py`: 33.5 s / 33.8 s / 33.9 s (min 33.5、max 33.9)。開始時 load average (1 分) 0.46 / 0.67 / 0.82。3 回の標準出力は同一 (`cmp` 一致)。
  - 前版の「10.0 s」は 1 回の計測で、今回の n=3 の範囲 (16.6〜17.1 s) と合わない。レビューの再実行 16.7 s とは一致する。
- 別アルゴリズムの検算: 線形走査の外向き 33 件はレビューの objdump 線形走査 33 件と一致。`.reloc` DIR64 の照合 (4,103・IPPCODE 0・`.text` 3,086) はレビューの照合と一致。
- ネガティブコントロール: `.reloc` の `.text` 指し 3,086 件が陽性対照 (検出器は機能している)。thunk のパターン照合 (`call` → `movsxd` → `lea` → `jmp [r10+rax*8]`) は一致しない場合に assert で停止し、33 箇所すべてで通過した。
- 範囲外: 2 段目以降の関数の意味 (IPP の API 名)・thunk 頭の実行時到達・mac 版は未検証。
