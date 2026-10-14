# #2070 REPORT — 0x52cf40 の「見つからない」経路と 0x4e5f50 / 0x4e6060 の RTTI artifact 整理

- 担当 issue: #2070 `[PLG-P0b-14]` (親 #2016)。
- 起点: `origin/main` 0d9b5385。branch `2070-plg-p0b-14-retaddr-rtti`。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-fw-stage1` を repo 直下に展開。`work-liftlib` / `toolchain-*` / `plugins-ott` は本 run で未使用。
- 測定 commit: `445a5549` (`fw_hostfix.py` の注釈のみ変更。IR 生成物は不変)。

## 1. 受入条件の達成状況

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | `0x52cf40` の `@441`/`@443` に対応する native 側の文言・分岐の意味を確定 | **達成 (前提の否定)**。native の `0x52cf40` は関数の入口ではなく、`.pdata` 関数 `[0x52ce50, 0x52cf67)` の命令途中 (§3.1)。呼出元 `0x52d230` も同様に `.pdata` 関数 `[0x52d220, 0x52d2fb)` の命令途中で、lift の `@441`/`@443` 分岐は native に対応する経路が無い。「見つからない経路」は native に存在せず、`fw_hostfix.py` の 0 注釈は stub (意味づけは無し) として扱う |
| 2 | `0x4e5f50` / `0x4e6060` の IR 名が lift artifact かを確認し、`fw_hostfix.py` の注釈を根拠付きで更新 | **達成**。両 VA は `.text` 内だが `.pdata` 外の RTTI 文字列領域 (§3.2)。注釈 (0x52cf40 / 0x4e6060) を訂正 (`445a5549`) |
| 3 | REPORT に実測 (所要時間・load・PASS/FAIL) と Phase A 回帰 `dispatch=38 ff=0` | **達成** (§2) |

## 2. 実測

環境: 4 vCPU・メモリ 15 GiB。load は `uptime` の 1 / 5 / 15 分値。

| 手順 | commit | 結果 | 所要時間 (real) | load (開始時) → (終了時) |
|---|---|---|---|---|
| `fw_stage2.sh` (stage-1 再利用・`FL_WIN64_DIR` 指定) | 445a5549 | exit 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 7 分 23.0 秒 (443 s) | 0.25 / 0.42 / 0.23 (08:48) → 2.50 / 2.46 / 1.22 (08:55) |
| `hs_e2e.sh --fresh` | 445a5549 | exit 1 / Phase A `dispatch=38 ff=0` (回帰 OK) / `Phase B 例外: memory access out of bounds` / `status=0xffffffff plug=0x0 rec=7` / `E2E FAIL: 1 項目` | 2 分 39 秒 (159 s) | 2.50 / 2.46 / 1.22 (08:55) → 1.13 / 1.89 / 1.20 (08:58) |

- Phase B の失敗は REPORT_2016 §2・REPORT_1933 §2 と同一 (OOB・`plug=0x0 rec=7`)。本 PR はコード動作を変えないため変化なし。
- 測定 commit `445a5549` 以降のコード差分: §4 参照。

## 3. 読解

### 3.1 `0x52cf40` (受入 1)

- `hs_callee_disasm.py` で `.pdata` 関数 `[0x52ce50, 0x52cf67)` を先頭から逆アセンブル。`0x52cf40` は線形列の命令境界に**無い** (`0x52cf3a lea` の 7 バイト `mov` `0x52cf3e` の内側に入る)。
- `.text` 全体の E8 (`call rel32`) 走査で、`0x52cf40` への直接 call は **0 件**。`jmp`/`jcc` の分岐先としても 0 件。絶対アドレス参照 (データ内のポインタ) も 0 件。
- 関数本体が呼ぶのは `0x418260`・`[rbx+0x58]` (vtable)・`0x418190` のみ。`0x52ce00` へ分岐する経路は無い。
- よって lift の `function_52cf40` は、命令途中から decode された artifact。旧注釈の「CRC32 → 0x52ce00 で OOB」は native に対応しない (訂正)。
- 呼出元は lift IR の `function_52d230` (`fw1` / `fw3` / `fw7`)。
- `0x52d230` も native では命令途中 (`0x52d229 mov qword ptr [rbp+0x20],0` の 8 バイト内)。実際の関数は `.pdata` `[0x52d220, 0x52d2fb)` で、そこは `0x52d0f0` の結果 (`eax`) を `0x52d25d`・`0x4397d0` で判定する別の処理。`0x52cf40` を呼ばない。
- よって lift の `@441`/`@443` 分岐は、命令途中から decode された IR 上の比較であり、native の文言・分岐先とは対応しない。

### 3.2 `0x4e5f50` / `0x4e6060` (受入 2)

- 両 VA は `.text` 内 (exec) だが `.pdata` 外。先頭 32 バイトは RTTI 文字列: `0x4e5f50` = `tem.Generics.Defaults`、`0x4e6060` = `Object>.ParrayofT`。
- E8 / jmp 走査で直接の分岐元は 0 件。
- 旧注釈の「0x4e5fc0 からの自己再帰」は、`0x4e5fc0` が `.pdata` 外のデータ領域で、関数として成立しない。`hs_dbg` の 40 段再帰は lift artifact 上の挙動。
- lift の `function_4e5f50` / `function_4e6060` は、RTTI 文字列を関数として decode した artifact と判定。`fw_hostfix.py` の 0 注釈は呼出元を通すための stub で、native の根拠は無い (注釈を訂正)。

## 4. コード差分

測定 commit `445a5549` から HEAD までのコード差分は 0 行 (本 REPORT の追加以外に変更なし。`git diff 445a5549 HEAD -- tools/plugins/framework/ ':!tools/plugins/framework/REPORT_2070.md'` の出力が空)。よって main 取り込み後の再測定は不要 (`docs/WORKFLOW.md` §6)。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x52d220` 関数 (native の実処理) の lift 対応 | lift 側 `function_52d230` は artifact で、正しい入口 `0x52d220` の IR 名が未確定 | 本 PR では扱わない (新規起票なし・受入外) |
| Phase B の OOB (fold deref `0x40d6e0` / `[0x710040]` と `plug != 0`) | e2e FAIL が継続 | #1890 `[PLG-P0b-8]` / #2008 `[PLG-P0b-11]` (既存) |
| 受入 1・2 (`0x4181e0` の基底構造体と戻り値) | `fw_hostfix.py` の 0 注釈の根拠は未確定 | #2069 `[PLG-P0b-13]` (既存) |

## 6. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
tar --zstd -xf $HOME/artifacts/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
tar --zstd -xf $HOME/artifacts/work-fw-stage1.tar.zst            # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh                        # exit 0・SMOKE PASS
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh          # FAIL (Phase B OOB) が期待値
PYTHONPATH=<capstone,pefile> FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 \
  python3 tools/plugins/framework/hostshim/hs_callee_disasm.py 60 0x52cf40 0x52ce00
```
