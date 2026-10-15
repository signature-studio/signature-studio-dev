# #2527 (LD-117): fix_ld115 を本番 IR 生成経路 (m11_gen_ir2.sh → m11_build.sh) に配線

親: #2447 (LD-115、CLOSED)。前段: #2402 (LD-112、CLOSED。fix_ld108 の配線)。

**判定: 達成** (受入条件 4 件すべて)。`fix_ld115.py` を `m11_gen_ir2.sh` の fix_ld108 直後に配線し、`m11_build.sh` が `ld115=applied` を要求するようにした。本番経路で作った wasm で 666a60 の AFTER が PASS、survey 942 unit で ok 退行 0。

測定 commit: `e7f0baa2` (コードを変えた最後の commit)。main 取り込み (`9aa9270a`) の後で `fix_ld115.py`・`fix_ld116.py`・`ld116_e2e.sh` を直し、その commit で全 e2e を再測定した (§2b・§6)。

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
- `tools/m11/ldfix/ld115_e2e.sh`: 旧版は `work/boot_final.prealloca.ll` から IR を作り、`ld108=applied` を手で記録していた。新版は本番経路 (`m11_gen_ir2.sh` → `m11_build.sh`) の A/B に組み替えた (§3・§4)。
- ldfix の順序は本番と同じ (ldfix → fix_ld108 → fix_ld115)。`ld108_e2e.sh` の build 経路 (`M11_ALLOW_LD108_DISABLED=1`) も `ld115=applied` の IR を使うため、本変更の影響を受ける。§5 で再実行して確認した。

## 2b. N ポインタの同定 (差し戻し対応・e7f0baa2)

main 取り込み後の HEAD (`9aa9270a`) では、`m11_gen_ir2.sh` の fix_ld115 が `assert '%15 = inttoptr i64 %ldfxu18 to ptr'` で止まり、本番 IR が作れなかった (fail-closed。e2e は未実行)。新しい ldfix 出力では N のポインタの SSA 名が `%ldfxu25` に変わったが、`store i32 %10, ptr %15` (機械語 `mov [N], arg2`) の構造は同じだった。`fix_ld115.py` と `fix_ld116.py` は名前ではなく「arg2 の書込み先 `%15`」で N を同定するように直した。`fix_ld115.py` の出力の差分は 8 行で変わらない。

`ld116_e2e.sh` は build 前の記録を直した。pre・mid は `ld115=disabled` を書いて `M11_ALLOW_LD115_DISABLED=1` で build し、post115・post116 は `ld115=applied` を書く。直す前は 4 版すべてが `ld115=applied の記録無し` で rc 2 になっていた。

## 3. 本番経路の A/B と動的確認 (受入条件 1・3)

`ld115_e2e.sh` (HEAD `e7f0baa2`)。rc 0・184.9 秒・`LD115_E2E_SUMMARY fail=0`。

| 版 | IR の作り方 | build | `ld115`・IR の sha256 (先頭 8 桁、build 直前) | `DYN 666a60` (`dyn_ld115.mjs`) |
|---|---|---|---|---|
| pre (修復前) | `M11_FIX_LD115=0 m11_gen_ir2.sh` | `M11_ALLOW_LD115_DISABLED=1` | `disabled`・`c00d5b80` | **TRAP** (`memory access out of bounds`) |
| mid (negctl) | pre の IR に `fix_ld115.py --only count` | 同上 (指紋だけ手で記録) | `disabled`・`c1458199` | FAIL(slot0.f16) (`slot0.f16=0x10be8d30` ほか) |
| post (修復後) | 既定の `m11_gen_ir2.sh` | 通常 | `applied`・`bc98519f` | **PASS** (`N=0x10be8cf0`、`ret=0x3`、`count=0x3`、`slot{0,1,2}.f16=0x10be8cf0`) |

build 後は `qstore` が適用されて指紋が変わる (post は `740852ef`)。`m11_cond --check` は build 後も全版で一致 (PASS)。

- IR の差は `function_666a60` の 1 関数だけ (関数単位の検算 `LD115_IRDIFF` で確認。関数外の本文は一致)。pre → post は 8 行 (回数初期値の `store` 1 行 → `load i32`・`zext`・`store` の 3 行、ループ内 `store` 1 行 → `inttoptr`・`load`・`store` の 3 行)。pre → mid は 4 行。
- `DYN_SUMMARY after_fail=0/1`。pre の TRAP と mid の slot.f16 FAIL は、REPORT_2447 §4 の BASE・MID と同じ判定になった (ただし IR の生成経路が違う: §4 注)。

## 4. survey 942 unit (受入条件 4)

`trap_triage/survey_units.mjs` を pre・post の wasm で実行し、`survey_diff.py` で突合 (`ld115_e2e.sh`、HEAD `e7f0baa2`)。

| 項目 | pre | post |
|---|--:|--:|
| ok / miss / other / halt0 / oob / noproc | 872 / 47 / 1 / 7 / 14 / 1 | 872 / 47 / 1 / 7 / 14 / 1 |
| 遷移 (A → B) | 全 942 unit で kind 不変 (ok → ok 872、oob → oob 14、halt0 → halt0 7、miss → miss 47、other → other 1、noproc → noproc 1) | |
| ok 退行 unit | **0** | |
| kind 以外も含めた差分 unit | **0** | |
| icall sites・targets の [ok, miss] 差 | 0 件 | 0 件 |

