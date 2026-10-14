# liftdiff REPORT 付録: LD-83 (#2192) wasm 側の site trace (IR の conditional br・import call) と native 1801c5e84 の je・HeapFree の対応

親 issue #1907 (LD-68)。前提は `REPORT_APPENDIX_LD68.md` §4・§5、`REPORT_APPENDIX_LD57.md` §3、`REPORT_APPENDIX_LD67.md` (計装の方式)。

既知類型との関係: 該当なし (本付録の対象は IR への観測 store の計装で、lift 出力の意味誤りを指す `docs/DEFECTS.md` の D1a〜D23 のいずれにも当たらない)。

## 修正 (レビュー round 2 への対応)

- 修正 commit `ed712942` (測定 commit):
  - blocking 2: `irtool.py` で、BLK_RE に一致しない block 境界 (`; <label>:N`・`dec_label_pc_<VA>.<suffix>:`) から次の `dec_label_pc_` までの site を記録しない。VA と ord を解除し、件数を `sites skipped` に数える。BLK_RE (LD-64) は変えていない。
  - blocking 3: `decode_sites.py` の ord 判定を、呼び出し先の block 記録を挟める形にした。site の VA (下位 32 bit) で戻り先を解決し、戻り先より上の block は呼び出し先として閉じる。B の VA (33 bit) と site の VA の桁を揃える。
  - minor b: `build_wasm.py` で `site_trace` は `block_trace` 必須 (無ければ終了)。
- 追加 commit `21194fc0` (テストのみ): 呼び出し先が 2 site を持つ正例。
- blocking 3 の前提: ord 連番は「記録の欠落」の検査として使えない。呼び出し先の block 記録が戻りの印無しで挟まるため。今の検査は VA による戻り先の解決に依る。同じ VA の再帰呼出しでは戻り先を誤りうる (§6)。
- 単体テスト (`python3 tools/liftdiff/tests/test_irtool_sites.py`): 11 件 PASS (`21194fc0`)。ネガティブコントロール: 旧版 (`irtool.py`・`decode_sites.py` とも `a14de29c`) に同じテストを当てると 3 件 FAIL (境界の skip・呼び出し先の正例・VA 未解決の NG)。

## 結論

- 受入条件 1 (方式の決定と実装) は**部分達成**。方式は「IR 側の site 記録」: block 内の conditional br と import call の直前に volatile store を入れ、block VA・種別・block 内の順番・br の条件値を記録する。
  全命令の VA は RetDec IR に無い (`tools/ott/work/ott.ll` に命令単位の VA 注記は無く、`dec_label_pc_` は block 先頭の 1943 件のみ)。命令単位の完全な trace は未達で、子 #2801 (LD-131) に切り出す。
