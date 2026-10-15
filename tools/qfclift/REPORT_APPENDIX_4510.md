# tools/qfclift 付録 4510 — #4510 (T-SH-126): longjmp 継続の偽の停止の修正

REPORT.md §7.8 の偽の停止 (`ExitProcess(0)`) の修正の記録。検証 HEAD = `2c6a92ec0` (コードを変えた commit)。

## 1. 原因と修正

- 原因: `qfc_ov_longjmp` は復元した継続を、longjmp を呼んだ深い C フレームの上で `ott_dispatch` する。継続の `ret` が
  古い C フレーム (`f_40fa40` → `f_40fb80`、呼出し site `0x40fcb8`) へ戻り、後行の `ExitProcess(0)` (`0x40fcdd`) に届く。
  実機の longjmp は戻らないので、この経路は実機に存在しない。
- 修正 (qfclift 内に閉じる。`fle_run` と rt は変えない): boot 専用の `qfc_run` が `setjmp` アンカーを張って `fle_run` を呼ぶ。
  `qfc_ov_longjmp` は継続先と復元値を記録して `longjmp` で C フレームを捨て、アンカーの直下から `ott_dispatch` する。
  `qfc_boot.sh` は `QFC_EXTRA_EXPORTS=_qfc_run` で export を足し、`qfc_boot.mjs` は `_qfc_run` を呼ぶ。e2e の entries・assert は変えない。

## 2. 対照 (同一 HEAD 系統・soft 版・各 1 回)

| 構成 | 停止点 (`stopped_by`) | `ExitProcess` の行数 |
|---|---|---|
| 修正前 (`qfc_ov_longjmp` が直接 `ott_dispatch`) | `[fle] ExitProcess(0)` (DllMain 内) | 1 |
| 修正後 (`2c6a92ec0`) | `FontCache_GetStats` で `call to UNLIFTED function 0 ret=0x57fb09` | 0 |

- 修正後の DllMain は `rax=0x1` で戻る (`steps[0]`: ok・7 ms)。`ExitProcess` より後の段へ進んだ。
- 修正後も boot は FAIL (strict は `MISSING IMPORT LocalAlloc`・soft は `FontCache_GetStats` の関数 0 が UNLIFTED)。
  PASS 条件 (3 段 ok・soft 呼出し 0) は未達。FT 解決 (`0x563000`) の未解決ポインタが次の停止点。

## 3. 検証

- e2e (`qfc_e2e.sh`、`2c6a92ec0`): PASS (exit 0)・functions 6,347 / insns 208,714 / unsup 0 / unlifted 0・
  `qfc_diff` PASS・negctl 4 本 FAIL 検出。real 131 s・load 1.00 0.66 0.34。
- boot (`qfc_boot.sh`、`2c6a92ec0`): FAIL (上記の停止点)。real 21 s・load 0.89 0.66 0.35。
