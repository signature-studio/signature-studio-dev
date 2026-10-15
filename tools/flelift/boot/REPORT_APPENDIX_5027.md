# tools/flelift/boot — FLE-40 (#5027): FLE_BOOT_LOG_CAP 超過の例外が exit に置き換わる経路の特定と log_cap 報告

> 測定値の正本。親 #5013 (FLE-39)。REPORT.md §0 から参照。

既知類型との関係: 該当なし (計測側の例外の伝播。lift の類型は判定していない)。

## 1. 結論

- cap の例外は**guest 内では捕まっていない**。`fle_boot.mjs` の `console.log`/`console.error` ラッパが投げた `FLE_BOOT_LOG_CAP exceeded` は、Emscripten の tty 書込み経路で捕まって errno (EIO) に変換される。guest には `fd_write` の失敗として返り、guest は止まらず走り続ける。
- その後の停止理由は cap の例外ではなく `ExitProcess` (`exit`, code 0)。cap 超過後も boot は `exit` まで走る。
- 修正: cap 超過 (`logCap.hit`) の後は、boot の分類を `log_cap` にし、生の停止理由を `boot.threw_raw` に残す (`fle_boot.mjs`)。既定経路 (cap 無効) の挙動は変えない。
- 実測: 修正後の既定経路 (`run_boot default`・`FLE_BOOT_LOG_CAP=4096`) で `boot.threw.cls = log_cap`・`boot.threw_raw.cls = exit`。cap なしは `exit` のまま。units は両方 895 で同一。

## 2. 経路の特定 (cap の例外が exit に変わる箇所)

生成物 `fleboot_plain.cjs` (Emscripten 出力) で確認した。ただし行番号 (L1113-1122・L4476-4486) は、前の測定 run の生成物を見たときの記録で、検収 run には生成物が無く照合していない (再生成には lift から link までの全工程が要る)。照合は後続で行う。

| 段 | 場所 | 働き |
|---|---|---|
| 1 | `fle_boot.mjs` L48-50 | `console.log`/`error` ラッパが `logCap.bytes > LOG_CAP` で `throw new Error('FLE_BOOT_LOG_CAP exceeded ...')` |
| 2 | `fle_boot.c` `fprintf(stderr, ...)` | guest 側の出力。Emscripten の stderr が `console.error` 経由で 1 に届く |
| 3 | `fleboot_plain.cjs` L1113-1122 (`FS` の tty `write`) | `try { put_char(...) } catch (e) { throw new FS.ErrnoError(29) }` (EIO)。cap の例外はここで飲まれる |
| 4 | `fleboot_plain.cjs` L4476-4486 (`_fd_write`) | `catch (e) { if (e.name === 'ErrnoError') return e.errno; }`。guest には `fd_write` の失敗として返る |

段 3 が cap の例外を `exit` に変える箇所の要点: cap の例外は boot の JS 例外として上がらない。guest は `fprintf` の失敗を無視して続行し、後続の `ExitProcess` (`imp_ExitProcess`・`fle_boot.c` L352-357) が `exit` の例外を投げて boot を止める。

## 3. 測定

- 測定 commit (修正を含む・コードを変えた最後の commit): `4ce0d2a59` (`fix(flelift): FLE_BOOT_LOG_CAP 超過を boot.threw の log_cap として報告する (#5027)`)。ベース `origin/main` = `695ef5514`。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`toolchain-emsdk` → `$RUNNER_TEMP/toolchain-emsdk` (`SS_EMSDK_ENV` で指定)。
- 同一 work (`$RUNNER_TEMP/fle5027/w`) で lift・clang を共有し、boot だけを 3 回走らせた。

### 3-1. 修正前: `FLE_BOOT_LOG_CAP=4096` で `run_boot default` (run1)

`$RUNNER_TEMP/fle5027_run1.log` の `FLEBOOT_RESULT`: `boot_threw: "exit"`・`log_cap: {hit: "bytes", bytes: 932930, lines: 14429}`・`units_run: 895`・`getmem: 3680`・`freemem: 1499`・IPP check ok。cap の例外は boot に届かず `exit` のまま。

### 3-2. 修正後: 同じ指定 (`FLE_BOOT_TAG=fle5027head`・commit `4ce0d2a59`)

結果 JSON: `results/boot_summary_fle5027head_default.json`。
`FLEBOOT_RESULT`: `boot_threw: "log_cap FLE_BOOT_LOG_CAP exceeded (4096 bytes); raw=exit"`・`boot_threw_raw: "exit"`・`log_cap: {hit: "bytes", bytes: 932930, lines: 14429, elapsed_ms: 583}`・`units_run: 895`・`getmem: 3680`・`freemem: 1499`・`FLEBOOT_IPP_CHECK ok (ptr 0x7f10001c)`。

### 3-3. 止まらなかった場合 (cap 無効・`FLE_BOOT_LOG_CAP=0`)

結果 JSON: `results/boot_summary_fle5027nocap_default.json`。
`FLEBOOT_RESULT`: `boot_threw: "exit"`・`boot_threw_raw: null`・`log_cap: null`・`units_run: 895`・`getmem: 3680`・`freemem: 1499`・IPP check ok。

### 3-4. 差分

| 項目 | cap 4096 (3-2) | cap 0 (3-3) |
|---|---|---|
| `boot.threw` (分類) | `log_cap` | `exit` |
| `boot.threw_raw` | `exit` | (なし) |
| `log_cap.hit` | `bytes` | null |
| `units_run` | 895 | 895 |
| `getmem` / `freemem` | 3680 / 1499 | 3680 / 1499 |

2 つの結果 JSON を全フィールド比較した差は、次の 2 群だけ。

- 分類・計数: `boot.threw` (`log_cap` / `exit`)・`boot.threw.msg`・`boot.threw_raw`・`log_cap` (cap 無効では null)。
- 出力メモリのハッシュ: `outmem.full` (`d925e598…` → `b2cbbde9…`)・`outmem.no_cstack` (`3d1da791…` → `0b22ce22…`)。`mem_bytes`・stack の base/end は同一。

cap の有無で同じなのは、units・GetMem/FreeMem・IPP・生の停止理由 (`exit`, code 0)。

出力メモリのハッシュの差が cap の影響か、同一 binary の再実行での非決定性かは、本 PR の測定では**未確認**。cap 0 の同一条件での 2 回実行はしていない。`REPORT_APPENDIX_672` §E-2 でも決定性は未検証と書かれている。したがって本付録では「cap の有無で boot の結果が同じ」とは書かず、停止理由・units・GetMem/FreeMem・IPP が同じことだけを主張する。決定性の確認は後続の子 issue の範囲外とし、必要になった時点で同一 binary の 2 回実行で扱う。

### 3-5. 規則の確認 (`log_cap_check.py`)

`python3 tools/flelift/boot/log_cap_check.py results/boot_summary_fle5027head_default.json results/boot_summary_fle5027nocap_default.json` → PASS。
分類の置換を外した結果 JSON (`boot.threw` を `exit` のまま) を入れると FAIL (`boot.threw.cls が log_cap でない: 'exit'`・`生の停止理由が exit でない: None`)。規則を壊すと落ちることを確認した。

## 4. 未解決・範囲外

- cap 超過後も guest が走り続ける理由 (`fprintf` の失敗を guest が無視すること) と、cap で boot を止める修正は本 issue の受入から外し、子 #5058 (FLE-41) に移した。cap の目的は出力の有界化であり、boot の停止は別件。
- `exit` が正常終了かの判定は子 issue #4970 [FLE-36] の範囲で、本 issue では扱わない。
