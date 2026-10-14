# #1891 REPORT — fail-soft 3 件 (0x52cf40 / 0x4e6060 / 0x4181e0) の分岐先と戻り値の読解 (途中経過)

- 担当 issue: #1891 `[PLG-P0b-9]` (親 #1848)。受入 1・2 は IR 読解で部分達成。受入 3 は未達 (§4)。
- 起点: `origin/main` 68534484。worktree `ws-1891`・branch `1891-plg-failsoft-retval-targets`。
- 前提の REPORT: `REPORT_1848.md` (PR #1893 未 merge。本 run は #1893 の内容に依存せず、同じ IR を再読解)。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64`、`work-fw-stage1` を repo ルート展開。
  `work-liftlib` / `work-icall` / `plugins-ott` は未展開 (hs 系の手順では不使用。issue 本文の `work-icall` は REPORT_1609 §1 のとおり不要)。
  `toolchain-emsdk` / `toolchain-retdec` は runner の `/opt/emsdk` を使用。
- コード変更: なし (`tools/plugins/framework/fw_hostfix.py` は未変更)。測定 commit は `68534484`。

## 1. 受入条件の達成状況

| # | 受入条件 | 結果 |
|---|---|---|
| 1 | `0x52cf40` (呼出元 `function_52d230`・比較 0 → `dec_label_pc_9a499d`) の分岐先の意味を確定 | **部分達成**。分岐先の IR 動作は確定 (§3.1)。文言・意味づけは `@441`/`@443` が zeroinitializer のため IR だけでは確定できない |
| 2 | `0x4e6060` (呼出元 `function_4e6140`・下位 1 バイト 0 → `dec_label_pc_8f3aa6`) の戻り値の意味を確定 | **部分達成**。0 = 非エラー経路 (`8f3aa6`) であることは IR で確定 (§3.2)。「戻り値 0 が何の成功か」は未確定 |
| 3 | `0x4181e0` の戻り値として正しい値を確定し、`fw_hostfix.py` の注釈を再検討 | **未達**。戻り値は基底ポインタとして使われるため、0 は誤り。正しい値は基底構造体の確定が必要 (§3.3・§4) |
| 4 | REPORT に実測値と Phase A 回帰 `dispatch=38 ff=0` | **達成** (§2) |

## 2. 実測

環境: 4 vCPU・メモリ 15 GiB。load は `uptime` の開始時値 (1 / 5 / 15 分)。

| 手順 | commit | 結果 | 所要時間 (real) | load (開始時) |
|---|---|---|---|---|
| `fw_stage2.sh` (stage-1 再利用・`FL_WIN64_DIR` 指定) | 68534484 (未変更) | exit 0・`SMOKE PASS` (`dispatch=38 units_done=0 va=1 heap=1 ff=0`) | 計測なし (下記注) | 0.23 / 0.26 / 0.11 (開始時 07:25) |
| `hs_e2e.sh --fresh` | 68534484 (未変更) | exit 1 / Phase A `dispatch=38 ff=0` (回帰 OK) / `[hs] Phase B 例外: memory access out of bounds` / `status=0xffffffff plug=0x0 rec=7` / `E2E FAIL: 1 項目` | 2 分 40.7 秒 | 2.15 / 1.83 (開始 07:33) → 1.70 / 1.12 (終了 07:36) |

- 注: `fw_stage2.sh` は `time` で計測していない (exit 0 と SMOKE PASS のみ確認)。所要時間は未取得。
- Phase A の回帰 `dispatch=38 ff=0` を stage2 と e2e の両方で確認。
- Phase B は REPORT_1609 §2・REPORT_1848 §2 と同じ失敗 (OOB・`plug=0x0 rec=7`) を再現。

## 3. 呼出側 IR の読解 (`hs_flat3.ll`)

素材: `tools/plugins/work/hs/hs_flat3.ll` (`hs_e2e.sh --fresh` で生成)。スタブ本体は全て `store i64 0 → slot 9048192 (0x8A1080)`・`ret i64 0` (`fw_hostfix.py`)。
つまり「戻り値」は呼出側が読む `9048192` の値で、スタブは 0 を書く。

### 3.1 `0x52cf40` → 分岐 (`function_52d230`)

- `hs_flat3.ll` 625849 行付近。`%15 = call @function_52cf40()` の直後、`%16` = slot `9048192`。
- `%10` は呼出前に読んだ `@442+24` の値。`@442` は zeroinitializer なので **0**。
- 直後に `%16` を `@442+24` へ store し、`icmp eq %16, %10` (= 戻り値 == 0) で分岐:
  - **0 → `dec_label_pc_9a499d`**: `@443` / `@441` を設定し `function_52d0d0` を呼ぶ後始末経路。
    `function_52d0d0` 側は `@239+8` の 32bit カウンタを `-1` して 0 判定する (refcount 型の解放処理と読める)。
  - **非 0 → `dec_label_pc_9a4927`**: `@441` を設定し `__icall_dispatch(5427863)` を呼んで、戻り値 `%26` を使う経路。
- 結論: 「0 = 見つからない」は **後始末経路に進む** と読める。ただし `@441`/`@442`/`@443` の文言が無いので、「見つからない」の意味づけは推定。
- 注意: `@442+24` に戻り値を store しているため、比較の右辺は呼出し前の 0 で固定されている (戻り値 0 判定と同値)。

### 3.2 `0x4e6060` → 分岐 (`function_4e6140`)

- `hs_flat3.ll` 406491 行 `%43 = call @function_4e6060()`。戻り値は slot `9048192` の下位 1 バイト (`trunc i64 → i8`)。
- `%48 = icmp eq i8 %47, 0`。0 のとき `dec_label_pc_8f3aa6` (406531 行)、非 0 のとき `dec_label_pc_8f3a52` (406503 行)。
- `8f3a52` は `@389`/`@390`・`inttoptr 36` の文字列・`function_5006d0` を設定する経路。
- 結論: 0 は非エラー側 (`8f3aa6`) に進む。REPORT_1609 §7.1 の「推定」を IR の分岐構造で確定した。
  ただし「0 が成功か」は `8f3aa6` 後の処理 (`0xmm0`/`rcx`) を読むまで確定しない。

### 3.3 `0x4181e0` → 基底ポインタ (呼出元は grep 先頭 10 件で確認。REPORT_1609 §7.1 では `0x4070f0`)

- 呼出元 `hs_flat3.ll` 9072 行 `%14 = call @function_4181e0()` ほか (同ファイルに 10 件以上)。戻り値 `%15` をベースポインタにして `+24` 等の byte/qword を読み書きする。
- よって 0 を返すと **アドレス 0 + オフセット** を deref する。REPORT_1848 §3.2 の読みと一致 (再確認)。
- 「該当なし = 0」の注釈 (`fw_hostfix.py` 188〜189 行) は、この構造と整合しない。
- 正しい戻り値 (有効なオブジェクトポインタ) は、基底が指す構造体 (`+24` の型・`+520` の field) の確定が前提。**本 run では未確定**。

## 4. 残作業 (子 issue へ)

- `0x4181e0` の正しい戻り値: 呼出元 (9072 行・31416 行付近) の基底構造体の型と、`hs_callee_disasm.py` の VA 境界修正 (native 確認) が要る。受入 3 の残り。
- `0x52cf40` の「見つからない」の確定: `@441`/`@443` に対応する Delphi 側の文言・分岐先 `function_52d0d0` の native 読解。受入 1 の残り。
- `0x4e6060` の「成功」側の意味: `8f3aa6` 以降の処理の読解。受入 2 の残り。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 3: `0x4181e0` の正しい戻り値 (基底構造体の確定) と `fw_hostfix.py` の注釈修正 | 0 を基底に deref し Phase B の障害になっている可能性 | #1933 `[PLG-P0b-10]` |
| 受入 1・2 の残り: 3 件の分岐先の意味づけ (native 読解) | 注釈の根拠が推定のまま | #1933 `[PLG-P0b-10]` |
| fold deref (`0x40d6e0` / `[0x710040]`) と `plug != 0` | Phase B が OOB のまま | #1890 `[PLG-P0b-8]` (既存) |
| `hs_callee_disasm.py` の VA 境界 | native 読解の精度 | 未起票 (本 PR では未対応) |
| `fw_stage2.sh` の所要時間 | 未計測 (time を取らなかった) | 次回再測定で取得 |

## 6. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 ANALYSIS_DIR=$RUNNER_TEMP/analysis
tar --zstd -xf $HOME/artifacts/work-fw-stage1.tar.zst          # repo ルートで展開
bash tools/plugins/framework/fw_stage2.sh                      # exit 0・SMOKE PASS
bash tools/plugins/framework/hostshim/hs_e2e.sh --fresh        # FAIL (Phase B OOB) が期待値
# IR 読解: tools/plugins/work/hs/hs_flat3.ll の該当行 (§3)
```
