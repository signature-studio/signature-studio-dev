# REPORT #2923 — spill 宛 `1046a30` の 2 site を再判定 (10479c7 = OK_LOAD / 1047556 = 判定不能の根拠を訂正) (LD-140)

親: #2838 (LD-135 の子)。受入条件 3 件を満たした。`1047556` は段数が一致し TRUE_DROP ではないが、IR の cell 番地が VA 表記で VA 漏れの疑いがあるため判定不能に留め、子 #2958 (LD-142) に起票した。

## 1. 測定

- 測定 commit: `94db5f8b` (コードを変えた最後の commit。判定 `candidate_verdicts_2923.jsonl`・`spill_classify_1161.py` の読込追加・再生成した `spill178_1161.tsv`)。基点は `origin/main` の `71bf0957`
- 素材: `work-m11` / `work-liftdiff` を `tar --zstd -xf` で `tools/m11/work/`・`tools/liftdiff/work/` (gitignore) に展開
- 実行: `TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground)。rc=0・real 122 s・load average 0.01 (開始前 1 分) → 0.87 (終了直後 1 分)。7/7 完了。`drops_510.tsv` と `spill178_1161.tsv` が results/ と cmp 一致
- 集計 (7/7): spill 宛 unk site 178 / 71 関数。status 確定 121 (前 120) / 判定不能 30 (同) / 未判定 27 (前 28)。脱落関数の和集合は [5] 69 + [6] 5 = 74 (前 74。増分 0)
- 測定後の差分: `git diff 94db5f8b HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results` は出力なし (以降の変更は本 REPORT と `docs/DOC_MAP.md` のみ)

## 2. 判定結果 (`1046a30` の 2 site)

| site | 判定 | 根拠 (要点) |
|---|---|---|
| 10479c7 | OK_LOAD (未判定 → 確定) | 機械語: `1047934 lea rax,[rax+0x16c]` → `1047942 mov [rbp+0x4d8],rax` (P = X+0x16c、X = `[rbp+0x4e8]`)。`10479be mov rax,[rbp+0x4d8]` → `10479c5 mov eax,[rax]` (P の 1 段 deref) → `10479c7 mov [rbp+0x5b8],eax`。IR: `dec_label_104796f` で `%491 = add %363,364`・`%492 = inttoptr %491` (P)、`dec_label_10479be` で `%505 = load i32, ptr %492` → `store i32 %505, ptr %stack_var_16` (= `[rbp+0x5b8]`)。深さ 1 で一致 |
| 1047556 | 判定不能 (維持・根拠を訂正) | 機械語: `104754c mov rax,[rip+0x59acad]` (cell VA 0x15e2200) → `1047553 mov rax,[rax]` → `1047556 mov [rbp+0x520],rax` (else 枝、値 = `[[cell]]`)。IR: `dec_label_104754c` で `%ce12n11 = inttoptr i64 22946304` (= VA 0x15e2200 の 10 進) → `%378 = load` → `%storemerge54.pre = load [%378]` → `store %storemerge54.reg2mem` (`boot_final3.ll` 17451–17455 行)。段数 2 は一致するため TRUE_DROP ではない。一方、番地が VA 表記で、同じ関数の他の cell は LVA 表記 (例 `18752024` = 0x11e2218 が 10 件) を使う。本番の `VA_TO_LVA = LB − IMG_BASE` (LB=0) では実効番地が LVA 18752000 になるはずで、IR の 22946304 と一致しない。M2q (`pass_m2q_fn980ed0`・#1043) と同型の VA 漏れの疑い。M2P (全件 remap) は既定 OFF (#417) のため、本番 IR では直っていない。OK_LOAD とは言えないので判定不能。修復は子 #2958 |

判定の根拠行は `tools/m11/ldfix/results/candidate_verdicts_2923.jsonl` (2 行)。

## 3. 訂正 (前 REPORT の記述)

- `REPORT_2245.md` §2 の「1047556: IR 側 (function_1046a30 の 16267–24295) にセル 0x15e2200 (inttoptr 18752000) の load が 1 件も無い」は、LVA 表記だけを探した誤り。同じ cell は VA 表記 `inttoptr i64 22946304` (17451 行) で load されており、段数は機械語と一致する。`REPORT_2838.md` §3 の「1047556 (判定不能の再分類)」も同じ前提に立つ。
- `REPORT_2838.md` §3 の「10479c7: `mov eax,[rbp+0x4d8]`→`mov eax,[rax]` (2 段参照)」は、`[rbp+0x4d8]` が `lea` で作った P を置く slot であり、実際の deref は 1 段 (IR `%505`)。

## 4. 限界・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 1047556 の IR 番地 22946304 (VA 漏れの疑い)。修復と本番影響の実測 | 1047556 は判定不能のまま。`1046a30` の `[rbp+0x520]` 読み値が誤る可能性 | #2958 (LD-142) |
| 10479c7 の X (`[rbp+0x4e8]`) の上流。機械語 `10474bf`→`10474c6`→`10474c9`→`10474d4` は 4 段、IR は `%351` (cell を i32 load) → `%359` (`[Q+8]`) → `%363` (`[%361]`) の 3 段に見える。同じ cell の `cmp [rax+0x10]` (`10474ad`) も IR が 1 段少ない | 10479c7 の OK_LOAD は spill site 自身の深さ一致に限る。上流が 1 段足りなければ 10479c7 の値も誤る。静的 image では cell の内容 (0x12bafc8) の先が機械語のバイト列で、実行時の値を辿れなかった | 未判定 (上流の段数は本 REPORT の範囲外。#2958 の本文に追記して追跡する) |

## 5. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

7/7 のみ (素材不要・commit 済み入力): `python3 tools/m11/ldfix/spill_classify_1161.py tools/m11/ldfix/results/audit_510_ssa.json "$RUNNER_TEMP/spill178.tsv"` の後、`cmp` で `tools/m11/ldfix/results/spill178_1161.tsv` と比較する。
