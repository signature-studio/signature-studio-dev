# 付録 C: §19 (PERF-P1 #155 lift ビルド標準設定 + 出力 bit 署名ガード) — tools/liftlib/

> **正本**: `tools/liftlib/REPORT.md` (結論・要約)。本書は `tools/liftlib/REPORT_APPENDIX.md` が 250 行上限 (`docs/DOC_MAP.md` §1) に
> 近いため、本節を新規付録として置いた §19 の全文 (節番号は本体の参照と一致。内容は削除していない)。
> 他の付録: [`REPORT_APPENDIX_A.md`](REPORT_APPENDIX_A.md) (§10〜§12)・[`REPORT_APPENDIX_B.md`](REPORT_APPENDIX_B.md) (§13〜§16)・[`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) (§17・§18)。

## 19. PERF-P1 (#155): lift ビルド標準設定 + 出力 bit 署名ガード (`python3 -m liftlib build`)

既知類型との関係: 該当なし (DEFECTS.md の D1a〜D16 はいずれも lift 内容の欠陥。本件は emcc フラグと検収ガードの追加で lift は未変更)。検証起点 commit: `18a6e58` (クリーン detached worktree `git worktree add --detach … HEAD` で 3 回実行)。署名ガード fail-open 修正後の再検証は `84067cb` (下の「fail-open の封じ込め」)。
**状態: 部分達成 (Closes しない)**。標準設定の正本・ビルド入口・署名ガード・合成入力での検証は完了。実 OTT / FA / KH を標準設定で通す検証は素材不足 (下の未解決表) で未実施。

標準設定 (正本 `data/std_build.json`、実装 `liftlib/stdbuild.py`。根拠は `tools/perf/REPORT.md` §2.1 の bit-exact OTT 実測):
- profile `std` = `-O3 -flto -ffp-contract=off -fno-fast-math -Wl,--gc-sections` + 最小 export (呼出側の `cfg.exports` のみ。pipeline は `_malloc`/`_free` を加える)。
- 禁止 (enforce profile = std/o2/o3 に混入すると `StdBuildError`): `-O0 -O1 -Os -Oz -msimd128 -mrelaxed-simd -ffast-math -Ofast -Wl,--no-gc-sections -sEXPORT_ALL --converge`。追加の wasm-opt 段は足さない (emcc 既定の binaryen 段のみ)。
- 署名ガードの変種 (既定): `ref` (-O0 / no-gc) / `o2` / `o3` (LTO 無) / `std`。`<tag>=<profile>` 形式と `cfg.emcc.variant_extra[<tag>]` で変種ごとの追加フラグを足せる (Kilohearts 申し送りの register file 局所化 pass の変種はこの枠に載せる)。
- `dev` = 旧 `pipeline.build` の `-O1` / no-gc。後方互換のみ。

入口 (1 つ): `python3 -m liftlib build <cfg.json> [--profile std] [--variants ref,o2,o3,std] [--expect SIG] [--n N]` = RetDec → 修復 → helper 生成 → 全変種 emcc → 同一シナリオ (`cfg.spec`、実機 oracle 不要) を各 wasm に流した出力の正規化署名 (`stdbuild.canon_digest`: diff.py と同じ `compare_ret`/`ignore_buffers`/`mask_ranges`/ポインタトークン規則) → **全一致のときだけ `<name>.cjs` を確定、不一致は exit 1 で成果物なし** (`<name>.sig.json` に変種別署名)。
shell 側: `tools/ott/lift/lift_build.sh` が `python3 liftlib/stdbuild.py flags <profile>` を使い既定 `std` (`LIFT_PROFILE=dev` で旧 -O1)、`LIFT_GUARD=1` で ref 版も作って `ott_x64c_bench.mjs` (`SIG_ONLY=1` を追加。計時なしで署名のみ出力) の署名を比較。
`lift` コマンド (実機差分ハーネス) の既定は `dev` のまま: std への切替は FA 400/400・KH 366/366 の再実行 (素材要) で確認してから。

検証 (`bash tools/liftlib/stdbuild_e2e.sh`、plugin バイナリ・RetDec 不要の合成 lift IR `tests/std/synth.ll` (別 TU helper 付き) と x64c 形の合成 C。3 回実行 3/3 PASS、所要 6 / 5 / 5 s、load(start) 0.17 / 0.24 / 0.38):
- U1〜U6 (emcc 不要): std フラグ・dev が旧 `pipeline.build` と同一の flag 列・禁止フラグ検出・guard 判定・正規化署名 (生ポインタ rax と ignore バッファは署名に入らず、バッファ 1 byte 差は署名が変わる)。
- S1 `pipeline.build_variants`: 4 変種の署名が全て `ddd24d668fb43743`。wasm B: ref 34,749 / o2 7,179 / o3 6,886 / std 7,403 (合成 1 関数での値であり OTT の性能・サイズ主張ではない)。
- C1 x64c 形 C (`emcc_cmd` + 外部 probe + CLI `stdbuild.py guard`): ref / o2 / std の署名 `510de60e` 一致 (wasm B 35,300 / 6,503 / 6,506)。
- 後方互換: `pipeline.build(profile="dev")` の wasm は旧 `build` の emcc コマンドを手で再構成してビルドしたものと sha256 一致 (`d3c673c2449795a7`、14,402 B)。

ネガティブコントロール (全て FAIL を確認):
- 同 IR に `-ffast-math` 変種 (`variant_extra`、profile `dev`) を足す → `ref=ddd24d668fb43743` に対し `fastmath=e8a51f44250f360b`: SignatureMismatch・`<name>.cjs` 無し (別 TU helper の `x*y + 0.1f*x` が再結合される)。C 側も同じ変種で CLI exit 1 (署名 `d5e328bd` 対 `510de60e`)。
- `--expect deadbeef…` 不一致 → exit 1 / `std` に `-msimd128` を混入 → `StdBuildError`。

fail-open の封じ込め (PR #497 レビュー指摘、修正コミット `84067cb`): 署名が取れなかった失敗を「全変種で同値 = 一致」と見なしていた 3 点を fail-closed にした。
- `stdbuild.guard()` は番兵署名 (`TIMEOUT` / `PROBE-FAIL*` / `NO-RESULT` / 空) を含めば全変種同値でも `SignatureMismatch`。`pipeline.build_variants` はタイムアウトを `TIMEOUT`、`canon_digest` 失敗を `NO-RESULT` として記録し guard に落とす (`<name>.sig.json` は残り `<name>.cjs` は作らない)。
- `canon_digest` は R 行 0 件 (= 空文字の sha256 `e3b0c44298fc1c14`) で `StdBuildError`。CLI `guard` は引数パスをキーにし、同名 basename の別ファイルを 1 件に潰さない。重複パス・1 件のみは exit 1。
- `tests/test_stdbuild.py` のネガコン N1〜N4 + C1 (同名 basename 2 件を 2 変種で比較) を追加。`stdbuild_e2e.sh <WORKDIR>` は既存 dir を消さず拒否 (省略時の `work/stdbuild_test` のみ作り直す)。
- 実測 (クリーン detached worktree の HEAD `84067cb`): `bash tools/liftlib/stdbuild_e2e.sh` 3 回 3/3 PASS、所要 13 / 13 / 13 s、load(start) 0.77 / 0.82 / 0.85。S1 署名 `ddd24d668fb43743`・C1 `510de60e` は修正前と同値。
- main 取り込み後 (merge commit `3ca9cda`、節番号衝突の解消のみ): 同 e2e 3 回 3/3 PASS、所要 13 / 13 / 13 s、load(start) 0.15 / 0.28 / 0.73。`OTT_SKIP_INFO=1 bash tools/ott/ott_e2e.sh --quick` PASS 10.7 s (22 シナリオ・9620 cell 全 bit-equal・max_ulp 0)。
- 旧コード (`085b829` の stdbuild.py / pipeline.py + 新テスト) では N1 (`TIMEOUT` 同士が guard を通る)・N2 (存在しない probe で CLI exit 0・「PASS: 1 変種」)・N3 (`canon_digest("")` が署名化)・N4 (全変種 TIMEOUT で `build_variants` 成功)・C1 (a/x.cjs b/x.cjs が「1 変種」に潰れる) がいずれも FAIL。
- 実 OTT (同 HEAD、素材 `analysis-ott-binaries`): `LIFT_GUARD=1 LIFT_OUT=tools/ott/work/lift bash tools/ott/lift/lift_build.sh` PASS 8 s (std / ref とも署名 `6b1696f0`)。空 `.cjs` 2 件 + `ott_x64c_bench.mjs` (`SIG_ONLY=1`) の CLI guard は `PROBE-FAIL(rc=1)` 同士でも exit 1。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 OTT (x64c) の std 既定 + `LIFT_GUARD=1`: `OTT_SKIP_INFO=1 bash tools/ott/ott_e2e.sh --quick` は HEAD `84067cb` で PASS 11 s (22 シナリオ・9620 cell 全 bit-equal・max_ulp 0・state_diff 0)、`LIFT_GUARD=1` は上記のとおり署名 `6b1696f0` 一致。`perf_gate.sh` は本修正後は未実行 (レビュー run が `085b829` で 11/11 PASS を報告、署名ガード修正は perf ハーネスに触れない) | `perf_gate.sh` の修正後 HEAD 再実行のみ残る | #155 (再レビュー run で `oc_artifacts: toolchain-emsdk analysis-ott-binaries`) |
| RetDec 経路 (FA/KH/OTT leaf) で `liftlib build` を未実行 (RetDec と plugin バイナリ無し)。期待署名 `cfg.signature.expect` も未記録 | 実ターゲットでの全変種署名一致が未確認 | #155 (素材: `toolchain-retdec work-liftlib-targets plugins-freshair plugins-kilohearts`) |
| `lift` / `liftlib ott` (recipes/ott.py の -O0 -g1 固定) の既定を std に切替えていない | 標準設定が `build` と lift_build.sh だけ | #155 (上の実行後に切替) |
| register file 局所化 (alloca → mem2reg) pass 自体は未実装 (#54 申し送り、REPORT は推定のみ・実測無し)。署名ガードの変種として載せる枠 (`variant_extra`) だけ用意 | Path B の wasm サイズ縮小は未着手 | 新規子チケット (`[PERF-n]`、親 #17。番号は PM 採番) を PM が起票 |
| `tools/ott/{avx,entry,crtinit}` の `-O1` 固定 emcc 行は未変更 | 当該 e2e は std 未適用 | #155 (lift_build.sh の std 検証後に同じ `stdbuild.py flags` へ) |
| `lift_build.sh` の dev は旧スクリプト (-O1) に `-Wl,--no-gc-sections` が増える (旧は -O1 既定の gc) | LIFT_PROFILE=dev の wasm サイズのみ | 影響軽微・対応なし |

## §20 LIFTLIB-7 (#478) ott_auto_none: FAIL 原因の実測・fail-closed 化・ネガコン・census 再計算

検証環境: nproc=4、並列なし、素材は PR 本文の `oc_artifacts` 7 本 (`work-m6-ott` が `tools/{m6,m8,m9,m10,ott}/work`、`analysis-ott-binaries` が `OTT_vst2_win64.dll` を供給)。pefile/capstone/numpy は `$RUNNER_TEMP` の uv venv、node は `/opt/emsdk/node/24.19.0_64bit/bin`。
旧コードの測定起点 HEAD `25330e7`、修正後は commit 済み HEAD `96a3887` (cli.py `ott_judge` / test_unit T18 / `ott_census.py`)。

**1. FAIL の原因 (実測)**: `--auto none` の合否に census 閾値は無く、junkHi 175 は表示値 (`cmd_ott`)。FAIL 条件は e2e (checks/maxdev/nbad/trap)・7 段 IR 一致・出力 SHA 突合の 3 つ。素材が揃えば PASS、**参照成果物が欠けると FAIL** になる (log の census 行は junkHi 175 を表示するので、FAIL と census 値が同居して見える)。

| 条件 (旧コード HEAD `25330e7`、`ott --auto none`) | 結果 | real (load 実行前) |
|---|---|---|
| 全素材あり | RESULT PASS rc 0。IR 一致 7 段 true、checks 8 / broken 0、maxdev 0.0 / nbad 0、trap 0、junkHi 175、outhash 42/42 (f0 21/21) | 11.741 秒 (load 0.31) |
| `tools/m10/work/ott_m10.ll` を欠落 | **RESULT FAIL rc 1**。`O4_m10_ll_identical: null` (`same()` が None)。他の IR 6 段 true、checks 8 / broken 0、junkHi 175 | 11.059 秒 (load 0.30) |
| `ott_m10.cjs(.wasm)` を欠落 (`ott_m10.ll` あり) | **RESULT PASS rc 0** (outhash は `None` のまま素通り) | 10.121 秒 |
| (依存未導入) | `liftlib/pe.py:10 import pefile` で `ModuleNotFoundError` | — |

- 元の FAIL 報告 (Actions run、census junkHi 175 を伴う) の素材構成は本 run から見えない。**元の run が `ott_m10.ll` 欠落だったことは未確認 (推定: 当時は `work-m6-ott` を渡せず `tools/m10/work` が無かった。#478 の素材行に `work-m6-ott` が無いことと、上の欠落再現が一致するため)**。
- **旧コードの穴 (実測)**: 参照 `ott_m10.cjs` が無いと outhash が実施されず、`--auto none` は SHA 突合なしで PASS・rc 0 になる (上表 3 行目)。IR 一致の `None` は FAIL でも、outhash の欠落は PASS だった。一貫していなかった。

**2. 修正 (期待値ではなく判定の側)**: 期待値 (junkHi 閾値) は `--auto none` に無く、古くもない。直したのは判定の fail-closed 化 (`cli.py` `ott_judge`)。`--auto none` は IR 一致 7 段 (None = 参照欠落は不合格)・outhash 実施かつ一致 (未実施・実行失敗・不一致は不合格)・e2e 合格の全てを必須とする。参照欠落は rc 2、不一致は rc 1 で区別する。`auto` 既定の junkHi ≤ 104 は junkHi が取れない場合も不合格にした。

**3. ネガコン (実測、HEAD `96a3887`)**:

| 操作 | 結果 |
|---|---|
| `ott_m10.cjs(.wasm)` 欠落 (旧コードは PASS rc 0) | `[ott] NG: outhash 未実施`、**RESULT FAIL rc 2**。10.172 秒 |
| `ott_m10.ll` 欠落 (cjs あり) | `NG: IR 一致 O4_m10_ll_identical: 参照 .ll が無い`、**RESULT FAIL rc 2** |
| 全素材あり | RESULT PASS rc 0。IR 一致 7 段 true、checks 8 / broken 0、junkHi 175、outhash 42/42。11.245 秒 (load 0.63) |
| `ott_judge` の None 分岐を `continue` に変異 | T18 が `AssertionError` で落ちる (検出力あり。元に戻して再 PASS) |
| `tests/test_unit.py` T18 (正 1 + NC1〜NC6 + auto 閾値 3) | 全 PASS。`python3 tests/test_unit.py` は ALL UNIT TESTS PASS、real 5 分 13.634 秒 (load 0.34) |
| `python3 -m liftlib regress` | `{"fa_gain":"PASS","kh_gain":"PASS","ott":"PASS","ott_auto_none":"PASS"}`、rc 0。39.490 秒 (load 0.92) |

**4. 数え方の定義と再計算スクリプト**: junkHi は `recipes/ott/e2e_check.mjs` E6 の出力分類で、param 0.5・N=256×2ch・float32 出力 512 値を `[0x248]=0/1` で 1 回ずつ処理し、`v==0`→zero、NaN→nan、`|v|>=4`→**junkHi**、`|v|<=1e-18`→junkTiny、他→normal と数える。再計算は `python3 tools/liftlib/ott_census.py <cjs> [--f248 0|1] [--expect-junkhi N] [--max-junkhi N]` (取得不能 rc 2、期待値違反 rc 1)。実測 (HEAD `96a3887`):

| 対象 | 実行 | 結果 |
|---|---|---|
| `work/ott/ott_gen.cjs` (`--auto none`) | `--expect-junkhi 175` | junkHi 175 / zero 132 / normal 69 / junkTiny 136 → PASS rc 0 (0.827 秒) |
| 同 | `--expect-junkhi 104` (ネガコン) | FAIL rc 1 |
| 同 | `--f248 1` | junkHi 252 / zero 4 / normal 254 / junkTiny 2 (表示のみ) |
| `work/ott_auto_f2_f7_p1/ott_gen.cjs` (auto 既定) | `--max-junkhi 104` | junkHi 104 / normal 140 → PASS rc 0 (1.401 秒) |
| 同 | `--max-junkhi 103` (ネガコン) | FAIL rc 1 |
| 存在しない cjs | `--expect-junkhi 175` | 取得不能 rc 2 |

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 元の FAIL の run が `ott_m10.ll` 欠落だったかの裏取り (推定のまま) | 原因は「参照欠落で FAIL する」ことまでは実測。元 run の素材は未確認 | #478 (PM が元 run の素材一覧を確認できれば確定) |
