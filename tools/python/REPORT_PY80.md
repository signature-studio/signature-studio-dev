# python 付録: PY-80 静的版のサブインタプリタ・Memory64・`_PyInterpreterState_GetRefTotal` の検証 (#2633)

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。PE は束縛 slot の参照走査と束縛関数の逆アセのみ)。
親: #83 (PY-2)。`REPORT_PY2.md` §7d・§7e・§7f の未解決を移管 (旧 #76 の T6)。

## 結論

| # | 項目 | 判定 | 節 |
|---|---|---|---|
| 1 | サブインタプリタ (静的版 wasm32) | **達成**。12/12 PASS | §1 |
| 2 | pthread + GIL | **未実施**。子 #2856 (PY-97) に分割 | §4 |
| 3 | Memory64 | **部分**。`MEMORY64=1` はリンクまで成功、node 22.23 では validate 不可。`MEMORY64=2` は実行でき 11/12 PASS (heap 増加 1 件 FAIL)。実行検証は子 #2858 (PY-98) | §3 |
| 4 | `_PyInterpreterState_GetRefTotal` | **FL PE は呼んでいない**。参照は束縛時の store 1 件のみ。束縛失敗は無言 | §2 |

測定 commit: `7e34fa2b` (コードを変えた最後の commit。以降は本節を含む文書のみ)。`git diff 7e34fa2b HEAD -- tools/python ':(exclude)*.md'` の出力は 0 行。`7e34fa2b` は、それより前の commit `37164f82` (同じ測定を実施) から、`build_cpython_wasm64.sh` の emsdk の指定だけを変えたもの (`[EMSDK]` の lint 対応)。測定は 7e34fa2b で再ビルドし直して行った。

環境: GitHub Actions runner (4 core)、node v22.23.3、emcc 6.0.12 ([EMSDK])。load は各 run 直前の `/proc/loadavg` 1 分値。

## 0. 素材と再ビルド (測定 commit で実行)

- 素材 fl-win64 ([WIN64]) の `extracted/` を `tar --zstd -xf ... --wildcards 'extracted/*'` で `$RUNNER_TEMP/fl-win64/extracted` に展開 (4.7 秒)。
- `bash build_cpython_wasm.sh` (wasm32): 3 分 59.8 秒、rc 0。
- `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash build_cpython_wasm64.sh` (`MEMORY64_LEVEL=1` 既定。`--host=wasm64-unknown-emscripten` で configure が `-sMEMORY64=1` を CFLAGS / LDFLAGS に付与): 2 分 39 秒、rc 0。
- `MEMORY64_LEVEL=2 EMSDK_ENV=... bash build_cpython_wasm64.sh` (`CFLAGS/LDFLAGS=-sMEMORY64=2`): 2 分 18 秒、rc 0。
- `FL_WIN64_DIR=... bash build_flpy_static.sh` (wasm32): `dist/flpy_static.wasm` 5,969,111 B。
- `FLPY_MEMORY64=1 CPY_BUILD=$PWD/work/build-wasm64 STATIC_OUT=flpy_static64 bash build_flpy_static.sh`: 6,375,065 B。
- `FLPY_MEMORY64=2 CPY_BUILD=$PWD/work/build-wasm64l STATIC_OUT=flpy_static64l bash build_flpy_static.sh`: 6,548,115 B。
- 3 リンクとも rc 0。`emcc` は `MEMORY64 is deprecated` の警告を出す (`-m64` / `--target=wasm64` を推奨)。

## 1. サブインタプリタ (静的版) — 達成

`node tests/static_subinterp_probe.mjs` (新規)。SAB 版 `tests/subinterp_probe.mjs` (`REPORT.md` §11・`REPORT_PY12.md`) と同じ観点。違い: `_flhost` は JS コールバックではなく静的版 provider (`channels.channelCount`) に直結するため、サブ内の `_flhost.call` が main と同じ値 (3) を返すことを検査する。

| 検査 | 結果 (測定 commit `7e34fa2b`) |
|---|---|
| 3 構成 (isolated OWN_GIL / isolated SHARED_GIL / legacy) で作成→実行→破棄、main 継続 | 3/3 PASS |
| FL 同梱 stdlib 22 module を isolated で import | PASS |
| builtin 66 本: isolated で拒否は 4 本 (`_elementtree _lsprof faulthandler pyexpat`。SAB 版と同一集合)、legacy は 0 本 | PASS |
| isolated は main の `__main__`・`sys.modules` を見ない | PASS |
| サブ内 `_flhost.call` (provider) が main と一致 (3 構成) | PASS |
| サブ内の例外は ok:false / stage:exec で報告され、main は継続 | PASS |
| 150 回 (50×3) の作成/実行/破棄の 3 系列で wasm メモリが増えない | PASS |
| **合計** | **12/12 PASS** (`STATIC SUBINTERP OK`、rc 0) |

- 所要 (wall): run 1 21.96 秒 (load 0.88)、run 2 22.13 秒 (load 0.84)。
- 1 インタプリタの作成〜破棄 (50 回平均、ms、run 1 の 3 trial): isolated json+re 33.55〜35.10、isolated+_flhost 33.39〜33.69、legacy+_flhost 33.28〜33.67。
- ネガティブコントロール `node tests/static_subinterp_probe.mjs --neg` (期待 1 件を欠く): `NEG-CONTROL DETECTED`、rc 1 (wall 22.15 秒、load 0.97)。
- wasm メモリの推移 (同一 instance、20 回ずつ 8 区間 = 160 回): 33,554,432 B で不変。

