# tools/plugins/distortion/REPORT.md — PLG-F6 (#203) distortion + multi-fx 9 本: lift 前提の実測

- 日付: 2026-10-13 / 担当 dir: `tools/plugins/distortion/` のみ / 検証起点 commit: **8db8705** (e2e 系スクリプト) と **c0fcf60** (nega の理由照合の修正 + `tables.py`。 e2e 系は 8db8705 と同一)
- 再現: `bash tools/plugins/distortion/distortion_e2e.sh` (測定 + 判定。 不合格は非 0) / `bash tools/plugins/distortion/distortion_nega.sh` (ネガティブコントロール) / `python3 tools/plugins/distortion/tables.py` (本書 §1〜§4 の表を出力)
- 素材: `fl-win64` / `toolchain-retdec` / `toolchain-emsdk` (`docs/WORKFLOW.md` §11)。 環境は `distortion/env.sh`
- 手法の出典: PR #506 (PLG-F3 dynamics, 未マージ) の e2e / matrix_check / ids_crosscheck / engine_lift を踏襲。 #506 の reviewer 指摘 2 点 (判定が不合格でも exit 0 / 判定そのものの NC が無い) は §5 の通り最初から潰した
- 既知類型との関係 (`docs/DEFECTS.md`): **該当なし** (閉包の判定は「通る」ことだけで silent miscompile を検出しない。 差分試験は未実施。 §4 の engine 型エラー E1/E2/E5 は emcc が拒否する loud な IR 型エラー、§7)

## 0. 結論 (先出し)

1. **#203 の出口条件 (差分試験 bit-exact + Render test .flp の E2E) は未達で、本 run では着手できない。** PLG-P0a #195 / P0b #196 / P0c #197 が OPEN (2026-10-13 `gh issue view` で確認)。
   Eff_Render 単位の native (DLL を VA 敷設して ms_abi 実行) ⟷ wasm の harness も repo に無い。 → PR は **`Refs #203`** (Closes しない)。
2. **手順 1 (固有閉包の lift) は Delphi 製 9 DLL (8 殻 + Distructor の `module`) すべてで通った** (§1)。 RetDec+pass 鎖 rc 0、`emcc -c` 0、`x86_fp80` 関数 0、
   合計 **336 関数 / 162,247 B**。 未実装 `__asm_*` helper は Love Philter の `__asm_rep_stosb_memset` 1 件のみ (issue 記載と一致、名前まで照合 §5)。
   T0/T1 の 6 本は `PLUGIN_MATRIX.json` の記録 (閉包 6 項目 + batch 4 項目) を再現、T2 の殻 2 本 (Distructor / Effector) は閉包 6 項目を再現し batch の lift 結果は今回初測定、
   **Distructor `module` (18916、116 関数) は閉包ごと今回初測定** (PLUGIN_MATRIX の `lift` 欄は各 plugin の先頭 module のみ)。 突合は 72/72 項目一致。
3. **host 呼出面は P0b の応答表 (`hs_ids.json`) で覆える。** 閉包の即値 Dispatcher ID は {2, 3, 8, 36} の 4 種で全て `hs_ids.json` に有る。 別算法の独立走査は Distructor に ID 48 の `call [reg]` × 2 site を追加で検出 (taint 版に載らない、ID 48 も `hs_ids.json` に有る)。
   動的 ID は Distructor 1 site のみ。 slot 0xc0 (Fast Dist 1 site) は P0b では fail-soft のみ (§2)。
4. **SIMD kernel 表への依存は 5 DLL に限られる**: Distructor 殻 1 / `module` 7 / Soft Clipper 2 / WaveShaper 11 / Love Philter 18 site。 Effector・Blood Overdrive・Fast Dist・Squeeze は閉包にも frontier にも 0 site (§3)。
   この 4 本の DSP は閉包内のインライン SSE に載っていると推定する (未確認)。 kernel 単位の差分試験 (P0c) では保証できず、**Eff_Render 単位の差分試験が必須**。
   **WaveShaper (2+2 site) と Love Philter (1+1 site) は P0c が bit-exact 未達と記録する 0x5dfd30 / 0x5dfdb0 を閉包で呼ぶ** (P0c §10.3: buf_diff 508,385 など。 dd 演算系列が真因)。
   Love Philter は #331 の対象に列挙された 0x5df040 も 1 site 使う。 Love Philter / `module` / Soft Clipper には Balance の 80 kernel にハッシュ対応付けできない呼出が計 7 種 (`raw:`) ある。
