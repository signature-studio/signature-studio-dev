# M11 REPORT 付録 — #5358 (FLE-44): function_409c80 の tail jump 誤 lift の修正 (部分達成)

親 issue: #5358 (親 #4011)。REPORT.md からの索引は §21 (本文は結論 1 行)。

## 1. 結論

- `function_409c80` の `0x409d2d jae 0x409c40` は call + fall-through ではなく tail jump。`ldfix/fix_tail409c80.py` で引数付き tail call (`call @function_409c40(%arg1,%arg2,%arg3)` + `ret`) に置換する。
- 既定 OFF の boot 測定値は修正前と同一 (下表)。`M11_M2V=1` では trap が `function_409c80` 内に残る。OOB の直接原因は未特定。受入 1〜3 は未達 (#5358 で継続)。

## 2. 機械語の根拠

- 入力 PE: `block00031_PE.bin` (`docs/REFERENCES.md` `[WIN64]`)。
- `0x409d2d`: `cmp rax,[rip+...]; jae 0x409c40`。`0x409c40` は `ret` のみで、その戻り値がそのまま `function_409c80` の戻り値になる (tail jump)。
- `0x409d2d` までに rcx / rdx / r8 / rax は書き換わらない (409c80 → 409d03 → 409d2d)。よって引数は `(%arg1, %arg2, %arg3)` に等しい。
- 修正前の IR は `%101 = call i64 @function_409c40()` の後に fall-through していた。`m11_post` の sigfix がこの引数不足を `(0,0,0)` で埋めていた。

## 3. 修正

| 対象 | 内容 |
|---|---|
| `tools/m11/ldfix/fix_tail409c80.py` (新規) | `function_409c80` の tail jump を置換。仮引数の署名・置換行数を assert で確認し、想定と違えば停止 (fail-closed) |
| `tools/m11/m11_gen_ir2.sh` | `fix_src412770` の直後に適用 (3 行) |

## 4. 測定 (修正 commit 以降の測定値の移送)

- 測定 commit: `dc0eba1f9` (本 PR の HEAD 時点のコード。以降のコード差分は無し)。
- 素材: fl-win64 (`block00031_PE.bin`)・work-m11・toolchain-emsdk を展開。`apt-mingw` は使用せず (未実在)。`toolchain-retdec` は未使用。
- 実行: `bash tools/m11/m11_gen_ir2.sh` → `bash tools/m11/m11_build.sh` → `tools/gui/flengine/build.sh` → `node tools/gui/flengine/boot_halt_probe.mjs` (`M11_M2V` は 0 / 1)。emsdk は toolchain-emsdk の `emsdk_env.sh` を source する (`docs/REFERENCES.md` `[EMSDK]`)。

| 構成 | 所要 | units_run | init | icall_miss | last_unit | threw |
|---|---|---|---|---|---|---|
| 既定 OFF | gen 34 秒 / build 19 秒 / gui 16 秒 | 109 | 111 | 7 | 114 `0x623840` (Halt0) | null |
| `M11_M2V=1` | gen+build+gui 合計 66 秒 | 129 | 132 | 16 | 144 `0x65c540` | memory access out of bounds |

- probe 所要: 既定 OFF 0.3 秒 / M2V 同左。load は未採取。
- 既定 OFF と修正前の比較: units_run / last_unit は同一 (修正の既定 OFF への影響 0)。
- 最初のウィンドウ: 未到達 (両構成)。

### 4.1 再測定の状況 (この記録の時点)

- 上表は前 run の実測を移送したもの。移送時 (fix run) には素材 (work-m11・toolchain-retdec・toolchain-emsdk) が展開されておらず、再測定はしていない。
- 測定ログ (run ID) は本リポジトリに残っていない。本表の値は PR 本文の記載に基づく。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| trap 時点のアドレス値 (`function_409c80` 内の `i64.load` の実アドレス) の採取と IR 突合 | 受入 1・3 が未達 | #5358 (継続) |
| `M11_M2V=1` の unit 145 OOB の直接原因 | last_unit 144 で停止 | #5358 (継続) |
| 修正後の trap の wasm offset | 未確認 (前 run の記録は未取得。`0xbf736` 等の値は本リポジトリに根拠が無いため記載しない) | #5358 (継続) |
| `#5092` (lift OFF 版の trap 連鎖) との関係 | 同一根因かは未確定。連鎖の共通部分 (`414c70` / `653660` / `6539e0` / `653f40` / `65c540`) あり | #5358・#5092 |

## 6. 製品 KPI (起動指標)

修正前 = #5358 の段 3 表 (測定 HEAD `21dae5a06`)、修正後 = 上表 (測定 commit `dc0eba1f9`)。

| 構成 | 修正前 units_run / last_unit | 修正後 units_run / last_unit |
|---|---|---|
| 既定 OFF | 109 / 114 (Halt0) | 109 / 114 (Halt0) |
| `M11_M2V=1` | 129 / 144 (OOB) | 129 / 144 (OOB) |

- 修正前後で差は 0。修正は KPI を動かしていない。
- 最初のウィンドウ: 未到達 (両構成・修正前後とも)。

## 7. 呼出し鎖と 0xa44eb0 の出所 (計装による・#5358 の PM 再投入の範囲)

測定 commit: `4fb932176` (origin/main。以降のコード差分は本 PR に無し)。派生計装は `m11_ov.c` に入れて測定後に元へ戻し、`git diff -- tools/m11/m11_ov.c` は 0 行 (commit しない)。
素材: fl-win64 (`block00031_PE.bin`)・work-m11・toolchain-emsdk。`m11_gen_ir2.sh` → `m11_build.sh` → `gui/flengine/build.sh` を `M11_M2V=1` で実行。

### 7.1 計装なしの基準 (再現)

| 構成 | units_run | init | icall_miss | last_unit | threw |
|---|---|---|---|---|---|
| `M11_M2V=1` | 129 | 132 | 16 | 144 `0x65c540` | memory access out of bounds |

- 製品 KPI: units_run 109 → 129 (既定 OFF からの変化は前 run と同じ)・last_unit 144・最初のウィンドウ 未到達。

### 7.2 観測 (計装版・1 回)

`function_4133f0` (UStrAsg) の入口で `src == 0xa44eb0` を検出し、初回の `new Error().stack` を保存した (派生)。
観測は 1 回 (`cnt=1`)。同じ run で `memory access out of bounds` も出た (trap の位置との前後関係は未確認)。

| wasm index | IR 関数 | 役割 |
|---|---|---|
| 14918 | `function_4133f0` | `System._UStrAsg`。観測点 (src = `0xa44eb0`) |
| 200 | `function_414c70` | 直接の呼出し元。IR 118362 行以降: `arg2 == 0` なら `4133f0(arg1,arg3)` (118370 行)。`arg2 != 0` かつ `arg3 == 0` なら `4133f0(arg1,arg2)` (118380 行)。両方非 0 の経路は文字列の連結 (`412c20`/`409c80`) |
| 3933 | `function_653660` | 上位 |
| 3934 | `function_6539e0` | 上位 |
| 3943 | `function_653f40` | 上位 |
| 3945 | `function_65c540` | unit 145 (VA 0x25c540 の unit) |

index と名前の対応は `m11_wasmnames.py` (今回の build の wasm) で確認した。

### 7.3 静的に確定した事実

- 訂正 (未確認): 以前の記録は「`0xa44eb0` が機械語に見える」と書いたが、引用したバイト列 `40 88 ff 48 8d 43 74 41 8b 8d 20 05 00 00 01 08` は `m11_image.bin` の**ファイル先頭 16 バイト**であり、`0xa44eb0` の位置ではない。VA → ファイル offset の対応は本記録に無い。したがって「`0xa44eb0` はコード領域」「文字列ヘッダではない」は**未確認**とし、§8.4 の未解決に移す。
- `function_653660` の 216802 行 (IR 行番号は §8 と統一。IR ファイルは本 run で再確認していない): `function_414c70(&s16, *s24, s16)`。`*s24` は `413480(s24, arg4, …)` で格納された `arg4` を 1 段 deref した値で、これが `414c70` の `arg2` になる想定 (`%27 = load(s24)`、`%29` はその変換値)。
- `653660` の `arg4` は呼出し元 `6539e0` の `arg3`。`6539e0` の呼出し元 `653f40` (IR 217195 行付近) では `6539e0(arg1 = global 0x2572dc, arg2 = (arg2 & ~0xff) | 1, arg3 = 0)`。`0x2572dc` は UTF-16 の定数文字列 (長さ 13・refcnt -1・"dsp_ipp v2.")。よって `arg3 = 0` (`arg4 = 0`)。
- 既存の逆アセンブル (`function_6539e0` / `function_653660` の先頭) は、`653660` が `arg2` (rdx) と `arg4` (r9) を受けることと一致する (IR の署名と整合)。
- `src = 0xa44eb0` が `414c70` のどちらの引数から来たかは、この時点では未確定 (`arg2` は 118380 行の経路、`arg3` は 118370 行の経路)。
- `M11_FIX_652500=1` (既存の検証ゲート、`*arg1` の 1 段 deref 復元) の測定値は基準と同一 (units_run 129 / last_unit 144 / OOB)。この gate が OOB の経路に効くかは未判定 (§7.4)。

### 7.4 判定 (受入 3)

- **判定: 確定不能。** 理由は次の 2 点。
  1. 観測の時点の `414c70` の引数 (`arg2` / `arg3`) の実値を採っていない。`src` が `arg2` 由来か `arg3` 由来かは、この値が無いと区別できない。計装は呼出し鎖の採取までで、引数の採取は行わなかった。
  2. `*s24` (= `arg2`) がどの store で書かれたかは、`413480` (文字列代入) の上流を辿る必要がある。今回は IR 上で `413480(s24, arg4, …)` までの確認に留まった。
- 「deref 欠落型かどうか」は、上の 1 と 2 が閉じるまで **判定しない**。`[src-4]` が文字列ヘッダでないことは確定しているが、それ単独では「1 段 deref が落ちた」とは言えない (別の値が文字列として流れた場合も同じ観測になる)。

### 7.5 次の入口

1. `414c70` 入口の `arg2`・`arg3` の実値を採る (派生計装・commit しない)。
2. `653660` の `arg4` (= 6539e0 の `arg3`) の上流 (653f40 の 18 行の呼出し元の定数 `0x2572dc` と `0`) を確認し、`*s24` の書込みを IR で辿る。
3. 上の結果で deref 欠落型かを判定し、この節を更新する (受入 3)。

### 7.6 検証ゲート (`M11_FIX_652500=1`)

| 構成 | units_run | init | icall_miss | last_unit | threw |
|---|---|---|---|---|---|
| `M11_M2V=1` + `M11_FIX_652500=1` | 129 | 132 | 16 | 144 `0x65c540` | memory access out of bounds |

- 基準 (7.1) と同一 (前 run の記録)。ただし同じ構成の再測定は §9.4 で units_run 134 と不一致 (原因未確定・REPORT_APPENDIX_5358.md §9.4)。units_run は 129 (前 run の記録) / 134 (§9.4)。効果は未判定 (§7.4・§8.4)。

## 8. arg 実値と s24 の書換え位置 (付録へ移動)

§8 の本文 (派生計装・測定 commit `410956bd5`・PM 03:2x Z の範囲) は `REPORT_APPENDIX_5358.md` §8 に移した (#5358 の REPORT 行数上限。削除していない)。

## 10. 既定 build で 414c70 入口の arg 実値を採取する計装経路 (#5358 PM 07:18Z の範囲)

測定 commit: `448d36738` (origin/main) + 本 PR の 4 ファイル (§10.1。HEAD 時点のコード = `bd8019b3f` のコード)。`448d36738`..HEAD のコード差分は 4 ファイルのみ (docs 以外)。境界: `97a5bd8ab` → `448d36738` の差分 (ldfix・trap_triage 等) は main 取り込み分で、boot 経路の IR・build には影響しないことを確認済み (`m11_gen_ir2.sh`・`ldfix.py`・`fix_450560.py`・`m11_build.sh`・`m11_cond.py`・`m11_run.mjs` から呼ばれない)。素材: fl-win64 (`block00031_PE.bin` を `$RUNNER_TEMP/fl/extracted/` に展開)・work-m11 (`tools/m11/work/` に展開)・toolchain-emsdk。IR は `M11_M2V=1 m11_gen_ir2.sh` で作り直した (`ir_conditions.json`: ldfix/ld108/ld115/r8b/450560 = applied・`ir_sha256` `8840c541…`)。

### 10.1 経路 (計装の作り方)

- 既存の `M11_INSTR_412770` / `M11_INSTR_E3EF60` と同じ方式。IR 本体は書き換えず、`m11_post.py` が env ゲートの probe wrapper を `function_414c70` に被せる (`M11_INSTR_414C70=1` のときだけ。既定 0 では何も入らない)。
- 観測関数 `m11_414c70_obs(arg1, arg2, arg3)` を `m11_ov.c` に置く (既定 0 で `#if` の外)。出力は `[m11][414c70] #n arg1=… arg2=… arg3=… [arg2-4]=… [arg2]=…` (上限 64 行。線形メモリ外は読まない)。
- `m11_build.sh` に stamp (`work/instr_414c70.stamp`) と `-DM11_INSTR_414C70` を足した。`tools/gui/flengine/build.sh` の `CF` も同じ `-D` を渡す (前 run の時点では、この `CF` が M11_INSTR_* を渡さず、計装版の `ov.o` が undefined symbol になっていた)。
- 変更ファイル: `tools/m11/m11_post.py` / `tools/m11/m11_ov.c` / `tools/m11/m11_build.sh` / `tools/gui/flengine/build.sh`。
- 注意: `tools/gui/flengine/build.sh` の `cc()` は `-nt` 判定のみで、`M11_INSTR_414C70` を切り替えても `GF_W/obj/ov.o`・`boot.o` は再 build されない。切替時は `GF_W/obj/ov.o` を手で消してから build する (消さないと link が undefined symbol で止まる)。

### 10.2 既定の不変性 (ゲート OFF)

- `M11_INSTR_414C70` 未設定の `boot_final3.ll` の sha256: 計装追加の前後で `ad30a949…` で一致 (差分 0)。
- 既定 build の `boot_halt_probe.mjs`: units_run 129 / init 132 / icall_miss 16 / threw `memory access out of bounds` / last_unit 144 (`0x65c540`)。前 run の既定値と一致。

### 10.3 計装版 (`M11_INSTR_414C70=1`) の採取

`m11_run.mjs` (計装版 `m11_boot.cjs`) を 3 回回した。stderr の観測行:

| run | 呼出し # | arg1 | arg2 | arg3 | [arg2-4] | [arg2] |
|---|---|---|---|---|---|---|
| 1 | #1 | `0x10aa1098` | `0x6c` | `0x2539c8` | 0 | `0x0` |
| 1 | #2 | `0x10aa10b8` | `0xa44eb0` | `0x0` | 2917695616 | `0x4174438d48ff8840` |
| 2 | #1・#2 | 同上 | 同上 | 同上 | 同上 | 同上 |
| 3 | #1・#2 | 同上 | 同上 | 同上 | 同上 | 同上 |

- 呼出し #2 の `arg2 = 0xa44eb0` は、前 run の観測 (`src = 0xa44eb0`) と一致。`arg3 == 0` なので、REPORT_APPENDIX_5358.md §9.3 の経路 (`arg3 == 0` かつ `arg2 != 0` → `4133f0(arg1, arg2)`) に入る。よって `src` は `arg2` = `*s24` 由来が実値でも確認された。
- `arg2 = 0xa44ed0` は今回の 3 回では出ていない。`arg2` の run 間変動は再現しなかった (REPORT_APPENDIX_5358.md §9.6 の未確定 2 は未確定のまま)。
- 計装版の結果: units_run 129 / init 132 / icall_miss 16 / threw `memory access out of bounds` (既定と同一。計装は挙動を変えない)。
- 所要 (PR 本文の記載に基づく・本 run では再測定していない・§4.1 と同じ扱い): `m11_build.sh` 18 秒・`tools/gui/flengine/build.sh` 16 秒・`boot_halt_probe.mjs` 0.5 秒。load は未採取。

### 10.4 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `arg2 = 0xa44ed0` の経路 (前 run の `src` 変動の片方) が今回の 3 回で観測されない | 受入 3 の判定 (deref 欠落が書換えに効くか) | #5358 (次 run) |
| `m11_run.mjs` の経路と `boot_halt_probe.mjs` (flengine) の経路で 414c70 観測の値が一致するか | 観測経路の差 | #5358 (次 run) |
| 計装版の `[arg2-4]` (長さ) は 2917695616 で、文字列ポインタとして読めない (命令列の先頭) | `arg2` が文字列ポインタか否か | #5358 (次 run) |
