# REPORT #2245 — spill 宛 未判定 関数群 B (32 site) の消費者分類 (一部・分割)

親: #2227 / #1161 (LD-35)。子: #2837 (LD-134・`10c7cd0` 12 site)・#2838 (LD-135・残り 10 site と判定不能 2 site の再分類)。
本 PR は群 B の 32 site のうち 10 site を分類した。残りは子 issue に移した (受入条件 1・3 は未達)。

## 1. 測定

- 測定 commit: `cae3d6d7` (コードを変えた最後の commit。候補判定 `candidate_verdicts_2245.jsonl`・`spill_classify_1161.py` の読込追加・再生成した `spill178_1161.tsv`)。基点は `origin/main` の `26f90ada`
- 素材: `work-m11` / `work-liftdiff` を `tar --zstd -xf` で `ws-2245` の `tools/m11/work/`・`tools/liftdiff/work/` (gitignore) に展開
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground、`TMPDIR=$RUNNER_TEMP`)。測定 commit での結果: rc=0・real 2m48.8s・実行後 load average 0.98 (1 分平均)
- 7/7 完了時に `spill178_1161.tsv` と `drops_510.tsv` が results/ と一致 (cmp OK)
- 集計 (step 7/7): spill 宛 unk site 178 site / 71 関数。status 確定 117 (前 109) / 判定不能 30 (前 28) / 未判定 31 (前 41)
- 測定後の差分 (`git diff cae3d6d7 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results`): 出力なし (差分 0)。以降の変更はこの REPORT のみ

## 2. 判定結果 (群 B 32 site のうち 10 site)

| fn | site | 判定 | 根拠 (要点) |
|---|---|---|---|
| 6bb3f0 | 6bb4e5・6bb52d・6bb59f・6bb5e4 | TRUE_DROP | 各 site の `mov [rsp+0x38],r13d` (8 番目の引数) は直後の間接 `call qword ptr [rax]` (6bb4fd・6bb539・6bb5b7・6bb5f0) が消費する。IR `function_6bb3f0` は boot_final3.ll 263382–263413 の 31 行で間接 call を持たない。消費者の脱落 (4120c0 と同型) |
| 1046a30 | 104cb44・104cbcb・1047208・104a9f6 | TRUE_DROP | 機械語 `mov rax,[rip+X]` → `mov rax,[rax]` (二段参照) の後に spill。IR は同じセル (k=0x11e2718・0x11e3ba0・0x11e3ec8・0x11e4dc0) を 1 段だけ load し、その値 V を base・null 判定に使う。二段目の deref が無い。10472ea (既存 TRUE_DROP) と同型 |
| 1046a30 | 1047556 | UNDETERMINED | 二段参照で spill。消費者は 20 箇所超。IR 側に参照セル 0x15e2200 (inttoptr 18752000) の load が 1 件も無い。値の出元が別経路か未確認 |
| 12cb680 | 12cb8e1 | UNDETERMINED | spill 元 `mov eax,[rbx]` と `cmp -1` は IR 85928–85929 (`%110`・`%111`) に対応し OK。一方、`!= -1` 分岐の書き戻し `mov [rbx],eax` (12cb908) は IR に無い。書き値は直前に読んだ値なので、間接 call `[rbp+0x70]` が `[rbx]` を書かなければ no-op。call 先の書込みは未確認 |

判定の根拠行は `tools/m11/ldfix/results/candidate_verdicts_2245.jsonl` (10 行)。

## 3. 前 run の記述の訂正

- 前 run (no-pr) の「1046a30 の 104cb44・104cbcb は linear disassembly に現れない (hit=0)」は再現しなかった。関数先頭 `1046a30` から線形に逆アセンブルすると両方とも命令境界に現れる (104cb44 は `mov rax,[rip+0x595bd7]`・`mov rax,[rax]` の直後)。site 列挙のずれではない
- 6bb3f0 の機械語命令数は 2,806 (前 run の訂正どおり)。IR 31 行との差は変わらない

## 4. 脱落関数の集合 (spill_classify_1161.py の [5][6])

- 出力 [6]: spill 宛の確定 TRUE_DROP 関数 22 (前 21)。drops_510 に無いもの 4 (4120c0・41a5d0・6bb3f0・6c3700)
- A ∪ B ∪ C = 69 + 4 = **73** (前 72)。増分は `6bb3f0` (本 PR の TRUE_DROP 4 site)
- 1046a30 は既に drops_510 の A ∩ B にあり、集合は増えない

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `10c7cd0` の未判定 12 site | 脱落関数の和集合 73 が未確定 | #2837 (LD-134) |
| `ddf630` 4・`466af0` 3・`12cbab4`・`12cba4d`・`10479c7` の未判定 10 site | 同上 | #2838 (LD-135) |
| 判定不能 2 site (1047556・12cb8e1) の再分類 | 同上 | #2838 (LD-135) |
| `6bb3f0` の IR 本体欠落 (IR 31 行・機械語 2,806 命令) | 4 site は消費者脱落として TRUE_DROP にしたが、関数本体欠落の類型は未確定 | PM (`docs/DEFECTS.md` 類型の判断) |

## 6. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```
