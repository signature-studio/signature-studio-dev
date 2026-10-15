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

## 5. WaveformColouring_CreateInstance の vcall `0x1a9e2b` の dispatch 先 (#2484 / T-SH-37)

既知類型との関係: 該当なし (逆アセと PE 読みのみ。lift・IR を作らないため D1a〜D23 の検出対象外)。
検証起点 commit: `80fb2fd0` (PR の基点・merge-base)。測定 commit (コードを変えた最後の commit): `da2ba516` (`tools/shared/scripts/ildsp_wc_dispatch.py`。対象 VA の走査 `fdb8bae0` を追加し、走査を遅延列挙にして実行時間を戻した。初版の追加は `8b1e34ac`)。

### 結論 (1 行)
`0x1a9e2b` の `call [rax+0x18]` は sub-object への dispatch ではない。instance 自身 (0x228 B・vptr は +0) の WC vtable slot 3 を呼び、その値は `0x1a9de0` (DIR64 reloc あり) で、**静的に `0x1a9de0` へ確定**する。前提は §5-5 の 1 件 (他 vtable 格納 2 件の書き込み先は §5-4 で解消)。

Issue 本文の「sub-object の vtable」という前提は誤り。CreateInstance は wrapper を作らず、単一の object を返す (§5-1)。

### 5-1. instance の生成と vptr (静的事実)
- `0x1ac470`: `mov ecx,0x228` → alloc (`0x1ac9c0`) → rbx。`memset` (`0x1aef60`、r8=0x228) の後 `mov rcx,rbx` → `jmp 0x1ac4a0`。
- `0x1ac4a0`: `lea rax,[rip+0x233cfc]` (0x1ac4ad、RVA `0x3e01b0`) → `mov [rcx],rax` (0x1ac4b4)。vptr は instance の +0 に書く。
- closure 内で WC vtable (`0x3e01b0`) を書くのは 0x1ac4b4 の 1 件のみ (`ildsp_wc_dispatch.py` の `vptr 格納` 節)。

### 5-2. vcall の解決
| 項目 | 値 | 根拠 |
|---|---|---|
| vcall の場所 | `0x1a9e2b`: `call qword ptr [rax+0x18]` (fn `0x1a9e10`) | objdump (検算) |
| `0x1a9e10` の位置付け | WC vtable slot 2 (RVA `0x3e01c0` の値) | vtable の生値 |
| 呼び出し元 | 直接 call/jmp は無い。exec セクション全走査 (`ildsp_wc_dispatch.py` の `direct_callers`: `0x1a9e10 <- []`)。8 バイト値の参照は WC vtable の slot 2 (`0x3e01c0`) だけ (`## 対象 VA への参照`) | スクリプト出力 |
| `this` の vptr 読み | `0x1a9e16`: `mov rax,[rcx]` (rcx = instance) | objdump |
| vptr の値 | `0x3e01b0` (§5-1) | |
| slot 番号 | 3 (`0x18` ÷ 8) | |
| slot RVA / 値 | `0x3e01c8` / `0x1a9de0` (VA `0x1801a9de0`、DIR64 reloc あり) | 生バイト検算 |
| 解決先の性質 | thunk でない・closure 内・11 命令 (int3 を除く。次の pdata 先頭 `0x1a9e10` までの int3 の詰め物 10 個は数えない) | ildsp_wc_dispatch.py (`insns (int3 除く)`) |
| 解決先の中身 (逆アセ読み) | 2 回ループで instance の +0x20・+0x24 (dword) と +0x40・+0x48 (qword) をゼロにする | objdump |

- vcall の後 (`0x1a9e2e` 以降) は、戻り値を使わずに instance の +0x8〜+0x18 等へ書く (逆アセ読み)。

### 5-3. closure の間接 call 19 件の内訳 (WC)
| 種別 | 件数 | 本 REPORT での扱い |
|---|---:|---|
| vcall `call [reg+disp]` | 1 (`0x1a9e2b`) | §5-2 で解決 |
| IAT | 16 | 子 [T-SH-52] #3216 で扱う |
| 画像内関数ポインタ | 2 (`0x1aedf6`→`0x268260`・`0x1b6f6c`→`0x268268`。helper `0x1aedc0`・`0x1b6f4c` 内) | §5-4 |

件数は `ildsp_wc_dispatch.py` の `## 間接 call の内訳` (vcall 1 / IAT 16 / 画像内ポインタ 2 / レジスタ 0 / 計 19) で出し、`ildsp_closure.py` の WaveformColouring 行 (間接 19) と一致する。IAT は PE の import 表の IAT 位置と照合した。

