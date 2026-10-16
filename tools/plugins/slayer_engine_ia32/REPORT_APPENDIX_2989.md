# REPORT_APPENDIX_2989 — x87 を含む関数の native vs wasm 差分試験 (#2989 PLG-G2-25)

既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない)。 f80→f64 の精度差は方式 (ADR D28) の帰結で、行案は `REPORT_APPENDIX_1099.md` §6 (D24 (案)) に既にある。 本付録はその関数レベルでの観測を足す (`DEFECTS.md` は編集しない)。

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13。 方式は `docs/DECISIONS.md` D28 (f80→f64)。 本付録が測定値の正本。
- 測定 commit: `565111174` (`feat(ott): native vs wasm differential test for x87 functions (#2989)`。 試験のコードを含む最後の commit)。 本付録の commit は docs のみ。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (sha256 は REPORT_APPENDIX_1223 §1 と同じ素材) と乱数で生成した試行のみ。

## 1. 結論

- x87 を含む leaf 関数 2 本 (`0x10002ee0`・`0x10005400`) を、native (実 x87 命令) と wasm (ia32 x64c lift → `ott_x87.h` の double) で各 4,000 試行 (seed 2989) 実行し、eax・ST(0)・x87 深さ・OBJ 窓 (1,344 B) を突合した。 **構造 (eax・x87 深さ・行数) は全行一致。 float32 結果 (ST(0)・OBJ 窓) は全行一致。**
- ST(0) を double で読むと、**行の 2.75% (`0x10002ee0`: 110 / 4,000) と 14.88% (`0x10005400`: 595 / 4,000) で 1 ulp 以上の差が出る**。 f80→f64 の丸め差で、float32 結果には伝播しなかった (本試験の入力範囲では)。
- 例外値 (NaN・inf・非正規・±0、§7): 数値どうしは float32 で全行一致。 NaN どうしのビット差 (符号・ペイロード) は `eax` 622 行・ST(0) 1,002 語で出る (§7)。 NaN と数値の混在は 0 件。
- ネガコン 2 種とも検出: (a) bit 一致の行 1 件の ST(0) の最下位 bit を反転 → 7,295 → 7,294。 (b) lowering の 1 演算の取り違え (`f_10002ee0` の fsubp を SUB→SUBR) → float32 結果が一致しない行 4,000 / 4,000。

## 2. 対象と方法

- 対象 (`x87_fn_diff.py` の `TARGETS`): どちらも lift 出力で x87 を含み、import も未 lift の call も無い leaf 関数。
  - `0x10002ee0`: thiscall (`ecx` = this、float a0、添字 a1) `ret 8`。 `[ecx+a1*4+0xb0..0x1f4]` を読み書きし、ST(0) を残して返る (lift 出力の x87 行 18 件)。
  - `0x10005400`: thiscall (`ecx` = this、float a0..a2) `ret 0xc`。 `fcomp`・`fnstsw`・`fdivr` と `[ecx+0x4fc..0x518]` の更新を含む (x87 行 71 件)。 entry 時点で読む引数は `[esp+4]`・`[esp+8]`・`[esp+0xc]` (a0・a1・a2) の 3 本だけ。 harness は a3・a4 (と a5 = 0) にも値を入れるが、本体は読まない余りの引数 (native・wasm とも 6 本を積む)。
- native (`x87_fn_native.c`): freestanding i386 ELF。 image を VA `0x10000000` に敷設し、呼出し前に `fninit`、呼出し後に `fnstsw` で TOP から深さ `d = (8 - TOP) & 7` を求め、`fsts` (float32)・`fstl` (float64) で ST(0) を読む。
- wasm (`x87_fn_glue.c`・`x87_fn_entry_wasm.mjs`): `ott_lifted.c` を同じ翻訳単位に取り込む (`ott_x87.h` の state は static のため)。 呼出し前に x87 を初期化し、呼出し後に `d = (8 - ott_ftop) & 7`、ST(0) を `(float)` と `(double)` で取る。
- 入力: seed 2989。 OBJ 窓の初期値は一様な有限の float32 (±1000)。 float 引数は `fn_10002ee0` が ±1000、`fn_10005400` が ±100。 添字は 0..15。
- 判定: 構造 (行数・eax・x87 深さ不一致 0、OBJ 窓が変わった行 = 非自明性) を exit の条件にする。 float 語の差分は落とさず分布として出す (ADR D28 の f80→f64 の差を gate しないため)。

## 3. 実測 (測定 commit `565111174`、`ws-2989` で再現)

| 関数 | n | 行の全項目が一致 | float32 結果のみ一致 | ST(0) float64 の一致 / 1ulp / 2ulp / ≥3ulp | eax・x87 深さ不一致 | OBJ 窓が変わった行 |
|---|---:|---:|---:|---|---:|---:|
| `0x10002ee0` | 4,000 | 3,890 (97.25%) | 4,000 / 4,000 | 3,890 / 64 / 22 / 24 | 0 / 0 | 4,000 |
| `0x10005400` | 4,000 | 3,405 (85.12%) | 4,000 / 4,000 | 3,405 / 595 / 0 / 0 | 0 / 0 | 4,000 |

