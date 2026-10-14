# REPORT_N1415 — #1415 (M11-N90): snapshot IR と再生成 IR の差の段ごとの切り分け

既知類型との関係: DEFECTS.md の類型は新規確定しない。該当なし。

## 1. 結論
- (c) の段の切り分け: **部分達成**。snapshot IR (`69c774de…`) と ldfix0 再生成 IR (`25e931f2…`) の差は、`m11_gen_ir2.sh` の **ldfix 段** (`ldfxr`・`ldfxc`) と、`alloca [N x i64]` の出所 (§4) の 2 段で生じる。`boot_all.ll`・`boot_allfx.ll` (merge・numfix・asmfix) までは snapshot と sha256 が完全一致する。両者は同じ `boot{0..4}.lift.ll` を入力にしているため、lift 段の差は本測定の範囲に無い。RetDec を再実行した lift 段の再現 (`--full`) は未実施。snapshot の ldfix 版と現 ldfix 版の `ldfxc` 差 (54 件) は未切り分け (§6)。
- `alloca [N x i64]` の 54 件 (snapshot) と 0 件 (ldfix0 再生成) の差: **`159d9fc0` (alloca pass R8 の追加) で生じる**。R8 導入前の `m11_alloca.py` (`159d9fc0~1`) を ldfix1 再生成 IR に当てると `alloca [N x i64]` は **54 件** で snapshot と一致する (§4)。現 HEAD の `m11_alloca.py` は 2,408 件を生む。
- (b) ok 818 → 868 (+50) の二分探索: **未着手** (commit 727 件が対象。本 run の残り時間では不可)。子 issue に切り出す (§6)。
- (d) `m11_e2e.sh` 既定経路の再通し: **未達**。`functions_dll.csv` は素材に無く、Ghidra 12.1.4 (`[GHIDRA]` 無し) の取得と headless 実行 (約 10 分) を本 run で行う時間が無かった。子 issue に切り出す (§6)。

受入条件の充足: (a)(c) は達成、(b)(d) は未達。issue は `Refs #1415`。

## 2. 測定の条件
- 測定 commit: `cb3a89a6` (origin/main)。コード変更なし。本 PR は REPORT のみ追加。
- 素材: `work-m11` (`tools/m11/work/` に展開、gitignore)・`fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`・1 member)。展開先は FL_WIN64_DIR (`[WIN64]` 参照)。
- 環境: 4 vCPU, 15 GiB, capstone 5.0.7 / pefile 2024.8.26。
- 作業: `ws-1415` worktree (ブランチ `1415-m11-lift-origin`)。

## 3. 段ごとの sha256 (実測)
`work/snap/` は snapshot 退避先 (gitignore)。

| 段 | snapshot (`work-m11`, 10-10 生成) | 再生成 ldfix0 (`M11_LDFIX=0`) | 再生成 ldfix1 (既定) |
|---|---|---|---|
| `boot_all.ll` (merge・numfix) | `24107dae…` (491,197 行) | 同左 (一致) | 同左 (一致) |
| `boot_allfx.ll` (asmfix) | `2aaa7a2c…` | 同左 (一致) | 同左 (一致) |
| `boot_final.ll` (passes・genstubs・dotfix・fnclex0) | `69c774de…` (490,653 行) | `25e931f2…` (491,108 行) | `2c68ceae…` (490,693 行) |

- `boot_all.ll` の sha256 の訂正: 旧記載の `3292943d…` は誤り。repo 内・`work-m11` 内に該当ファイルは無く、出典の build は特定できない。現 HEAD の `m11_merge.py` を `boot{0..4}.lift.ll` に掛け、`m11_gen_ir2.sh` と同じ numfix 置換 (`@<数値>` → `@m11num_<数値>`) を行うと、出力は snapshot と `cmp` で完全一致する (`24107dae…`・491,197 行)。
- ldfix0 と ldfix1 は REPORT_N1165 §3-2 の `25e931f2…` / `2c68ceae…` と一致する。
- snapshot と ldfix0 の差: diff の変更行 7,237 行。`ldfxr` は snapshot 3,027 件・ldfix0 0 件。`ldfxc` は snapshot 66 件・ldfix0 0 件。ldfix 段が差の一因。
- snapshot と ldfix1 の差: `ldfxr` は両方 3,027 件で一致。`ldfxc` は snapshot 66 件・ldfix1 12 件で一致しない。ldfix1 の `ldfix_report` は `F1(load_dropped)=902`・`F1v=4`・`F2=30`・`F3a=3`・`F3b=5`・`F3c=36` (errors 0)。ldfix の変換差 (`ldfxc` 54 件) は、snapshot 生成時の ldfix 版との差として残る (未切り分け)。

## 4. `alloca [N x i64]` の出所
| IR | `alloca [N x i64]` 件数 |
|---|---|
| snapshot `boot_final.ll` | 54 |
| ldfix0 再生成 | 0 |
| ldfix1 再生成 | 0 |
| ldfix1 再生成 + 現 HEAD `m11_alloca.py` (`159d9fc0` 以降) | **2,408** |
| ldfix1 再生成 + `159d9fc0~1` の `m11_alloca.py` (R8 導入前) | **54** |

- 再生成 IR は `m11_gen_ir2.sh` 段では alloca 拡幅を持たず、`alloca [N x i64]` は 0 件。拡幅は `m11_build.sh` 側の `alloca/m11_alloca.py` が行う (`m11_build.sh` L84〜88)。
- 旧版 pass (R1〜R7・R8 無し) の件数 54 は snapshot の 54 と一致。`159d9fc0` (R8: escape gap の拡幅) が R7 の 39,006 件に加えて 4,077 件 (`R8_escape_gap`) を拡幅し、件数が 54 → 2,408 に増える。
- snapshot は R8 導入前の pass で作られた IR と推定される (`work-m11` の生成は 10-10、`159d9fc0` は 10-12)。

