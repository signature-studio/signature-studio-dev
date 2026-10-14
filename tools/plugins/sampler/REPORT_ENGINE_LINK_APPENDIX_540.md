# sampler REPORT_ENGINE_LINK 付録: #540 受入条件 4 の残り (a)(b)(c) の再解析

本書は `REPORT_ENGINE_LINK.md` §10 の分割移動 (250 行上限のため)。 本文は REPORT_ENGINE_LINK.md §10 の要約を参照。

- **§9 (a) の訂正**: §9 の「呼出し元 0 件」は誤り。 生バイトの `E8` 候補を命令境界で検証 (`call`/`jmp` の復号一致) すると、wrapper 0x846a80 (sel 2) の呼出し元は **9 件**、0x846ac0 (sel 4) は **8 件**。 線形走査 (`call` の即値) でも候補の一部 (例 0x843288 `call 0x843790`) を拾えていないため、呼出し元の列挙は命令境界の検証に基づくものだけを採る。
- 呼出し元と `edx` (= 内側 id、直線区間の最後の代入) の機械抽出結果 (逆アセンブル、分岐をまたぐ場合は誤りうる):

| wrapper | 呼出し元 | `edx` の書込み | 内側 id |
|--|--|--|--|
| 0x846a80 (sel 2) | 0x84422f | `xor edx, edx` | 0 |
| 0x846a80 (sel 2) | 0x84433f | `mov edx, 1` | 1 |
| 0x846a80 (sel 2) | 0x84435a | `mov edx, 2` | 2 |
| 0x846a80 (sel 2) | 0x844375 | `mov edx, 0xa` | 10 |
| 0x846a80 (sel 2) | 0x8443b0 | `mov edx, 0xb` | 11 |
| 0x846a80 (sel 2) | 0x8446b0 | `mov edx, 0xb` | 11 |
| 0x846a80 (sel 2) | 0x84b49e | `mov edx, 8` | 8 |
| 0x846a80 (sel 2) | 0x84571c | `mov edx, 0xe` (0x84570f) | 14 |
| 0x846a80 (sel 2) | 0x84bd8f | `movsxd rdx, esi` | **未確定** (esi の由来は未追跡) |
| 0x846ac0 (sel 4) | 0x843d39 | `xor edx, edx` | 0 |
| 0x846ac0 (sel 4) | 0x843dd2 | `mov edx, 1` | 1 |
| 0x846ac0 (sel 4) | 0x844ab6 | `mov edx, 3` | 3 |
| 0x846ac0 (sel 4) | 0x844ae0 | `mov edx, 7` | 7 |
| 0x846ac0 (sel 4) | 0x844b05 | `mov edx, 8` | 8 |
| 0x846ac0 (sel 4) | 0x8456b3 | `mov edx, 7` | 7 |
| 0x846ac0 (sel 4) | 0x847863 | `mov edx, 1` | 1 |
| 0x846ac0 (sel 4) | 0x847e56 | `mov edx, 0xa` (`esi` 由来の r8 も併用) | 10 |