- 既定 build との差 0: `results/ld67/compare_blk.py` の 12 case で `cases=12 diff=0` (測定 commit `ed712942`・2 回)。block 件数は LD-67 と一致 (vm0 の 27・287・42・304)。
- 境界の修正 (blocking 2) で、`ott.ll` の `; <label>:N` と `.threadK` 形式の block の site 21 件は記録されなくなった (前版の 22 件のうち 1 件 (`1c5e84` vm0 の `C801c2173.1`) など、VA の帰属を誤っていた site)。
- 受入条件 2 (1c0b6f・1c0b82 の wasm 側の位置) は **site 単位で対応付けた**。vm0 の `1c0b6c` の br は 5 回とも native の `je` (1c0b6f) の成立・不成立と一致し、HeapFree の call site は 1 回で native (vm0) の 1 回と一致する (§4)。
- u16 は、前版 (`a14de29c`) では `1c0b71` の HeapFree で shim の trap により止まっていた。main の shim 修正 `a4a620a9` (#2802・PR #2846) を取り込んだ後は trap せず、block 列が最後まで取れる。native (u16) と同じ 5 回の HeapFree を wasm 側でも記録する (§4・§5)。
- 残り 5 関数 (受入の範囲外) は #2193 (LD-84)。

## 1. 測定条件

- 測定 commit: `ed712942` (`fix(liftdiff): skip sites after non-dec_label block boundaries; resolve callee returns in site ord check (Refs #2192)`。コード差分の最終 commit)。後続の `21194fc0` はテストのみ。
- 検証 HEAD の main 取り込み: `83e7bde5` (main `88b0f1c3` を merge。shim の `a4a620a9` (#2802) を含む)。main 取り込みの後で測定し直した (前版の `a14de29c` の値とは shim が違う)。
- 測定 runner: `uptime` 20:10:22 (load average 0.05 / 0.20 / 0.13)。所要時間は run ごとに記録していない (ログ `work/ld83/run_*.log` に出力のみ)。
- 素材: `work-m6-ott` (`tools/ott/work/ott.ll`・`tools/m6/work`・`tools/m8/work`・`tools/m9/work`・`tools/m10/work`)・`work-liftdiff` (`tools/liftdiff/work/`)・`analysis-ott-binaries` (`$HOME/analysis/plugins/ott/binaries`。`PLUGINS_DIR=$HOME/analysis/plugins`)・emcc は既存の `/opt/emsdk`。`toolchain-emsdk` は展開していない。
- build: `python3 ldlib/build_wasm.py targets/ott_old_site.json --force` (rc 0・`sig_mismatch` 0・`undefined` 0・stderr `[irtool] sites skipped (block without dec_label_pc_ VA): 21`)。既定版は `targets/ott_old.json --force` (rc 0・`sig_mismatch` 0・`undefined` 0)。
- run: `python3 liftdiff.py run targets/ott_old_site.json --fn 0x1801ab1d0,0x1801ab258,0x1801c5e84,0x1801c621c,0x1801c682c,0x1801c69cc --pattern vm0,u16 --nobuild --notrace --json <out>` (既定版は `targets/ott_old.json` で同じ引数)。r1・r2 の 2 回。
- 比較: `python3 results/ld67/compare_blk.py work/ld83/head_def_r<k>.json work/ld83/head_site_r<k>.json` (`k`=1,2)。両方 `cases=12 diff=0`。site JSON と既定 JSON は r1 と r2 でバイト一致 (`cmp`)。
- 内訳: `python3 results/ld83/decode_sites.py work/ld83/head_site_r<k>.json --seq 15` (`--seq` の列は §4)。ord 欄が全 case `ok`。
- 単体テスト: `python3 tools/liftdiff/tests/test_irtool_sites.py` → 11 件 OK。

## 2. 方式 (site trace)

`ldlib/irtool.py` の `instrument(..., sites=True)` (target の `site_trace: true`・`targets/ott_old_site.json`)。block 入口の記録 (LD-64 の `ld_blk_arr`) に、次の 2 種を追加で同じ配列へ volatile store する。値は 64 bit で、wasm 側の `ld_blk` の出力 (`blk` の `0x..` 列) にそのまま入る。

| 記録点 | IR 上の位置 | 値 |
|---|---|---|
| block 入口 (LD-64) | `dec_label_pc_<VA>:` の直後 | VA (33 bit) |
| conditional br | `br i1 %c, label ...` の直前 | `1<<62 \| 1<<56 \| ord<<40 \| cond<<39 \| VA & 0xffffffff` |
| import call | `call ... @<declare 名>` (`SKIP_DECL` 以外) の直前 | `1<<62 \| 2<<56 \| ord<<40 \| VA & 0xffffffff` |

- `ord` は同じ block 内の site の通し番号 (0 始まり。block 入口で 0 に戻る)。`cond` は br の条件の真偽 (1 = 真)。
- VA は下位 32 bit だけを残す (block 入口の 33 bit VA と桁が違う。例: `1801c5e84` の block の site は `801c5e84`)。
- 境界: `dec_label_pc_<VA>:` (BLK_RE) 以外の block 境界 (`; <label>:N`・`dec_label_pc_<VA>.<suffix>:`) では B 記録が無い。そこから次の `dec_label_pc_` までの site は記録せず、`sites skipped` に数える (修正 `ed712942`)。
- 方式の判断: RetDec 由来の IR に命令の VA が無いため、命令単位の VA を残すには RetDec 側の変更が要る (D5 の RetDec 路線で新規作業になる)。その代わり、native の `je` は IR の conditional br、native の `call [IAT]` は IR の import call に 1 対 1 で対応する (構造上の対応)。
- vm0 の cond と je の向き: ott.ll で確認済み。`dec_label_pc_1801c0b6c:` の `%0 = icmp eq i64 %arg1, 0` → `br i1 %0, label %dec_label_pc_1801c0ba8, label %dec_label_pc_1801c0b71`。true 側 (cond=1) は `rcx == 0` で、native の `je` (1c0ba8 への分岐) の成立と同じ条件になる。

## 3. 測定結果 (測定 commit `ed712942`・main 取り込み後)

| 関数 | pattern | 既定 outcome | 計装 outcome | 判定 | blocks | J | C | sites | 計 | ord |
|---|---|---|---|---|---|---|---|---|---|---|
| 1ab1d0 | vm0 / u16 | equal | equal | SAME | 0 | 0 | 0 | 0 | 0 | ok |
| 1ab258 | vm0 / u16 | equal | equal | SAME | 0 | 0 | 0 | 0 | 0 | ok |
| 1c5e84 | vm0 | diff | diff | SAME | 27 | 16 | 5 | 21 | 48 | ok |
| 1c5e84 | u16 | diff | diff | SAME | 67 | 36 | 25 | 61 | 128 | ok |
| 1c621c | vm0 | diff | diff | SAME | 287 | 183 | 5 | 188 | 475 | ok |
| 1c621c | u16 | diff | diff | SAME | 337 | 208 | 30 | 238 | 575 | ok |
| 1c682c | vm0 | diff | diff | SAME | 42 | 33 | 5 | 38 | 80 | ok |
| 1c682c | u16 | diff | diff | SAME | 43 | 34 | 5 | 39 | 82 | ok |
| 1c69cc | vm0 | diff | diff | SAME | 304 | 192 | 10 | 202 | 506 | ok |
| 1c69cc | u16 | diff | diff | SAME | 354 | 217 | 35 | 252 | 606 | ok |

`cases=12 diff=0`。blocks の vm0 の列 (27・287・42・304) と 1c682c u16 (43) は LD-67 の `blk` 件数 (27・4・287・6・42・43・304・10) と一致する。LD-67 の u16 の残り (4・6・10) は shim の trap で止まった値で、§3 の (c) のとおり変わった。`sites skipped`: 21 (`ott_old_site` の build の stderr)。

- 前版 (`a14de29c`) からの変化: (a) site 数: 1c5e84 vm0 22→21、1c621c vm0 189→188、1c682c vm0 39→38 (u16 40→39)、1c69cc vm0 204→202。境界の 1 件 (`C801c2173.1`・`; <label>:25` の `SetLastError`) を VA 付きで数えていたため。(b) ord: 前版は 5 case が NG。境界の修正だけでは 5 case とも NG のまま (レビュワーの試験・本 run では未再現)。呼び出し先の戻りを扱う ord 判定で 5 case とも ok になった。(c) u16: outcome が `wasm_trap` → `diff`、blocks が 4・6・10 → 67・337・354 (shim の trap が main の `a4a620a9` で消えたため。既定版も同じ outcome で、計装の差ではない)。

ord 判定の制約: 呼び出し先の block が同じ VA (再帰呼出し) の場合は、戻り先を誤って解決しうる。実データ 12 case では全て ok (再帰の有無は未確認)。

## 4. 1c0b6f (je) と 1c0b82 (HeapFree) の wasm 側の位置 (1801c5e84)

記号 (`decode_sites.py` の出力のまま): `B<VA>` = block 入口、`J<VA>.<ord>=<cond>` = site の br、`C<VA>.<ord>` = site の import call。VA は 33 bit の 16 進 (site は下位 32 bit)。

- **vm0** (全 48 件のうち `1c0b6c` の br): cond = `[0, 1, 1, 1, 1]`。native (LD-57 §3) の `rcx` は `[1720f3000 (je 不成立), 0, 0, 0, 0]` で、`je` の成立 (`rcx=0`) は cond=1 と一致する。
- **vm0 の HeapFree**: `1c0b71` の call site (`C801c0b71.0`) は 1 回。native (vm0) の `KERNEL32!HeapFree` も 1 回。直後の `J801c0b71.1=0` で HeapFree の戻りは偽 (`1c0b8c` へ)。
- 先頭の列 (vm0): `B1801c5e84 J801c5e84.0=0 B1801c5eb8 B1801c0b6c J801c0b6c.0=0 B1801c0b71 C801c0b71.0 J801c0b71.1=0 B1801c0b8c B1801bafb0 B1801c20c8 C801c20c8.0 J801c20c8.1=1 B1801c2109 B1801c3dc8`
- **u16**: `1c0b6c` の br は `[0, 0, 0, 0, 0]` (cond=0・`je` 不成立)。native (u16) の `rcx` は 1 回目 `1400000001`、2 回目以降は非ゼロ (LD-57 §3・§5 の記載) で、`je` は不成立。`C801c0b71.0` (HeapFree) は **5 回** で、native (u16) の HeapFree 5 回と回数が一致する。
  - site は値を持たないため、wasm 側が HeapFree へ渡した値は記録していない。

## 5. u16 の trap (前版で確認・main の修正で解消)

- 前版 (`a14de29c`) の trap 文字列: `memory access out of bounds @ ld_wasm.wasm.block_ok < ld_wasm.wasm.HeapFree < ld_wasm.wasm.function_1801c0b6c`。`tools/shim/src/heap.c` の `block_ok(user)` は範囲外のポインタを読んでいた。
- main の `a4a620a9` (`fix(shim): reject out-of-range pointers before reading block header (#2802)`) で、範囲外ポインタは header を読む前に弾かれる。#2802 は PR #2846 で閉じられた (LD-132)。`83e7bde5` の測定では trap は出ず、u16 の block 列が最後まで取れる (§3・§4)。
- 本付録の計装の変更ではない (既定版も同じ outcome)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 命令単位の完全な trace (RetDec IR に命令の VA が無い。方式は RetDec 側の変更か x64c の別経路かの PM 判断が要る) | site 単位でしか native 命令と対応しない。受入 1 の残り | #2801 (LD-131) |
| `dec_label_pc_` 以外の block 境界 (`; <label>:N`・`.<suffix>`) の site は記録しない (`ott_old_site` で 21 件・VA 不明) | その block の site は trace に現れない。site 数は `sites skipped` で確認できる | PM 判断 (未起票) |
| ord 判定の再帰呼出しでの解決誤り (同じ VA の block が積まれる場合) | 実データ 12 case は ok。再帰の有無は未確認 | PM 判断 (未起票) |
| 残り 5 関数の native 対応 | 受入の範囲外 | #2193 (LD-84) |

## 7. 測定 commit と差分

- 測定 commit: `ed712942` (§3・§4 の値)。後続の `21194fc0` はテストのみで、計装・decode・build は変えていない。
- `git diff ed712942 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/targets tools/liftdiff/results tools/shim tools/ott/rt tools/m6` の出力は 0 行 (REPORT の更新 commit は範囲の外)。
- 前版からの修正の差分: `git diff a14de29c ed712942 -- tools/liftdiff/ldlib tools/liftdiff/results` (`irtool.py`・`build_wasm.py`・`decode_sites.py`)。
