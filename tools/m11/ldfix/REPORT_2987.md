# REPORT #2987 — ddf630 の TRUE_DROP 4 site の IR 修復 pass (LD-143)

親: #2838 (LD-135)。前提の #2921 (LD-138・PR #2962) は 2026-10-14 に merge 済み。
既知類型との関係: `REPORT_2921.md` §冒頭と同じ (m11 の D17。`docs/DEFECTS.md` の ID は付けない)。

## 0. 結論

- 修復 pass `fix_spill_deep_2987.py` を実装した。ddf630 の 1 段 load 2 本 (429019・429020) に 2 段目の deref を補い、対象 4 site を覆う。store 宛の複写 (429862・430849) は、複写元の値が 2 段になるため IR の行は変えていない。
- 修復前後で spill 宛の確定数・脱落関数の和集合は変わらない (§3)。判定が候補判定に基づき、audit の cell 判定 (CELL_DEEP) も修復前後で同じだから。
- **未解決**: 2 段目の値 `[V]` の確認 (`REPORT_2921.md` §4 の宿題) は完了していない。静的イメージを読むと、`REPORT_2921.md` の値と違う結果になった (§4)。この修復は既定の m11 build に配線しない。
- 受入条件 1〜3 は満たした。ただし「根拠なしの修復は入れない・先に値を確認する」の注意は満たせていないため `Refs #2987` とする。

## 1. 測定条件

