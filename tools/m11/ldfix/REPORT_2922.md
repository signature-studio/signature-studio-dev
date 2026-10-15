# REPORT #2922 — spill 宛 12cb680 の 3 site を TRUE_DROP に分類 (LD-139・#2838 子)

既知類型との関係: 該当 DEFECTS.md D15 (メモリ間接 call の IR 欠落)。D15 の行が M11 #682 の `function_47b260` (notify `call qword [rbx+0x20]` が IR に無い) を同型の新事例として挙げる。D15 の原因 (stage-0 の capstone 変換か、m11 の RetDec 経路か) は本件では同定していない (DEFECTS.md)。

親: #2838。残り 3 site (`12cb8e1` 判定不能の再分類、`12cba4d`・`12cbab4` 未判定) を分類した。3 site とも、spill 値の消費者 (コールバックの `[rcx+4]` 読み) が IR で脱落している。

## 1. 測定

- 測定 commit: `53a739d2` (`origin/main` の `940c0d6a` を取り込んだ merge。コードを変えた最後の commit。ldfix のコードは `e272ee3c` と同一)。直前の測定 commit は `e272ee3c` (`bf725b96` の取り込み)・`be5f4697` (`e87eb52a` の取り込み)・`55ed65a2` (`3d37a190` の取り込み)。取り込み前の PR 測定は `ff010340` (基点 `71bf0957`)
- main 取り込み: (1) `55ed65a2`: `origin/main` (`3d37a190`) を merge。競合は `docs/DOC_MAP.md` と `spill_classify_1161.py` の 2 箇所。(2) `be5f4697`: `origin/main` (`e87eb52a`) を merge。競合なし。(3) `e272ee3c`: `origin/main` (`bf725b96`・#2837 を含む) を merge。競合は `spill_classify_1161.py` の docstring 1 箇所で、2837 と 2922 の候補判定の両方を残した。`spill178_1161.tsv` は統合後の script で再生成し、merge の結果と一致。(4) `53a739d2`: `origin/main` (`940c0d6a`) を merge。競合なし (auto-merge)。`spill178_1161.tsv` は統合後の script の出力と一致 (cmp OK)。rebase はしていない
- 素材: `work-m11` / `work-liftdiff` は repo 外 (`$RUNNER_TEMP/ws2957_art`) に `tar -C` で展開し、`M11_WORK` / `LD_WORK` で指定した。tar の内部パスは `tools/m11/work/`・`tools/liftdiff/work/` (WORKFLOW §11 の既定) だが、AGENTS 禁止 4 により repo 内の `tools/**/work/` には置かない。実行は clean な worktree (`ws-2957`・HEAD `53a739d2`) で行った
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground)。`53a739d2` で rc=0・real 165s・load average 0.65 → 1.01・7/7 完了。`drops_510.tsv`・`spill178_1161.tsv` が results/ と一致 (cmp OK)。`e272ee3c` で rc=0・real 123s・load average 0.04 → 0.91・7/7 完了 (cmp OK)。`be5f4697` では rc=0・real 122s・load average 0.89 → 1.13・7/7 完了 (cmp OK)。`55ed65a2` では rc=0・real 159s・load average 0.10 → 1.10・7/7 完了
- 取り込み前の測定 (`ff010340`): rc=0・real 154s・load average 0.93・7/7 完了・cmp OK
- 集計 (7/7、`53a739d2`): spill 宛 unk site 178 / 71 関数。status 確定 139 (前 136) / 判定不能 29 (前 30) / 未判定 10 (前 12)。「前」は `origin/main` (`940c0d6a`) の `spill_classify_1161.py` を同じ `ssa.json` に当てた実測 (main の `results/spill178_1161.tsv` と一致)。`e272ee3c` 時点の集計と同じ値で、main 取り込みは集計を変えなかった
- 脱落関数の和集合: spill 宛の確定 TRUE_DROP 関数 26 (前 25)。増分は `12cb680`。A ∪ B ∪ C = 69 + 8 = **77** (前 76 = 69 + 7)
- 測定後の差分: `git diff 53a739d2 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results tools/m11/lb_base.py` は出力なし (差分 0)。`53a739d2` の ldfix 差分は `e272ee3c` から 0 (同じ範囲)。HEAD の増分は REPORT の文言のみ
- 差し戻し後の修正 (round 4・文書のみ): `origin/main` (`940c0d6a`) の merge と、REPORT の数値・文言 (§1・§3 表の列見出し・§4・§5) の修正。ldfix のコードと results は merge の前後で変えていない
- 差し戻し後の e2e 再実行 (取り込み前の `bd643abf`): rc=0・real 157s・load average 0.48 → 0.96・7/7 完了・cmp 一致。集計は確定 123 / 判定不能 29 / 未判定 26 (取り込み前の値)

## 2. 判定結果 (12cb680 の 3 site)

