# python 付録: PY-109 静的版 subinterp 12 check の headless Chrome 実行 (#2919)

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。ビルドと probe の検証のみ)。
親: #2858 (PY-98 の未達分を分割)。上流: `REPORT_APPENDIX_2858.md` §5-1 (smoke 版 PASS 3/3)・§5-3 (wasm64 の配線)。関連: #2918 (PY-108, MEMORY64 の heap 増加)。

## 結論

| # | 項目 | 判定 | 節 |
|---|---|---|---|
| 1 | 静的版 wasm32 (`flpy_static`) を headless Chrome で 12 check 実行 | **達成**。12/12 PASS。node 版 `static_subinterp_probe.mjs` と同じ 12 check 名・判定 (node 版も 12/12 PASS) | §2 |
| 2 | 静的版 Memory64 (`flpy_static64`、MEMORY64=1) | **11/12 PASS・FAIL 1**。FAIL は「150 回 (50×3) の作成/実行/破棄で wasm メモリが増えない」。33,554,432 → 48,365,568 B (+14,811,136 B)。2 回とも同じ値 | §2・§3 |
| 3 | 失敗 check の扱い | **未対応** (修正せず)。起票先: #2918 (open, PY-108「MEMORY64 subinterp heap 増加」)。#2918 の前提「MEMORY64=1 では増えない」は smoke 版の workload に限られると判明した (§3) | §3・§4 |

測定 commit (WORKFLOW §6 の定義: コード差分の最終 commit): `5e9a8b8e` (probe の追加)。本 REPORT は docs のみで、`git diff 5e9a8b8e HEAD -- tools/python ':(exclude)*.md'` の出力は 0 行 (本 commit 時点で確認)。全測定は `5e9a8b8e` のソースで build した dist による (dist は HEAD のソースで再リンクした。§1 の 7)。

環境: GitHub Actions runner (4 core、メモリ 15 GiB)、Google Chrome 155.0.8059.39 (UA `Chrome/155.0.0.0`、runner 同梱)、node v22.23.3、emcc 6.0.12 ([EMSDK]。素材 `toolchain-emsdk`)、CPython 3.12.1 (`Python-3.12.1.tgz` sha256 `d01ec6a3…97b2`)。素材 `fl-win64` は本 probe では使わない (dist だけを読む)。load は driver が記録した `os.loadavg()[0]` (1 分値) の前後。node 版は driver が無く load を記録していない。

## 1. 再ビルド (測定 commit のソース)

1. `Python-3.12.1.tgz` を取得し展開 (`tools/python/work/`、gitignore)。
2. native python: emsdk を PATH から外し `configure -C` と `make -j4`。1 分 29.6 秒。
3. wasm64 CPython: `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash build_cpython_wasm64.sh`。2 分 43.2 秒、rc 0。
4. `FLPY_MEMORY64=1 CPY_BUILD=$PWD/work/build-wasm64 STATIC_OUT=flpy_static64 bash build_flpy_static.sh`。6.7 秒。`flpy_static64.wasm` 6,377,060 B (PY-80 の測定時は 6,375,065 B)。
5. wasm32 CPython: `build_cpython_wasm.sh` の wasm32 段と同じ configure 引数と `emmake make python.js`。2 分 15.6 秒。`build_cpython_wasm.sh` 全体は使わなかった。末尾の `tools/legal/notices/record.mjs` が legal の記録を書き換えるため (本 PR の範囲外)。
6. `bash build_flpy_static.sh` (既定)。6.6 秒。`flpy_static.wasm` 5,970,629 B。
7. 4 と 6 は、最初は `8600bbce` 由来のソースでリンクしていた。`provider/fl_engine.c` が origin/main と異なっていたため、測定前に HEAD のソースで再リンクした。

## 2. probe の結果 (commit `5e9a8b8e`)

実行コマンド (`tools/python` で実行):

