# tools/shared/elastique REPORT — élastique 2.2.15 (win `elastique_x64.dll`) の静的 IPP 入口と dispatch 層の実測 (T-SH-10 / #152)

> 正本: `tools/shared/elastique/REPORT_152.md` (#152・T-SH-10)。同ディレクトリの `REPORT.md` は #2613 (T-SH-40) の REPORT で、別の文書。方針は `docs/DECISIONS.md` D20 (所有者限定 tier・side module)、分類の事実は `tools/shared/REPORT.md` §0・§5。

既知類型との関係 (DEFECTS.md): 該当 — D9 (`jmp reg` 型の間接分岐) と類似の表 dispatch (本件は `jmp [r10+rax*8]` の 8 バイト絶対ポインタ表で、D9 の `lea` + 4 バイト表の `mov` とは同型ではない)。D15 (`call [mem]` の欠落) が `jmp [mem]` にも及ぶかは lift 段で確認する。D11・D14 (表の絶対 VA・可変索引の窓) も lift 段の確認対象。線形走査の IPPCODE 内データ誤デコード (外向き 32 件) は既存 ID に該当なし。

日付: 2026-10-14 / 担当: #152 fix run 4 (review round 4 の差し戻し対応) / 測定 commit: facts `7cf85980` (`scripts/elastique_facts.py`、以後変更なし)・dispatch `dcd3e7df` (`scripts/elastique_dispatch.py`、以後変更なし)
再現: `python3 tools/shared/elastique/scripts/elastique_facts.py` と `python3 tools/shared/elastique/scripts/elastique_dispatch.py` (入力 `tools/shared/work/win/elastique_x64.dll`。素材は `docs/REFERENCES.md` `[WIN64]` の `extracted/block24357_PE.bin` を `fl-win64` から `tar --zstd -xf` で展開して改名)。依存は capstone のみ。出力は `tools/shared/work/elastique/` (gitignore)。`dispatch.json` の `summary.D_qword_refs` に §2.4 の 8 バイト走査の結果。

## 0. 結論 (先出し)

| 項目 | 結論 (実測) |
|---|---|
| 判断 (PM, D20) | élastique は所有者限定 tier (運用形態 B) でのみ lift。公開 tier には載せない。FL 本体と別の side module、ビルドフラグ 1 つで除外。lift 対象は win 版 + 自前 IPP (#38) |
| 対象 DLL | `elastique_x64.dll` 4,997,632 B・PE32+ (x64)・export 15 (`*_CreateInstance` ほか) |
| 静的 IPP | 節 `IPPCODE` vsize 979,394 B (pdata 関数 919)。**IPP の動的 import は無い** (IAT は KERNEL32 77・WS2_32 2 のみ) |
| IPPCODE への直接入口 | `.text` → IPPCODE の直接 call/jmp: **線形走査 810 箇所・入口 197 個** / pdata 範囲内のみ 763 箇所・入口 182 個 (測定方法を §1.3 に明記) |
| dispatch 層 (新規) | `.text` に thunk 33 本 (`call` 初期化スタブ → 索引 `[0x1804afc54]` → `jmp [表+索引*8]`)。表の 1 段目の飛び先は **198 スロット・distinct 186 個、全て `.text`** (IPPCODE 直接は 0)。186 個のうち 59 個が IPPCODE へ直接 call/jmp を持つ (§2) |
| IPPCODE の外部依存 | **0 ではない**。線形走査で外向き直接分岐 33 件 (イメージ外 32 = 誤デコードとみなす / `.text` 1 = 初期化スタブ `0x1803e71b0` 内の `call` (`0x1803e71b6`) → `0x1800010a0`)。pdata 関数内だけを数えると 0 (測定方法は §1.3) |
| 入口集合は閉じているか | **閉じていない (静的に示せない)**。thunk 頭 33 本は、直接 call/jmp・RIP 相対・即値では参照されない。8 バイト値としての参照は枠の中身 (`.data` 33 件・`.reloc` DIR64 と同じ) だけ (§2.4)。到達元は実行時計算の経路と推定 (未確定) |
| D20 の停止条件 | 未発動 (置換不能の根拠は見つからない)。ただし dispatch 層の `.text` の 1 段目の飛び先 186 個と、その本体の直接分岐先 251 個 (2 段目。1 段目と重複しないもの・関数内の位置を含む。関数先頭は 87 個) の IPP API 同定は未了 → #2667 |
| 完了範囲 | 測定と置換可否の一次判定まで。dispatch 飛び先の IPP 同定は T-SH-43 (#2667・§8)。RetDec lift と side module ビルドは未着手 → T-SH-41 (lift + side module・#2614) |

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
| 入口 182 の内訳 (pdata 基準) | 関数先頭 181 個 + pdata 範囲外 1 個 (`0x1802f8030`。どの pdata 範囲にも入らない IPPCODE 内の位置で、pdata 関数の途中ではない) | pdata 範囲判定 |
| 線形 197 の内訳 | pdata 先頭 195 個 + 非先頭 2 個 (`0x1802f8030`・初期化スタブ `0x1803e71b0`)。pdata 外にしか現れない入口 15 個 (うち `0x1803e71b0` を含む) | 線形 − pdata |
| IPPCODE → 外への直接 call/jmp | pdata 基準 **0** / 線形 **33** (内訳: イメージ外 32・`.text` 1 = `0x1803e71b6` (初期化スタブ `0x1803e71b0` 内の `call`) → `0x1800010a0`。33 件とも送り元は pdata 外) | pdata / 線形 |
| IPPCODE 内の間接分岐 | pdata 基準: call reg 69・jmp reg 102 (計 171) / 線形: call reg 72・jmp reg 102・jmp mem 12 (計 186) | 同上 |
| IPPCODE 内の RIP 相対参照 (IPPCODE 宛) | pdata 基準 158 / 線形 170 | 同上 |
| `.text` 内の間接分岐 | call mem 2,180・call reg 193・jmp reg 113・jmp mem 44 (計 2,530。pdata 基準・`facts.json`) | pdata 基準 |
| `.text` → IPPCODE の RIP 相対参照 | 0 (pdata 基準・線形の両方) | 逆アセンブル |
| 絶対 8 バイト値が IPPCODE を指す | 0 (全節の 8 バイト整列位置の走査) | `elastique_dispatch.py` の `D_qword_refs` |
| `.reloc` DIR64 の照合 (陽性対照つき) | 4,103 件。指す先: IPPCODE **0** / `.text` 3,086 (陽性対照) / `.rdata` 978 / `.data` 39 | `.reloc` 全件 |
| `ipp*` 形式の文字列 | 大文字小文字を区別しない `strings -a -n 4 \| grep -i ipp` は **5 行**: `IPPCODE`・`IPPDATA`・`@IPPDATA`・`` `IPPCODE ``・RTTI `.?AVCzplfFFTIPP@@` (FFT が IPP 由来であることを示唆)。大文字小文字を区別する `^ipp` は 0 | 文字列走査 |

## 2. dispatch 層 (`scripts/elastique_dispatch.py`・測定 commit `dcd3e7df`)

### 2.1 構造

- **thunk 33 本**: 頭は `0x180001800` + 0x30 × k (k = 0〜31) と `0x1801bad00`。形は `call 0x1803e71b0` (IPPCODE 内・非 pdata の初期化スタブ: push×4 → `call 0x1800010a0` (呼出し命令は `0x1803e71b6`) → pop×4 → ret) → `movsxd rax,[0x1804afc54]` → `lea r10,[表]` → `jmp [r10+rax*8]`。thunk は索引を読む前に毎回このスタブを通る。
- **索引 `[0x1804afc54]`** (dword。ファイル上の初期値 −1): 書込みは `.text` の 2 箇所のみ。`0x1800010bb` (`mov …, 0`・判定失敗の経路) と `0x1800010e6` (`mov [索引], edx`。edx は `0x1800010e2` で `[rsp+0x28]` から読んだ値)。`[rsp+0x28]` は CPU 判定関数 `0x1800015a0` の out 変数。呼出し側 `0x1800010cf` の `lea rdx,[rsp+0x28]` が番地を渡し、`0x1800015a9` の `mov rdi,rdx` で rdi に入れる。
  - `0x1800015a0` の直接 store (rdi = out のまま到達するもの) は **13 箇所・値 0〜5** (`dispatch.json` の `cpu_fn_out_stores_rdi` 13 件)。この中の `0x1800017b2`・`0x1800017c0` は `mov rdi,r12` (`0x180001791`) より後の位置だが、`0x180001783` の `je 0x1800017a9` がその `mov` を飛び越えて到達するため rdi はまだ out (逆アセンブルで確認)。
  - **索引の値域 = {0,…,5}** (6 種の CPU クラス。6 は未対応で null)。ただし、これは `0x1800015a0` の直接 store に限る。callee 経由の書込みは下記の未解決 (§6)。
  - callee の検査 (逆アセンブル): `0x1800015c8` の `call 0x180001120` は rdx = out のまま呼ばれる。`0x180001120` は `[r13]` (= rcx = `[rsp+0x20]` の一時領域) と RIP 相対にしか store しない。しかし `call 0x1802f8030` (IPPCODE・`0x180001150`) の時点でも rdx = out のまま。`0x18000168c` の `call 0x180001580` は RIP 相対の store しか持たず、out には書けない。**`0x1802f8030` が `[rdx]` へ書くかは未検査**。
- **0x1800010a0** (`.text`・pdata 先頭・0x80 B): 索引を書く関数。`0x1800010b4` の分岐 (判定 `0x180001000` の戻り値) の両側が `0x1800010ca` に合流し、`0x1800015a0` を呼んだ後、`0x1800010e6` で `[索引] = edx` を書き、`0x1800010ec` で IPPCODE の `0x1802f83b8` を直接 call して戻る (`0x180001105`)。thunk → `0x1803e71b0` → `0x1800010a0` → `0x1802f83b8` の経路は、全 thunk に共通。
- **枠 (dispatch 枠・record)**: 1 つにつき 8 qword (IPP 関数との対応は未同定。同定は #2667)。`枠 = B − 8` (B は表の先頭) に thunk 頭 (再配置される絶対ポインタ)、`B+0〜+5` = CPU クラス 0〜5 の実装、`B+6` = 0、`B+7` = 次の枠の thunk 頭 (例 `0x180001830`)。32 本は `0x1804afc60 + 0x40 × k` に連続。最後の 1 本 (`0x1801bad00`・枠 `0x1804b08c0`) は `B+6` が非 0 (`0x1801bb1c0`) で、32 本の配置と合わない別群 (索引値域 0〜5 では `B+6` は到達しない)。
- 表の参照: `lea r10,[rip+表]` が 33 箇所 (`.text`)。

### 2.2 先頭 2 本の全エントリ (例示)

33 本のうち先頭 2 本の表を載せる (索引 0〜7 の全スロット)。残り 31 本は §2.3 の集計と `work/elastique/dispatch.json` (`records` = 33 本分、キーは thunk 頭。`variant_targets`・`hop2_targets`) を指す。

thunk `0x180001800` (枠 `0x1804afc60`・表 `0x1804afc68`):

| 索引 | 飛び先 | 節 | pdata | IPPCODE への直接 call/jmp | 本体の直接分岐先 (2 段目) |
|---|---|---|---|---|---|
| 0〜5 (6 クラス同一) | `0x180001e00` | `.text` | 範囲外 | 0 | `0x1802840e0` (`.text`・pdata 先頭・IPPCODE 直接 0) |
| 6 | 0 (null) | – | – | – | – |
| (7 = 次の枠の thunk 頭) | `0x180001830` | – | – | – | – |

thunk `0x180001830` (枠 `0x1804afca0`・表 `0x1804afca8`):

| 索引 | 飛び先 | 節 | pdata | IPPCODE への直接 call/jmp | 本体の直接分岐先 (2 段目) |
|---|---|---|---|---|---|
| 0〜5 (6 クラス同一) | `0x180001e20` | `.text` | 範囲外 | 0 | `0x180284120` (`.text`・pdata 範囲外・IPPCODE 直接 0) |
| 6 | 0 (null) | – | – | – | – |
| (7 = 次の枠の thunk 頭) | `0x180001860` | – | – | – | – |

`0x180001e00` は `test ecx,ecx; jle; cmp ecx,0x7fffffff; jbe` で ecx の範囲を検査し、範囲内なら `jmp 0x1802840e0` (tail jump)、範囲外なら `xor eax,eax; ret`。

`0x1802840e0` (`.text`・pdata 先頭) の逆アセンブル: `ecx ≤ 0` なら 0 を返す。`eax = ecx + 0x48` を求め (符号付き溢れ検査 `cmp eax,ecx`)、`rcx = rax` として `call 0x1802d10b0` (`.text`) を呼ぶ。戻り値 0 なら 0 を返す。非 0 なら `rdx = (rax+0x47) & ~0x3f` (64 バイト整列) の位置の `[rdx-8]` に確保戻り値 rax を保存し、rdx を返す。`0x180284120` (`.text`) は `[rcx-8]` の保存値を読み `jmp 0x1802d109c` (`.text`) する (整列確保の解放の形)。`0x1802d10b0`・`0x1802d109c` の中身は未同定。

### 2.3 33 本の集計

- 1 段目: 198 スロット (33 本 × 索引 0〜5) → distinct **186 個** (飛び先)、全て `.text`、IPPCODE 直接 0。
  - pdata 先頭 (関数先頭) 167 個 (IPPCODE へ直接 call/jmp あり **59** / なし 108)、pdata 範囲外 19 個 (なし)。
  - 6 クラスの飛び先が全て同一の thunk は 2 本、5 種 2 本、6 種 29 本。
- 2 段目 (1 段目の本体の直接 call/jmp 先のうち、1 段目と重複しないもの): distinct **251 個** (関数内の位置を含む)、全て `.text`。内訳は pdata 先頭 (関数先頭) 87 (IPPCODE 直接あり 22) / pdata 途中 (関数内の位置) 99 (同 23) / pdata 範囲外 65 (同 10)。関数先頭は 87 個だけ。IPPCODE 直接ありは計 55 個。

### 2.4 thunk 頭への参照 (入口の静的な見え方)

- thunk 頭 33 本 (`0x180001800`・… `0x1801bad00`) への参照: 直接 call/jmp **0**、RIP 相対 **0**、即値 **0** (`elastique_dispatch.py` の計数)。全節の 8 バイト整列位置の走査 (`D_qword_refs`) で thunk 頭の値は `.data` **33** 件 (枠の中身。下の行の `.reloc` と同じ 33)、他の節 **0**。
- 枠 33 個 (`.data`) を指す参照: RIP 相対 **0** (計数)、枠のアドレスを値に持つ 8 バイト **0** (同じ走査)。枠の中身 (thunk 頭) は `.reloc` の DIR64 33 件 (`dir64_at_slots` = `dir64_value_is_thunk_head` = 33) で再配置される絶対値として存在する。
- `call 0x1803e71b0` (初期化スタブ) の呼出しは `.text` の thunk 33 本からのみ (IPPCODE 内の呼出し 0)。
- 結論: thunk 頭への到達は**静的には見えない**。実行時に計算したアドレス経由で到達すると推定 (未確定。検証は #2643)。

## 3. 解釈 (差し戻し後の結論)

1. **IPPCODE の 197 入口だけでは IPP 機能の入口を尽くさない**。`.text` の dispatch 表の 1 段目の飛び先は 186 個 (全て `.text`) で、そのうち 59 個が IPPCODE へ直接 call/jmp を持つ。IPP 相当の実装の所在は、IPPCODE 内 (197 入口) と `.text` 内 (飛び先 186 個のうち未同定) の両方に見える。`.text` 側の IPP 同定は未解決 (→ #2667)。
2. **IPPCODE は外部依存 0 ではない**。線形走査の外向き直接分岐 33 件のうち、32 件は飛び先がイメージ外 (例: `0x1803dfc26 → 0x161ae316a`) で、データの誤デコードとみなす。残る 1 件は初期化スタブ `0x1803e71b0` (pdata 外) の `call` (`0x1803e71b6`) から `.text` の `0x1800010a0` (索引を書く関数・pdata 先頭) への呼出し。IPPCODE と `.text` は双方向に結ばれている。
3. **「自己完結」「丸ごと外せる」「依存 0」は成り立たない** (撤回)。IPPCODE だけを差し替えても、索引の書込み・dispatch 表・`.text` の飛び先 186 個が残る。
4. **入口集合は静的に閉じていない**。thunk 頭 33 本の到達元が静的に見えない (§2.4)。「閉じている」と書いていた前版の記述は撤回する。
5. D20 の停止条件は未発動のまま (置換不能の根拠は見つからない)。ただし dispatch 層の `.text` の 1 段目の飛び先 186 個と、2 段目の飛び先 251 個 (1 段目と重複しないもの) の同定と、thunk 頭の到達元の確認が済むまで、置換対象の件数は確定しない → #2667・#2643。

## 4. D20 の停止条件 (「置換できない場合は理由を報告して停止」) の評価

- 現時点: 置換不能の根拠は見つからない (IPP 相当の実装の所在は、IPPCODE 内と `.text` 内の未同定の飛び先 186 個の両方に見える)。
- 未確定: (a) IPPCODE 直接の 197 入口と dispatch 表の 1 段目の飛び先 186 個 (2 段目の飛び先 251 個は 1 段目と重複しないもの) のうち、`tools/ipp` (239 API) に対応が無いものの数。(b) thunk 頭 33 本の到達元。(a) は T-SH-43 (#2667)、(b) は T-SH-42 (#2643) で確定し、対応の無いものが残れば、その入口ごとに理由を報告して停止する (D20)。

## 5. 所有者限定 tier と side module (D20 の適用・子 T-SH-41 (#2614) の前提)

- élastique は公開 tier に載せない。release guard の deny-list への追加は D11 に従い PM が手元で行う (本 run は触らない)。
- FL 本体と別の side module としてビルドし、ビルドフラグ 1 つで除外できる構成にする (フラグ名は T-SH-41 で定める)。
- 運用の根拠: 運用形態 B (限定公開・非頒布、`docs/LEGAL.md` §6.0)。法的助言ではない (D20)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| IPPCODE 直接の入口 197 と dispatch 表の 1 段目の飛び先 186 個 (2 段目の飛び先 251 個は 1 段目と重複しないもの) の IPP API 同定と `tools/ipp` への対応 (D20 停止条件の判定を含む) | 置換できる入口数が確定しない | 子 T-SH-43 (#2667) |
| dispatch 表経由で到達する `.text` 内の IPP 相当関数の同定 (上記 186 個の内訳と IPPCODE 直接 call を持つ 59 個)。索引 `[0x1804afc54]` の値域の callee 経由の確認 (`0x1800015a0` → `0x180001120` → `0x1802f8030` の rdx = out が `[rdx]` へ書くか) | 置換対象が過小になりうる。索引の値域 {0..5} が確定しない | 子 T-SH-43 (#2667)。#2667 本文へ追記 |
| thunk 頭 33 本の到達元 (実行時に計算されるアドレスの経路・枠の参照元) | 入口集合が静的に閉じない | 子 T-SH-42 (#2643・実行時到達の動的確認。既存の受入条件) |
| `.text` 本体の RetDec lift (4,556 関数)・KERNEL32 77 件の host 置換・side module の構成・除外フラグ | élastique の機能が wasm に無い | 子 T-SH-41 (#2614) |
| release guard deny-list への élastique 追加 | 公開 tier への混入を機械検査できない | PM (D11・手元作業) |
| mac 版 (dylib。実体名・Accelerate 依存の扱いは未確認) | 本 REPORT は win 版のみ。mac 版は実測していない | 依頼者の判断待ち (#152 の needs-user-input): mac 版 (dylib) を追跡するか・既定案: 追跡せず win 版のみ。本 PR は `Closes #152` のため merge で #152 は閉じる |

## 7. 検証

- 測定 commit と差分 (WORKFLOW §6):
  - `scripts/elastique_facts.py`: 測定 commit `7cf85980`。`git diff 7cf85980 HEAD -- tools/shared/elastique/scripts/elastique_facts.py` の出力は空 (0 行)。
  - `scripts/elastique_dispatch.py`: 測定 commit `dcd3e7df` (8 バイト走査の最終版)。`git diff dcd3e7df HEAD -- tools/shared/elastique/scripts` の出力は本 REPORT の commit 時点で空 (0 行)。
- 実行時間 (4 core・n=3・所要は実測の real・実行時の HEAD は `dcd3e7df`。facts の script は `7cf85980` から不変):
  - `elastique_facts.py`: 16.8 s / 16.6 s / 17.0 s (min 16.6、max 17.0)。開始時 load average (1 分) 0.98 / 0.99 / 0.99。3 回の標準出力は同一 (`cmp` 一致)。
  - `elastique_dispatch.py`: 33.3 s / 33.5 s / 34.4 s (min 33.3、max 34.4)。開始時 load average (1 分) 0.60 / 0.76 / 0.87。3 回の標準出力は同一 (`cmp` 一致)。
- 別アルゴリズムの検算: 線形走査の外向き 33 件はレビューの objdump 線形走査 33 件と一致 (前版)。`.reloc` DIR64 の照合 (4,103・IPPCODE 0・`.text` 3,086) は前版から変わらない。
- 陽性対照 (検出器が陽性を出せることの確認): `.reloc` DIR64 の `.text` 指し 3,086 件。IPPCODE 指しの 0 件は、この検出器が陽性を出せる前提での 0 件である。
- 陰性対照 (1 件を壊して FAIL することの確認・dcd3e7df で実施): リポジトリ外 `$RUNNER_TEMP/ex/neg/` に DLL のコピーを作り、thunk 0 (`0x180001800`) の `jmp *(%r10,%rax,8)` (`41 ff 24 c2`・ファイル offset `0xc1e`) を `jmp %rax` + `nop nop` (`ff e0 90 90`) に置き換えた。`elastique_dispatch.py` にこのコピーを渡すと **rc=1・`AssertionError: 0x180001810`** (thunk 形の assert で停止)、標準出力 0 バイト (出力を書く前に停止)。参考 (前版 `a27c04e5` で確認): 同じ箇所を 4 バイト NOP にした場合は `IndexError` で rc=1 (assert ではなく例外で落ちる。FAIL の結果は同じ)。
- thunk パターン照合 (`call` → `movsxd` → `lea` → `jmp [r10+rax*8]`) は、本物の DLL の 33 箇所すべてで assert を通過した (rc=0)。
- 自己検査フラグ `summary.A_dispatch.record_layout_null_slot6_all_zero` は `false` になる。33 本の表の `B+6` (表の先頭 + 48) が全て 0 かを見るフラグで、最後の 1 本 (`0x1801bad00`) の `B+6` が `0x1801bb1c0` (非 0) のため (§2.1)。期待どおりの値で、欠陥ではない。
- 範囲外: 2 段目以降の関数の意味 (IPP の API 名)・thunk 頭の実行時到達・mac 版・`0x1802f8030` が `[rdx]` へ書くか (callee 経由の索引値域) は未検証。(`0x1802f8030` は §8.3 で検査済み。残りは §8.5)

## 8. T-SH-43 (#2667): dispatch 飛び先と初期化スタブの IPP 同定

測定 commit: `02aca7e5` (`scripts/elastique_dispatch_ident.py` の呼出しガードと `data/dispatch_targets.csv` の再生成。以後 scripts・data の変更なし)。前版 `e64d258f` の呼出しガードは呼出先の名前の和集合しか見ておらず、名前の無い呼出先を含む本体に名付けを残していた (差し戻し round 1 の指摘)。入力 `dispatch.json` は `scripts/elastique_dispatch.py` (測定 commit `dcd3e7df`) の出力。

```sh
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/shared/elastique/scripts/elastique_dispatch.py
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/shared/elastique/scripts/elastique_dispatch_ident.py
```

素材: `fl-win64` の `extracted/block24357_PE.bin` を `tools/shared/work/win/elastique_x64.dll` に複製、照合先は `extracted/block24356_PE.bin` (dsp_ippv2_x64)。依存は capstone・pefile。

### 8.1 方法

- 照合は #2613 (`ipp_entries.py`) と同じ。thunk を 4 段まで追い、正規化命令列 (分岐先・RIP 相対変位を伏せる) の SHA-1 の**完全一致**だけを根拠にする。名前は dsp export が 12 段以内で到達する本体の集合。近似比は使わない。
- **呼出しガード (本節で追加)**: 正規化は呼出先を `T` に伏せるため、呼出しを含む本体の一致は形の一致で、呼出先の同一性を示さない。実測でも 11 命令の Sqrt 系ラッパーが 6 スロットで同名に一致した。そこで呼出しを含む本体は、**全呼出先が IPPCODE で、各呼出先が #2613 で名付けられ (`entries.csv` の names が空でない)、その呼出先の名前が照合の名前と 1 つ以上重なる場合だけ**名付ける (呼出先ごとに判定。コードは `guard()`)。それ以外は `class = shape_only` (形のみ一致・未同定扱い。`names` は候補)。呼出しを含まない本体の完全一致はそのまま採る。陽性対照と stub・索引書込み関数の判定も同じ `guard()` を通す。
- 呼出先ごとの判定と、「全呼出先が名前を持つ」かつ「呼出先の名前の和集合が照合の名前と重なる」判定は、CSV 437 行の全てで結果が同じ (差 0 件。CSV の `ipp_callees`・`names` からの再計算)。
- 出力 `data/dispatch_targets.csv` は 1 行 1 飛び先 (437 行)。`label` が最終の表示 (API 名・族候補・未同定)。

### 8.2 結果 (受入 1・2)

| 段 | 飛び先 (distinct) | 一意 API 名 | 族候補 (未同定扱い) | 形のみ一致 (未同定) | 照合不能 (未同定) | 自明本体 (未同定) |
|---|---|---|---|---|---|---|
| 1 段目 (表の飛び先) | 186 | 7 | 2 | 118 | 58 | 1 |
| 2 段目 (1 段目の本体の直接 call/jmp 先) | 251 | 2 | 3 | 13 | 222 | 11 |

- 一意名 (全て呼出しを含まない完全一致・本体 77〜147 トークン):
  - `ippsPhase_32fc`: 1 段目 6 飛び先 (`0x180005900`・`0x180005ae0`・`0x180005cc0`・`0x180005ea0`・`0x180006080`・`0x180006260`)
  - `ippsThreshold_GTVal_32f_I`: 1 段目 `0x1800067a0`
  - `ippsRealToCplx_32f`: 2 段目 `0x18000df60`・`0x18000e5c0`
- 族候補 (名前が決まらない。候補集合は CSV の `names`): 1 段目 2 (`0x18000d520`・`0x18000de80` = {`ippsFFTFwd_RToCCS_32f`・`ippsFFTFwd_RToPack_32f`・`ippsFFTFwd_RToPerm_32f`・`ippsFFTInv_CCSToR_32f`・`ippsFFTInv_PackToR_32f`・`ippsFFTInv_PermToR_32f` の 6 名。本体 11 トークン・呼出しなし)、2 段目 3 (`0x18000ec20`・`0x18000ec60`・`0x18000eca0` = {`ippsFFTInit_R_32f`・`ippsFFTInit_R_64f`・`ippsZero_16s`・`ippsZero_32f`・`ippsZero_32s`・`ippsZero_64f`・`ippsZero_64s`・`ippsZero_8u` の 8 名。呼出先 2 件はいずれも名付けられ、呼出先ごとの重なりを満たす)。
- 族候補から外れたもの: `0x180001e40`・`0x180001ec0`・`0x180001f40`・`0x180001fc0` (前版の族候補 {`ippsRealToCplx_16s`・`ippsRealToCplx_32f`}) は、呼出先 3 件のうち 2 件が未命名 (例 `0x1802f8f10`・`0x1802f9000`) のため形のみ一致へ落ちた。`ippsRealToCplx_16s` は族候補の名前から消えた。
- IPPCODE 直接 call を持つ 59 件 (1 段目) からは**一意名は 0 件**。内訳は族候補 0・形のみ一致 43・照合不能 16 (前版は族候補 4・形のみ一致 39・照合不能 16)。
- 名前の distinct 数 (族候補の名前を含むものと、一意名だけのもの。前版の「合計 35」は前者の数え方を含んでいた):
  - 197 側 (#2613): 行は一意 8 (名前 distinct 3 = `ippsConj_32fc`・`ippsRealToCplx_32f`・`ippsSet_8u`)・族候補 26。族候補の名前を含む distinct は 33。
  - dispatch 側 (本節): 一意名 3 (`ippsPhase_32fc`・`ippsThreshold_GTVal_32f_I`・`ippsRealToCplx_32f`)。族候補の名前を含む distinct は 17。
  - 一意名だけの和集合は 5 名 (`ippsConj_32fc`・`ippsRealToCplx_32f`・`ippsSet_8u`・`ippsPhase_32fc`・`ippsThreshold_GTVal_32f_I`)。新規に加わるのは 2 名 (`ippsPhase_32fc`・`ippsThreshold_GTVal_32f_I`)。

### 8.3 初期化スタブと外向き分岐 (受入 3)

- `0x1803e71b0` (IPPCODE・10 命令・`push×4; call 0x1800010a0; pop×4; ret`): 形は dsp の `0x1839810` と一致し、#2613 の `ippiResize_8u_C3R`・`C4R` の族候補になる (REPORT.md §3 注の偶然一致)。ただし呼出先 `0x1800010a0` (.text) と dsp 側の呼出先の同一性は示せない。**IPP API 名は付けない (未同定・glue)**。`data/entries.csv` の当該行は #2613 の正本として変えず、本節の判定で名付けから外す。
  - 判定 (`guard()` 後): class = `shape_only`、names = {`ippiResize_8u_C3R`・`ippiResize_8u_C4R`} (match = `exact_final`)。呼出先 `0x1800010a0` は .text で IPPCODE ではないため、ガードで未同定。
- `0x1800010a0` (.text・0x80 B・索引を書く関数): `0x180001000`・`0x180001080`・`0x1800015a0` (CPU 判定)・IPPCODE の `0x1802f83b8` を呼ぶ。形は同じく ippiResize 族と一致するが、呼出しガードで `shape_only` → 未同定 (élastique 固有の dispatch 処理)。判定 (`guard()` 後): class = `shape_only`、names = {`ippiResize_8u_C3R`・`ippiResize_8u_C4R`} (match = `exact_final`)、呼出先 {`0x180001000`・`0x180001080`・`0x1800015a0` (.text)・`0x1802f83b8` (IPPCODE)} は IPPCODE 以外を含むため未同定。
- IPPCODE → 外向きの直接分岐 (線形走査 33 件): イメージ外 32 (§1.3 のとおりデータの誤デコード)・`.text` 1 件 = `0x1803e71b6` → `0x1800010a0`。扱い: この 1 件は glue から索引書込み関数への呼出しで、IPP 節と .text は双方向に結ばれたまま。IPPCODE だけを置換しても `0x1800010a0` → `0x1802f83b8` (.text → IPPCODE) と索引書込みが残るため、side module の置換単位は IPPCODE 単独にできない (D20 の判断材料)。
- `0x1802f8030` (§6 の未検査項目): 本体は `mov rax, 1; ret` で、memory への store を持たない。`0x180001120` → `0x1802f8030` の経路で `[rdx]` へ書く項目は閉じた (この callee に限る)。

### 8.4 検証

- 陽性対照: `0x1802f8db0` (#2613 の一意名 `ippsRealToCplx_32f`) は `identified` を返す。呼出しを持たないためガードの対象外 (標準出力に記録)。
- 再現性: 測定 commit `02aca7e5` の HEAD で 3 回再実行 (dispatch は `dcd3e7df` の出力を入力)。標準出力は 3 回とも同一、`data/dispatch_targets.csv` は 3 回とも commit 版と `cmp` 一致。実行時間 (real): 30.2 s / 30.2 s / 30.1 s (開始時の load 1 分 0.21 / 0.52 / 0.71)。修正前の 1 回実行は 29.9 s (`705c560d` の HEAD。scripts は `e64d258f` と同一、同じ環境)。
- 修正の差分: `git diff e64d258f 02aca7e5 -- tools/shared/elastique/data` は CSV の 4 行の差し替え (diff 上は削除 4・追加 4)。対象は 1 段目の 4 飛び先 `0x180001e40`・`0x180001ec0`・`0x180001f40`・`0x180001fc0` の class・label のみ。
- 差分: `git diff 02aca7e5 HEAD -- tools/shared/elastique/scripts tools/shared/elastique/data` の出力は 0 行 (本節の commit 時点)。

### 8.5 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 形のみ一致 131 件 (1 段目 118・2 段目 13): 呼出先が未同定または .text のため、名前を確定できない | 名付けの件数は過小。候補名は CSV `names` | 未起票 (PM 判断。#2613 の未同定 163 と同じ扱い) |
| 2 段目の未同定 222 件 (呼出先を含む本体の照合不能を含む) | IPP 相当の同定が過小 | 未起票 (同上) |
| 索引書込み関数 `0x1800010a0` の呼出先 (`0x180001000`・`0x180001080`) の同定 | 索引の CPU 判定経路の全体像が未確定 | 未起票 |