- 注: 0x84433f・0x84435a・0x844375 の `mov edx, 1/2/0xa` は、それぞれ直後の `call` の直前にある。 0x8443b0 の `edx` は直線区間で最後の代入。 分岐を越えるケースは確認していない。
- 内側 id の値の範囲は 0〜14 にわたる。 sel 2 の内側 id 集合には 0, 1, 2, 8, 10, 11, 14 が出た。
- **(a) の結論**: sel 2・4 の呼出し元 17 件 (sel 2 が 9 件、sel 4 が 8 件) のうち 16 件で内側 id が確定。 未確定は 0x84bd8f (sel 2) の `esi` 由来 1 件のみ。
- **(a) の 1 件 (0x84bd8f) の追跡 (main c9500722 で測定、コード変更なし)**: 0x84bd8f は関数 0x84bc30〜0x84be5b (`.pdata` で解決) の内部で、`movsxd rdx, esi` の直後に `call 0x846a80` (sel 2 wrapper)。 `esi` は 0x84bc7d〜0x84bc86 で `rsi = |[rbx+0x18]|` (`rbx` = 関数 0x84bc30 の第 2 引数)。 0x84bca0〜0x84bcd6 の分岐で `esi` が 8 / 3 のとき 0xc に置き換わる。 よって内側 id は `|[rbx+0x18]|` と確定。 ただし `rbx` (= 第 2 引数) の値は、関数 0x84bc30 の参照が殻の `.text`・`.data` のどこにも見つからず未確定。 参照走査は E8 rel32 0 件、絶対 8 バイト VA 0 件、RVA 4 バイト 1 件 (0x52a858、`.pdata` の unwind 項目 = 関数自身の BeginAddress)。 このため 0x84bc30 の呼出し元は静的に特定できない (未確認: 実行時に計算された関数ポインタ経由の可能性)。
- **(b) の結論**: §9 の確定 (sel 10 の `r8` = 関数 0x843930 の第 2 引数の C 文字列コピー) は変更なし。 第 2 引数の書込み元は 0x843930 の呼出し元 5 件 (0x843b21・0x844cf5・0x846ca5・0x847029・0x847099) で、 `rdx` の由来は `[rbp+0x40]`・`[rbp+0x48]`・`[rbp+0x78]`・`[rbp+0x88]`・`[rax+0xa0]` と `esi` の混在。 文字列の内容の確定までは未了。
- **(c) の結論**: 未確定 (本 run で未着手。engine 側 `DispatchToEngine` 0x180147bc0 の sel 2 case (0x180147d38) は `[rcx+0x1b0]` の外部関数を呼ぶが、その戻り値の型と case 後の `rax` の扱いは未読解)。
- **受入条件 5 (本 run)**: runner に `wine` 無し (`which wine wine64` 不在) のため、VEX の SSE 固定の動的確認は実施不可。
- 受入条件 4 は引き続き **部分達成**。 未確定は (a) 0x84bd8f の 1 件、(b) 第 2 引数の文字列内容、(c) 戻り値型。

- 受入条件 5 (VEX の SSE 固定の動的確認): 本 run では **未着手**。 Windows 実行環境 (wine 等) は runner に無く、動的確認は未実施。

## 11. 受入条件 5 (VEX helper の SSE 固定) の静的判定 (#540 本 run)

- 測定 commit **`82e53552`** (解析ツール `vex_reach.py`・`vex_pin.py` の追加 commit)。 capstone + pefile による静的解析のみで、engine は実行していない。 各表示は 1 回の決定的な出力 (n=1)。 環境: 4 vCPU・RAM 15 GiB (`nproc`・`free -g`)。 素材 `fl-win64` 展開先 `$RUNNER_TEMP/fl-win64`。
- 固定の前提 (既存の lift 鎖): `tools/plugins/lift/passes/m11_simd2.py` の `CPUID_BODY` は cpuid(1) で SSE2 までを広告 (ecx = 0、OSXSAVE・AVX・FMA なし)、`xgetbv` は 0 を返す。 engine の経路 (`lift_ranges.sh`・`lift_from_ll.sh`) はこの pass を通る。
- 固定する値 (23664 の逆アセンブルで確認):
  - `0x180277ae4` (AVX 使用可否フラグ): 関数 `0x1801fcf98` (cpuid・xgetbv を含む) が cpuid(1).ecx の `0x18001000` (OSXSAVE・AVX・FMA) と xgetbv の `eax & 6 == 6` を判定して 1 / 0 を書く。 固定値 0 (`cmp [flag],0; jne` の `jne` を不採用)。
  - `0x18026e018` (ISA 段階): `cmp [.],3; jb` (0x1801e51a0) と `cmp [.],2; jl` (0x18018abdd) で読む。 `0x1801cd340` (cpuid を含む) が 3 を書く。 段階の意味 (AVX2 = 3) は MSVC CRT の慣例からの推定で未確認。 固定値 1 (SSE2 段階)。
- 解析ツール:
  - `vex_reach.py <block>`: 関数単位の辺 (直接 call/jmp、RIP 相対の関数参照、データ内の関数ポインタ) で、export とエントリポイントから到達する VEX 関数を数える。 `--list` で経路を出す。
  - `vex_pin.py <block> --pin=none|sse --indirect=none|stored|all [--list] [--dump-vex] [--probe=<hex,...> [--path]]`: 命令単位の CFG。 `--pin=sse` は上の 2 slot を固定して `cmp [slot],imm; jcc` を評価し不採用の辺を落とす。 switch のジャンプテーブル (`lea` 基底・`add`・`mov [基底+I*4+D]`) は飛び先を解く。 解けない間接 jmp は関数内の全命令へ、間接 call はデータ内の関数ポインタ全体 (`stored`) か全関数 (`all`) か無し (`none`) へ辺を張る。 `stored`・`all` は過大評価側。
