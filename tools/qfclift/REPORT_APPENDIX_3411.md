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
- 停止点までの間接呼出しは 0 件のため、6 件 (直接) と併せて停止点までの全数は 6 件。停止後は #4262 で扱う。
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

測定 commit = `93fde48ab` (`gen_count_wrap.py` が imp_tab の各行 223 件を計数版に置換した commit)。実行 `qfc_count.sh` は rc 0・21 s・load 0.24→0.46。
- 生成: imp_tab 行 223 (うち used 222・imp_unimpl 1)。直接呼出し書換え 1681 箇所 (名前別 222 種)。
- 停止点まで: `[step] DllMain` → 直接呼出し 6 件 (GetCurrentThreadId・TlsAlloc・LocalAlloc・TlsSetValue・TlsGetValue・ExitProcess) → `ExitProcess(0)` → `[trap] DllMain`。
- 間接経由 (`(ind)`) の呼出し: **0 件**。`imp_by_index` 経路は停止点まで通っていない。
- 戻り値・副作用: 計数行は stderr の `[fle] CALL <名> (ind)` のみ。行き先は元の imp_<名> をそのまま呼ぶ。
- 未達のまま残る点: 停止後の進行 (偽の停止か) は #4262 で扱う。停止後の間接呼出しは現時点で未計数。

### 10.4 TLS 変更の前後の計数 (#4307 / T-SH-116)

受入: `973b85aca` (rt の Win32 TLS 仕様化 #4234 / PR 4285) の前後で、同じ `qfc_count.sh` の計数が一致すること。

- 測定 commit = `1110965b3` (`qfc_count.sh` に soft 呼出し件数と件数集計を足した commit。計数版の本体)。
- 前 = `1110965b3` の worktree で `tools/flelift/rt/fle_cpu.c` だけ `973b85aca` を逆適用したもの (TLS の 3 関数だけが `973b85aca^` に戻る)。これは issue #4307 の指定 (`973b85aca` の親 `9c0dfadc9`) とは厳密には一致しない: 残る差は #3434 の `imp_GetProcAddress` → `fle_gpa_hook` 結線 (`git diff 9c0dfadc9 -- tools/flelift/rt/fle_cpu.c` の 2 行) のみで、TLS の差ではない。`9c0dfadc9` 基準の計数は本 PR では未実施 (emcc と FreeType wasm32 と lift 成果物が本 run に無かった)。`9c0dfadc9` の worktree に HEAD 版の `qfc_count.sh`・`qfc_count.mjs`・`gen_count_wrap.py` をコピーすれば同じ手順で計数できる (未実施。PR 本文の未解決表に記載)。
- soft 呼出し件数 0 は「停止点 `ExitProcess(0)` までに soft stub が呼ばれなかった」ことを示すだけで、件数集計 (`grep -c '^\[qfc-soft\] '`) の正しさは確認していない。soft stub が 1 件以上記録する入力での計数は未実施。
- 後 = `1110965b3` そのまま (HEAD の TLS 仕様版)。
- 両方で同じ `lift_meta.json` / `soft_imp.c` (`qfc_boot.sh` の出力) を使い、`qfc_count.sh` を foreground で 1 回ずつ実行 (wall 20.9 s / 20.9 s、load 0.10 → 0.10)。
- 素材: `fl-win64` (`extracted/block24350_PE.bin`)、`toolchain-emsdk` (emcc 6.0.12)、FreeType 2.7 wasm32 を `tools/shared/oss/freetype/build.sh` の手順で作成。


判定: 受入を満たす。TLS 変更で DllMain 経路の直接呼出し・停止点は変わらない。

計数の限界 (変わらず): 計数は直接呼出しだけ。間接経由は #4374 で未計数。TLS の戻り値の差 (`TlsAlloc` の割当値・未割当 index の last error など) は計数に現れないため、#4375 の範囲。

boot (`qfc_boot.sh`、HEAD・`QFC_BOOT_REBUILD=1`、実測 51.6 s、load 0.21 → 0.71): strict は `MISSING IMPORT LocalAlloc`、soft は `ExitProcess(0)` で DllMain が止まった (前回 REPORT と同じ停止点)。