5. **C++ DLL 2 本 (Effector engine / Hardcore) は RetDec+pass 鎖までは通るが `emcc -c` は未通過** (§4)。 両者とも型エラーが連鎖し (E1 → E2 / E5)、VEX を含む未実装 helper 宣言が 110 / 102、`x86_fp80` 関数が 1 ずつある。
   **Hardcore は Delphi framework 無しだが、全 `.pdata` 1,726 関数を lift しただけで、DSP の閉包 (エントリからの到達集合) は未算出**。 T2 の見積 4 人日/本には engine 側の未知工数が残る。

## 1. 閉包 lift 結果 (Delphi 製 9 DLL)

定義: 閉包 = vtable override 実装 (DestroyObject / Dispatcher / SaveRestoreState / GetName / ProcessParam / Eff_Render) から `call/jmp rel32` で到達する、framework 共通ハッシュ (13 DLL 以上) でない `.pdata` 関数
(`lift/plugin_closure.py`)。 frontier = 閉包から呼ぶ framework 関数 (P0a の共有 wasm 側)。 vcall / ptr = 間接呼出 site 数 (件数のみ)。 iat = IAT 経由 Win32 呼出 site。

| DLL | block | Tier | 閉包 関数 / B | frontier 関数 / B | vcall | ptr | iat | final.ll define (うち range 内部の追加) | f80 関数 | 未実装 helper | `emcc -c` | lift 秒 |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Distructor | 18914 | T2 | 16 / 5,737 | 39 / 4,826 | 43 | 8 | 0 | 18 (2) | 0 | 0 | 0 | 2 |
| Distructor module | 18916 | T2 | 116 / 37,137 | 91 / 16,675 | 109 | 54 | 2 | 116 (0) | 0 | 0 | 0 | 5 |
| Effector | 18972 | T2 | 17 / 15,055 | 54 / 17,402 | 26 | 2 | 0 | 17 (0) | 0 | 0 | 0 | 3 |
| Fruity Blood Overdrive | 18987 | T0 | 13 / 8,052 | 48 / 9,170 | 14 | 2 | 0 | 13 (0) | 0 | 0 | 0 | 3 |
| Fruity Fast Dist | 19004 | T0 | 12 / 8,381 | 50 / 10,585 | 10 | 3 | 0 | 12 (0) | 0 | 0 | 0 | 3 |
| Fruity Love Philter | 19024 | T1 | 105 / 59,894 | 145 / 20,916 | 132 | 43 | 3 | 109 (4) | 0 | 1 | 0 | 10 |
| Fruity Soft Clipper | 19078 | T0 | 15 / 5,567 | 44 / 9,176 | 9 | 5 | 0 | 15 (0) | 0 | 0 | 0 | 3 |
| Fruity Squeeze | 19082 | T0 | 21 / 10,011 | 48 / 6,988 | 14 | 7 | 0 | 21 (0) | 0 | 0 | 0 | 3 |
| Fruity WaveShaper | 19089 | T0 | 21 / 12,413 | 63 / 11,508 | 40 | 13 | 2 | 21 (0) | 0 | 0 | 0 | 4 |
| 計 | | | **336 / 162,247** | | | | | 342 | 0 | 1 | 0 | |

- `emcc -c` 列は `emcc -c -O0 -msimd128` の終了コード (0 = 通過)。 **通過 ≠ 正しさ**: 正しさは差分試験でしか示せない (batch_plan §4)。
- final.ll define = `grep -c '^define'`。 括弧は RetDec が range 内部に切り出した関数の追加数 (`engine_defs.py` の extra_inside)。 全 9 DLL で「閉包 range の開始 VA に対応する define が無い」は 0 件、
  かつ define = 閉包関数数 + 追加数 が成り立つ (judge の条件、§5)。 つまり閉包の関数は 1 本も脱落していない。
- Distructor 殻は閉包 16 関数・host call 4 site と小さく、DSP 本体は `module` (18916、116 関数、kernel 7 site) 側にあると推定する (殻と `module` の結合方式は未解析)。
- 直接 Win32 API (`PLUGIN_MATRIX.json` `win_direct_api`): Effector = registry 3 / gdi 6 / clipboard 3 / threads 1 / dynload 2 / file_io 10 (どの module の値かは PLUGIN_MATRIX の定義未確認)。 Hardcore = registry 6 / dynload 3 / file_io 17 / gdi 6 / clipboard 3 / threads 1。 他の殻は 0。

