# REPORT_PY72 の付録 (#3214): PY-77 通知 0x550・0x562 の送信元と hwnd の由来 (PE 確定)

`REPORT_PY72.md` の「追加解析 (PY-77 / #3214)」節の全文を、250 行上限のため分割移動したもの (内容は無変更)。節の要約は `REPORT_PY72.md` に残す。

## 追加解析 (PY-77 / #3214): 通知 0x550・0x562 の送信元と hwnd の由来、N 既定値・一覧 A/B・0x525ec0 の確認

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #2576 (PY-77)。本 issue #3214 (PY-171) は受入 3 (通知の送信元と hwnd) を達成し、受入 1・2・4 を子へ移送した: #3267 (PY-177)・#3268 (PY-178)。

### 測定

- 測定 commit: `44235515` (`pe_scan_store.py` に dword/qword の指定を追加。コードを変えた最後の commit)。以降の commit は本節の REPORT だけ。`git diff 44235515 HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行。
- 展開: `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> extracted/block00031_PE.bin` (1.6 秒。`--wildcards` は使わない)。素材は `$ARTIFACTS_DIR` の実在を確認してから使った (`fl-win64.tar.zst` 2.3 GB)。展開先は repo 外。
- 実行: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_disasm.py <VA> <N>`・`pe_xref.py <VA>`・`pe_callgraph.py callers <VA>`・`pe_scan_store.py 0x2f4 dword` (30 hits・19.5 秒)。`pe_xref.py 0x1001b70,0xffe290` は instructions=5,022,467 hits=0 stores=0 (34.2 秒)。`pe_callgraph.py callers 0xffe290,0x1001b70` は直接 call 0 件。
- 補助 (repo 外の一時スクリプト): `.text` の即値 0x550・0x562・0x150・0x162 の走査 (capstone・IMM オペランド)、`.data` の 8 バイト絶対ポインタ走査 (`.data` 内の .text を指す値 12,894 件)。

### 結論 (PE 実測で確定した範囲)

#### 1. 通知 0x550・0x562 の送信元と hwnd の由来 (受入 3 の本体)

| 項目 | PE 実測 |
|---|---|
| 0x550 の送信 | 単位 2 (`0xd5a958`〜): `[chan+0x2f4] = clamp(…)` (`0xd5a97c`) → `0x117baa0(chan)` の戻り値を rbx (`0xd5a982`)。rbx≠0 かつ `0x40fe90(rbx, [0xf55e80])`≠0 のとき `0x617920(rbx)` の戻り値を hwnd にする (`0xd5a9a5`・`0xd5a9aa`)。`mov edx,0x550` (`0xd5a9ad`)・`r8 = movsxd [chan+0x794]` (`0xd5a9b6`)・`r9 = 0`・`call 0x425210` (`0xd5a9c0`) |
| 0x562 の送信 | task 生成 `0xd843d0` の中 (`0xd84486`〜`0xd844a3`): `obj = *(*(0x15e0ff8))` → `0x617920(obj)` → `mov edx,0x562`・`r8 = r9 = 0`・`call 0x425210` |
| 送信の実体 | `0x425210` は `jmp [0x1970b10]` (`.idata` の IAT。pefile の import 表で `user32.dll!PostMessageW`)。引数はそのまま PostMessageW(hwnd, msg, wParam, lParam) に渡る |
| hwnd の由来 | `0x617920(obj)` = `0x6178e0(obj)` のあと `return [obj+0x45c]`。`0x6178e0` は `[obj+0x45c]==0` なら、親 `[obj+0x78]` があればそれを先に処理し、`call [vtbl(obj)+0x1d0]` を呼ぶ (window 生成とみられる仮想呼出し。`+0x1d0` の実装は未読)。hwnd は `obj+0x45c` の qword |
| obj の由来 | 0x550: `0x117baa0(chan)` (分岐の一部だけ読了)。0x562: 大域 `*(*(0x15e0ff8))` |

- 受け手 (WndProc の分岐先): **未確定**。理由: (a) 即値走査 (`cmp`・`sub`・`add`・`mov`・`lea`) で、msg の即値 0x550・0x562 を持つ受け手の比較は無い。0x550 は `0xd5a9ad` (送信)・`add r12,0x550` (`0x5ebb81`)・`add rdx,0x550` (`0x5ebd5e`)・`sub rsp,0x550` (`0xd18133`) の 4 件で、受け手の分岐ではない。0x562 は `0xd84498` (送信) の 1 件だけ。(b) WM_USER 相対 (0x150・0x162) の比較も無い (`0x632c99` は `0x425390` の引数、`0x1040d41` は範囲の clamp)。(c) WndProc は window クラスの `lpfnWndProc` (RegisterClassEx) か `+0x1d0` の生成先で決まるが、本 run では未読。次段は未解決表に書く (子は作らない)。

#### 2. N 既定値 (受入 1 の一部。子 #3267)

- N (`[obj+0x2f4]`) の既定値 2 の書込みは `0xfe948d` `mov dword ptr [rcx+0x2f4], 2`。関数 `0xfe9090` (object の初期化) の中で、直前の `0xfe9486` `mov qword ptr [rcx+0x6f4], rax` (`rax = 0x3ff0000000000000` = 1.0 double。`0xfe9478`) と並ぶ。`0xfe9090` の object は引数 rcx で、`[rbp+0x20]` に保存される (`0xfe9099`)。
- `.text` の dword 書込み走査 (`pe_scan_store.py 0x2f4 dword`): 30 件。`mov dword ptr [rcx+0x2f4], 2` は `0xfe948d` の 1 件だけ。他は `eax`・`ecx` の値、`add … , 1`、`0` (別構造体・スタック)、`0x434c0000`・`0x437f0000` (float 定数の別構造体への書込み。対象の型は未確定)。単位 2 の書込みは `0xd5a97c` (`eax`)。
- `0xfe9090` の直接 call 元は 2 件: `0xffe29b` (関数 `0xffe290`: `rbx=rcx` の後に呼び、`byte [rbx+0x79d]=0`) と `0x1001b7b` (関数 `0x1001b70`: 呼出し後に `dword [rbx+0x2f0]=-1`)。
- 上の 2 関数の呼出し経路は **未確定**。`pe_callgraph.py callers` の直接 call 0 件、`pe_xref.py` の RIP 相対参照 0 件、`.data` の 8 バイト絶対ポインタ 0 件。`.data` には .text を指す絶対ポインタが 12,894 件あり vtable は存在するので、この 2 関数だけが静的に載っていない。動的に決まる呼出し (関数ポインタの格納元・動的 vtable) と推定する。よって「reset が chan に呼ばれるか」と「呼ばれない場合の N 既定値の適用元」は本 run では確定しない。

#### 3. 一覧 A/B の要素型 (受入 2 の一部。子 #3267)

- 一覧 A の大域 slot = `0x15e2218` (`0x100573e`・`dl≠0`)、一覧 B = `0x15e0128` (`0x1005779`・`dl=0`)。slot の値 P の指す値 Q (`*(*slot)`) が容器 (`0x100575e`〜`0x10057a8`)。
- `0xfe8bb0(Q, idx)` (`0xfe8bb0`〜`0xfe8bd5`): `0 ≤ idx ≤ dword [Q+0x10] − 1` のとき `qword [[Q+8] + idx*8]`、範囲外・負値は 0。よって要素は 8 バイトのポインタ `T*` である。
- T の構造体型名は未確定。callback は `[chan+0x794]`・`[chan+0x2f4]` を読む (`0xd5a9b6`・`0xd5a97c`) ので、T は chan と整合する。ただし Q への要素追加・件数更新の箇所は本 run で列挙していない。

#### 4. 0x525ec0 の比較対象 (受入 4 の一部。子 #3268)

- 比較 (`0x525f42`〜`0x525f4e`): `rcx = *(0x15e4f18)` (RIP 相対 load)、`eax = dword [X+8]` (X = `0x525940()`)、`cmp eax, dword [rcx]`。
- X: `0x525940` は `*(0x41d110() + 0x238)` を返す (未生成なら `0x522710` で作る)。`0x41d110` は `mov rax, gs:[0x58]` で TLS 配列から引くので、スレッドごとに異なる値。
- 同期の条件: `eax == dword [*(0x15e4f18)]` (同じスレッド) かつ `(r8b & r9b) == 0` (`0x525f58`・`0x525f5e`) のとき、`[task+8]≠0` なら `call [task+8]` (rcx=`[task+0x10]`)、そうでなければ `[task+0x18]` を使う (`0x525f60`〜`0x525faa`)。それ以外は `0x525faf` 以降の待ち行列経路へ (後段は未読)。
- 比較対象の初期化元は **未確定**。`0x15e4f18` は RIP 相対で 23 件すべて load (`mov rcx,[rip+..]`)、直接 store は 0 件。レジスタ経由の store は本 run では追っていない。

### 受入条件の判定 (#3214 の本文は受入 3 だけに縮めた)

- [x] 受入 3: hwnd の由来を確定 (`0x617920` → `[obj+0x45c]`・`0x6178e0` の生成経路)。受け手の分岐先は未確定で、理由は 1 に記載。「確定できない場合は理由を書く」を満たす。
- 移送 (旧 受入 1): N 既定値の書込み箇所 (`0xfe948d`) は確定。reset が chan に呼ばれるかは未確定 → #3267。
- 移送 (旧 受入 2): 容器と要素ポインタ (`0xfe8bb0`) は確定。T の型名は未確定 → #3267。
- 移送 (旧 受入 4): 同期条件は確定。比較対象の初期化元は未確定 → #3268。
