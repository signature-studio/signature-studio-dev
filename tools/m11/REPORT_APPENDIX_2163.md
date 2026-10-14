# REPORT_APPENDIX_2163 — #2163 の ldfix 有り再測定 (REPORT_N1415.md §8-4 の全文)

## 8-4. ldfix 有りの再測定 (#2163) による §8-1〜§8-3・§9 の訂正
- 訂正: `c2936605` (PE パス修正) より前の commit は、`tools/m11/m11_gen_ir2.sh` の `PE=` 行が旧 ubuntu 環境の固定パスを指しており、この run の環境では `ldfix skip` になっていた。`035274be`・`ec79ef5c` の 861 はこの skip 条件の値で、比較の基準にできない。測定用の展開コピーだけ固定パスを `FL_WIN64_DIR` の PE に置き換え (commit しない) て ldfix を有効にし、gen ログで `ldfix skip` が 0 件なのを確認した。
- 測定: 各 commit を `git archive <commit> tools/m11 tools/shim tools/shared tools/m6` → `work-m11` の lift 成果物 + `M11_LDFIX=1 m11_gen_ir2.sh` → `m11_data_gen.py` → `m11_image_gen.py` → `M11_QSTORE=0 m11_build.sh` → `m11_survey.mjs`。fl-win64 の PE sha256 `b2c64da4…` (REPORT §8 と一致)。4 vCPU、load 0.76〜1.20。

