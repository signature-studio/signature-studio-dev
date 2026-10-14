# REPORT #2923 — spill 宛 `1046a30` の 2 site を再判定 (10479c7 = 判定不能に戻す / 1047556 = 判定不能の根拠を訂正) (LD-140)

親: #2838 (LD-135 の子)。受入条件 3 件を満たした。`1047556` は段数が一致し TRUE_DROP ではないが、IR の cell 番地が VA 表記で VA 漏れの疑いがあるため判定不能に留め、子 #2958 (LD-142) に起票した。`10479c7` は前 round で OK_LOAD (確定) としたが、根拠は段数一致の 1 条件だけだったため判定不能に戻した。IR 側の確認は #2958 に追加した。

## 1. 測定

- 測定 commit: `7554d620` (コードを変えた最後の commit。`candidate_verdicts_2923.jsonl` の 10479c7 を UNDETERMINED にし、`spill178_1161.tsv` を再生成)。基点は `origin/main` の `71bf0957`
- 前回測定 (`94db5f8b`・work-m11 あり): `TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` rc=0・real 122 s・load average 0.01 → 0.87・7/7 完走。このときの確定 121 のうち 10479c7 (OK_LOAD) を撤回した
- 本 round の素材: work-m11 / work-liftdiff は本 run に無い (`$ARTIFACTS_DIR` は fl-win64 のみ)。step 7 だけを `results/audit_510_ssa.json` (commit 済み) から再実行した。steps 1〜6 は入力が変わらない (`spill_classify_1161.py` だけが `candidate_verdicts_2923.jsonl` を読む) ため、前回測定が有効
- 実行 (HEAD `7554d620`): `python3 tools/m11/ldfix/spill_classify_1161.py tools/m11/ldfix/results/audit_510_ssa.json "$RUNNER_TEMP/spill178_HEAD.tsv"` → `cmp` で `results/spill178_1161.tsv` と一致 (rc=0)
- 集計 (step 7): spill 宛 unk site 178 / 71 関数。status 確定 120 (前 121) / 判定不能 31 (前 30) / 未判定 27 (同)。脱落関数の和集合は [5] 69 + [6] 5 = 74 (変化なし)
- 測定後の差分: `git diff 7554d620 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results` は出力なし (以降の変更は本 REPORT と PR 本文のみ)

## 2. 判定結果 (`1046a30` の 2 site)

| site | 判定 | 根拠 (要点) |
|---|---|---|
| 10479c7 | 判定不能 (前 round の OK_LOAD は撤回) | 機械語: `1047934 mov rax,[rbp+0x4e8]` → `104793b lea rax,[rax+0x16c]` → `1047942 mov [rbp+0x4d8],rax` (P = X+0x16c、X = `[rbp+0x4e8]`)。`10479be mov rax,[rbp+0x4d8]` → `10479c5 mov eax,[rax]` (P の 1 段 deref) → `10479c7 mov [rbp+0x5b8],eax`。IR: `104796f` で `%491 = add %363,364`・`%492 = inttoptr %491` (P)、`dec_label_pc_10479be` で `%505 = load i32, ptr %492`・`store i32 %505, ptr %stack_var_16` (= `[rbp+0x5b8]`)。確認できたのは段数 1 の一致だけ。OK_LOAD の根拠として不足のため判定不能。未確認: (i) 1047942〜10479be の間に `[rbp+0x4d8]` への書込が無いこと (命令範囲)、(ii) IR `%492` が slot の reload に直接対応する根拠 (slot の SSA 畳み込み等)、(iii) `stack_var_16` の後続の読みが IR の対応命令と一致すること、(iv) `dec_label_pc_10479be` が entry から到達可能なこと。#2923 本文の前提「`[rbp+0x4d8]` に対応する IR slot (`stack_var_-208`) が見当たらない」は (ii) まで未解決。IR (`boot_final3.ll`・work-m11) が本 round の素材に無いため (i)〜(iv) は確認していない |
| 1047556 | 判定不能 (維持・根拠を訂正) | 機械語: `104754c mov rax,[rip+0x59acad]` (cell VA 0x15e2200) → `1047553 mov rax,[rax]` → `1047556 mov [rbp+0x520],rax` (else 枝、値 = `[[cell]]`)。IR: `dec_label_104754c` で `%ce12n11 = inttoptr i64 22946304` (= VA 0x15e2200 の 10 進) → `%378 = load` → `%storemerge54.pre = load [%378]` → `store %storemerge54.reg2mem` (`boot_final3.ll` 17451–17455 行)。段数 2 は一致するため TRUE_DROP ではない。一方、番地が VA 表記で、同じ関数の他の cell は LVA 表記 (例 `18752024` = 0x11e2218 が 10 件) を使う。本番の `VA_TO_LVA = LB − IMG_BASE` (LB=0) では実効番地が LVA 18752000 になるはずで、IR の 22946304 と一致しない。M2q (`pass_m2q_fn980ed0`・#1043) と同型の VA 漏れの疑い。M2P (全件 remap) は既定 OFF (#417) のため、本番 IR では直っていない。OK_LOAD とは言えないので判定不能。修復は子 #2958 |

判定の根拠行は `tools/m11/ldfix/results/candidate_verdicts_2923.jsonl` (2 行)。

## 3. 訂正 (前 REPORT の記述)

- `REPORT_2245.md` §2 の「1047556: IR 側 (function_1046a30 の 16267–24295) にセル 0x15e2200 (inttoptr 18752000) の load が 1 件も無い」は、LVA 表記だけを探した誤り。同じ cell は VA 表記 `inttoptr i64 22946304` (17451 行) で load されており、段数は機械語と一致する。`REPORT_2838.md` §3 の「1047556 (判定不能の再分類)」も同じ前提に立つ。
- `REPORT_2838.md` §3 の「10479c7: `mov eax,[rbp+0x4d8]`→`mov eax,[rax]` (2 段参照)」は、`[rbp+0x4d8]` が `lea` で作った P を置く slot であり、実際の deref は 1 段 (IR `%505`)。
- 本 PR の前 round (`94db5f8b`) で 10479c7 を OK_LOAD (確定) としたのは撤回した。根拠が段数一致だけだった。

## 4. 限界・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 10479c7 の IR 側確認 (上記 (i)〜(iv)、work-m11 が要る)。確認できれば OK_LOAD に戻せる | 10479c7 は判定不能のまま。spill 宛 確定 120 に含まれない | #2958 (LD-142 本文に追加) |
| 1047556 の IR 番地 22946304 (VA 漏れの疑い)。修復と本番影響の実測 | 1047556 は判定不能のまま。`1046a30` の `[rbp+0x520]` 読み値が誤る可能性 | #2958 (LD-142) |
| 10479c7 の X (`[rbp+0x4e8]`) の上流。機械語 `10474bf`→`10474c6`→`10474c9`→`10474d4` は 4 段、IR は `%351` (cell を i32 load) → `%359` (`[Q+8]`) → `%363` (`[%361]`) の 3 段に見える | 上流が 1 段足りなければ 10479c7 の値も誤る。静的 image では cell の内容 (0x12bafc8) の先が機械語のバイト列で、実行時の値を辿れなかった | #2958 (本文に記載済み) |

## 5. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

step 7 のみ (素材不要): `python3 tools/m11/ldfix/spill_classify_1161.py tools/m11/ldfix/results/audit_510_ssa.json "$RUNNER_TEMP/spill178.tsv"` の後、`cmp` で `tools/m11/ldfix/results/spill178_1161.tsv` と比較する。