- OBJ 窓の float32 語: 1,344 B = 336 語 × 4,000 行 × 2 関数 = 2,688,000 語、全語一致。
- 所要 (1 driver 実行): native build 0.03–0.05 s、emcc 3.36–3.64 s、native 実行 0.104–0.106 s、wasm (node) 0.145–0.152 s。 load1 は 0.16–0.49 (cpu 4)。 driver 全体は約 5 s。
- 再現: 同じ seed で 2 回実行し、上の数値は同一 (`main` checkout と `ws-2989` の双方で確認)。

## 4. ネガコン

- (a) 判定器: wasm 側の bit 一致行 (行 0) の ST(0) float32 の最下位 bit を反転 → bit 一致 `7295 → 7294` (`python3 x87_fn_diff.py --nega`、exit 0 = 検出)。
- (b) 意味の誤り: `lift` の `f_10002ee0` の最初の `x87_arith(2, 1, …)` (X87_SUB) を `(3, 1, …)` (X87_SUBR) に差し替えて wasm を作り直す → `fn_10002ee0` の float32 結果が一致しない行 `4,000 / 4,000` (`python3 x87_fn_diff.py --nega-lower`、exit 0 = 検出)。 この取り違えで float32 結果がずれることを確認したので、float32 の全行一致は空振りではない。
- (c) 例外値の判定 (`nan-num`): 特殊値モードの wasm 出力で、両方が NaN の最初の行 (行 0・`fn_10002ee0`) の ST(0) を `3f800000` (1.0) に置き換え、突合し直す。 `nan-num` は 0 → 1 に増え、突合の判定は FAIL (本体の exit 1 と同じ経路) になる (`python3 x87_fn_diff.py --special --nega-nan`、exit 0 = 検出)。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 EMSDK=$RUNNER_TEMP/emsdk    # fl-win64 は extracted/block22434_PE.bin のみで足りる
source $EMSDK/emsdk_env.sh                                            # emsdk 6.0.12 (toolchain-emsdk)
python3 tools/plugins/slayer_engine_ia32/lift_text.py                 # work/lift_text/ott_lifted.c を作る (前提)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py               # 突合 (exit 0)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --nega        # ネガコン (a) (exit 0)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --nega-lower  # ネガコン (b) (exit 0)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --special       # 例外値の突合 (exit 0)
python3 tools/plugins/slayer_engine_ia32/x87_fn_diff.py --special --nega-nan  # ネガコン (c) (exit 0)
```

- 鮮度の証跡 (WORKFLOW §6): 測定 commit `565111174` の後の変更は、本付録・REPORT / DOC_MAP の文書と、review 指摘によるコメントだけの修正 (`x87_fn_diff.py` の TARGETS の注釈 2 行・`x87_fn_native.c` の冒頭注釈 1 行)。 実行されるコード・生成コード・乱数の列は変えていないので、再測定はしていない。 `git diff 565111174 HEAD -- tools/plugins/slayer_engine_ia32/x87_fn_diff.py tools/plugins/slayer_engine_ia32/x87_fn_native.c tools/plugins/slayer_engine_ia32/x87_fn_glue.c tools/plugins/slayer_engine_ia32/x87_fn_entry_wasm.mjs tools/plugins/slayer_engine_ia32/lift_text.py tools/ott/lift tools/ott/rt` の出力 (全文):

```diff
diff --git a/tools/plugins/slayer_engine_ia32/x87_fn_diff.py b/tools/plugins/slayer_engine_ia32/x87_fn_diff.py
index 73ef78a57..834c45fb4 100644
--- a/tools/plugins/slayer_engine_ia32/x87_fn_diff.py
+++ b/tools/plugins/slayer_engine_ia32/x87_fn_diff.py
@@ -27,8 +27,8 @@ N_PER_TARGET = 4000
 SEED = 2989
 
 # va: 入口 VA。 gen: 引数と OBJ 窓の初期値の作り方 (ecx = OBJ)。 どちらも leaf で x87 を含み、import・未 lift の call が無い。
