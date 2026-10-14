# REPORT #1169 — D17 spill 宛 CELL_COLLAPSED 37 site の判定対応と修復 pass の判断 (LD-37)

既知類型との関係: D4 (2 段 deref 脱落) の spill 宛版に近い。ただし本 REPORT は機構を確定しない (`docs/DEFECTS.md` の該当 ID は付けない)。

親: #968 (LD-21)。本 issue は規約 (`docs/WORKFLOW.md` §3 の Closes 縮小規定) に従い範囲を縮小した。完了分は判定対応 (受入 1 の 30/37 確定 + 残りの担当付け)・残数の実測 (受入 3)・emcc 構文検証 (受入 4)。修復 pass (受入 2) は子 issue へ移した (§4)。

## 1. 測定条件

- 測定 commit: `30860c30` (コードを変えた最後の commit。判定対応の e2e 追加)。作業 worktree `ws-1169` (branch `1169-spill-frame-verdict`)
- 素材: `work-m11` を `tar --zstd -xf` で展開 (gitignore 対象の `tools/m11/work/`)。worktree には無いため `M11_WORK` で main の展開先を読んだ (読込のみ)
- 実行: `M11_WORK=<main>/tools/m11/work bash tools/m11/ldfix/fix_d17_e2e.sh` (foreground、`TMPDIR=$RUNNER_TEMP`)
- 結果: rc=0、real 23.3 s、load average (uptime) 0.09 → 0.40。5 ステップすべて完走、emcc rc=0、`spill37_1169.tsv` は results/ と一致
- 測定後の差分: 測定 commit 以降、`tools/m11/ldfix` のコード・入力は変えていない (§5 の `git diff`)

| 項目 | 修復前 | 修復後 (fix_d17.py) |
|---|--:|--:|
| spill 宛 CELL_COLLAPSED site | 37 | 37 |
| spill 宛 CELL_COLLAPSED 関数 | 22 | 22 |
| store 宛 CELL_COLLAPSED site | 86 | 53 |
| store 宛 CELL_COLLAPSED 関数 | 49 | 28 |
| alg3 flagged 関数 | 77 | 58 |

- `fixed_fns=24 fixed_cells=29` (`fix_d17.py`)。spill 宛の集合は修復前後で同一 (`spill37_1169.py` が 2 本の audit JSON で一致を確認)。`fix_d17.py` は store 宛 (`frame=False`) だけを対象とするため、spill 宛は変わらないのが想定どおり
- 修復前後の store 宛の値 (86→53・49→28) は `REPORT_968.md` §2 と一致する

## 2. 判定対応 (受入 1)

集合は audit_lsf_ssa.py の定義 (frame=true かつ cell.verdict=CELL_COLLAPSED) の 37 site。全 37 site が `results/spill178_1161.tsv` (#1161 の全数分類) に判定を持つ (37/37)。判定は #1161 の既存結果で、本 PR で新たに消費者を追跡したものではない。

| 判定 | site | 関数 | 扱い |
|---|--:|--:|---|
| TRUE_DROP (確定) | 24 | 17 | 修復 pass の対象 → 子 issue (§4) |
| NO_CONSUMER (確定) | 4 | 4 | 消費者なし。修復対象外 (#1161 の判定) |
| OK_LOAD (確定) | 2 | 2 | 正常。修復対象外 |
| UNDETERMINED (判定不能) | 7 | 5 | 既存 #2253 (LD-95) が担当 |

- 全 37 site の表: `results/spill37_1169.tsv` (fn・site・source・verdict・status・oracle・text)
- TRUE_DROP の関数と site: 1003c20 (1003c73)・100b890 (100b8d0)・1046a30 (10472ea・104c3f0・104c56d・104c769・104c9e6)・11f16b0 (11f1785)・1221840 (1221a63)・1221bc0 (1221c58)・1253260 (12532d6)・127fe20 (127fef3)・1280530 (12827e6)・128c320 (128ca3f)・12a4450 (12a4531)・1354630 (1354b99)・c589b0 (c5d2df・c5d343)・e4f410 (e4f4e1)・ea7ae0 (ea7c61・ea7c97・ea7cc8)・f40840 (f43266)・ff8b60 (ff8c63)
- UNDETERMINED の site: 1280530 1284dab・128c320 128cad6・128c320 128d007・128c320 128d495・128f9e0 12900c4・c343f0 c3460e・dcdde0 dcdeee (#2253 が担当)

注意 (旧版の記述の訂正): `results/drops_510.tsv` の dest=frame の 37 行は、audit の集合と 34 site しか重ならない。cf3790 の 3 site (cf387f・cf38be・cf390f) は audit では cell.verdict=CELL_DEEP で集合に入らず、126cad0 126ce03・f40840 f44154・ff8b60 ff8c15 の 3 site は drops_510 に無い。本表は audit の集合を正とした。

## 3. 修復 pass (受入 2): 本 run では未実装

- `fix_d17.py` の方式 (IR の 1 本の load を `%cellp` 経由の 2 段に割る) は spill 宛には流用できない。spill 宛は、機械語の store に対応する IR 命令が無い site を含む (下の 1003c20 の例)。
- 観察 (1003c20・TRUE_DROP・site 1003c73 `mov qword ptr [rbp + 0x38], rax`): 機械語 1003c42 `cmp dword ptr [rax + 0x794], 0` と 1003c49 `jge` の比較が、IR の `function_1003c20` (`boot_final3.ll` 845〜912 行、68 行) には無い。1003c73 に対応する store も IR に無い。IR と機械語の対応が取れていない兆候で、spill 宛の欠落を IR 側の 2 段 deref 脱落とは断定できない。
- 修復方式の決定には、TRUE_DROP 24 site ごとに「IR に対応する命令があり値が 1 段に潰れているか」「lift 段で欠落しているか」を先に判定する必要がある。後者は #2705 (LD-125) と同じ問い。判定が付かないまま pass を入れると、脱落の検出と修復の判定が循環し、silent miscompile の危険がある (#1740 の注意と同じ)。
- そのため受入 2 は未実施。修復後の残数の再測定 (受入 3 の後半) も修復 pass と同時に行う。

## 4. 未解決と起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| spill 宛 TRUE_DROP 24 site (17 関数) の修復方式の判定と修復 pass | 脱落が残る (spill 宛 CELL_COLLAPSED は 37 のまま) | 子 issue #2794 [LD-130] (本 PR で起票) |
| spill 宛 判定不能 7 site (5 関数) | 判定なし | #2253 (LD-95) |

## 5. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
bash tools/m11/ldfix/fix_d17_e2e.sh
```

判定対応だけなら audit JSON を 1 本渡す: `python3 tools/m11/ldfix/spill37_1169.py OUT.tsv AUDIT.json [AUDIT_AFTER.json]` (素材不要。audit JSON は `fix_d17_e2e.sh` の step 1 の出力)。

測定後の差分 (測定 commit 以降のコード・入力): `git diff 30860c30 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results` の出力は空 (§1 の結論を保つ)。
