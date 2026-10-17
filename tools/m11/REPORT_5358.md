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

- 基準 (7.1) と同一。効果の有無は未判定 (§7.4・§8.4)。

## 8. arg 実値と s24 の書換え位置 (PM 03:2x Z の範囲・派生計装・測定 commit `410956bd5`)

測定 commit: `410956bd5` (`origin/5358-m11-callchain` = `09bcb13d6` に `origin/main` `360f7ecd2` を取り込んだ merge)。計装は派生で `m11_ov.c` と `work/boot_final.ll` に入れて測定後に戻した。コードを変えた commit は本節の追記のみ。素材: fl-win64・work-m11・toolchain-emsdk ([EMSDK])。`M11_M2V=1` で `m11_gen_ir2.sh` → `m11_build.sh` → `m11_run.mjs`。

### 8.1 計装なしの基準 (再現)

| 構成 | units_run | init | icall_miss | last_unit | threw |
|---|---|---|---|---|---|
| `M11_M2V=1` (IR 再生成) | 129 | 132 | 16 | 144 `0x65c540` | memory access out of bounds |

- 製品 KPI: units_run 109 → 129・last_unit 144・最初のウィンドウ 未到達。`M11_M2V` を付けずに build だけ行うと units_run 109 (前 run と同じ)。
- 所要 (実測): `m11_gen_ir2.sh` 52 秒 / `m11_build.sh` 25 秒 / `m11_run.mjs` 2 秒。

### 8.2 観測 (計装版・派生・1 回ずつ)

| 観測点 | run | 実値 | 意味 |
|---|---|---|---|
| `653660` 入口 | 記録なし (run 不明) | `arg2 = 0x2572dc`, `arg4 = 0` | 定数 "dsp_ipp v2." と 0 (`653f40` の定数どおり) |
| `413480(s24, arg4)` 直後 | 記録なし (run 不明) | `s24 = 0` | 期待どおり |
| `652500(s24)` 直後 | 記録なし (run 不明) | `s24 = 0xa44ed0` | 書き換わったと観測 |
| `414c70` 入口 | A | `arg1 = &s24`, `arg2 = 0xa44eb0`, `arg3 = 0` | run A 内で `s24` の値は記録していない |
| `414c70` 入口 | B | `arg1 = &s24`, `arg2 = 0xa44ed0`, `arg3 = 0` | run B 内で `s24` の値は記録していない。`652500` 直後の `0xa44ed0` と値は一致するが、run の対応は取れていない |

- 同一 run 内で `s24` と `arg2` の一致は**未照合**。上表の観測は run の対応が無く、`arg2 = *s24` は支持も否定もできない。
- `arg3` (= `s16`) は 0。`414c70` は `arg2 != 0` なので `4133f0(arg1, arg2)` の経路 (118380 行) を通ると IR 上で読める (IR は本 run で未再確認)。
- `0xa44eb0` / `0xa44ed0` のコード領域性は未確認 (§7.3 参照)。

### 8.3 s24 の書換え位置 (IR 上)

- `652500` (IR 215852 行) の本体に `s24` (= `arg1` の指す先) への直接 `store` は無い。
- `652500` 内で `arg1` (= `&s24`) を書くのは `414bb0(%1 = arg1, ...)` (IR 39 行)。`414bb0` (IR 118312 行) は `414ad0(arg1, len)` と `409c80(...)` で `*arg1` を更新する。
- 653660 で `413480` の後にある `652500(s24)` が `s24` の中身を 0 から `0xa44ed0` に変えた、と観測から言える。

### 8.4 判定 (受入 3・§7.4 の更新)

