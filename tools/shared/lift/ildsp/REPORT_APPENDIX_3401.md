# ildsp REPORT 付録: PSOLA_CreateInstance の closure lift と native 差分 (#3401)

`REPORT.md` §8 の全文 (250 行上限のため分割移動の形で置く)。手順・実測・未解決の正本はこのファイル。
親: #161 (T-SH-15)。前例: `REPORT_APPENDIX_3216.md` (WaveformColouring、同じ harness)。

## 8. PSOLA_CreateInstance の closure lift と native 差分 — T-SH-75 (#3401・縮小して完了)

既知類型との関係: 該当なし (差分は CreateInstance・slot 0・4・5 の範囲で 0 件。`docs/DEFECTS.md` の新しい類型は確認していない)。
測定 commit: `9b1902fe5` (コードを変えた最後の commit。main (`52e768489`) 取り込み後の code を全て含む。以降の差分は `.md` のみ・§8-8)。検証起点: `42357b73e` (origin/main)。

### 8-1 結論 (1 行)
規模の正本は vtable 経由 closure (82 関数・4,601 命令・間接 call 18)。その一部 (CreateInstance + slot 0・4・5 の到達集合 = 36 関数・1,046 命令・unsup 0) を x64c で C に lift し wasm (80,737 B) にした。native 対 wasm は 64 case で全一致 (ネガティブコントロール FAIL 64/64)。slot 1–3 (DSP 本体へ jmp する thunk) と閉包の残りは未 lift で、当時は子 T-SH-81 に残した (現在の状態は §8-9)。

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
- slot 2 は閉包が unsup 0 で、ymm は理由にならない。本 PR では呼んでいない (差分テストは未実施。#3427 (残り) → 子 #4237 [T-SH-105] の受入に含める)。
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
| slot 1・3 (DSP 本体 0x17f700・0x180830 と、そこから呼ばれる helper) を含む閉包の native 差分。閉包の lift は unsup 0 (§8-9) | 受入 (2)・(3) の残り (閉包全体の全バイト差分) | 子 #4237 [T-SH-105] |
| x64c の unsup (閉包 ymm 語 2,396 site・VEX-128 ほか 76 site) | 解消 (§8-9)。PR #3471 (`285ab7650`) で main 取り込み済み | #3428 (T-SH-82) は PR #3471 で完了 |
| slot 2 (`0x1ab690` → `0x1804b0`): 閉包は unsup 0 だが、本 PR では差分テストを行っていない | 受入 (3) の残り | 子 #4237 [T-SH-105] の受入に含める |
| 間接 call の native 到達実測と扱い (helper `0x1aedc0`・`0x1b6f4c` の 4 件、画像内ポインタ `0x268260`・`0x268268`)。PSOLA の閉包も同じ helper を含む (`REPORT_CLOSURE.md` §4.6) | 受入 (2)。PSOLA の IAT 16 件は stub で lift 済み | 既存 #3250 [T-SH-54] (GPS の同じ helper の実測。PSOLA でも同一アドレス) |
| x64c の closure (235 関数) と `ildsp_closure.py` の closure (82 関数) の関数集合の差 (重なり 71) | 規模の数値の定義。どちらを使うかで閉包の大きさが変わる | #161 (親・PM 判断) |
| 差分が 1 経路 (.data 不変・全 case 同一経路) | 分岐網羅の証拠にならない | 子 #4237 [T-SH-105] の受入に含める |

### 8-7 slot 4・5 の差分テストの位置付け
- slot 4 (クリア) と slot 5 (`return [+0x98]`) は呼び出しの memory 効果を差分に含める。戻り値は slot 5 だけ畳み込む (§8-4)。slot 4 の戻り値は未検証。
- slot 5 の `[+0x98]` は CreateInstance が 0 にする領域で、差分の rax は 0 相当の値のみ見ている。0 以外の入力での振る舞いは未検証 (`.data` は run で不変のため、内部 +0x98 は zero のまま)。

### 8-9 閉包 7 root の再測定と slot 1–3 の差分 (#3427 (残り) → 子 #4237 [T-SH-105])
- #3428 (PR #3471) の ymm 対応が main に入った後の実測。7 root (基準 + slot 1–3) の閉包は **unsup 0** (§8-3 の 2,472 site が解消)。235 関数・60,095 命令・unlifted callees 0・traps 0・imports 18 (`lift_psola_closure.sh` の lift)。
- 測定 commit: `c2cc726a2` (コードを変えた最後の commit)。鮮度の根拠: `git diff c2cc726a2 HEAD -- tools/shared/lift/ildsp tools/flelift/x64c.py` は差分 0 (HEAD は `.md` のみ)。
- 差分 (呼出しは基準と同じ CreateInstance → slot 0 → slot 4 → slot 5): PASS 64 / FAIL 0 (wasm 3,549,536 B・trap 0)。閉包を広げても基準の一致は保たれる。
- slot 1–3 を差分に入れると、native 側が全 64 case で addr 0 の SIGSEGV になり比較対象が 0 件になる (`wc diff` は PASS 0・excluded 64)。DSP 本体 (0x17f700 ほか) は `this` の内部フィールド (+0xc4・+0xcc・+0x33c・+0x6a0・+0x24・+0x6bc など) を書いてから helper を呼ぶ。null 参照の原因 (未設定の内部ポインタ) は未特定。host 側の事前設定が要る。
- 未解決 (子 #4237 [T-SH-105] の受入): slot 1–3 の host 前提の確定と、その入力での native 対 wasm 差分。slot 2 の差分は未実施。

### 8-8 測定後のコード差分 (historical: 9b1902fe5 時点の証跡)
測定 commit `9b1902fe5` 以降に変えたのは本付録・`REPORT.md`・`DOC_MAP.md` (`.md` のみ)。
`git diff 9b1902fe5 HEAD -- tools/shared/lift/ildsp tools/flelift/x64c.py tools/flelift/rt tools/shared/env.sh tools/shared/scripts ':!*.md'` の出力は `9b1902fe5` 時点では空だった (差分 0)。
現在の HEAD では #3471 の変更で差分がある (`x64c.py` +130 ほか)。このため現在の鮮度の根拠にはしない。現在の根拠は §8-9。
測定 commit には main 取り込み (`52e768489`・`ba70aa677` 経由) の code 差分を含む (`tools/flelift/rt/fle_cpu.{c,h}`・`ildsp/lift_wc.sh`・`ildsp/wc_image.py`・`ildsp/closure_select.py` ほか)。経路外かどうかで除外せず、全 code で測定した。

## 9. slot 2 の差分追加と slot 1・3 の native 落ち原因 — T-SH-105 (#4237)

測定 commit: `b53a5ec8f` (コードを変えた最後の commit。`lift_psola.sh` の差分と、main 取り込みで入った `ildsp_native.c`・`fle_cpu.c`・`lift_psola_closure.sh` の差分を含む)。`d7a1b641e` からの差分は main 取り込み分のみ。§9-2・§9-3 は `e50124848` (HEAD) で再測定した。

### 9-1 結論 (1 行)
slot 2 を加えて 64/64 PASS (ネガコン FAIL 64/64) し、slot 1・3 は復号鍵 `[0x3f7ad0]` が 0 のため native が 64/64 で落ちるので差分に入れていない (鍵の書込み元は未特定)。

### 9-2 slot 1〜3 の native 単独呼出し (実測・HEAD・各 64 case・`lift_wc.sh`)
測定: `e50124848` (コードは `b53a5ec8f` と同一・`git diff b53a5ec8f HEAD -- tools/shared/` は 0 バイト)。`WC_ROOTS` は `lift_psola.sh` と同じ。`WC_CALL_IDX` と `WC_RET_IDX=5` を指定して呼ぶ。
| WC_CALL_IDX | native 結果 | 備考 |
|---|---|---|
| `1` (CreateInstance → slot 1) | SIGSEGV/SIGBUS 64/64・addr 0x0 | slot 0 を呼ばない |
| `2` (CreateInstance → slot 2) | PASS 64/64 (落ちない・wasm 差分 PASS 64/64) | 単独でも成立 |
| `3` (CreateInstance → slot 3) | SIGSEGV/SIGBUS 64/64・addr 0x0 | |
| `1 4 5` | SIGSEGV/SIGBUS 64/64 | |
| `0 1 4 5` | SIGSEGV/SIGBUS 64/64 | slot 0 (dtor) の後でも同じ |

注: `lift_psola.sh` は `WC_CALL_IDX` を無条件に上書きするため、上の表は `lift_wc.sh` を直接呼んで得た。`lift_psola.sh` 経由では別の slot 集合になる。

### 9-3 落ち箇所の特定 (slot 1 単独・RIP を実測)
- SIGSEGV 時の RIP は `rip=0x1cb5e0` (`jmp rax`)・`rax=0xae64b77e88c8000` (HEAD で 64/64 同一)。計測は `lift_wc` の native harness の複製 (`ildsp-probe` 作業用・repo 外へ置かない)。
- `rax` の値は `0x1b6f4c` の復号結果と一致する。`0x1b6f4c` の (a) `0x1b6f88` は `rbx = ror([0x3f5d98] ^ [0x3f7ad0], cl)` を計算する。`[0x3f5d98] = 0x2b992ddfa232`・`[0x3f7ad0] = 0` (ロード後の image)・`cl = 50` から `ror = 0xae64b77e88c8000`。よって鍵が 0 のとき復号結果が不正なポインタになり、`jmp rax` が addr 0 を踏む。(b) `movabs r10, 0xd1ed0fdf1cd32070` を置き、(c) `call [rip+0xb12f6]` (RVA `0x268268`) を呼ぶ。
- 直接 call: `0x1b6f4c` を直接呼ぶ E8 call は画像内に 4 箇所ある (`0x1ac9ce`・`0x1b9049`・`0x1b9c45`・`0x1c20a9`。`objdump -D` で確認。rel32 の解決先は `0x1b6f4c`)。ハーネスの direct hook 表 (`ildsp_native.c`) は同じ 4 箇所を trace している。
- 鍵 `0x3f7ad0` の参照: `0x1b6fa2` (`xor rbx, [0x3f7ad0]`・読み) と `0x1b6f44` (`mov [0x3f7ad0], rcx; ret`・書き) の 2 箇所。`objdump` の RIP 相対コメントで確認。`0x1b6f44` は関数として存在するが、画像内に直接の call/jmp は無く、絶対アドレスの参照も無い。書き込みの呼出し元は未特定。
- 未確認 (旧記述から取り下げ): 旧 §9-3 の thunk の `rcx = [this+8]` 読みは、`0x17f700` の逆アセンブルで確認できなかった。戻り番地 `0x1b6f72` も HEAD の `lift_wc` 側では再確認していない。

### 9-4 受入の達成状況 (issue #4237)
| 受入 | 状態 |
|---|---|
| (1) slot 1・3 の host 前提 (`this` の内部フィールド・未設定ポインタ) を特定し差分の入力に決める | **部分**。落ち箇所 (`0x1b6f4c` の復号鍵 `0x3f7ad0` が 0 → 復号結果が不正ポインタ) まで HEAD で特定。鍵を書く `0x1b6f44` の呼出し元は未特定。入力には決めていない |
| (2) slot 1–3 を含む呼出し順で native 対 wasm の差分 | **部分**。slot 2 を含む差分は `WC_CALL_IDX="0 2 4 5"` で実施 (64/64・ネガコン 64/64)。slot 1・3 は未達 |
| (3) .data 入力の変化で分岐の到達を数値に示す | **未達**。差分は従来どおり .data 不変・同一経路 (§8-4 と同じ制限) |

### 9-5 実測 (slot 2 を含む差分・測定 commit は下記・4 core・1 回)
測定 commit: コードを変えた最後の commit `b53a5ec8f`。その後の `e50124848` は `lift_psola.sh` の**コメント 1 行だけ**を変えた (`git diff b53a5ec8f HEAD -- tools/shared/lift/ildsp/lift_psola.sh` は comment 行のみ)。本表は `e50124848` の作業ツリーで取り直した値。
| 項目 | 値 |
|---|---|
| `lift_psola.sh all` elapsed | 3.53 s (real・rc 0。`b53a5ec8f` 時点の同コマンドは 3.02 s) |
| 本検査 (ok) | 1.74 s・PASS 64 / FAIL 0 (wasm trap 0・native crash 0・SIGSEGV/SIGBUS 0) |
| neg-cmp | 1.76 s・FAIL 64 (rc 1・期待どおり)・ALL OK |
| x64c | 37 関数・1,059 命令・unsup 0 (従来の基準 36・1,046 から slot 2 の 1 関数・13 命令を追加) |
| wasm | 81,303 B (SizeOfImage 0x447000) |
| load | 本検査の開始 0.03 0.28 0.27 → 終了 0.03 0.28 0.27 |
| 環境 | emsdk 6.0.12 (`EMSDK_ENV` は `/tmp/opencode/emsdk` に導入)・fl-win64 は `/tmp/opencode/win64` に展開 |

### 9-6 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot 1・3 の復号鍵 `[0x3f7ad0]` を設定する host 初期化の特定 | 受入 (1)(2) の残り。slot 1・3 を差分に入れられない | #4302 [T-SH-114] |
| `.data` 入力の変化による分岐の数値化 | 受入 (3) | #4303 [T-SH-115] |