## 2. host 呼出面 (閉包内の Dispatcher ID / host vtable slot)

`inventory/host_calls.py` の taint 追跡 (`Host=[this+0xbc]` → `vt=[Host]` → `call [vt+disp]`、ID = 直前の `r8` 即値) を閉包 ranges 内の関数に限定して集計 (`closure_facts.py`)。 slot0 = Dispatcher。

| DLL | host call site 計 | slot0 (Dispatcher) 即値 ID (site) | 動的 ID | 他 slot (offset: site) | hs_ids.json に無い ID |
|---|--:|---|--:|---|---|
| Distructor | 4 | 8 (1) | 1 | 0x100: 1, 0x108: 1 | 無し |
| Distructor module | 20 | 3 (2) | 0 | 0x100: 9, 0x108: 9 | 無し |
| Effector | 1 | 2 (1) | 0 | — | 無し |
| Fruity Blood Overdrive | 1 | 2 (1) | 0 | — | 無し |
| Fruity Fast Dist | 2 | 2 (1) | 0 | 0xc0: 1 | 無し |
| Fruity Love Philter | 34 | 2 (1), 36 (1) | 0 | 0x100: 16, 0x108: 16 | 無し |
| Fruity Soft Clipper | 1 | 2 (1) | 0 | — | 無し |
| Fruity Squeeze | 1 | 2 (1) | 0 | — | 無し |
| Fruity WaveShaper | 7 | 2 (1) | 0 | 0x100: 3, 0x108: 3 | 無し |

- 即値 ID の distinct = {2, 3, 8, 36}。 `hs_ids.json` (35 ID) に**不足 0**。
- **別算法の検算** (`ids_crosscheck.py`、taint を使わず閉包を線形逆アセンブルし `mov r8d, imm` の後 8 命令以内の `call [reg]` (disp 0) を全数拾う): 9/9 DLL で taint 版の ID 件数を取りこぼしなく再現した。
  一致しない差は 1 点で、**Distructor に ID 48 の `call [reg]` が 2 site** (taint 版は host 経由と判定せず未計上)。 host 呼出か別オブジェクトの slot0 呼出かは未判別。
- 0x100 / 0x108 は ABI.md §6 が「別オブジェクト由来の偽陽性を含む可能性」とする offset。 0xc0 は P0b では 44 slot 共通の fail-soft + 呼出記録のみ (意味未解析)。

## 3. SIMD kernel 表 (45 変数 / 80 実装) への依存

`p0c/kernel_matrix.py` の `scan_dll` (kernel 変数経由・関数ポインタ slot 経由・直接 call の 3 経路) を再利用し、call site の所在関数を閉包 ranges / frontier で分類。
kernel 番号は Balance (block 18983) の VA に正規化。 DLL 側 VA を Balance の 80 kernel にハッシュ対応付けできなかった呼出は `raw:<その DLL の VA>` と表記 (別 DLL と番号が衝突しうる)。

| DLL | 閉包内 site | 閉包内で呼ぶ kernel (site) | frontier 内 site | DLL 固有関数走査 site / kernel 種 |
|---|--:|---|--:|---|
| Distructor | 1 | 0x5dfae0 (1) | 0 | 23 / 2 |
| Distructor module | 7 | 0x5de390 (2), 0x5de4b0 (1), raw:0x5fc000 (2), raw:0x5fcdc0 (2) | 0 | 42 / 15 |
| Effector | 0 | — | 0 | 22 / 1 |
| Fruity Blood Overdrive | 0 | — | 0 | 22 / 1 |
| Fruity Fast Dist | 0 | — | 0 | 22 / 1 |
| Fruity Love Philter | 18 | 0x5de390 (2), 0x5de4b0 (1), 0x5dee50 (1), 0x5df040 (1), 0x5dfb60 (1), 0x5dfbe0 (1), 0x5dfd30 (1), 0x5dfdb0 (1), raw:0x6286f0 (2), raw:0x6288c0 (2), raw:0x6294b0 (3), raw:0x6295f0 (2) | 2 | 60 / 24 |
| Fruity Soft Clipper | 2 | 0x5dfae0 (1), raw:0x5dfb60 (1) | 0 | 26 / 4 |
| Fruity Squeeze | 0 | — | 0 | 22 / 1 |
| Fruity WaveShaper | 11 | 0x5de390 (2), 0x5de4b0 (1), 0x5dfb60 (2), 0x5dfbe0 (2), 0x5dfd30 (2), 0x5dfdb0 (2) | 0 | 53 / 18 |

