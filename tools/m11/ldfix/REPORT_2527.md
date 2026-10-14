# #2527 (LD-117): fix_ld115 を本番 IR 生成経路 (m11_gen_ir2.sh → m11_build.sh) に配線

親: #2447 (LD-115、CLOSED)。前段: #2402 (LD-112、CLOSED。fix_ld108 の配線)。

**判定: 達成** (受入条件 4 件すべて)。`fix_ld115.py` を `m11_gen_ir2.sh` の fix_ld108 直後に配線し、`m11_build.sh` が `ld115=applied` を要求するようにした。本番経路で作った wasm で 666a60 の AFTER が PASS、survey 942 unit で ok 退行 0。

測定 commit: `4ec81912` (コードを変えた最後の commit)。

## 1. 受入条件

| 受入条件 | 結果 |
|---|---|
| `m11_gen_ir2.sh` の fix_ld108 の直後に `fix_ld115.py` を配線。`M11_FIX_LD115=0` で無効化。`ir_conditions.json` に `ld115=applied` / `ld115=disabled` を記録 | **達成**。§2 |
| `m11_build.sh` が `ld115=applied` を要求 (`ld108` と同じ fail-closed)。`M11_ALLOW_LD115_DISABLED=1` の opt-in のみ無効 IR を build | **達成**。§2、ネガコン NC4 (opt-in 無しで rc 2) |
| 本番経路 (`m11_gen_ir2.sh` → `m11_build.sh`) で作った wasm で `dyn_ld115.mjs` の AFTER が PASS | **達成**。§3 (after = 既定の経路で作った wasm) |
| survey 942 unit の修復前後の突合で ok 退行 0 | **達成**。§4 (ok 872 → 872、退行 0) |

## 2. 配線

- `tools/m11/m11_gen_ir2.sh`: `--reset` に `ld115=not-applied` を追加。fix_ld108 の後に `ldfix/fix_ld115.py` を掛けて `ld115=applied` を記録。`M11_FIX_LD115=0` のときは `ld115=disabled` を記録して掛けない。`ldfix=skipped` (fail-closed) の枝には入れない。
- `tools/m11/m11_build.sh`: `ldfix=applied` の枝で `ld115` を検査。`disabled` かつ `M11_ALLOW_LD115_DISABLED=1` のときだけ WARNING を出して通す。それ以外で `applied` でなければ rc 2 で止める。
- `tools/m11/ldfix/ld115_e2e.sh`: 旧版は `work/boot_final.prealloca.ll` から IR を作り、`ld108=applied` を手で記録していた。新版は本番経路 (`m11_gen_ir2.sh` → `m11_build.sh`) の A/B に組み替えた (§3・§4・§5)。
- ldfix の順序は本番と同じ (ldfix → fix_ld108 → fix_ld115)。`ld108_e2e.sh` の build 経路 (`M11_ALLOW_LD108_DISABLED=1`) も `ld115=applied` の IR を使うため、本変更の影響を受ける。§5 で再実行して確認した。

## 3. 本番経路の A/B と動的確認 (受入条件 1・3)

`ld115_e2e.sh` (HEAD `4ec81912`)。

| 版 | IR の作り方 | build | `ld115`・IR の sha256 (先頭 8 桁、build 直前) | `DYN 666a60` (`dyn_ld115.mjs`) |
|---|---|---|---|---|
| pre (修復前) | `M11_FIX_LD115=0 m11_gen_ir2.sh` | `M11_ALLOW_LD115_DISABLED=1` | `disabled`・`7c653b0f` | **TRAP** (`memory access out of bounds`) |
| mid (negctl) | pre の IR に `fix_ld115.py --only count` | 同上 (指紋だけ手で記録) | `disabled`・`64182871` | FAIL(slot0.f16) (`slot0.f16=0x10be8d30` ほか) |
| post (修復後) | 既定の `m11_gen_ir2.sh` | 通常 | `applied`・`fc0403c9` | **PASS** (`N=0x10be8cf0`、`ret=0x3`、`count=0x3`、`slot{0,1,2}.f16=0x10be8cf0`) |

build 後は `qstore` が適用されて指紋が変わる (post は `67bbdbeb`)。`m11_cond --check` は build 後も全版で一致 (PASS)。

