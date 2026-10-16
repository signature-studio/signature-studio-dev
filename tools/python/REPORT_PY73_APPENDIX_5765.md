# REPORT_PY73_APPENDIX_5765 — PY-5386 (#5765): 0x12cab20 の間接 call 閉包と書込み先 (部分)

親 #5049 の子 #5765。親の付録: `REPORT_PY73_APPENDIX_3649.md` §8 (本付録へ移動)。

再現: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_closure_writes_5386.py 0x12cab20 3` (測定 commit `948c60093`。展開は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block00031_PE.bin'`)。

### 8-1 解決方法 (決定)

- 間接 call は**静的に解決しない**。閉包は直接 call (E8) だけで辿り、間接 call の箇所は未解決の枝として数えて列挙する。
- 理由: 閉包内の間接 call 139 件のうち `mem` (`call qword ptr [...]`) は 138 件、`reg` は 1 件 (`0x12dfa06` の `call rsi`)。`mem` のうち `[rip+disp]` は 9 件 (例: `0x40941e`・`0x411e47`)、残りは `[reg+disp]` (仮想呼出し)。`[reg+disp]` の呼出し先は受け手オブジェクトの class (vtable) で決まり、PE だけでは確定しない。`[rip+disp]` の 9 件は PE 内の初期値しか読めず、実行時の登録先は未確定。
- よって閉包の書込み集合は**下限**であり、「閉包の副作用の完全列挙」とは書かない。

### 8-2 閉包の実測 (`pe_closure_writes_5386.py`)

| 項目 | 実測 |
|---|---|
| 閉包関数数 (深さ ≤ 3) | 155 (親 #5049 の `pe_callgraph.py fwd` と一致) |
| 間接 call 箇所 | 139 (`mem` 138・`reg` 1。親の計測と一致) |
| 閉包内の `[rip+disp]` 書込み (誤逆アセンブル 2 件を除く) | 21 |
| 閉包内の `[rbp/rsp+disp]` 書込み (関数ローカル) | 724 (副作用ではない) |
| 閉包内の `[reg+disp]` 書込み (先が静的に未確定) | 547 |

- 誤逆アセンブル 2 件 (`0x104cf5f`・`0x12cb4a2`) は、`ret` の後の 0 埋め領域を命令として読んだもの。`0x12cb4a2` の書込み先 `0x12cb7ab` は `.text` 内。両方を除外した。
- 実行: 測定 commit `948c60093`・実測 83.4 秒・real・user 82.4 秒 (load 0.52・並列 1)。コード差分 0 の証跡は §6 と同じ手順 (`git diff 948c60093 HEAD -- tools/python/analysis` の出力は 0 行)。

### 8-3 `[rip+disp]` 書込み 21 件 (閉包内)

`0x12cab20` 自身が書く 9 件 (親 #5049 のコメントの 9 件と一致):

| 書込み先 VA | 書込み箇所 (所属関数 `0x12cab20`) | 命令 |
|---|---|---|
| `0x15d4f28` | `0x12cb16d` | `mov byte ptr [rip+0x309db4], 1` |
| `0x15d4f29` | `0x12cb234` | `mov qword ptr [rip+0x309cee], rax` |
| `0x15d4f31` | `0x12cab74` | `mov byte ptr [rip+0x30a3b6], 0` |
| `0x15d4f31` | `0x12cac71` | `mov byte ptr [rip+0x30a2b9], 1` |
| `0x15d4f34` | `0x12cac7e` | `mov dword ptr [rip+0x30a2b0], eax` |
| `0x193fc68` | `0x12cb1ea` | `mov dword ptr [rip+0x674a74], 0xffffffff` |
| `0x193fc6c` | `0x12cb1f4` | `mov dword ptr [rip+0x674a6e], 0x80000001` |
| `0x193fc88` | `0x12cab4a` | `mov byte ptr [rip+0x675137], 1` |
| `0x193fc88` | `0x12cb259` | `mov byte ptr [rip+0x674a28], 0` |

閉包内の子 (`0x12cb2e0`・`0x12de9d0`・`0x12de9e0`・`0x12dfa30`・`0x12e2ff0`・`0x412a60`・`0x11d54f0`) が書く 12 件:

| 書込み先 VA | 書込み箇所 (所属関数) |
|---|---|
| `0x15d4f31` | `0x12cb2f3` (`0x12cb2e0`) |
| `0x193fc88` | `0x12cb491` (`0x12cb2e0`) |
| `0x13a5008` | `0x412a6c` (`0x412a60`) |
| `0x16bc9f4` | `0x11d54fc` (`0x11d54f0`) |
| `0x196eb20`・`0x196eb24` | `0x12de9d0` (`0x12de9d0` 内の `0x12de9d0`・`0x12de9d6` の 2 箇所) |
| `0x196eb28`・`0x196eb2c` | `0x12de9e0`・`0x12de9e6` (`0x12de9e0`) |
| `0x196eb40` | `0x12dfa38` (`0x12dfa30`) |
| `0x196eb70`・`0x196eb78`・`0x196eb80` | `0x12e3011`・`0x12e3034`・`0x12e3055` (`0x12e2ff0`) |

### 8-4 受入条件 (#5765) の判定

- [x] 間接 call の解決方法を決めた (§8-1: 静的に解決せず、未解決の枝として列挙)
- [ ] 閉包内の書込み先を全件列挙する → **未達**。`[rip+disp]` の 21 件は列挙したが、`[reg+disp]` の 547 件は書込み先が静的に未確定。間接 call 139 件の先も未確定のため、閉包の下限しか示していない

### 8-5 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 call 139 件 (`mem` 138・`reg` 1) の呼出し先 | 閉包の書込み集合が下限 | #5765 (継続) |
| `[reg+disp]` 書込み 547 件 (閉包全体) の書込み先 | 同上。`0x12cab20` 自身の `[reg+disp]` 書込みは未分類 | #5765 (継続) |
