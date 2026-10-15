# libreverb (win `Reverb.dll`) lift + 差分テスト — T-SH-15 (#161) 部分達成

検証起点 commit: `e848740` (クリーン worktree `git worktree add --detach HEAD` で再現)。
既知類型との関係: **D1a (DEFECTS.md)** の変種 1 件 (§3)。他は該当なし。

## 結論 (1 行)
win 版 `Reverb.dll` の `Process_Fruity_32FM_32FS` / `Process_UF_32FM_32FS` を RetDec で lift し、`ucomiss` flags 修復 (1 pass) + SSE scalar helper 生成で wasm 化。
**native 実機械語 vs wasm の全バイト比較 240/240 一致** (ネガコン 4 件は全て FAIL = ゲートは効く)。**実インスタンス (CreateReverbInstance) 駆動は未達**: 生成直後の状態では `Process_Fruity` が SIGSEGV (§7 → [T-SH-71] #3361)。**ildsp は未達**: WaveformColouring は #3216 (CLOSED・部分達成。残りは #3274・#3275・#3276)。GeneralPitchShifter の残件は #3318・#3320。PSOLA は [T-SH-75] #3401 (起票済み)。残り 7 instance は未起票で #161 に残す (§6)。

## 0. gen_helpers の未対応 op 全数 (#3316・ildsp 0x161fc0 closure)

測定 commit: `2ae10ac85` (`gen_helpers.py` の変更。ildsp 側の lift 入力は `c5bd6af6e` の `lift_vtable.sh 0x161fc0`)。
- 変更: 未対応の宣言を即 exit せず**全数列挙**してから exit 1 にする。`i8` (psrldq/psrlq/psllq 等の即値) を型写像に追加 (従来は KeyError で落ちていた)。対応済み 7 種の出力は変えない。
- 件数の定義 (本節の数字はこの 3 つだけを指す。他の節・PR 本文はこれを参照する):

| 記号 | 定義 | 値 | 出典 |
|---|---|---|---|
| (a) declare 行数 | `norm_raw.ll` のうち `^declare` かつ `@__asm_*` を持つ行数 | 未再測定 (本 run に `toolchain-retdec` が無く、`.ll` も無い) | — |
| (b) distinct op 名数 | `grep '^declare' norm_raw.ll \| grep -oE '@__asm_[a-z0-9]+' \| sort -u \| wc -l` (対応済み op を含む closure 全体) | 54 | [ildsp REPORT_LIFT §3](ildsp/REPORT_LIFT.md) (`f180a18d4`・toolchain-retdec v5.0) |
| (c) 未対応シグネチャ数 | `gen_helpers.py` が未対応として列挙した declare 行数 (rc=1) | 62 (2ae10ac85 での実行結果。本 run では再現していない) | 本節の測定 |

- (b) は対応済み 7 種 (movss/movaps/addss/subss/mulss/xorps/ucomiss) を含む全 op 名の数。したがって未対応の op 名の数は「(b) − 7 以上・(b) 以下」で、(b) そのものを未対応の数とは読めない。(c) は gen_helpers の対応表で弾かれた declare 行の数。旧記述「declare 62 件が未対応 (op 名 54 種)」は (b) と (c) を取り違えていた。
- issue #3316 の題名の「49 種」は古い数字で、本文の「54 種」が (b) と一致する。
- 未対応の op 名の例: `cvttss2si`・`movd`・`cvtdq2ps`・`divss`・`vfmadd231sd`・`ucomisd`。
- 未再測定の扱い: (a) と (c) は、`toolchain-retdec` の素材を付けた run (`oc_artifacts: fl-win64 toolchain-retdec`) で `lift_vtable.sh 0x161fc0` を再実行して確定する。それまでは上の値を「過去の記録」として扱う。
- `gen_helpers.py` の rc=1。残りの wasm 化 (helper の C 実装) は [T-SH-65] #3318、native 差分は [T-SH-64] #3317 が持つ。

## 1. 対象の再特定 (mac の 0x25c0-0x2f87 は win では使えない)
`python3 locate.py <Reverb.dll> <out>` が export stub → 実体 → `.pdata` の連鎖で範囲を求める (RVA, 範囲内に base reloc 0 件・外部 call 0 件)。

| export | stub RVA | 実体 (RVA) | サイズ | .pdata 連鎖 |
|---|---|---|---|---|
| `Process_Fruity_32FM_32FS` | 0x1b80 (`jmp`, 引数並べ替え) | 0x1240–0x1b7f | 2367 B | 3 エントリ (本体は primary + 2 chained) |
| `Process_UF_32FM_32FS` | 0x2790 (`call`, stack 引数 1 個) | 0x1ba0–0x278b | 3051 B | 3 エントリ |

- 注意: export stub は 33–37 B のみ。**`.pdata` の 1 エントリ (0x1240–0x12e4 = 164 B) だけを lift すると本体 (0x12e4–) を落とす**。UNWIND_INFO の CHAININFO で連結する。
- DLL: `fl-win64/extracted/block24352_PE.bin` (PE32+, 492,544 B)。`block24360_PE.bin` = ildsp_x64.dll (4,197,376 B)。

## 2. lift と差分テスト (`FL_WIN64_DIR=… bash lift.sh [ok|neg-*|all]`)
工程: `locate.py` → RetDec `--select-ranges` (2 範囲) → `libkio/ir_normalize.py` (流用) → `fix_rv.py` → `gen_helpers.py` (IR の `declare @__asm_*` から C helper を生成。未知 op は exit 1) → emcc standalone wasm (18,769–18,802 B)。
- RetDec 単一範囲 (Fruity のみ) 実測 0.842 s。2 範囲 lift 後の IR は 2 関数。`__asm_*` は addss/subss/mulss/movss/movaps/xorps/ucomiss の **7 種・12 declare** (mac slice の 10 種と異なり andps/andnps/orps/cmpneqss は win では出ない)。
- 参照 = `native_ref.c`: 元の機械語を RWX mmap し **ms_abi 関数ポインタで直接実行** (非循環)。被験 = wasm を node 実行。
- ケース: Fruity/UF × small/wide × 60 = **240**。this 状態 (0x260 B) + 14 本の delay buffer (各 4096 float) + 入力 (n = 0〜255)。比較は「状態 + 全 buffer + 出力 (+ UF の aux 出力)」の**全バイト** (出力バッファは 0xA5 毒入れ、ポインタ欄は 0 に正規化)。
- カバレッジ gate (欠ければ exit 1): UF aux 有 66 / 無 54, `[this+0x78]` ==0 が 121 / !=0 が 119 / **NaN が 36**, n=0 が 39, n≥129 が 30。
- 本検査結果: **240/240 PASS** (Fruity small 60/60, wide 60/60, UF small 60/60, wide 60/60)。native 側の出力サンプルのうち NaN は Fruity 3,532/9,200・UF 3,589/8,050 (全 240 ケース合計。`[this+0x78]`=NaN や wide 入力が伝播) で、NaN もビット単位で一致を要求している (「NaN だから比較できない」ケースは無い)。範囲内の外部 call 0 件・範囲外への分岐 0 件は capstone 逆アセンブルで確認 (Fruity/UF とも)。

## 3. 欠陥 (修復した 1 件)
| 症状 | 根本原因 | 検出信号 | 修復 |
|---|---|---|---|
| `ucomiss xmm0,xmm12; jp; je` の分岐が壊れる (D1a (DEFECTS.md) 変種) | RetDec は `__asm_ucomiss` を no-op 化し、`%or.cond = icmp eq i1 <ZF of 'add rax,4'>, <PF of 'add rax,4'>` と**直前の無関係なポインタ加算の flags** で分岐条件を作る | `call @__asm_ucomiss` の直後の `%or.cond` (2 箇所: Fruity/UF) | `fix_rv.py`: `fcmp oeq float lane0(A), lane0(B)` に置換 (NaN で false → jp 経路 = 元 asm と同じ)。置換数が 2 でなければ exit 1 |
- `uselistorder` 行は置換で不整合になるため `fix_rv.py` で除去 (意味を持たないヒント)。

## 4. ネガティブコントロール (全て `lift.sh` に実装・`all` で自動実行)
| 名前 | 壊し方 | 結果 (pass/240) |
|---|---|---|
| `neg-helper` | `__asm_mulss` helper を add に | 39 |
| `neg-nofix` | `fix_rv` を飛ばす (ucomiss 未修復) | 75 |
| `neg-compare` | 比較器検査: wasm 結果 1 byte を反転 | 239 (case#0 の byte0 で不一致を検出) |
| `neg-nan` | 修復の `oeq` を `ueq` に (NaN 経路だけ誤る) | 210 |
`neg-*` は FAIL を検出したとき exit 0、**PASS してしまったとき exit 1** (ゲートが効かない状態を検知)。`ok` は 1 ケースでも不一致 / TRAP / カバレッジ不足で非 0。

## 5. 実測 (クリーン HEAD `e848740`, `lift.sh all` = 本検査 + ネガコン 4 件, 4 core runner)
| run | 所要 (s) | load (開始前 1 分値) | exit |
|---|---|---|---|
| 1 | 24.78 | 0.46 | 0 |
| 2 | 27.96 | 0.64 | 0 |
| 3 | 28.08 | 0.78 | 0 |
3 回とも本検査 240/240・ネガコン 4 件期待通り FAIL。

## 6. ildsp (`block24360_PE.bin`) 調査のみ (lift 未実施)
ildsp の規模測定 (命令数・call 数・export closure 表) と未解決は [lift/ildsp/REPORT.md](ildsp/REPORT.md) が正本。
追跡先 (いずれも実在): WaveformColouring は #3216 (CLOSED・部分達成。残りは #3274 [T-SH-57]・#3275 [T-SH-58]・#3276 [T-SH-59])。GeneralPitchShifter は #2483 の子 #2528・#2529・#3300 (いずれも CLOSED)。その残件は CreateInstance closure の wasm 化 #3318 [T-SH-65] と全バイト差分 #3320 [T-SH-66]、vtable slot 1–3 は #3299 [T-SH-61]、slot 5 は #3404。PSOLA は [T-SH-75] #3401 (起票済み)。残り 7 instance (LimiterLite・Limiter・LowFreqEnhancer・Shimmer・StereoEnhancer・TransientLooper・Transmitter) は子 issue が未起票のため、親 #161 に残す (一覧は #161 のコメント)。

## 検証範囲 / 範囲外
- 範囲: win 版 Process_Fruity/UF の**合成状態** (乱数 + 境界値) に対する wasm と native 機械語のビット一致。
- 範囲外: ① 実インスタンス状態での駆動 (§7 で実測: 未達 → #3361) ② Process_UF 以外の Reverb 内関数 ③ mac slice ④ ildsp lift ⑤ wasm の性能。

## 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実インスタンス (CreateReverbInstance → Process) の駆動検証。生成直後の状態は Process_Fruity が SIGSEGV (§7) | 14 本の遅延線ポインタの割付け元が未特定。状態レイアウトの意味づけは乱数/境界値で代替したまま | [T-SH-71] #3361 |
| D1a 変種「分岐条件が直前の無関係な add の parity/zero flag」の DEFECTS.md 反映 | カタログ未反映 | 行案は §3。DEFECTS.md の編集は PM 判断 |
| ir_normalize / fix pass が `libkio` 配下の流用 (汎用化されていない) | 他 lib 転用時にコピーが増える | [T-SH-16] #144 |

## 7. 実インスタンス (CreateReverbInstance) の native 実行 — 生成直後の状態は Process_Fruity が落ちる

測定 commit: `ccea76aeb` (HeapAlloc / HeapFree の呼び出し回数の出力を追加。`git diff ccea76aeb HEAD -- tools/shared/lift/libreverb ':!tools/shared/lift/libreverb/REPORT.md'` の出力は空)。
手順: `FL_WIN64_DIR=<fl-win64 展開先> bash tools/shared/lift/libreverb/inst_probe.sh` (locate.py → `inst_probe.c` を gcc で build → 実行 → 期待値と照合。期待値と違えば exit 1)。

| 項目 | 実測 |
|---|---|
| `CreateReverbInstance` (RVA 0x3fa0) | 171 B・47 命令。直接 call は alloc ラッパ 0x404c (60 B)・memset 0x5300 (400 B)・遅延線初期化 0x1000 (88 B) ×2 |
| IAT の到達 (ctor 経路・実測) | HeapAlloc (IAT 0x60130) は **5 回**、HeapFree (0x60138) は **0 回** 呼ばれる (出力 `HEAPALLOC_CALLS` / `HEAPFREE_CALLS`)。この 2 件を C 実装 (calloc / free) に差し替えると完走。ctor 以外の経路 (`Process_*` など) での到達は未計測 |
| 返り値 | 非 NULL・vptr = img+0x603c0 (RVA)・0x2a0 B のうち 18 B が非 0 |
| 遅延線 2 本 (`this+0x290`・`this+0x298`) | 両方確保済み。buffer 非 NULL・index 0・mask 0xfff (4096 float) |
| 遅延線ポインタ 14 本 (`this+0xbc+8i`, i=0..13) | **14/14 が 0** |
| `Process_Fruity_32FM_32FS` (n=4) を実インスタンスに対して 1 回 | **SIGSEGV (11)** |

- 読み: Fruity は `qword [this+0xbc+8i]` を 13 本 (0xbc〜0x11c。例 0x13a7 `rax, qword ptr [r10+0xbc]`) 読み、UF は加えて 0x124 を読む (計 14 本)。NULL をそのままたどる。遅延線 1 本のレイアウトは、逆アセンブル (0x1220・0x1180) から `+4` = buffer ポインタ・`+0x10` = index・`+0x14` = mask と推定 (2 本の実測値と一致)。
- 未特定 (子 [T-SH-71] #3361 の対象): コンストラクタが作るのは 2 本だけ。vtable の先頭 6 slot (RVA 0x28d0・0x3270・0x2980・0x3f80・0x3f90・0x2950) のうち、slot 1 (0x3270・665 命令) は float パラメータ (`this+0x20`・`0x200`・`0x208`) を読むが、確保の call を含まない。slot 3 (0x3f80) は `this+0x10` を返す getter、slot 4 (0x3f90) は `ret 0`。`qword ptr [reg+disp]` 形の 14 本への書き込みは静的走査で見つからなかった (`dword` の書き込みは 0xd0〜0x14c にあり、遅延線の index 更新と見られる)。
- 検証範囲: 静的な書き込み命令の走査と、生成直後の 1 状態 (引数 NULL) での実行。ポインタを埋めた状態で Fruity が通るかは未実施 (子 #3361)。

### 14 本の書き込み元の観測 (#4194 / 親 #3361)

測定 commit: `866c93ed0` (`inst_probe.c` の書き込み観測・対照モードを追加。HEAD までのコード差分は 0 行)。
手順: 4096 B 境界の領域を PROT_READ にして書き込みを SIGSEGV で捕まえ、TF で 1 命令だけ進めて RIP と書き込み後の値を記録する。

| モード | 対象 | 結果 (`WRITES_PTR` = `this+0xbc+8i` への書き込み) |
|---|---|---|
| `ctor` | `CreateReverbInstance` 1 回 | `WRITES_TOTAL=58 WRITES_OBJ=44 WRITES_PTR=0`・`PTR14_ZERO=14` (呼び出し後も 14/14 が 0) |
| `noctor` (陰性対照) | CreateReverbInstance を呼ばない空の状態 | `WRITES_TOTAL=0 WRITES_PTR=0` |
| `selftest` (陽性対照) | C 側から 14 本へ書く | `WRITES_PTR=14`・RIP が image 外で 14 件。観測手段は書き込みを見逃さない |
| `vt` | vtable slot 0〜5 を ctor 後の object に対して 1 つずつ実行 | slot 0: `this+0` の vptr 書き込みのみ / slot 1: 書き込み後に SIGSEGV / slot 2・4: 書き込み 0 / slot 3: SIGSEGV / slot 5: object 外へ 2048 件・object 内 0 |
| `fruity` | ctor 後の object に `Process_Fruity` (n=4) | 書き込み 3 件 (`this+0x6c`・`0x70`・`0x74` = 値 0) の後に SIGSEGV。`this+0xbc+8i` への書き込みは無い |

- 読み: 14 本の書き込み元は、`CreateReverbInstance` (0x3fa0 からの直接 call 網) にも、vtable slot 0〜5 にも、`Process_Fruity` の経路にも無い。
  静的走査でも `[reg+0xbc+8i]` 形の qword 書き込みは 0 件 (`mov word [rax+0xbc]` の 2 件は 16 bit 書き込みで別物)。
- `0x27c0` (RVA 0x27c0–0x2853) は遅延線 2 本を `this+0x290`・`0x298` に作るコンストラクタで、`0x1000` を 2 回呼ぶ。`0x27c0` は直接 call の呼び出し元が無く (間接 call の経路は未確認)、`[rbx+0x10]` に vptr `0x5dbec` を書くため、この object の ctor かどうかは未確定。
- 未特定: 14 本を埋めるのは、ctor より後に呼ばれる別の entry (ホストの初期化など) と見られる。entry の候補は未列挙。
- 全 `.text` 走査 (`scan_writes.py`・測定 commit は下記の HEAD): 90,226 命令のうち `[reg+0xbc+8i]` (i=0..13) を書き先にする命令は qword 0 件。dword 27 件は `0xd4`〜`0x104` の `sub …,1` と `mov …,eax` (カウンタ更新で、ポインタ代入ではない)。word 2 件 (0x3f09b・0x3f19b) は `0xbc` の 16 bit 書き込み。
- export は 3 件 (`CreateReverbInstance` 0x3fa0・`Process_Fruity_32FM_32FS` 0x1b80・`Process_UF_32FM_32FS` 0x2790)。14 本を埋める entry は、この 3 件の外 (内部関数・ホストが直接呼ぶ別経路) にあると見られるが、未特定。
- 観測の限界: 観測は `this` 直下の書き込みだけを見る。14 本を別オブジェクトや間接的な経路で書くなら、`this` 直下の観測では見えない。

### 実測 (4 core・3 回)

| 検査 | 測定 commit | 所要 (s) | load (開始前 1 分値) | 結果 |
|---|---|---|---|---|
| `lift.sh all` (本検査 + ネガコン 4 件) | `2de7679d` | 36.30 / 36.23 / 36.49 | 0.54 / 0.74 / 1.17 | rc 0・PASS 240/240・ネガコン 4 件 FAIL (期待通り) |
| `inst_probe.sh` | `ccea76aeb` | 0.234 / 0.234 / 0.232 | 0.13 | rc 0・期待値と一致・`HEAPALLOC_CALLS=5 HEAPFREE_CALLS=0` (ctor 状態で Fruity が SIGSEGV) |

- `lift.sh all` は fix 環境に `toolchain-retdec` / `toolchain-emsdk` が無く、再実行していない (上の行は `2de7679d` の実測)。`2de7679d` から HEAD までの lift の入力 (`lift.sh`・`locate.py`・`fix_rv.py`・`gen_helpers.py`・`diff_test.py`・`native_ref.c`・`run_wasm.mjs`) の差分は 0 行。
- `inst_probe.sh` の実測は fix 環境で `fl-win64` の `extracted/block24352_PE.bin` だけを展開して行った (他のファイルは使わない)。
- ネガティブコントロール: 期待値 `FRUITY_SIGNAL=11` を `10` に変えた一時コピーの `inst_probe.sh` は `MISMATCH`・rc 1 (実測。一時コピーは削除済み)。

- `lift.sh all` の所要は §5 (24.8〜28.1 s) より長い (36.2〜36.5 s)。load は §5 と同程度 (0.5〜1.2) で、原因は未確認。判定 (PASS / FAIL の内容) には影響しない。
