# ildsp (`block24360_PE.bin`) 規模調査

自動生成ではない。再現コマンドは下記。親: #161 (T-SH-15) / 本件: #791 (T-SH-19)。

## 再現

```
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/scripts/ildsp_survey.py
```

- 入力: `$FL_WIN64_DIR/extracted/block24360_PE.bin` (win64 PE, 4,197,376 B)
- 依存: `capstone`・`pefile` (`uv venv` + `uv pip install capstone pefile`)
- 出力: 表を標準出力へ、JSON を `tools/shared/work/raw/ildsp_survey.json` (gitignore)
- 所要: 実測 `real 0m3.620s` (Python 3.14 / capstone 5.0.7 / pefile 2024.8.26、入力 sha256 f4b23b0f…、HEAD 検証時)

## 1. 全体 (実測)

| 項目 | 実測 |
|---|---:|
| `.text` 命令数 (線形走査・仮想サイズ) | 362,280 |
| `.pdata` 関数数 (生データ読み) | 2,622 |
| 直接 call / 間接 call | 5,898 / 848 |
| 間接 call 比 | 12.6% |
| `IPPCODE` 命令数 | 129,192 |
| `IPPCODE` SIMD 比 | 70.0% |
| `.text` SIMD 比 | 48.68% (176,373 / 362,280) |

上表は script 出力 (JSON: `text_instructions` 362280 / `simd_ratio` 0.4868 / `ippcode_instructions` 129192) と一致する。同一入力 (sha256 f4b23b0f…) で 2 回実行し JSON が完全一致 (`cmp` で確認) したため決定的。旧 REPORT の 362,277 / 129,188 は script で再現しなかった (下記未解決を参照)。

### 未解決: `.text` SIMD 比の定義

旧 libreverb REPORT §6 にあった 111,346 (30.7%) を再現する定義は見つからなかった。試した定義と件数:

- `xmm`/`ymm`/`zmm` を含む全命令: 176,373
- 同上から GPR↔XMM の move を除外: 168,168 / 140,996 (スカラー ss/sd を除外)
- `simd_stats.py` の分類 (avx512 / avx_256 / avx_128 / sse_packed / sse_scalar): 176,373 (`sse_other` 除く 175,346)
- `.pdata` 関数の範囲に限定: 260,600 / 464,542 (56.1%)
- packed 演算のみ (`*ps`/`*pd`): 125,570

いずれも 111,346 とは一致しない。REPORT の値の出典 (別の母集団・別の定義) を特定できていない。定義を推測で作ることはしない。**起票先: #161 継続 (REPORT §6 の SIMD 比の出典を確認)**。

## 2. export 単位 closure 規模表

closure = export entry の関数 (`.pdata` 境界) から、直接 call と直接 jmp (別関数への tail) を辿った到達集合。間接 call は辿らず件数のみ数える。

| export | entry | 関数数 | 命令数 | SIMD 比 | 直接 call | 間接 call | 間接比 |
|---|---|---:|---:|---:|---:|---:|---:|
| GeneralPitchShifter_CreateInstance | 0x1aa290 | 8 | 238 | 8.8% | 14 | 4 | 22.2% |
| LimiterLite_CreateInstance | 0x1aa540 | 10 | 417 | 5.0% | 18 | 5 | 21.7% |
| Limiter_CreateInstance | 0x1aafd0 | 11 | 858 | 8.5% | 67 | 5 | 6.9% |
| LowFreqEnhancer_CreateInstance | 0x1ab3d0 | 140 | 10,307 | 4.2% | 540 | 61 | 10.2% |
| PSOLA_CreateInstance | 0x1ab540 | 8 | 238 | 8.8% | 14 | 4 | 22.2% |
| Shimmer_CreateInstance | 0x1ab810 | 44 | 1,765 | 2.3% | 155 | 37 | 19.3% |
| StereoEnhancer_CreateInstance | 0x1abca0 | 139 | 9,925 | 4.0% | 501 | 61 | 10.8% |
| TransientLooper_CreateInstance | 0x1abe00 | 9 | 289 | 0.0% | 24 | 6 | 20.0% |
| Transmitter_CreateInstance | 0x1ac260 | 12 | 1,020 | 8.9% | 101 | 64 | 38.8% |
| WaveformColouring_CreateInstance | 0x1ac470 | 10 | 762 | 27.4% | 17 | 4 | 19.1% |