注: REPORT_2447 §5 の ok 869 とは数値が違う。2447 は `boot_final.prealloca.ll` から作った IR で測り、本 REPORT は本番経路 (`m11_gen_ir2.sh` → `m11_build.sh`、qstore・alloca 等を含む) の IR で測った。A/B の対は同じ経路で揃えてある。
限界 1: 666a60 は survey の 942 unit で実行されない (REPORT_509 §4.3 の既存測定)。本 run では入口通過を再測定していない。したがって ok 退行 0 は「関数が実行されないこと」によるもので、修復の波及は survey では測れない。
限界 2: survey の基準 IR は `work-m11` の lift 断片から `m11_gen_ir2.sh` で作った。`docs/WORKFLOW.md` §11 は `work-m11` を survey の基準に使わないと明記している。issue #2527 が素材に `work-m11` を指定したため今回は使ったが、この数値はその扱いの下でのみ読む。

## 5. ld108 の回帰確認

`ld108_e2e.sh` (HEAD `e7f0baa2`): rc 0・183.6 秒・`LD108_E2E_SUMMARY fail=0`。IR の差は `function_41a670` の 1 関数だけ (pre → post 6 行、関数外の本文は一致)。DYN 41a670 は before=0x3333 (FAIL)・after=0x2222 (PASS)。survey ok 872 → 872、退行 0。`build` の追加検査 (ld115) は ld108 の経路でも通る (既定の IR は `ld115=applied`)。

## 5b. ld116 (#2513 の検証経路。本番未配線)

`ld116_e2e.sh` (HEAD `e7f0baa2`): rc 0・149.3 秒。`post115 → post116` の IR の差は 14 行。

- DYN 666a60: post115 (`arg2=0`) は TRAP、post116 (`arg2=0`) は `ret=0x0 count=0x0 tag=0x2` で PASS。`arg2=3` は post115 と post116 が同一 (PASS)。
- survey: post115 ok 871 / miss 47 / other 1 / halt0 8 / oob 14 / noproc 1、post116 も同じ。ok 退行 0。
- 注: ld116 の post115 は本番経路の post と IR が 4 行違う (`function_980ed0` の定数 1 箇所: 本番 `inttoptr i64 18759808`、ld116 `inttoptr i64 22954112`)。survey の ok が 871 (ld116) と 872 (本番) で違うのはこれに由来すると見られるが、切り分けていない。ld116 の数値は ld116 の中の比較にだけ使う。

## 6. 検証 (WORKFLOW §6)

- 測定 commit: `e7f0baa2`。`git diff e7f0baa2 HEAD -- tools/m11 ':(exclude)*.md'` の出力 (コード・スクリプトの差分) は 0 行 (本文執筆時点の HEAD で確認)。以後の commit は REPORT と PR 本文のみ。
- 旧版の「0 行」の記述は main 取り込み前 (`8d9d5786`) のものだった。`9aa9270a` では `4ec81912` から `tools/m11` のコードが 7870 行変わっていた (差し戻し指摘 1)。その下で `ld115_e2e.sh`・`ld108_e2e.sh` の再測定を行い、`ld116_e2e.sh` を新たに通した。3 本とも `e7f0baa2` で rc 0。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/ldfix/ld115_e2e.sh` (前提: `tools/m11/work` に work-m11、`[EMSDK]` (`docs/REFERENCES.md`)、`capstone`・`pefile`。`fl-win64` は `$ARTIFACTS_DIR/fl-win64.tar.zst` を展開)。`ld108_e2e.sh`・`ld116_e2e.sh` も同じ。
- 所要 (`time` の real): ld115 184.9 秒、ld108 183.6 秒、ld116 149.3 秒。load average (1 分) は ld115 開始時 0.60、ld108 開始時 0.83 (4 コア)。
- 出力: `LD115_E2E_SUMMARY fail=0`、`LD108_E2E_SUMMARY fail=0`、ld116 rc 0 (NC1〜NC4 と IR・指紋・DYN・survey の全 PASS)。
- 20 MiB 超の blob: 本 PR は含めない (ir・wasm は `work/` にのみ置く)。

## 7. 製品 KPI (起動・GUI に関わる変更の扱い)

本 PR は m11 の IR のうち `function_666a60` (ループ回数・ループ内 store) だけを変える。**起動 KPI (FLEngine 起動の dispatch 数・通過 unit 数・最初のウィンドウ) は動かしていない**。起動 e2e (`tools/flelift/boot`) は本 run で実行していない。survey の ok は 872 → 872。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 起動 KPI の前後測定 (`tools/flelift/boot`) | 本修復が起動経路の KPI をどう動かすかは未測定 | 本 PR の未解決表で追跡 (再測定のみのため起票しない) |
| 666a60 が survey で実行されない (REPORT_509 §4.3) | ok 退行 0 は実行されないことによる。修復の波及は survey では測れない | REPORT_2447 §9 から継続 (本 run では再測定しない) |
| 回数 0 の早期脱出 (機械語 `666ae0`〜`666ae4`) が本番 IR に無い。`fix_ld116.py` は ld116_e2e の検証用で本番未配線 | 本番 IR では arg2=0 で wasm が trap する | 子 #2513 (LD-116) |
| ld116 の post115 と本番 post の 4 行差 (`function_980ed0` の定数) | survey ok 871 と 872 の差の原因は未切り分け | 本 PR の未解決表で追跡 (調査のみのため起票しない) |
| 欠陥の根本原因 (RetDec のどの段か) | 修復は後追いの単独パッチのまま | REPORT_2447 §9 から継続 (原因調査のみのため起票しない) |
| main 取り込み (`origin/main` は本測定の HEAD の 153 commit 先) | 本測定は取り込み前の HEAD。main 側の `tools/m11` の変更 (`guard699`・REPORT_2211 ほか) が IR に効くかは未測定 | 取り込み後の PR で測り直す (本 run では取り込まない) |
