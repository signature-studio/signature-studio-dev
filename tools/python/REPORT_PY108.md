# python 付録: PY-108 MEMORY64=2 の静的版と subinterp 反復の heap 増加 (#2918)

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。ビルドと probe の検証のみ)。
親: #2858 (PY-98 の未達分を分割)。関連: `REPORT_PY109.md` §3 (MEMORY64=1 で 150 回の増加を最初に観測・#2919)。

## 結論

| # | 項目 | 判定 | 節 |
|---|---|---|---|
| 1 | MEMORY64=2 の libpython と静的版 `flpy_static64l` を作る | **達成**。ビルド rc 0。wasm 6,555,715 B。validate true・ptr は i64 | §1 |
| 2 | smoke (`str(1+1)`) の 160 回 subinterp の heap | **達成**。L2 は 33,554,432 B のまま (L1・wasm32 も同じ) | §2 |
| 3 | import を含む subinterp の反復で増加を再現 | **再現**。L2 で json+re 160 回 +14,811,136 B (L1 と全点一致) | §3 |
| 4 | 増加の出所の切り分け | **部分**。切り分けた範囲: MEMORY64 固有ではない・import 無しでも起きる・Python 側の循環参照の回収では消えない。未切り分け: リークか断片化か | §4 |
| 5 | MEMORY64=1 との比較表 | **達成**。wasm32 / L1 / L2 を同じ commit で並べた | §5 |

**訂正**: `REPORT_PY109.md` §3 の「wasm32 は増えない」「Memory64 版に固有」は 160 回の窓での結果であり、400 回では wasm32 も増える。
増加は MEMORY64 に固有ではない (§4・§5)。PY-109 の 12 check の判定 (wasm32 12/12、MEMORY64 11/12) は L2 でも同じだった (§2)。

測定 commit (コードを変えた最後の commit): `627191db7` (probe の追加)。ビルド元は `bb0f61949` (origin/main) と同じソース。
`git diff 627191db7 HEAD -- tools/python ':(exclude)*.md'` は 0 行 (本 REPORT の commit は .md のみ)。

環境: GitHub Actions runner (nproc 4)、Chrome 154.0.8037.97 (headless、UA `HeadlessChrome/154.0.0.0`)、node v22.23.3、emcc 6.0.12 (`EMSDK_ENV=<[EMSDK] の emsdk_env.sh>`)、CPython 3.12.1 (`Python-3.12.1.tgz` sha256 `d01ec6a3…97b2`)。素材 `fl-win64` は使わない (dist だけを読む)。load は `uptime` の 1 分値で 1.5〜2.9。

## 1. ビルド (commit `627191db7` のソース)

1. native build-python: `configure -C` と `make` 、1 分 21.8 秒 (`work/build-native`)。
2. MEMORY64=2 libpython: `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> MEMORY64_LEVEL=2 bash build_cpython_wasm64.sh`。2 分 10.1 秒、rc 0。make.log の `-sMEMORY64=` 行は 215 行 (`work/build-wasm64l`)。
3. `FLPY_MEMORY64=2 CPY_BUILD=$PWD/work/build-wasm64l STATIC_OUT=flpy_static64l bash build_flpy_static.sh`。5.3 秒。`dist/flpy_static64l.wasm` 6,555,715 B。build_flpy_static.sh は変更していない (`FLPY_MEMORY64` の値を `-sMEMORY64` に渡す既存の分岐で足りた)。
4. 比較用 L1: `bash build_cpython_wasm64.sh` (既定 `MEMORY64_LEVEL=1`) 1 分 53.0 秒、`FLPY_MEMORY64=1 ... STATIC_OUT=flpy_static64` 。`flpy_static64.wasm` 6,382,495 B。
5. 比較用 wasm32: `build_cpython_wasm.sh` の wasm32 段と同じ configure 引数と `emmake make python.js` (1 分 56.6 秒)。末尾の `tools/legal/notices/record.mjs` は本 PR の範囲外のため実行せず。`flpy_static.wasm` 5,975,953 B。

