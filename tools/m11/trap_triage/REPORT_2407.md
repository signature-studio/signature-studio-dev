# REPORT_2407 — `e3ef60` 入口の arg1 (this) を観測する probe (#2407, 親 #2373)

既知類型との関係: 該当なし (計測 hook の追加のみ。新規の欠陥類型は無い。DEFECTS 行案も無し)。

## 0. 結論

- `e3ef60` の入口の arg1 (this = rcx) は **非 null** (`0x12ba808`)。`e3ef60` の入口は全 942 units のうち unit 895 の 1 回だけ (§2-2)。その時の `[arg1]` (u64) は `0`。
- したがって `60a270` の this=0 (REPORT_882_APPENDIX §14.3) は、`e3ef60` の arg1 が null だから起きるのではない。推定: 9 箇所のうち this を `[arg1+off]` から取る箇所の field が 0 (静的な call 構造は `REPORT_2373` §3)。どの箇所かは #2400 で扱う。
- 既定 build (probe OFF) は変更前の `origin/main` (`93307cc6a`) と同一。wasm md5・post IR・per-unit の kind と err (942 件) が一致する (§2-1)。probe ON でも集計は変わらない。

## 1. 変更 (commit `c941830b`)

| ファイル | 変更 |
|---|---|
| `tools/m11/m11_ov.c` | `M11_INSTR_E3EF60=1` のときだけ `m11_e3ef60_obs(arg1)` を定義。`arg1` と `[arg1]` (u64) を `[m11][e3ef60] #n arg1=… [arg1]=…` で stderr に出す (上限 64 行。線形メモリ外は読まない)。 |
| `tools/m11/m11_post.py` | `M11_INSTR_E3EF60=1` のとき PROBES に `0xe3ef60` を末尾追加 (既存 index 不変)。wrapper 先頭で `m11_e3ef60_obs(%p0)` を呼ぶ。declare は ON のときだけ出す。 |
| `tools/m11/m11_build.sh` | CF に `-DM11_INSTR_E3EF60` (既定 0)。ON/OFF の切替で `boot_final3.ll` と `obj/ov.o` を作り直す stamp (`work/instr_e3ef60.stamp`)。 |

