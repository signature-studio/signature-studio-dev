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

- 測定 commit **`557cc1d9`** (`vex_pin.py` の switch 上限の修正 commit。 解析ツールの追加は `82e53552`、修正前の判定は `019c24df`)。 capstone + pefile による静的解析のみで、engine は実行していない。 各表示は 1 回の決定的な出力 (n=1)。 環境: 4 vCPU・RAM 15 GiB (`nproc`・`free -g`)。 素材 `fl-win64` 展開先 `$RUNNER_TEMP/fl-win64`。
- 固定の前提 (既存の lift 鎖): `tools/plugins/lift/passes/m11_simd2.py` の `CPUID_BODY` は cpuid(1) で SSE2 までを広告 (ecx = 0、OSXSAVE・AVX・FMA なし)、`xgetbv` は 0 を返す。 engine の経路 (`lift_ranges.sh`・`lift_from_ll.sh`) はこの pass を通る。
- 固定する値 (23664 の逆アセンブルで確認):
  - `0x180277ae4` (AVX 使用可否フラグ): 関数 `0x1801fcf98` (cpuid・xgetbv を含む) が cpuid(1).ecx の `0x18001000` (OSXSAVE・AVX・FMA) と xgetbv の `eax & 6 == 6` を判定して 1 / 0 を書く。 固定値 0 (`cmp [flag],0; jne` の `jne` を不採用)。
  - `0x18026e018` (ISA 段階): `cmp [.],3; jb` (0x1801e51a0) と `cmp [.],2; jl` (0x18018abdd) で読む。 `0x1801cd340` (cpuid を含む) が 3 を書く。 段階の意味 (AVX2 = 3) は MSVC CRT の慣例からの推定で未確認。 固定値 1 (SSE2 段階)。 感度は下の表の注を参照。
- 解析ツール:
  - `vex_reach.py <block>`: 関数単位の辺 (直接 call/jmp、RIP 相対の関数参照、データ内の関数ポインタ) で、export とエントリポイントから到達する VEX 関数を数える。 `--list` で経路を出す。 末尾の `[upper: +stored fn ptrs]` 行は、データ内の関数ポインタも root に足した上限版 (guard 除外)。
  - `vex_pin.py <block> --pin=none|sse --indirect=none|stored|all [--flag=0|1] [--level=N] [--list] [--dump-vex] [--probe=<hex,...> [--path]]`: 命令単位の CFG。 `--pin=sse` は 2 slot を固定して `cmp [slot],imm; jcc` を評価し不採用の辺を落とす (既定 `--flag=0`・`--level=1`)。 switch のジャンプテーブル (`lea` 基底・`add`・`mov [基底+I*4+D]`) は飛び先を解く。 上限は表の添字 I と同じレジスタへの `cmp I, N` からだけ取る。 上限が取れない表は、飛び先が関数 [lo,hi) に入る間だけ読む。 解けない間接 jmp は関数内の全命令へ、間接 call はデータ内の関数ポインタ全体 (`stored`) か全関数 (`all`) か無し (`none`) へ辺を張る。 `stored`・`all` は過大評価側。
- 実測 (`vex_guard.py` の基準値は §5 と同じ: 23664 の VEX 関数 229、23677 は 94):

| 解析 | block | 固定なし | SSE 固定 (`--pin=sse`) |
|---|---|---|---|
| `vex_reach` (関数単位、直接+RIP+データ内ポインタ) | 23664 | export+entry から到達 VEX 関数 6 (うち guard を経由しない 6) | (固定なし) |
| `vex_reach` | 23677 | 到達 0 (entry のみ root・94 関数中 94 が非到達) | (固定なし) |
| `vex_reach` 上限版 (データ内の関数ポインタも root・guard 除外) | 23664 / 23677 | VEX 関数 95 / 45 | (固定なし) |
| `vex_pin` `indirect=none` (直接辺のみ) | 23664 | VEX 関数 6 / VEX 命令 427 | **VEX 関数 1 / VEX 命令 8** (0x1801f1920) |
| `vex_pin` `indirect=none` | 23677 | 0 / 0 (entry のみ root) | 0 / 0 |
| `vex_pin` `indirect=stored` (過大評価) | 23664 | 120 / 14252 | 111 / 13638 |