## 2. smoke (`static64_browser_probe.mjs`、`str(1+1)` を 160 回)

| wasm | ポインタ | heap 0 → 160 回 (B) | 結果 |
|---|---|---|---|
| `flpy_static` (wasm32) | i32 | 33,554,432 → 33,554,432 | `STATIC64 PROBE OK` |
| `flpy_static64` (L1) | i64 | 33,554,432 → 33,554,432 | `STATIC64 PROBE OK` |
| `flpy_static64l` (L2) | i64 | 33,554,432 → 33,554,432 | `STATIC64 PROBE OK` (validate true・init_rc 0・run_stdout "2") |

`static_subinterp_browser.mjs` (12 check) を L2 で実行: `STATIC_WASM=flpy_static64l STATIC_MEM64=2 node tests/static_subinterp_browser.mjs` → 11/12 PASS、rc 2。失敗は「150 回で wasm メモリが増えない」の 1 件のみ (L1 の PY-109 §2 と同じ)。

## 3. subinterp 反復 (`static64_growth_probe.mjs`、mode 0 = isolated)

heap は `HEAPU8.buffer.byteLength`。20 回ごとに記録。

**`import json, re` + `json.dumps([1])` を 400 回 (3 回の再現、3 回とも系列が同一)**

| wasm | 33,554,432 のまま | 増えた後の値 (B) と初めて増えた回 | 400 回の値 (B) |
|---|---|---|---|
| `flpy_static` (wasm32) | 0〜200 | 40,304,640 (220) / 48,365,568 (280) / 58,064,896 (360) | 58,064,896 |
| `flpy_static64` (L1) | 0〜100 | 40,304,640 (120) / 48,365,568 (160) / 58,064,896 (200) / 69,730,304 (260) / 83,689,472 (340) | 83,689,472 |
| `flpy_static64l` (L2) | 0〜100 | L1 と同じ系列 | 83,689,472 |

**`result = "1"` (import 無し) を 400 回 (各 1 回)**

| wasm | 400 回の値 (B) | 増えた回 |
|---|---|---|
| `flpy_static` | 40,304,640 | 400 付近 |
| `flpy_static64` | 58,064,896 | 220 (40,304,640)・280 (48,365,568)・380 (58,064,896) |
| `flpy_static64l` | 58,064,896 | L1 と同じ系列 |

増加後の値はすべて `33,554,432 × 1.2^k` を 64 KiB ページ単位に切り上げた値に一致する (615・738・886・1064・1277 ページ)。Emscripten の幾何的な伸長 (×1.2) の列であり、heap は高水位で伸びて縮まない。

## 4. 増加の出所の切り分け

確かめたこと (commit `627191db7`):

1. **MEMORY64 固有ではない**。wasm32 も json+re 400 回で +24,510,464 B (33.5 → 58.1 MB) 増える。MEMORY64=1 と =2 は全点一致 (level の差は影響しない)。
2. **import 無しでも起きる**。`result = "1"` でも L1・L2 は 400 回で 58.1 MB、wasm32 は 40.3 MB。増加は subinterp の作成・破棄に由来し、import はそれを**早める**だけ (L1/L2 の初回増加 220 回 → json+re では 120 回)。PY-109 §3 の「import を含む workload でだけ観測」は 160 回の窓の結果で、この点も訂正する。
3. **Python 側の循環参照の回収では消えない**。サブインタプリタ内で `gc.collect()` を呼んでも増加は同じ (`import enum, gc` + collect: 160 回で 40,304,640、`import functools, gc` + collect: 40,304,640、`import json, re, gc` + collect: 48,365,568。gc 無しと同じ)。
4. **モジュールごとの差**。160 回の窓 (L2): `import _sre` は増えず、`import enum`・`import functools` は +6,750,208 B、`import re`・`import json`・`import json, re` は +14,811,136 B。
5. **400 回まで増え続ける** (段階的に増え、段と段の間は平ら)。段の間隔 (40・40・60・80 回) から、1 回あたりの残存量は推定 170〜240 KB/回 (粗い見積もり。20 回刻みの記録による)。

