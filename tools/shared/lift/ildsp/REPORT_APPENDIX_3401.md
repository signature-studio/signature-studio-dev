# ildsp REPORT 付録: PSOLA_CreateInstance の closure lift と native 差分 (#3401)

`REPORT.md` §8 の全文 (250 行上限のため分割移動の形で置く)。手順・実測・未解決の正本はこのファイル。
親: #161 (T-SH-15)。前例: `REPORT_APPENDIX_3216.md` (WaveformColouring、同じ harness)。

## 8. PSOLA_CreateInstance の closure lift と native 差分 — T-SH-75 (#3401・縮小して完了)

既知類型との関係: 該当なし (差分は CreateInstance・slot 0・4・5 の範囲で 0 件。`docs/DEFECTS.md` の新しい類型は確認していない)。
測定 commit: `9b1902fe5` (コードを変えた最後の commit。main (`52e768489`) 取り込み後の code を全て含む。以降の差分は `.md` のみ・§8-8)。検証起点: `42357b73e` (origin/main)。

### 8-1 結論 (1 行)
規模の正本は vtable 経由 closure (82 関数・4,601 命令・間接 call 18)。その一部 (CreateInstance + slot 0・4・5 の到達集合 = 36 関数・1,046 命令・unsup 0) を x64c で C に lift し wasm (80,737 B) にした。native 対 wasm は 64 case で全一致 (ネガティブコントロール FAIL 64/64)。slot 1–3 (DSP 本体へ jmp する thunk) と閉包の残りは未 lift で、子 T-SH-81 に残す。

### 8-2 規模の定義 (受入 1)
- 正本: vtable 経由 closure (`ildsp_closure.py`・`REPORT_CLOSURE.md` §4.2)。理由: §4 で instance の lift 単位を「CreateInstance + vtable slot 先の到達集合」と決めている。`.pdata` 基準 (`REPORT.md` §2: 8 関数・238 命令) は slot 先を含まない下限で、正本にしない。
- PSOLA の確定値 (`ildsp_closure.py` の出力と一致):

| 項目 | 値 |
|---|---:|
| vtable (RVA) | 0x3e0030・6 slot (thunk 3) |
| 関数数 (`.pdata` 無し) | 82 (29) |
| 命令数 | 4,601 |
| SIMD 比 | 21.4% |
| 直接 call / 間接 call | 201 / 18 (IAT 16・画像内関数ポインタ 2・vcall 0・call reg 0) |
| CreateInstance 単体 (entry-only) | 36 関数・961 命令 |

- slot の役割 (逆アセ・vtable 実読で確認): slot 0 = 0x1ab590 (dtor 相当。内部オブジェクトを解放)、slot 1 = 0x1ab680 (`mov rcx,[rcx+8]; cvtsd2ss xmm1,xmm1; jmp 0x17f700`)、slot 2 = 0x1ab690 (`mov rcx,[rcx+8]; jmp 0x1804b0`)、slot 3 = 0x1ab6a0 (`mov rcx,[rcx+8]; jmp 0x180830`)、slot 4 = 0x1ab6b0 (内部状態のクリア・戻り値は ABI 上未定義)、slot 5 = 0x1ab800 (`mov rax,[rcx+8]; mov eax,[rax+0x98]; ret` = 内部 +0x98 を返す)。
- 注 (未解決): x64c の closure (`--closure 99`・7 root) は 235 関数・60,095 命令で、82 関数とは 71 関数しか重ならない (x64c のみ 164・82 のみ 11)。規模の定義が 2 種類ある状態は残る (§8-6)。

### 8-3 lift (受入 3 の縮小範囲)
- 基準 root (CreateInstance + slot 0・4・5): `0x1ab540`・`0x1ab590`・`0x1ab6b0`・`0x1ab800` (`lift_psola.sh` の `WC_ROOTS`)。
- x64c (基準): 36 関数・1,046 命令・**unsup 0**・unlifted callees 0・traps 0・imports 10 (EnterCriticalSection・FlsGetValue・FlsSetValue・GetLastError・HeapAlloc・HeapFree・LeaveCriticalSection・RaiseException・RtlPcToFileHeader・SetLastError)。
- wasm: 80,737 B (emcc 6.0.12 `-O1`)。
- slot を足した閉包 (`--closure 99`・測定 commit `9b1902fe5`・unsup は `lift_meta.json` の `unsup_sites`。fail-fast `int 0x29` と `div by zero` の番兵は数えない):

