# REPORT_APPENDIX_3696 (WIN-37 #3696)

親 #3353 の受入 3 の残り。`cfi_probe.mjs` の `boot.err` (22 行目) と `call.err` (43 行目) が `String(e)` で `[object Object]` になる整形を直した。

## 1. 結論

- 受入 1 (整形の一本化): 達成。`err_line.mjs` の `errLine(e)` を `boot.err` と `call.err` の両方が使う。
- 受入 2 (合成例外の単体検証): 達成。`err_line_check.mjs` (node のみ) は 9 件 PASS。ネガコン (整形を元の `((e && e.message) || String(e)).split('\n')[0]` に戻す) では 3 件 FAIL。
- 受入 3 (`cfi_boot7.sh` の前後比較): 達成。修正前 (`origin/main` `fee0ae57b`) と修正後 (`a8200f1e0`) で `boot.ok`・`call.returned`・`call.err`・`reach` が一致。変わったのは `boot.err` だけ (§3)。

## 2. 実測 (測定 commit `a8200f1e0`・修正前は `fee0ae57b`)

- 手順: `ws-3696` (worktree・`3696-cfi-probe-err-format`) に `work-m11` を展開し、`m11_wndseed.sh` (rc 0・3 分 35 秒・WNDCLASS-CHECK PASS) で `boot6.lift.ll` を作ってから `cfi_boot7.sh` を実行。EMSDK = `/opt/emsdk`・RETDEC = `/opt/retdec/bin`・FL_WIN64_DIR = `fl-win64` の展開先。
- `cfi_boot7.sh`: 修正前 5 分 47 秒・rc 0 / 修正後 5 分 43 秒・rc 0 (`closure new functions: 1133`)。
- load (`uptime` 1 分値・修正後の run の終了後 05:46Z): 0.54 (4 core)。
- 単体検証: `node err_line_check.mjs` → `PASS all` (rc 0)。ネガコン (`errLine` を元の式に置換した複製) → `FAIL 3 件` (rc 1)。
- 生成物は `tools/m11/work/` と `tools/gui/work/` (gitignore。commit しない)。

## 3. 前後比較 (`cfi_b7.json`)

| 項目 | 修正前 | 修正後 | 一致 |
|---|---|---|---|
| `boot.ok` | true | true | 一致 |
| `boot.err` | `[object Object]` | `{"m11_dllmain_done":1}` | **変化 (意図どおり)** |
| `call.returned` | false | false | 一致 |
| `call.err` | `Aborted(native code called abort())` | 同左 | 一致 |
| `reach` | 24 件 | 24 件 (中身も同一) | 一致 |
| `call.stack` | `cfi_probe.mjs:41:17` を含む | `cfi_probe.mjs:42:17` | import 1 行の追加による行番号の差のみ |

`boot.err` の `{"m11_dllmain_done":1}` は、boot が DllMain の完了で投げる marker (`m11_throw_dllmain_done`) である。`boot.ok: true` の経路で、例外による失敗ではない。stack は `out.boot.stack` に別に残るため、JSON からは外している。

## 4. 検証範囲

- 単体検証は、各値を実際に `throw` して `catch` し、`cfi_probe.mjs` と同じ経路で `errLine` に通す。対象は `Error` (message あり・複数行・空)・message を持たない object (marker 形・plain・循環参照)・文字列 (複数行)・`null`・`undefined`。
- `err_line_check.mjs` の `[object Object]` を含まないチェックは、整形結果が 1 行で `[object Object]` を含まないことを確かめる。

## 5. 製品 KPI (起動・GUI)

`boot_b7.json` の前後比較 (run.mjs・同じ手順)。起動結果は変わらない (`boot_metric: unchanged`)。

| KPI | 修正前 | 修正後 |
|---|---|---|
| `dllmain_done` | true | true |
| 通過 unit 数 (`units_run` / `units_total`) | 109 / 942 | 109 / 942 |
| `init_count` | 111 | 111 |
| 最初のウィンドウ (`CreateWindowExW` の IMPL 呼出し) | 1 回 | 1 回 |
| `reach` | 24 件 | 24 件 (同一) |

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| init 1675 (`InitializeCriticalSection(0x12bd390)`) に boot が届かない | `EnterCriticalSection` の CS-MISS で止まる | #3478 [WIN-26] (既存) |
| boot7 込みの e2e (JUDGE・S1) は未測定 | 既定の build は boot7 を含まない | #2904 [WIN-12] (既存) |
