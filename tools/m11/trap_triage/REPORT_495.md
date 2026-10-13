# #495: `SV_TRACE_AT` 付き survey で unit 134 が ok→oob になる原因と修正

**判定: 受入条件 3 件すべて達成。** 原因は trace の `fprintf` が wasm shadow stack の SP 直下に残す文字列の残骸を、unit 134 の callee
(`function_413870`) が**未初期化 alloca として読む**こと。`function_413870` は RetDec が rcx/rdx/r8 の 3 引数を落とした 0 引数関数で、
本番の survey が ok なのは「SP 下が未使用のゼロ」だったためにすぎない。trace 出力の前後で SP 直下 8 KiB を退避/復元して trace を透過にした。
検証起点 = 修正前 `cda69f5` (#493 HEAD) / 修正 `17a7a73` (`m11_ov.c`・`m11_rt.c`・`survey_units.mjs`・`negctl_495.sh`)。先行 #481 → #493 の上に積んだ stacked PR。

既知類型との関係 (`docs/DEFECTS.md`): **D5 (DEFECTS.md) に近い** (引数が落ち、未初期化 alloca が代役)。ただし D5 は xmm 引数、本件は整数 reg 引数 (rcx/rdx/r8) の全脱落で、
結果が shadow stack の残骸に依存する点が新しい。行案は §7。

## 1. 再現 (修正前)

`SV_TRACE_AT=<n>` は unit n の直前から `m11_set_trace(1)` (以降の全 unit で trace)。`99999` は一致する unit が無く trace は入らない (stderr の書出しだけ有効)。
修正前の build (`-DM11_TRACE_ISOLATE=0` = 素の `fprintf`) + 現 harness で 942 unit 全部を実行し、trace 無し (`none`) と突き合わせた (`negctl_495.sh iso0`):

| `SV_TRACE_AT` | ok / oob (他は不変) | kind が変わる unit | kind 以外 (frames 深さ / va_mb) だけ変わる unit |
|---|---|---|---|
| 無し (基準) | 839 / 24 | — | — |
| 99999 | 839 / 24 | なし | なし |
| 0 | 838 / 25 | **134 (ok→oob, `memory access out of bounds`)** | 138, 291, 368, 923 |
| 114 | 838 / 25 | **134 (ok→oob)** | 291 |
| 134 | 839 / 24 | なし | 291 |

(旧 harness は trace 行も `err` に入れたため t0 で 941 unit・t114 で 827 unit の `err` 欄が差分になっていた。§3 の harness 修正で `err` からは外した。)

最小再現: `SV_ONLY=115,134 SV_TRACE_AT=115` で 134 が oob (修正前)。unit 115 は icall miss の trace 1 行を出すだけの unit。`SV_ONLY=134` 単独・unit 134 だけ trace (`SV_TRACE_AT=134`) では ok。
**trace を入れた「前の」unit の `fprintf` が後続 unit 134 を壊す**。unit 134 自身の trace では壊れない。

## 2. 原因の特定 (実測)

| 段 | 実測 |
|---|---|
| 経路が stack 残骸か | trace 無しで unit 134 の直前に SP 直下を埋めると再現 (`SV_ONLY=115,134`、調査用の使い捨て script で実測。常設は `SV_STK_FILL`): `0xA5` / `0xFF` で 64 KiB 窓・`0xFF` で SP 直下 341 B 以上 → **oob**。`0x01` 埋め・`0x00` 埋め・340 B 以下の `0xFF` 埋めは ok。二分探索で SP-341 の 1 バイトが効く |
| trace が残すもの | `SV_ONLY=115,134` の unit 134 開始時点で SP 下 2048 B を trace 有り/無しで比較: **差のあるバイト 95、SP からの距離 141〜414 B**。trace 側は ASCII の断片 (`icall-miss` 書式 `(closure 外; skip, ret 0)` の文字列片) |
| trace の効果は残骸だけか | 各 unit の直前に SP 下 8 KiB を `0x00` で埋めると、trace 有り (`t0_fill00`) と無し (`fill00`) の survey JSON が **完全一致** (md5 同一、§4 の表。修正前 build でも同じ) |
| 読み手 | unit 134 = `function_63a5e0` (`dec [mem]` 後に `function_63a330`→`function_639920` を呼ぶ。`cpuid` と 13 B 表の比較をするので CPU 判定の初期化と**推定**) → `function_639920` → **`function_413870()`**。トラップ時の最上位 wasm frame は `function_413870` (V8 index 2083、build 後は 2085) |
| `function_413870` の姿 | IR は `define i64 @function_413870()` (引数 0)。比較ループは `rcx`/`rdx`/`r8` を `%rcx.1.reg2mem` 等の**初期化されない alloca** から `load` して `inttoptr` で deref する。`r8` が 0 なら比較せず 0 を返すので、SP 下がゼロなら無害 |
| 機械語では | `disasm_img.py 639997 0x40`: `lea rcx,[rsp+0x33]` / `imul rdx,rdx,0xd; lea rdx,[rax+rdx]` / `lea r8,[rax+1]` → `call 0x413870` — **3 引数を渡している**。IR の呼出しは `call i64 @function_413870()` (引数なし)。IR 全体で同形の呼出しは `function_639920` ×2・`function_d14470` ×1 (`grep -c 'call i64 @function_413870()'` = 4、残り 1 は `m11_tr_` の tramp) |

注: `survey_units.mjs` の `frames` は非 halt0 の分岐で `.slice(1)` するため、**最上位 frame (実際に trap した関数) が落ちる**
(unit 134 の frames[0] が `function_639920` なのは caller)。`e.stack` の先頭は `RuntimeError…` 行ではなく最初の `at wasm://…` 行で、1 つ余分に捨てている。

## 3. 修正

| 変更 | 内容 |
|---|---|
| `m11_ov.c` `M11_TRACE(...)` | trace の `fprintf` の前後で `emscripten_stack_get_current()` 直下 `M11_TRACE_SPAN` (8192) B を **JS 側 (`EM_JS`, shadow stack を使わない)** で退避/復元。`m11_ov.c` の 7 か所 (`icall` / `icall-miss` / `InitUnits` / `unit` / `InitLib` / `UStrAsg` / `longjmp`) を置換。`-DM11_TRACE_ISOLATE=0` で素の `fprintf` に戻る (ネガコン) |
| `m11_rt.c` | `VirtualAlloc` の trace 専用 `EM_ASM` (`[m11][VA-stack]`) も同じ退避/復元で囲む (`m11_trace_isolate` で切替) |
| `survey_units.mjs` | trace 行 (`TRACE_RE`) は `rec.err` に入れず stderr にだけ出す。`SV_STK_FILL=<hex>` (各 unit 直前に SP 下 8 KiB を埋める)・`SV_TRACE_PROBE=1` (trace が汚した最深距離を測る) を追加 |

wasm の frame 寸法は不変 (`m11_icall` 128 B / `m11_call_unit` 32 B / `function_4133f0` 80 B、修正前後で `llvm-objdump -d` の prologue が同じ)。
`M11_TRACE_SPAN` の根拠: `SV_TRACE_PROBE=1 SV_TRACE_AT=0` の全 survey で trace が汚した最深距離は **544 B** (< 8192 B)。

## 4. 検証 (`bash tools/m11/trap_triage/negctl_495.sh`、コミット済み HEAD `17a7a73`、942 unit)

`md5` は per-unit JSON (frames 含む全欄)。`vs 基準` = 同じ variant の `none` との差 (frames は深さのみ比較)。

| variant | 構成 | ok / oob / halt0 / miss / noproc | md5 | 基準との差分 unit / kind 変化 |
|---|---|---|---|---|
| **iso1 (修正後)** | none | 839 / 24 / 32 / 46 / 1 | `2553ec6ee734` | (基準) |
| | t0 / t114 / t134 / t99999 | 同上 (4 構成とも) | **`2553ec6ee734` (全一致)** | **0 / 0** |
| | fillff (trace 無し, 全 unit 直前に 0xff) | 838 / 25 / … | `4bb56580fe8c` | 134, 138, 368, 923 / 134 ok→oob |
| | fill00 | 839 / 24 / … | `a62162c84287` | 138, 291, 368, 923 / 0 |
| | t0_fill00 (vs fill00) | 839 / 24 / … | `a62162c84287` | **0 / 0** |
| iso0 (修正前相当) | none | 839 / 24 / 32 / 46 / 1 | `7b3983cfac05` | (基準) |
| | t0 | 838 / 25 / … | `86d4d0a2eb13` | 134, 138, 291, 368, 923 / **134 ok→oob** |
| | t114 | 838 / 25 / … | `ccc477730f9e` | 134, 291 / **134 ok→oob** |
| | t134 | 839 / 24 / … | `cf2c269e992e` | 291 / 0 |
| | t99999 | 839 / 24 / … | `7b3983cfac05` | 0 / 0 |
| | fillff / fill00 / t0_fill00 | iso1 と同じ組 | — | iso1 と同じ (fillff で 134 ok→oob、t0_fill00 = fill00 一致) |

- 修正前 (`cda69f5`, 旧 harness, trace 無し) → 修正後 (`17a7a73`, trace 無し): `survey_diff.py` で **遷移はすべて同一 kind (ok 839 / oob 24 / halt0 32 / miss 46 / noproc 1)、ok→非 ok 0 unit**。
  kind 以外の差分 unit は 8 (162, 184, 185, 190, 370, 888, 898, 905、すべて halt0): `err` の `Runtime error 0 at 00000000102510A0` → `…10251220` だけ (wasm の data 配置が `EM_JS` / 定数追加でずれた分と**推定** (差は 0x180、未検証)。同一 kind・同一の 8 unit)。
- 所要 (HEAD 実行、n=3、各回 trace 無し / `SV_TRACE_AT=0` の順): 7.69–7.80 s / 7.95–8.06 s、load average (1 分) 0.48–0.73。md5 は 6 回とも `2553ec6ee734`。`negctl_495.sh` 全体 106.7 s (2 variant × 8 構成 + build 2 回)。
- #482 の ablation 計測が壊れていないこと: `SV_ONLY=1,17,45,95,114 SV_TRACE_AT=114` で `[m11][icall] 0x1c0e70` 4 行 / `icall-miss` 0 行 (REPORT_482 §4 と同じ)。
- `find tools/m11 docs -type f -size +20M -not -path '*/work/*'` 該当なし。`git status --porcelain=v1 -- tools/m11` クリーン (コミット済み HEAD で実行)。

## 5. ネガコン

1. **修正を外す** (`iso0`): trace 有りで unit 134 が ok→oob に戻り、kind 以外も含む差分 unit が 5 (t0) / 2 (t114) / 1 (t134)。修正後は 0。
2. **機構を壊す側から**: trace 無しで SP 下を `0xFF` にすると 134 が ok→oob (修正後 build でも)。`0x00` にすると trace の有無は一致する (t0_fill00 = fill00)。trace の影響経路は shadow stack の残骸だけ。

## 6. 検証範囲 / 範囲外

- 範囲: 942 unit 各 1 回 (先頭から順) の survey JSON と SP 下 8 KiB の残骸感度。fl-win64 は未取得 (PE が要る `m11_e2e.sh`・`M11_LB_BASE != 0` build・#447 併用は範囲外)。
- `M11_TRACE_SPAN=8192` は、この survey で最深 544 B に対しての値。`fprintf` 以外の trace 経路 (`VirtualAlloc` 先頭 3 回の `EM_ASM`、stderr に `[m11][VA-stack]` 3 回) も同じ測定に含まれる。
- 「残骸への感度」は SP 下 8 KiB の 0x00 / 0xFF 埋めで見た範囲。ヒープ側の未初期化読みは見ていない。
- 修正は trace を透過にするもので、unit 134 の ok は依然として**残骸がゼロであること**に依存する。真の欠陥 (`function_413870` の引数脱落) は未修正 (下表)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_413870` (rcx=p1 / rdx=p2 / r8=len の比較ルーチン。CompareMem 相当と**推定**) が 0 引数に lift されている。呼出し `function_639920` ×2・`function_d14470` ×1 も引数なし (機械語は 639920 で渡している。d14470 は未確認) | unit 134 の ok は SP 下がゼロな間だけ。他 unit の変更で SP 下の使われ方が変われば同じ ok→oob が起きる。実機でも残骸次第で trap | **新規子チケット (M11)**: C 転記で `function_413870` と 3 呼出元の引数を復元 (REPORT_482 の 5c03d0 と同じ手順)。#474 REPORT §6 の「D15 / ldfix 検出漏れ全数」子チケットに「引数脱落 + 未初期化 alloca」版として併記 |
| 残骸に感度のある unit が 134 以外に 4 つ: 138 (frames 深さ 11→15)・291 (8→10)・368 (va_mb 734.7→なし)・923 (va_mb なし→1.3、frames 10→13)。どれも未初期化読みの出所は未調査 | survey の va_mb / frames がビルド・trace・他修正で揺れる | **新規子チケット (M11)**: `SV_STK_FILL=ff` / `00` の差分 unit を個別に追う (本 REPORT の `negctl_495.sh` が入口) |
| `survey_units.mjs` の `frames` が非 halt0 で最上位 frame を捨てる (`.slice(1)`) | oob の「最上位 frame」集計 (`annotate.py` の `8cc190` ×9 など) が実際の trap 関数より 1 段上を数えている疑い (推定。halt0 の分岐は別実装) | #130 にコメント。直すと全 oob unit の frames が 1 段増え survey_diff の基準が変わるため本 PR では未変更 → **#663 で解消** (REPORT_663.md) |
| `TRACE_RE` は trace 行の prefix を手で列挙している | `M11_TRACE` に新しい書式を足したときに `TRACE_RE` へ足し忘れると、その行が `rec.err` に入る | 起票不要 (本 REPORT §3 に記載。新規 trace は `[m11][<名>]` 形式で `TRACE_RE` に追加) |

DEFECTS.md 行案 (D5 に隣接する新規類型。編集は PM 判断): 「**整数 reg 引数 (rcx/rdx/r8) の脱落 + 未初期化 alloca 代役** — `function_413870` (比較ルーチン) が 0 引数で lift され、callee は reg2mem の未初期化 alloca から
ポインタ/長さを読む。呼出元も引数を渡さない。結果が wasm shadow stack の SP 下の残骸に依存し (ゼロなら len=0 で 0 を返す)、trace 等で SP 下が汚れると OOB。
検出信号: 同一 build で `SV_STK_FILL=ff` を付けると unit の kind が変わる / 機械語の callsite が 1〜3 引数 reg を設定しているのに IR の `call` が引数なし。修復: 呼出元ごと C 転記」。

## 8. 再現手順

```sh
cd tools/m11   # work/ = work-m11 展開済み。emsdk (/opt/emsdk) が要る。disasm_img.py は capstone (pip) が要る
bash m11_build.sh                                                         # 現行 (M11_TRACE_ISOLATE=1)
node trap_triage/survey_units.mjs work/a.json; SV_TRACE_AT=0 node trap_triage/survey_units.mjs work/b.json; cmp work/a.json work/b.json   # 修正後は同一
SV_STK_FILL=ff node trap_triage/survey_units.mjs work/c.json              # trace 無しでも 134 が ok→oob (残骸感度)
SV_TRACE_PROBE=1 SV_TRACE_AT=0 node trap_triage/survey_units.mjs /dev/null | grep TRACE_MAXDIRTY   # 544
python3 trap_triage/disasm_img.py 639997 0x40                             # 413870 の呼出元が rcx/rdx/r8 を設定している
bash trap_triage/negctl_495.sh [iso1] [iso0]                              # 修正あり/なし × trace 構成 × 埋め (終了時 ov.o / rt.o を再生成)
```
