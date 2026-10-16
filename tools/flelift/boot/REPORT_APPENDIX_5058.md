# tools/flelift/boot — FLE-41 (#5058): FLE_BOOT_LOG_CAP 超過で guest を止める (log_cap で boot を停止)

> 測定値の正本。親 #5027 (FLE-40)。REPORT.md §0 から参照。

## 0. log_cap の経緯 (REPORT.md §0 から分割移動・#5897 で移動)

- FLE-37 (#4983): 既定経路の `FLE_BOOT_LOG_CAP` 無効化を修正 (`REPORT_APPENDIX_4983.md`)。
- FLE-40 (#5027): cap 超過の例外は Emscripten の tty write で飲まれ `exit` に残る経路を特定し、超過を `boot.threw` の `log_cap` として報告する (`REPORT_APPENDIX_5027.md`)。
- FLE-41 (#5058): 超過後は次の dispatch で止める (既定 cap 4096 で units 13 で停止・cap 0 は 895 のまま) (本付録)。

既知類型との関係: 該当なし (計測側の例外の伝播。lift の類型は判定していない)。

## 1. 結論

- cap 超過の例外は tty write が飲むため、boot は止まらなかった (#5027)。本件では、**guest の次の dispatch** (`ott_dispatch` の先頭 `fle_dispatch_probe`) で `log_cap` の例外を投げて止める経路を入れた。
- 既定経路 (`run_boot default`・`FLE_BOOT_LOG_CAP=4096`) で `boot.threw.cls = log_cap`・`units_run = 13` (cap 無効は 895)。停止は guest の 14 unit 目以降の dispatch で起きた。
- cap 無効 (`FLE_BOOT_LOG_CAP=0`) の挙動は変わらない (units 895・`exit`・IPP ok)。
- 規則 `log_cap_check.py` は、正常時 PASS、分類を `exit` に戻した変異で FAIL。

## 2. 経路の特定 (照合済み)

#5027 §2 の行番号は前 run の生成物の記録で、照合は未了だった。本 run で生成した `fleboot_plain.cjs` (測定 commit `f6973b811`) で照合した。

| 段 | 場所 (今回の生成物) | 働き |
|---|---|---|
| 1 | `fle_boot.mjs` L48-53 | `console.log`/`error` ラッパが `logCap.bytes > LOG_CAP` で `globalThis.FLE_LOG_CAP_HIT = 1` を立て、`throw` する |
| 2 | `fleboot_plain.cjs` L1112-1122 (`FS` の tty `write`) | `catch (e) { throw new FS.ErrnoError(29) }` (EIO)。段 1 の例外はここで飲まれる |
| 3 | `fle_boot.c` `fle_probe_dispatch` 冒頭 | `if (fle_log_cap_hit()) fle_throw_kind("log_cap", t)`。次の dispatch で JS の例外として上がる |
| 4 | `fle_boot.mjs` の分類 | `classify` が `fle_kind = log_cap` を `cls: log_cap` にする。包み直しは `cls` が `log_cap` でない場合だけ |

`fleboot_plain.cjs` の `_fd_write` の errno 返し (段 4 相当) は、今回の生成物では `e.name === 'ErrnoError'` の判定で確認した (行番号は付録に書かない)。

## 3. 測定

- 測定 commit (コードを変えた最後の commit): `f6973b811` (`fix(flelift): FLE_BOOT_LOG_CAP 超過で guest の次の dispatch から boot を log_cap で止める (Refs #5058)`)。ベース `origin/main` = `11ebc423b`。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`toolchain-emsdk` (emsdk 6.0.12) → `$RUNNER_TEMP/toolchain-emsdk` (`SS_EMSDK_ENV` で指定)。
- 工程: `fle6_measure.sh` を `FLE_BOOT_RUNS=default` で実行 (gen → lift → clang-plain → boot)。

### 3-1. 修正後・cap 4096 (既定経路)

- 実行: `FLE_BOOT_TAG=fle5058cap FLE_BOOT_LOG_CAP=4096 FLE_BOOT_RUNS=default bash tools/flelift/boot/fle6_measure.sh`
- 所要: 20:44:54 → 20:48:07 (3 分 13 秒)。lift 完了 ~80 s・clang-plain 98 s・boot 11 s。load は clang-plain 完了時 2.11 / boot 開始時 2.11・boot 終了時 1.94 (4 vCPU)。
- `FLEBOOT_RESULT`: `units_run 13` / `units_total 942` / `boot_threw "log_cap"` / `boot_threw_raw null` / `log_cap {hit: bytes, bytes: 5311, lines: 68, elapsed_ms: 607}` / `getmem 10` / `freemem 5` / `longjmp 0` / `exit 0`。
- `FLEBOOT_IPP_CHECK`: `ok: false` (`ptr_15F34A0 = 0x0`)。IPP 登録の前 (unit 14 以前) で止まるため、判定は NG になる。これは停止の結果で、既定 (cap 0) の判定ではない。rc 3。
- 結果 JSON: `results/boot_summary_fle5058cap_default.json`。

### 3-2. 修正後・cap 0 (対照)

- 実行: `FLE_BOOT_TAG=fle5058nocap FLE_BOOT_LOG_CAP=0 FLE_BOOT_RUNS=default bash tools/flelift/boot/fle6_measure.sh`
- 所要: 20:48:26 → 20:51:09 (2 分 43 秒)。lift 77 s・clang-plain 68 s・boot 12 s。load は boot 開始時 1.89 (4 vCPU)。
- `FLEBOOT_RESULT`: `units_run 895` / `units_total 942` / `boot_threw "exit"` / `boot_threw_raw null` / `log_cap null` / `getmem 3680` / `freemem 1499` / `longjmp 1` / `exit 1` / `ipp_total 67`。
- `FLEBOOT_IPP_CHECK`: `ok: true` (`ptr_15F34A0 = 0x7f10001c`)。rc 0。
- 結果 JSON: `results/boot_summary_fle5058nocap_default.json`。
- #5027 §3-3 (cap 0) と units・GetMem/FreeMem・IPP・停止理由が一致。

### 3-3. 規則の確認 (`log_cap_check.py`)

- `python3 tools/flelift/boot/log_cap_check.py results/boot_summary_fle5058cap_default.json results/boot_summary_fle5058nocap_default.json` → `PASS` (rc 0)。
- 変異 (cap 側 JSON の `boot.threw.cls` を `exit` に書き換え) → `FAIL cap 超過で boot.threw.cls が log_cap でない: 'exit'`・`FAIL (1)` (rc 1)。

## 4. 影響範囲と未解決

- **挙動の変化**: `FLE_BOOT_LOG_CAP` を指定した run は、cap 超過の後の dispatch で止まる (従来は cap 超過後も `exit` まで走った)。cap 既定値 (0 = 無効) は変えていない。`fle6_measure.sh` の `diag_shim` / `diag_negctl` / `ilt` は既定 cap 256MiB のため、超過すると早く止まる (units 数が変わる)。これらの診断 route の結果の読み方は、この変化を前提にする必要がある。
- 出力メモリのハッシュは cap の有無で差が出る (#5027 §3-4)。本 run では比較していない。
- `exit` が正常終了かの判定は #4970 [FLE-36] の範囲。
- 起動 KPI: cap 無効の既定経路は units 895 のまま (変化なし)。cap 4096 では units 13 で止まる (KPI 上は cap の計測路のみ)。最初のウィンドウの有無は**動かしていない** (本 PR は boot の停止経路のみ)。