-#   fn_10002ee0: stdcall (float a0, int a1 = 添字 0..15) ret 8。 [ecx+a1*4+0xb0..0x1f4] を読み書きし、ST(0) を残して返る。
-#   fn_10005400: stdcall (float a0..a4) ret 0xc。 fcomp・fnstsw・fdivr を含み、[ecx+0x4fc..0x518] を更新する。
+#   fn_10002ee0: thiscall (ecx = this、float a0、int a1 = 添字 0..15) ret 8。 [ecx+a1*4+0xb0..0x1f4] を読み書きし、ST(0) を残して返る。
+#   fn_10005400: thiscall (ecx = this、float a0..a2) ret 0xc。 fcomp・fnstsw・fdivr を含み、[ecx+0x4fc..0x518] を更新する。 gen が積む a3・a4 (と a5 = 0) は本体が読まない余りの引数。
 TARGETS = [
     {'va': 0x10002EE0, 'name': 'fn_10002ee0', 'gen': 'idx_store'},
     {'va': 0x10005400, 'name': 'fn_10005400', 'gen': 'state_update'},
diff --git a/tools/plugins/slayer_engine_ia32/x87_fn_native.c b/tools/plugins/slayer_engine_ia32/x87_fn_native.c
index 72a788e2c..80d069f06 100644
--- a/tools/plugins/slayer_engine_ia32/x87_fn_native.c
+++ b/tools/plugins/slayer_engine_ia32/x87_fn_native.c
@@ -1,6 +1,6 @@
 /* x87_fn_native.c: x87 を含む Slayer_Engine.dll (block22434) の関数の参照ランナー (#2989)。
  * native_entry.c と同じ方式 (freestanding i386 ELF・int 0x80 のみ) だが、x87 を含む関数のために
- *  - 引数は 6 本 (stdcall の float 引数を含む)、 OBJ 窓は OBJ_WIN バイト (既定 0x540)、
+ *  - 引数は 6 本 (スタック渡しの float 引数を含む)、 OBJ 窓は OBJ_WIN バイト (既定 0x540)、
  *  - 呼出し前に fninit、呼出し後に ST(0) を float32 として読み (fsts)・x87 の深さを FSW.TOP から求める。
  * 使い方: x87_fn_native <image.bin> <scen.txt> <out.txt>
  * 出力 1 行: 行番号 va eax st0(float32 bits) d(x87 深さ) mem(OBJ 窓の hex)。 */
```

検証 HEAD は PR 本文の『検証 HEAD』欄が正 (付録の commit 自身では hash を書けないため)。 `0x10005400` の逆アセンブル根拠 (`objdump -d -M intel`・`pei-i386`): `sub esp,0x8` の後の `[esp+0xc]`・`[esp+0x10]`・`[esp+0x14]` が entry の `[esp+4]`・`[esp+8]`・`[esp+0xc]` (a0・a1・a2) に当たり、`call` を含まず、`add esp,0x8` の後に `ret 0xc`。 `0x10002ee0` は `call` を含まず、`ret 0x8`。 両方とも `[ecx+...]` を基底にする (thiscall)。

## 6. 範囲と未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 残りの leaf x87 関数 36 本 (lift 済み・import と call が無い) の差分試験 | 対象の 2 本以外の x87 の命令組合せは未確認。 本付録の 2 本で受入は満たす | #3715 (PLG-G2-31・子。親 #2989) |
| 超越関数・`frndint`・`fscale`・`fprem` 等を含む関数 (lift が `ott_unsup` のまま) | 対象外 | #2966 (PLG-G2-23) |
| `fld`/`fstp` m80 の差分試験 | 80bit メモリ経路は未試験 | #2967 (PLG-G2-24) |
| 例外値 (NaN・inf・非正規・±0) の NaN どうしのビット差 (符号・ペイロード)。 数値どうしは float32 で全行一致 (§7) | NaN の値そのものは一致しない。 本試験は後段の値を検査していないので、この差が後段の結果を変えるかは判定していない。 残課題は §10 | #5263 (PLG-G2-72・親 #4744)。 PM agent の判断待ち: NaN どうしのビット差を許容するか・既定案: 許容 (非決定の源は §9.1 で特定済み。#142 の許容は IPP の話で x87 には当てはまらない)。 判断・後段の検査の追跡は #5264 (PLG-G2-73) |
| export `main`・import を通る関数・実行時の間接 call・`sahf` の AF・`fs:` (TEB) | 関数単位の残り (x87 以外も含む) | #3127 / #3128 |
| f80→f64 の丸め差 (ST(0) の double で 1 ulp 以上。分布は §1 参照) | float32 結果には伝播しなかった。 方式の帰結 | ADR D28 (方式)。 行案 D24 (案) は `REPORT_APPENDIX_1099.md` §6 |

## 8. ebp 相対のスタック書込みと空スタック (#4146 PLG-G2-49)

- 測定 commit `bd20dd255` (main 取り込みの merge。 判定器・TARGETS・stk 窓・ebp を変えた最後の commit)。 検証 HEAD は同じ。 再現は `cd tools/plugins/slayer_engine_ia32 && python3 x87_fn_diff.py` (+ `--nega`・`--nega-lower`・`--special`・`--special --nega-nan`)。
- 判定器: 非自明性を「OBJ 窓が変わった」に加え「guest スタックの窓 `[0x10EFEF00, 0x10EFF0E0)` (ebp-0x100..ebp+0xE0) が変わった」も数える。 両 runner は `ebp = 0x10EFF000` (`GUEST_STACK_TOP - 0x1000`。 main の #4088 `e4514bf39` の設定) を置き、窓を事前に 0 にして、`stk=` として出す (native `x87_fn_native.c`・wasm `x87_fn_glue.c`・`x87_fn_entry_wasm.mjs`)。 `ebp=0` では `[ebp-0x90]` が負のアドレスになり native が SIGSEGV するため、呼出し元の frame を模した値にした。
- 追加した 2 本: `fn_1000b6c1`・`fn_1000b936` (OBJ 窓を書かず、ebp 相対のスタックだけを書く)。 入口で空の ST(0) を読まない (`fstp st(0)` で捨てるだけ) ので underflow に依らない。

| 関数 | n | 構造 (eax・深さ) 不一致 | 行の全項目が bit 一致 | 非自明 (OBJ か stk が変化) | ST(0) float32 | OBJ 窓 + stk 窓 (float32 語 1,824,000 語) |
|---|---:|---:|---:|---:|---|---|
| `0x10002ee0` | 4,000 | 0 | 3,890 (97.25%) | 4,000 | 全行一致 | 全語一致 |
| `0x10005400` | 4,000 | 0 | 3,405 (85.12%) | 4,000 | 全行一致 | 全語一致 |
| `0x1000b6c1` | 4,000 | 0 | 4,000 (100.00%) | 4,000 | 全行一致 | 全語一致 |
| `0x1000b936` | 4,000 | 0 | 4,000 (100.00%) | 4,000 | 全行一致 | 全語一致 |

- 判定器の負の対照: OBJ 窓もスタック窓も変わらない行を入れると `ok = False` (検出)。
- ネガコン (通常): `--nega` 通過 (bit 一致 15,295 → 15,294、exit 0)、`--nega-lower` で `f_10002ee0` の float32 不一致 4,000 / 4,000 (exit 0)。
- ネガコン (例外値): `--special` PASS (exit 0)、`--special --nega-nan` で `nan-num` 0 → 1 (判定 FAIL、exit 0 = 検出)。

### 空スタック (underflow) の 3 本の決定

- 判断: `0x1000b8cd`・`0x1000b8cf`・`0x1000b8f7` は **範囲外**として扱い、TARGETS に入れない。 wasm 側で native の -qNaN を再現することはしない。
- 根拠 (実測): 3 本とも入口で空の ST(0) を `fstp` / `fld TBYTE` する。 同じ入力での突合 (`uf_probe`、4,000 行ずつ) は、ST(0) の float32 が全行 native `nan-num`・wasm の 0 になり、OBJ 窓の 1 語 (`nan-num` 4,000) も同様に食い違う。
- 1000b8a2 も同じ類型: 入口の `fstp TBYTE [ebp-0x9e]` が空の ST(0) を読み、native は `ffff c000…` (x87 indefinite) を書いて `[ebp-0x97]&0x40` の分岐を変える。 wasm は 0 を書くので分岐が変わる。 TARGETS に入れると `nan-num` の mismatch で FAIL するため除外した (`0x1000b8a2` 0 / 4,000 bit 一致、構造は一致)。
- 類型: `ott_x87.h` の制限 (4) (over/underflow を模型化しない) の範囲外。 既存の DEFECTS 行は立てていない (`docs/DEFECTS.md` は同 PR で編集しない)。 DEFECTS への類型追加は起票先 (下の表)。

## 7. 例外値 (#3716 PLG-G2-32)

- 測定 commit `661530759` (ネガコン `--nega-nan` を加えた最後のコード commit。 判定器の `--special` は `18a5dced7` のまま)。 検証 HEAD は同じ。 `python3 x87_fn_diff.py --special` (exit 0、wall 8.11 s、load1 0.33)。 通常モード (`python3 x87_fn_diff.py`、exit 0、wall 7.57 s、load1 0.13) も同じ commit で再現し、§3 の数値と一致した (`0x10002ee0` 3,890/4,000、`0x10005400` 3,405/4,000)。 `--nega`・`--nega-lower`・`--special --nega-nan` も同じ commit で exit 0。
- 入力: 別の乱数系列 (seed 2990) で各関数 4,000 行。 `a0` は NaN (±・signaling)・±inf・最小の正の非正規・最大の負の非正規・±0 を巡回させる。 OBJ 窓の語の 1/4 も同じ集合から選ぶ。 `fn_10005400` の a1・a2 も 1/2 で例外値。 通常行 (§3) の列は変えていない。
- 判定の追加: NaN どうしのビット差 (`nan`) と、NaN と数値の混在 (`nan-num`) を分けて数える。 `nan-num` が 1 件でもあれば PASS しない。 NaN どうしの差は構造の判定 (eax) から外して別計上する。

| 関数 | n | eax 不一致 (数値) | eax 不一致 (NaN どうし) | x87 深さ不一致 | ST(0) float32 の一致 / NaN どうし / 数値の 1ulp 以上 / NaN と数値の混在 | OBJ 窓 float32 語の NaN どうし / 混在 |
|---|---:|---:|---:|---:|---|---|
| `0x10002ee0` | 4,000 | 0 | 0 | 0 | 3,539 / 461 / 0 / 0 | 906 / 0 |
| `0x10005400` | 4,000 | 0 | 622 | 0 | 3,459 / 541 / 0 / 0 | 4,134 / 0 |

- 数値どうしの float64 の差 (ST(0) の double): `0x10002ee0` で 2 件、`0x10005400` で 28 件 (いずれも 1 ulp)。 float32 では全て一致。 f80→f64 の丸め差 (ADR D28)。
- NaN どうしの差: `eax` と ST(0) の NaN の符号・仕様ビットが native と wasm で違う行がある (例: native `7fc00000`・wasm `ffc00000`、native `7fc00001`・wasm `ffc00000`)。 原因は本付録では切り分けていない (どちらが実 FL の x87 の値と一致するかも未確認)。 本付録の判定では NaN どうしのビット差を数値の判定に使わない (値の一致は要求しない)。 後段の値は検査していないので、この差が後段の結果を変えるかは未確認。 この扱いを許容するかは PM の判断が要る。
- 非自明性: 4,000 / 4,000 行で OBJ 窓が変わった (§3 と同じ)。
- ネガコン (通常): `--nega` (bit 一致 7,295 → 7,294、exit 0)、`--nega-lower` (`f_10002ee0` の演算取り違えで float32 不一致 4,000 / 4,000、exit 0) とも検出。
- ネガコン (例外値): `--special --nega-nan` で wasm の NaN 1 語 (行 0 の ST(0)) を 1.0 に置換 → `nan-num` 0 → 1、判定 FAIL (exit 0 = 検出)。 測定 commit `661530759` (§7 の先頭行)。
- 判定器の誤りを 1 件修正した: 初版は NaN どうしの差も構造の不一致として数えたため、特殊値モードが FAIL した。 数値の差と NaN どうしの差を分けて、この FAIL を解消した (判定の変更は `18a5dced7`)。 NaN と数値の混在は 0 件で、判定はこれで通す。
- NaN どうしの差の切り分け (#4756 PLG-G2-60・CLOSED): 源は §9.1 (#4775)、残課題は §10 (#5264 PLG-G2-73 で追跡)。

## 9. 特殊値の不一致行の分類 (#4743 PLG-G2-58)

- 測定 commit `63b9e06ab` (`x87_fn_diff.py` に `mismatch_classes` を加えた最後のコード commit。判定の条件は変えていない)。 検証 HEAD と再測定は §11 を参照。 `python3 x87_fn_diff.py --special` (exit 0、wall 20.3 s、load1 0.45)。 `--special --nega-nan` (exit 0、ネガコン検出)。 通常モード (`python3 x87_fn_diff.py`、exit 0) も同じ commit で §3 と一致した (`0x10002ee0` 3,890/4,000、`0x10005400` 3,405/4,000)。
- 入力: `--special` の 20,000 行 (seed 2989 の特殊値系列)。 行の不一致は次の 3 種だけで、`other` (それ以外) は 0 件。

| 関数 | NaN どうしのビット差 | float64 のみ 1〜2 ulp (float32 は一致) | 計 |
|---|---:|---:|---:|
| `0x10002ee0` | 858 | 2 | 860 |
| `0x10005400` | 876 | 28 | 904 |
| `0x10005d20` | 506 | 0 | 506 |

- 判定の数値 (PASS・構造・nan-num 0) は前節 §7 と同じ。 NaN どうしのビット差は判定に入れず、本節の分類で別計上する。
- 残り (NaN どうしのビット差の原因切り分け・後段への伝播) は #5264 (PLG-G2-73)。 後段の未検査も #5264 で扱う (§10.3)。

### 9.1 揺れの源 (#4775 PLG-G2-61)

- 測定 commit `a4f7e12f0` (`x87_fn_diff.py` の `WASM_TIER` 固定を入れた最後のコード commit)。 `python3 x87_fn_diff.py --special` (exit 0、wall 19.5 s、load1 0.46)。 通常モード・`--nega`・`--special --nega-nan` も同じ commit で exit 0 (ネガコン検出)。
- 揺れの再現 (修正前、tier 未固定): 同じ `scen.txt` の先頭 8,000 行を同じ wasm・同じ image で 6 回実行すると、出力の md5 が 5 種に割れた (6 回中 2 回は一致)。 揺れは行単位で、同じ行が `ffc00000` と `7fc00001` を返す。 数値 (非 NaN) の差は 0 件。
- 切り分け (先頭からの接頭辞ではなく、単独の probe で ops ごとに確認した):
  - probe の原本: `probes/nanprobe/probe_tier.mjs` (追跡対象・依存なし。wasm のバイト列を直接組み立てる)。 実行: `node --liftoff-only probes/nanprobe/probe_tier.mjs > liftoff.txt` と `node --no-liftoff probes/nanprobe/probe_tier.mjs > turbofan.txt` の後に `diff liftoff.txt turbofan.txt` (emcc 不要。node 22.23.3 で実測)。
  - 実測 (`probe_tier.mjs`・入力は float32 の 8 値 (NaN 5 種 = qNaN・-qNaN・sNaN・ペイロード違い・0xffffffff、1.0、±0) の全組、f32 add/sub/mul/div と f64 add/sub/mul、promote・demote・neg): 出力 467 行、Liftoff と TurboFan で 72 行が違う。 違いは f32_add・f32_mul・f64_add・f64_mul の 18 行ずつで、すべて両オペランドが NaN の行 (NaN 以外の入力を含む行は 0 件)。 `sub`・`div`・単項・変換は両 tier で一致。 LDF32 と `(float)` 変換は源ではない。
  - 6 回の再現: 同じ probe を `--liftoff-only` で 6 回実行すると md5 `5c49732b…` が 6/6 同一。 `--no-liftoff` でも 3/3 同一 (md5 `1e471b8b…`、Liftoff とは別の値)。
  - 結論: 源は V8 の tier 切替で、NaN×NaN の返す NaN の選び方が tier で違う。 wasm の NaN の符号・ペイロードは仕様で未規定。
- 固定の確認 (受入の「同じ入力で 6 回以上」): 正は `--liftoff-only` で 20,000 行の run を 6 回取った md5 `5254ee2f…` (`1f7ba1bfb` の 6/6・§10.2)。 本節の旧記述 `23fc7196…` (6/6 同一) は**記録の誤り** (#5263 で訂正)。 `23fc7196…` は同じ条件で再現せず、出所 (条件) も記録から特定できない。 再測定の結果は `a4f7e12f0` (3 回・node 24 / 2 回・node 22) も `5254ee2f…`。 `--no-liftoff` の値は `5254ee…` とは別 (未測定の値は書かない)。 固定の根拠は §10.2 の記録。
  - 入力の出所: `scen.txt`・`image.bin` は `x87_fn_diff.py --special` が seed 2989 と素材 `block22434_PE.bin` (`FL_WIN64_DIR`、`fl-win64` の `extracted/`) から毎回生成する (`work/x87fn_special/`、gitignore)。 生成は決定的で、同じ素材・同じ seed なら同じ `scen.txt` になる。 `wasm_out.txt` の md5 の正は §10.2 (`5254ee2f…`)。 再現手順は `x87_fn_diff.py --special` を実行し、その `work/x87fn_special/wasm_out.txt` を取り直す (`toolchain-emsdk` と `fl-win64` が要る)。
  - 再確認 (#5263): 同じ tier 固定の効果を単独 probe で 6 回測定した (上の probe の項)。 両 tier は NaN ビットだけが違い、native 対 liftoff の NaN 以外の差は 0 件 (8,000 行で確認)。 20,000 行の md5 は §10.2 の再測定 (`1f7ba1bfb`・`a4f7e12f0`・`6bc58a66d`) で取り直した。
- 修正前後の判定への影響: 判定 (PASS・構造・nan-num 0) は変わらない。 mismatch 分類の件数は run ごとに揺れた。 固定後の基準値 (`a4f7e12f0`、2 回とも一致): `fn_10002ee0` NaN どうし 858・f80 2 行、`fn_10005400` NaN どうし 701・f80 28 行、`fn_10005d20` NaN どうし 458。
- 後段への伝播 (固定後の wasm 対 native。 NaN どうしの差のみ。 非 NaN の差は全関数 0 件):
  - `fn_10005400`: `eax` の NaN どうし 622 行。 OBJ 窓の NaN どうし 4,134 語 (うち `[0x508..0x518)` の範囲は 1,948 語)。
  - `fn_10002ee0`: ST(0) の NaN どうし 461 行、OBJ 窓 906 語。 `fn_10005d20`: ST(0) 284 行、OBJ 窓 1,320 語。
  - 分岐 (`fcomp`→`fnstsw`→`test ah`) への影響は §10.1 で検査済み (影響なし)。 値を読む後段の演算は本 issue では検査しない (§10.2・§10.3)。
- 判断案 (PM の判断が要る): **許容** を推す。 理由: (1) 揺れの源は wasm の NaN 符号の未規定と V8 の tier で、ロジックの誤りではない。 (2) 非 NaN の値は全件一致。 (3) tier 固定で再現する。 ただし `eax` の NaN どうしと OBJ 窓の NaN どうしが実 FL の値と一致するかは未確認。 本件の判断は #5264 (PLG-G2-73) で追跡する。後段の未検査の起票先も #5264 (§10.3)。
- 注: 受入の「先頭から揺れた行までの接頭辞での再現」は、接頭辞の二分探索ではなく ops 単位の probe で代えた。 揺れの源は ops で確定したので、接頭辞の再現は行わなかった。
- 再測定 (#4756 レビュー対応・測定 commit `3bf12f0c2`・emsdk 6.0.12 を上流から導入して実 emcc で実行): `x87_fn_diff.py --special` を 2 回。 exit 0・PASS、wall 16.1 s / 16.9 s、分類は両回とも `fn_10002ee0` NaN どうし 858・f80 2、`fn_10005400` 701・28、`fn_10005d20` 458。 wasm 出力の md5 は 2 回とも `5254ee2f…` (§9.1 の 20,000 行の値と一致)、native は `cca1f57e…`。 `--special --nega-nan` (exit 0、nan-num 0 → 1、判定 FAIL = 検出)。 通常モード (exit 0、`fn_10002ee0` bit 一致 3,890/4,000、`fn_10005400` 3,405/4,000)。 `--nega` (exit 0、bit 一致 15,495 → 15,494、検出)。 `--nega-lower` (exit 0、OBJ 窓が変わった行 4,000/4,000)。 ※ `--nega` は通常モードの出力 (`work/x87fn/`) を前提にするため、先に通常モードを実行した。
- lift 経路 (`lift_text.py`、実 emcc): 70b68ebc9 は第 2 パスの追加 roots 5 個 (`ott_lifted.c` 2,384,521 B)、`3bf12f0c2` は 9 個 (2,400,299 B)。 増えた 4 個 (`0x1000ea92`・`0x1000eaac`・`0x1000eab4`・`0x1000eb8c`) で関数 355 行が追加された。 対象 3 関数 (`f_10002ee0`・`f_10005400`・`f_10005d20`) の本体は md5 が両版で一致。 `x87_fn_diff.py --special` の分類件数は両版で同じ (上の再測定)。

## 10. NaN どうしのビット差の残課題 (#5264 PLG-G2-73)

源の特定 (V8 の tier 切替) は §9.1 (#4775・PR #4795) が正。 6 回の固定の確認と md5 の正は §10.2 (#5263 で訂正)。 本節は残る未検査の範囲と判断だけを書く。 未検査の範囲の起票先は #5264 (PLG-G2-73)。

### 10.1 分岐への NaN の伝播 (#5264 PLG-G2-73)

- 測定 commit `1f7ba1bfb` (`x87_branch_nan.py` を加えた最後のコード commit。 `x87_fn_diff.py` は `d6982bccc` から変えていない)。 検証 HEAD は同じ。
- 方法: `x87_branch_nan.py` が 14 値 (NaN 5 種・±inf・±0・非正規 2 種・通常 3 種) の全 196 組について、実 x87 (`fcomps` → `fnstsw`) と `tools/ott/rt/ott_x87.h` の `x87_fcom` (lift の `fcomp` と同じ経路) の C3/C2/C0 を比べ、`test ah,0x41` → `je` の分岐の真偽も比べた。
- 実測: NaN を含む組 115 件。 native と model の C3/C2/C0 の不一致 0 組。 NaN を含む組は 115/115 で unordered (C3=C2=C0=1)。 分岐 (真偽) の不一致 0 組。 PASS。
- lift の対象: `fn_10005400` の `fcom` は ST(0) と定数 `0x10013578` (0.9) を比べ、`test ah,0x41`・`jne` で分岐する。 `fn_10002ee0`・`fn_10005d20` には `fcom` が無い。
- 突合の行 (20,000 行、`x87_fn_diff.py --special`) では、`eax` の数値どうしの不一致が 0 行 (3 関数とも)、非 NaN の ST(0)・OBJ 窓の差が 0 語。 NaN どうしの差だけが出ている。 これは分岐の違いが結果に出ていないことを示すが、分岐そのものを直接は観測していない。 分岐の一致は次の点で示す。
- 結論: NaN との比較は符号・ペイロードに依らず unordered になり (probe で 115/115)、分岐 (`fn_10005400` の `jne`) は native と一致する。 分岐への NaN 伝播は、この harness の範囲で影響なし。

### 10.2 `eax`・OBJ 窓の NaN どうしと実 FL の値 (#5264 PLG-G2-73)

- 基準: 実 FL の x87 (Windows の `Slayer_Engine.dll`) は本 runner では実行できない。 本 issue の定義どおり、基準は native の x87 命令 (`x87_fn_native.c`) とする。 以下は native との一致を見る。
- 測定 commit `1f7ba1bfb`、`x87_fn_diff.py --special` を 6 回実行 (exit 0・PASS。 wall は 1・2 回目が 15.0 s・14.8 s)。 wasm 出力の md5 は 6/6 で `5254ee2f…`。 native 出力の md5 は `cca1f57e…` (PR #4779 本文の記録と一致。 再計測は 1 回のみ)。 mismatch の件数は 6 回とも §9.1 と一致 (`fn_10002ee0` 858・`fn_10005400` 701・`fn_10005d20` 458、f80 は 2・28)。 件数と 6/6 の再現が受入の根拠。
- 食い違いの解消 (#5263・2026-10-15、commit `6bc58a66d`・ws-5263 で再測定): 同じ HEAD で `x87_fn_diff.py --special` を 6 回 (exit 0・PASS・wall 20〜28 s)。 wasm md5 は 6/6 で `b7172a8b…`、native は 6/6 で `2942c957…`。 この HEAD は 7 関数・28,000 行の版 (`fn_100052d0`・`fn_10005550` を含む) で、`1f7ba1bfb` (5 関数・20,000 行) とは入力が違うため直接比べられない。 同じ条件の比較として `1f7ba1bfb` (2 回) と `a4f7e12f0` (3 回) を再実行すると、どちらも wasm `5254ee2f…`・native `cca1f57e…` で、20,000 行・6/6 の記録と一致した (node 24.19.0)。 `a4f7e12f0` は node 22.23.3 でも 2 回とも `5254ee2f…` (`--liftoff-only` の既定)。 `23fc7196…` は再現しなかった。 判定: §9.1 の `23fc7196…` は記録の誤り (訂正済み)。 `5254ee2f…` が `a4f7e12f0`・`1f7ba1bfb` の正の値。 残る未解決 (NaN どうしの許容・後段の算術) は #5264 (PLG-G2-73) と PM 判断 (§10.3)。
- NaN どうしの差 (`--special` の全 5 関数・20,000 行の合計。 `eax` の 622 件は全て `fn_10005400`):

| 場所 | sign のみ | payload のみ | 計 | NaN と数値の混在 |
|---|---:|---:|---:|---:|
| `eax` | 223 | 399 | 622 | 0 |
| ST(0) (float32) | 525 | 761 | 1,286 | 0 |
| OBJ 窓 (float32 語) | 2,072 | 4,288 | 6,360 | 0 |

- 差の出所 (入力): `x87_nan_bits.py` の分類で、NaN どうしの差は入力に NaN・±0・±inf のいずれかを含む行だけに出る (`fn_10005400` で `eax` の差 365 件は NaN を含む入力)。
- 判定: `eax` と OBJ 窓の NaN どうしは native と一致しない (1 件でも不一致なら一致と言えない)。 数値の値 (非 NaN) は全件一致。 NaN の符号・ペイロードだけが native と違う。
- 未確認: この NaN の値を読む後段の算術 (NaN の伝播先の値を使った計算) は未検査。 分岐は 10.1 のとおり影響なし。

### 10.3 残課題 (PM 判断)

- **判断 (PM・#5264 受入 1・R7 (a)①)**: NaN どうしのビット差 (符号・ペイロード) は**許容する**。 既定の挙動・既存の数値は変えない。 根拠は §9.1 の判断案と 10.1・10.2 の実測、`REPORT_APPENDIX_5264.md` §5。 数値 858・701・458 は測定 commit `6bc58a66d` の時点の値 (§9.1 の基準値とも一致する)。 ただし `6bc58a66d..HEAD` で `x87_fn_diff.py` の `--special` の実行経路が変わっている (`417548895` #4858: TARGETS に `0x1000bf1e` を追加、`1b5eb4899` #4924: ecx 基底の書込みの数え方、`93ca2520c` #5464: 行末書込み対応と `wide_patch` 入力)。 このため現 HEAD の値としては書かない。 現 HEAD の再測定は未実施 (emsdk 等の素材が本 run に無い)。 数値を現 HEAD で取り直すのは後続の作業 (次の run)。
- **未確認 (R7 ④)**: 実 FL の x87 (Windows の `Slayer_Engine.dll`) との NaN ビット一致は、本 runner では確認していない。 基準は native の x87 命令のみ。 この点は未確認のまま、許容の既定で進める。 一致が必要になった場合は、差の原因切り分け (wasm の NaN 符号・ペイロードの規定) から新しい issue が要る。
- 起票先: 10.2 の後段の算術 (NaN を読む演算) の検査は、判断の結果に応じて PM が決める (本 issue では検査しない)。
- 後段の算術の実測 (#5264 PLG-G2-73): `REPORT_APPENDIX_5264.md`。 四則・符号・絶対値・比較・連鎖で、NaN どうしの差は NaN ビットにだけ出て、非 NaN の結果と比較には 0 件。 許容の判断 (上の項目) で、この突合が後段の受入 (許容時の突合) を満たす。

## 11. 測定 commit と検証 HEAD の記録 (#4744 PLG-G2-59)

- 測定 commit: `cfd295fa1` (`origin/main`・PR #5245 取り込み後)。 検証 HEAD: 本節を含む commit (docs のみ)。 測定 commit からのコード差分は `git diff --name-only cfd295fa1 HEAD -- tools/plugins/slayer_engine_ia32 tools/ott/lift tools/ott/rt` で REPORT 以外に 0 ファイル (REPORT のみ変更)。
- §9 の測定 commit `63b9e06ab` の後に、試験のコードを変える commit が入っていた。 `git diff 63b9e06ab cfd295fa1 -- tools/plugins/slayer_engine_ia32/x87_fn_diff.py tools/plugins/slayer_engine_ia32/x87_fn_native.c tools/plugins/slayer_engine_ia32/x87_fn_glue.c tools/plugins/slayer_engine_ia32/x87_fn_entry_wasm.mjs tools/plugins/slayer_engine_ia32/lift_text.py tools/ott/lift tools/ott/rt` の `--stat` (全文の diff は同じコマンドで出る):

```
 tools/ott/lift/x64c.py                             |   3 +
 tools/ott/rt/ott_cpu.c                             |  16 +++
 tools/ott/rt/ott_cpu.h                             |   8 ++
 tools/ott/rt/ott_x87.h                             |   9 +-
 tools/plugins/slayer_engine_ia32/lift_text.py      |  16 ++-
 tools/plugins/slayer_engine_ia32/x87_fn_diff.py    | 123 +++++++++++++++++++--
 .../slayer_engine_ia32/x87_fn_entry_wasm.mjs       |   4 +-
 tools/plugins/slayer_engine_ia32/x87_fn_glue.c     |   9 ++
 tools/plugins/slayer_engine_ia32/x87_fn_native.c   |  13 ++-
 9 files changed, 180 insertions(+), 21 deletions(-)
```

- 再測定 (HEAD `cfd295fa1`・素材 `fl-win64` の `block22434_PE.bin`・`toolchain-emsdk` 6.0.12 の実 emcc・`lift_text.py` で lift を作り直した後):
  - `python3 x87_fn_diff.py --special`: exit 0・PASS、wall 37.2 s (emcc のビルドを含む)、開始時 load1 1.12。 入力は 7 関数 × 4,000 = 28,000 行 (TARGETS の現行版。 §9 の 20,000 行は 5 関数の版)。
  - `--special --nega-nan`: exit 0 (ネガコン検出: 行 0 の NaN を 1.0 に置換 → `nan-num` 0 → 1、判定 FAIL)、wall 16.4 s。
  - 通常モード (`python3 x87_fn_diff.py`): exit 0・PASS、wall 19.5 s。 `fn_10002ee0` bit 一致 3,890 / 4,000、`fn_10005400` 3,405 / 4,000 (§3 と一致)。
- 特殊値モードの NaN どうしのビット差 (§9 の分類と同じ形式): `fn_10002ee0` 858 行 (f80 1〜2 ulp 2 行)、`fn_10005400` 701 行 (f80 28 行)、`fn_10005d20` 458 行。 追加の 2 関数: `fn_100052d0` 692 行 (f80 9 行)、`fn_10005550` 697 行 (f80 29 行)。 `eax` の数値どうしの不一致と x87 深さの不一致は、7 関数すべて 0 行。
- `fn_10005400` の NaN どうし 701 行・f80 28 行と、`fn_10005d20` の 458 行は §9.1 の固定後の基準値 (`a4f7e12f0`) と一致する。 §9 の表の 876・506 は固定前の測定値で、この節の値とは別である (§9.1 の揺れの記録)。 ただし §9 の `--special` 20,000 行と今回の 28,000 行は TARGETS が違うため、件数の直接比較はできない。 件数の数値は同じ HEAD の再測定値を正とする。
- 本節の数値はすべて HEAD `cfd295fa1` の出力 (`work/x87fn_special/`)。 `wasm_out.txt` の md5 `b7172a8b…` は、§9.1・§10.2 の `5254ee2f…` (20,000 行・5 関数版) とは別の入力 (7 関数版) の出力で、直接比べられない。
