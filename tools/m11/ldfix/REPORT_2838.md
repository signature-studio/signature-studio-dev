# REPORT #2838 — spill 宛 未判定 群 B 残り 12 site のうち 466af0 の 3 site を TRUE_DROP に分類 (LD-135・範囲縮小)

親: #2245。本 issue は範囲を縮めた (受入条件の残りは子 issue へ移した)。完了分は `466af0` の 3 site。残り 9 site は #2921 (LD-138)・#2922 (LD-139)・#2923 (LD-140) に起票 (§3)。

## 1. 測定

- 測定 commit: `6e2f0057` (コードを変えた最後の commit。判定 `candidate_verdicts_2838.jsonl`・`spill_classify_1161.py` の読込追加・再生成した `spill178_1161.tsv`)。基点は `origin/main` の `b2b052ce`
- 素材: `work-m11` / `work-liftdiff` を `tar --zstd -xf` で repo 直下に展開 (gitignore 対象の `tools/m11/work/`・`tools/liftdiff/work/`)
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground、`TMPDIR=$RUNNER_TEMP`)。測定 commit `6e2f0057` で rc=0・real 2m36.2s・実行後 load average 0.96 (1 分平均)。基点 `b2b052ce` でも同じ e2e が rc=0 で 7/7 一致
- 7/7 完了時に `spill178_1161.tsv` と `drops_510.tsv` が results/ と一致 (cmp OK)
- 集計 (7/7): spill 宛 unk site 178 / 71 関数。status 確定 120 (前 117) / 判定不能 30 (前 30) / 未判定 28 (前 31)
- 脱落関数の和集合: `[6]` の spill 宛確定 TRUE_DROP 関数は 23 (前 22)。増分は `466af0` (drops_510 に無い)。A ∪ B ∪ C = 69 + 5 = **74** (前 73。REPORT_2245 §4 の 73 からの増分)
- 測定後の差分: `git diff 6e2f0057 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results` は出力なし (差分 0)。以降の変更は本 REPORT と `docs/DOC_MAP.md` のみ

## 2. 判定結果 (466af0 の 3 site)

| fn | site | 判定 | 根拠 (要点) |
|---|---|---|---|
| 466af0 | 466bca・466d9b・466e03 | TRUE_DROP | 3 site とも同じ rip 相対セル VA `0x15e4608` (LVA 18761224)。機械語は `mov rax,[rip+X]` → `mov rax,[rax]` の 2 段参照で、セル内容 V = `0xfa9b10` の先の `[V]` = `0x840f02a83043b60f` を読む。IR は `inttoptr (18761224)` の 1 段 load (V) のみを `stack_var` (= `[rbp+0x80]`・`[rbp+0x38]`) へ store する。二段目の deref が IR に無い (1046a30 104cb44 と同型)。消費者は `call 0x448de0` (IR で同じ `stack_var` の番地を ptr 引数に渡す) |

判定の根拠行は `tools/m11/ldfix/results/candidate_verdicts_2838.jsonl` (3 行)。

限界: 消費者 `0x448de0` 内での値の読み方は見ていない。TRUE_DROP の根拠は「機械語と IR で値の段数が 1 つ違う」ことだけ。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ddf630` の 4 site: `ddf6b5`・`ddf6c6` (2 段参照で `[rbp+0x80]`・`[rbp+0xb8]`)、`ddff5a`・`de0bfe` (フレーム間コピー `[0xb8]→[0xa0]`・`[0x80]→[0xc0]`)。IR は `%25`・`%26`・`%27` の 1 段 load をポインタとして使う | 未判定 4 site。脱落関数の和集合 74 が未確定 | #2921 (LD-138) |
| `12cb680` の 3 site: `12cba4d`・`12cbab4` (未判定)、`12cb8e1` (判定不能の再分類)。IR (`stack_var_-48`) に `[rbp+0x38]` への store が無い | 未判定 2・判定不能 1 | #2922 (LD-139) |
| `1046a30` の 2 site: `10479c7` (未判定。`[rbp+0x4d8]` の 2 段参照。IR の対応 slot `stack_var_-208` が見当たらない)、`1047556` (判定不能の再分類) | 未判定 1・判定不能 1 | #2923 (LD-140) |

## 4. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

7/7 のみ (素材不要・commit 済み入力): `python3 tools/m11/ldfix/spill_classify_1161.py <ssa.json> tools/m11/ldfix/results/spill178_1161.tsv` の後、`cmp` で一致を確認する。
