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
- 上表は `case=cfi` の行 (CreateFruityInstance 内)。同じ呼出元 VA の boot 段の 2 行 (`case=ep`・`case=u880`) では x または w に `0x7fff00000000` が出る。int 引数の上位 32 bit の残りと考えられる (推定)。下位 32 bit は 0 で、上表と一致する。
- 前提 (m1): `ld_stub_ent` は単一のグローバルで、`wt_rec` は `ld_stub` の戻り後にこれを読む。3 import の stub は guest code を呼び戻さない (§5.4 の既定 0 応答) ことを前提にする。この前提が崩れると、別の入口を読んで呼出元 VA を誤る。現状は影響しない。

### 6.2 stk 位置の不一致 (既存の挙動。本 PR では未修正)

- `ld_ms_call.S` の `ld_stub_common` は `leaq 212(%rsp)` で stk を渡す。実測 `stk_minus_entry=28` (entry rsp からの差)。MS x64 の第5引数は entry+0x28 (=40) にある。
- 影響: `MultiByteToWideChar`・`WideCharToMultiByte` の a4/a5 (`stk[0]`・`stk[1]`) が誤る。実測の spike で `WideCharToMultiByte` の a4 は `0x55844ec000000000` (ホスト値)。
- 既定の応答を変えるため、本 PR では直さない → 子 issue [LD-170] (boot 928/942 と sample:800 への影響を測る)。修正と測定は [`REPORT_APPENDIX_LD170.md`](REPORT_APPENDIX_LD170.md) (#3619)。修正後の boot は 892/942 (first_fail 149) に変わった (dst 書込みの経路の変化)。
- 本 PR の trace は entry+0x28 から直接読む (`wt_rec`)。その値は CreateWindowExW の第5〜12引数として整合 (x=y=w=h=0・hInstance=イメージ基底)。

### 6.3 既定の挙動の回帰 (spike: FLEngine 起動の KPI)

基準は PR が取り込んだ main `058984fa0`。この PR が `tools/liftdiff` に加えた差分は `git diff 058984fa0 2eba8b3e2 -- tools/liftdiff` の 3 ファイル (`rt/ld_ms_call.S`・`rt/ld_native.c`・`spike_cfi.py`) だけ。測定は fix run で行った (素材 fl-win64・work-liftdiff・work-m11。spike は各条件 2 回)。

| run | commit | 条件 |
|---|---|---|
| b1・b2 | `058984fa0` (基準。記録の分岐は無い) | 環境変数 `SPIKE_WINTRACE=0` |
| o1・o2 | `2eba8b3e2` (`tools/liftdiff` のコードは測定 commit `cfc0071d9` と同一) | `SPIKE_WINTRACE=0` (記録オフ) |
| n1・n2 | `2eba8b3e2` | 既定 (記録オン) |

| 項目 | 結果 (b・o・n の 6 run とも) |
|---|---|
| units_run / first_fail | 928/942・830 (同一) |
| CreateFruityInstance | segv rip_rva `0x4e0fab` (同一) |
| 呼出し import 数・戻り値 | 35 件。戻り値・関数名は全件一致 |

spike 出力 JSON の `calls_full` (35 件の関数名・戻り値・全引数) の比較:

| 比較 | 差のある呼出し | 差のある引数 | 内訳 |
|---|---|---|---|
| b1 vs b2 (基準同士) | 0 | 0 | 完全一致 |
| o1 vs o2 (記録オフ同士) | 0 | 0 | 完全一致 |
| n1 vs n2 (記録オン同士) | 0 | 0 | 完全一致 |
| b1 vs o1 (基準 vs 記録オフ) | 16 | 16 | stack 13・WideCharToMultiByte a4 1・GetLastError arg0 2 (下表) |
| o1 vs n1 (記録オフ vs 記録オン) | 18 | 19 | stack 13・使わない引数の残り値 6 |

基準 vs 記録オフ の 16 件 (値は `基準 → 記録オフ`):

| 関数 (引数番号) | 引数の種別 (API の仕様) | 呼出し | 基準 → 記録オフ |
|---|---|---|---|
| TlsGetValue (arg3・arg2 ×2 組) | 使わない (1 引数の関数) | 4 | `0x7fffffffb7a8` → `0x7fffffffb768` |
| GetClassInfoW (arg2) | 使う (出力先 WNDCLASS) | 1 | `0x7fffffffb858` → `0x7fffffffb818` |
| GetFileAttributesW (arg2) | 使わない (1 引数の関数) | 1 | `0x7fffffffa68c` → `0x7fffffffa64c` |
| FindFirstFileW (arg1) | 使う (WIN32_FIND_DATA) | 2 | `0x7fffffffa3d0` → `0x7fffffffa390` 他 1 件 |
| GetCurrentThreadId (arg2) | 使わない (0 引数の関数) | 1 | `0x7fffffffa57c` → `0x7fffffffa53c` |
| SetFilePointer (arg2) | 使う (lpDistanceToMoveHigh。NULL 可) | 4 | `0x7fffffffa35c`・`0x7fffffffa34c` (×3) → `…a31c`・`…a30c` |
| WideCharToMultiByte (arg4) | 使う (lpMultiByteStr。§6.2 の stk 位置の誤りで stk から読む) | 1 | `0x55845ec000000000` → `0x5555b8ba00000000` (ホスト stack の値) |
| GetLastError (arg0) | 使わない (0 引数の関数) | 2 | `0x1e336b0` → `0x70`・`0x24` |

- stack の 13 件はすべて基準より `0x40` 低い。rsp も同じ差 (`0x7fffffffa4a0` → `0x7fffffffa460`)。記録オフは基準と cwd が違い (環境変数の長さが違う)、stack 配置が動いたと推定 (確認はしていない)。同じ cwd 同士は完全一致。
- WideCharToMultiByte の a4 は使わない引数ではない。§6.2 の stk 位置の誤りで、ホスト stack 上の値を読んでいる。値が基準と違うのは run 環境の差 (推定)。
- 記録オン vs 記録オフ の 13 件の stack は、記録オフより一律 `0x50` 高い (オン側が低い)。記録オンでは環境変数 `LD_WINTRACE_OUT` が加わるため stack 配置が動いたと推定 (確認はしていない)。
- 使わない引数の残り値 6 件 (記録オン → 記録オフ): RegisterClassW (1 引数) arg1 `0xffffffffffffffff` → `0x380`・arg2 `0x78` → `0x4`、FindClose (1 引数) arg1 `0x0` → `0x580`・`0x0` → `0x6c0`、GetLastError (0 引数) arg0 `0x43` → `0x70`・`0x43` → `0x24`。使われない値なので戻り値には影響しない。

ネガティブコントロール: 記録オフ (o1・o2) の `spike_wintrace.txt` は 0 行、記録オン (n1・n2) は 9 行 (cfi 3 件 + boot 6 件)。

### 6.4 liftdiff e2e の回帰 (`bash liftdiff_e2e.sh --m11-only`・受入 3)

| 実行 | commit | 一致 / 不一致 / 実行不能 | 所要 | 結果 |
|---|---|---|---|---|
| 基準 | `01f1b7e51` (取り込み前の origin/main。`tools/liftdiff` は `42c6bcfdd` と同一: `git diff 42c6bcfdd 01f1b7e51 -- tools/liftdiff` は空) | 360 / 234 / 206 | 3 分 04 秒 | LIFTDIFF_E2E PASS (rc 0) |
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
| spike 2 回の差 (記録オン同士・`cfc0071d9` の 1 回目と 2 回目) | rsp/rbp/rsi/s1 など stack アドレス (0x10) のみ。rip・status・calls・窓の記録行は一致 |
| spike 実行時間 (real, 1 回目) | 18.4 s |
| e2e `bash liftdiff_e2e.sh --m11-only` 1 回目 | `LIFTDIFF_E2E PASS` (rc 0)・real 3m09.9s・sample:800 一致 361 / 不一致 233 / 実行不能 206 |
| e2e `bash liftdiff_e2e.sh --m11-only` 2 回目 | `LIFTDIFF_E2E PASS` (rc 0)・real 3m10.1s・sample:800 一致 360 / 不一致 234 / 実行不能 206 |
| e2e 内の `CHECK_INITUNITS` | PASS (2 回とも・hybrid `units_run=928/942 first_fail=830`) |
| e2e 内の UNIT18 の 3 項目 (`_UStrAsg`・`Move(409c80)`・`4123c0`) | 3 件 PASS (2 回とも) |

e2e は 2 run。一致 361/233 と 360/234 の差は §6.4 と同じく同一コードでの揺れで、既定の挙動の変化とは判定しない。`CreateWindowExW` の窓は戻り 0 の stub のため作られず、KPI (最初のウィンドウ・dispatch 数・通過 unit 数) は §6.5 と同じ。

### 6.8 fix の範囲 (コメントのみ・再測定なし)

測定 commit `cfc0071d9` の後、`rt/ld_ms_call.S` の 79 行の行末コメントだけを直した (`leaq 184(%rsp),%rax` の命令部分は変えていない)。

- `git diff cfc0071d9 HEAD -- tools/liftdiff/rt` の差分は、この 1 行のコメントの置換だけ。
- 同じパス名で `gcc -c -O1 -g` した変更前後の `ld_ms_call.S` の `.o` は `cmp` でバイト一致。
- `gcc -E -P` の結果から `#` 以降を除くと、変更前後で一致。

オブジェクトが同一なので、§6.3〜§6.7 の測定値は測定 commit のまま扱う (再測定は求めない)。
