# tools/python REPORT: PY-146 channels.processRECEvent の PE 意味論と mock/C 実装 (#2544, 親 #2500)

> 前段: `tools/python/REPORT_PY235.md` (general 版の成功経路式・族の分岐)・`REPORT_PY126.md` (呼出し鎖 0xd84740)・`REPORT_PY39.md` / `REPORT_PY70.md` (channels 版の書式 `Iii`)。
> 既知類型との関係: 該当なし (lift ではなく PE の直接逆アセンブル。docs/DEFECTS.md の類型は対象外)。

## 結論

- **channels 版 `0xd58e00` は general 版 `0xd69f00` と同じ呼出し鎖に入る**。解析失敗 (0xd58e94)・成功時の `0xd84740(rbx, &out, eventId, value, flags)` (0xd58e74)・status ≠ 0 の例外経路 (0xd58e94)・`out+0x08` の int 化 (0xd58e82〜) は、general 版 (REPORT_PY126) と同形。
- よって戻り値の式は PY-235 のものを channels 版にもそのまま当てる。**成功経路 (R-other 族かつ `(eventId & 0xffff) != 8`) で戻り値 = value**。族の定義は `host/fl_mock.mjs` の `recPassFamily` と `provider/fl_engine.c` の `rec_pass_family` (general 版と共有の式)。
- mock と C に `channels.processRECEvent` を実装。族外・未確定の経路は code 2 (未実装 error)。
- **未確定**: gate `*(0x15e1890)` の意味 (#3777 は close 済み)・`(eventId & 0xffff) == 8` の -1 条件 (#3777)・固定 eventId 4 族の `flags & 0x22 != 0` の右辺 (#4616 は NOT_PLANNED で close)・0x70000000 族と index 族 (#3779 が open で追跡)。channels 版も同じ核なので、これらは general 版と同じ未確定。

## PE 解析 (fl-win64 `block00031_PE.bin`)

| 項目 | VA | 内容 |
|---|---|---|
| ハンドラ | 0xd58e00 | `d5e620(self)` → `rbx = *rax`。書式 `Iii` (VA 0xd58ee0): eventId = `[rbp+0x7c]`、value = `[rbp+0x78]`、flags = `[rbp+0x74]` |
| 解析失敗 | 0xd58e5c `jle` → 0xd58e94 | `0xd82c20(eax)` を返す |
| 成功の呼出し | 0xd58e74 | `call 0xd84740(rbx, &out, eventId, value, flags)`。`pe_disasm.py` で確認 |
| 例外経路 | 0xd58e7d〜0xd58e94 | `out.status` ≠ 0 なら `0xd82c20(status)` |
| 値の返し | 0xd58e82〜0xd58e92 | status = 0 なら `out+0x08` を IAT `0x88b3f4` で Python 値にして返す |

- 検証: `analysis/py235_process_rec_families.py` (31 ok・0 FAIL・rc 0)・`analysis/py126_process_rec_chain.py` (rc 0)。両方とも general 版の VA を検証する既存スクリプトで、channels 版の呼出し先 `0xd84740` と同じ核 (`0x1046a30`) を使うことを示す。

## 手段

- 展開: `tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64" --wildcards '*block00031_PE.bin'`。
- 逆アセンブル: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 analysis/flapi/pe_disasm.py 0xd58e00 80`。
- 素材 (`fetch_inputs.sh` 用): `*block24429_DATA.bin`・`*block24430_DATA.bin`・`*block25159_DATA.bin`・`*block24618_DATA.bin` を同じ tar から展開。

## 実装と検証

- 変更: `host/fl_mock.mjs` (`channels.processRECEvent`)・`provider/fl_engine.c` (`h_channels_processRECEvent`)・`tests/channels_diff.mjs` (呼出し 15 件を追加。成功経路・族外・固定 4 族の flags 境界・個数違い)・`tests/provider_expect/pe146.json` (実装 1 件の期待)。
- 測定 commit: `01803d59d` (コードを変えた最後の commit)。以降はこの REPORT のみ。`git diff 01803d59d HEAD -- tools/python/host tools/python/provider tools/python/tests tools/python/analysis` の出力は 0 行。
- 環境: emsdk 6.0.12 を `toolchain-emsdk` から展開 (`$RUNNER_TEMP/emsdk-root`)。`EMSDK_ENV` で指定。load avg は測定直前 `1.72 0.90 0.37` (4 コア)。
- `bash provider/build.sh`: rc 0。
- `build_cpython_wasm.sh`: rc 0 (3 分 50 秒)。`FLPY_SKIP_TABLE=1 build_flpy.sh`: rc 0 (flpy.js 120529 B・flpy.wasm 5924680 B)。
- `node tests/channels_diff.mjs`: `{"calls":253,"loop_cases":9,…,"diffs":0,"grid_calls":1200,"grid_diffs":0,"PASS":true}`。
- `node tests/general_diff.mjs`: `{"calls":56,"diffs":0,"PASS":true}` (general 版は変更なし)。
- `node tests/provider_check.mjs`: `{"functions":435,"implemented":234,"unimplemented":201,"mcp_static":60,"PASS":true}`。
- `FL_ENGINE=wasm node tests/all_tools.mjs`: `{"total":48,"ok":48,"soft_error":0,"raised":0,"no_args":0,"host_calls":37425,"callback_roundtrip":true}` (rc 0)。
- wasm 差分テスト (`grep -l createWasmEngine tests/*.mjs` の 28 本、`all_tools` を除く): 28 本全て rc 0。PASS 判定があるもの 26 本で全て diffs 0 または fails 0 (`provider_impl_dump.mjs`・`static_bench.mjs` は PASS 判定なし)。
- KPI: 起動・GUI に関わらない PR のため、製品 KPI は記載しない。

## 副作用 (PE)

- **ハンドラ `0xd58e00`**: 書込みは自分のスタックフレーム (`[rbp+...]`・0xd58e0c〜0xd58e9f) だけ。外部へ作用する呼出しは `0xd84740` (0xd58e74) のみ。その他の呼出し (0xd5e620・0x415610・0x415c30・PyArg 解析の IAT 0x889004・int 化の IAT 0x88b3f4・0xd82c20) は副作用を確認していない。
- **`0xd84740` の callback** (`fl-win64` block00031): `job+0x60` = -2 (0xd846e8) → 0 (0xd8470e)、結果を `job+0x10` へ (0xd84725)。REPORT_PY126 の記述と一致 (再確認: `pe_disasm.py 0xd846e0`)。
- **共通本体 `0x1046a30`**: 入口で gate `*(0x15e1890)` を読む (0x1046d83)。general 版と同じ gate で、1 のとき -1 の経路 (0x1046d8d)。本体の heap への書込み (base レジスタ経由の store) は線形走査で 58 件。channels 成功経路でどの store が実行されるかは CFG で追っていないため、**未確定**。
- 結論: channels 版の副作用は「job の 2 フィールド (0xd84740 経由)」までが PE で確定。本体の書込み先の全列挙は未確定で、未解決表に残す。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 共通本体 `0x1046a30` の heap への書込み先 (channels 成功経路で実行される store の列挙) | 副作用の全列挙が未確定 | 本表で追跡 (追跡 issue なし。解析のみのため子 issue は切らない) |
| gate フラグ `0x15e1890` の意味・`0x663bf0`・`0xffac50`・`[0x15e2878]` | gate 0 を仮定した成功経路の前提。実行時に gate が 1 の場合の挙動が未確定。#3777 は 2026-10-15 に close 済みで、この残りは open な追跡先が無い | 本表で追跡 (PM 判断待ち) |
| 固定 eventId 4 族の `flags & 0x22 != 0` の右辺 | `flags & 0x22 == 0` の成功経路だけ実装。0x20・0x2 のとき code 2 | #4616 (PY-349、NOT_PLANNED で close 済み。追跡先が無い) |
| 0x70000000 族・index 族 (eventId < 0x10000000) の戻り値式 | 2 族が code 2 (未実装) | #3779 (PY-253) |
| 範囲外 code の PE 確定 (受入 1 の「範囲外 code」) | 族外の経路の code は現状 2 で固定。PE 上の範囲外経路は上の未確定族に含まれる | #3779 (PY-253) |