### 5-4. 共通の例外送出 helper `0x1aedc0` / `0x1b6f4c` (T-SH-36 #2483 の結果を参照)
- 結論: 宛先 (`0x268260`・`0x268268`) は静的に確定しない。T-SH-36 の結論 (`REPORT.md` §4-6) をそのまま引く。本 issue では再調査しない。
- `0x1aedc0` は IAT の `RtlPcToFileHeader`・`RaiseException` を呼ぶ。`0x1aedf6` の間接 call は `0x268260` → `0x1cb5e0` (`jmp rax`)。
- `0x1aedc0` は MSVC の C++ 例外送出と推定 (RTTI 未確認)。ecx = 例外コード `0xe06d7363`、引数 4 個 (rdx = 1 = noncontinuable)、ExceptionInformation[0] = `0x19930520` (一部の経路で `0x1994000`)、[1] = 例外オブジェクト、[2] = rdx の throw 情報、[3] = `RtlPcToFileHeader` の戻り値 (イメージ基底と推定)。`RaiseException` (IAT `0x268090`) を呼ぶ。
- 他 vtable 格納 (§5-5 前提 1 の解消)。旧出力の 3 件は 2 件: `0x1acfe0` は `jmp 0x1801b34a8` の 1 命令の stub で格納は無く、pdata の無い関数の範囲が `0x1acfe8` と重なったため `0x1acfff` を 2 回数えていた (`ildsp_wc_dispatch.py` を格納箇所ごとに 1 件に修正)。残る 2 件の書き込み先は、どちらも例外オブジェクトのスタック上の一時領域:
  - `0x1acfff` (fn `0x1acfe8`、vptr `0x3d2778`): 直接の呼び出し元は `0x1ad011` の 1 件。`0x1ad008` の `lea rcx,[rsp+0x20]` (`0x1ad00c`) の直後にある。`0x1ad008` は `0x1ac9c0` の `0x1ac9f0` から呼ばれる。`0x1ac9c0` は確保関数 (CreateInstance の `0x1ac47b` を含む多数から呼ばれる)。確保が失敗し new handler (`0x1b6f4c`) が 0 を返したとき、`rbx == -1` なら `0x1ad028`、それ以外なら `0x1ad008` へ進む。
  - `0x16475a` (fn `0x164740`、vptr `0x3d27a0`): 直接の呼び出し元は `0x1ad031` (fn `0x1ad028`、`lea rcx,[rsp+0x20]` は `0x1ad02c`) と `0x1647c9` (fn `0x1647c0`、`lea rcx,[rsp+0x20]` は `0x1647c4`) の 2 件。`0x1ad028` は `0x1ac9f6` から呼ばれる。
  - よって 2 件の格納先 `[rcx]` は、どちらの経路でも呼び出し元が直前に作ったスタック上のアドレスで、WC instance (ヒープ上の 0x228 B) ではない。
  - 範囲: `ildsp_wc_dispatch.py` の `direct_callers` (exec セクション全走査の直接 call/jmp) と `## 対象 VA への参照` 節 (全画像走査の RIP 相対の命令参照と 8 バイト絶対値)。対象 `0x1acfe8`・`0x164740`・`0x1ad008`・`0x1ad028`・`0x1ac9c0` は、RIP 相対 0 件・8 バイト値 0 件。レジスタに計算した値からの参照と、4 バイト相対値のテーブルは網羅していない。
- `0x1b6f4c` の `0x1b6f6c` は `0x268268` → `0x1cb600` (`jmp [0x268260]`) で、同じ `jmp rax` に至る。`rax` の値は静的に不明。
- 扱いの案 (未確認・推定): 例外送出の path とみなし、lift では trap を第一候補にする。正常系の到達は `REPORT_APPENDIX_3276.md` で確定 (HeapAlloc 成功時は 0 回)。

