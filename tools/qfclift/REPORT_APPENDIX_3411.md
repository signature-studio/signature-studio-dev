# qfclift REPORT 付録 (#3411): DllMain 経路の import 呼出し計数

本文は `REPORT.md` §10 (結論と未解決)。全文・表・手順はこのファイル。


測定 commit = `5c79daa2b` (HEAD。`qfc_count.sh` を HEAD で link・実行して得た値)。再現は `tools/qfclift/qfc_count.sh` (前提: `qfc_boot.sh` で lift 済み)。判定はしない。
間接経由も計数した (§4374: 停止点まで 0 件)。停止後の間接呼出しは未計数 (#4262)。

### 10.1 呼出し回数 (直接呼出し・DllMain(PROCESS_ATTACH) → 停止点まで、n=1)

| import | 呼出し回数 (直接) | 実装元 | Windows 仕様との対応 (戻り値・副作用) |
|---|---|---|---|
| `GetCurrentThreadId` | 1 | `fle_cpu.c:160` | 戻り値 = スレッド ID。rt は固定値 1 を返す (実物の ID ではない) |
| `TlsAlloc` | 1 | `fle_cpu.c:170` | 戻り値 = 新しい TLS index。HEAD の rt は 0 から連番 (`g_tls_next`) を返し、64 を超えると `0xFFFFFFFF` (TLS_OUT_OF_INDEXES) を返す。Windows の実物の割当値とは一致しない (実物との突き合わせは未実施) |
| `LocalAlloc` | 1 | `qfc_imp.c:7` | 戻り値 = 割当メモリの HLOCAL (失敗時 NULL)。`calloc` で 0 初期化 (LMEM_ZEROINIT の有無によらず 0 初期化する点は実物より強い) |
| `TlsSetValue` | 1 | `fle_cpu.c:177` | 副作用 = slot への値の保存、戻り値 = 成功で非 0 (HEAD の rt は割当済み index なら 1、未割当 index なら 0 を返す) |
| `TlsGetValue` | 1 | `fle_cpu.c:173` | 戻り値 = slot の値。HEAD の rt は割当済み index の未設定 slot で 0 を返す (仕様どおり)。未割当 index でも 0 を返すが、Windows の `ERROR_INVALID_INDEX` に相当する last error は立てない (rt の `GetLastError` は常に 0) |
| `ExitProcess` | 1 | `fle_cpu.c:198` | 副作用 = プロセス終了 (戻り値なし)。rt は `exit(code & 0xff)` で終了する |

- 停止点 (HEAD の計数版): `ExitProcess(0)` (DllMain 内の直接呼出し。`[trap] DllMain` で終了)。soft stub の呼出しは 0 件。HEAD の boot (`qfc_boot.sh`) は strict が `MISSING IMPORT LocalAlloc`、soft が `ExitProcess(0)` で止まった (`0x59c210` の段は本 run のログでは確認していない)。
- DllMain の戻り値は得られていない。`FontCache_GetStats` / `FontCache_CleanUp` は未到達。

### 10.2 この PR で行ったこと / 行わなかったこと

- 直接呼出しとして計数された import は 6 件で、すべて rt・`qfc_imp.c` に既存。よって直接経路で新たに実装が必要な import は **0 件**。`qfc_imp.c` と rt は変更していない。
- `qfc_count.sh` の emcc 行を `qfc_lift.sh` の `wasm_build` と同じ入力集合 (`qfc_ov.c`・`qfc_import.c`・`FT_WASM32_LIB`・`-I` 群) に揃えた (commit `5c79daa2b`)。一時版の手修正は使っていない。
- 停止点までの間接呼出しは 0 件。直接呼出しの件数は §4374 (HEAD 計測) の 5 件が正本。§10.1 の 6 件は `5c79daa2b` 時点の値で HEAD と一致しない (差の原因は未特定・§10.3 の未解決表)。停止後は #4262 で扱う。
- 受入 2 の「soft 呼出し 0 件にする」は満たさない (soft 呼出し 0 件は元から満たしていた)。停止点の解釈 (偽の停止か) は #4262 の範囲。

### 10.3 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 停止点 `ExitProcess(0)` が偽の停止か (longjmp 継続後の進行) | DllMain が完走したか不明 | #4262 (T-SH-106) |
| longjmp (0x40f9c0) の発生条件と戻り先 `0x59c210` の lift 対応 | 停止点の解釈 | #4263 (T-SH-107) |
| 停止後の間接呼出し | 停止点までは 0 件 (§4374)。停止後は未計数 | #4262 (T-SH-106) |
| HEAD の rt の TLS 系の残る差: `GetLastError` が常に 0 (`TlsGetValue`・`TlsSetValue` の未割当 index で last error が立たない)・`TlsFree` の実装が無い (`imp_TlsFree` 不在。import された場合の扱いは未確認)・`TlsAlloc` の割当値が実物と違う | DllMain 後段で TLS 値・last error を読むと結果が変わり得る。FLEngine の既存結果への影響は未確認 | #4375 (T-SH-122) |
| `GetCurrentThreadId` (固定 1) の実物との対応が未確認 | 値を使う経路で結果が変わり得る | #4280 (T-SH-108) |
| `FontCache_GetStats` / `CleanUp` の実行と DllMain の戻り値 | PASS 判定が未到達 | #4296 (T-SH-113) |

## 4374 間接経由 import 呼出しの計数 (T-SH-121 / #4374)

測定 commit = `0f43b7741` (計測した code。`origin/main` 取り込み後の HEAD)。`git diff 0f43b7741 HEAD -- tools/qfclift tools/flelift/rt tools/shared/oss/freetype tools/flelift/x64c.py ':!*.md'` の出力は 0 行 (以後の commit は REPORT の md のみ)。
前回の測定 commit `71b77279b` は main 取り込みで code が入ったため、その後の `0f43b7741` で再測定した (`71b77279b..0f43b7741` の code 差分は `tools/flelift/rt` 4 ファイル・`x64c.py`・`qfc_probe_4262.sh` で 1107 行追加)。
手順: `QFC_BOOT_REBUILD=1 qfc_boot.sh` → `qfc_count.sh` (いずれも foreground)。素材: `fl-win64` と `toolchain-emsdk` (emcc 6.0.12)・FreeType 2.7 wasm32 を `tools/shared/work/` に作成。
- boot: rc 1 (FAIL)。lift は functions 6348・unsup 0・unlifted 0・imports 222。strict `MISSING IMPORT LocalAlloc`・soft は `DllMain` rc=0x1 の後 `FontCache_GetStats` で trap。wall 28.3 s・load 1.12 → 1.15。
- 実行 `qfc_count.sh`: rc 0・wall 11.2 s・load 1.15 → 1.12。
- 生成: imp_tab 行 223 (used 222)。直接呼出し書換え 1681 箇所 (名前別 222 種)。
- 停止点まで: `[step] DllMain` → 直接呼出し 5 件 (GetCurrentThreadId 1・TlsAlloc 1・LocalAlloc 1・TlsSetValue 1・TlsGetValue 1) → `[trap] DllMain`。`ExitProcess` は出ない。
- 間接経由 (`(ind)`) の呼出し: **0 件**。soft 呼出し: **0 件**。
- 戻り値・副作用: 計数行は stderr の `[fle] CALL <名>` のみ。行き先は元の imp_<名> をそのまま呼ぶ。
- 未達のまま残る点: 停止後の進行 (偽の停止か) は #4262 で扱う。停止後の間接呼出しは現時点で未計数。
- 旧計測 (`93fde48ab`・直接 6 件・停止点 `ExitProcess(0)`) は、その後の `tools/qfclift` の変更で HEAD と一致しなくなった。原因は未特定 (§10.3)。

### 10.4 TLS 変更の前後の計数 (#4307 / T-SH-116)

受入: `973b85aca` (rt の Win32 TLS 仕様化 #4234 / PR 4285) の前後で、同じ `qfc_count.sh` の計数が一致すること。

- 測定 commit = `1110965b3` (`qfc_count.sh` に soft 呼出し件数と件数集計を足した commit。計数版の本体)。
- 前 = `1110965b3` の worktree で `tools/flelift/rt/fle_cpu.c` だけ `973b85aca` を逆適用したもの (TLS の 3 関数だけが `973b85aca^` に戻る)。これは issue #4307 の指定 (`973b85aca` の親 `9c0dfadc9`) とは厳密には一致しない: 残る差は #3434 の `imp_GetProcAddress` → `fle_gpa_hook` 結線 (`git diff 9c0dfadc9 -- tools/flelift/rt/fle_cpu.c` の 2 行) のみで、TLS の差ではない。`9c0dfadc9` 基準の計数は本 PR では未実施 (emcc と FreeType wasm32 と lift 成果物が本 run に無かった)。`9c0dfadc9` の worktree に HEAD 版の `qfc_count.sh`・`qfc_count.mjs`・`gen_count_wrap.py` をコピーすれば同じ手順で計数できる (未実施。PR 本文の未解決表に記載)。
- soft 呼出し件数 0 は「停止点 `ExitProcess(0)` までに soft stub が呼ばれなかった」ことを示すだけで、件数集計 (`grep -c '^\[qfc-soft\] '`) の正しさは確認していない。soft stub が 1 件以上記録する入力での計数は未実施。
- 後 = `1110965b3` そのまま (HEAD の TLS 仕様版)。
- 両方で同じ `lift_meta.json` / `soft_imp.c` (`qfc_boot.sh` の出力) を使い、`qfc_count.sh` を foreground で 1 回ずつ実行 (wall 20.9 s / 20.9 s、load 0.10 → 0.10)。
- 素材: `fl-win64` (`extracted/block24350_PE.bin`)、`toolchain-emsdk` (emcc 6.0.12)、FreeType 2.7 wasm32 を `tools/shared/oss/freetype/build.sh` の手順で作成。

| 項目 | 前 (973b85aca の逆) | 後 (HEAD) |
|---|---|---|
| 直接 import 呼出し件数 | 6 | 6 |
| 内訳 | GetCurrentThreadId 1・TlsAlloc 1・LocalAlloc 1・TlsSetValue 1・TlsGetValue 1・ExitProcess 1 | 同左 |
| soft 呼出し件数 | 0 | 0 |
| 停止点 | `ExitProcess(0)` (`[trap] DllMain`) | 同左 |
| `call.log` | 前後で全行一致 (`diff` 0) | |

判定: 受入を満たす。TLS 変更で DllMain 経路の直接呼出し・停止点は変わらない。

計数の限界 (変わらず): 計数は直接呼出しだけ。間接経由は #4374 で未計数。TLS の戻り値の差 (`TlsAlloc` の割当値・未割当 index の last error など) は計数に現れないため、#4375 の範囲。

boot (`qfc_boot.sh`、HEAD・`QFC_BOOT_REBUILD=1`、実測 51.6 s、load 0.21 → 0.71): strict は `MISSING IMPORT LocalAlloc`、soft は `ExitProcess(0)` で DllMain が止まった (前回 REPORT と同じ停止点)。

## 未解決 (REPORT §10 から分割移動・#4525 で更新)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ExitProcess(0)` の偽の停止は #4262 で判定、#4510 で修正済み (停止点は `FontCache_GetStats` へ進んだ) | DllMain は完走。boot は FAIL のまま | #4510 (T-SH-126) |
| longjmp (0x40f9c0) の発生条件と戻り先 `0x59c210` の lift 対応 | 停止点の解釈 | #4263 (T-SH-107) |
| 間接経由の import 呼出しが未計数 | DllMain 経路の全数が不明 | #4374 (T-SH-121) |
| HEAD の rt の TLS 系の残る差 (`GetLastError` 常に 0・`imp_TlsFree` 不在・`TlsAlloc` の割当値) | DllMain 後段で TLS 値・last error を読むと結果が変わり得る | #4375 (T-SH-122) |
| `GetCurrentThreadId` (固定 1) の実物との対応が未確認 | 値を使う経路で結果が変わり得る | #4280 (T-SH-108) |
| `FontCache_GetStats` / `CleanUp` の実行と DllMain の戻り値 | PASS 判定が未到達 | #4296 (T-SH-113) |
