# REPORT 付録 — #5253 (HB-H58): CreatePlugInstance の戻り値到達と Wrapper 起動経路からの入場 (#4582 の受入 2・3)

> **正本の分担**: 停止点 `f_4079e0` の原因 (受入 1) は子 #5252 (HB-H57) の範囲。本付録は戻り値未到達の再確認と、起動経路からの到達の実測だけを記録する。

測定 commit: `845010c6e` (`cpi_entry_refs.py` を追加した commit。`cpi_reach.sh` と `cpi_host.c` は変えていない)。検証起点: `origin/main` @ `425347571`。
環境: x64c 生成 (`block19091_PE.bin`・`ott_lifted.c` 1,472,969 行)・emsdk 6.0.12 (`toolchain-emsdk` を `$RUNNER_TEMP/emsdk` に展開)・`fl-win64` を `$RUNNER_TEMP/fl-win64/extracted` に展開・node v22.23.3・4 vCPU。全段直列。

## 1. 受入条件の対応

| # | 受入条件 (issue #5253) | 結果 | 根拠 |
|---|---|---|---|
| 1 | CreatePlugInstance (VA 0x86ab10) が戻り値を返すまで走る。止まる場合は最初に失敗する関数と理由を記録 | 未達 (止まる場所は記録) | `ret=null`・trap `memory access out of bounds`・停止 VA `0x407a3e` (`f_4079e0`・`and rcx, qword ptr [rax - 8]`)。原因の特定は #5252 |
| 2 | 起動経路 (LoadLibrary → GetProcAddress("CreatePlugInstance")) から入場する、または到達できない理由を実測で記録 | 未達 (部分の実測のみ) | §3 の `cpi_entry_refs.py` の結果。名前文字列を直接参照する lift 命令は 0 件。ただし GetProcAddress 呼出 10 件の引数の出所は未追跡のため「到達不可」とは言えない |

## 2. 再現 (測定 commit `845010c6e`)

`cpi_reach.sh block19091_PE.bin <work>` を HEAD で実行した。

- 所要 78 秒 (x64c の生成は別段で 74 秒・`cpi_reach.sh` は emcc 2 回・link・node 実行の全体)。load 0.74 → 0.66 (1 分値・開始→終了は `uptime` で確認)。n=1。
- `entered=true`・`ret=null`・`trap=memory access out of bounds`・`insn_count=908`・`host_calls=2`・`last_insn` 末尾 `0x407a3e`。
- `host_log`: `[cpi] host slot 0 rcx=0xa00000 rdx=0 r8=0x47` → `[cpi] host slot 6 rcx=0xa40000 rdx=0x40f r8=0x77fba8`。
- #3597 付録 §3.2 の値 (`insn_count=908`・`0x407a3e`) と一致した。

## 3. 起動経路の実測 (受入 2)

`cpi_entry_refs.py block19091_PE.bin <ott_lifted.c>` の出力:

| 項目 | 値 |
|---|---|
| export `CreatePlugInstance` の VA | `0x86ab10` |
| 名前文字列 `"CreatePlugInstance\0"` の VA (PE の file offset から RVA 換算) | `0x911059` (`.rdata` 内・export 名表) |
| 生成 C で名前 VA を参照する行 | 0 件 |
| 生成 C で export VA `0x86ab10` を参照する行 | 1 件 (dispatch の `case 0x86ab10ULL`) |
| 生成 C の `imp_GetProcAddress();` 呼出 | 10 件 |

読み取り: Wrapper の code が `"CreatePlugInstance"` の名前文字列を直接参照していない。したがって、名前で引く経路 (GetProcAddress) から `f_86ab10` に入る経路は、lift 済みの直接参照としては見つからない。ただし次の点は未検証:

- GetProcAddress の 10 件は引数 (名前ポインタ) の出所を追っていない。名前を計算で作る・別の文字列を使う可能性は残る。
- `"CreatePlugInstance"` の文字列の UTF-16 版は PE に無い (ASCII のみ)。
- 入場は現状 harness が `_ott_run` で VA を直接呼ぶ方式のまま。Wrapper の LoadLibrary → GetProcAddress 経路での入場は未実施。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `f_4079e0` の停止原因と `ret` 取得 (受入 1) | 完走・戻り値は未達 | #5252 (HB-H57) |
| GetProcAddress 10 件の名前引数の出所の追跡 (受入 2 の「到達不可」の判定) | 起動経路からの到達可否は未判定 | #5253 (本 issue・部分達成のため open) |
| 完走後の wasm 実行結果 (bit 一致) | 未検証 | #4582 (HB-H56) |