## 2. `_PyInterpreterState_GetRefTotal` — FL PE は呼んでいない

- 対応表 `analysis/pybind/pybind_map.json`: 束縛関数 `0xc395a0` の `lea` (0xc39e09) → resolver `0x4235f0` → slot `0x16b84e0`。release build の CPython には定義が無い (許容 1 件)。
- 参照走査 `python3 analysis/pybind/slot_refs.py --pe <block00031_PE.bin> --slot 0x16b84e0` (新規): rip 相対の参照は **1 件** (0xc39e18 の `mov [rip],rax`。束縛時の store)。呼出し・読出しは **0 件**。絶対 64bit / 32bit の参照も 0 件。
- 走査の対照 (呼出しを拾えることの確認): `Py_NewInterpreterFromConfig` の slot `0x16b8250` は store (0xc395f8) と `call [rip]` (0xc3b46b)。
- 束縛関数の逆アセ (`llvm-objdump -d`、0xc395a0〜0xc3a120): resolver `0x4235f0` の呼出し 110 件は全て、直後が `movq %rax, slot(%rip)` (格納)。戻り値の検査 (test / cmp / 分岐) は無い。よって束縛が NULL を返しても、読み込み時には止まらず、slot に無言で格納される。
- 結論: FLEngine PE は GetRefTotal を呼ばない。「FL が使う場合の束縛失敗時の挙動」は、この PE では発生しない。
- 注意: 走査は rip 相対と絶対参照の範囲。`PyInterpreterState_Get` (slot `0x16b8568`) も呼出しは 0 件 (絶対 64bit 参照 1 件) で、FL は呼ばずに束縛だけする名前がある。python312.dll 側や他 DLL での利用は調べていない。

## 3. Memory64 — リンクは成功、実行は node 22.23 で一部

- `build_cpython_wasm64.sh`: wasm64 の configure は config.site に sizeof の固定値を持たないため、ポインタ幅は CFLAGS の `-sMEMORY64=1` に従う。
- `-sMEMORY64=1` (wasm64 libpython + 静的版): リンク 6,375,065 B。node 22.23.3 で `WebAssembly.validate` は **false** (`--experimental-wasm-memory64` を付けても false)。instantiate は `invalid table elements limits flags` で失敗する (table64 の形式)。この環境では実行できない。
- `-sMEMORY64=2` (binaryen の memory64/table64 lowering): リンク 6,548,115 B。`validate` は **true**。
  - `STATIC_WASM=flpy_static64l STATIC_MEM64=2 node tests/static_subinterp_probe.mjs` は `STATIC SUBINTERP FAIL` (rc 2)。**11/12 PASS**。失敗は wasm メモリ不変の 1 件だけ。3 系列とも 33,554,432 → 48,365,568 B (+14,811,136 B)。wall 23.53 秒 (load 0.98)。
  - 同一 instance の推移 (20 回区間): 33,554,432 (0〜100 回) → 40,304,640 (120 回) → 40,304,640 (140 回) → 48,365,568 (160 回)。32bit 版は同じ 160 回で増えない (§1)。
  - 1 インタプリタの作成〜破棄 (50 回平均、ms、run 1 の 3 trial): isolated json+re 36.39〜37.76。
  - 原因は未切り分け (lowering の影響、アロケータの経路差、Python 側の保持のいずれか)。
- table64 に対応するエンジン (headless Chrome など) での `MEMORY64=1` の実行は未検証 → 子 #2858 (PY-98)。

## 4. pthread + GIL — 未実施

- 静的版の複数スレッド版 (`--enable-wasm-pthreads` で libpython を再ビルド、`-pthread` でリンク) は未実施。この run の残り時間で完結しないと判断し、子 #2856 (PY-97) に分割した。
- 既存の前提 (`REPORT_PY2.md` §7d): FL は `PyEval_SaveThread` / `PyEval_RestoreThread` と `PyThreadState_New` / `PyThreadState_Swap` を束縛し、`PyGILState_*` は束縛しない。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| pthread + GIL の静的版のビルドと複数スレッドからの実行 | MIDI スレッド分離の可否 | 子 #2856 (PY-97) |
| `MEMORY64=1` の実行 (node 22.23 は table64 を validate できない。table64 対応エンジンで同じ probe を通す) | Memory64 の実行可否が未確認 | 子 #2858 (PY-98) |
| `MEMORY64=2` の heap 増加 (160 回で +14.8 MB、32bit 版は 0) の原因 | Memory64 (lowered) 版で長い作成/破棄を繰り返すと増える可能性 | 子 #2858 (PY-98) |
| `_PyInterpreterState_GetRefTotal` の結論は FLEngine PE の rip 相対・絶対参照の走査に限る | python312.dll や他 DLL での利用は未調査 | 追加起票なし (結論の範囲の注記) |

## 検証範囲 / 範囲外

- 範囲: Linux・node 22.23.3・静的版 wasm32 と Memory64 の 2 種 (level 1 はリンクのみ、level 2 は実行)。
- 範囲外: pthread、headless Chrome / Firefox / Safari での wasm64、実 FLEngine wasm への接続 (子 #2631 PY-79)。
