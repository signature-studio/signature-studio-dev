# REPORT_679 — icall site 0x41037d の hit 23,053,861 の内訳と判定 (#679, 親 #419 / PR #446)

**既知類型との関係: 該当 ID なし。** 計測 site 0x41037d・0x41032e は RetDec が落とした VMT 間接 call (`call [rbx-0x50]` /
`call [rax-0x30]`) を C 転記した箇所で、D15 型 (`docs/DEFECTS.md` D15) の転記に付随して計上される (DEFECTS.md D15 とは別物として扱う)。
暴走 loop の根本原因が既知類型かは未検証 (§5)。

## 0. 結論 (先出し)

1. **23,053,861 hit の 99.999% は unit idx 101 (VA 0x1de960, halt0) 1 本**: 23,053,622 hit。残り 70 unit の合計は **239 hit** (最大は unit 54 の 41 hit)。
2. **unit 101 は #513 の暴走 unit と同一**: VA 0x1de960 / halt0 / VirtualAlloc 1477.2 MB が #513 の 1,477,181,440 B (GetMem 23,056,285 回) と一致。(#513 のコメントは VA を 0x5de960 と書くが、0x5de960 − 0x400000 = 0x1de960 で同じ VA の表記違い。本 REPORT は image base 0x400000 を引いた値 0x1de960 で統一する。)
3. **判定: 正常な頻度ではなく暴走と判断**。根拠は §3 (halt 時の生存スタックが 1 段ずつ、object 生成が 1:1、OOM で停止、残り unit は 239 hit)。loop は 1 スナップショットからの推定。
4. **既定ビルドでは 0x41032e (410320) 経由で同じ暴走が出る**: `M11_OV_CLASSCREATE=0` (既定) では site 0x41037d は 0 hit だが、410320 (ClassCreate) が vmtNewInstance を呼ぶ site **0x41032e が 23,053,917 hit** (unit 101 は 23,053,623)。410320 は `M11_OV_CLASSCREATE` では制御されず、#474 以降常時転記されている (`m11_ov.c` L646-647)。issue の 0x41037d の数値だけが ON 構成でのみ現れる。