| root | 関数 | 命令 | unsup site | 内訳 |
|---|---:|---:|---:|---|
| 基準 (4 root) | 36 | 1,046 | 0 | — |
| 基準 + slot 2 (`0x1ab690` → `0x1804b0`) | 37 | 1,059 | 0 | — |
| 基準 + slot 1 (`0x1ab680` → `0x17f700`) | 156 | 27,799 | 73 | ymm 語 23 (うち `f_180012720` 20)・VEX-128 37・shlx 4・movddup 4・pushfq 3・div 2 |
| 基準 + slot 3 (`0x1ab6a0` → `0x180830`) | 156 | 36,539 | 2,401 | ymm 語 2,374 (`f_18021b080` 1,300・`f_18021de40` 846・`f_180036900` 118・`f_180036420` 98 ほか)・他 27 |
| 7 root (基準 + slot 1–3) | 235 | 60,095 | 2,472 | ymm 語 2,396・他 76 (VEX-128 命令・palignr 12 ほか) |

- DSP 本体の窓 (`0x17f700`・`0x1804b0`・`0x180830` から各 24 KiB) に unsup site は **0 件**。unsup は窓の外、DSP 本体から呼ばれる helper の関数 (unsup の RVA は `0x1945`〜`0x25474b` に散る) にある。よって slot 1・3 の lift の前提は、その helper の ymm と VEX-128 命令の対応 (子 T-SH-82) である。
- slot 2 は閉包が unsup 0 で、ymm は理由にならない。本 PR では呼んでいない (差分テストは未実施。子 T-SH-81 の受入に含める)。
- 7 root の閉包 (235 関数・60,095 命令・unsup 2,472) の再現手順:
  ```
  python3 -c 'import json,sys; print(json.dumps({"roots": [0x180000000 + int(x, 16) for x in sys.argv[1:]], "calltgt": []}))' 0x1ab540 0x1ab590 0x1ab680 0x1ab690 0x1ab6a0 0x1ab6b0 0x1ab800 > entries7.json
  python3 tools/flelift/x64c.py --pe <fl-win64 展開先>/extracted/block24360_PE.bin --entries entries7.json --out <dir> --closure 99 --img 0x180000000 --shift 0x150000000 --img-size 0x447000 --impbase 0x1D80000
  ```
  基準 (4 root) は同じ手順で root から `0x1ab680`・`0x1ab690`・`0x1ab6a0` を除く (`--img-size` は PE の SizeOfImage `0x447000`)。

### 8-4 差分テスト (受入 3・4)
- 方式: `lift_psola.sh` (`lift_wc.sh` の harness を環境変数で差し替え。既定値の WC は変えていない)。CreateInstance → slot 0 → slot 4 → slot 5 の順に呼ぶ (`WC_CALL_IDX="0 4 5"`)。
- 戻り値 rax の畳み込みは CreateInstance と slot 5 だけ (`WC_RET_IDX="5"`)。理由: slot 4 の戻り値は ABI 上未定義で、最後に読んだ値か呼出し前の rax が残る。native (C 側の残り値) と wasm (`wc_run` の設定値) で一致しないため、畳み込むと harness の未定義動作を比べることになる。実測では slot 4 を畳み込むと全 64 case が rax で FAIL した (memory 差分は一致)。
- 比較: rax・import stub の呼出回数・heap (arena 64 KiB)・.data 全体 (`wc_diff_test.py`)。
- 実測 (`9b1902fe5`・1 回): 差分 `PASS=64 FAIL=0 excluded(native crash)=0`・wasm trap 0。
- ネガティブコントロール `neg-cmp` (wasm 結果の arena 先頭 1 bit 反転): `FAIL=64` (期待どおり)。`all` は ALL OK。
- 観測の範囲: 64 case は同一経路 (rax は 1 種 `0x5d9b00000`・import stub 呼出 4 回・arena の sha256 は 1 種で全 case 非ゼロ)。.data は run で一度も変化しない (0 case)。よって 64 PASS は「入力 .data に依存しない 1 経路の一致」であり、分岐の網羅ではない (`REPORT_APPENDIX_3216.md` §7-6 と同じ制限)。

