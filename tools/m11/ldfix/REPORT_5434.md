# REPORT #5434 — spill 宛 `128f9e0` の 12 site: 欠落区間の pass 特定と到達性 (LD-269)

既知類型との関係: DEFECTS.md の D19 (生 lift で欠落) に近い。ただし本件は lift 段ではなく RetDec 内の LLVM pass (Jump Threading) が枝を付け替えた結果と確定した (§2)。

親: #4959 (LD-246)。前提: #2705 (merged・欠落区間の特定)。判定は UNDETERMINED のまま (§4)。

## 1. 測定条件

- 測定 commit: `7e861de2d` (コードを変えた最後の commit。`8439f2a58` で `ld269_pass_trace.py`・`ld269_reach.py` と結果 TSV を追加、`7e861de2d` で `ld269_reach.py` に gap 到達数を追加)。作業 worktree `ws-5434` (branch `5434-ld269-128f9e0-gap`、起点 `origin/main` = `11ebc423b`)。
- 素材: `work-m11`・`work-liftdiff` を `tar --zstd -xf` で展開 (gitignore 対象の `tools/m11/work/`・`tools/liftdiff/work/`)。`toolchain-retdec` を repo 外の作業先へ展開し、RetDec ([RETDEC]) を使用。`fl-win64` から PE `block00031_PE.bin` (`[WIN64]`) のみ展開。
- 実行 (すべて foreground):
  - `python3 tools/m11/ldfix/ld125_lift_gap.py` → rc=0。出力は commit 済みの `ld125_lift_gap_128f9e0.tsv` と差分なし。
  - RetDec 1 関数実行 (`--select-ranges "0x128f9e0-0x1294ab8" --select-decode-only --print-after-all`) → rc=0・real 20.7 s。stderr は `tools/m11/work/pa/stderr.log` (gitignore)。
  - `python3 tools/m11/ldfix/ld269_pass_trace.py` → `results/ld269_pass_trace_128f9e0.tsv`。
  - `python3 tools/m11/ldfix/ld269_reach.py` → `results/ld269_reach_128f9e0.tsv` (`boot3.drc.dsm` を入力)。
  - `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` → rc=0・real 2m11.0s・load average 0.94 (実行後 uptime)。ログの `[spill178 (修復後 IR)] results/spill178_1161.tsv と一致` を確認。
- 判定 (`candidate_verdicts_1161.jsonl`) は変更していない (§4)。

## 2. 機構 (受入 2): RetDec の Jump Threading が欠落を起こした

RetDec の pass ごとの dump (`--print-after-all`・1 関数で 155 dump) で、label `dec_label_pc_1290645` と dispatch の `switch i32 7` の有無を追った (`ld269_pass_trace.py`)。

| dump | pass | label `1290645` | `switch i32 7` |
|---|---|---|---|
| 0 | After Input binary to LLVM IR decoding | あり | なし |
| 66 | After Global Value Numbering | あり | あり |
| 68 | After Combine redundant instructions | あり | あり |
| 69 | **After Jump Threading** | **なし** | なし |

(dump 番号は 0 始まり。`results/ld269_pass_trace_128f9e0.tsv` の変化点と一致する。)

- dump 68 → 69 で、`je 0x1290645` (`0x12905da`) と `jmp 0x1290645` (`0x129060e`) の宛先が `dec_label_pc_129460b` へ書き換えられ、`dec_label_pc_1290645` の block 全体が消える。これが lift IR (`boot3.lift.ll`) の欠落の直接の原因。
- 前段の `boot3.drc.ll` (RetDec の最終出力) で既に欠落しているので、repo 側の `ir_normalize.py` (norm0)・`ir5_patch.py` (lift) の処理ではない。
- GVN (dump 66) で、`0x1290680` の dispatch が `switch i32 7` に畳まれている。dispatch の値は `0x1290591` の `mov dword ptr [rip+0x340f4d], 7` の定数で、同じ global (`0x15d14e8`) を `0x1290680` が読む。Jump Threading はこの定数に基づいて、`0x1290645` を経由する枝を直接 `0x129460b` へ付け替えた。

## 3. 到達性: 12 site は値 7 の経路上にない (`ld269_reach.py`)