- 修正前 (`82e53552`) の `vex_pin` (23664・固定なし・直接辺) は 9 関数 / 483 命令だった。 増えた 3 関数 (0x180001fc0・0x180009230・0x1800097d0) は、0x1801e52c2・0x1801e53f2 (関数 0x1801e5050 の switch) の偽の飛び先 (0x17fffffff・0x180001fc0 など、表の外) からの到達だった。 この表の添字は `r11` (`shr 5` 後) で、`cmp r8, 0x100` は添字の上限ではない。 修正後は上限が取れないため飛び先を関数 [lo,hi) に限って読み、 `vex_reach` と一致する 6 関数 / 427 命令になった。 `--pin=sse` は 1 / 8 のまま変わらない。
- 固定値の感度 (23664・`--pin=sse --indirect=none`): `--level=0`・`--level=2` は 1 関数 / 8 命令 (`--level=1` と同じ)。 `--level=3` は 2 関数 / 76 命令。 `--flag=1 --level=1` は 5 関数 / 359 命令。
- ネガティブコントロール (WORKFLOW §5): `--pin=sse --flag=1 --level=3` (AVX 側の値を固定) は 6 関数 / 427 命令 (固定なしと同じ) に戻る。 固定の効果が測れていることの確認。
- 上限版の `vex_reach` (`[upper]`) の結果: 23664 は 95 VEX 関数、23677 は 45 VEX 関数 (guard 除外)。 23677 の表の「到達 0」は下限 (entry のみ root・直接辺) である。
- 残る不正確さ: 一部の表 (例: 0x1801544c8 の byte 添字の表) は上限 cmp が表の実サイズより大きいため範囲外の値も読む。 そこから得た辺は過大評価側に寄与しうる。 本測定の VEX 集計への影響は未確認。
- 固定で消えた VEX 関数 (解釈): 0x1801e5050 (VEX 68 命令) は `cmp [0x18026e018],3; jb` の AVX 段階側の区間。 0x1801f3270・0x180202fc0・0x1801f1920 の主要部は `cmp [0x180277ae4],0; jne` の飛び先が VEX 区間。 0x1801fd480・0x1801fd670 (VEX 21 ずつ) は呼出し元 4 関数 (0x1801f05e0・0x1801f0e70・0x1801f3270・0x1801f3ad0) の計 8 呼出しが全て非到達 (`--probe` 実測: 0x1801f0a1e・0x1801f0a30・0x1801f12da・0x1801f13d0・0x1801f35f5・0x1801f3800・0x1801f3f0f・0x1801f4015 が全て `reached=False`)。
- **固定しても残る VEX 8 命令** (0x1801f28a7〜0x1801f2f7a、関数 0x1801f1920): 経路は `0x1801f1940 jne` の非成立側 (SSE 側) → `0x1801f2ec8`〜`0x1801f2ed2 jne` → `vmovsd`・`vmovq` → `call 0x1801fcd30` → `jmp 0x1801f28a7` (AVX 区間の `vmovdqa`)。 `0x1801f2ed2` の条件は `0x18021fed0` と `0x18021ff00` の 2 語との AND 判定で、この 2 語は .data の初期値が `0x7FF0000000000000` (+inf) と `0x000FFFFFFFFFFFFF` (仮数マスク) で、CPU 機能ビットではない (書込みは mov 形式で見つからず、他の書込み形式は未確認)。 つまり **CPUID 固定の経路ではない** 値依存の分岐から、AVX 区間へ戻る。
- 未確定: (a) 間接 call (レジスタ・vtable 経由) の先。 `stored` の過大評価で 111 関数が残り、固定の効果はこの表からは判定できない。 (b) 23677 は export が無く entry のみを root にしたため、直接辺で VEX に届かない結論は root 不足の可能性がある。 (c) 固定後の 8 命令が lift 後に helper 実装済みか stub かは未確認 (`final.ll` の確認が要る)。
- 判定 (受入条件 5): **未達**。 SSE 固定 (CPUID 偽装) だけでは 23664 の VEX 命令 8 が残るため、「CPUID 分岐で SSE 路に固定できる」とは言えない。 残りは (1) 0x1801f1920 の 8 命令の扱い (helper 実装 or 値の到達不能の証明)、(2) 間接 call の到達性 (関数ポインタの dataflow)。 この問いは AC3 の実装と同一のため、起票先は #779 (AC3 の実装は PM 承認 (#527 コメント 2026-10-13T18:59Z) で #779 へ移管済み。 #534 は CLOSED)。 #527 は参照として残す。
- 再現 (commit `557cc1d9`): `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/plugins/sampler/vex_pin.py 23664 --pin=none --indirect=none` と `--pin=sse --indirect=none --list` (他の表と感度・ネガコンは `--indirect`・`--flag`・`--level` を組み替える)。 `vex_reach.py 23664` の末尾行が上限版。