- **確定したこと**: `s24` が `413480` の後に 0 で、`652500(s24)` の後に `0xa44ed0` であったという観測 (run 対応は未記録)。`414c70` で `arg2` が `0xa44eb0` / `0xa44ed0` の 2 値観測されたこと (run A/B)。
- **未確定 (確定に入れない)**: `414c70` の `arg2` が `653660` の `*s24` と一致すること (run 対応が無く未照合)。`0xa44eb0` / `0xa44ed0` がコード領域アドレスであること (VA → offset 未確認)。`s24` の書換えが `414bb0` 経由で行われること (IR 追跡未了)。
- **判定**: 「deref 欠落型」かは**未確定**。値が run ごとに変わる理由も未確定。
- `M11_FIX_652500=1` の既存 gate (§7.6) は `652500` の `*arg1` 読みを補正するもので、本節の書換えを直接は扱わない。§7.6 の結果は「基準と同一」のみで、効果の有無は判定しない。

### 8.5 次の入口

1. `652500` → `414bb0(&s24, c)` → `414ad0` の経路で、`s24` の書換え元 (`c` = `s16` の値と `414ad0` の出力) を IR と機械語で突き合わせる。
2. run ごとの `arg2` の変動 (`0xa44eb0` / `0xa44ed0`) の原因を確定する (同一 build で 3 回測る)。
3. 1・2 の結果で §7.4 の判定を確定する。

## 9. 書換え経路の機械語突合・同一 build の再測定・計装 (#5358 PM 05:10Z の範囲)

測定 commit: `97a5bd8ab` (origin/main)。以降のコード差分 0 (計装は派生で測定後に戻し、`git diff -- tools/m11/m11_ov.c tools/m11/work/boot_final.ll` は 0 行)。素材: fl-win64 (`block00031_PE.bin` を `$RUNNER_TEMP/fl-win64/extracted/` に展開)・work-m11 (`tools/m11/work/` を worktree にコピー)・toolchain-emsdk。`M11_M2V=1` で `m11_gen_ir2.sh` (52 秒) → `m11_build.sh` (24 秒) → `m11_run.mjs` (2 秒)。`m11_build.sh` は PE を `M11_PE` / `PE` で指定しないと IR と PE の不一致で止まるため、両方に同じ PE を渡した。

### 9.1 IR 関数名と PE の対応 (機械語で確定)

- IR の `function_NNNN` は PE の **絶対 VA** (ImageBase `0x400000` + RVA)。`414bb0` → RVA `0x14bb0`、`652500` → RVA `0x252500`、`414c70` → RVA `0x14c70`、`413480` → RVA `0x13480` で、逆アセンブルの先頭命令列が IR の本体 (`arg2==0` 判定・`414ad0` 呼出し等) と一致した。
- `m11_image.bin` は RVA を添字とする (`m11_image[0xa44eb0]` と PE の `.text` RVA `0xa44eb0` の 16 バイトが一致)。このため `0xa44eb0` / `0xa44ed0` は**どちらも `.text` 内の RVA** で、文字列ポインタの位置ではない (§7.3 の未確認を、この対応で確認した)。

### 9.2 書換え経路 `652500` → `414bb0` → `414ad0` (受入の主、§8.5-1)

- `652500` (RVA `0x252500`): `if (*arg1 != 0) { p=*arg1; len=[p-4]; 414ec0(&slot,p,len,1); if (414e70(slot, c) != 0) 414bb0(arg1, c); } 412d60(&slot)`。`c` は `rip` 相対の定数 (`0x2525a4` 系)。IR の `[arg1-4]` 読みは `*arg1` の 1 段 deref 欠落 (§m11_ov.c の `M11_FIX_652500` と同じ判定)。
- `414bb0(arg1, rdx=c)` (RVA `0x14bb0`): `c==0` なら終了。`*arg1` が 0 なら `4133f0(arg1, c)`。非 0 なら `414ad0` 相当の長さ調整 (`arg1` の `*s` を `[c-4]` 長に確保し直す) と `409c80` で連結し、`s` を書く。
- `414ad0` (RVA `0x14ad0`): `arg1` は var 引数 (`&s`)。`rbx=rcx` を経由して `[rbx]` を読む (1 段 deref)。確保後 `[rbx] = 新しい文字列` で `s` を書換える。
- **確定**: `s24` (= `*arg1` の `arg1` は `&s24`) を書き換えるのは `414bb0` 経由。`653660` の `652500(s24)` の後に `s24` が変わるのは、`414bb0` の `*arg1` 書換えによる。