機械語 (`boot3.drc.dsm`・函数 3681 命令) の CFG を入口 `0x128f9e0` から辿った。

| 観点 | 結果 |
|---|---|
| 間接分岐 | 本関数に無し (確認後に BFS を実行) |
| 欠落区間 `1290645`〜`129460b` (3033 命令) への外部からの分岐・call | 0 件 |
| 通常の CFG で入口から 12 site へ到達 | 12/12 到達 (全 3681 命令が到達可能) |
| dispatch の値を 7 に固定 (`0x129068b`・`0x1290692`・`0x129069d` の辺を値 7 の経路だけに絞る) | **12 site すべて未到達**・到達は 672/3681 命令 |
| 欠落区間の到達命令 | 24/3033 (`1290610`〜`1290644` の枝経路。12 site は含まない) |
| 支配: store `0x1290591` を除くと dispatch load `0x1290680` に届くか | 届かない (store が dispatch を支配する → 固定 7 の前提が成り立つ) |

- つまり、この関数の 12 site (`stack_var_-760〜-1336` の store・load・`cmp [rbp+d],0`) は、値 7 の dispatch で通常の実行経路から外れている。欠落区間は「RetDec が落とした生きたコード」ではなく、dispatch の定数に対する dead code と読める。
- 注意: この結論は「dispatch の値が常に 7」という前提に依る。前提は store の支配で成り立つが、欠落区間に入る枝の入力 (`0x12905af` の `cmp byte ptr [rax],0x40` の結果) は本 REPORT で検証していない。判定を変える前にこの点を別途確認する必要がある (§5)。

## 4. 判定 (受入 1): UNDETERMINED のまま据え置き

- 12 site の判定 (TRUE_DROP / OK_LOAD / NO_CONSUMER) は、IR に store・load・消費者の結線が無い (#2705 §4)。§3 の到達性は「実行経路から外れる」根拠になるが、判定の定義 (IR 上の結線) を満たす根拠ではない。
- 本 REPORT は判定を変えない。`candidate_verdicts_1161.jsonl` の 12 行は UNDETERMINED のまま (根拠は §2・§3 に書いた)。
- 判定を変えると、脱落関数の和集合 69 (`REPORT_1161.md` §3) と `spill178_1161.tsv` が動く。#2689 (LD-124) の最終化に影響するため、本 PR では変えない。
- 受入 1 の「欠落区間を IR に戻せない場合は、根拠付きの未判定のまま REPORT に書いて閉じてよい」に従う。根拠は §2 (pass)・§3 (到達性)。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 欠落区間の入力 (`0x12905af` の `cmp byte ptr [rax],0x40` の値) が、どの入力でも dispatch を 7 のまま保つか。dispatch 値の支配は確認済みだが、欠落区間の入る前提の実行時検証は未了 | 12 site を dead code と判定してよいかの最終根拠 | #5435 (LD-270: 到達経路と F 照合) の範囲 |
| Jump Threading が同型の枝付け替えを他関数でも行うか (dispatch 定数の畳み込みを伴う関数の洗い出し) | 他の lift 欠落の検出範囲 | 親 #4959 の残件 (本 PR は 128f9e0 のみ) |
| 12 site の判定 (UNDETERMINED → 確定) | 128f9e0 の判定が UNDETERMINED のまま。和集合 69 は不変 | #2689 (LD-124) の最終化で扱う |

## 6. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst && tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
python3 tools/m11/ldfix/ld125_lift_gap.py
RETDEC=<toolchain-retdec の retdec-decompiler> timeout 900 <retdec> <PE> -o work/pa/f.drc.c --select-ranges "0x128f9e0-0x1294ab8" --select-decode-only --timeout 800 --print-after-all 2> work/pa/stderr.log
python3 tools/m11/ldfix/ld269_pass_trace.py && python3 tools/m11/ldfix/ld269_reach.py
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

`--select-ranges` は `0x` 接頭辞付きで指定する (接頭辞なしは rc=1)。

## 7. 測定 commit 以降の差分

`git diff 7e861de2d HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results` の出力は空 (本 REPORT と `docs/DOC_MAP.md` のみ追加)。