- 測定 commit: `e4ff48a29` (コードを変えた最後の commit: `fix(m11): repair CELL_DEEP TRUE_DROP ddf630 cells with 1-to-1 gate (#2987)`)。基点 `origin/main` = `e4c52eadd`。作業 worktree `ws-2987` (branch `2987-ld143-ddf630-ir-repair`)。
- 素材: `work-m11` と `work-liftdiff` を `tar --zstd -xf` で `tools/m11/work/`・`tools/liftdiff/work/` に展開 (gitignore 対象)。`fl-win64` は e2e が使わないため未展開。
- 実行: `TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground、`timeout 900`)。
- 実測 (測定 commit `e4ff48a29`): rc=0、real **2m59.19s**、load average (1 分) 0.63 → 0.98。同じ e2e をコミット前の作業ツリーで 1 回: real 2m57.97s、load 0.18 → 0.96。
- 結果: step 5 `drops_510.tsv`・step 7 `spill178_1161.tsv` は results/ と一致 (cmp)。step 6 のネガコン (NC7 を含む) は既存どおり通過。step 8 (修復後 IR の audit と spill 再生成) は `spill178_1161.tsv` と一致。
- 測定後のコード差分: 本 REPORT を追加する commit 以外は無い。`git diff e4ff48a29 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/*.sh tools/m11/ldfix/results` の出力は空 (差分 0)。

## 2. 修復の内容

`fix_spill_deep_2987.py` は `fix_spill_2794.py` の 1 対 1 gate (`judge_1to1`: 機械語で X に触れる命令がちょうど 1 つ・`mov reg,[rip+X]`・IR の `i64 K to ptr` がちょうど 1 つ・幅一致) を再利用する。違いは対象: 2794 は `CELL_COLLAPSED` だけを対象にするが、ddf630 の 4 site は幅 64 の定数 load を持ち、audit で `CELL_DEEP` に入る (alg3 = FRAME)。判定の単位はセル X。

| セル | 修復した load | 対象 site | gate | 修復の形 |
|---|---|---|---|---|
| X = `15e2318` (K = `11e2318`) | `%25 = load i64, ptr inttoptr (i64 18752280)` (429019) | ddf6b5 (→ `[rbp+0x80]`)・de0bfe (複写 → `[rbp+0xc0]`) | 1 対 1 OK (w=64) | `%cellps.11e2318 = load ptr, ptr inttoptr (i64 18752280)` / `%25 = load i64, ptr %cellps.11e2318` |
| X = `15e3c70` (K = `11e3c70`) | `%26 = load i64, ptr inttoptr (i64 18758768)` (429020) | ddf6c6 (→ `[rbp+0xb8]`)・ddff5a (複写 → `[rbp+0xa0]`) | 1 対 1 OK (w=64) | `%cellps.11e3c70 = load ptr, ...` / `%26 = load i64, ptr %cellps.11e3c70` |

- IR の差分: `boot_final3.ll` の 2 行 → 4 行 (429019・429020 の置換のみ)。関数は ddf630 の 1 つ。
- 複写 site (ddff5a・de0bfe) は IR の store (429862・430849) がそのまま `%26`・`%25` を複写するため、修復は SSA 伝播で届く。store 行は変えていない。

## 3. 修復前後の件数

| 項目 | 修復前 (`e4c52eadd` の判定・results) | 修復後 (修復 IR から再生成) |
|---|---|---|
| spill 宛 unk site / 関数 | 178 / 71 | 178 / 71 |
| status 確定 / 判定不能 / 未判定 | 147 / 30 / 1 | 147 / 30 / 1 |
| oracle CELL_DEEP / 確定 (ddf630 の 4 site を含む) | 52 | 52 |
| audit の cell 判定 (ddf630 の 4 site) | CELL_DEEP ×4 | CELL_DEEP ×4 |
| audit の関数単位の差分 (`ssa.json` 前後) | - | 0 関数 (実測) |
| 脱落関数の和集合 A ∪ B ∪ C (drops_510 の store 51 ∪ frame 22 = 69、spill 確定 TRUE_DROP で drops_510 に無い 14 を加える) | 83 | 83 |

- `REPORT_2921.md` §2 の「脱落関数の和集合 75」は、2921 の時点 (`5e0177c7`) の値。その後 `candidate_verdicts_2922.jsonl`・`2923.jsonl` が `spill_classify_1161.py` に読み込まれ、HEAD の値は 83 になった。本 REPORT の 83 は HEAD の基準値であり、2921 の 75 との差は修復の効果ではない。
- audit の cell 判定が変わらない理由: `audit_lsf_ssa.py` の `cell_check` は、幅 64 の定数 load を `CELL_COLLAPSED` にせず、alg3 が `SHALLOW` のときだけ collapse とみなす。ddf630 の alg3 は FRAME のため、1 段でも 2 段でも `CELL_DEEP` になる。つまり audit はこの修復の効果を測れない。効果の根拠は IR の差分 (§2) と e2e の cmp のみ。

## 4. 2 段目の値 (未解決)

`cell_check` と同じ座標 (イメージのファイル offset = VA − base = LVA。セル内容は LVA で書かれている。FOLDED_OK 判定が IR の LVA 定数と比べるのと同じ) で読むと:

| セル内容 V (LVA) | `[V]` (8 バイト) |
|---|---|
| `0x153fc08` (X = 15e2318) | `0000000000000000` |
| `0x153fbf8` (X = 15e3c70) | `0000000000000000` |

`REPORT_2921.md` §4 の値 (`0x5080f0170016002`・`0x600130024206`) は、V を VA として読んだ (ファイル offset = V − 0x400000) 結果と一致する。読み方の座標が 2921 と本 REPORT で違う。どちらの座標でも `[V]` は object 参照に見えない (0 または不定の値)。

- 含意: 2 段の機械語どおりなら、静的な値では消費者の `cmp dword [rax+0x14],0` が 0 を参照する。静的イメージは起動前の状態で、実行時にセルが書き換わる可能性がある。よって判定は確定できない。
- 次に必要な確認 (PM 判断・未起票): 起動時に ddf630 に入った時点のセル X と `[V]` の実値 (実行時の値)。この値が得られるまで、修復を既定経路に配線しない。

## 5. 限界・未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 2 段目の値 `[V]` の実行時の値 (§4) | 修復の意味的な正しさが未確定。既定 build への配線を止めている | #2987 (本 issue に残す。値の取得は PM 判断・未起票) |
| audit の `cell_check` が幅 64 の 1 段/2 段を区別しない | 修復の効果を audit で測れない (§3) | 未起票 (audit の規則見直しは PM 判断) |
| 修復を既定の m11 build (`m11_gen_ir2.sh`) に配線していない | 脱落関数の和集合 83 件は不変。起動・GUI への効果は未測定 | #2987 |

- 起動・GUI の KPI (FLEngine dispatch 数・通過 unit・最初のウィンドウ) は動かしていない。既定経路を変えていないため、KPI は本 PR の対象外。

## 6. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh     # 8/8 (約 3 分)
python3 tools/m11/ldfix/fix_spill_deep_2987.py tools/m11/work/boot_final3.ll $SSA tools/m11/work/m11_image.bin "tools/m11/work/boot*.drc.config.json" OUT.ll --verdicts tools/m11/ldfix/results/candidate_verdicts_2921.jsonl
diff tools/m11/work/boot_final3.ll OUT.ll   # 429019・429020 の 2 行のみ
```