### 9.3 `414c70` の `arg2` の出所 (機械語で確定)

- `414c70(arg1=&s16, arg2, arg3)` (RVA `0x14c70`): `arg2==0` → `4133f0(arg1, arg3)`。`arg3==0` (かつ `arg2 != 0`) → `4133f0(arg1, arg2)`。`arg2==arg3` → `414bb0(arg1, arg3)`。両方非 0 別値 → 連結。
- 観測の `414c70` 入口 `arg3 = 0` (§8.2) なので、`src` (`0xa44eb0` / `0xa44ed0`) は **`arg2` = `*s24` 由来**。IR 118345 行の経路と一致 (§8.2 の run 対応は未照合のまま)。

### 9.4 同一 build の再測定 (`M11_M2V=1`、計装なし、§8.5-2)

| 構成 | 回数 | units_run | init | icall_miss | threw |
|---|---|---|---|---|---|
| `M11_M2V=1` (既定 `M11_FIX_652500=0`) | 3 | 129 | 132 | 16 | memory access out of bounds |
| `M11_M2V=1` + `M11_FIX_652500=1` | 6 (計装版 3・計装なし 2・出口計装 1) | **134** | (未記録) | (未記録) | memory access out of bounds |

- 既定 build は 3 回とも同値。`arg2` 変動の観測点が無いので、run 間の `0xa44eb0` / `0xa44ed0` の変動は**未確定** (同一 run の `s24`/`arg2` の対応は取れていない)。
- **§7.6 の記録 (`M11_FIX_652500=1` で units_run 129) と不一致**: 今回は 134 (6 回とも。計装の有無・入口/出口の別によらず同値。計装を外した build でも 134。`m11_ov.c` は原本と byte 一致を確認済み)。build 経路の差 (ldfix・指紋の再記録) か、§7.6 当時の測定条件の差かは**未確定**。§7.6 の「基準と同一」は、今回の経路では再現しない。

### 9.5 計装 (派生・測定後に戻した)

- `m11_ov.c` の `function_652500` (M11_FIX_652500 転記) の入口・出口に `M11_TRACE` で `s24` を出力 (`M11_FIX_652500=1`、入口 3 回・出口 1 回): 入口・出口とも **`s24 = 0x0`**。入口で `*arg1 == 0` のため、転記の `if` 内 (`414ec0`/`414e70`/`414bb0`) は通らない。`414bb0` による書換えはこの経路では起きていない。
- 既定 build (`M11_FIX_652500=0`) の `652500` 出口は計装できなかった。IR 直接編集は `m11_genstubs.py` が `declare` を no-op スタブ化して計装が効かず、`m11_build.sh` の指紋検査 (`ir_conditions.json`) で止まったため。**既定 build で `s24=0xa44ed0` が出るかは未確認**。
- 計装版 IR は `m11_cond.py --bind` で指紋を付け直して build したが、`declare` を外した後の状態が原本と一致することを `cmp` で確認して破棄した。

### 9.6 判定 (§8.4 の更新、§8.5-3)

- **確定**:
  1. `652500` → `414bb0(&s24, c)` → `414ad0` の書換え経路 (機械語・IR の対応)。
  2. `414c70` の `arg2 = *s24` 由来 (`arg3 == 0` 経路の機械語)。
  3. IR 関数名 = ImageBase + RVA、`m11_image.bin` は RVA 添字。`0xa44eb0` / `0xa44ed0` は `.text` 内の RVA (文字列ポインタではない)。
- **未確定**:
  1. 既定 build で `s24` が `0xa44ed0` になる経路 (`414bb0` 内の `c` と `414ad0` の出力)。計装できていない。
  2. `arg2` の run 間変動 (`0xa44eb0` / `0xa44ed0`) の原因。今回の 3 回は全て同値で、変動は再現しなかった。
  3. `M11_FIX_652500=1` の units_run が 129 (§7.6) と 134 (今回) で異なる原因。