- 実測 (`vex_guard.py` の基準値は §5 と同じ: 23664 の VEX 関数 229、23677 は 94):

| 解析 | block | 固定なし | SSE 固定 (`--pin=sse`) |
|---|---|---|---|
| `vex_reach` (関数単位、直接+RIP+データ内ポインタ) | 23664 | export+entry から到達 VEX 関数 6 (うち guard を経由しない 6) | (固定なし) |
| `vex_reach` | 23677 | 到達 0 (entry のみ root・94 関数中 94 が非到達) | (固定なし) |
| `vex_pin` `indirect=none` (直接辺のみ) | 23664 | VEX 関数 9 / VEX 命令 483 | **VEX 関数 1 / VEX 命令 8** (0x1801f1920) |
| `vex_pin` `indirect=none` | 23677 | 0 / 0 (entry のみ root) | 0 / 0 |
| `vex_pin` `indirect=stored` (過大評価) | 23664 | 120 / 14252 | 111 / 13638 |

- `vex_pin` (23664・固定なし・直接辺) で増えた 3 関数 (0x180001fc0・0x180009230・0x1800097d0) は、switch の飛び先を解いて初めて到達する。 `vex_reach` は switch を解かないため 6 件にとどまる。
- 固定で消えた VEX 関数 (解釈): 0x1801e5050 (VEX 68 命令) は `cmp [0x18026e018],3; jb` の AVX 段階側の区間。 0x1801f3270・0x180202fc0・0x1801f1920 の主要部は `cmp [0x180277ae4],0; jne` の飛び先が VEX 区間。 0x1801fd480・0x1801fd670 (VEX 21 ずつ) は呼出し元 4 関数 (0x1801f05e0・0x1801f0e70・0x1801f3270・0x1801f3ad0) の計 8 呼出しが全て非到達 (`--probe` 実測: 0x1801f0a1e・0x1801f0a30・0x1801f12da・0x1801f13d0・0x1801f35f5・0x1801f3800・0x1801f3f0f・0x1801f4015 が全て `reached=False`)。
- **固定しても残る VEX 8 命令** (0x1801f28a7〜0x1801f2f7a、関数 0x1801f1920): 経路は `0x1801f1940 jne` の非成立側 (SSE 側) → `0x1801f2ec8`〜`0x1801f2ed2 jne` → `vmovsd`・`vmovq` → `call 0x1801fcd30` → `jmp 0x1801f28a7` (AVX 区間の `vmovdqa`)。 `0x1801f2ed2` の条件は `0x18021fed0` と `0x18021ff00` の 2 語との AND 判定で、この 2 語は .data の初期値が `0x7FF0000000000000` (+inf) と `0x000FFFFFFFFFFFFF` (仮数マスク) で、CPU 機能ビットではない (書込みは mov 形式で見つからず、他の書込み形式は未確認)。 つまり **CPUID 固定の経路ではない** 値依存の分岐から、AVX 区間へ戻る。
- 未確定: (a) 間接 call (レジスタ・vtable 経由) の先。 `stored` の過大評価で 111 関数が残り、固定の効果はこの表からは判定できない。 (b) 23677 は export が無く entry のみを root にしたため、直接辺で VEX に届かない結論は root 不足の可能性がある。 (c) 固定後の 8 命令が lift 後に helper 実装済みか stub かは未確認 (`final.ll` の確認が要る)。
- 判定 (受入条件 5): **未達**。 SSE 固定 (CPUID 偽装) だけでは 23664 の VEX 命令 8 が残るため、「CPUID 分岐で SSE 路に固定できる」とは言えない。 残りは (1) 0x1801f1920 の 8 命令の扱い (helper 実装 or 値の到達不能の証明)、(2) 間接 call の到達性 (関数ポインタの dataflow)。 この問いは #527 の受入条件 3 と同一のため、起票先は #527 (重複起票しない)。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/plugins/sampler/vex_pin.py 23664 --pin=sse --indirect=none --list` (他の表も同じ引数の組み替え)。
