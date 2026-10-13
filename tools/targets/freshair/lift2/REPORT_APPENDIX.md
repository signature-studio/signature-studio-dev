# lift2 REPORT 付録 — FA-10 (#666): lift2_e2e 工程 6 (ctrl) 失敗の切り分け / rep movs・stosw 対応

- 日付: 2026-10-13 / Issue #666 `[FA-10]` / 起点 HEAD: 8d883c3 (origin/main) → 修正 commit a092759
- 本付録は `REPORT.md` の上限 (250 行) のため分割した追記 (`docs/DOC_MAP.md` §1)。内容は削除していない。
- 既知類型との関係: `docs/DEFECTS.md` (D1a〜D16) に rep 系・素材配線の類型は無い (該当なし。grep 実測)。
  `rep movs*` の未対応は lift の対応範囲の欠落で、mlift が `llvm.trap()` に置換するため実行時に検出される (silent ではない)。

## 1. 結論

1. **工程 6 の FAILED の原因は素材の展開漏れ**。factory `.epf` 8 本 (`Fresh Air.Win.zip` 内
   `FACTORY Presets/Factory Bank/`) が `tools/targets/freshair/work/win/` に無いと、制御層シナリオが
   15 本 → 7 本に縮退する。その結果、乱数列がずれ、ランダムシナリオ先頭 (`S2000`) で native が Abort して MISMATCH になる。
   同一コードで epf を展開すると ctrl は 15/15 bit-exact PASS (A/B, §2.1)。
2. **rep movsb/stosw の Unsupported は実在する** (baseline build で 17 関数・26 命令)。本 PR で rep movs{b,w,d,q} と
   rep stosw を実装し、rep 起因の Unsupported を 0 にした。ただし **既存の 3 e2e (comp/filter/ctrl) は新経路を実行しない**
   (trap 挿入の mutation でも PASS, §2.3)。よって新経路の意味論は e2e で未検証 → 未解決 (§5)。
3. capstone 5.0.7 は `rep movsb` を単一 mnemonic `rep movsb` で返す (実測)。capstone 4.0.2 は導入できず
   (sdist ビルドが `pkg_resources` を要求)、版差の影響は**未切り分け**。FA-2c (9b420bd) 以降 `mlift/` は無変更
   (`git log`)、`lift2/` の dd9bc5e 以降の変更は docs のみ (2ac5d90)。入力 `SlateCore.core_64` の sha256 は
   `work-liftlib-targets` と Win zip で一致 (`2cf759f7…`, 36,285,952 B)。

## 2. 実測

### 2.1 切り分け (A/B: 同じ lift コードで epf の有無だけを変えた)

| 条件 | コード | epf | 生成シナリオ | build の failed 関数 | run_ctrl.sh 2 5 |
|---|---|---|---|---|---|
| B0 | 8d883c3 (origin/main) | 無 | 7 | 17 関数 (rep movsb 12 / rep stosw 3 / SSE 整数 2) | **MISMATCH** (native `ERR S2000 sig=11`, `free(): invalid size`), exit 1 |
| B1 | a092759 | 有 (8) | 15 | 2 関数 (SSE 整数 pshuflw/pcmpeqw/vpcmpeqw) | **15/15 BIT-EXACT**, exit 0, 4.3 s |
| B2 | a092759 | 無 | 7 | — | **exit 2** (`ERROR: factory .epf 8 本が無い`) |

- B0 の内訳 (`$RUNNER_TEMP/build_ctrl_base.log` 相当の実測): `rep movsb` 16 命令 / `rep stosw` 6 命令 / `pcmpeqw|pshuflw` 4 命令。
  mlift の `emit_insn` は `rep` 接頭辞で `stos{b,d,q}` のみ受理していた (`inner in (...)`) ため、`inner='movsb'` 等は
  `Unsupported('rep prefix rep movsb')` になる。
- 乱数列のずれの根拠: `gen_ctrl_scen.py` の epf ループは `change()` 経由で `rnd` を消費する。epf が無いと
  structured/random シナリオの中身が変わり、ランダム先頭 `S2000` (`NR` の 0 番目) が native で OOB を起こす。
  `run_ctrl.sh` 冒頭が述べる「既知限界 (乱数注入の OOB)」と同型。**2/5 の回帰セットは epf を含む乱数列でのみ PASS する**
  (seed 依存) — この脆さは未解決 (§5)。
- 旧 `run_ctrl.sh` の `EXPECT=NS+NR+8` は生成本数を見ていなかったため、epf 欠落でも表示上は "15/15" になり得た。
  本 PR で `EXPECT` を生成行数 (`wc -l`) に変え、8 本未満なら `exit 2` にした (B2)。

