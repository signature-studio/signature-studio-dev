# lift2 REPORT 付録 — FA-10 (#666): lift2_e2e 工程 6 (ctrl) 失敗の切り分け / rep movs・stosw 対応

- 日付: 2026-10-13 / Issue #666 `[FA-10]` / 起点 HEAD: 8d883c3 (origin/main) → 修正 commit a092759
- 本付録は `REPORT.md` の上限 (250 行) のため分割した追記 (`docs/DOC_MAP.md` §1)。内容は削除していない。
- `REPORT.md` の §12 (FA-4 #51) 全文は `REPORT_APPENDIX_FA4.md` に分割移動 (本 PR)。
- 既知類型との関係: `docs/DEFECTS.md` (D1a〜D16) に rep 系・素材配線の類型は無い (該当なし。grep 実測)。
  `rep movs*` の未対応は lift の対応範囲の欠落で、mlift が `llvm.trap()` に置換するため実行時に検出される (silent ではない)。

## 1. 結論

1. **工程 6 の FAILED の原因は素材の展開漏れ**。factory `.epf` 8 本 (`Fresh Air.Win.zip` 内
   `FACTORY Presets/Factory Bank/`) が `tools/targets/freshair/work/win/` に無いと、制御層シナリオが
   15 本 → 7 本に縮退する。その結果、乱数列がずれ、ランダムシナリオ先頭 (`S2000`) で native が Abort して MISMATCH になる。
   同一コードで epf を展開すると ctrl は 15/15 bit-exact PASS (A/B, §2.1)。
2. **rep movsb/stosw の Unsupported は実在する** (baseline build で 17 関数・26 命令)。本 PR で rep movs{b,w,d,q} と
   rep stosw を実装し、rep 起因の Unsupported を 0 にした。ctrl e2e は rep 経路を**実行する** (`h_rep_str` 先頭の trap で FAIL, §10.1)。
   comp / filter の rep 経路の動的確認は未実施 (§5)。
3. capstone 5.0.7 は `rep movsb` を単一 mnemonic `rep movsb` で返す (実測)。capstone 4.0.2 は導入できず
   (sdist ビルドが `pkg_resources` を要求)、版差の影響は**未切り分け**。FA-2c (9b420bd) 以降 `mlift/` は無変更
   (`git log`)、`lift2/` の dd9bc5e 以降の変更は docs のみ (2ac5d90)。入力 `SlateCore.core_64` の sha256 は
   `work-liftlib-targets` と Win zip で一致 (`2cf759f7…`, 36,285,952 B)。

## 2. 実測

### 2.1 切り分け (A/B: 同一コード・同一 build で epf の有無だけを変えた)

同一 HEAD (`7783af9`) の同一 `native_ctrl` / `ctrl_full.cjs` で、`FACTORY Presets` を一時退避する前後を比較した (退避は復元済み)。

| 条件 | epf | 生成シナリオ | run_ctrl.sh 2 5 | 直接実行 (native / wasm, fma0) |
|---|---|---|---|---|
| A | 有 (8 本) | 15 | **15/15 BIT-EXACT** (3 回の e2e で再現, §2.2) | 15 行 / 15 行, 両側 ERR 1 件 (同一 scenario) |
| B | 無 (退避) | 7 | **exit 2** (`ERROR: factory .epf 8 本が無い … 生成シナリオ 7 本`) | native: **exit 134** (`ERR S2000 sig=11`, `free(): invalid size`, 出力 2 行で停止) / wasm: S2000 で `ERR` (exit 0, 出力 9 行) |

- B では native が S2000 で abort し、wasm も同じ S2000 で ERR を出す。両側の ERR scenario は一致するが、native の出力が途中で止まるため `ctrl_norm.py` は行数不一致で不合格 (`lines native/wasm 2/7`)。よって B は「gate で止まる + 素材なしで直接実行しても bit-exact は成立しない」ことの実測であり、「native/wasm が同一 ERR で完走する」ことの証明ではない。
- 「同じ lift コードで epf の有無だけを変えた」は B0 (8d883c3) との比較では成立しない。B0 は別コードのため、上表はコードを固定した A/B に差し替えた。
- B0 (8d883c3, origin/main) の失敗内訳 (参考・別コード): `rep movsb` 16 命令 / `rep stosw` 6 命令 / `pcmpeqw|pshuflw` 4 命令で build の failed が 17 関数。mlift の `emit_insn` は `rep` 接頭辞で `stos{b,d,q}` のみ受理していた (`inner in (...)`) ため、`inner='movsb'` 等は `Unsupported('rep prefix rep movsb')` になる。B0 の run_ctrl 結果 (MISMATCH) は B0 のコードでの結果であり、epf 欠落のみに帰属させない。
- 乱数列のずれの根拠: `gen_ctrl_scen.py` の epf ループは `change()` 経由で `rnd` を消費する。epf が無いと
  structured/random シナリオの中身が変わり、ランダム先頭 `S2000` (`NR` の 0 番目) が native で OOB を起こす。
  `run_ctrl.sh` 冒頭が述べる「既知限界 (乱数注入の OOB)」と同型。**2/5 の回帰セットは epf を含む乱数列でのみ PASS する**
  (seed 依存) — この脆さは未解決 (§5)。
- 旧 `run_ctrl.sh` の `EXPECT=NS+NR+8` は生成本数を見ていなかったため、epf 欠落でも表示上は "15/15" になり得た。
  本 PR で `EXPECT` を生成行数 (`wc -l`) に変え、8 本未満なら `exit 2` にした (B2)。

### 2.2 lift2_e2e.sh 全体 (HEAD 7783af9, 実測 3 回)

検証 HEAD は `7783af9` (`run_ctrl.sh` の判定コメントのみ修正したコミット。挙動は不変)。
`TMPDIR=$RUNNER_TEMP bash tools/targets/freshair/lift2/lift2_e2e.sh` を worktree `ws-698` で実行。

| 回 | exit | real | user / sys | 開始前 load (1 分) | 結果 |
|---|---|---|---|---|---|
| 1 | 0 | 1m19.336s | 1m12.087s / 5.636s | 0.19 (up 4 min) | `RESULT: lift2_e2e ALL PASS` |
| 2 | 0 | 1m15.112s | — | 0.88 | `RESULT: lift2_e2e ALL PASS` |
| 3 | 0 | 1m14.871s | — | 0.89 | `RESULT: lift2_e2e ALL PASS` |
| 4 (HEAD `0e8ff06`, docs のみ追加) | 0 | 1m15.232s | 1m10.948s / 5.560s | 0.12 | `RESULT: lift2_e2e ALL PASS` |
| 5 (HEAD `fa219ea`, origin/main 取り込み後) | 0 | 1m14.509s | 1m10.444s / 5.349s | 0.53 | `RESULT: lift2_e2e ALL PASS` |

- 現 HEAD `fa219ea` (最終) の min–max: real 1m14.509s–1m15.232s (n=2, 回 4・5)。全 5 回の min–max: 1m14.509s–1m19.336s。nproc 4。
- 工程別 (1 回目の実測): comp fma0 200 / fma1 200 (計 400, mismatch 0, 両側 ERR 0) / filter 400 (mismatch 0) /
  fuzz comp・filter × fma0・fma1 の各 1200 mismatch 0 / ABI violations 0 / ctrl 15/15 (fma0+fma1, 両側 ERR 1/1 同一 scenario) /
  ablation 注入 5 種すべて検出 (comis_noflags 200/200, xmm_args_drop 200/200, xmm_ret_drop 200/200,
  icall_drop 80/200, cmov_drop 172/200)。ablation が本 e2e の負のコントロール。
- 参考 (旧 HEAD a092759, 1m13.467s) は本改訂前の記録で、現 HEAD の数値ではない。
- 再現: `bash tools/targets/freshair/lift2/lift2_e2e.sh` (env.sh が capstone 5.0.7 の venv を作る。素材は下記 §3)。

### 2.3 rep movs / stosw の実行到達性 (負のコントロール)

rep 経路の trap 版 (`h_rep_str` 先頭への `llvm.trap`) の数値は **§10 が正本** (§10.1 / §10.2)。ctrl は rep 経路を実行し、trap 版で FAIL する。
comp / filter の trap 版は未実施のため、それらの rep 経路の動的確認は未達 (§5)。

### 2.4 epf 欠落時のゲート (負のコントロール)

`FACTORY Presets` を一時退避して `bash run_ctrl.sh 2 5` → `exit 2`、
`ERROR: factory .epf 8 本が無い … 生成シナリオ 7 本` を出力 (2.1 B と同一の実測)。復元後は 8 本 (実測)。

### 2.5 「15/15 BIT-EXACT」の内訳 (ERR 1 件の扱い)

- `ctrl_norm.py` は両側で**同一 scenario** の ERR を許容する (ERR 集合が一致しない場合は不合格)。
- 既定 seed (`0xFA2C0001`) の 15 シナリオでは **S2001 (native: `ERR S2001 sig=5`)** が native / wasm 両側で ERR (同一 scenario)。
  実測: `ctrl_norm.py ... 1/1 (同一 scenario: yes)`。よって「15/15 BIT-EXACT」の中に **両側 ERR の 1 件を含む**。
  ERR を含む scenario は bit-exact 比較の対象外 (出力は ERR 行のみ) で、残り 14 件が実際の出力比較。
- `run_ctrl.sh` 冒頭コメントの旧記述 (「ERR 0 を含む 4 条件」) は実装と一致しなかったため、本改訂で「ERR は両側同一 scenario のみ許容」に修正した。

### 2.6 FA-11 (#692): SSE 整数 lowering 追加 と rep movs ネガコン (実測, 2026-10-13)

- 追加: `pcmpeqw` (icmp eq <8 x i16> → sext)、`pshuflw` (下位 4 lane の shufflevector)、`pmovmskb` (xmm → 16bit mask)。
  `mlift_ops.py` の `emit_sse` に追加。`build_ctrl.sh` の FAIL は `pcmpeqw`・`pshuflw` が消え、
  残りは `vpcmpeqw ymm1` (256bit AVX2, mlift は ymm 未対応) の 1 件のみ (`failed(funcs with unsupported) 1`)。
- 残った `vpcmpeqw ymm` は ctrl closure 内 (f_1810577ac @181057857) で、ymm 対応は未実装。
- rep 経路のネガコン (trap 版) の数値は §10 が正本 (§2.3 と同じ。旧記録の「15/15 PASS」は誤り・撤回)。
  comp 側の trap 版は未実施。
- 未解決: rep movs/stosw を実行する scenario の追加 (受入 1)、seed 非依存化 (受入 3)、`vpcmpeqw ymm` (受入 2 の残り)。

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
| rep movs/stosw の経路は ctrl e2e で実行・検出される (§10.1)。comp/filter の rep 経路は未実行 (trap 版未実施) | comp/filter 側の rep 系 lowering の誤りを e2e が検出するかは未確認 | #692 (FA-11) |
| SSE 整数 `pcmpeqw`/`pshuflw`/`vpcmpeqw` の lowering 未実装 (ctrl closure 2 関数, trap) | 到達すると wasm trap。現シナリオでは未到達 | #692 に併記 |
| CI の素材配線: plugins-freshair の Win zip → `work/win` の epf 展開が無い (fetch.sh は既存ディレクトリでスキップ) | ctrl 工程は epf 欠落で exit 2 (手動展開が必要) | #693 (FA-12) |
| 2/5 回帰セットが epf 有無で乱数列が変わる seed 依存 | 別 seed では native OOB の可能性 (既知限界の再発) | #692 に併記 |
| capstone 4 系の版差 (FA-2c 当時の capstone 版は不明) | 73 s 当時との差の原因は未切り分け | 本 Issue #666 に留保 |

## 6. FA-11 (#692) 途中経過: SSE 整数 pcmpeq{b,d} の lowering (部分達成)

- 検証 HEAD: `db279818` (重複解消 `1496922d` を含む。`mlift_ops.py` の本 PR 差分は `pcmpeq{b,d}` の 8 行のみ)。
- 追加 (本 PR): `mlift/mlift_ops.py` の `emit_sse` に `pcmpeq{b,d}` (legacy 2 オペランド、`icmp eq` + `sext`)。
- `8c217092` との関係: main の `8c217092` が `pcmpeqw` / `pshuflw` (と `pmovmskb`) の lowering を既に入れている。本 PR の初版は `pshuflw` と `pcmpeq[bwd]` の分岐を先に評価させ、main 側を覆っていた (dead code)。`1496922d` で `pshuflw` 分岐を削除し、`pcmpeq` の正規表現を `[bd]` に絞った。以後 `pcmpeqw` / `pshuflw` は main 側だけが実行される。
- ctrl build (`build_ctrl.sh`, `db279818`): `failed(funcs with unsupported)` 1 件 (`f_1810577ac: vpcmpeqw ymm1, ymm1, [r9]`、ymm 非対応)。解消前の `90ff81f4` で失敗していた `pmovmskb` 2 件は main `8c217092` の lowering で解消済み。

### 検証 (`db279818`、`lift2_e2e.sh`)
- `RESULT: lift2_e2e ALL PASS`, exit 0, real 84 s, load 0.46→0.92, nproc 4 (TMPDIR=`$RUNNER_TEMP`)。
- comp 400/400 BIT-EXACT (non-grow 206/206・grow 194/194)・filter 400/400 BIT-EXACT・ctx-fuzz 4 系統 mismatch 0・ABI violations 0・ctrl BIT-EXACT 15/15 (S2001 は両側 ERR で同一シナリオ)・ablation 5 種すべて検出。
- 素材: 本 run の `$ARTIFACTS_DIR` に `fl-win64` / `work-liftlib-targets` / `plugins-freshair` の 3 本の実在を確認。`work-liftlib-targets` を展開し、`plugins-freshair` は `fetch.sh` (`FA_DL`) で factory `.epf` 8 本を補完 (WORKFLOW §11)。emsdk 6.0.12 は `[EMSDK]` の手順で `$RUNNER_TEMP` に導入し、`env.sh` の参照先に配置。

### 新 lowering の実行到達 (`db279818`、ctrl)
- 対照 (検出手法の検証): `pshufd` (ctrl で実行される既存命令) の先頭に `llvm.trap()` を入れると `run_ctrl.sh 2 5` は FAIL (exit 1, `S900` で wasm 側のみ `ERR`)。
- `pcmpeq{b,d}` の trap 版: 同じ `run_ctrl.sh 2 5` は 15/15 BIT-EXACT (exit 0)。
- 静的確認: trap 版の `work/ctrl/ctrl_full.ll` に `icmp eq <16 x i8>` / `icmp eq <4 x i32>` は 0 件 (`icmp eq <8 x i16>` 3 件は main 側の `pcmpeqw`)。`work/ctrl/ctrl_rep.json` の mnemonic に `pcmpeqb` / `pcmpeqd` は 0 件。新分岐は ctrl closure を 1 つも emit しないため、S2001 内での発火も無い。
- 元に戻した後、`mlift/mlift_ops.py` を HEAD と `cmp` で一致確認済み。

### comp / filter (IR 静的確認のみ、動的確認は未実施)
- HEAD (`db279818`) の `work/ml/comp_full.ll` と `work/filter/filter.ll` に `icmp eq <16 x i8>` / `icmp eq <4 x i32>` は 0 件 (`icmp eq <8 x i16>` も 0 件)。
- `run_comp.sh` / `run_filter.sh` の trap 版は未実施。

## 7. FA-13 (#905): rep movs/stosw の実行到達 (実測, 2026-10-13, 測定 HEAD 863f3d3c)

- HEAD の対応: 測定は `863f3d3c` で行った。以後 `12146acf`・`a01812f9`・`15243d54`・`8048c43a` の差分は本ファイル (文書) のみで、コードは `863f3d3c` から `8048c43a` まで不変 (その後の lift2 コード変更は下の再測定で扱う)。確認: `git diff --stat 863f3d3c 8048c43a` → `REPORT_APPENDIX.md | 15 +++` (1 file changed, 15 insertions)。`git diff 863f3d3c 8048c43a -- tools/targets/freshair/lift2 ':!*REPORT*'` は 0 行。
- 検証: worktree `ws-905` (branch `905-lift2-rep-movs-e2e`)。素材 `plugins-freshair` (`Fresh Air.Win.zip` に `SlateCore.core_64` と factory `.epf` 8 本) を `fetch.sh` で展開 (`FA_DL=$RUNNER_TEMP/pf`)。
- `build_ctrl.sh`: exit 0, real 38.1 s。mlift は `lifted 1256 funcs`, `failed 1` (`f_1810577ac` の `vpcmpeqw ymm`、既知)。
- 基準 `run_ctrl.sh 2 5` (trap 無し): **15/15 BIT-EXACT**, exit 0, real 4.3 s。
- rep 出現箇所 (実測, 測定 HEAD `863f3d3c` の mlift 出力を `c91d292b` でも再現): `work/ctrl/ctrl_full.ll` の `; <addr>: rep (movs[bwdq]|stosw) ` コメント行を数えた結果は **45 行・15 関数**。
  - 正規表現: `^\s*; [0-9a-f]+: rep (movs[bwdq]|stosw) ` (ll 内のコメント行。mlift が命令ごとに出す)。
  - 命令別: `rep movsb` 39 / `rep stosw` 6 (計 45)。`rep movsw`・`rep movsd`・`rep movsq` は 0。
  - 関数別 (行数): f_1803e12c0 (4)・e2190 (1)・e2240 (8)・e2600 (8)・e2b50 (1)・e4ee0 (1)・e5070 (1)・e8b70 (2)・e95f0 (7)・fb860 (3)・fbb80 (3)・fdc70 (1)・f_180401070 (1)・f_180402e50 (1)・f_180ca4e70 (3)。
  - 旧記録の「40 箇所 (12 関数)」は、上の列挙のうち先頭 12 関数の合計 (40) と一致する。残り 3 関数 (f_180401070・f_180402e50・f_180ca4e70、計 5 行) が漏れていた。**正しい値は 45 行 (15 関数)**。
  - 参考: `ctrl_rep.json` の mnemonic 集計も `rep movsb` 39・`rep stosw` 6 で一致。`rep stosb` 84・`rep stosq` 1 は §7 の対象外 (movs / stosw のみ)。
- ネガコン (旧記録, 測定 HEAD `863f3d3c`, 本 run では未再現): 旧記録では 40 箇所に `llvm.trap` を入れ emcc で再ビルドした版の `run_ctrl.sh 2 5` が **15/15 PASS**, exit 0 とされている。旧記録の 40 箇所は、漏れた 5 行 (f_180401070・f_180402e50・f_180ca4e70) を含まないため、**45 箇所全体のネガコンではない**。
- 挿入後の trap 件数 (本 run, 実測): 45 箇所 (rep の `done` 先頭ブロックの直前に `call void @llvm.trap()`、作業用コピー `work/ctrl/ctrl_neg.ll`) を入れた結果、`grep -c llvm.trap` は **1695** (= 挿入前 1650 + 45)。`diff ctrl_full.ll ctrl_neg.ll` は `>` 行 45 のみ。元の `ctrl_full.ll` は sha256 `dadbc54b…` のまま不変。
- 本 run で **未実施**: (a) `ctrl_neg.ll` の emcc 再ビルドと `run_ctrl.sh` 実行 (runner に `/opt/emsdk` が無く emcc 不在のため wasm 段が実行不能)、(b) 陽性対照 (既到達関数先頭に trap を入れ `run_ctrl.sh` が FAIL することの確認)。よって 45 箇所版のネガコン結果は未取得。
- 「既定 seed では rep 経路は実行されない」は**未検証の推定**。旧 40 箇所版の PASS と、既定 seed の到達を示す実測 (trace) がないため断定しない。
- 探索 seed (`2 40 0xFA2C0001`, `10 60 0xFA2C0002`) は trap 版でも trap 無し版でも同じ形で **MISMATCH** (wasm 側 0 行)。trap 版と trap 無し版で同一の結果のため、rep 経路の到達判定には使えない (既知限界の乱数 OOB と同根と推定。根拠となる節・issue は未特定)。
- 元に戻した後、`ctrl_full.ll` の sha256 が挿入前と一致 (`dadbc54b…`)、`.cjs` は `cmp` で一致。`git status` は clean。
- 件数の解消 (本 run): 旧 40 件は漏れ (上記)。正しい値は **45 行 (movsb 39 + stosw 6・15 関数)**。PM 中間コメントの 45 と一致する。
- 素材 (本 run): `$ARTIFACTS_DIR` に `fl-win64.tar.zst` と `plugins-freshair.tar.zst` の両方が実在。`plugins-freshair` を `tar --zstd -xf` で `$RUNNER_TEMP/plugins-freshair` に展開し、`FA_DL=... fetch.sh` で factory `.epf` 8 本を確認 (`win: 17 files, factory .epf: 8`)。
- mlift 段の再実行: `build_ctrl.sh` の mlift 部分 (emcc より前) を `c91d292b` の worktree で実行。`lifted 1256 funcs / failed 1` (`f_1810577ac` の `vpcmpeqw ymm`、既知)。`env.sh` は `/opt/emsdk` を source するため、そこだけ外して実行した (mlift は emsdk 不要)。
- 再測定 (HEAD `e8109f7a`, 本 fix。`863f3d3c..e8109f7a` は mlift の `vpcmpeqw ymm` 等のコード変更を含むが、rep の件数は上の 863f3d3c 測定と一致): `build_ctrl.sh` exit 0, real 41.1 s, `lifted 1256 funcs / failed 0`。`ctrl_full.ll` の rep 行を上の正規表現で数えた結果は **45 行 (movsb 39 / stosw 6)・15 関数**で、上の関数別行数と全件一致。素材は `plugins-freshair` を `$RUNNER_TEMP/pf` に展開し `FA_DL=... fetch.sh` で factory `.epf` 8 本を確認。trap 版は作っていないため `run_ctrl.sh` は未実施。
- 結論: 受入 1 (実行到達 scenario) は**未達**。rep 経路の到達は本 run で確認していない (trace 未取得)。受入 2 (ネガコン FAIL) は、45 箇所版の trap 件数 (1695) までは確認、wasm 再ビルドと陽性対照は**未実施**のため判定不能。残りは #692 で扱う。

## 未解決 (起票先 #692)
- 新 lowering `pcmpeq{b,d}` の comp / filter 経路の動的確認 (trap 版の `run_comp` / `run_filter`)。
- rep 経路の e2e 到達・ネガコン (受入条件 1)、回帰セットの seed 非依存化 (3)。
- `vpcmpeqw` (ymm、`f_1810577ac`) の lowering。
- epf 展開の素材配線は #693。

## 7. FA-14 (#907): 回帰セットの seed 依存の実測 (2026-10-13)

- 検証基点: `origin/main` = `99b87bc2`。素材は `plugins-freshair` のみ (`FA_DL` → `fetch.sh`、factory .epf 8 本を補完)。
- 既定 `run_ctrl.sh 2 5` は seed `0xFA2C0001` 固定 (`run_ctrl.sh` 既定値)。#907 受入 1 の「seed を固定値で明記」の方式を採る (コード変更なし)。
  epf 欠落時は `run_ctrl.sh` が exit 2 で止まる (本 run で退避実測: `ERROR: factory .epf 8 本が無い ... 生成シナリオ 7 本`, rc=2)。この rc=2 は PASS ではなくゲート停止であり、epf 欠落時の PASS は仕様上対象外。epf 有時は 15/15 PASS (§9)。
- 別 seed の実測 (structured 2 + random 5、native のみ、`native_ctrl` 単体):
  - `0x1` / `0x2` / `0x3` はいずれも `native_ctrl` が `Aborted` (rc=134) で途中停止 (出力 8 / 10 / 9 行、15 行に満たない)。
  - 既知限界 (`run_ctrl.sh` 冒頭: 乱数が意味 field に OOB 書込を起こす) の再発で、seed 非依存ではない。
- epf 8 本のみ (`gen_ctrl_scen.py <out> 0 0 <seed>`、乱数未使用) の native 出力は seed 0x1/0x2/0x3 で全て rc=0・8/8 行・ERR 0。
  seed 間の出力差の内訳は本 run では分類していない。判定の根拠は `ctrl_norm.py` の規則 (8 byte 単位で値 ≥ `MASK_MIN` = 0x100000000 の 16 桁を両側同時にマスク) のみで、マスク後に一致することは本 run では未実測 (seed 0x1/0x2/0x3 の wasm 側出力は未取得)。同一 seed の再実行で差が変わるかも未測定 (素材不足で e2e を再実行できない)。
- 結論: 既定の structured/random を含む回帰は seed 依存 (0x1/0x2/0x3 で native_ctrl が abort、上記実測)。epf 8 本のみの部分は native で seed 0x1/0x2/0x3 とも rc=0 だが、seed 非依存とは未確認 (wasm 比較は未実施)。

## 8. FA-14 (#907) 未達と起票先
- 受入 2 (`vpcmpeqw ymm`): mlift のレジスタは `XMM = <4 x i32>` 固定で ymm (256bit) の上位を保持できず、構造変更が要る。1 run に収まらないため子 issue に分割する。
- 受入 3 (`lift2_e2e.sh` ALL PASS): §9 に実測 (実測 commit `c531a0cb`)。
- 受入 2 の子 issue: [FA-15] lift2 ctrl closure の vpcmpeqw ymm (AVX2 256bit) lowering — #1105 (OPEN、親 #907)。

## 9. FA-14 (#907) 実測: lift2_e2e.sh (`origin/main` = `99b87bc2`)

- 実測の commit: `c531a0cb`。lift2 コードは `99b87bc2` と同一で、`99b87bc2..c531a0cb` の差分は本ファイル (REPORT_APPENDIX.md) のみ。`RESULT: lift2_e2e ALL PASS`, rc=0, real 1m14.253s, user 1m10.095s, load 0.22 (`uptime`), TMPDIR=`$RUNNER_TEMP`。
- 基点 `99b87bc2` でも実測: rc=0, real 1m18.548s, load 0.12, ALL PASS。
- 注: 上記は素材取得時の実測。後続のレビュー run では素材不足で再実行できていない (未再検証)。
- ただし step 6 (ctrl build) は `failed(funcs with unsupported) 1` (`f_1810577ac: vpcmpeqw ymm1, ymm1, ymmword ptr [r9]`)。build は継続し、ctrl 出力は 15/15 BIT-EXACT (epf 8 + structured 2 + random 5, fma0/1)。
- ctrl ERR: native/wasm 1/1 (同一 scenario)。comp/filter/fuzz/ABI/ablation 5 種はいずれも実測どおり PASS。

## 10. FA-10 (#666) rep 経路のネガコン (ctrl) — 実測・受入 4 達成

本節が rep 経路ネガコンと検証 HEAD の数値の正本 (§2.3・§2.6 は本節を参照)。検証 HEAD は **`3214a40e`** (全節共通)。

### 10.0 前回記録の訂正

- 旧 §2.3 / §2.6 の「trap 版 15/15 PASS」は**未検証として削除**する。その記録は HEAD (`32f3561b` / `5aec7dda` / `84e43186` の 3 種が混在) と trap の挿入位置を特定できず、同一 HEAD での再実行 (§10.1) とも一致しない。
- 同一 HEAD `3214a40e` での再実行 (§10.1) は FAIL (exit 1) で、旧「trap 版 exit 1」の記録 (旧版の §10.1) と一致した。以後の数値は本節の実測のみを採る。
- 旧版の §10.3 の全体実行値 (real 48.302 s) は旧 run の値。本節の数値は §10.3 の 1 箇所に集約する (他節は参照のみ)。

### 10.1 rep 経路ネガコン (HEAD `3214a40e`, 実測)

- 対象: `h_rep_str` 先頭に `llvm.trap` + `unreachable` を入れた一時版 (`mlift/mlift_ops.py`)。`ctrl_rep.json` に `rep movsb` / `rep stosb` / `rep stosw` / `rep stosq` が入っており、ctrl 閉包はこれを実行する。
- 検証 HEAD `3214a40e` (`mlift/mlift_ops.py` の blob `f8f57a70`。現 PR head `7ec97437` でも同一ファイル)。
- trap 版 (`h_rep_str` の `bits = ...` 行の直前に `fl.e('call void @llvm.trap()'); fl.e('unreachable'); return True`):
  - `build_ctrl.sh` → exit 0, `mlift: lifted 1157 funcs / 483427 B / 103228 insns, failed(funcs with unsupported) 1` (`f_1810577ac: vpcmpeqw ymm1` のみ、既知) / `ctrl build ok`。
  - `run_ctrl.sh 2 5` → **exit 1** (`RESULT: MISMATCH in ctrl scenarios`)。`fma=0` / `fma=1` ともに `scenarios 15, lines native/wasm 15/0, ERR native/wasm 1/0 (同一 scenario: NO)`。wasm 側 stderr に `RuntimeError: unreachable`。`ctrl_w0.txt` は 0 行、`ctrl_n0.txt` は 15 行。
- 元に戻した版: `git checkout -- tools/targets/freshair/lift2/mlift/mlift_ops.py` → `git show 3214a40e:…/mlift_ops.py | cmp - …` で **一致 (CMP OK)**。
- 判定: rep 経路 (`stos*`/`movs*` 共通の `h_rep_str`) の誤りは ctrl e2e で検出される。受入 4 達成。comp / filter の trap 版は未実施 (§5 の未解決)。

### 10.2 再現コマンド

1. HEAD `3214a40e` で `mlift/mlift_ops.py` の `h_rep_str` の `bits = ...` 行の直前に `fl.e('call void @llvm.trap()'); fl.e('unreachable'); return True` を入れる。
2. `bash build_ctrl.sh` → `bash run_ctrl.sh 2 5` (foreground, `TMPDIR=$RUNNER_TEMP`)。exit 1 / `同一 scenario: NO` / `RuntimeError: unreachable` を期待する。
3. `git checkout -- tools/targets/freshair/lift2/mlift/mlift_ops.py` で戻し、`git show 3214a40e:…/mlift_ops.py | cmp - …` で一致を確認する。

素材: `work-liftlib-targets` を展開し、`plugins-freshair` は `FA_DL` の `fetch.sh` で epf 8 本を補完 (`work/win` に 8 本を確認)。emsdk は `[EMSDK]`、retdec は `[RETDEC]` (`docs/REFERENCES.md`) を使用。

### 10.3 lift2_e2e.sh 全体 (元に戻した HEAD `3214a40e`, 実測)

- 実測コマンド: `TMPDIR=$RUNNER_TEMP FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/targets/freshair/lift2/lift2_e2e.sh` (foreground)。
- 実測: `RESULT: lift2_e2e ALL PASS`, exit 0, real **60.300 s**, load 0.53→0.89 (nproc 4, TMPDIR=`$RUNNER_TEMP`)。
- 注: 本節の値は `3214a40e` での実測。HEAD `7ec97437` 以降での再実行は素材不足 (§ 冒頭の 2026-10-14 試行) のため未実施。
- comp 400/400 BIT-EXACT (non-grow 206/206・grow 194/194)・filter BIT-EXACT・fuzz 4 系統 mismatch 0 (各 1200, ERR 0/0)・ABI violations 0・ctrl BIT-EXACT 15/15 (fma0/fma1 とも `ERR native/wasm 1/1 同一 scenario: yes`)・ablation 5 種すべて検出 (comis_noflags 200/200, xmm_args_drop 200/200, xmm_ret_drop 200/200, icall_drop 80/200, cmov_drop 172/200)。
- 必要な素材: `oc_artifacts: fl-win64 work-liftlib-targets plugins-freshair toolchain-emsdk toolchain-retdec`。
- 2026-10-14 の再実行試行 (HEAD `7ec97437`): `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk work-m11` では `SlateCore.core_64` が無く、`lift2_e2e.sh` は exit 2 (`ERROR: … SlateCore.core_64 が無い`)。`fl-win64` / `work-m11` の tar 一覧にも `SlateCore` / `Fresh Air` は無い。このため上記 (`3214a40e`) の値は本 HEAD での再実行値ではない。

## 11. FA-13 (#905): kind 別の rep ネガコンと到達の実測 (HEAD `8bc34ed9`)

- 測定 HEAD: `8bc34ed9` (origin/main)。`git diff 3214a40e 8bc34ed9 -- tools/targets/freshair/lift2/` は REPORT_APPENDIX.md のみ (コード不変)。
- 素材: `oc_artifacts: fl-win64 toolchain-retdec toolchain-emsdk plugins-freshair` で展開。`fetch.sh` → factory .epf 8 本、`lift2_e2e.sh` の build・run とも通る。
- 基準 `lift2_e2e.sh` (trap 無し): `RESULT: lift2_e2e ALL PASS`, exit 0, real **79 s**, load 0.36→0.89 (nproc 4, TMPDIR=`$RUNNER_TEMP`)。comp 400/400・filter 400/400・fuzz 4 系統 mismatch 0・ABI violations 0・ctrl 15/15・ablation 5 種検出。
- 一時版は `h_rep_str` の先頭に `llvm.trap` + `unreachable` を入れ、`kind` で絞って実施。各版の後に `mlift_ops.py` を元の退避コピーから戻し、`cmp` で一致を確認 (CMP_OK, 3 回とも)。
  | 一時版 (trap を入れた kind) | `build_ctrl.sh` | `run_ctrl.sh 2 5` | 判定 |
  |---|---|---|---|
  | 全 kind (`h_rep_str` 全体) | exit 0 (`lifted 1157 funcs`) | exit 1, `ERR native/wasm 1/0 (同一 scenario: NO)`, wasm 0 行 | FAIL (§10.1 と一致) |
  | `stosb` のみ | exit 0 | exit 1, `ERR native/wasm 1/0`, wasm 0 行 | FAIL |
  | `movsb` のみ | exit 0 | exit 0, `15/15`, `ERR 1/1 同一 scenario: yes` | PASS (経路未到達) |
  | `stosw` のみ | exit 0 | exit 0, `15/15`, `ERR 1/1 同一 scenario: yes` | PASS (経路未到達) |
- 結論:
  - **受入 1 (`movsb`・`stosw` の実行到達 scenario) は未達**。既定の ctrl 15 本は `stosb` の経路を実行するが、`movsb`・`stosw` の経路は実行しない。`movsb`・`stosw` の到達を示す trace は未取得。
  - **受入 2 (ネガコン FAIL) は `stosb` と全 kind 版で FAIL を実測**。`movsb`・`stosw` 単独版の FAIL は未確認 (未到達のため)。
  - 訂正: §10.1 の「`ctrl_rep.json` の rep は ctrl 閉包が実行する」は、kind ごとには成立しない (`movsb`・`stosw` は未実行)。§10.1 の数値は全 kind 版の値として有効。
- 未解決 (起票先 #692 (FA-11)・既存のため子 issue は起票せず): `movsb`・`stosw` を実行する入力の設計と ctrl (または新 scenario) への追加、その後の `movsb`・`stosw` 単独ネガコン FAIL 化。

## 12. FA-13 (#905): movsb / stosw を含む関数の呼び出し経路 (静的調査, HEAD `e8109f7a`)

- 測定値 (件数・ビルド結果) は §7 が正本。本節は関数の一覧と呼び出し経路だけを書く。
- 対象: `work/ctrl/ctrl_full.ll` の `define` 単位で rep 行を数えた、rep movsb / rep stosw を含む関数の全件 (§7 と同じ 15 関数)。

  | 関数 (VA) | movsb | stosw | `fa_icall` の case 値 | direct 呼び出し元 (`ctrl_full.ll`) |
  |---|---|---|---|---|
  | `1803e12c0` | 4 | | あり | `1803e2190`, fa_icall |
  | `1803e2190` | 1 | | あり | `1803e4ee0`, fa_icall |
  | `1803e2240` | 8 | | あり | `1803e6000`, fa_icall |
  | `1803e2600` | 8 | | あり | `1803e66f0`, fa_icall |
  | `1803e2b50` | 1 | | あり | `1803e4d50`, fa_icall |
  | `1803e4ee0` | 1 | | あり | `1803e95f0`, fa_icall |
  | `1803e5070` | 1 | | あり | `1803e95f0`, fa_icall |
  | `1803e8b70` | | 2 | あり | fa_icall のみ |
  | `1803e95f0` | 7 | | あり | fa_icall のみ |
  | `1803fb860` | 3 | | あり | `1803e55c0`, fa_icall |
  | `1803fbb80` | 3 | | あり | `1803e5870`, fa_icall |
  | `1803fdc70` | 1 | | あり | `18040b950`, fa_icall |
  | `180401070` | 1 | | あり | `1803fe400`, `181020a74`, fa_icall |
  | `180402e50` | | 1 | あり | `1803e49e0`, fa_icall |
  | `180ca4e70` | | 3 | あり | `180f8fd00`, fa_icall |

  - 表の行数の合計は §7 の測定と一致する。`rep stosb` / `rep stosq` は本節の対象外。
- 確認した事実 (実測, `ctrl_full.ll` の静的解析):
  1. 上表の 15 関数はすべて `fa_icall` の switch の case 値として現れる (間接呼び出しの解決先)。`1803e95f0` は `i64 6446552560` (= 0x1803e95f0)。
  2. `build_ctrl.sh` の `--root` 38 個 (すべて `ctrl_full.ll` に定義あり) から direct の `call` 辺だけで辿ると、15 関数はどれも到達しない。
- 未確認 (未解決): vtable の**どの slot から**これらの case が呼ばれるか (`fa_icall` の case 値の参照元)、および、どの scenario の入力でその経路が通るか。上の「direct 呼び出し元」は直前の 1 段のみで、2 段以上の上流は未追跡。
- 次の作業 (#905 の残件): (a) vtable 参照元の特定と、通る入力 (macro / 子 meter / flag) の決定。(b) その scenario を `gen_ctrl_scen.py` に追加し、`movsb`・`stosw` 単独 trap で `run_ctrl.sh` が FAIL することを実測する。(c) trap を戻し `cmp` で一致を確認する。
- 起票先: #905 (FA-13, OPEN)。親 #692。
