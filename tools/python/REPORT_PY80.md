# python 付録: PY-80 静的版のサブインタプリタ・Memory64・`_PyInterpreterState_GetRefTotal` の検証 (#2633)

既知類型との関係: 該当なし (lift / 逆アセの欠陥類型ではない。PE は束縛 slot の参照走査と束縛関数の逆アセのみ)。
親: #83 (PY-2)。`REPORT_PY2.md` §7d・§7e・§7f の未解決を移管 (旧 #76 の T6)。

## 結論

| # | 項目 | 判定 | 節 |
|---|---|---|---|
| 1 | サブインタプリタ (静的版 wasm32) | **達成**。12/12 PASS | §1 |
| 2 | pthread + GIL | **未実施**。子 #2856 (PY-97) に分割 | §4 |
| 3 | Memory64 | **部分**。`MEMORY64=1` はリンクまで成功。headless Chrome 154 では validate 可、node 22.23 では validate 不可 (エンジン依存)。`MEMORY64=2` は node で実行でき 11/12 PASS (heap 増加 1 件 FAIL)。`MEMORY64=1` の実行検証は子 #2858 (PY-98) | §3 |
| 4 | `_PyInterpreterState_GetRefTotal` | **FL PE は呼んでいない**。参照は束縛時の store 1 件のみ。束縛失敗は無言 | §2 |

測定 commit (WORKFLOW §6 の定義: コード差分の最終 commit): `2a85bd96`。以降の差分は本節を含む文書のみで、`git diff 2a85bd96 HEAD -- tools/python ':(exclude)*.md'` の出力は 0 行 (fix の HEAD で確認)。probe の実行 commit: `7e34fa2b` (probe の値は、この commit を再ビルドした dist で測定)。`7e34fa2b` → `2a85bd96` の差分は Chrome の validate 確認ページ (`tests/memory64_validate_chrome.html`) 1 件だけで、probe の測定経路には入らない。`7e34fa2b` は、それより前の commit `37164f82` (同じ測定) から `build_cpython_wasm64.sh` の emsdk の指定だけを変えたもの ([EMSDK] の lint 対応)。

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

| 検査 | 結果 (probe 実行 commit `7e34fa2b`) |
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
- 入力の展開 (`tools/python` で実行、gitignore の `work/` に置く): `mkdir -p work/py80 && tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C work/py80 --wildcards '*block00031_PE.bin'` ([WIN64]・`$ARTIFACTS_DIR` は素材の置き場) → `work/py80/extracted/block00031_PE.bin` (22,227,016 B、展開 2.9 秒)。
- 参照走査 `python3 analysis/pybind/slot_refs.py --pe work/py80/extracted/block00031_PE.bin --slot 0x16b84e0` (新規): rip 相対の参照は **1 件** (0xc39e18 の `mov [rip],rax`。束縛時の store)。呼出し・読出しは **0 件**。絶対 64bit / 32bit の参照 (値 `0x16b84e0` のバイト列の出現。ファイル全体で数えた) も 0 件。出力は `0x16b84e0 disp_va=0xc39e18 opcode=mov [rip],reg` の 1 行 (6.4 秒。fix の作業ツリー HEAD `43846de0` で再実行し一致。`slot_refs.py` は変更していない。走査は rip 相対の disp32 だけで、絶対参照は含まない)。
- 走査の対照 (呼出しを拾えることの確認): `Py_NewInterpreterFromConfig` の slot `0x16b8250` は store (0xc395f8) と `call [rip]` (0xc3b46b)。
- 束縛関数の逆アセ (`llvm-objdump -d`、0xc395a0〜0xc3a120): resolver `0x4235f0` の呼出し 110 件は全て、直後が `movq %rax, slot(%rip)` (格納)。戻り値の検査 (test / cmp / 分岐) は無い。よって束縛が NULL を返しても、読み込み時には止まらず、slot に無言で格納される。
- 結論: FLEngine PE は GetRefTotal を呼ばない。「FL が使う場合の束縛失敗時の挙動」は、この PE では発生しない。
- 注意 (`PyInterpreterState_Get`、slot `0x16b8568`): rip 相対の束縛 store は 1 件 (0xc3a06e、束縛関数内)、rip 相対の呼出し・読出しは 0 件。ただし絶対 64bit のポインタが `.data` の VA `0x15e1238` に 1 件あり (値 `0x16b8568` = slot 自体の番地)、この cell を rip 相対で読む命令が 2 件 (0xd90114・0xd972ed) ある。いずれも直後が `call *(%rax)` (`objdump -D -b binary -mi386:x86-64` で確認)。よって FL PE は `PyInterpreterState_Get` を間接呼出しする。旧版の「FL は呼ばない」は誤り。この結論は GetRefTotal にだけ当たる。python312.dll 側や他 DLL での利用は調べていない。