- **判定**: 「deref 欠落型かどうか」は**未確定**。§8.4 の判定 (未確定) は変えない。`652500` の `[arg1-4]` 読みは機械語と食い違うことが確定したが (9.2)、それが `s24` の書換えと OOB の因果に効くかは、既定 build の `s24` を採るまで判定しない。

### 9.7 次の入口

1. 既定 build (`M11_FIX_652500=0`) の `652500` 出口に `s24` を出す計装を入れる。`m11_genstubs.py` のスタブ化を避けるため、計装は `m11_ov.c` の強定義で `652500` の lift 版を置き換えるのではなく、`414bb0` 入口 (`m11_ov.c` 側の既存転記があれば) で採る。
2. `M11_FIX_652500=1` の 134 と §7.6 の 129 の差を、ldfix・指紋・work/ の差に分けて切る。

## 10. 既定 build で 414c70 入口の arg 実値を採取する計装経路 (#5358 PM 07:18Z の範囲)

測定 commit: `97a5bd8ab` 系 (origin/main `448d36738` に取り込み)。以降のコード差分は下記 §10.1 の 4 ファイルのみ。素材: fl-win64 (`block00031_PE.bin` を `$RUNNER_TEMP/fl/extracted/` に展開)・work-m11 (`tools/m11/work/` に展開)・toolchain-emsdk。IR は `M11_M2V=1 m11_gen_ir2.sh` で作り直した (`ir_conditions.json`: ldfix/ld108/ld115/r8b/450560 = applied・`ir_sha256` `8840c541…`)。

### 10.1 経路 (計装の作り方)

- 既存の `M11_INSTR_412770` / `M11_INSTR_E3EF60` と同じ方式。IR 本体は書き換えず、`m11_post.py` が env ゲートの probe wrapper を `function_414c70` に被せる (`M11_INSTR_414C70=1` のときだけ。既定 0 では何も入らない)。
- 観測関数 `m11_414c70_obs(arg1, arg2, arg3)` を `m11_ov.c` に置く (既定 0 で `#if` の外)。出力は `[m11][414c70] #n arg1=… arg2=… arg3=… [arg2-4]=… [arg2]=…` (上限 64 行。線形メモリ外は読まない)。
- `m11_build.sh` に stamp (`work/instr_414c70.stamp`) と `-DM11_INSTR_414C70` を足した。`tools/gui/flengine/build.sh` の `CF` も同じ `-D` を渡す (前 run の時点では、この `CF` が M11_INSTR_* を渡さず、計装版の `ov.o` が undefined symbol になっていた)。
- 変更ファイル: `tools/m11/m11_post.py` / `tools/m11/m11_ov.c` / `tools/m11/m11_build.sh` / `tools/gui/flengine/build.sh`。

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

- 呼出し #2 の `arg2 = 0xa44eb0` は、前 run の観測 (`src = 0xa44eb0`) と一致。`arg3 == 0` なので、§9.3 の経路 (`arg3 == 0` かつ `arg2 != 0` → `4133f0(arg1, arg2)`) に入る。よって `src` は `arg2` = `*s24` 由来が実値でも確認された。
- `arg2 = 0xa44ed0` は今回の 3 回では出ていない。`arg2` の run 間変動は再現しなかった (§9.6 の未確定 2 は未確定のまま)。
- 計装版の結果: units_run 129 / init 132 / icall_miss 16 / threw `memory access out of bounds` (既定と同一。計装は挙動を変えない)。

### 10.4 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `arg2 = 0xa44ed0` の経路 (前 run の `src` 変動の片方) が今回の 3 回で観測されない | 受入 3 の判定 (deref 欠落が書換えに効くか) | #5358 (次 run) |
| `m11_run.mjs` の経路と `boot_halt_probe.mjs` (flengine) の経路で 414c70 観測の値が一致するか | 観測経路の差 | #5358 (次 run) |
| 計装版の `[arg2-4]` (長さ) は 2917695616 で、文字列ポインタとして読めない (命令列の先頭) | `arg2` が文字列ポインタか否か | #5358 (次 run) |