### 5-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| instance の vptr が `0x3e01b0` のまま変わらないこと (動的な書き換えは静的には見ていない)。他 vtable 格納 2 件の書き込み先は §5-4 でスタック上と確認済み | §5-2 の解決 (`0x1a9de0`) の前提 | 子 [T-SH-52] #3216 |
| 例外 path の catch 先 (`RaiseException` の先) が trap か stub か (`REPORT_APPENDIX_3276.md` の未解決) | 画像内関数ポインタ 2 件 (§5-4) の扱い | 子 [T-SH-52] #3216 |
| IAT 16 件の扱い (GetLastError・HeapAlloc 等) | lift 規模 | 子 [T-SH-52] #3216 |
| 70 関数の lift・native 全バイト差分・ネガティブコントロール・gate (#2484 の受入条件 2・3) | 本 PR では未実施 | 子 [T-SH-52] #3216 |

- native 確定 (T-SH-59 #3276): 正常系で helper `0x1aedc0`・`0x1b6f4c` は 0 回。例外 path の vptr 格納先はスタック。詳細と実測は `REPORT_APPENDIX_3276.md`。

### 5-6. 検証
- 再現 (3 コマンド): `FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_closure.py` → `FL_WIN64_DIR=<展開先> python3 tools/shared/scripts/ildsp_wc_dispatch.py` → `python3 tools/shared/scripts/ildsp_wc_dispatch_check.py tools/shared/work/raw/ildsp_wc_dispatch.json <PE>`。
- 入力: `block24360_PE.bin` (sha256 f4b23b0f…)。`ildsp_closure.py` の WaveformColouring 行 (70 関数・2,757 命令・SIMD 23.8%・間接 19) を再現した。
- 結果: `ildsp_wc_dispatch_check.py` は `ALL OK` (rc 0)。`ildsp_wc_dispatch.py` の `## 対象 VA への参照` 節は、対象 5 関数で RIP 相対 0 件・8 バイト値 0 件。`0x1a9de0`・`0x1a9e10` の 8 バイト値は WC vtable の slot 3 (`0x3e01c8`)・slot 2 (`0x3e01c0`) の 1 件ずつ。
- 独立の確認 (objdump の `# 0x<VA>` 注釈を数える。スクリプトとは別): 対象 7 VA (`0x1ac9c0`・`0x1ad008`・`0x1ad028`・`0x1acfe8`・`0x164740`・`0x1a9de0`・`0x1a9e10`) の RIP 相対参照は 0 件。陽性対照の WC vtable `0x1803e01b0` は vptr 格納の `lea` で 1 件。
- 実測 (測定 commit `da2ba516`、4 core。`ildsp_wc_dispatch.py` の 3 回の load average は実行前 0.77 / 実行後 0.82、`ildsp_wc_dispatch_check.py` の実行前は 0.35): `ildsp_wc_dispatch.py` 5.524 / 5.544 / 5.617 s (rc 0 ×3。3 回の stdout は `cmp` で完全一致)、`ildsp_wc_dispatch_check.py` 0.057 / 0.058 / 0.056 s (rc 0 ×3・ALL OK ×3)。比較のため同じ入力で旧版 (`960405ba`) を 2 回実行 (load 0.8 前後): 5.300 / 5.423 s。対象 VA の走査を入れた初版 (`fdb8bae0`) は 17 秒台で、全命令の operands 参照と命令オブジェクトの一覧保持が原因。RIP 判定を `rip` を含む命令に限り、走査を遅延列挙にして (`da2ba516`) 旧版と同等に戻した。
- ネガティブコントロール (JSON を壊して検算を通すか。測定 commit `da2ba516` の JSON):

| 名前 | 壊し方 | 結果 |
|---|---|---|
| neg_target | vcall の target_rva を `0x1a9de1` | `MISMATCH: slot`・rc=1 |
| neg_store | 格納 vtable (`stores[0].vtable`) を `0x3e01b8` | `MISMATCH: store`・rc=1 |

- 検算の範囲: 命令は objdump、slot 値と DIR64 reloc は PE の生バイトで照合。closure の完全性は検算していない。対象 VA の参照は、RIP 相対の命令参照と 8 バイト絶対値だけを見る (レジスタ計算値・4 バイト相対値は対象外。他 vtable 格納 2 件の書き込み先は §5-4 の走査で確認)。
- `git diff da2ba516 HEAD -- tools/shared/scripts` の出力は空 (差分 0)。

## 6. vtable slot 4 (0x1aa3a0) の lift と native 差分 (#2529)

### 結論 (1 行)
GeneralPitchShifter vtable slot 4 (RVA 0x1aa3a0・42 命令・直接 call / 間接 call 0) を RetDec で lift し、元の機械語との差分は 240/240 で一致。ネガティブコントロール 2 件は期待どおり FAIL。
全文 (手順・選定根拠・実測・未解決) は `REPORT_APPENDIX_2529.md` §6 が正本 (250 行上限のため分割移動)。

## 7. WaveformColouring_CreateInstance の x64c lift と native 差分 — T-SH-52 (#3216・部分達成)

### 結論 (1 行)
WaveformColouring closure の入口 70 関数を x64c で C に lift し wasm にした。CreateInstance → slot 0 の native 対 wasm は 64 case で全バイト一致 (ネガティブコントロール FAIL 64/64)。slot 1–5 の host 前提と VEX 3 命令の未対応は子 T-SH-57・58・59 に残す。
全文 (手順・実測・未解決の表) は `REPORT_APPENDIX_3216.md` §7 が正本 (250 行上限のため分割移動)。

## 8. PSOLA_CreateInstance 閉包の x64c lift — T-SH-82 (#3428・部分達成)

### 結論 (1 行)
PSOLA 閉包 (CreateInstance + vtable slot 先) の unsup を 2,472 site から 0 にした (ymm 算術・vextractf128 ほか)。命令単位の差分 83 件 PASS、WaveformColouring の回帰 PASS 64/64。閉包単位の native 差分は子 issue に分離。
全文 (再現・内訳・差分テストの内訳・実測・未解決) は `REPORT_APPENDIX_3428.md` が正本 (測定 commit `b2b898522`)。