## 12. 受入条件 5 の残り: 固定後の VEX 8 命令の経路 (#540 本 run)

- 測定 commit **`4d16053d`** (`vex_nan_branch.py` の修正 commit。 追加は `1c055ac6`)。 capstone + pefile による静的解析のみ、n=1。 環境は §11 と同じ (4 vCPU・15 GiB)。 素材 `fl-win64` は `$RUNNER_TEMP/fl-win64` に展開 (`extracted/block23664_PE.bin`)。
- 分岐 `0x1801f2ed2` (`jne`) は CPUID 旗ではなく、倍精度の NaN 判定である。 直前 7 命令は `r10 = [0x18021fed0] & r8`、`rax = (r10 == [0x18021fed0]) ? r8 : 0`、`r10 = [0x18021ff00] & rax`、`jne` (`r10 != 0`)。 定数は X = `0x7ff0000000000000` (指数部全 1)、Y = `0x000fffffffffffff` (仮数マスク)。 両方とも `.rdata` (PE の節属性で書込み不可) にあり、`.text` からの書込みは 0 件。 taken (`0x1801f2f30`) は r8 が NaN のとき、fall-through (`0x1801f2ed4`) は NaN でないとき。
- **両辺とも VEX 命令を含む**: fall-through は直線区間 6 命令のうち VEX 3 件 (`0x1801f2ed4` vmovsd・`0x1801f2eda` vmovsd・`0x1801f2ee0` vmovq) で `0x1801f2ef1` の jmp まで。 taken は直線区間 19 命令のうち VEX 3 件 (`0x1801f2f6e`・`0x1801f2f74`・`0x1801f2f7a`) で `0x1801f2f8b` まで。 よって `0x1801f2eb0` に到達すれば、r8 の値に依らず VEX 命令が実行される。
- 固定の再測定 (`vex_pin.py 23664 --pin=sse --indirect=none --probe=0x1801f2ed4,0x1801f2f30,0x1801f2ec8 --path`): VEX 命令 8 / 関数 1 (§11 と同値)。 3 点とも `reached=True`。
- 経路上の分岐 (`0x1801f1920` から `0x1801f2eb0` まで): `0x1801f1939 cmp dword [0x180277ae4], 0; jne` は AVX 旗 (CPUID 由来) で、§11 の SSE 固定で外れる。 後続の `0x1801f1970 je`・`0x1801f20ec je`・`0x1801f20f5 je` は r8・r9 などの値に依存し、CPUID 固定の対象ではない。 `vex_pin` はこれらの両辺を残すため、8 命令の到達は上限評価 (値依存の到達性は未確定)。
- ネガコン (`vex_nan_branch.py`): `--ctrl=0x180277ae4` (CPUID 旗、`.data`) は `.text` から書込み 1 件 (書込み検出が働くことの確認)。 `--branch=0x1801f2ec8` (分岐でない) は形の検査で NG かつ exit 1。
- **判定 (受入条件 5)**: 「CPUID 分岐で SSE 路に固定できるか」は**不成立**。 probe が示した経路上の CPUID 旗の分岐は `0x1801f1939` の 1 箇所だけで、固定すると外れる。 残る VEX 8 命令は値依存の分岐の両辺にあり、固定では除外できない。 残りの問いは (i) 関数 `0x1801f1920` の入力 r8 等の値域 (呼出し元 `0x18014b4a4` の鎖の解析)、(ii) 8 命令の helper 実装 (#779)。 動的確認 (wine 等) は未実施。
- 再現: `python3 tools/plugins/sampler/vex_nan_branch.py "$RUNNER_TEMP/fl-win64/extracted/block23664_PE.bin"` (実測 3.0 s、exit 0)。 `vex_pin.py` の再現は §11 と同じ。
- 鮮度の証跡 (測定 commit `4d16053d` から HEAD まで、コード差分): `git diff 4d16053d HEAD -- tools/plugins/sampler ':!*.md'` の出力は 0 行 (確認時 HEAD `383efaa1`。 変更は REPORT 2 ファイル・DOC_MAP の md のみ)。
