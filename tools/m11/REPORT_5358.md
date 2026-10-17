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

- `0xa44eb0` は wasm 線形メモリ上で **機械語** として読める: `40 88 ff 48 8d 43 74 41 8b 8d 20 05 00 00 01 08` (`m11_image.bin` の先頭 16 バイト)。`[src-4] = 0xade88080`・`[src-8] = 0x8080b941` で、文字列の長さ・refcnt ヘッダではない。`src` を文字列ポインタとして扱うと、呼出し元の値は文字列ではなく **コード領域のアドレス**。
- `function_653660` の 216816 行: `function_414c70(&s16, *s24, s16)`。`*s24` は `653660` の `arg4` (`413480(s24, arg4)` の格納値) を 1 段 deref した値。この **`*s24` が `arg2` (414c70) に渡る**。
- `653660` の `arg4` は呼出し元 `6539e0` の `arg3`。`6539e0` の呼出し元 `653f40` (IR 217183 行以降の 18 行目) では `6539e0(global 0x2572dc, %8, i64 0)` で、`6539e0` の `arg3` は `0`。
- 既存の逆アセンブル (`function_6539e0` / `function_653660` の先頭) は、`653660` が `arg2` (rdx) と `arg4` (r9) を受けることと一致する (IR の署名と整合)。
- `src = 0xa44eb0` が `414c70` のどちらの引数から来たかは、この時点では未確定 (`arg2` は 118380 行の経路、`arg3` は 118370 行の経路)。
- `M11_FIX_652500=1` (既存の検証ゲート、`*arg1` の 1 段 deref 復元) でも測定値は不変 (units_run 129 / last_unit 144 / OOB)。この deref 欠落は OOB の原因ではないと判定する。

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

- 基準 (7.1) と同一。`652500` の 1 段 deref 欠落は、unit 145 の OOB の経路に効いていない。
