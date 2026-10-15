# REPORT 付録 — WIN-34 (#3557): 窓 import の呼出元 VA・引数の trace と main 取り込み後の再測定

親: [`REPORT_WIN7_2718.md`](REPORT_WIN7_2718.md) §6 (要約)。本ファイルは §6 の全文で、節番号は親と同じ。手順の正本は `spike_cfi.py`。

## 6. WIN-34 (#3557): 窓 import の呼出元 VA・引数の trace (部分達成。画素統計は子 issue へ)

測定 commit: `913063ebe` (WIN-34 の実装の最後の commit。§6.1〜§6.6 はこの時点の実測)。main (`c2324dea6`) を取り込んだ後の再測定は §6.7 (測定 commit `33ddb3f45`)。
再現: `cd tools/liftdiff && FL_WIN64_DIR=<fl-win64 展開先> python3 spike_cfi.py targets/flelift.json` (`SPIKE_WINTRACE=0` で窓の記録を切る)。
素材: fl-win64・toolchain-emsdk・work-m11・work-liftdiff。実行環境: GitHub Actions runner (4 CPU)、`uptime` の load average 0.33 (e2e 直前)。

### 6.1 窓 import の呼出元と引数 (実測・spike 1 回)

| import | 呼出元 VA (rva) | 引数 (実測) | 戻り |
|---|---|---|---|
| GetClassInfoW | 0x52a825 (0x12a825) | class="TPUtilWindow" | 0 |
| RegisterClassW | 0x52a85e (0x12a85e) | class="TPUtilWindow"・style=0x0・wndproc rva=0x24920・hInstance=0x400000 | 0 |
| CreateWindowExW | 0x52a8c3 (0x12a8c3) | ex=0x80・class="TPUtilWindow"・wname=""・style=0x80000000・x=y=w=h=0・parent=0・menu=0・hInstance=0x400000・lpParam=0 | 0 |

- 既定の応答は変えていない (記録の追加のみ)。窓の戻り値は従来どおり 0 で、CreateFruityInstance は従来どおり rva `0x4e0fab` で segv する。
- **訂正**: §1.1 は S19 の窓を `TApplication` と推定していたが、実測の class は `TPUtilWindow` (隠し 0×0 の WS_POPUP 窓)。Delphi の `Classes.AllocateHWnd` の引数並びと一致 (推定)。`TApplication` の窓はこの時点では作られていない。
- 呼出元 (rva 0x12a8c3 付近) の関数名は未同定。

### 6.2 stk 位置の不一致 (既存の挙動。本 PR では未修正)

- `ld_ms_call.S` の `ld_stub_common` は `leaq 212(%rsp)` で stk を渡す。実測 `stk_minus_entry=28` (entry rsp からの差)。MS x64 の第5引数は entry+0x28 (=40) にある。
- 影響: `MultiByteToWideChar`・`WideCharToMultiByte` の a4/a5 (`stk[0]`・`stk[1]`) が誤る。実測の spike で `WideCharToMultiByte` の a4 は `0x55844ec000000000` (ホスト値)。
- 既定の応答を変えるため、本 PR では直さない → 子 issue [LD-170] (boot 928/942 と sample:800 への影響を測る)。
- 本 PR の trace は entry+0x28 から直接読む (`wt_rec`)。その値は CreateWindowExW の第5〜12引数として整合 (x=y=w=h=0・hInstance=イメージ基底)。

### 6.3 既定の挙動の回帰 (spike: FLEngine 起動の KPI)

| 項目 | 変更前 (基準 `42c6bcfdd`。`tools/liftdiff` は origin/main と差分 0) | 変更後 (`913063ebe`) |
|---|---|---|
| units_run / first_fail | 928/942・830 | 928/942・830 (2 回とも同じ) |
| CreateFruityInstance | segv rip_rva `0x4e0fab` | 同じ |
| 呼出し import 数 | 35 | 35 |
| 記録オフ (`SPIKE_WINTRACE=0`) 2 回の差 | — | 完全一致 (呼出し 35 件の全項目) |
| 基準 vs 記録オフ | — | 戻り値・関数名は 35 件全件一致。引数は 20 件のみ差 (使われない未初期化レジスタの残り値 = ホストの `0x5555…`・stack の `0x7fff…`) |

ネガティブコントロール: `SPIKE_WINTRACE=0` で窓の記録行 0 行 (`spike_wintrace.txt`)、既定で 9 行 (cfi 3 件 + 他 case 6 件)。

### 6.4 liftdiff e2e の回帰 (`bash liftdiff_e2e.sh --m11-only`・受入 3)

| 実行 | commit | 一致 / 不一致 / 実行不能 | 所要 | 結果 |
|---|---|---|---|---|
| 基準 | `01f1b7e51` (origin/main) | 360 / 234 / 206 | 3 分 04 秒 | LIFTDIFF_E2E PASS (rc 0) |
| 新 1 | `913063ebe` | 361 / 233 / 206 | 3 分 05 秒 | PASS (rc 0) |
| 新 2 | `913063ebe` | 360 / 234 / 206 | 3 分 03 秒 | PASS (rc 0) |