| commit | 内容 | ok | trap | miss | 備考 |
|---|---|---|---|---|---|
| `035274be` | Merge PR #700 (main 側) | 856 | 38 | 46 | ldfix 有り。§8-1 の 861 は skip 条件の値 |
| `ec79ef5c` | main 側 (枝の親) | 856 | 38 | 46 | ldfix 有り |
| `8afdc9e1` | fix(m11) restore indirect call (#132) | 856 | 39 | 46 | |
| `c2936605` | fix(m11) PE パス修正 (#134) | 856 | 38 | 46 | |
| `5ee72b93` | fix(m11) _LStrSetLength/IntToStr 転記 (#134) | 862 | 32 | 47 | main 側の 856→862 段。単独 commit |
| `13e8962f`・`6654322b`・`de50ffa7`・`078fe56c` | #134 の判定・記録・ICALL 修正 | 862 | 32 | 47 | 変化なし |
| `04fafae6` | Merge PR #701 | 862 | 32 | 47 | |
| `03692a0c^` | 枝の起点 (PR #706) | 856 | 38 | 46 | |
| `03692a0c` | fix(m11) 47b260 TList Add 転記 (#682) | 861 | 33 | 46 | 枝の 856→861 段。`m11_ov.c` +23 |
| `f39a9e3b^1` | main 側 (枝の直前) | 862 | 32 | 47 | |
| `9952e605^1` (= `36bdd5ab`) | merge の枝側の親 (PR #706 の枝。`03692a0c` を含む) | 861 | 33 | 46 | `03692a0c` と同値。code 差分も 0 |
| `9952e605^2` (= `8d640675`) | merge の origin/main 側の親 (`5ee72b93`・`04fafae6`・`035274be` を含む) | 862 | 32 | 47 | |
| `9952e605` | merge: origin/main 取り込み | 866 | 28 | 47 | 862→866 は `03692a0c` (下記) |
| `f39a9e3b` | Merge PR #706 | 866 | 28 | 47 | |
| `49bca5e6` | main 側 (`9af7827f` の親) | 866 | 28 | 47 | n=2 で同値 |
| `9af7827f` | fix(m11) 10 進 inttoptr を LVA に remap (#1043) | 867 | 27 | 47 | n=2 で同値。866→867 の単独 commit (`2c77e8b0` の merge 差分と md5 一致) |
| `2c77e8b0` | Merge PR #1256 | 867 | 27 | 47 | |
| `35c3425b` | Merge PR #1326 | 867 | 27 | 47 | |
| `3bdae05d` | Merge PR #1316 | 868 | 26 | 47 | 867→868 |
| `4778dff5` | origin/main (本 PR の起点) | 868 | 26 | 47 | |

### merge `9952e605` の 862→866 (受入 1)
- 親の向き (git の事実): `9952e605^1` = `36bdd5ab` は枝 (PR #706 の枝)、`9952e605^2` = `8d640675` は origin/main 側 (Merge PR #633)。`git log 9952e605^2..9952e605^1` は `03692a0c` と文書 commit 5 件だけ。`git rev-list --count 9952e605^1..9952e605^2` は 279 で、すべて main 側の commit。`git diff --stat 03692a0c 9952e605^1 -- tools/m11 tools/shim tools/shared tools/m6 ':!tools/m11/REPORT*.md' ':!tools/m11/trap_triage'` は空 (枝側の親の code は `03692a0c` と同じ)。
- **862→866 を起こす commit は `03692a0c`** (枝の `function_47b260` C 転記)。`9952e605^2` (862) → `9952e605` (866) の code 差分は `m11_ov.c` +23 行だけで、ほかは `trap_triage/` の triage スクリプトと文書。この `m11_ov.c` の +/- 行は `03692a0c^..03692a0c` の差分と md5 が一致する (`eb4f6edb…`)。
  ```
  $ git diff --stat 9952e605^2 9952e605 -- tools/m11 tools/shim tools/shared tools/m6 ':!tools/m11/REPORT*.md'
   tools/m11/m11_ov.c                       |  23 ++++
   tools/m11/trap_triage/REPORT_682.md      | 177 +++++++++++++++++++++++++++++++
   tools/m11/trap_triage/chain_682.sh       |  14 +++
   tools/m11/trap_triage/check_682.py       |  23 ++++
   tools/m11/trap_triage/negctl_682.sh      |  14 +++
   tools/m11/trap_triage/store_watch_682.sh |  26 +++++
   tools/m11/trap_triage/watch_store_682.c  |  31 ++++++
   tools/m11/trap_triage/watch_store_682.py |  80 ++++++++++++++
   8 files changed, 388 insertions(+)
  ```
- 数の整理: `03692a0c` の効果は 856 起点 (`03692a0c^` → `03692a0c`) で +5 (856→861)、862 起点 (`9952e605^2` → `9952e605`) で +4 (862→866)。起点で 1 差が出る。856 から両方を取り込んだ merge は 866 (+10) で、`5ee72b93` (856→862, +6) と `03692a0c` (856→861, +5) の和 +11 より 1 小さい。同じ unit を両方が ok にした可能性があるが、unit の特定は未実施 (survey の unit 別出力を比べていない)。`9952e605^1` (861) → `9952e605` (866) の +5 は main 側の取り込み分。
- `f39a9e3b^1` (862) → `f39a9e3b` (866) の code 差分も `m11_ov.c` +29 行のみ (ほかは `trap_triage/` の triage スクリプトと文書。`03692a0c` の +23 と、`2b793aee` の +7/-1 (store 計装の `M11_FIX_682` 対応。ok は `9952e605` と `f39a9e3b` で同値の 866) の差し引き +6 の合計)。

### その他の段
- main 側の 856→862 は `5ee72b93` 単独 commit (`git diff --stat 8afdc9e1 5ee72b93 -- tools/m11` は 84 行。親 `8afdc9e1` は 856)。
- 866→867: `9af7827f` 単独 (67 行)。n=2 で同値。
- 867→868: `3bdae05d` 単独 (PR #1316 merge の code 変更 1 件)。
- 未測定の中間 commit (`be764c40`・`2b99366a` ほか) は本節の対象外。

### §8-1〜§8-3・§9 の値の扱い
- PE が固定パスのまま (`c2936605` を祖先に持たない) の commit は、skip 条件の値の可能性がある。該当は `03692a0c^`〜`36bdd5ab` の枝の commit・`d6a17b64`・`035274be`・`ec79ef5c`。
- 本節で再測した `035274be`・`03692a0c^`・`03692a0c`・`36bdd5ab` は 856・856・861・861 で、§8-1/§9 の 861・861・866・866 と異なる。
- `d6a17b64` (§9 の 861、「ldfix 適用済み」の記載) は未再測。`d6a17b64:tools/m11/m11_gen_ir2.sh` の `PE=` 行が旧 ubuntu 環境の固定パスで `035274be` と同形のため、skip 条件の値の可能性がある。
- 本節と §8-1/§8-2/§9 の両方で測った commit のうち `c2936605` を祖先に持つもの (`8afdc9e1`・`c2936605`・`5ee72b93`・`04fafae6`・`f39a9e3b^1`・`9952e605`・`f39a9e3b`・`2c77e8b0`・`35c3425b`・`3bdae05d`) は値が一致する。

### 測定 commit と HEAD の差分
- 測定 commit: `4778dff5` (origin/main)。本 PR の差分は `tools/m11/REPORT_N1415.md` の追記・`tools/m11/REPORT_APPENDIX_2163.md` の新規追加・`docs/DOC_MAP.md` の索引更新の文書のみ。
- `git diff --stat 4778dff5 HEAD -- tools/m11 tools/shim tools/shared tools/m6 ':!tools/m11/REPORT*.md'` の出力は空 (実行される code の差分 0)。REPORT を除かない同じ pathspec では上記 2 ファイルの追加行だけが出る。よって上の表の `4778dff5` の値は HEAD の値として扱ってよい。

### 未解決 (起票先: 親 #1597)
- (a) `03692a0c` の効果が起点で +5 / +4 と 1 差になる理由 (どの unit が `5ee72b93` と重なるか)。
- (b) `e07cc83f`〜`2c77e8b0` 間の未測定 commit。
- (c) n=1 の commit (`e07cc83f`・`35c3425b` 等) の n=2 再測。
- (d) `d6a17b64` の ldfix 有り再測。
