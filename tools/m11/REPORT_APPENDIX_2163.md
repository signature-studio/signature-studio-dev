# REPORT_APPENDIX_2163 — #2163 の ldfix 有り再測定 (REPORT_N1415.md §8-4 の全文)

## 8-4. ldfix 有りの再測定 (#2163) による §8-1〜§8-3 の訂正
- 訂正: `c2936605` (PE パス修正) より前の commit は PE を `/home/ubuntu/...` に固定しており、この run の環境では `ldfix skip` になっていた。`035274be`・`ec79ef5c` の 861 はこの skip 条件の値で、比較の基準にできない。測定用の展開コピーだけ固定パスを `FL_WIN64_DIR` の PE に置き換え (commit しない) て ldfix を有効にし、gen ログで `ldfix skip` が 0 件なのを確認した。
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
| `9952e605^2` | 枝の先端側の親 (`f39a9e3b^2` の祖先) | 862 | 32 | 47 | |
| `9952e605^1` | merge の main 側の親 (`03692a0c` を含む) | 861 | 33 | 46 | `03692a0c` と同値 |
| `9952e605` | merge: origin/main 取り込み | 866 | 28 | 47 | 862→866 の段 (merge 内、下記) |
| `f39a9e3b` | Merge PR #706 | 866 | 28 | 47 | |
| `49bca5e6` | main 側 (`9af7827f` の親) | 866 | 28 | 47 | n=2 で同値 |
| `9af7827f` | fix(m11) 10 進 inttoptr を LVA に remap (#1043) | 867 | 27 | 47 | n=2 で同値。866→867 の単独 commit (`2c77e8b0` の merge 差分と md5 一致) |
| `2c77e8b0` | Merge PR #1256 | 867 | 27 | 47 | |
| `35c3425b` | Merge PR #1326 | 867 | 27 | 47 | |
| `3bdae05d` | Merge PR #1316 | 868 | 26 | 47 | 867→868 |
| `4778dff5` | origin/main (本 PR の起点) | 868 | 26 | 47 | |

- merge `9952e605`: 親 `9952e605^1` (main 側) = 861 と `9952e605^2` (枝側) = 862 の両方から 866 になる。`03692a0c` (861) は main 側にあり、枝の 47b260 転記 (`m11_ov.c` +23) はこの merge の main 側で既に 861 に効いている。+5 を起こす commit は merge 内の枝側 (`9952e605^2` の祖先のうち `9952e605^1` に無いもの) で、未分解。
- main 側の 856→862 は `5ee72b93` 単独 commit (`git diff --stat 8afdc9e1 5ee72b93 -- tools/m11` は 84 行。親 `8afdc9e1` は 856)。
- 866→867: `9af7827f` 単独 (67 行)。n=2 で同値。
- 867→868: `3bdae05d` 単独 (PR #1316 merge の code 変更 1 件)。
- 未測定の中間 commit (`be764c40`・`2b99366a` ほか) は本節の対象外。

- 測定 commit: `4778dff5` (origin/main)。HEAD までの差分 0 の確認: 本 PR の HEAD は `4778dff5` の子孫で、本 PR の差分は `tools/m11/REPORT_N1415.md` の追記のみ。
  - `git diff --stat 4778dff5 HEAD -- tools/m11 tools/shim tools/shared tools/m6` の出力は空 (本 PR で code を変えないため)。よって上の表の `4778dff5` の値は HEAD の値として扱ってよい。

- 未解決 (起票先: 親 #1597): (a) merge `9952e605` の枝側 (`9952e605^2` 862 → 866) の commit 単位の切り分け、(b) `e07cc83f`〜`2c77e8b0` 間の未測定 commit、(c) n=1 の commit (`e07cc83f`・`35c3425b` 等) の n=2 再測。