### 8-5 実測 (測定 commit `9b1902fe5`・4 core・各 1 回)
| 項目 | 値 |
|---|---|
| `lift_psola.sh ok` elapsed | 1.61 s |
| `lift_psola.sh neg-cmp` elapsed | 1.48 s |
| load (ok: 開始 → 終了) | 0.00 0.15 0.17 → 0.08 0.16 0.17 |
| 差分 (ok) | PASS 64 / FAIL 0 (wasm trap 0) |
| neg-cmp | FAIL 64 (rc 1・期待どおり)・ALL OK |
| 回帰 (WC) `lift_wc.sh ok` | PASS 64/64・elapsed 1.70 s・load 0.07 0.16 0.17 → 0.15 0.17 0.18・x64c 60 関数・2,656 命令・unsup 3・wasm 138,754 B |

- 再現 (PSOLA): `FL_WIN64_DIR=<展開先> EMSDK_ENV=<toolchain-emsdk 展開先>/emsdk/emsdk_env.sh bash tools/shared/lift/ildsp/lift_psola.sh all`
- closure 数値: `FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_closure.py` (PSOLA 行が §8-2 の表)。

### 8-6 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot 1・3 (DSP 本体 0x17f700・0x180830 と、そこから呼ばれる helper) を含む閉包の lift と native 差分。7 root の unsup は 2,472 site | 受入 (3) の残り (閉包全体の全バイト差分) | 子 [T-SH-81] |
| x64c の unsup: 閉包全体で ymm 語 2,396 site・VEX-128 ほか 76 site。実装は PR #3471 (`3428-x64c-psola-ymm`) が進行中 | 上の lift の前提。未対応のまま呼ばれると trap になる | 子 [T-SH-82] (#3428) |
| slot 2 (`0x1ab690` → `0x1804b0`): 閉包は unsup 0 だが、本 PR では差分テストを行っていない | 受入 (3) の残り | 子 [T-SH-81] の受入に含める |
| 間接 call の native 到達実測と扱い (helper `0x1aedc0`・`0x1b6f4c` の 4 件、画像内ポインタ `0x268260`・`0x268268`)。PSOLA の閉包も同じ helper を含む (`REPORT_CLOSURE.md` §4.6) | 受入 (2)。PSOLA の IAT 16 件は stub で lift 済み | 既存 #3250 [T-SH-54] (GPS の同じ helper の実測。PSOLA でも同一アドレス) |
| x64c の closure (235 関数) と `ildsp_closure.py` の closure (82 関数) の関数集合の差 (重なり 71) | 規模の数値の定義。どちらを使うかで閉包の大きさが変わる | #161 (親・PM 判断) |
| 差分が 1 経路 (.data 不変・全 case 同一経路) | 分岐網羅の証拠にならない | 子 [T-SH-81] の受入に含める |

### 8-7 slot 4・5 の差分テストの位置付け
- slot 4 (クリア) と slot 5 (`return [+0x98]`) は呼び出しの memory 効果を差分に含める。戻り値は slot 5 だけ畳み込む (§8-4)。slot 4 の戻り値は未検証。
- slot 5 の `[+0x98]` は CreateInstance が 0 にする領域で、差分の rax は 0 相当の値のみ見ている。0 以外の入力での振る舞いは未検証 (`.data` は run で不変のため、内部 +0x98 は zero のまま)。

### 8-8 測定後のコード差分 (差分 0 の証跡)
測定 commit `9b1902fe5` 以降に変えたのは本付録・`REPORT.md`・`DOC_MAP.md` (`.md` のみ)。
`git diff 9b1902fe5 HEAD -- tools/shared/lift/ildsp tools/flelift/x64c.py tools/flelift/rt tools/shared/env.sh tools/shared/scripts ':!*.md'` の出力は空 (差分 0)。
測定 commit には main 取り込み (`52e768489`・`ba70aa677` 経由) の code 差分を含む (`tools/flelift/rt/fle_cpu.{c,h}`・`ildsp/lift_wc.sh`・`ildsp/wc_image.py`・`ildsp/closure_select.py` ほか)。経路外かどうかで除外せず、全 code で測定した。