- `scan_dll` の出力は `nvars=45 / nimpls=80 / kernels_hash_ok=80 / bad=0` (Distructor `module` / Love Philter / WaveShaper / Soft Clipper の 4 DLL で確認。 他 5 DLL は未確認)。 `raw:` の呼出は計 7 種 (`module` 2 / Love Philter 4 / Soft Clipper 1)。
  80 kernel とハッシュは全て一致しているので、Balance の VA へ写す規則 (ハッシュ → 最初の VA) で取れない同一ハッシュの別 VA (twin) と推定する (未確認)。
- 0x5de390 (22 site) は 9 DLL 共通で、閉包にも frontier にも属さない (framework 側の深い関数と推定、未確認)。

P0c (`p0c/REPORT.md`) で見た各 kernel の現状 (本 PR では再測定していない):

| kernel | P0c の記録 |
|---|---|
| 0x5de390 / 0x5de4b0 | f64mem。 0x5de390 は実機械語 ⟷ x87 版 / f64 lowering 版とも差分 0 / 300,000 (§3)。 f64mem 全体では ±1 ulp 0.018% を許容条件として記録 |
| 0x5dfae0 | transc。 f32 出力で 0 / 200,000 (§3) |
| 0x5dfb60 | k80_diff.py で bit-exact (§9) |
| 0x5dfbe0 | rc_chop。 `f80_lower.py --ext` で bit-exact (§10.0) |
| 0x5dfd30 / 0x5dfdb0 | **bit-exact 未達** (§10.0: 真因は dd 演算系列。 0x5dfdb0 は ext 全機能で buf_diff 508,385、§10.3)。 **WaveShaper 各 2 site / Love Philter 各 1 site が閉包で使う** |
| 0x5df040 | #331 の対象に列挙 (P0c §14.4 の記述)。 **Love Philter が閉包で 1 site 使う** |
| 0x5dee50 | P0c REPORT に個別記述を見つけられなかった (grep で 0 件)。 Love Philter が 1 site 使う |

## 4. C++ DLL 2 本 (Effector engine / Hardcore)

両者とも MSVC C++ (VS2019, link 14.29)、export は `CreatePlugInstance` 1 つ、import に USER32 / GDI32 を含む (GUI を持つ)。 Effector engine の殻との結合方式 (LoadLibrary 経路) は未解析。

| DLL | block | サイズ B | `.text` B | `.pdata` 関数 / B | import (DLL: 件数) |
|---|--:|--:|--:|--:|---|
| Effector engine | 18973 | 498,176 | 273,056 | 1,305 / 251,711 | KERNEL32: 79, USER32: 31, GDI32: 11, ADVAPI32: 3, SHELL32: 1, ole32: 3 |
| Hardcore | 19101 | 641,536 | 376,416 | 1,726 / 349,625 | KERNEL32: 95, USER32: 31, GDI32: 11, COMDLG32: 2, ADVAPI32: 3, SHELL32: 2, ole32: 3 |

| DLL | RetDec rc | final.ll define | `.pdata` で define 無し (関数 / B) | f80 関数 | 未実装 helper | `emcc -c` | fixcmp 後の `emcc -c` | lift 秒 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Effector engine | 0 | 1,362 | 1 / 61 | 1 | 110 (うち VEX 79) | 1 | 1 | 39 |
| Hardcore | 0 | 1,780 | 1 / 61 | 1 | 102 (うち VEX 68) | 1 | 1 | 58 |

`engine_lift.sh <block>` は全 `.pdata` 関数を `lift_ranges.sh` (RetDec+pass 鎖) → `emcc -c` に通す。 「`.pdata` で define 無し」= `function_<開始VA>` の define が final.ll に無い range 数 (分母は `.pdata` 関数数、B はその range 長の合計)。
両 DLL とも同じ 61 B の 1 関数: MSVC の `_DllMainCRTStartup` 相当 (`cmp edx,1` → `__security_init_cookie` 相当の call → `jmp` で dllmain_dispatch へ) で、参照元は final.ll に無い。 DSP ではない。