### 2.2 lift2_e2e.sh 全体 (HEAD a092759, 作業ツリーはコミット済みで clean)

- 結果: **`RESULT: lift2_e2e ALL PASS`**, exit 0, `time` real **1m13.467s**, load (1 分平均) 0.32 → 0.87, nproc 4。
  (開始 08:36:22Z → 終了 08:37:35Z。FA-2c 当時の記録 73 s と同程度。)
- 工程別: comp 400/400 (non-grow 206/206, grow 194/194) / filter 200 × fma0+fma1 = 400/400 /
  fuzz 4 組 × 1200 mismatch 0 / ABI violations 0 / ctrl 15/15 (fma0+fma1) /
  ablation 注入 5 種すべて検出 (comis_noflags 200/200, xmm_args_drop 200/200, xmm_ret_drop 200/200,
  icall_drop 80/200, cmov_drop 172/200)。ablation が本 e2e の負のコントロール。
- 再現: `bash tools/targets/freshair/lift2/lift2_e2e.sh` (env.sh が capstone 5.0.7 の venv を作る。素材は下記 §3)。

### 2.3 rep movs / stosw の実行到達性 (負のコントロール, 実測)

新経路 (movs b/w/d/q と stosw) の先頭に `call void @llvm.trap()` を挿入した一時版で各 e2e を再ビルドした。
経路が実行されれば wasm trap で FAIL になるはず。

| 一時版の e2e | 結果 |
|---|---|
| build_ctrl.sh + run_ctrl.sh 2 5 | **15/15 PASS** (経路未実行) |
| build_comp.sh + run_comp.sh 400 | **400/400 PASS** (経路未実行) |
| build_filter.sh + run_filter.sh 200 | **400/400 PASS** (経路未実行) |

→ 既存 e2e は新経路を一度も実行していない。新経路の正しさは build (capstone 復号 + IR 生成) までの確認で、
実行結果の bit-exact 検証は未達。元に戻して `cmp` で一致を確認した (`git status` clean)。

### 2.4 epf 欠落時のゲート (負のコントロール)

`FACTORY Presets` を一時退避して `bash run_ctrl.sh 2 5` → `exit 2`、
`ERROR: factory .epf 8 本が無い … 生成シナリオ 7 本` を出力。復元後は 8 本。

## 3. 再現手順 (素材)

```sh
tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/pf"   # Fresh Air.Win.zip を含む
unzip -q -o "$RUNNER_TEMP/pf/Fresh Air.Win.zip" "Fresh Air/C__ProgramData_Slate Digital/Fresh Air/FACTORY Presets/*" \
  -d tools/targets/freshair/work/win                                            # epf 8 本 (gitignore 対象)
bash tools/targets/freshair/lift2/lift2_e2e.sh                                   # ALL PASS (§2.2)
```

- `work-liftlib-targets` は `SlateCore.core_64` のみで epf を含まない。`fetch.sh` は `work/win/Fresh Air` が
  既に在るとき Win zip の展開をスキップするため、epf は自動では入らない (§5 の未解決)。

## 4. 検証範囲 / 範囲外

- 範囲内: comp / filter / ctrl の既定シナリオでの bit-exact・fuzz・ABI・ablation (§2.2) と、epf 有無の A/B (§2.1)。
- 範囲外: rep movs/stosw の実行時の正しさ (§2.3 で未到達)。SSE 整数比較 (`pcmpeqw`/`pshuflw`/`vpcmpeqw`) の lowering
  (未実装、ctrl closure の 2 関数が trap のまま)。capstone 4 系との版差。CI 上での epf の自動展開。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| rep movs/stosw の経路が comp/filter/ctrl のどの e2e でも実行されない (§2.3) | rep 系 lowering の誤りを e2e が検出しない | #692 (FA-11) |
| SSE 整数 `pcmpeqw`/`pshuflw`/`vpcmpeqw` の lowering 未実装 (ctrl closure 2 関数, trap) | 到達すると wasm trap。現シナリオでは未到達 | #692 に併記 |
| CI の素材配線: plugins-freshair の Win zip → `work/win` の epf 展開が無い (fetch.sh は既存ディレクトリでスキップ) | ctrl 工程は epf 欠落で exit 2 (手動展開が必要) | #693 (FA-12) |
| 2/5 回帰セットが epf 有無で乱数列が変わる seed 依存 | 別 seed では native OOB の可能性 (既知限界の再発) | #692 に併記 |
| capstone 4 系の版差 (FA-2c 当時の capstone 版は不明) | 73 s 当時との差の原因は未切り分け | 本 Issue #666 に留保 |
