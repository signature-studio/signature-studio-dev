# qfclift REPORT 付録 (#3411): DllMain 経路の import 呼出し計数

本文は `REPORT.md` §10 (結論と未解決)。全文・表・手順はこのファイル。


測定 commit = `55615e160`。再現は `tools/qfclift/qfc_count.sh` (前提: `qfc_boot.sh` で lift 済み)。判定はしない。
計数は直接呼出し `imp_<名>();` だけ。間接経由 (`imp_by_index` → `imp_tab[k]()`) は含まない (未計数。§10.3)。

### 10.1 呼出し回数 (直接呼出し・DllMain(PROCESS_ATTACH) → 停止点まで、n=1)

| import | 呼出し回数 (直接) | 実装元 | Windows 仕様との対応 (戻り値・副作用) |
|---|---|---|---|
| `GetCurrentThreadId` | 1 | `fle_cpu.c:160` | 戻り値 = スレッド ID。rt は固定値 1 を返す (実物の ID ではない) |
| `TlsAlloc` | 1 | `fle_cpu.c:165` | 戻り値 = 新しい TLS index。rt は常に 0 を返す (index 0 を毎回返すため、2 回目以降の割当が区別できない) |
| `LocalAlloc` | 1 | `qfc_imp.c:7` | 戻り値 = 割当メモリの HLOCAL (失敗時 NULL)。`calloc` で 0 初期化 (LMEM_ZEROINIT の有無によらず 0 初期化する点は実物より強い) |
| `TlsSetValue` | 1 | `fle_cpu.c:167` | 副作用 = slot への値の保存、戻り値 = 成功で非 0 (rt は 1 を返す) |
| `TlsGetValue` | 1 | `fle_cpu.c:166` | 戻り値 = slot の値 (**未設定 slot は 0 を返す**のが仕様)。rt は TEB 初期化で全 slot に非 NULL の `FLE_TLSBLOCK + …` を入れるため、未設定 slot でも非 0 を返す (**仕様と不一致**) |

- 停止点 (n=1 の計数版): `0x59c210` (`call to UNLIFTED function`・ret=0)。soft stub の呼出しは 0 件。
- DllMain の戻り値は得られていない (`trap`)。`FontCache_GetStats` / `FontCache_CleanUp` は未到達。

### 10.2 この PR で行ったこと / 行わなかったこと

- 直接呼出しとして計数された import は 5 件で、すべて rt・`qfc_imp.c` に既存。よって直接経路で新たに実装が必要な import は **0 件**。`qfc_imp.c` と rt は変更していない。
- 間接経由の import 呼出しは未計数のため、「DllMain 経路で実際に呼ばれる import は 5 件」とは言えない (§10.3 の未解決)。再測定 (計数版に `imp_by_index` 経路を加える) は emcc 実行環境が必要で、本 PR では行っていない。
- 受入 2 の「soft 呼出し 0 件にする」は満たさない (soft 呼出し 0 件は既に満たしていた。停止点は #3410 の範囲で、`0x59c210` の lift 対応が必要)。
- rt の `TlsGetValue` の未設定 slot の値 (仕様は 0) は、DllMain がこの値を読むまでは停止点に影響しない。修正は rt の既存 FLEngine の結果に影響し得るため本 PR では変えない (別件で確認が必要)。

### 10.3 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x59c210` (setjmp/longjmp 継続) の lift 対応と longjmp の起動元 | DllMain が完走しない。残りの import 呼出し (計数は停止までの直接呼出し 5 件) が不明 | #3410 (T-SH-77) |
| rt の `TlsGetValue` (未設定 slot が非 0)・`TlsAlloc` (常に 0) が仕様と異なる | DllMain 後段で TLS 値を読むと結果が変わり得る。FLEngine の既存結果への影響は未確認 | #4234 (T-SH-104) |
| `GetCurrentThreadId` (固定 1) の実物との対応が未確認 | 値を使う経路で結果が変わり得る | #4280 (T-SH-108。#4234 は `GetCurrentThreadId` を範囲外としている) |
| `FontCache_GetStats` / `CleanUp` の実行と DllMain の戻り値 | PASS 判定が未到達 | #3412 の子 #3434 ・ #3410 の後段 |
| 間接経由 (`imp_by_index` → `imp_tab[k]()`・`ott_missing_import`) の import 呼出し | 計数は直接呼出しの 5 件だけ。DllMain 経路の間接呼出しは未計数 | #3410 (T-SH-77) |
