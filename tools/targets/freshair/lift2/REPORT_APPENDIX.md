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
   rep stosw を実装し、rep 起因の Unsupported を 0 にした。ただし **既存の 3 e2e (comp/filter/ctrl) は新経路を実行しない**
   (trap 挿入の mutation でも PASS, §2.3)。よって新経路の意味論は e2e で未検証 → 未解決 (§5)。
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

### 2.3 rep movs / stosw の実行到達性 (負のコントロール, 実測)

新経路 (movs b/w/d/q と stosw) の先頭に `call void @llvm.trap()` を挿入した一時版で各 e2e を再ビルドした。
経路が実行されれば wasm trap で FAIL になるはず。

| 一時版の e2e | 結果 |
|---|---|
| build_ctrl.sh + run_ctrl.sh 2 5 | **15/15 PASS** (経路未実行) |
| build_comp.sh + run_comp.sh 400 | **400/400 PASS** (経路未実行) |
| build_filter.sh + run_filter.sh 200 | **400/400 PASS** (経路未実行) |

→ 既存 e2e は新経路を一度も実行していない。新経路の正しさは build (capstone 復号 + IR 生成) までの確認で、
**実行結果の bit-exact 検証は未達 (build のみ・実行未検証)**。元に戻して `cmp` で一致を確認した (`git status` clean)。

注: 本表は trap 挿入版の結果で、2.2 の PASS は通常版 (trap 無し) の結果。新経路を実行させる e2e は無い。

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
- rep movs ネガコン (movs 経路の先頭に `llvm.trap` を挿入した一時版): `build_ctrl.sh` + `run_ctrl.sh 2 5` は
  **15/15 PASS**、`build_comp.sh` + `run_comp.sh 400` は **400/400 PASS**。既存 e2e は movs 経路を実行しない (§2.3 と同じ結論を再確認)。
  一時 trap は削除済み。
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
| rep movs/stosw の経路が comp/filter/ctrl のどの e2e でも実行されない (§2.3) | rep 系 lowering の誤りを e2e が検出しない | #692 (FA-11) |
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
