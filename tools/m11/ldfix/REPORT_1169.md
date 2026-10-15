# REPORT #1169 — D17 spill 宛 CELL_COLLAPSED 37 site の判定対応と修復 pass の判断 (LD-37)

既知類型との関係: D4 (`mov r64,[r8]` の disp=0 の 1 段 deref の脱落) と、load の脱落で値が化ける点は近い。ただし同一とは確定しない。本 REPORT は spill 宛の機構を確定せず、`docs/DEFECTS.md` の該当 ID は付けない。

親: #968 (LD-21)。本 issue は規約 (`docs/WORKFLOW.md` §3 の Closes 縮小規定) に従い範囲を縮小した。完了分は判定対応 (受入 1 の 30/37 確定 + 残りの担当付け)・残数の実測 (受入 3)・emcc 構文検証 (受入 4)。修復 pass (受入 2) は子 issue へ移した (§4)。

## 1. 測定条件

- 測定 commit: `30860c30` (コードを変えた最後の commit。判定対応の e2e 追加)。作業 worktree `ws-1169` (branch `1169-spill-frame-verdict`)
- 素材: `work-m11` (`tools/m11/work/` に展開) と `toolchain-emsdk` (`[EMSDK]` に展開)。どちらも PR 本文の `oc_artifacts:` 行で agent-setup が展開する (`docs/WORKFLOW.md` §11)。実装 run の測定は ws-1169 に素材が無かったため、`M11_WORK` で main の展開先を読んだ (読込のみ)。再現の手順は §5 の 1 通り
- 素材の性質: `work-m11` は #516 qstore 以前の生成で、現 main の生成手順と一致しない snapshot (`docs/WORKFLOW.md` §11・#680)。以下の「37 のまま」の結論はこの IR に限る。現 main の IR に対する結論ではない
- 実行: `bash tools/m11/ldfix/fix_d17_e2e.sh` (既定の `M11_WORK` = `tools/m11/work`、`TMPDIR=$RUNNER_TEMP`、foreground)。測定時は `M11_WORK=<main>/tools/m11/work` を指した
- 結果: rc=0、real 23.3 s、load average (uptime) 0.09 → 0.40。5 ステップすべて完走、emcc rc=0、`spill37_1169.tsv` は results/ と一致
- 測定後の差分: 測定 commit 以降の変更は `spill37_1169.py` の step 4 だけ (`with` での読込と引数の整理。出力は不変)。step 1〜3・5 は未変更。HEAD での e2e 再実行は、本 round では素材が無く未実施 (§5)

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
- 上の 1003c20 の IR 照合 (`function_1003c20` に 1003c42 の比較が無い) は未検証。本 round では `work-m11` が無く IR を開けなかった。素材を使える round で再確認し、結果をこの行に追記する。子 #2794 の根拠になっているため、確認が済むまで根拠の強さは未確定

## 4. 未解決と起票先

| 未解決 | 影響 | 起票先 |
|---|---|---|
| spill 宛 TRUE_DROP 24 site (17 関数) の修復方式の判定と修復 pass | 脱落が残る (spill 宛 CELL_COLLAPSED は 37 のまま) | 子 issue #2794 [LD-130] (本 PR で起票) |
| spill 宛 判定不能 7 site (5 関数) | 判定なし | #2253 (LD-95) |

## 5. 再現

素材は agent-setup が PR 本文の `oc_artifacts: work-m11 toolchain-emsdk` で展開する (`work-m11` → `tools/m11/work/`、`toolchain-emsdk` → `[EMSDK]`)。再現の手順は次の 1 通り。

```
bash tools/m11/ldfix/fix_d17_e2e.sh
```

agent-setup の外で再現するときも同じ配置にする (`tar --zstd -xf <work-m11>.tar.zst -C <repo 直下>`、`sudo tar --zstd -xf <toolchain-emsdk>.tar.zst -C [OPT-TOOLS]`)。

step 4 (判定対応) だけを試すなら audit JSON を渡す: `python3 tools/m11/ldfix/spill37_1169.py OUT.tsv AUDIT.json [AUDIT_AFTER.json]`。`results/audit_510_ssa.json` (#510 時点の snapshot。HEAD の audit の代用ではない) を入力にすると、素材なしで `results/spill37_1169.tsv` と `cmp` 一致する (本 round で 1 本・2 本の両方を確認)。

測定 commit `30860c30` から HEAD までのコード差分 (`git diff 30860c30 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results`。最後のコード commit は `8f58dc81`):

```diff
diff --git a/tools/m11/ldfix/spill37_1169.py b/tools/m11/ldfix/spill37_1169.py
index 0d92b28d..68a5d8d7 100644
--- a/tools/m11/ldfix/spill37_1169.py
+++ b/tools/m11/ldfix/spill37_1169.py
@@ -24,7 +24,8 @@ def rows(path):
 
 
 def frame_collapsed(audit_path):
-    audit = json.load(open(audit_path))
+    with open(audit_path) as f:
+        audit = json.load(f)
     out = set()
     for va, v in audit['functions'].items():
         for s in v['sites']:
@@ -37,9 +38,10 @@ def frame_collapsed(audit_path):
 def main():
     if len(sys.argv) not in (3, 4):
         sys.exit(__doc__)
-    out_path, audits = sys.argv[1], sys.argv[2:]
-    sites = frame_collapsed(audits[0])
-    for a in audits[1:]:
+    out_path, audit_path = sys.argv[1], sys.argv[2]
+    after_paths = sys.argv[3:]
+    sites = frame_collapsed(audit_path)
+    for a in after_paths:
         if frame_collapsed(a) != sites:
             print('FAIL: 修復後の audit の spill 宛 CELL_COLLAPSED 集合が修復前と不一致 (%s)' % a, file=sys.stderr)
             sys.exit(1)
@@ -59,7 +61,7 @@ def main():
     with open(out_path, 'w') as f:
         f.write('\n'.join(lines) + '\n')
     print('spill 宛 CELL_COLLAPSED site %d / 関数 %d (audit %d 本で一致)'
-          % (len(sites), len({k[0] for k in sites}), len(audits)))
+          % (len(sites), len({k[0] for k in sites}), 1 + len(after_paths)))
     for k, n in sorted(cnt.items(), key=lambda x: -x[1]):
         print('%s %s: site %d / 関数 %d' % (k[0], k[1], n, len(fns[k])))
 
```
