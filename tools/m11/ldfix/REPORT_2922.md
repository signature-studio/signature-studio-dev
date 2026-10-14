# REPORT #2922 — spill 宛 12cb680 の 3 site を TRUE_DROP に分類 (LD-139・#2838 子)

親: #2838。残り 3 site (`12cb8e1` 判定不能の再分類、`12cba4d`・`12cbab4` 未判定) を分類した。3 site とも、spill 値の消費者 (コールバックの `[rcx+4]` 読み) が IR で脱落している。

## 1. 測定

- 測定 commit: `ff010340` (コードを変えた最後の commit。`candidate_verdicts_2922.jsonl`・`spill_classify_1161.py`・再生成した `spill178_1161.tsv`)。基点は `origin/main` の `71bf0957`
- 素材: `work-m11` / `work-liftdiff` を `tar --zstd -xf` で repo 直下に展開 (gitignore 対象の `tools/m11/work/`・`tools/liftdiff/work/`)
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground、`TMPDIR=$RUNNER_TEMP`)。`ff010340` で rc=0・real 154s・実行後 load average 0.93 (1 分平均)。7/7 完了。`drops_510.tsv`・`spill178_1161.tsv` が results/ と一致 (cmp OK)
- 集計 (7/7): spill 宛 unk site 178 / 71 関数。status 確定 123 (前 120) / 判定不能 29 (前 30) / 未判定 26 (前 28)
- 脱落関数の和集合: spill 宛の確定 TRUE_DROP 関数 24 (前 23)。増分は `12cb680`。A ∪ B ∪ C = 69 + 6 = **75** (前 74)
- 測定後の差分: `git diff ff010340 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results` は出力なし (差分 0)

## 2. 判定結果 (12cb680 の 3 site)

| fn | site | 判定 | 根拠 (要点) |
|---|---|---|---|
| 12cb680 | 12cb8e1 | TRUE_DROP (前 判定不能) | `[rbx]` を `[rbp+0x38]` (= コールバックの s.b) へ spill → `call [rbp+0x70]` (`rcx=&[rbp+0x34]`)。消費者はコールバック先の `[rcx+4]` 読み。IR に間接 call が無い |
| 12cb680 | 12cba4d | TRUE_DROP (前 未判定) | 同型。`call [rbp+0x70]` は 12cba58 |
| 12cb680 | 12cbab4 | TRUE_DROP (前 未判定) | 同型。`call [rbp+0x70]` は 12cbabf。base は大域 `[rdi]` |

判定の根拠行は `tools/m11/ldfix/results/candidate_verdicts_2922.jsonl` (3 行)。

## 3. 根拠と限界

- 関数 `12cb680` は `arg1` (rcx 入力) をコールバックのアドレスとして `call qword ptr [rbp+0x70]` で呼ぶ (機械語に 11 本)。IR (`boot_final3.ll` 85713–86490) の直接 call は 47 本だけで、間接 call も `%arg1` の参照も無い。spill の store と消費者の call は IR に無い。
- 既知の呼び出し先 (rcx の定数) は 3 つ。機械語の直接呼び出し (`0x1003730`・`0x12a3ff0`・`0x13111a0`) と IR の直接 call (`boot_final3.ll` 430・78322・100762 行) が一致する。
  - `0x10036b0`: 先頭で `mov eax,[rcx+4]` (無条件に s.b を読む)
  - `0x12a3ec0`: 先頭で `mov eax,[rbx+4]` (無条件に読む)
  - `0x12ca330`: `12ca408` で `mov eax,[rbx+4]` (条件付きの経路で読む)
- 限界: IR の `m11_tr_function_12cb680` (`boot_final3.ll` 499835 付近) は `%a0` を callee に渡す ABI 殻で、外部から任意の関数ポインタを受ける。その先は未確認。TRUE_DROP は既知の 3 先について消費者の存在を示すもので、動的な先が読まない経路の有無は判定していない。
- 書き戻し `[rbx]` / `[rdi]` (`12cb908`・`12cba78`・`12cbad2`) の IR 対応は、spill の判定には使っていない (消費者の有無だけで判定した)。`12cb8e1` が判定不能だった理由 (REPORT_2245 §2) は、この書き戻しの要否だった。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `m11_tr_function_12cb680` の `%a0` 経路 (外部から渡される任意の関数ポインタ) の先の読み方 | 静的な 3 先の範囲でだけ TRUE_DROP。動的な先が `[rcx+4]` を読まない経路の有無は未確認 | PM (判定の範囲の判断) |
| `12cb680` の間接 call 11 本 (`call [rbp+0x70]`) が IR に 0 本。関数内の他の store/load も同じ脱落か | 脱落関数の和集合 75 の類型 | PM (`docs/DEFECTS.md` 類型の判断) |
| 書き戻し `[rbx]`・`[rdi]` (`12cb908`・`12cba78`・`12cbad2`) の IR 対応 | spill の判定とは別の store 脱落の有無 | PM (判定の要否) |

## 5. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst      # repo 直下で展開
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

素材不要の確認: `python3 tools/m11/ldfix/spill_classify_1161.py <ssa.json> tools/m11/ldfix/results/spill178_1161.tsv` の後、`cmp` で `results/` と一致を確認する。