失敗の連鎖 (clang は最初の型エラーで止まるため 1 件ずつ露見。 `first_errors.txt` に記録):
1. 両 DLL: `icmp eq ptr %x, %arg1` (`%arg1` は i64 仮引数) → "defined with type 'i64' but expected 'ptr'" (#506 §7 の E1 と同型)。 `engine_fixcmp.py` (engine 局所 pass、共有鎖には未組込) で Effector engine 6 / Hardcore 11 operand を直す。
2. Effector engine: 次に `__asm_rep_stosq_memset` 呼出の引数が SSA 値を含む `zext` 定数式 → "zext constexprs are no longer supported" (#506 §7 の E2 と同型)。
3. Hardcore: 次に `%ce1n11_function_180018de0 = zext 0 to i64` (型の無い定数を zext、`function_180018de0`、final.ll に 1 site) → "expected type" (**E5、新規**。 #534 の E4 = `fix_asm_stores.py` の dangling use とは別類型)。 `zext (…)` 定数式も 1 site 残り、E2 も後に露見する。
- 未実装 helper (distinct 宣言数) は Effector engine 110 (VEX 79)、Hardcore 102 (VEX 68)。 非 VEX は `blendv*`・`cmp*pd/ps`・`pmulld`・`pmuludq`・`fxsave`・`rep_movsb_memcpy` など。 VEX が CPUID 分岐で SSE 路に固定できるかは未確認。
  `x86_fp80` 関数は各 1 (#197 の `f80_lower.py` の適用対象)。
- 以上は到達性の実測で、engine の正しさは何も示していない。

## 5. 検証 (コミット済み HEAD・4 core / 15 GiB の Actions runner・逐次実行で並列数 1)

| 項目 | 実測 |
|---|---|
| 前提 inventory (初回のみ。 fl-win64 tarball 展開 + `win_scan` / `win_funcs` / `win_unique` / `win_abi` / `kernel_table` 生成を含む) | `inventory.sh` **9 m 10.5 s** (user 35 m 2 s)。 `win_funcs.py` が並列で走り、`uptime` で観測した load average (1 分) の最大は 17.23。 以降の run は生成済みを再利用 |
| `distortion_e2e.sh` 全体 (HEAD 8db8705 = c0fcf60 の e2e 系、inventory 済、3 回連続) | **4:29.80 / 4:29.74 / 4:26.43**、いずれも exit 0。 開始時 load average (1 分) 0.32 / 1.01 / 1.12。 内訳のうち 9 閉包 lift は 34–36 s (seconds 列の合計)、C++ DLL 2 本の lift は 96–98 s (下行の秒の合計)。 すべて逐次 (並列数 1)。 参考: コミット前の作業ツリー (`unimpl_names.py` 追加前) の 1 回目は 4:31.96 |
| lift 秒 (`status.csv` の seconds、3 回の min–max) | Distructor 2–3 / `module` 5–5 / Effector 3–4 / Blood Overdrive 2–3 / Fast Dist 2–3 / Love Philter 9–10 / Soft Clipper 2–3 / Squeeze 3–3 / WaveShaper 4–4 (9 本計 34–36 s)。 Effector engine 39–40 s、Hardcore 57–58 s |
| 3 回の結果一致 | 判定列 (`status.csv` の seconds 以外)・`shell_audit.csv`・`facts.json`・`engines.csv` (lift_s 以外) の sha256 先頭 16 桁は 3 回とも同一 (facts `6650e975d4e86b1e` / status `5a51892da5bfae1d` / audit `a5f384f76704ec66` / engines `f8063cfae5009545`) |
| 判定 (各回) | `judge.py` 9/9 block 合格 → `unimpl_names.py` 9/9 → `matrix_check.py` **72/72** 項目一致 (閉包 6 項目 × 8 plugin + batch 4 項目 × 6 plugin) → `ids_crosscheck.py` 9/9 → `judge.py --engines` 2/2 |
| `distortion_nega.sh` (HEAD c0fcf60、e2e の直後) | exit 0、**9.08 s**、**37/37** 項目 (下表) |

ネガティブコントロール (数値は `distortion_nega.sh` の出力。 判定系は「期待した理由の文言で落ちたか」まで照合する):

| NC | 内容 | 結果 |
|---|---|---|
| NC-J (18 件) | `distortion_e2e.sh --judge-only` に、実測 status.csv を 1 点だけ壊した入力を与える。 対照 (無改変) は exit 0 + 最終行 OK。 壊し方: `emcc_c_rc`=1 / `lift_rc`=1 (殻と `module`) / `f80_funcs`=3 / `declares_unimpl`=5・許容超過 (Love Philter 2 > 1)・-1 / `defines`=0・9999 / 非整数 / 行の削除・重複・対象外 block の追加 / 欠落監査 csv の `missing_define`=1・`function_defines`+1・`extra_inside`=0 / ヘッダ破損 | 壊した 17 件はすべて exit 1 (ヘッダ破損のみ入力不正の exit 2)、最終行 OK なし、期待した理由の文言が出力に有り |
| NC-JE (5 件) | engines.csv の判定。 対照 exit 0。 `lift_rc`=1 / `defines`=0 / 集計不能 (-1) / 行削除 | 4 件とも exit 1 |
| NC-N (5 件) | `unimpl_names.py`。 対照 exit 0。 別名の helper (stosb→stosw) / 未実装 0 の block に名前を追記 / 件数 1 だが名前の行が無い / log 無し | 4 件とも exit 1 |
| NC-E | Soft Clipper (19078) の `final.ll` の 1 関数の `ret` を除去 | `emcc -c` rc **0 → 1** |
| NC-R | 19078 の閉包 ranges 14 本の末尾 1 本 (`function_6c11c0`) を落として再 lift | その define 1 → 0、全体 define **15 → 13** (RetDec は 1 range から 2 define を出すことがあり差は 1 と限らない) |
| NC-I | `ids_crosscheck.py` に Distructor の ID 8 の件数を 1 → 2 にした facts を与える | exit 0 → **1** (9/9 → 8/9) |
| NC-M | `matrix_check.py`: Distructor の `closure_funcs` +1 / Fast Dist の `emcc_c_rc` を 1 にした status | 72/72 → **71/72** (exit 1)、後者も 71/72 (exit 1) |
| NC-D | `engine_defs.py` に実在しない range を 1 本足す | `missing_define` **1 → 2** |
| NC-W | e2e 本体 (`--skip-lift`) に、Fast Dist の最終行が `emcc_c_rc`=1 の lift 結果を与える | e2e 全体が exit 1、最終行 OK なし、`FAIL  block 19004 … emcc_c_rc=1` を表示 (#506 で露見した「判定が落ちても e2e が exit 0」の再発防止) |

衛生 (HEAD c0fcf60 + 本書): `git status --porcelain=v1 -- tools/plugins/distortion` は本書のみ未追跡、`git diff 042f869 HEAD --stat` の範囲は `tools/plugins/distortion/` のみ、`find tools/plugins/distortion -type f -size +1M` は 0 件。 大物は `tools/plugins/work/` (gitignore)。

検証範囲: 閉包の機械的な到達性 (RetDec+pass 鎖 → `emcc -c`)・閉包 range の脱落監査・host / kernel 依存の静的な数え上げ・C++ DLL の到達性。
範囲外: wasm のリンクと実行、native との出力比較、framework / host shim との結合、Render test .flp、Hardcore の DSP 閉包の特定。 範囲外の項目について、本書は何も主張しない。

## 6. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 差分試験 bit-exact (出口条件 3)。 Eff_Render 単位の native / wasm harness が無く、P0a/P0b 未完 | #203 を閉じられない | #195 / #196 / #197 の完了後に #203 を再開 (Closes はその時)。 harness は新規 **#544 [PLG-F6-1]** に起票 (#506 §6 が提案する PLG-F3a と共通化できるので統合は PM 判断) |
| Render test .flp の E2E (出口条件 4) | 同上 | FLEngine 統合待ち。 親 #14 / #203 |
| Effector engine / Hardcore の `emcc -c` 未通過 (E1 → E2 / E5 の連鎖、VEX 含む未実装 helper 110 / 102、f80 各 1) | T2 の 2 本 | 新規 **#545 [PLG-F6-2]** に起票 (共有鎖の修復は #534 / #523 / #527 / #540 と共通化) |
| Hardcore の DSP 閉包 (CreatePlugInstance / TFruityPlug 殻のエントリからの到達集合) が未算出 | Hardcore の工数 (見積 4 人日) の根拠 | #545 (`plugin_closure.py` は Delphi vtable 前提のため C++ 用のエントリ抽出が要る) |
| Distructor 殻と `module` (18916) の結合方式 | DSP がどちらにあるかの確定 | #544 (差分 harness の設計時に結合方式を解析する) |
| Love Philter の `__asm_rep_stosb_memset` (未実装 helper) | wasm 化 | #197 にコメント (issue 記載の memset 写像で足りるか) |
| 0x5dfd30 / 0x5dfdb0 の bit-exact 未達 (P0c §10.3) を WaveShaper 各 2 / Love Philter 各 1 site が閉包で使う | 両 plugin の出口条件 (bit-exact か許容条件の記録) | #197 にコメント (両 kernel の残差を許容条件にするか再実装かの判断が要る) |
| 0x5df040 (Love Philter が閉包で 1 site 使用) の P0c 残差 | Love Philter の kernel 保証 | #331 に依存を追記 |
| `raw:` kernel 呼出 7 種 (§3) が Balance の 80 kernel の twin か未確認 | kernel 依存の数え上げ | #197 にコメント |
| Distructor の ID 48 × 2 site (taint 版に載らない)・slot 0xc0・動的 ID 1 site の意味 | host 呼出面 | #196 作業 5 (0x13173a0 全 case 解析) に追記 |
| 0x5de390 の 22 site の所在 (閉包外・frontier 外) | §3 の解釈 | #197 / #195 の統合時に所在関数を特定 |
| `nsis_names.py` が Actions 上で動かない (`block_manifest.json` 不在) | inventory の再現性 | `mk_blockmap.py` で回避済み (#506 と同じ)。 `docs/WORKFLOW.md` §11 への追記は PM 判断 |
| `env.sh` / `mk_blockmap.py` / `engine_*.py` が #506 の `tools/plugins/dynamics/` と重複 (#506 が未マージのため複製) | 保守 | #506 マージ後に `tools/plugins/` 共通へ寄せる別 PR |
| `docs/DOC_MAP.md` の REPORT 索引に本書が未掲載 | 索引漏れ | PM が追記 (並行 run との衝突を避け本 PR では触らない) |

## 7. DEFECTS.md 行案 (候補・loud な IR 型エラー。 追加の可否は PM 判断)

| 類型 | 症状 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|
| E1 icmp ptr/i64 混在 | `icmp eq ptr %x, %argN` (argN は i64) | Effector engine 6 operand / Hardcore 11 operand | emcc "defined with type 'i64' but expected 'ptr'" | `engine_fixcmp.py` (局所)。 `fix_ptr_params.py` の拡張が本筋 |
| E2 SSA 値入りの定数式 | `__asm_rep_stosq_memset` の引数に `zext (… i64 %v …)` | Effector engine 1 site / Hardcore 1 site | emcc "zext constexprs are no longer supported" | 未修復 |
| E5 型の無い zext | `%x = zext 0 to i64` | Hardcore `function_180018de0` 1 site | emcc "expected type" | 未修復 |

## 8. 成果物

| ファイル | 内容 |
|---|---|
| `distortion_e2e.sh` | inventory → 9 閉包 → batch_lift → `judge.py` (殻) → `unimpl_names.py` → `closure_facts.py` → `matrix_check.py` → `ids_crosscheck.py` → C++ DLL 2 本 → `judge.py --engines`。 判定が落ちたら非 0 で終わり、最終行 `OK` は出ない。 `--skip-lift` / `--judge-only` あり |
| `judge.py` | status.csv / engines.csv の合否判定 (不合格で exit 1、入力不正で exit 2) |
| `unimpl_names.py` | 未実装 helper の名前を許容リストと突合 (`judge.py` は件数のみ) |
| `distortion_nega.sh` | ネガティブコントロール (§5) |
| `closure_facts.py` `tables.py` | 閉包 / host ID / kernel 依存 / C++ DLL 外形 → `work/distortion/facts.json` / §1〜§4 の表 |
| `matrix_check.py` `ids_crosscheck.py` | `PLUGIN_MATRIX.json` との突合 (閉包 6 項目 + batch 4 項目) / Dispatcher ID の別算法検算。 どちらも `--facts` / `--status` を取る |
| `engine_lift.sh` `engine_ranges.py` `engine_defs.py` `engine_fixcmp.py` | C++ DLL の全 `.pdata` lift・欠落監査 (`engine_defs.py` は殻の閉包にも使う)・局所修復 |
| `inventory.sh` `mk_blockmap.py` `env.sh` `targets.py` | `block_manifest.json` 不要の inventory 前提 / 環境 / 対象表 (block・Tier・許容) |
