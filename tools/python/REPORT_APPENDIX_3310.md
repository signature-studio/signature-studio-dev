# PY-185 付録 (#3310): 換算値 V (slot 0x15e25f8) の確定

親: `tools/python/REPORT_PY39_2548.md` の「PY-185 (#3310)」節。本文の行数上限 (250 行) のため分割移動 (内容は削除していない)。

---

## PY-185 (#3310): 換算値 V (slot 0x15e25f8) の確定

- 測定: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_step_v.py` (測定 commit `a9bf0957a` で再実行: 終了 0・0.57 秒・load average 0.06/0.33/0.23 (実行前)・4 core)。全出力は本節の数値の出所。
- 補助測定 (測定 commit `a9bf0957a`・同じ展開先・終了 0): `pe_xref.py 0x15e25f8` (hits 189・stores 0・100.4 秒)、`pe_xref.py 0x15e2600` (ネガティブコントロール。slot を 1 つずらした対象。hits 35・stores 0・100.6 秒)、`pe_slot_writers.py 0x15e25f8 0` (候補 6 件・100.5 秒)、`pe_slot_writers.py 0x15e25f8 8` (候補 7 件・100.8 秒)。上の 4 本は同時実行の時間。単独の実行 (`f320cc061` 時) は `pe_xref` 61.8〜62.4 秒・`pe_slot_writers` 58.7・59.4 秒。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'` (2.6 秒)。
- 測定 commit: `a9bf0957a` (`pe_step_v.py` の docstring 2 行の修正。解析の出力は `f320cc061` と同一)。差分 0 の証跡は下の「差分 0 の証跡」節。
- main 取り込み後の再測定 (測定 commit `236a6da9a`・競合解消の merge commit。測定経路の解析コードは `a9bf0957a` から不変): `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_step_v.py` 終了 0・0.46 秒・load average 0.46/0.30/0.12 (実行前)。静的値 (slot → `0x15d89c4`・X 96・V 24・V への store `0x13111e5`) は上と同一。`pe_xref.py 0x15e25f8` は hits 189・stores 0 (48.3 秒・load average 0.42 (実行前))。

### slot の初期化 (静的)

- slot `0x15e25f8` は `.data` (file 0x11e0ff8)。静的値は **`0x15d89c4` (ポインタ)**。`.bss` ではないので、ロード直後から値を持つ。
- RIP 相対の参照は読込み 189 件のみ。書込み 0 件・`lea` 0 件 (`pe_xref.py 0x15e25f8`)。slot 自体は実行中に書き換えられない (RIP 相対で見える範囲)。
- 指す構造体 T (base `0x15d89c0`) の静的内容: `+0` (X) = 96、`+4` (V) = **24** (slot の指す int)、`+8` = 96、`+0xc` = 4。`[0x15d898c]` = 4 (steps per beat の定数)。`0x15452a8` の表も `[16, 4, 96]` で、PPQ 96 と整合 (`general.getRecPPQ` 既定 96・PY-119)。

### V の書込み元と式 (PE 実測)

- 更新関数 F = `0x13111a0` (引数 ecx = c)。`0x13111bf call 0x1311050(c)` の戻り値 X' を使う。
  - `0x13111dc mov [T+0], eax` (X := X')。`0x13111e2 shr eax, 2`。`0x13111e5 mov [T+4], eax` (**V := X' >> 2**)。
  - `0x1311205` で `[T+8] = V × [0x15d898c] (=4)`。`0x13112c8` で `[T+0xc]` に eax を書く (直前の `0x13112a1 call 0x1311030` の後。戻り値の式は未追跡)。
- `pe_xref.py 0x15d89c0` の store は `0x13111dc` の 1 件のみ (X の書込み元は F だけ)。
- V (`0x15d89c4`) への **RIP 相対の直接 store は `0x13111e5` の 1 件** (`pe_xref.py 0x15d89c4,0x15d89c8,0x15d89cc,0x15d89d0` の stores 3 = V・T+8・T+0xc)。slot 経由の間接書込みは次の節の候補で、窓内の候補はすべてスロット由来でない (範囲は次の節)。
- F の呼出し元 (E8 rel32 の線形スキャン): 9 件 (`0xecccb0`・`0xece999`・`0xf46a20`・`0xf4ee3b`・`0xf4f7d2`・`0x11ca6bf`・`0x11d4042`・`0x1362d78`・`0x1365758`)。
  - 引数 = X 自身 (`[0x15e01c8]` → T+0): 4 件 (`0xecccb0`・`0x11ca6bf`・`0x11d4042`・`0x1365758`)。この 4 件は X を「同じ値で再計算」する形。
  - 他: `0xf46a20` は `[[0x15e0db0]]` (`.bss` 0x196eb38 の int)、`0xece999` は `0x43aae0` の戻り値、`0x1362d78` はスタック引数、`0xf4ee3b`・`0xf4f7d2` は未追跡。

### 0x1311050 (X' の算出。PE 実測)

- 記法: `[a]` は a 番地の qword を読むこと。O = `[0x15e13b8]` (静的値 `0x196edd0`・`.bss`)、候補の list L = `[[O]+0xaf0]+0x4f8`。件数は vtable `+0x28`、項目は vtable `+0x18`、項目の値は `0x43aae0(項目, 0x7fffffff)`。
- ゲート: `*O == 0` なら候補を見ず **X' = c** (引数のまま)。O の指す `.bss` は静的に読めない。
- ゲートを通るとき: c 以下の最大候補 (floor)・c 以上の最小候補 (ceil) を集め、`|c - floor| < |c - ceil|` なら floor、それ以外は ceil。c と一致する候補があれば c (`0x1311118`〜`0x1311159`)。
- 候補集合の項目の意味 (`0x43aae0`・vtable `+0x18`) は未確定。

### V への間接書込みの判定 (pe_slot_writers の候補 13 件・#3390 の差し戻し対応)

- 列挙: `pe_slot_writers.py 0x15e25f8 0` (V 側。候補 6 件) と `... 8` (T+0xc 側。候補 7 件)。候補は「slot を `mov reg,[slot]` で読んだ直後 0x40 バイト内の `mov [reg+disp],…`」で、レジスタの一致は見ていない (近接の検出)。
- 判定: 各候補の store の基底レジスタを、直前の命令の逆アセンブルで手で追った (再現: `pe_disasm.py <関数の先頭 VA> <命令数>`。例: `0xe862f6` (関数 `0xe863b7` の先頭)、`0x12cfce0`、`0x1309250`)。

| 候補 VA | 書込み | 基底の出所 (実測) | 判定 |
|---|---|---|---|
| 0xe863b7 | `mov [rbx],ecx` | `0xe862fb mov rbx,rcx` (関数入口の第 1 引数)。窓内で rbx の再代入なし。slot の読込み先は rax (0xe86377) | 引数 (呼出し元は未追跡) |
| 0x1062890 | `mov [rcx],dl` | 0x1062868 の ret の後の別関数 (leaf)。rcx はその第 1 引数 | 関数境界越え |
| 0x11e7e10 | `mov [rax],ecx` | `0x11e7df3 mov rax,[0x15e3000]` で再ロード。slot (0x11e7dfa) は rcx に入り `imul` の値だけ | 別の大域 |
| 0x11e7e53 | `mov [rcx],edx` | `0x11e7e41 mov rcx,[0x15e1068]` で再ロード (0x11e7e32 の call で slot 読込みの rcx は失われる) | 別の大域 |
| 0x11fcb5f | `mov [rax],ecx` | `0x11fcb4f mov rax,[0x15e0450]` で再ロード (slot 読込み 0x11fcb27 の rax は 0x11fcb3d で上書き) | 別の大域 |
| 0x130927c | `mov [rdi],eax` | rdi は窓 0x300 内で代入なし (項目の引数。同関数で `[rdi+0x11]` を読む)。slot (0x1309263) は r8 に入り `idiv [r8]` の除数 | 引数 (呼出し元は未追跡) |
| 0xe4eb8e | `mov [rdx+8],ecx` | `0xe4eb8a mov rdx,[rbp+0x30]` で再ロード (slot 0xe4eb72 の rdx は `add r8d,[rdx]` の値読みのみ) | スタックのローカル |
| 0xe4ebaf | `mov [rdx+8],ecx` | `0xe4ebab mov rdx,[rbp+0x30]` で再ロード (slot 読込みは別の分岐) | スタックのローカル |
| 0xe64661 | `mov [rax+8],ecx` | `0xe6464d`・`0xe64654` で rax = `[[rbp+0xad8]+0x58c]` に再代入 (slot 0xe6463e の rax は上書き) | 別の構造体 |
| 0x11b3748 | `mov [rax+8],ecx` | `0x11b3736 mov rax,[0x15e0fd0]` (大域)。slot (0x11b373d) は rcx に入り `add ecx,ecx` の値 | 別の大域 |
| 0x12cff43 | `mov [rsi+8],eax` | `0x12cfeb3 lea rsi,[rcx+rdx*4]` (配列要素)。slot (0x12cff29) は rcx に入り `idiv` の除数 | 配列要素 |
| 0x12cff48 | `mov [rsi+8],0` | 同上 (rsi = 0x12cfeb3) | 配列要素 |
| 0x12cff67 | `mov [rsi+8],eax` | 同上。slot (0x12cff59) は rdx に入り `imul` の係数 | 配列要素 |

- 結論: 13 件すべてで、store の基底レジスタは slot の読込み先ではない。slot を読んだ後の値は `idiv`・`imul`・`add`・`cvtsi2sd` の値としてだけ使われる。
- 範囲: 窓 0x40 バイト内の `mov [reg+0]`・`mov [reg+8]` に限る。引数で渡された基底 (0xe863b7・0x130927c) の呼出し元、窓外・呼出しを跨ぐ間接書込み、`mov` 以外の書込み形式 (`add`・`movss`・`rep stos` 等) は未追跡 (下の未解決表)。

### V の意味と既定値

- `0x130f740`: `step' = step × V` (`mov eax,[V]; imul eax,r8d`)。`0x130f200` の `start = (note[0] / V) × V` (PY-78 節) と合わせ、**V は step 1 つあたりの tick 数**と読める。
- `V = X / 4`。`4` は `shr eax,2` の定数 (かつ steps per beat)。`X` は PPQ 相当 (既定 96)。
- **既定値 = 24** (`.data` の静的初期値 = `T+4`。X の既定 96 から `96 / 4`)。
- 実行時の既定: F が最初に呼ばれたとき、ゲートが通れば X は候補にスナップされる。ゲートの実行時値と 9 呼出し元の引数の出所 (上の未追跡分) は未確定。ゆえに「実行時に V が 24 のままか」は未確定。

### ネガティブコントロールと差分 0 の証跡

- ネガティブコントロール (測定 commit `a9bf0957a`): 対象 slot を 1 つずらした `pe_xref.py 0x15e2600` は hits 35。実 slot `0x15e25f8` は hits 189。対象 VA の参照を数えるため、対象を変えると hits が変わる。
- 差分 (測定経路): `git diff a9bf0957a 236a6da9a -- tools/python/analysis/flapi/pe_step_v.py tools/python/analysis/flapi/pe_xref.py tools/python/analysis/flapi/pe_slot_writers.py tools/python/analysis/flapi/pe_disasm.py | wc -l` の出力は `0`。`f320cc061` からの差分は `pe_step_v.py` の docstring 2 行 (`a9bf0957a`) のみ。
- 差分 (範囲を広げた場合): `git diff a9bf0957a 236a6da9a -- tools/python/provider tools/python/host tools/python/tests tools/python/analysis | wc -l` の出力は `1362` (main 取り込みで入った他 PR の 13 ファイル: `provider/fl_engine.c`・`host/fl_mock.mjs`・`tests/note_enum_diff.mjs` 等と PY-188・PY-86 系の解析スクリプト。PY-185 の測定経路には入らない)。この REPORT の commit は REPORT だけを変える。

### 未解決 (次回の着手点)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| ゲート `*[0x15e13b8]` の実行時値 (初期化元) と候補集合の項目の意味 (`0x43aae0`) | 実行時の V が 24 のままかどうか | #3311 (V を使う handler の前提として追記) |
| F の呼出し元 9 件のうち引数の出所が未追跡の 5 件 (`0xf46a20`・`0xece999`・`0x1362d78`・`0xf4ee3b`・`0xf4f7d2`) | 同上 | #3311 |
| step 換算 (`step × V`) を `provider/fl_engine.c`・`host/fl_mock.mjs` に入れ、diffs 0 を保つ (受入条件 3 の移管) | 未接続 | #3311 |
| V のアドレスを引数で渡す経路を含む、窓 0x40 の外・呼出しを跨ぐ間接書込み (`0xe863b7`・`0x130927c` の引数の呼出し元を含む。`mov` 以外の書込みも未追跡) | V の実行時値が 24 から変わる可能性 | #3311 (未追跡として追記) |