関数単位 (800 件) の突合 (case outcome の変化・verdict の変化。再現: `python3 tests/batch_flips.py <基準の batch.jsonl> <新の batch.jsonl>`):

| 比較 | case outcome 変化の関数数 | verdict 変化 |
|---|---|---|
| 基準 vs 新 1 | 7 | 1 |
| 基準 vs 新 2 | 4 | 0 |
| 新 1 vs 新 2 (同じコード) | 6 | 1 |

同じコード同士でも同程度に揺れる (hang・timeout の分類、ホストのアドレスを含む比較)。件数の差は実行ごとの揺れの範囲内で、既定の挙動の変化とは判定しない。

### 6.5 KPI (起動・GUI に関わる。PR 本文に転記)

| KPI | 前 | 後 |
|---|---|---|
| 最初のウィンドウ (surface の画素) | 無し | **無し・動かしていない**。作られるのは隠し窓 `TPUtilWindow` (0×0)。可視窓 (TApplication) は rva 0x4e0fab の segv より後の段 |
| CreateWindowExW の呼出元 | 未記録 | VA `0x52a8c3` (rva `0x12a8c3`)、引数を記録 |
| FLEngine 起動の dispatch 数・通過 unit 数 | 928/942 (first_fail 830) | 同じ (928/942・830) |

### 6.6 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| headless host への接続と surface 画素統計 (受入 2)。PNG は作らない (受け渡し: PM 判断待ち) | 可視窓の画素は未取得。前提は `.mo` 読込み後の止まりの解消 (#3556) | 子 issue [WIN-35] (依存: #3556) |
| stk 位置 (entry+28 ≠ 第5引数 entry+40) | MultiByteToWideChar/WideCharToMultiByte の a4/a5 が誤り得る | 子 issue [LD-170] |
| 呼出元 rva 0x12a8c3 の関数名 | 未同定 (推定: Classes.AllocateHWnd) | 追跡のみ (PR 本文の未解決表に記載) |

### 6.7 main 再取り込み後の再測定 (merge `cfc0071d9`・競合解消)

main `058984fa0` の取り込みで `rt/ld_native.c` (main 側の LD-161 `ab_return`)・`rt/ld_core.h`・`rt/ld_runner.mjs`・`ldlib/` にコード変更が入った。前回の測定 commit `33ddb3f45` とはコードが変わったため、取り込み後の HEAD で spike と e2e を再実行した。競合は `rt/ld_native.c` の 1 箇所で、両側を残した (`wt_rec` を先、`ab_return` を後)。

- 測定 commit: `cfc0071d9` (main `058984fa0` の merge と競合解消。コードを変えた最後の commit)。
- 測定後の差分: `git diff cfc0071d9 HEAD -- tools/liftdiff/rt tools/liftdiff/spike_cfi.py tools/liftdiff/ldlib tools/liftdiff/liftdiff_e2e.sh` の出力は空 (コード差分 0)。
- 環境: GitHub Actions runner (4 CPU)。load average は spike 1 回目の直前 0.61、e2e 1 回目の直前 0.77、e2e 2 回目の直前 5.51 (1 回目の直後で並列 shard の負荷が残った)。

| 項目 | 結果 (`cfc0071d9`) |
|---|---|
| spike: units_run / first_fail | 928/942・830 (2 回とも同一) |
| spike: CreateFruityInstance | segv rip_rva `0x4e0fab`・呼出し import 35 件・`calls_over` 0 (2 回とも同一) |
| spike: 窓 import の呼出元 VA | GetClassInfoW `0x52a825`・RegisterClassW `0x52a85e`・CreateWindowExW `0x52a8c3` (§6.1 と一致。2 回とも同一) |
| spike 2 回の差 | rsp/rbp/rsi/s1 など stack アドレス (0x10) のみ。rip・status・calls・窓の記録行は一致 |
| spike 実行時間 (real, 1 回目) | 18.4 s |
| e2e `bash liftdiff_e2e.sh --m11-only` 1 回目 | `LIFTDIFF_E2E PASS` (rc 0)・real 3m09.9s・sample:800 一致 361 / 不一致 233 / 実行不能 206 |
| e2e `bash liftdiff_e2e.sh --m11-only` 2 回目 | `LIFTDIFF_E2E PASS` (rc 0)・real 3m10.1s・sample:800 一致 360 / 不一致 234 / 実行不能 206 |
| e2e 内の `CHECK_INITUNITS` | PASS (2 回とも・hybrid `units_run=928/942 first_fail=830`) |
| e2e 内の UNIT18 の 3 項目 (`_UStrAsg`・`Move(409c80)`・`4123c0`) | 3 件 PASS (2 回とも) |

e2e は 2 run。一致 361/233 と 360/234 の差は §6.4 と同じく同一コードでの揺れで、既定の挙動の変化とは判定しない。`CreateWindowExW` の窓は戻り 0 の stub のため作られず、KPI (最初のウィンドウ・dispatch 数・通過 unit 数) は §6.5 と同じ。