- 最小: GeneralPitchShifter と PSOLA が同率 238 命令 (8 関数)。両者のバイト列は一致しない (sha1 713ff04f… / 0391d052…)。
- 規模の大きい 2 つ (LowFreqEnhancer 10,307 / StereoEnhancer 9,925 命令) は 140 / 139 関数。残り 8 件は 8〜44 関数。
- closure は間接 call を辿らないため、実到達はこの表より大きい可能性がある。
- 注意: `.pdata` 先頭でない entry は `owner()` で含む関数の先頭に正規化してから辿る。export の 10 件はすべて `.pdata` 先頭に一致した。
- 正本の関係: 本表の関数数・命令数は chained `.pdata` と `.pdata` に無い葉を辿らない下限。GeneralPitchShifter_CreateInstance の closure の正本は §4-5 (単独 36 関数・924 命令)。
- vtable 経由の実体 closure (`.pdata` の無い先を含む・10 export・検算 `ildsp_closure_check.py`) は `REPORT_CLOSURE.md` (T-SH-15 #161)。

## 3. 次の子 issue の起票案 (PM が起票)

最小 instance は **PSOLA_CreateInstance** (または GeneralPitchShifter_CreateInstance)。どちらも本表では 238 命令・8 関数 (下限。GeneralPitchShifter の正本は §4-5) で、lift と差分テストの初回対象に向く。ただし closure の間接 call 比が 22.2% あるため、間接 call の解決方法 (テーブル or 実行時 dispatch) を先に決める必要がある。

## 4. GeneralPitchShifter_CreateInstance の instance vtable (#2483 / T-SH-36)

既知類型との関係: 該当なし (逆アセと PE 読みのみ。lift・IR を作らないため D1a〜D23 の検出対象外)。
検証起点 commit: `9f403c97` (origin/main)。測定 commit (コードを変えた最後の commit): `703acac3` (検算の変更は `604507d5`・`703acac3`。生成 `ildsp_vtable.py` は `d36ac78f` から変更なし)。

### 結論 (1 行)
vtable (RVA 0x3dfcf8) は 6 slot。slot 0 は解放を伴う dtor、slot 1–3 は内部 3 関数への thunk、slot 4 は内部状態のクリア、slot 5 は `return 0`。**slot 1–3 と 5 の「どの method か」は静的には確定できない** (native 実行は子 issue)。

### 再現
```
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/scripts/ildsp_vtable.py
python3 tools/shared/scripts/ildsp_vtable_check.py tools/shared/work/raw/ildsp_vtable.json   # ALL OK で exit 0
```
入力: `block24360_PE.bin` (sha256 f4b23b0f…、4,197,376 B)。検算は pefile / capstone を使わず、PE ヘッダを struct で読み、固定バイト列で照合する (別実装)。

### 4-1. CreateInstance (0x1aa290) の呼出し規約 (静的事実)
- 引数は読まない (rcx / rdx を使わず `mov ecx, imm` で上書きする)。戻り値は rax。ms_abi 前提。
- `mov ecx,0x10` → 0x1ac9c0 (alloc) → rdi = ラッパ (16 B)。`lea rax,[rip+0x235a45]` の RIP 相対先が vtable (0x3dfcf8)、`mov [rdi],rax` で vptr を格納。
- `mov ecx,0x2f8` → alloc → rbx。`memset(rbx, 0, 0x2f8)` (0x1aef60、r8=0x2f8)。`[rdi+8]=rbx`。`return rdi`。内部オブジェクトには vptr を書かない。

### 4-2. vtable の 6 slot
| slot | 値 (RVA) | 種別 (実測) | 役割 (静的判定) | 根拠 |
|---|---|---|---|---|
| 0 | 0x1aa2e0 | 関数 (.pdata 3 chunk, 0x1aa2e0–0x1aa36d) | **解放を伴う dtor** (deleting dtor 相当。先頭に null 判定 `test rcx,rcx; je` があり、flag 判定なし) | 0x1aa2f3 で vptr を再格納 → 内部の 6 ポインタを解放 → 内部 0x2f8 B を `mov edx,0x2f8` で解放 → ラッパ 0x10 B を `mov edx,0x10` で解放 (0x1ac9b0 への sized 呼出し 2 回) |
| 1 | 0x1aa370 | thunk: `mov rcx,[rcx+8]; jmp 0x161fc0` | 内部 instance の method (**役割 未確定**) | 転送先 0x161fc0 は `mov [rsp+0x10],rbx` で始まる |
| 2 | 0x1aa380 | thunk: 同上 → 0x162760 | 同上 (**未確定**) | 転送先 0x162760 は `cmp edx,0xe` で始まる (edx が index の可能性・未確認) |
| 3 | 0x1aa390 | thunk: 同上 → 0x162f90 | 同上 (**未確定**) | 転送先 0x162f90 は `test edx,edx` で始まる (未確認) |
| 4 | 0x1aa3a0 | 関数 (0x1aa3a0–0x1aa46c) | **内部状態のクリア** | `[rdx+0x10]`・`[+0x18]`・`[+0x20]` (件数 `[+0x28]`) と `[+0x258]`・`[+0x260]` (件数 `[+0x244]`) の配列をゼロ化し、`[+0x284]`〜`[+0x2b0]` の複数フィールドと `[rdx]` を 0 にする |
| 5 | 0x1aa470 | 定数返し (`xor eax,eax; ret`) | `return 0` の no-op (**未確定**) | 3 B |
| (6) | 0x1803e6fc0 (VA) | `.rdata` の値 (`.text` 外) | vtable 終端 | JSON `end_in_text=False`。slot 数は 6 |

### 4-3. 検算 (ildsp_vtable_check.py・生バイト照合)
- vptr 格納の `lea` の RIP 相対先 = vtable / slot 0–5 の値 = JSON / slot 6 が `.text` 外 / thunk = `48 8b 49 08 e9 rel32` / 定数返し = `31 c0 c3` または `33 c0 c3` / dtor の `ba 10 00 00 00`・`ba f8 02 00 00` の直後に 0x1ac9b0 への `e8` / 関数範囲内の `e8` 走査と JSON の call 箇所の一致 / 間接 call = `ff 15 disp32` とスロット値・スロット領域の DIR64 reloc (§4-6)。
- 結果: **ALL OK (exit 0)**。
- 検算の範囲: 直接 call・間接 call・slot の宛先を生バイトで照合するが、closure の完全性は見ない (JSON が挙げた箇所の部分集合を見る)。`[closure_*] 参考` 行の closure 外 e8 = 1 件 (0x1b8435→0x1b89f2) は偽陽性: 0x1b8432 の `lea r8,[rbp-0x18]` (`4c 8d 45 e8`) の disp8 0xe8 を e8 の call と誤認したもの。
- ネガティブコントロール (JSON を壊して FAIL することを確認):

| 名前 | 壊し方 | 結果 |
|---|---|---|
| neg_thunk | slot 1 の thunk_target を 0x161fc1 | FAIL 1 件、rc=1 |
| neg_slotval | slot 2 の target_rva を 0x1aa381 | FAIL 3 件、rc=1 |
| neg_indslot | closure_with_slots の先頭間接 call (0x1ad63f) の slot_rva を 0x268261 (元は 0x268050) | FAIL 1 件、rc=1 |
| neg_reloc | PE のコピーで 0x268260 の DIR64 reloc エントリを ABSOLUTE (type 0) に変更 (`--pe` で差し替え、`pe_sha256` はそのコピーに合わせる) | FAIL 2 件、rc=1 (件数 15・0x268260 欠落) |

### 4-4. 実測 (測定 commit `703acac3`、4 core、load 開始前 0.11)
生成 + 検算を 3 回 (`ildsp_vtable.py` → `ildsp_vtable_check.py`、bash の `date` で計時・プロセス起動込み): 0.204 / 0.200 / 0.195 s (min–max 0.195–0.204 s)、rc 0/0 (3 回とも)、ALL OK、実行後 load 0.11。旧測定 (`d36ac78f`) は 0.263–0.265 s で、計時方法の差は未確認。

### 4-5. closure と issue 本文の数値
| closure | 関数 | 命令 | SIMD | 直接 call | 間接 call | 間接 jmp |
|---|---:|---:|---:|---:|---:|---:|
| CreateInstance 単独 | 36 | 924 | 21 | 95 | 10 | 5 |
| CreateInstance + 全 slot | 87 | 4,991 | 1,627 | 211 | 18 | 8 |

- 数え方: 関数 = `.pdata` の primary (CHAININFO で連結されたチャンクを束ねた単位)、または `.pdata` に無い葉 (int3 境界まで)。直接 call と関数外への直接 jmp を辿る。間接は件数のみ。命令 = 関数範囲の線形走査。
- 旧 issue 本文の「15 関数・473 命令・SIMD 11.4%・間接 call 4」は本 REPORT に出典が無く、上の定義では再現しない (定義未確認)。
- §2 の survey 表は `.pdata` の chained チャンクを束ねず、`.pdata` に無い葉を辿らないため **下限**。本節の値で読むこと。

### 4-6. 間接 call 4 件 (0x1aedc0 ×3・0x1b6f4c ×1) のスロット (静的事実)
| site | 所属関数 | スロット RVA | ファイル内の値 | 指す先 |
|---|---|---|---|---|
| 0x1aedf6 | 0x1aedc0 | 0x268260 | 0x1801cb5e0 | 0x1cb5e0 = `jmp rax` (trampoline。rax の値は静的に不明) |
| 0x1aee04 | 0x1aedc0 | 0x268088 | 0x3f3e5e | `.rdata` 内 (関数ではない) |
| 0x1aee4a | 0x1aedc0 | 0x268090 | 0x3f3e72 | `.rdata` 内 (関数ではない) |
| 0x1b6f6c | 0x1b6f4c | 0x268268 | 0x1801cb600 | 0x1cb600 = `jmp [rip+0x9cc5a]` → slot 0x268260 (= 0x1801cb5e0 = 0x1cb5e0 の `jmp rax`)。0x1aedf6 と同じ末尾に至る (rax は静的に不明) |

- スロット領域 (0x268000–0x268300) には DIR64 の再配置 (`.reloc`) が **16 件** ある: 0x268250・0x268258・0x268260・0x268268・0x268270・0x268280・0x268288・0x268290・0x268298・0x2682a0・0x2682b8・0x2682c0・0x2682c8・0x2682e0・0x2682e8・0x2682f0。0x268260 と 0x268268 は上の表の 2 slot で、0x268088・0x268090 には無い。ファイル内の値は既定 base (0x180000000) の VA で、ロード時に実 base とのずれ分だけ補正される。RVA に直した宛先 (0x1cb5e0 など) は実行時も同じ関数を指す。件数と位置は `ildsp_vtable_check.py` の `[.reloc]` 行 (生バイト走査) で再現する。pefile の full parse でも同じ 16 件を確認した (一時スクリプト・未コミット)。
- 結論: 宛先は静的に確定しない。0x268088 / 0x268090 はファイル内で関数を指さない。実行時に値が入るか、この経路に到達しないかのどちらかと推定 (未確認)。`CreateInstance 単独` の間接 call は計 10 件で、残り 6 件は 0x1b8820 / 0x1b900c / 0x1b9084 / 0x1b9c1c 内にある。

## 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| vtable slot 1–3・5 の役割 (どの method か) の native 実行による確定 | 受入条件 (1) の残り | 子 [T-SH-38] |
| 間接 call 4 件 (0x1aedc0 / 0x1b6f4c) の正常系での到達実測・扱いの決定 (4-6) | 受入条件 (3) | 子 [T-SH-38] |
| 15 関数 (closure は 4-5 の定義で 36 / 87 関数) の lift・native 差分・ネガコン・gate | 受入条件 (2)(4) | 子 [T-SH-39] |
| 旧 issue 本文の「15 関数・473 命令・SIMD 11.4%」の出典 | 本 REPORT で再現できない | #2483 本文から削除 (本 PR) |
| §2 survey 表が chained `.pdata` 未処理で下限 | §2 の数値は下限 | #161 継続 |
| `.text` SIMD 比 30.7% の定義・出典 | 旧 libreverb REPORT §6 の数値が再現できない | #161 継続 |
| 旧 REPORT 値 (362,277 / 129,188 / 10,305) の出典 | 現 script では再現しない (決定的な出力は 362,280 / 129,192 / 10,307)。旧値は別の版・別の script 状態の産物と推定するが未確認 | #161 継続 (旧値の出典確認) |
| closure の間接 call 先の解決 | 表の命令数は下限 | 起票案 (PSOLA lift) で扱う |
| ildsp の lift 本体 | #161 後半未達 | #161 継続 |

## 5. WaveformColouring_CreateInstance の x64c lift と native 差分 — T-SH-52 (#3216・部分達成)

既知類型との関係: 該当なし (`docs/DEFECTS.md` D1a〜D23 に VEX 未対応・jump table 未到達の記述は無い。差分は CreateInstance と slot 0 の範囲で 0 件)。
測定 commit: `d631564c` (コードを変えた最後の commit)。以降の差分は本節のみ (§5-8)。検証起点: `bea685f7` (origin/main)。

### 5-1 結論 (1 行)
closure の入口 70 関数は x64c で C に lift し wasm (138,754 B) にした (C 本体 60 + label 8 + IAT thunk 2)。CreateInstance → slot 0 の native 対 wasm は 64 case で全バイト一致。残りは slot 1–5 の host 前提 (native が null 参照で落ちる) と、VEX 3 命令の未対応 (unsup 3 site)。

### 5-2 再現
```
FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<toolchain-emsdk 展開先>/emsdk/emsdk_env.sh bash tools/shared/lift/ildsp/lift_wc.sh [ok|neg-cmp|all]
```
- 入力: `extracted/block24360_PE.bin` (sha256 `f4b23b0f…`)。素材は `tar --zstd -xf fl-win64.tar.zst extracted/block24360_PE.bin` で取る。
- 段: `x64c.py` (root = CreateInstance `0x1ac470` と vtable `0x3e01b0` の slot 先 `0x1a9cf0`・`0x1a9f10`・`0x1a9e10`・`0x1a9de0`・`0x1aa0b0`・`0x1ac460`、`--closure 99`) → `wc_image.py` (DIR64 補正・IAT pseudo-VA) → `wc_cases.py` (case 64 = 元の `.data` と数バイト書換え 63) → emcc 6.0.12 `-O1` → `native_ref.c` (gcc・ms_abi 直接実行) → `run_wasm.mjs` (node 22) → `diff_test.py`。
- vcall `0x1a9e2b` (`call [rax+0x18]` = slot 3 = `0x1a9de0`) は静的に束縛せず、x64c の `ott_dispatch` が実行時に vtable を読んで解決する。前提は instance の vptr が `0x3e01b0` (CreateInstance が `[rcx]` に置く)。
- runtime `fle_cpu.c` の既定 `imp_HeapAlloc` は host `malloc` を使い、native とポインタが一致しない。`lift_wc.sh` は `wc_glue.c` が定義する `imp_*` だけ `-D` で改名して除外し、決定的 bump heap の定義を使う。

### 5-3 実測 (測定 commit `d631564c`・HEAD で 3 回)
| 項目 | 値 |
|---|---:|
| x64c の lift 関数 (C 本体) | 60 (`unlifted callees` 0・imports 18) |
| closure 入口 70 のうち C に現れる | 70 (60 は `f_` 関数、8 は呼出元の関数内 label、2 は IAT thunk `jmp [rip+IAT]` = `imp_` 呼出 `0x1b932c`・`0x1b9334`) |
| closure の命令数 (`ildsp_closure.py` の定義・70 範囲の線形走査) | 2,757 |
| x64c が C に出した命令数 (`/* addr: */` 注釈で数えた) | 2,656 |
| closure にあって C に無い命令 | 109 = int3 77 + nop 14 + 非 padding 18 (うち IAT thunk 2) (§5-4) |
| C にあって closure に無い命令 | 8 (`0x1aef40`–`0x1aef4f`。x64c が辿るが JSON の closure 定義は辿らない) |
| unsup (`ott_unsup`) | 3 site: `0x1ca277` vcvtss2sd・`0x1ca33f` vpmovsxdq・`0x1ca34c` vshufps (いずれも closure 内。CreateInstance の実行経路には無い) |
| wasm | 138,754 B (`emcc` 6.0.12) |
| 差分 `ok` (CreateInstance → slot 0) | cases 64 / PASS 64 / FAIL 0 / native 落ち除外 0 / wasm trap 0 |
| 差分の観測値 | 戻り値の合成値 `0x5d9b00001` (= 返り値 `0x30500000`·31 + slot 0 の返り値 1) が両側で一致。import 呼出 1 回 (HeapAlloc 0x228 B) |
| ネガティブコントロール `neg-cmp` (wasm 結果の heap 先頭 1 bit 反転) | FAIL 64/64 (`arena@+0x0`)・rc 1 → 期待通り |
| 所要 `ok` (lift 無し・emcc 込みの 1 回) | 実測 1 s・1 s・1 s (load 開始 0.04–0.11・4 core)。ただし emcc の sysroot キャッシュ作成時は 9 s |

### 5-4 closure と lift の差 (未確定)
- 直接分岐の先になっていない非 padding 命令 16 件: `0x1ac9b8` (`0x1ac9b0` の後続)・`0x1b8eb1`–`0x1b8ec8` (`call 0x1be130` を含む 6 命令)・`0x1bd4b0`–`0x1bd4b7`・`0x1be14e`–`0x1be16c` (`ucomisd`・`cvtsd2si`・`ret` 等)。直接分岐の照合 (closure 内の jcc/jmp/call の先) は 0 件。間接 jump (jump table) の先か、到達不能のどちらか。x64c は認識した jump table しか辿らないため、ここでは確定しない。
- 到達した場合の挙動: 直接 call で届けば x64c が必ず lift する。`call reg` 経由で未 lift の先に届けば `ott_unlifted` で止まる (fail-fast。silent ではない)。

### 5-5 slot 1–5 の観測 (未確定)
- slot 0 (`0x1a9cf0`): CreateInstance 直後に `this` = instance で呼べる (import 0 回)。差分 64 case に含めた。
- slot 1 (`0x1a9f10`): `[this+0x20]` (CreateInstance が 0 にしたまま) を読み、その値を後続で使うため、native が `addr 0x0` で SIGSEGV (probe: 呼出元の一時コピーで確認・未コミット)。CreateInstance → slot 0–5 の全呼出を入れた版では 64/64 case が native で落ちた。
- したがって slot 1–5 は、host が事前に `this` の内部フィールドを設定する前提が要る。その前提は未確定 (子 #T-SH-57)。

### 5-6 検証範囲 / 範囲外
- 範囲: CreateInstance (1 呼出) → slot 0 (1 呼出)。引数は `rcx` = instance・`rdx` = arena+0x8000・`r8`・`r9` = 0。`.data` の事前状態 64 種。比較は rax (合成値)・import 呼出回数・heap 領域 64 KiB・`.data` 全体。
- 範囲外: slot 1–5 と closure 70 関数の全体差分 (子)、VEX 3 命令 (子)、stack・TEB・TLS の比較 (比較していない)、import 戻り値の実 Windows との一致 (両側で同じ手書き規約。lift の正しさだけを見る)。
- `issue #3216` 本文が参照する「REPORT.md §5-5 の未解決 (WC 以外の vptr 格納 3 件・helper `0x1aedc0`/`0x1b6f4c`)」は、現 HEAD の REPORT に記載が無い。`REPORT_CLOSURE.md` §4.6 の表が対応する。これは未実施 (子)。

### 5-7 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| slot 1–5 の host 前提の確定と、closure 70 関数の native 対 wasm 全バイト差分 | 受入 (2) の残り・gate の範囲 | 子 [T-SH-57] |
| VEX 3 命令 (vcvtss2sd・vpmovsxdq・vshufps) の x64c 対応 (unsup 3 site) | 受入 (1) の残り。実行到達時は trap | 子 [T-SH-58] |
| REPORT_CLOSURE.md §4.6 の未解決 (WC 以外の vptr 格納 3 件・helper `0x1aedc0`/`0x1b6f4c` の正常系到達) の native 確定 | 受入 (3) | 子 [T-SH-59] |
| 非 padding 16 件の到達性 (§5-4) | closure の完全性 | [T-SH-57] の受入に含める |

### 5-8 測定後のコード差分 (差分 0 の証跡)
`git diff d631564c HEAD -- tools/shared/lift/ildsp ':!*.md'` の出力は空 (本節は `.md` のみ)。