| 測定 | コマンド | 結果 | 所要 | load (1 分値、前→後) |
|---|---|---|---|---|
| node 版 wasm32 | `node tests/static_subinterp_probe.mjs` | `STATIC SUBINTERP OK`、rc 0 | 23.0 秒 (プロセス全体) | 未記録 |
| Chrome 版 wasm32 | `STATIC_WASM=flpy_static STATIC_MEM64=0 node tests/static_subinterp_browser.mjs` | `STATIC SUBINTERP OK`、12/12、rc 0 | 22.2 秒 (ページ内) | 1.21 → 1.23 |
| Chrome 版 wasm32 `--neg` | 同上 + `--neg` | `NEG-CONTROL DETECTED`、rc 1 (期待を 1 つ壊し、その check だけ FAIL) | 未計測 | 未記録 |
| Chrome 版 wasm64 (1 回目) | `node tests/static_subinterp_browser.mjs` (既定 `flpy_static64`、MEM64=1) | `STATIC SUBINTERP FAIL`、11/12、rc 2 | 25.7 秒 (ページ内) | 1.14 → 1.27 |
| Chrome 版 wasm64 (2 回目) | 同上 | `STATIC SUBINTERP FAIL`、11/12、rc 2 | 25.8 秒 (ページ内) | 1.27 → 1.21 |
| Chrome 版 wasm64 `--neg` | `node tests/static_subinterp_browser.mjs --neg` | rc 2 (FAIL)。neg は失敗が 1 件の時だけ DETECTED になるため、本 FAIL では DETECTED にならない | 未計測 | 未記録 |
| 既存 smoke (PY-98) wasm64 | `node tests/static64_browser_probe.mjs flpy_static64` | `STATIC64 PROBE OK`、rc 0。`result = str(1 + 1)` を 160 回。heap は全点 33,554,432 B | 4.2 秒 (ページ内) | 未記録 |

check 名は `tests/browser/static_subinterp.html` と `tests/static_subinterp_probe.mjs` の `check(` 定義 8 件 (ループ内の 3 系列を展開すると 12 件) の文字列が一致することを確認した。node 版の結果 (`failed: []`) から、node 版は 12 件すべて PASS。

| # | check 名 (`static_subinterp_probe.mjs` と同一) | node wasm32 | Chrome wasm32 | Chrome wasm64 |
|---|---|---|---|---|
| 1 | `isolated_own_gil: Py_NewInterpreterFromConfig → run → Py_EndInterpreter が成功し main が継続` | PASS | PASS | PASS |
| 2 | `isolated_shared_gil: Py_NewInterpreterFromConfig → run → Py_EndInterpreter が成功し main が継続` | PASS | PASS | PASS |
| 3 | `legacy: Py_NewInterpreterFromConfig → run → Py_EndInterpreter が成功し main が継続` | PASS | PASS | PASS |
| 4 | `isolated: FL 同梱スクリプトの stdlib 22 module を全て import` | PASS | PASS | PASS |
| 5 | `isolated: 拒否される builtin は {_elementtree,_lsprof,faulthandler,pyexpat} の 4/66 (全て 'does not support loading in subinterpreters')` | PASS | PASS | PASS |
| 6 | `legacy: 66 本全て import 可 (拒否 0)` | PASS | PASS | PASS |
| 7 | `isolated: main の __main__ 変数と sys.modules は見えない` | PASS | PASS | PASS |
| 8 | `isolated_own_gil: サブインタプリタで _flhost が import でき、provider の channelCount が main と一致する` | PASS | PASS | PASS |
| 9 | `isolated_shared_gil: サブインタプリタで _flhost が import でき、provider の channelCount が main と一致する` | PASS | PASS | PASS |
| 10 | `legacy: サブインタプリタで _flhost が import でき、provider の channelCount が main と一致する` | PASS | PASS | PASS |
| 11 | `サブインタプリタ内の例外 → ok:false stage:exec + traceback、main は継続` | PASS | PASS | PASS |
| 12 | `150 回 (50×3) の作成/実行/破棄が 3 系列 (isolated json+re / isolated+_flhost / legacy+_flhost) とも全て成功し、各系列で wasm メモリが増えない` | PASS | PASS | **FAIL** (下記) |

