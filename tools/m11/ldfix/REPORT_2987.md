# REPORT #2987 — ddf630 の TRUE_DROP 4 site の IR 修復 pass (LD-143)

親: #2838 (LD-135)。前提の #2921 (LD-138・PR #2962) は 2026-10-14 に merge 済み。
既知類型との関係: `REPORT_2921.md` §冒頭と同じ (m11 の D17。`docs/DEFECTS.md` の ID は付けない)。

## 0. 結論

- 修復 pass `fix_spill_deep_2987.py` を実装した。ddf630 の 1 段 load 2 本 (429019・429020) に 2 段目の deref を補い、対象 4 site を覆う。store 宛の複写 (429862・430849) は、複写元の値が 2 段になるため IR の行は変えていない。
- 修復前後で spill 宛の確定数・脱落関数の和集合は変わらない (§3)。判定が候補判定に基づき、audit の cell 判定 (CELL_DEEP) も修復前後で同じだから。
- 2 段目の値 `[V]` の実行時の値を測った (§4・probe `dyn_ld143_2987.mjs`)。静的イメージ・survey 942 unit の後のいずれも `[V]` = 0。実 boot は完走せず、InitUnits の状態は得られない。`[V]` が object 参照かは確定できない。この修復は既定の m11 build に配線しない (配線判断は PM)。
- 受入条件 1〜3 は満たした (PR #3686)。注意の「先に値を確認する」は本 PR の測定で試みたが確定できなかった。残りは §5 の未解決に移し、`[V]` を読む受入を起票先の #3646 に追加して、本 issue は閉じる。

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

## 4. 2 段目の値 `[V]` の実行時の値 (測定 commit `af04a6a83`)

- 測定: `M11_WORK=<tools/m11/work の絶対パス> node tools/m11/ldfix/dyn_ld143_2987.mjs` (foreground、17 s、rc=0)。load average 0.34 → 0.53。素材は `work-m11` の展開 (`m11_boot.cjs`・`m11_boot.cjs.wasm`・`m11_image.bin`)。
- 座標は LVA。IR の `inttoptr (i64 18752280)` (= 0x11e2318) と同じ wasm メモリ番地で、`mod.HEAPU8.set(img, 0)` により image のファイル offset と一致する。`M11_LB_BASE` は使わない。
- 測定 commit: `af04a6a83` (コードを変えた最後の commit。survey に clobber 検出・復元を加えた)。測定後のコード差分: `git diff af04a6a83 HEAD -- tools/m11/ldfix/dyn_ld143_2987.mjs` の出力は空 (差分 0)。本 commit は REPORT だけ。
- 注意 (harness): 展開済みの `m11_boot.cjs` (2026-10-12 build) は `_m11_set_va_unit_budget`・`_m11_va_unit_begin` を export していない。emsdk が無く再 build できないため、survey は VA 予算と unit ごとの計数を掛けずに回した (両方とも export があるときだけ呼ぶ)。clobber 検出・復元は `m11_survey.mjs` と同じ判定 (unit 実行後に InitTable の先頭・末尾の VA を比べ、変わっていれば unit 実行前の image を書き戻す) を写した。ptrPre は計測用で状態を変えないため省いた。survey の trap 83 件はこの条件での値。
- 注意 (clobber 判定の範囲): 判定は InitTable の 2 件の VA だけを見る。image の他の位置 (0x14 を含む) への書き込みは clobber として検出しない。実測で `m11_unit_va(941)` は boot 後に 0 だった。

| 測定 | セル X = `0x11e2318` (V・[V]) | セル X = `0x11e3c70` (V・[V]) | 備考 |
|---|---|---|---|
| 静的イメージ | `0x153fc08`・0 | `0x153fbf8`・0 | 前回 (`32c684c7c`) と同じ |
| 実 boot (survey なし) | `0x153fc08`・0 (不変) | `0x153fbf8`・0 (不変) | `threw: memory access out of bounds`・boot_stage 1・units_run 17・InitUnits probe 0 |
| survey (942 unit を隔離実行) | `0x153fc08`・0 (全 unit 後も不変) | `0x153fbf8`・0 (全 unit 後も不変) | trap 83 件・clobber 0 件。cell の値は変わらない |

- 消費者が 2 段目で読む番地 `0x14`: 静的 0。survey で unit 189 (`_m11_unit_va(189)` = `0x2b7e40`) の実行後に 1 になり、unit 600 (`0x8349a0`) の実行後に 0 へ戻った。1 段の読み (`V+0x14`) は全時点で 0。
- 原因は未特定。clobber は survey 全体で 0 件 (復元は発動していない) で、復元の有無は `0x14` の変化に影響しない。書き込み元の命令は未特定 (unit 189 の実行中に書かれた)。
- `V` は image の 0 埋め領域 (`0x11e5003`〜`0x1576000`、約 3.7 MB) の中にある (.bss 相当)。この値は実行時の初期化 (InitUnits) で書かれる可能性がある。現行の harness は InitUnits の状態に到達しない (実 boot の停止点は `tools/m11/REPORT_N1050.md` と同じ)。
- 含意: 機械語は 2 段 (`[[X]+0x14]`)、IR は 1 段である点は静的に確定している (§2)。ただし修復後に消費者が指す値 `[V]` は、この harness では 0 のまま。よって修復の意味的な正しさは確定できない。`REPORT_2921.md` §4 の値 (VA 座標の読み) とは一致しない。
- 次に必要な確認: InitUnits を完走させた状態で `[V]` を読むこと。通常 boot の完走確認は #3646 (CI-172) の受入にあるが、`[V]` を読む受入は入っていなかった。#3646 に `[V]` を読む受入を追加した (https://github.com/signature-studio/signature-studio-dev/issues/3646#issuecomment-6184949588)。修復の既定 build への配線は、この値が取れるまで行わない。

## 5. 限界・未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 2 段目の値 `[V]` の実行時の値 (§4) | 修復の意味的な正しさが未確定。harness では `[V]` = 0 | #3646 (CI-172。`[V]` を読む受入を追加したコメント: https://github.com/signature-studio/signature-studio-dev/issues/3646#issuecomment-6184949588) |
| audit の `cell_check` が幅 64 の 1 段/2 段を区別しない | 修復の効果を audit で測れない (§3) | PM agent の判断待ち: `cell_check` で幅 64 の 1 段/2 段を区別するか (起票の要否を含む)・既定案: 現行の判定のまま・未起票 |
| 修復を既定の m11 build (`m11_gen_ir2.sh`) に配線していない | 脱落関数の和集合 83 件は不変。起動・GUI への効果は未測定 | PM agent の判断待ち: 既定 build (`m11_gen_ir2.sh`) へ配線するか・既定案: 未配線のまま (§4 の `[V]` が取れるまで配線しない) |
| `0x14` の書き込み元 (unit 189 の実行中。§4) | 2 段目の消費者 `[0+0x14]` の読み値が unit 189 の前後で変わる。修復の効果の判断に入る | PM agent の判断待ち: 書き込み元の特定を別 issue にするか・既定案: 本 PR では特定せず、原因未特定のまま残す |

- 起動・GUI の KPI (FLEngine dispatch 数・通過 unit・最初のウィンドウ) は動かしていない。既定経路を変えていないため、KPI は本 PR の対象外。

## 6. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh     # 8/8 (約 3 分)
python3 tools/m11/ldfix/fix_spill_deep_2987.py tools/m11/work/boot_final3.ll $SSA tools/m11/work/m11_image.bin "tools/m11/work/boot*.drc.config.json" OUT.ll --verdicts tools/m11/ldfix/results/candidate_verdicts_2921.jsonl
diff tools/m11/work/boot_final3.ll OUT.ll   # 429019・429020 の 2 行のみ
M11_WORK=<tools/m11/work の絶対パス> node tools/m11/ldfix/dyn_ld143_2987.mjs   # §4 の PROBE143 (1 行 JSON)
```