| fn | site | 判定 | 根拠 (要点) |
|---|---|---|---|
| 12cb680 | 12cb8e1 | TRUE_DROP (前 判定不能) | `[rbx]` を `[rbp+0x38]` (= コールバックの s.b) へ spill → `call [rbp+0x70]` (`rcx=&[rbp+0x34]`)。消費者はコールバック先の `[rcx+4]` 読み。IR に間接 call が無い |
| 12cb680 | 12cba4d | TRUE_DROP (前 未判定) | 同型。`call [rbp+0x70]` は 12cba58 |
| 12cb680 | 12cbab4 | TRUE_DROP (前 未判定) | 同型。`call [rbp+0x70]` は 12cbabf。base は大域 `[rdi]` |

判定の根拠行は `tools/m11/ldfix/results/candidate_verdicts_2922.jsonl` (3 行)。

## 3. 根拠と限界

- 関数 `12cb680` は `arg1` (rcx 入力) をコールバックのアドレスとして `call qword ptr [rbp+0x70]` で呼ぶ (機械語に 11 本)。IR (`boot_final3.ll` 85713–86490) の直接 call は 47 本だけで、間接 call も `%arg1` の参照も無い。spill の store と消費者の call は IR に無い。
- 直接呼び出し元 (機械語) は 3 つ: `0x1003730`・`0x12a3ff0`・`0x13111a0`。IR の直接 call (`boot_final3.ll` 430・78322・100762 行) と一致する。既知の先 (rcx の定数) は次の 3 つ。
  - `0x10036b0`: 先頭 (`0x10036b0`) で `mov eax,[rcx+4]` (無条件に s.b を読む)
  - `0x12a3ec0`: `mov rbx,rcx` (`0x12a3ecd`) の直後の `0x12a3ed3` で `mov eax,[rbx+4]` (無条件に読む)
  - `0x12ca330`: `0x12ca408` で `mov eax,[rbx+4]`。直前の `0x12ca406` の `je` を通らない条件付きの経路で読む
- 呼び出し元と先の対応 (`m11_image.bin` を capstone で逆アセンブルし、`lea rcx,[rip+disp]` の解決先を確認。IMG_BASE `0x400000`):

  | 呼び出し元 | lea 命令の番地 (`lea rcx`) | call 命令の番地 (`call 0x12cb680`) | 先 (`lea rcx` の解決先) |
  |---|---|---|---|
  | `0x1003730` | `0x1003850` | `0x1003859` | `0x10036b0` |
  | `0x12a3ff0` | `0x12a4290` | `0x12a429a` | `0x12a3ec0` |
  | `0x13111a0` | `0x1311358` | `0x1311361` | `0x12ca330` |

  判定は先の読みだけで決まり、対応には依らない。
- 判定の基準: 既知の 3 先のうち 1 本以上で `[rcx+4]` (= s.b) の消費者が機械語に存在すること。IR の `12cb680` には間接 call が 1 本も無いため、spill の store と消費者の call が IR で落ちている。
- 判定の基準の外: IR の `m11_tr_function_12cb680` (`boot_final3.ll` 499835 付近) は `%a0` を callee に渡す ABI 殻で、外部から任意の関数ポインタを受ける。その動的な先の全数は判定の前提に含めない。その先が実行時に到達するか、`[rcx+4]` を読まないかも判定していない。
- 書き戻し `[rbx]` / `[rdi]` (`12cb908`・`12cba78`・`12cbad2`) の IR 対応は、spill の判定には使っていない (消費者の有無だけで判定した)。`12cb8e1` が判定不能だった理由 (REPORT_2245 §2) は、この書き戻しの要否だった。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `m11_tr_function_12cb680` の `%a0` 経路 (外部から渡される任意の関数ポインタ) の先 | 判定の基準の外 (既知 3 先の 1 本で判定が立つ)。その先が実行時に到達するか、`[rcx+4]` を読まないかは未確認 | PM (判定範囲の確認) |
| `12cb680` の間接 call 11 本 (`call [rbp+0x70]`) が IR に 0 本。関数内の他の store/load も同じ脱落か | 脱落関数の和集合 77 の類型 | PM (`docs/DEFECTS.md` 類型の判断) |
| 書き戻し `[rbx]`・`[rdi]` (`12cb908`・`12cba78`・`12cbad2`) の IR 対応 | spill の判定とは別の store 脱落の有無 | PM (判定の要否) |

## 5. 再現

```
mkdir -p "$RUNNER_TEMP/ws2957_art"                  # repo 外に展開 (tar の内部パスは tools/m11/work/・tools/liftdiff/work/)
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst -C "$RUNNER_TEMP/ws2957_art"
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst -C "$RUNNER_TEMP/ws2957_art"
M11_WORK="$RUNNER_TEMP/ws2957_art/tools/m11/work" LD_WORK="$RUNNER_TEMP/ws2957_art/tools/liftdiff/work" bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

既存の `ssa.json` がある場合 (`ssa.json` は work-m11 から `audit_lsf_ssa.py` が作る): `python3 tools/m11/ldfix/spill_classify_1161.py <ssa.json> <出力 TSV>` の後、`cmp` で `results/spill178_1161.tsv` と一致を確認する。