## 5. 検証範囲 / 範囲外
- 範囲: 本 runner の 1 ホスト・PE 1 member・n=1 (各段は決定的に再現)。
- 範囲外: (b) 二分探索・(d) e2e 再通し・ldfix の判定 (ldfix1 の survey 値は本 run で測らない)。
- 本 run で survey (m11_survey) は実行していない。`ok` 値は本節に載せない。

## 6. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| (b) 旧 build (`d6a17b64`) → HEAD で ok 818 → 868 (+50) の二分探索。§8 の結果: 861→862 は `5ee72b93` (414ad0/43a3f0 転記)、862→866 は `f39a9e3b` (47b260 転記 = #682)、866→868 は未特定 | 過去数値の解釈 | #1597 ([M11-N103]) の部分達成 + 子 issue (§8) |
| (d) `m11_e2e.sh` 既定経路の再通し: `functions_dll.csv` (Ghidra 12.1.4 headless・約 10 分) の作成と、e2e 全体の実測 | 受入 (e2e 検証) | #1598 ([M11-N104]) |
| ldfix1 と snapshot の `ldfxc` 差 54 件 (snapshot 66・ldfix1 12) の切り分け | (c) の ldfix 段の完全な特定 | #1415 に残す (本 PR で部分達成) |
| `159d9fc0` (R8) が snapshot IR の alloca 54 件 → 2,408 件を生む件の survey 影響の実測 (ok/trap が変わるか) | R8 の採否 | #132 (R8 の起票元) |

## 8. (b) 二分探索の結果 (#1597・部分達成)
- 測定 commit: 各行の commit ごとに `git archive <commit> tools/m11 tools/shim tools/shared` を展開し、work-m11 の lift 成果物から IR を再生成 (`m11_gen_ir2.sh`, `M11_LDFIX=1`, `M11_QSTORE=0`) → `m11_build.sh` → `m11_survey.mjs`。PE は fl-win64 の `block00031_PE.bin` (sha256 `b2c64da4…`)。n=1。4 vCPU。load 0.8〜1.3。
- 対象列: `git rev-list --first-parent d6a17b64..origin/main -- tools/m11 tools/shim tools/shared` の 221 件 (`4c3f7458` 時点の main 上)。
- 実測 (survey の ok/miss/trap):

| commit | ok | miss | trap | 備考 |
|---|---|---|---|---|
| `d6a17b64` | 861 | 46 | 34 | 旧 base。ldfix 適用済みで再生成 |
| `035274be` | 861 | 46 | 34 | PR #700 直前 |
| `c2936605` | 856 | 46 | 38 | PE パス修正 (#134)。`035274be` では ldfix が skip されていた (PE が `/home/ubuntu` 固定) |
| `8afdc9e1` | 856 | 46 | 39 | boot5 (#132) |
| `5ee72b93` | 862 | 47 | 32 | 414ad0・43a3f0 の転記 (#134) |
| `51d64326` | 862 | 47 | 32 | |
| `5249d12e` | 862 | 47 | 32 | PR #703 merge |
| `f39a9e3b` | 866 | 47 | 28 | 47b260 の転記 (#682, `m11_ov.c` +29 行 ほか) |
| `04fafae6` | 862 | 47 | 32 | PR #701 merge (列上では 861 → 862 の境界) |
| `35c3425b` | 867 | 47 | 27 | |
| `4c3f7458` | 868 | 47 | 26 | issue の HEAD 値と一致 |

- 注意 1: issue 本文の 818 と前回コメントの 856 は、本 run の測定と一致しない。本 run の `d6a17b64` は 861 (ldfix 有り)。基準は 861 とする。
- 注意 2: 列は path 絞りの rev-list で線形ではない。二分探索は `04fafae6`(862) と `f39a9e3b`(866) の順に並ばない箇所がある (`5249d12e` 862 → `f39a9e3b` 866)。結果は単調ではない前提で読む。
- 注意 3: `035274be` (861) と `c2936605` (856) の差は ldfix の有無 (PE パス) と数えた。測定条件が途中で変わるため、ここを 1 段と数えない。
- 結論: 861→862 は `5ee72b93` (`414ad0`/`43a3f0` の転記, #134)。862→866 は `f39a9e3b` (`47b260` の転記, #682)。866→868 (+2) は未特定 (`f39a9e3b`〜`4c3f7458` の間)。

## 7. 再現
```sh
# work-m11 を repo ルートで展開 (アーカイブ内のパスは tools/m11/work/ を含む)
tar --zstd -xf work-m11.tar.zst -C .
# fl-win64 の PE 1 member
tar --zstd -xf fl-win64.tar.zst -C "$FL_WIN64_DIR" extracted/block00031_PE.bin
cd tools/m11
mkdir -p work/snap && cp -p work/boot_all.ll work/boot_allfx.ll work/boot_final.ll work/snap/
FL_WIN64_DIR=<FL_WIN64_DIR の展開先> M11_LDFIX=0 bash m11_gen_ir2.sh    # ldfix0 → 25e931f2…
FL_WIN64_DIR=<FL_WIN64_DIR の展開先> bash m11_gen_ir2.sh                # ldfix1 → 2c68ceae…
python3 alloca/m11_alloca.py work/boot_final.ll out.ll --report r.json   # 2,408 件
```