受入条件: 1 (内訳) 達成 (§2)・2 (#513 との関係) 達成 = 同一 unit の確認 (同一根因かは未確定、§5)・3 (判断と根拠) 達成 (§3)。

## 1. 測定の基準と再現 (検証起点)

- 検証起点 commit: `8d883c3` (origin/main)。本 PR のコード変更は `trap_triage/icall_41037d_679.py` (計測・検査) と本 REPORT のみ。`m11_ov.c` 等は未変更。
- **基準 (c)** = `docs/REFERENCES.md` `[WIN64]` の fl-win64 (PE `block00031_PE.bin`) で IR・data・image を再生成したもの (REPORT §8.2 の採用基準と同じ)。
  work-m11 スナップショット (基準 (a)) の IR は古いため、再現数値は基準 (c) で取った。
- 基準 (a) (スナップショット IR のまま) の ON は 0x41037d の ok 23,054,371 (miss 8) で、基準 (c) と 510 hit 違う (§8.2 (e) の基準固定の問題と同じ)。

再現 (1 コマンドずつ。PE の素材は `[WIN64]` (`docs/REFERENCES.md`) の fl-win64 を使う。`m11_gen_ir2.sh` は PE 行を固定値で持つため、PE 行を差し替えた一時コピーを `work/` に作って実行した。コミットはしない):

```sh
cd tools/m11
export FL_WIN64_DIR=<fl-win64 の展開先>          # 例: $RUNNER_TEMP/fl-win64 (tar --zstd -xf fl-win64.tar.zst)
PE=$FL_WIN64_DIR/extracted/block00031_PE.bin
sed -e "s#^cd \"\$(dirname \"\$0\")\"#cd $PWD#" -e "s#^PE=.*#PE=$PE#" m11_gen_ir2.sh > work/gen_ir2_pe.sh
uv run --with capstone --with pefile python3 m11_image_gen.py "$PE" && uv run --with capstone --with pefile python3 m11_data_gen.py "$PE"
uv run --with capstone --with pefile bash work/gen_ir2_pe.sh          # boot_final.ll (ldfix 込み)
M11_OV_CLASSCREATE=1 uv run --with capstone --with pefile bash m11_build.sh   # ON (qstore は capstone が要る)
node trap_triage/survey_units.mjs work/trap_triage/on_c.json
python3 trap_triage/icall_41037d_679.py work/trap_triage/on_c.json --expect-ok 23053861 --expect-miss 9
M11_OV_CLASSCREATE=0 uv run --with capstone --with pefile bash m11_build.sh   # OFF (ネガコン)
node trap_triage/survey_units.mjs work/trap_triage/off_c.json
python3 trap_triage/icall_41037d_679.py work/trap_triage/on_c.json --off work/trap_triage/off_c.json
```

LB_BASE は 0 (既定)。IR の lift 段 (`boot0..4.lift.ll`) は work-m11 スナップショットを使い、RetDec の再 lift はしていない。

## 2. 実測 (基準 (c))

### 2-1. unit 別の内訳 (`icall_41037d_679.py`、ON、942 unit)

| unit | VA | kind | va_mb | site 0x41037d ok | miss | site 0x41032e ok (410320) | 合計比 |
|--:|---|---|--:|--:|--:|--:|--:|
| 101 | 0x1de960 | halt0 | 1477.2 | **23,053,622** | 0 | 23,053,623 | **99.999%** |
| 54 | 0x1658e0 | ok | — | 41 | 0 | 41 | 0.000% |
| 56 | 0x16fde0 | halt0 | — | 21 | 1 | 23 | 0.000% |
| 61 | 0x17fd50 | ok | — | 16 | 0 | 16 | 0.000% |
| 45 | 0x12f1f0 | miss | — | 15 | 1 | 16 | 0.000% |
| 95 | 0x1d2680 | oob | — | 14 | 0 | 14 | 0.000% |
| 58 | 0x177290 | ok | — | 12 | 0 | 12 | 0.000% |
| 53 | 0x158e20 | ok | — | 11 | 0 | 11 | 0.000% |
| 63 | 0x182230 | ok | — | 8 | 0 | 8 | 0.000% |
| 311 | 0x4cb690 | ok | — | 6 | 0 | 6 | 0.000% |

- 0x41037d の合計: **ok 23,053,861 / miss 9 / 71 unit**。上位 1 unit 以外は 239 hit (70 unit)。
- 0x41032e (410320 の `call [rax-0x30]`、既定 ON) の合計: ok 23,053,917 (100 unit)。
- 検査 (スクリプトが自動判定): (1) unit 合計 = sidecar 累計 (`<survey>.icall.json`) ✔ (2) 0x41037d の ok = 別カウンタ target 0x410070 の ok ✔ (3) 最上位 unit が idx 101 (0x1de960, halt0) かつ 99% 以上 ✔ → `RESULT PASS`。

### 2-2. 基準・構成ごとの値 (survey: `SURVEY_UNITS` 行)

| 基準 | build | ok / oob / halt0 / miss / noproc | 0x41037d ok (miss) | 0x41032e ok |
|---|---|---|--:|--:|
| (c) | ON (`M11_OV_CLASSCREATE=1`) n=3 | 823 / 13 / 54 / 51 / 1 | **23,053,861 (9)** (n=3 とも同じ) | 23,053,917 |
| (c) | OFF (既定) | 828 / 13 / 54 / 46 / 1 | 0 (0) | 23,053,917 |
| (a) スナップショット | ON | 813 / 23 / 55 / 50 (noproc 1) | 23,054,371 (8) | 23,054,426 |
| (a) スナップショット | OFF | 818 / 21 / 56 / 46 / 1 | 0 (0) | 23,054,426 |

- (c) ON / OFF の survey は REPORT §8.2 (c) の値、(a) は §8.2 (a) の値と一致 (既存の数値の再現)。
- 所要 (n=1 の参考値、4 コア runner、1 本ずつ直列、load average 0.44–0.70。範囲は測っていない): IR 再生成 (`gen_ir2`、ldfix 込み) を含む 21.8 s (wall、初回に失敗した image/data 2 件を含む)、image + data の本実行 1.0 s、ON build 25.2 s (wall)、ON survey 18.4 s (wall)。

## 3. 判定: 正常な頻度ではなく暴走と判断 (根拠)

1. **集中**: 上表のとおり 99.999% が 1 unit。他 70 unit は合計 239 hit (1 unit あたり最大 41) で、同じ site がこの桁に留まることを示す。
2. **ループの可能性が高い (再帰ではないと見える)**: unit 101 が halt0 (OOM) で止まった時点の生存スタック (innermost → outermost) は
   `409730` (Error) ← `409410` (GetMem) ← `40f960` (NewInstance) ← `m11_icall` ← `410320` (ClassCreate) ← `448d40` (Exception.Create) ← `47a250` ← `4fa210` ← `4fa8f0` ← `4fb980` ← `5de960` (unit 初期化) ← `m11_call_unit`。
   halt 時点の 1 スナップショットでは各 frame が 1 段ずつで、深さは増えていない。`4fa210` の 1 段が繰り返し呼ばれ、その都度 例外 object を作る形に見える。
   (注: 1 スナップショットからの推定であり、周回数そのものは未計測。)
3. **object 生成が 1:1 (0x41032e と 0x41037d の対応)**: 0x41032e (ClassCreate の vmtNewInstance call site) 23,053,623 と 0x41037d (AfterConstruction) 23,053,622 はほぼ一致する。
   1 object 生成 = 1 GetMem (`409410`) = 1 AfterConstruction とみなせる。#513 の「1 回あたり 64.07 B」で割ると確保量 1477.2 MB と整合 (推定)。
   (注: NewInstance 側の target hit は本 REPORT の表に実測値として載せていないため、根拠に使わない。)
4. **終了せず OOM で停止**: halt0 の経路は GetMem 失敗 (`409410` → `409730`)、wasm の `growMemory` が上限で失敗 (`err` に記録)。正常終了ではない。
   確保した object は解放されない (#513 の実測で FreeMem 0 回) → 1.48 GB がそのまま残る。

## 4. 検査スクリプトの負のコントロール (`trap_triage/icall_41037d_679.py`)

検査スクリプトの負のコントロールは、合成 fixture (`tools/m11/work/trap_triage/`、gitignore、コミットなし) で本 PR の HEAD 上で実測した。

| 条件 (fixture) | 期待 | 実測 |
|---|---|---|
| 正しい期待値 (ok 1005 / miss 2) + `--off` (OFF の 0x41037d = 0) | PASS | `RESULT PASS`、exit 0 |
| 期待値を 1 だけ外す (`--expect-ok 1004`) | FAIL | `FAIL (5) ok 1005 != 期待 1004`、`RESULT FAIL`、exit 1 |
| ON の survey を `--off` に渡す (0x41037d が 1007 hit) | FAIL | `FAIL (4) OFF なのに 0x41037d が 1007 hit`、`RESULT FAIL`、exit 1 |

実データ (942 unit の survey) での PASS (`--expect-ok 23053861 --expect-miss 9`) は、本 REPORT の初版で取得したもの。survey の JSON は `work/` にあり本 PR では再実行していない。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 101 の loop の終了条件 (`4fa210` の走査が止まらない理由)・例外 object が解放されない (FreeMem 0) 理由 | 1 unit が 1.48 GB を確保して OOM で halt0 (#513 の残件そのもの)。根本原因 (lift 欠陥か本来の挙動か) は未特定 | #739 (`[M11-N40]`。#513 は CLOSED のため新規起票) |
| #513 の GetMem 23,056,285 と本測定の AfterConstruction 23,053,622 (unit 101) の差 2,663 | 未切り分け (測定基準の差か、410320 を経由しない GetMem か) | #739 |
| 基準 (a) (スナップショット IR) と (c) で 0x41037d が 510 hit ずれる | 測定基準の固定 (§8.2 (e) と同じ) | 既存 #419 の (e) 判断 (PM) |
| 既定ビルドでも同じ hit が site 0x41032e に出る | 「ClassCreate override の計測」を読むとき、既定 ON の site を併記しないと誤読する | 本 REPORT で説明 (追加の起票なし) |

## 6. 次の一手 (提案)

- (追跡先は #739、§5) unit 101 の `4fa210` の走査条件 (リスト終端判定) と `47a250`・`448d40` の例外 object 解放経路を逆アセンブルで見る。
  解放経路の間接 call が D15 型で落ちていないかを確認する (仮説。未検証)。
- 周回数の実測: `4fa210` の入口を数える probe を入れて、1 周回あたり object 数 (1 のはず) を確かめる。

## 9. 現 HEAD での再測と、halt0 が消えた commit の特定 (#2773, 親 #739)

既知類型との関係: 該当 ID なし (暴走の機構は未確定。本節は測定事実と差し替え実験の結果のみ)。

### 9-1. 結論 (先出し)

1. **測定 commit `bae12679` (origin/main 当時) の ON (`M11_OV_CLASSCREATE=1`) では unit 101 の halt0 (暴走) は再現しない。** unit 101 は **oob** (0x41037d 1 hit)。halt0 は 7 unit。OFF (既定) の unit 101 の値は本 PR では**未測定** (本 script は ON のみを build する。#739 の既存記録は未検証のため根拠にしない)。oob の frame は本 script の出力に含めないため、本節では扱わない。
2. **検証起点 `8d883c3` では §2 の値が再現する**: unit 101 halt0、0x41037d 23,053,622、0x41032e 23,053,623、halt0 54 unit (§2-2 の (c) ON と一致)。
3. **二分探索**: `tools/m11`・`tools/shared` を変える first-parent commit 388 件から、9 回で境界を特定した。`035274be` (PR #700) は halt0 53 unit・unit 101 halt0 (bad)、**`04fafae6` (PR #701 の merge) は halt0 8 unit・unit 101 oob (good)**。測った標本 6 commit (`503d1915` ほか、§9-2) も halt0 7〜8 unit で、減少は #701 で起きた (標本の外の commit は未確認)。
4. **差し替え実験**: `04fafae6` のツリーで 1 ファイルだけ、または 1 部分だけ `035274be` の版に戻した (下表)。ON, unit 101 の値。
5. **結論の範囲**: 暴走の消失 (halt0 → oob) は、`m11_win.c` の trace 用の 3 行 (`extern int m11_trace_flag;`・`EM_JS(m11_js_stack)`・MessageBoxA の `m11_js_stack()` 呼出し) に依る。BSTR 実装 (SysAllocStringLen 等) ではない。機構 (なぜ JS import の追加で 4fa210 の周回が止まるか) は**未確定**。

| 構成 (`04fafae6` ベース・ON。ただし最終行のみ `035274be` ベース) | unit 101 kind | 0x41037d hit | halt0 unit |
|---|---|--:|--:|
| そのまま (= #701 merge) | oob | 1 | 8 |
| `m11_ov.c` だけ `035274be` 版 (B) | oob | 1 | 8 |
| `m11_win.c` だけ `035274be` 版 (A) | **halt0** | **23,053,163** | 55 |
| `m11_win.c` から BSTR 3 関数だけ除去 | oob | 1 | 8 |
| `m11_win.c` から trace 用 3 行だけ除去 | **halt0** | **23,053,163** | 55 |
| ネガコン: `035274be` の `m11_win.c` 末尾に無害な関数を 1 つ追加 (`035274be` ベース) | halt0 | 23,053,622 | 53 |

- 行 3 と行 5 は同じ値 (23,053,163)。行 4 (BSTR を除去) は oob のまま。
- 行 6 (`035274be` に無害な関数を追加) は halt0 のまま。単に `m11_win.c` に定義を足したことでは消えない。
- **仮説 (未検証)**: `EM_JS` は wasm の import を 1 つ増やす。import が増えると defined function の wasm index が全体にずれる。index を値として使う箇所 (icall の解決・関数ポインタの格納) が別の関数を指すと、周回が止まらなくなる可能性がある。行 6 は defined function を末尾に足すだけで index がずれないため、この仮説と整合する。検証には、import を増やさずに index だけずらす変更、または icall の解決先の確認が要る。

### 9-2. bisect の全点 (`halt0` unit 数・unit 101 の kind、ON)

| commit | 区分 | halt0 unit | unit 101 |
|---|---|--:|---|
| `8d883c3` (#446、検証起点) | bad | 54 | halt0 (0x41037d 23,053,622) |
| `035274be` (#700) | bad | 53 | halt0 |
| `04fafae6` (#701 merge) | good | 8 | oob (1 hit) |
| `503d1915` / `9957996e` / `0760e367` / `28dbfb32` / `6d77c635` / `5cf3dd6a` | good | 7〜8 | halt0 以外 (kind は未記録。判定は halt0 の有無のみ) |
| `bae12679` (測定 commit = origin/main 当時) | good | 7 | oob (1 hit) |

- `8d883c3`・`035274be` の halt0 数の差 (54 → 53) は、unit 101 以外の halt0 unit が 1 件変わったことによる。
- 9 回の探索で、`035274be` と `04fafae6` が隣接することを確認した (二分探索の範囲 idx 2→3)。monotone を仮定しているため、途中に反転があれば見落とす。

### 9-3. 再現手順 (1 コマンド)

```sh
export FL_WIN64_DIR=<fl-win64 の展開先>          # 例: $RUNNER_TEMP/fl-win64 (tar --zstd -xf fl-win64.tar.zst)
bash tools/m11/trap_triage/unit101_2773.sh bae12679                                   # bae12679 の ON
bash tools/m11/trap_triage/unit101_2773.sh 04fafae6 tools/m11/m11_win.c 035274be    # 表の行 3 (A)
```

`git archive <commit>` で `tools/m11`・`tools/shared` を `$RUNNER_TEMP/unit101_2773/` に展開し、`work-m11` の lift 出力から IR を作り直す。作業ツリーは変えない。
所要は n=1 (1 回の実行) の値で、min–max は未測定: 50〜60 秒 (4 コア、load 0.5〜1)。

### 9-4. 検証範囲と限界

- 素材: fl-win64 `block00031_PE.bin` の sha256 は `b2c64da40921cf262c15c5b25c2b0422e4d1851e953c87e0bc38ed2c19f9496d`。確認コマンド: `tar --zstd -xOf fl-win64.tar.zst extracted/block00031_PE.bin | sha256sum` (2026-10-14 に実行して一致)。work-m11 の lift 出力 (`boot0`〜`boot4.lift.ll`) を入力にし、各 commit の m11 pass で IR を作った。lift 出力の生成元 PE は本節では未確認。
- 各構成は n=1。ただし `8d883c3` の値は §2 の n=3 と完全に一致する (決定的に再現する)。
- 範囲外: 差 2,663 の切り分け (親 #739)・機構の確定 (#2773 に残す)。

### 9-5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 暴走の機構: trace 用 3 行 (JS import 追加) で 4fa210 の周回が止まる理由。index ずれの仮説の検証 | 受入 1 (根本原因) が未達。既知類型への対応も未確定 | #2773 (open のまま) |
| 差 2,663 (GetMem 23,056,285 と AfterConstruction 23,053,622) | 未切り分け | #739 (親) |
| 既定 (OFF) の unit 101 の値が未測定 (本 script は ON のみ build する)。ON の結果だけで既定ビルドの挙動は断定できない | 既定ビルドの暴走の有無が未確定 | #2773 (open のまま。再測定だけの子は起票しない) |
| 数値の取得元未記録 (REPORT_739 §5) | 本節の値で置き換えない。REPORT_739 の未検証値は根拠にしない | #739 |

### 9-6. 測定以降のコード差分 (WORKFLOW §6)

測定 commit は `bae12679`。既存の `tools/m11`・`tools/shared` のコードに測定以降の差分が無いことの証跡:

```sh
git diff bae12679 HEAD -- tools/m11 tools/shared ':(exclude)tools/m11/trap_triage/unit101_2773.sh' ':(exclude)tools/m11/trap_triage/REPORT_679.md'
```

- 出力: 0 行 (確認時の HEAD は本 commit の親 `295c2c0b`)。本 commit が変えるのは、除外した 2 ファイル (`unit101_2773.sh`・本 REPORT) だけ。