## 3. Memory64 — リンクは成功、実行は node 22.23 で一部

- `build_cpython_wasm64.sh`: wasm64 の configure は config.site に sizeof の固定値を持たないため、ポインタ幅は CFLAGS の `-sMEMORY64=1` に従う。
- `-sMEMORY64=1` (wasm64 libpython + 静的版): リンク 6,375,065 B。
  - node 22.23.3 で `WebAssembly.validate` は **false** (`--experimental-wasm-memory64` を付けても false)。instantiate は `invalid table elements limits flags` で失敗する (table64 の形式)。
  - 再現 (`tools/python` で実行。`dist/flpy_static64.wasm` は `FLPY_MEMORY64=1 CPY_BUILD=$PWD/work/build-wasm64 STATIC_OUT=flpy_static64 bash build_flpy_static.sh` で作る): `node -e 'const b=require("fs").readFileSync("dist/flpy_static64.wasm");console.log(WebAssembly.validate(b))'` → `false`。上の数値は測定 commit `2a85bd96` の dist による。fix の run では emsdk が無く dist を再ビルドしていない (再実行していない・測定時の値)。この 1 行の書式は、空の wasm (`\0asm` + version) で `true`、壊れたファイルで `false` を確認した。
  - instantiate の失敗 (測定時の文言 `invalid table elements limits flags`) の再現: `node -e 'new WebAssembly.Module(require("fs").readFileSync("dist/flpy_static64.wasm"))'` → 同じ compile 段の `CompileError` (測定時は instantiate 側で同じ文言)。この run では dist を作れず、このコマンドは未実行。代わりに、同じ文言の系統を次で確認した (node v22.23.3、本 run): table64 の limits (flags `0x04`) だけを持つ最小 wasm `new Uint8Array([0,97,115,109,1,0,0,0,4,4,1,112,4,1])` を `new WebAssembly.Module` に渡すと `CompileError: WebAssembly.Module(): invalid table elements limits flags @+12`。
  - headless Chrome 154 では `validate=true` (wasm32 の `flpy_static.wasm` も true)。table64 はブラウザでは受理される。再現コマンド (html 冒頭と同じ。測定時の実フラグの記録は無いため、この 1 形式に統一): `google-chrome --headless=new --no-sandbox --disable-gpu --allow-file-access-from-files --virtual-time-budget=15000 --dump-dom file://$PWD/tests/memory64_validate_chrome.html`。本 run では dist が無いため、3 件とも `Failed to fetch` の RESULT 行が出る (rc 0。コマンドの形の確認のみ、validate の値は測定時のもの)。instantiate と probe の実行は未実施 (子 #2858)。
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
| `MEMORY64=1` の instantiate と probe 実行 (node 22.23 は validate 不可、Chrome 154 は validate 可) | Memory64 の実行可否が未確認 | 子 #2858 (PY-98) |
| `MEMORY64=2` の heap 増加 (160 回で +14.8 MB、32bit 版は 0) の原因 | Memory64 (lowered) 版で長い作成/破棄を繰り返すと増える可能性 | 子 #2858 (PY-98) |
| `_PyInterpreterState_GetRefTotal` の結論は FLEngine PE の rip 相対・絶対参照の走査に限る | python312.dll や他 DLL での利用は未調査 | 追加起票なし (結論の範囲の注記) |
| FLEngine PE が `PyInterpreterState_Get` を間接呼出しする 2 箇所 (0xd90114・0xd972ed) の呼出し先での挙動 | 静的版の probe (単体) は FL の呼出し文脈を含まない | 追加起票なし (注記) |

## 検証範囲 / 範囲外

- 範囲: Linux・node 22.23.3・静的版 wasm32 と Memory64 の 2 種 (level 1 はリンクのみ、level 2 は実行)。
- 範囲外: pthread、headless Chrome / Firefox / Safari での wasm64、実 FLEngine wasm への接続 (子 #2631 PY-79)。
