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
- 実行: `bash tools/m11/m11_gen_ir2.sh` → `bash tools/m11/m11_build.sh` → `tools/gui/flengine/build.sh` → `node tools/gui/flengine/boot_halt_probe.mjs` (`M11_M2V` は 0 / 1)。emsdk は `source /opt/emsdk/emsdk_env.sh`。

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
