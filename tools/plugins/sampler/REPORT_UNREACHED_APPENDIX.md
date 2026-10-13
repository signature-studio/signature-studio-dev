# tools/plugins/sampler/REPORT_UNREACHED_APPENDIX.md — REPORT_UNREACHED.md の付録 (分割移動)

> **正本**: `tools/plugins/sampler/REPORT_UNREACHED.md`。 本書は 250 行上限のため、同 REPORT から無変更で分割移動した節の全文。 節番号は REPORT_UNREACHED.md に合わせる。

## A. §2d-7 の旧 NC 表 (改訂前 b36fef5 系の実測)

NC の改訂後の全結果は REPORT_UNREACHED.md §2f の検証表。 本表は改訂前 (b36fef5 系) の実測で、NC2 の `rc 0 ✗` は §2f の U6 で解消した。

| NC | 壊した入力 | 期待 | 実測 |
|---|---|---|---|
| 対照 | `closure_unreached.py` (無改変) | rc 0 | **rc 0** ✓ |
| NC1 | BFS の seed から (a) RVA32 の根を外す | U2 FAIL | **rc 1 (U2)** ✓ |
| NC2 | BFS の辺から命令内即値を外す (即値辺を含む閉包 `make_edge3` の即値項を外す) | U6 FAIL | **rc 1 (U6)** ✓。 実データ (即値辺 0 件) では識別できないため、U6 (合成入力) で示す (§2f)。 別案の合成入力 NC2a / NC2b は §B |
| NC2 (別案) | 合成入力 `nc2_imm_synth.py` で BFS から即値辺を外す (NC2b) | U2 FAIL | **rc 1 ✓** (§B。 対照 NC2a は rc 0 ✓) |
| NC3 | 排他分類の (c) に (a) を二重計上 | U4 FAIL | **rc 1 (U4)** ✓ |
| NC4 | capstone 側の RVA32 集合に偽の値 0x7fffff01 を注入 | U1 FAIL | **rc 1 (U1)** ✓ |
| NC5 対照 | `judge.py shells` (無改変 status_run.csv) | rc 0 | **rc 0** ✓ |
| NC5 | FL Keys の行に emcc_c_rc=1 | judge FAIL | **rc 1** ✓ |
| NC6 対照 | `unr_e2e.sh --skip-lift` (無改変) | rc 0・OK あり | **rc 1 ✗** (range 欠落監査 FAIL のため。 実データの不合格を正しく検出している) |
| NC6 | 同 + emcc_c_rc=1 の行を追記 | rc ≠ 0・OK 無し | **rc ≠ 0・OK 無し** ✓ |

NC 実行後、`status_run.csv` は元の 8 行 (header + 7) に復元した。

## B. §2g #879 別案: NC2 (即値辺の除去) の合成入力による識別力

**結論 (先出し)**: 実データは即値辺が 0 件のため、NC2 は実データでは識別しない。 即値辺を持つ合成入力 (`nc2_imm_synth.py`) で識別力を示し、NC2 の合成検査 (NC2a / NC2b) を別案として併記した。 即値検査の識別力は、即値参照を持つ実データが出るまで実データ上では未確認のまま (即値辺の件数は REPORT_UNREACHED.md §2f の 7 本とも 0 件)。

**合成入力 (`sampler/nc2_imm_synth.py`)**: 関数 4 件 (E `0x1200` = total2、R `0x1000` = RVA32 表から載る根、F `0x1100`・G `0x1300` = outside)。 R は `mov eax, 0x1100` (imm_rva) と `mov rcx, 0x140001300` (imm_va) を持つ。 即値辺は va 1 / rva 1。

| 入力 | 期待 | 実測 |
|---|---|---|
| NC2a 対照 (即値辺を BFS に含める) | U2 PASS、rc 0 | **rc 0**、total3 = 0x1000, 0x1100, 0x1200, 0x1300、漏れ 0・根の漏れ 0 |
| NC2b BFS から即値辺を外す (`--drop-imm-bfs`) | U2 FAIL、rc 1 | **rc 1**、total3 = 0x1000, 0x1200、漏れ 2・根の漏れ 0 |

**限界 (明記)**: 合成検査は `closure_unreached.py` の BFS と U2 の式を `nc2_imm_synth.py` に複製している。 実物の `main()` への変異ではない。 `imm_capstone` だけは実物を呼ぶ。 実データでの即値辺の識別は未確認。

**検証 (commit `07894a58` を含む worktree、`unr_nega.sh`)**: rc 0、`[unr_nega] OK: 全ネガコンが期待通り`。 NC0〜NC8 (NC2a・NC2b を含む) すべて期待どおり。 `unr_e2e.sh` は前提生成込みで rc 0 (real 10 min 59 s、17:48:14 → 17:59:13 UTC)。 終了後の `uptime` は load average 1 分 0.21・5 分 3.64 (4 core)。 `count_imm_edges.py` は `work/` の生成物 (gitignore) で commit していない。