- IR の差は `function_666a60` の 1 関数だけ (関数単位の検算 `LD115_IRDIFF` で確認。関数外の本文は一致)。diff は 8 行 (回数初期値の `store` 1 行 → `load i32`・`zext`・`store` の 3 行、ループ内 `store` 1 行 → `inttoptr`・`load`・`store` の 3 行)。
- `DYN_SUMMARY after_fail=0/1`。pre の TRAP と mid の slot.f16 FAIL は、REPORT_2447 §4 の BASE・MID と同じ判定になった (ただし IR の生成経路が違う: §4 注)。

## 4. survey 942 unit (受入条件 4)

`trap_triage/survey_units.mjs` を pre・post の wasm で実行し、`survey_diff.py` で突合。

| 項目 | pre | post |
|---|--:|--:|
| ok / miss / other / halt0 / oob / noproc | 872 / 47 / 1 / 7 / 14 / 1 | 872 / 47 / 1 / 7 / 14 / 1 |
| 遷移 (A → B) | 全 942 unit で kind 不変 (ok → ok 872、oob → oob 14、halt0 → halt0 7、miss → miss 47、other → other 1、noproc → noproc 1) | |
| ok 退行 unit | **0** | |
| kind 以外も含めた差分 unit | **0** | |
| icall sites・targets の [ok, miss] 差 | 0 件 | 0 件 |

注: REPORT_2447 §5 の ok 869 とは数値が違う。2447 は `boot_final.prealloca.ll` から作った IR で測り、本 REPORT は本番経路 (`m11_gen_ir2.sh` → `m11_build.sh`、qstore・alloca 等を含む) の IR で測った。A/B の対は同じ経路で揃えてある。
限界: 666a60 は survey の 942 unit で実行されない (REPORT_509 §4.3 の既存測定)。本 run では入口通過を再測定していない。したがって ok 退行 0 は「関数が実行されないこと」によるもので、修復の波及は survey では測れない。

## 5. ld108 の回帰確認

`ld108_e2e.sh` を HEAD `4ec81912` で実行: rc 0・208 秒・`LD108_E2E_SUMMARY fail=0`。DYN 41a670 は before=0x3333 (FAIL)・after=0x2222 (PASS)。survey ok 872 → 872、退行 0。`build` の追加検査 (ld115) は ld108 の経路でも通る (既定の IR は `ld115=applied`)。

## 6. 検証 (WORKFLOW §6)

- 測定 commit: `4ec81912`。`git diff 4ec81912 HEAD -- tools/m11 ':(exclude)*.md'` の出力 (コード・スクリプトの差分) は 0 行 (本文執筆時点の HEAD で確認)。以後の commit は REPORT と DOC_MAP のみ。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/ldfix/ld115_e2e.sh` (前提: `tools/m11/work` に work-m11、`[EMSDK]` (`/opt/emsdk`)、`capstone`・`pefile`。`fl-win64` は `$ARTIFACTS_DIR/fl-win64.tar.zst` を展開)。
- 所要: `4ec81912` で 205 秒 (rc 0)。直前のコード同一の実行で 209 秒。load average (1 分) は実行前 0.58、実行後 1.01 (4 コア)。
- 出力: `LD115_E2E_SUMMARY fail=0` (NC1〜NC4 と IR・指紋・DYN・survey の全 PASS)。
- 20 MiB 超の blob: 本 PR は含めない (ir・wasm は `work/` にのみ置く)。

## 7. 製品 KPI (起動・GUI に関わる変更の扱い)

本 PR は m11 の IR のうち `function_666a60` (ループ回数・ループ内 store) だけを変える。**起動 KPI (FLEngine 起動の dispatch 数・通過 unit 数・最初のウィンドウ) は動かしていない**。起動 e2e (`tools/flelift/boot`) は本 run で実行していない。survey の ok は 872 → 872。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 起動 KPI の前後測定 (`tools/flelift/boot`) | 本修復が起動経路の KPI をどう動かすかは未測定 | 本 PR の未解決表で追跡 (再測定のみのため起票しない) |
| 666a60 が survey で実行されない (REPORT_509 §4.3) | ok 退行 0 は実行されないことによる。修復の波及は survey では測れない | REPORT_2447 §9 から継続 (本 run では再測定しない) |
| 回数 0 の早期脱出 (機械語 `666ae0`〜`666ae4`) が IR に無い | arg2=0 で wasm が trap する | 子 #2513 (LD-116) |
| 欠陥の根本原因 (RetDec のどの段か) | 修復は後追いの単独パッチのまま | REPORT_2447 §9 から継続 (原因調査のみのため起票しない) |
