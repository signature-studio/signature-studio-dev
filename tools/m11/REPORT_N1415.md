# REPORT_N1415 — #1415 (M11-N90): snapshot IR と再生成 IR の差の段ごとの切り分け

既知類型との関係: DEFECTS.md の類型は新規確定しない。該当なし。

## 1. 結論
- (c) の段の切り分け: **部分達成**。snapshot IR (`69c774de…`) と ldfix0 再生成 IR (`25e931f2…`) の差は、`m11_gen_ir2.sh` の **ldfix 段** (`ldfxr`・`ldfxc`) と、`alloca [N x i64]` の出所 (§4) の 2 段で生じる。`boot_all.ll`・`boot_allfx.ll` (merge・numfix・asmfix) までは snapshot と sha256 が完全一致する。両者は同じ `boot{0..4}.lift.ll` を入力にしているため、lift 段の差は本測定の範囲に無い。RetDec を再実行した lift 段の再現 (`--full`) は未実施。snapshot の `ldfxc` 差 (54 件) は **`b5eeb322` (#736・F3c-block の値 store 門) で生じる**。その直前の `7db8953b` の ldfix で snapshot の `ldfxc` 66 行と完全一致し、`b5eeb322` 以降は 12 行 (§3-2)。
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
- snapshot と ldfix1 の差: `ldfxr` は両方 3,027 件で一致。`ldfxc` は snapshot 66 件・ldfix1 12 件で一致しない。ldfix1 の `ldfix_report` は `F1(load_dropped)=902`・`F1v=4`・`F2=30`・`F3a=3`・`F3b=5`・`F3c=36` (errors 0)。

### 3-2. `ldfxc` 54 件の出所 (#1739・実測)
- 方法: 同一の pre-ldfix IR (`M11_LDFIX=0` で生成・`25e931f2…`) に、`ldfix.py` を変えた 16 commit (`git log 7dc07f40..origin/main -- tools/m11/ldfix/ldfix.py`) のそれぞれを `git archive <commit> tools/m11` の展開先で実行し、`ldfxc` を含む行数と snapshot との差を数えた。
- 測定 commit: `576c4976` (origin/main HEAD)。`ldfix.py` は `5b6d03c2` と HEAD で同一 (`git diff 5b6d03c2 HEAD -- tools/m11/ldfix/ldfix.py` は空)。ldfix 段の結果は HEAD と同じ。
- 結果 (`grep -c ldfxc`・snapshot の `ldfxc` 行は 66):

| commit | 内容 | `ldfxc` 行 | snapshot との差 |
|---|---|---|---|
| `d7a04be8` `95054de6` `3162415b` `3f1d7b8b` `0e7a240a` `7be6bab5` `8a6dcf4b` `7db8953b` `1e3e499a` | #736 より前 | 66 | 0 |
| `b5eeb322` | #736 F3c-block の値 store 門 | 12 | 54 |
| `ec1326d2` `7aa4f6a9` `c5e6944c` `1af9cad2` `5b6d03c2` (HEAD の ldfix.py と同一) | #736 以降 | 12 | 54 |

- `e6066afc` は `ldfix.py` の `NameError` (`a` 未定義) で終了し、出力が無い。対象外。
- `1e3e499a` は #736 より前の枝を取り込んだ merge で、`b5eeb322` を含まない。66 行を出すのはこのため。
- 差の 54 行は 12 関数 (`5c1030`・`607b90`・`6088a0`・`60f010`・`6214a0`・`737d10`・`73b300`・`7cbc20`・`7ff6e0`・`840720`・`d243c0`・`e404e0`) の `load i64 [%argN]` 修復。`ldfix/REPORT_736.md` §3 がこの 12 関数を「戻り値 reg へのコピーだけを修復していた誤修復」と記録し、門で外している。よって `ldfxc` 54 件は誤修復の除去で、snapshot 生成時の ldfix 版は #736 より前の版。
- 注: `ldfxc` 行の一致は ldfix 段のみの切り分け。snapshot と HEAD の IR 全体は一致しない (`alloca` 54 件 (§4) と `ldfxr` 番号の繰り上がり等が残る。`ldfxc` 以外の残差は本節の対象外)。

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
| (b) 旧 build (`d6a17b64`) → HEAD で ok 818 → 868 (+50) の二分探索 (commit 727 件が対象) | 過去数値の解釈 | #1597 ([M11-N103]) |
| (d) `m11_e2e.sh` 既定経路の再通し: `functions_dll.csv` (Ghidra 12.1.4 headless・約 10 分) の作成と、e2e 全体の実測 | 受入 (e2e 検証) | #1598 ([M11-N104]) |
| (解決) ldfix1 と snapshot の `ldfxc` 差 54 件 → `b5eeb322` (#736) で生じると §3-2 で特定 | — | #1739 で完了 |
| `159d9fc0` (R8) が snapshot IR の alloca 54 件 → 2,408 件を生む件の survey 影響の実測 (ok/trap が変わるか) | R8 の採否 | #132 (R8 の起票元) |

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

## 8. #1597 (M11-N103) の二分結果: ok 862→866・866→868 の変化点 (#2163)
- 測定の条件: 各 commit で `git archive <commit> tools/m11 tools/shim tools/shared tools/m6` を展開し、work-m11 の lift 中間物 (`boot0..6.lift.ll`) と `m11_image.bin` だけ外から置く。`M11_LDFIX=1 bash m11_gen_ir2.sh` → `m11_data_gen.py` → `m11_image_gen.py` → `M11_QSTORE=0 bash m11_build.sh` → `node m11_survey.mjs`。`FL_WIN64_DIR` は fl-win64 の PE 1 member。`m11_data.c` と `m11_image.bin` は commit ごとに作り直す (`m11_e2e.sh` と同じ順)。
- 環境: 4 vCPU。Node v22.23.3。1 commit の測定は gen 18〜83 秒・build 13〜51 秒・survey 8〜31 秒 (2〜4 並列で実行したため、時間は並列数で変わる)。load average は直列測定時 0.66 (`uptime`)、並列時は未記録。
- 測定 commit (本 PR の起点): `6444b186` (main)。HEAD までのコード差分: `git diff 6444b186 HEAD -- tools/m11 tools/shim tools/shared` は空。

### 8-1. 変化点の特定 (survey, n=1 を基本。再現確認は下記)
| commit | 内容 | ok | trap | miss |
|---|---|---|---|---|
| `03692a0c^` (= `8d883c3b`) | PR #706 の枝の起点 | 861 | 34 | 46 |
| **`03692a0c`** | `fix(m11): 47b260 TList Add の disp=0 deref 脱落を C 転記で修復 (D4, #682)` | **866** | 29 | 46 |
| `c922c193`・`bb3b7d58`・`bc7d9e97`・`8be7b5de`・`36bdd5ab`・`9952e605`・`2b793aee`・`05bd1ffc`・`08f948fc` | PR #706 の枝 (03692a0c 以降) | 866 | 28〜29 | 46〜47 |
| `f39a9e3b` | Merge PR #706 | 866 | 28 | 47 |
| `f39a9e3b^1` | main 側 (枝の直前) | 862 | 32 | 47 |
| `ef34c29f` (merge-base) | — | 862 | 32 | 47 |

- **862→866 を起こす commit は `03692a0c`**。その直前 `03692a0c^` は 861 で、枝の上では 861→866 (+5)。`03692a0c` の差分は `tools/m11/m11_ov.c` の +23 行 (`function_47b260` の C 転記) のみ。
  ```
  $ git diff --stat 03692a0c^ 03692a0c -- tools/m11
   tools/m11/m11_ov.c | 23 +++++++++++++++++++++++
   1 file changed, 23 insertions(+)
  ```
  差分本文 (`git diff 03692a0c^ 03692a0c -- tools/m11`) は `function_47b260` の C 転記 (`#if M11_FIX_682` で囲まれた 23 行、`m11_ov.c` の 480 行付近)。
- 注: main 側の 862 (`f39a9e3b^1`) と枝の起点の 861 は一致しない。code 変更を含む first-parent 列で見ると、`035274be` (861) の次の code 変更 commit `04fafae6` (Merge PR #701 `134-m11-stage6`) で 862 になる。この merge の内部 commit 単位の切り分けは未実施。
- 再現確認: `03692a0c` 866 / `03692a0c^` 861 を再実行して同値 (n=2)。

### 8-2. ok 866→867→868 の変化点 (`e07cc83f`〜`3bdae05d`)
first-parent で `e07cc83f`〜`3bdae05d` を測った (merge 単位、各 n=1)。

| commit | 内容 | ok | trap | miss |
|---|---|---|---|---|
| `e07cc83f` | Merge PR #1243 (878-m11-815e10-ir) | 866 | 28 | 47 |
| `2c77e8b0` | Merge PR #1256 (1043-m11-n61-vabig-409470) | **867** | 27 | 47 |
| `902f1132` | Merge PR #1244 (410-m11-x64c-regression-rerun) | 867 | 27 | 47 |
| `8bc34ed9` | Merge PR #1242 (1041-negctl-594-precondition)。`b6e4eb42`・`902f1132` の祖先で first-parent 列の外 | 866 | 28 | 47 |
| `b6e4eb42` | Merge PR #1261 (882-m11-oob-95-895-recheck-8bc34ed9) | 867 | 27 | 47 |
| `35c3425b` | Merge PR #1326 (1134-ldfix-root-cause) | 867 | 27 | 47 |
| `3bdae05d` | Merge PR #1316 (1096-m11-enumdisplaymonitors-callback) | **868** | 26 | 47 |
| `6444b186` (HEAD) | — | **868** | 26 | 47 |

- first-parent 上の code 変更 commit の列: `e07cc83f`(866) → `2c77e8b0`(867) → (途中 14 件は未測定。902f1132・b6e4eb42 は 867 と測定済み) → `35c3425b`(867) → `3bdae05d`(868)。`e07cc83f`→`2c77e8b0` の間に code 変更 commit は無いので、**866→867 の変化点は `2c77e8b0` の merge の差分**。`35c3425b`→`3bdae05d` の間は code 変更 commit が `3bdae05d` の 1 件だけなので、**867→868 の変化点は `3bdae05d`**。
- `8bc34ed9` (866) は `e07cc83f` (866) の祖先で、`b6e4eb42` (867) の枝にも含まれる。merge 単位の表は祖先関係どおりに並べていないため、時系列の単調性は主張しない。`b6e4eb42` (867) の内部で 867 を起こす commit は未分解。
  - `e07cc83f`→`2c77e8b0` の間は first-parent 上 18 merge。`2c77e8b0` の内側は未分解。
  - `35c3425b`→`3bdae05d` は first-parent 上 1 merge (`3bdae05d` 自身)。`3bdae05d` 単独で 867→868。


### 8-3. 検証範囲 / 未解決
- 範囲: 本 runner・1 ホスト・PE 1 member・各 commit n=1 (`03692a0c`・`03692a0c^` のみ再実行して n=2、同値)。
- 未解決 (起票先: 親 #1597): (i) `04fafae6` (Merge PR #701) の内部 commit 単位の切り分け (861→862 の起点)、(ii) `2c77e8b0`〜`35c3425b` の間の code 変更 commit 14 件 (未測定。`902f1132`・`b6e4eb42` は 867 と測定済み)。受入条件の範囲外。