作成/実行/破棄の時間 (1 インタプリタあたりの ms。50 回の平均を 3 区間の範囲。wasm32 は 1 回、wasm64 は 2 回の範囲):

| 系列 | wasm32 Chrome | wasm64 Chrome |
|---|---|---|
| isolated json+re | 31.6〜37.0 | 37.7〜44.4 |
| isolated+_flhost | 31.9〜35.5 | 36.9〜41.0 |
| legacy+_flhost | 31.3〜32.1 | 36.7〜37.1 |

wasm メモリ (`HEAPU8.length`): wasm32 は 3 系列とも 33,554,432 → 33,554,432 B (1 回)。wasm64 は 3 系列とも 33,554,432 → 48,365,568 B (+14,811,136 B。2 回とも)。

## 3. 失敗 check (#12) の再現と判定

- 再現: `cd tools/python && node tests/static_subinterp_browser.mjs` (既定 `flpy_static64`、MEM64=1)。
- 判定: check 12 が `false`。他の 11 件は PASS。失敗は wasm 線形メモリの増加で、インタプリタの実行結果 (`ok`・`result`) の誤りではない。
- 同じ条件での対照: 同一 commit・同一 probe の wasm32 (`flpy_static`) は増えない (3 系列とも 33,554,432 B のまま)。
- 増加の形 (同一インスタンス、`import json, re` のみの反復、20 回ごとに記録。2 回とも同じ): 0〜100 回は 33,554,432 B。120 回で 40,304,640 B。140 回は同じ。160 回で 48,365,568 B。
- smoke 版 (`result = str(1 + 1)`、同一インスタンス 160 回) は、wasm64 でも全点 33,554,432 B。増加は import を含む workload でだけ観測された。
- 3 系列 (isolated・isolated+_flhost・legacy+_flhost) で増加量が同じ (+14,811,136 B) ため、この増加は隔離モード・_flhost の有無に依らない (単一観測)。
- **未切り分け**: 増えた分が解放されない確保 (リーク) か、allocator の高水位 (断片化) か。mallinfo 等の計測は未実施。wasm32 は増えないため、Memory64 版 (table64 の lowering) に固有の挙動と見られる。

## 4. 変更点

- `tools/python/tests/browser/static_subinterp.html`: node 版 `static_subinterp_probe.mjs` の 12 check を、headless Chrome のページで実行する (query: `static`・`mem64`・`neg`)。
- `tools/python/tests/static_subinterp_browser.mjs`: `serve.mjs` と Chrome (DevTools) で上記ページを開く driver。`STATIC_WASM` (既定 `flpy_static64`)・`STATIC_MEM64` (既定 1)・`--neg`。終了コードは node 版と同じ (0 OK / 2 FAIL / 1 NEG-CONTROL DETECTED)。
- 既存の `tests/static64_browser_probe.mjs` (PY-98 smoke) は変更していない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| MEMORY64=1 の静的版で、`import json, re` を含む subinterp を反復すると線形メモリが増える (120 回目から、160 回で +14.8 MB)。増加の出所 (リーク / 断片化) は未切り分け。#2918 の前提「MEMORY64=1 では増えない」は smoke 版 (`str(1+1)`) の workload に限られる | 長時間の反復実行で wasm メモリが増え、上限に近づく可能性 | #2918 (既存・PY-108) |

node 22 は table64 (`flpy_static64`) を validate できないため、wasm64 の検査は Chrome でのみ行う (`REPORT_PY80.md` §3 の既知事項。本 run では node 版の wasm64 は実行していない)。

## 6. 製品 KPI

起動・GUI に関わらない変更のため、製品 KPI は書かない。