未切り分け (本 REPORT の範囲外):

- **リーク (解放されない確保) か断片化か** は区別していない。linear memory の使用量を取る手段 (`mallinfo` 等) が wasm 側に export されていないため。推定 170〜240 KB/回の残存は、リークを示唆するが断定はできない。
- Py_EndInterpreter 後に残るインタプリタ状態 (Python 側の保持) を直接見ていない。
- `mode 2` (legacy) と `_flhost` の有無の 400 回測定は未実施。PY-109 の 160 回では 3 系列とも同じ増加量だった。

## 5. MEMORY64=1 との比較表 (同じ commit・同じ probe)

各セルは heap の最終値。括弧内は 0 からの増分 (B)。

| 条件 | wasm32 | L1 (`flpy_static64`) | L2 (`flpy_static64l`) |
|---|---|---|---|
| smoke `str(1+1)` 160 回 | 33,554,432 (0) | 33,554,432 (0) | 33,554,432 (0) |
| `import enum` 160 回 | 33,554,432 (0) | 40,304,640 (+6,750,208) | 40,304,640 (+6,750,208) |
| `import json, re` 160 回 | 33,554,432 (0) | 48,365,568 (+14,811,136) | 48,365,568 (+14,811,136) |
| `import json, re` 400 回 | 58,064,896 (+24,510,464) | 83,689,472 (+50,135,040) | 83,689,472 (+50,135,040) |
| import 無し 160 回 | 33,554,432 (0) | 33,554,432 (0) | 33,554,432 (0) |
| import 無し 400 回 | 40,304,640 (+6,750,208) | 58,064,896 (+24,510,464) | 58,064,896 (+24,510,464) |

判定: smoke (PY-98 の 160 回) は 3 系列とも増えない。ただし import 無しの増加は 220 回以降に始まるため、160 回の smoke 結果は長時間の安全を示さない。

## 6. 再現コマンド (`tools/python` で実行)

```
EMSDK_ENV=<[EMSDK] の emsdk_env.sh> MEMORY64_LEVEL=2 bash build_cpython_wasm64.sh     # 前提: work/build-native/python
FLPY_MEMORY64=2 CPY_BUILD=$PWD/work/build-wasm64l STATIC_OUT=flpy_static64l bash build_flpy_static.sh
node tests/static64_browser_probe.mjs flpy_static64l                                  # smoke 160 回
node tests/static64_growth_probe.mjs flpy_static64l 0 400 "import json, re
result = json.dumps([1])"                                                             # 反復 400 回
node tests/static64_growth_probe.mjs flpy_static64l 0 400 "result = '1'"              # import 無し
```

probe の中身: `tests/browser/static64_growth.mjs` (ページ) と `tests/static64_growth_probe.mjs` (driver)。URL 引数 `mode`・`n`・`code` で Python コードを差し替える。`every` 既定は 20。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| リーク (解放されない確保) と断片化の区別。wasm 側で `mallinfo` 等の計測が無い | 長時間の反復で線形メモリが増え続ける。対策 (subinterp の再利用・破棄の見直し) は性質が決まってから | PM 判断 (親 #2858 の配下。新規子の要否は PM) |
| `mode 2` (legacy) と `_flhost` 有無の 400 回測定 | 増加の条件の網羅が未完 | PM 判断 (本 PR の範囲外) |
| wasm32 でも 400 回で増える件 (`REPORT_PY109.md` §3 の記述は 160 回の窓の結果) | subinterp を多数回作る運用は wasm32 でも上限に当たり得る | 本 PR で `REPORT_PY109.md` §3 に訂正を入れた。対策の起票は PM 判断 |

## 8. 製品 KPI

起動・GUI に関わらない変更のため、製品 KPI は書かない (本 PR は probe と REPORT のみ)。