形は `M11_INSTR_60A270` (#882) と `M11_INSTR_412770` (#3325) と同じ。既定 0 では post 出力も ov.o も変わらない。`IR 上の function_e3ef60` は `(i64 %arg1, i64 %arg2, i64 %arg3)` なので `i64 %p0` をそのまま渡す。

`c941830b` の後に `origin/main` (`93307cc6a`) を取り込んだ (merge `c58ccc387`)。main 側で `fix_ld115` が既定 ON になり (#2447・#2527)、IR と build の経路が変わったため、測定は取り込み後の HEAD で取り直した。

## 2. 測定

- 測定 commit: `c58ccc387` (コードの差分を含む最後の commit。`c941830b` の後に main を取り込んだ merge)。
- `git diff c58ccc387 HEAD -- tools/m11/m11_build.sh tools/m11/m11_ov.c tools/m11/m11_post.py` の出力: 空 (差分 0)。
- 素材: `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`FL_WIN64_DIR`)。`work-m11` / `work-liftdiff` を worktree 直下に展開。`toolchain-emsdk` は `[EMSDK]` (agent-setup の展開先)。
- 比較対象は `origin/main` (`93307cc6a`) を detached worktree (`$RUNNER_TEMP/2407-base2`) に展開し、同じ手順で測った。
- load average (1 分): 0.8〜0.9 (測定前後の `uptime`)。各 build・survey は 1 回ずつ (n=1)。

| build | gen_ir2 | build | survey (`SV_RAW=1`) の集計 | `e3ef60` の stderr 行 |
|---|---|---|---|---|
| 変更前 `93307cc6a` (既定) | rc=0 / 41 s | rc=0 / 21 s | `ok 873 / halt0 7 / miss 47 / oob 14 / noproc 1` (計 942) | 未採取 |
| 変更後 `c58ccc387` (既定 = OFF) | rc=0 / 41 s | rc=0 / 21 s | 同上 | 0 行 |
| 変更後 `c58ccc387` (`M11_INSTR_E3EF60=1`) | rc=0 / 41 s | rc=0 / 20 s | 同上 | 1 行 (unit 895) |

- 集計は `survey_units.mjs` の `SURVEY_UNITS` 行の値 (survey 所要はいずれも 10 s)。stderr は `SV_ERR_LOG` で全行を unit 番号付きで採り、`e3ef60]` を数えた。
- 旧 REPORT (`REPORT_882_APPENDIX` §14.3・`REPORT_2373`) の既定 build の集計 `ok 870 / halt0 7 / miss 47 / oob 16 / other 1 / noproc 1` は、現 main の変更前でも再現しない (§5 の未解決)。

### 2-1. 既定 build の同一性 (変更前 `93307cc6a` との比較)

| 比較 | 結果 |
|---|---|
| `work/m11_boot.cjs.wasm` の md5 | 一致 (`f62a58dfd8043c351c8f9a12f495ce80`) |
| `work/boot_final3.ll` (post 出力) の `cmp` | 一致 |
| survey JSON の unit ごとの kind と err (942 件) | 一致 |
| survey JSON 全体 | 差は stack trace の `survey_units.mjs` のパス (worktree の場所) だけ。`sed` で正規化して差 0 |

### 2-2. probe の観測 (ON)

- unit 895 の stderr: `[m11][e3ef60] #1 arg1=0x12ba808 [arg1]=0x0`。
- 同じ unit の frame (ON): `function_60a270` ← `function_e3ef60__lifted` (wrapper 経由)。wrapper で frame 名が 1 段増えるのは ON だけ。集計には出ない。
- ネガコン: OFF の stderr に `e3ef60` 行は 0 件、ON は 1 件。OFF の `boot_final3.ll` に `m11_e3ef60_obs` は 0 件 (ON は宣言 1 + 呼出し 1)。
- ON で unit 895 の kind は `halt0` のまま。OFF と ON の per-unit kind は全 942 件で一致。

## 3. 受入条件

1. `e3ef60` の入口で this (rcx) を観測する probe を、`M11_INSTR_60A270` と同じ形 (計測専用・既定 0) で追加: **達成** (§1)。
2. 観測結果を REPORT に書く: **達成** (§0・§2-2)。
3. 既定 build の survey が変わらないこと: **達成** (変更前 `93307cc6a` と wasm・post IR・per-unit kind が一致。§2-1)。issue 本文の `870 / 16` は現 main で再現しない (変更前でも 873 / 14)。値の更新は下の未解決に書く。

## 4. 再現

```sh
cd tools/m11
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP   # fl-win64 の展開先
bash m11_gen_ir2.sh                                              # rc=0 (41 s)
M11_INSTR_E3EF60=1 bash m11_build.sh                             # ON (20 s)
M11_INSTR_E3EF60=1 SV_RAW=1 SV_ERR_LOG=$RUNNER_TEMP/err_on.log node trap_triage/survey_units.mjs $RUNNER_TEMP/on.json
grep 'e3ef60\]' $RUNNER_TEMP/err_on.log                          # unit 895 の 1 行
bash m11_build.sh                                                # OFF (既定に戻す, 21 s)
SV_RAW=1 SV_ERR_LOG=$RUNNER_TEMP/err_off.log node trap_triage/survey_units.mjs $RUNNER_TEMP/off.json
```

- 検証範囲: `m11_gen_ir2.sh` → `m11_build.sh` → `survey_units.mjs` (942 units)。`m11_e2e.sh` 全体は実行していない。
- 範囲外: `e3ef60` の 9 箇所それぞれの field 値 (#2400)、arg1 の上位 caller (#882)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `e3ef60` の 9 箇所のうち this=0 を渡す箇所と、その field (`[arg1+off]`) の値 | `60a270` の this=0 の出所 (arg1 は非 null と確認済み) | #2400 (親 #2373) |
| arg1 (`0x12ba808`) を渡す上位 caller (`12d0f80` 以降) の出所 | arg1 の由来 | #882 |
| 既定 build の survey 基準値。`REPORT_882_APPENDIX` §14.3 と `REPORT_2373` の `870 / 16` は現 main で再現しない (変更前で 873 / 14) | 旧値を基準にした判定の誤読 | #2373 (親。旧値の注記は親の REPORT で扱う) |
