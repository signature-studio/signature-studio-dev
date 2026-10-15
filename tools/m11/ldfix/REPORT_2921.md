# REPORT #2921 — spill 宛 未判定 `ddf630` の 4 site を TRUE_DROP に分類 (LD-138)

親: #2838 (LD-135)・#2245 (LD-93)。受入条件 3 項を満たしたので `Closes #2921`。
既知類型との関係: m11 の **D17** (rip 相対セルの 2 段 deref が IR で 1 段に潰れる。`REPORT_510.md`・`REPORT_968.md` の定義)。`docs/DEFECTS.md` の D1a〜D23 とは別の番号体系で、対応は未確認。

## 1. 測定

- 測定 commit: `5e0177c7` (コードを変えた最後の commit = 再現スクリプト `ld138_ddf630_dis.py` を含む)。その前が `3ec6620c` (判定 JSONL・`spill_classify_1161.py` の読込行・`spill178_1161.tsv` 再生成)。基点は `origin/main` の `71bf0957`。
- 素材: `work-m11` (337 MB) と `work-liftdiff` (58 MB) を `tar --zstd -xf` で repo 直下に展開 (4.4 s)。gitignore 対象の `tools/m11/work/`・`tools/liftdiff/work/`。`fl-win64` は e2e が使わないため未展開。
- 実行: `TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground、`timeout 900`)。

| 測定 | commit | rc | real | load (前→後, 1 分平均) | 結果 |
|---|---|---|---|---|---|
| 基点 | `71bf0957` | 0 | 2m41.6s | 0.75→1.00 | 7/7 |
| 判定追加 | `3ec6620c` | 0 | 2m40.9s | 0.16→0.95 | 7/7 |
| 測定値 | `5e0177c7` | 0 | 2m40.4s | 0.38→1.04 | 7/7 |

- wall time は 3 回で 2m40.4s–2m41.6s (n=3 の min–max)。並列数は 1 (直列の Python 処理)。
- 7/7 の内訳: step 5 `drops_510.tsv` と step 7 `spill178_1161.tsv` の `cmp` が一致 (`e2e_meas.log` の `[drops_510.tsv] results/ と一致`・`[spill178_1161.tsv] results/ と一致`)。
- 測定後の差分 (`5e0177c7` 以降に変えたのは本 REPORT・`docs/DOC_MAP.md`・`REPORT_2838.md` の 1 行のみ): 下記の出力は空。

```
git diff 5e0177c7 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results
(出力なし = 差分 0)
```

## 2. 判定 (4 site・全て TRUE_DROP)

判定基準は `REPORT_2838.md` と同じ: 機械語の値の段数が IR の値より 1 つ多く、その値が object 参照 (`[rax+0x14]` の読み・call の this) に使われる site を TRUE_DROP とする。

| site | 機械語 (段数) | IR (段数・行) | 消費者 (機械語 / IR) | 判定 |
|---|---|---|---|---|
| `ddf6b5` → `[rbp+0x80]` | `ddf6ab` rip セル `0x15e2318` (LVA 18752280) → `ddf6b2 mov rax,[rax]`: **2 段** | `429019` `%25 = load (18752280)`: **1 段** | `ddffa2`・`ddffca` `[rax+0x14]`、`ddffed` → `ddfffa` call `0x12df530` の this / IR `429877` `add %25,20`・`429907` `call @function_12df530(%25)` | TRUE_DROP |
| `ddf6c6` → `[rbp+0xb8]` | `ddf6bc` rip セル `0x15e3c70` (LVA 18758768) → `ddf6c3 mov rax,[rax]`: **2 段** | `429020` `%26 = load (18758768)`: **1 段** | `ddff2f`・`ddff36` の比較 (IR `429850`)、`ddff53` → `ddff5a` の複写 | TRUE_DROP |
| `ddff5a` → `[rbp+0xa0]` (← `[rbp+0xb8]`) | 複写 (2 段のまま) | `429862` `store %26 → stack_var_-280`: 1 段 | `ddf766`→`ddf776` `[rax+0x14]`、`ddf7c6` call `0x12df210` の this / IR `429101`・`429132`・`429187` | TRUE_DROP |
| `de0bfe` → `[rbp+0xc0]` (← `[rbp+0x80]`) | 複写 (2 段のまま) | `430849` `store %25 → storemerge23`: 1 段 | `de023d` `[rax+0x14]`、`de0266` → call `0x40fe90` の this / IR `430128`・`430139`・`430185`・`430250` (de022d ブロック以降) | TRUE_DROP |

- 機械語の対応 (2 段参照・複写・消費者) は `python3 tools/m11/ldfix/ld138_ddf630_dis.py` で再現する。出力は主要行のみ (4 site の範囲の命令・`[rbp+0x80/0xa0/0xb8/0xc0]` を読む mov/lea・`want` の IR 11 行)。上表の次の行は出力されない: 機械語 `ddf776`・`de023d` (`cmp dword [rax+0x14],0`)、`ddfffa`・`ddf7c6` (call)、IR `429101`・`429132`・`429187`。全行の根拠は下記の JSONL。
- 根拠の全文は `tools/m11/ldfix/results/candidate_verdicts_2921.jsonl` (4 行)。

**spill 宛 178 site の集計 (`spill178_1161.tsv`) の変化**

| 項目 | 前 (`71bf0957`) | 後 (`5e0177c7`) |
|---|---|---|
| 確定 | 120 | **124** (+4) |
| 判定不能 | 30 | 30 |
| 未判定 | 28 | **24** (−4) |
| spill 宛の確定 TRUE_DROP 関数 (drops_510 に無いもの) | 23 (うち増分 `466af0`) | **24** (増分に `ddf630` を追加) |
| 脱落関数の和集合 A ∪ B ∪ C | 74 | **75** (`69 + 6`) |

## 3. ネガティブコントロール

- 候補判定の 1 行 (`ddf6b5`) を除去して `spill_classify_1161.py` を実行 → 確定 123・未判定 25 となり、`cmp` が `differ: byte 6787, line 94` で FAIL (rc=1)。読込行と結果 TSV の結線は検出される。
- 本 NC は配線の検査であり、判定そのものの真偽は検査しない (次節)。

## 4. 検証範囲・限界

- 検証範囲: 機械語 (`m11_image.bin` の逆アセンブル、`ldmach_img.py`) と `boot_final3.ll` の静的対応のみ。実行時の値は見ていない。
- 2 段目の値 `[C]` (セル内容 `0x153fc08`・`0x153fbf8` が指す先) の実値は確認していない。イメージから読んだ値 (`0x5080f0170016002`・`0x600130024206`) は object として妥当に見えないが、イメージがデータ領域を含むかを確かめていないため、判定の根拠には使わない。
- TRUE_DROP の根拠は「段数が 1 つ違い、その値が object 参照に使われる」ことだけ (`REPORT_2838.md` §2 と同じ限界)。消費者の内部 (`0x12df530`・`0x12df210`・`0x40fe90` の中) での値の読み方は見ていない。
- 本 issue は分類のみ。IR の修復 (2 段目の deref を補う) は行っていない。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ddf630` の TRUE_DROP 4 site の IR 修復 pass (1 段 load に 2 段目の deref を補う) | 脱落関数の和集合 75 件の 1 件として残る。修復は本 issue の受入条件の外 | [LD-143] #2987 (親 #2838) |
| `[C]` の実値と消費者内部の値の読み方の検証 (動的検証) | TRUE_DROP の確度 (限界の節) | PM 判断・未起票 (`REPORT_2838.md` §3 の限界と同じ扱い) |

## 6. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh     # 7/7 (約 2m40s)
python3 tools/m11/ldfix/ld138_ddf630_dis.py   # 4 site の機械語・消費者・IR の主要行 (全行は results/candidate_verdicts_2921.jsonl)
```
