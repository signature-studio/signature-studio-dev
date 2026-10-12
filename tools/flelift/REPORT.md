# tools/flelift — x64c を FLEngine 向けに汎用化 (CAB-226 / ICALL-1)

## 0. 結論 (先出し)

- **判定: 達成**。FLEngine_x64.dll 全体 (M11 closure 7,421 関数のうち lift 可能 **7,031 関数 / 340,774 命令**) を
  x64c (tools/ott/lift/x64c.py の vendored fork) で lift し、**未対応 site を 1,105 (0.32%) → 0 にした**。
  `bash tools/flelift/fle_e2e.sh` (約 2.7 分) = **PASS**。
- **wasm build 成功**: emcc -O0 で **wasm 27.6MB** を生成 (lift 35 秒 + data gen + emcc 28 秒、合計約 60 秒)。
- **spot 差分検証 (native 実機械語直実行 vs wasm)**: 7 関数 / 16 case のうち **14 case が戻り値・xmm0・
  メモリ書換 (.data/.bss/TEB/scratch/arena) 全て bit 一致**。verdict は tools/liftdiff FORMAT.md (v1) §3 準拠の
  JSONL (`results/verdict_flelift.jsonl`)。採点は CAB-232/233 (本 tickets の範囲外、liftdiff e2e は未実行)。
- **D7–D11 の x64c 版対策を完了** (§3)。D9 は **136,333 rip-rel site 全件で capstone disp = 手動 modrm 解釈
  (不一致 0)** を実証 — x64c は disp_size フィールド非依存ゆえ D9 の影響なし。
- **tools/ott 本体・tools/liftdiff・tools/liftlib・tools/icall は 1 行も変更していない** (読取/実行/ベンダーコピーのみ)。
  `bash tools/ott/ott_e2e.sh` = PASS (本担当の作業後も OTT route は健全、tools/ott 側の未コミット変更は
  並行稼働中の CAB-137+91 担当分であり本担当は触れていない)。
- **ユーザ確定方針 (2026-10-10) に沿う**: FLEngine 全体 lift は RetDec+icall pass ではなく x64c 拡張ルートで確定
  (CAB-89 / CAB-132 にコメント投稿済み)。

## 1. 成果物 (tools/flelift/)

| パス | 役割 |
|---|---|
| `x64c.py` | vendored fork 本体。IMG/SHIFT/IMG_SIZE を CLI パラメタ化 (既定 = FLEngine 0x400000/0/0x18c0000) + 未対応命令 handler 群 (§2) |
| `rt/fle_cpu.h` / `fle_cpu.c` | CPU 状態 + 命令 helper + Win32 import stub (原型 = ott_cpu)。DF/AF flag, YL (ymm 上位), **M[8] (MMX 独立レジスタ)**, x87_cw/sw, TEB (gs), IAT pseudo-VA |
| `rt/fle_glue.c` | `fle_run` (JS→lifted 呼出, stack 引数対応) / `fle_set_stackarg` / `fle_reset` / `fle_init` |
| `fle_data_gen.py` | image 敷設生成: .data/.rdata/.didata/**.reloc** (恒等写像ゆえ reloc 補正不要) + .bss ゼロ + .text 内 jump table 窓 (3,226) + **IAT slot に pseudo-VA 敷設** |
| `fle_lift.sh` | lift → data gen → emcc → wasm (1 コマンド) |
| `fle_native.c` / `fle_ms_call.S` | native 参照ローダ (原型 = tools/ott/native)。ImageBase 0x400000 に mmap、TEB (ARCH_SET_GS)、VirtualAlloc bump を wasm と同一 VA に |
| `fle_natdrv.c` | native driver 実行ファイル (PIE + setarch -R。python3 が non-PIE で 0x400000 を占有するため別プロセス化) |
| `fle_wasm_runner.mjs` / `fle_diff.py` | 関数単位 spot diff → **FORMAT.md v1 準拠 verdict JSONL** |
| `probe_d9_disp.py` | D9 検証 (capstone vs 手動 modrm 全件突合) |
| `t_ustrasg.mjs` | smoke: _UStrAsg 3 case + Move 7 case |
| `results/verdict_flelift.jsonl` | spot diff verdict (FORMAT.md §3 スキーマ、tag は `x-` なし標準キー) |
| `fle_e2e.sh` | 1 コマンド検証 (lift→build→smoke→diff→D9) |

生成物 (wasm 27.6MB / lifted C 34MB 等) は `work/` (gitignore)。20MB 超 blob は git に入れない。

## 2. 未対応 1,105 site の解消内容 (全て実装・lift 結果 unsup = 0)

| 群 | site 数 | 実装 |
|---|--:|---|
| string (非 rep) movsq/stosq/stosd + **movsd 文字列形** | 788 | movs*/stos*/lods* 全幅 + DF (fDF) 対応。rep 系は DF 反転経路も追加 |
| lock 系 (xadd/cmpxchg/xchg/cmpxchg16b) | 91 | 単一スレッド前提の非 atomic 実装 (flag 意味は FL_ADD/FL_SUB で保持)。cmpxchg16b は 128bit 比較 + CF/PF |
| bt/bts/btr/btc mem,reg | 29 | ビット文字列: byte = ea + (idx>>3), bit = idx&7 |
| SSE2 整数 (pack*/pmul*/pminmax/paddsat/pshuflw·hw/cvtps2dq/movhlps·lhps ほか) | ~140 | 飽和 helper (sat_u8/u16/i16) 込み。MMX 形は M[8] で独立実装 |
| MMX (mm0-7 形 + 3DNow! pi2fw/pi2fd) | ~60 | **M[8] 独立レジスタ** (実機で XMM 非 alias を実測 §3-c)。emms = no-op |
| AVX ymm (vmovups/vmovaps/vmovntps/vzeroupper) + sfence 系 | ~20 | YL[16] = ymm 上位 128bit。vmovntps = 非一時 store |
| x87 制御 (fldcw/fnstcw/fnstsw/fnclex/fninit/emms) | 13 | x87_cw/x87_sw モデル (演算命令は lift 集合に存在せず制御のみ) |
| jecxz/jrcxz, xgetbv, lea riz, gs/fs segment, movd/mm 系 CRASH | ~44 | TEB モデル (SEG_GS=0x1D00000, TLS)、XCR0=7 固定、riz=無視、cpuid/rdtsc モデル |

 lift 実測: **7,031 関数 / 340,774 命令 / unsup 0 / unlifted callees 0 / import 341 名 (IAT 738 slot)**。

## 3. 汎用化過程で判明・修正した欠陥 (x64c 側)

| # | 欠陥 | 対策 / 実測 |
|---|---|---|
| a | **entry より前への後方分岐で C 関数の入口が断片になる** (FLEngine Move 0x409c80 が 0x409c40 断片を後方参照) | lift 冒頭に `goto L_entry` を生成 (OTT では未発火の潜在欠陥)。Move 4 case が全 bit 一致 |
| b | 原版 `i_shufps` の format 引数不足 (13 site が CRASH) | selector 4 本を正しく展開 (原版潜在バグ、OTT では shufps 未出現のため未発火) |
| c | **MMX を XMM low 64bit alias として実装すると実機と不一致** | 実機 probe (`movq mm0,rax` 後の xmm0 変化なし) で非 alias を確認 → **M[8] 独立レジスタ**に変更。0x660c40 (MMX blend) が全 case bit 一致 |
| d | `fle_set_stackarg` が ret push 分 (8B) ずれ、5+ 引数関数の第 5 引数以降を 1 slot ずらして読む | STACK_TOP+0x20+8i に修正。0x6a7180 (7 引数) が bit 一致 |
| e | spot diff harness の .bss ゼロ範囲・比較領域を RVA/VA 混在で記述 (image VA = 0x400000+RVA) | VA 0x15e5008..0x196f000 (.bss) / 0x13a5000..0x196f000 (比較) に修正 |
| f | **D10 (jump table)**: OTT の MSVC 形 (4B RVA + add) 検出では Delphi 形 (`lea rB,[rip+d]` + `jmp [rB+idx*8+disp]`, 8B 絶対 VA, index が負方向) を解決できない | `jump_table_abs` を追加 (前後両方向へ解決)。FLEngine lift 集合の jump table は **1 site** (0x40d253, 関数 0x40d210, 9 entry) を解決し switch 化。他 14 site は .data 間接 (`jmp [abs]`) で dispatch 経由 |
| g | `mov rax,[iat]; call rax` 形の間接呼出 (Delphi RTL が使用) が dispatch で解決できない | IAT slot に pseudo-VA (IMP_VA_BASE 0x1D80000 + index) を敷設し、dispatch が imp 呼出に解決 |

## 4. 既知欠陥 D7–D11 の x64c 版対策 (チケット要件 2)

| 欠陥 | x64c での状態 | 実測 |
|---|---|---|
| D7 (zero-disp 参照消滅) | **構造的に無い** (x64c は定数折畳み最適化を持たず全 load を明示生成) | `_UStrAsg` 0x413440 `mov rax,[rbx]` → C `LD64((R[3]))` を確認。p_self case (旧値読出し) bit 一致 |
| D8 (comis flag 未定義) | `comis_f` inline helper が ZF/PF/CF を設定 (OF/SF/AF = 0 — 実 HW も 0 を返す) | F set 829 site。直後分岐の内訳: jbe 426 / jp 217 / ja 65 / jb 61 / jae 12 / je 8 / jl 1 / jne 1 — jl の 1 site も SF=OF=0 で HW と整合 |
| D9 (capstone disp_size 誤り) | x64c は `address+size+mem.disp` 自前計算で disp_size 非依存 | **全 136,333 rip-rel site で capstone disp = 手動 modrm 解釈 (不一致 0)**。prefix 別: 66 = 2,542 / F2 = 9,049 / F3 = 7,765 / REX = 106,219 / none = 10,569 (手動解析不能 189 は 0F 38/3A 拡張等) |
| D10 (jump table) | MSVC 形 + Delphi 形両対応 (§3-f) | 1 site 解決 (0x40d253)。table 9 entry は .text 内データとして data_gen が敷設 |
| D11 (chained .pdata) | x64c は .pdata を関数境界に使わない (再帰降下)。断片は分岐到達で inline 化 or 独立 lift (二重 lift は無害) | chained flag 関数 0x40d210 も正常 lift。断片の二重 lift は lift 数 7,031 に含まれる |
| D12 (landing pad) | **対象外** (CAB-227) | FLEngine 879 gap site は未対応のまま (M11 boot 経路には出現しない) |
| D13 (CFG thunk) | 解決済 (原版から)。`jmp rax` → ott_dispatch | FLEngine は MSVC CFG 不使用ゆえ出現 0 |

## 5. 検証 (チケット要件 3)

### 5.1 命令被覆率 — **残存未対応 = 0**
lift 結果 `unsup = {}` (1,105 → 0)。被覆率 100% (lift 集合 340,774 命令)。

### 5.2 wasm build — **成功**
emcc -O0 で **27,630,238 byte** wasm (flel.cjs + flel.wasm)。build 約 28 秒。node で instantiate 成功。

### 5.3 spot 差分 (native vs wasm) — **14/16 case bit 一致**
方法: native = 実機械語を ImageBase 0x400000 に敷設して MS x64 ABI で直接実行 (fle_natdrv)、
wasm = flelift 産物 (fle_run)。双方同じ敷設 (TEB/scratch/arena 同一 VA, alloc bump 同一) で
rax / xmm0 / .data+.bss / TEB / scratch / arena の 8B block 差分を比較。

| 関数 | case | verdict |
|---|---|---|
| 0x409c80 Move (rep movsb + movups + AVX/SSE2 dispatch, D10 関連) | 4 (n=392/36/17/0) | **match** (4/4 equal) |
| 0x4133f0 _UStrAsg (**lock xadd 経路**含む, M11 unit#18 leaf) | 3 | **match** (3/3) |
| 0x6a7e40 SSE2 blend (cvtps2dq/packssdw/punpck/pmulhuw, 7 引数) | 2 | **match** |
| 0x6a7180 SSE2 mix (7th stack 引数 + rip-rel .data 定数) | 1 | **match** |
| 0x69a130 min/max→cvtps2dq (movhlps/movlhps/movlps) | 2 | **match** |
| 0x660c40 MMX blend (pxor/punpcklbw/pshufw/psubsw/psllw/pmulhw/paddw/packuswb/emms) | 2 | **match** |
| 0x6a7990 MMX RGB 乗算 (stack 引数 mm7 + r9 mm6) | 2 | **mismatch** — dst 1-3 block の一部 byte が不一致 (§6) |

verdict JSONL: `results/verdict_flelift.jsonl` (FORMAT.md §3: `liftdiff_version` / `function` / `verdict` /
`cases[].outcome` / `static.machine`)。**tools/liftdiff の e2e は実行していない** (V12 検収との衝突回避) —
スキーマ準拠出力の用意のみ (採点は CAB-232/233)。

### 5.4 smoke (M11 unit#18 chain 接続確認)
`_UStrAsg(0x4133f0)`: (1) src=0 → dest=0 ✓ (2) refcnt=1 + lock xadd → **refcnt 2 ✓** (旧 x64c はここで
fail-fast) (3) self-assign ✓。`Move(0x409c80)` n=392 (**M11 の 0x188 record 初期化と同一の Move 経路**) /
64 / 36 / 24 / 3 / 1 / 0 全て内容一致 ✓。
注: literal 経路 (`call 0x412c20` → FastMM GetMem) は Delphi System 初期化 (memory manager table は .bss
0x13a5c90 にあり unit init で設定) が必要 → 本 ticket では未実施。M11 boot (CAB-5) の領域。

### 5.5 OTT bit-exact 回帰 (読取のみの範囲)
`bash tools/ott/ott_e2e.sh` = **PASS** (本担当作業後も 6/6 check 正常、tools/ott は未改変 — 作業中に観測した
未コミット差分は並行担当 CAB-137+91 のもの)。

## 6. 未解決・限界 (実測ベース)

1. **0x6a7990 (MMX RGB 乗算) の dst 1-3 block が byte 単位で不一致** (16 case 中 2 case)。r戻り値・xmm0・他の
   メモリは一致。packuswb/pmulhuw の primitive 単位は実機 probe で式を確認済みゆえ、ループ内の状態伝搬
   (eax leftover の `shl eax,16` 経由引継ぎ等) の差と推定。再現: `python3 fle_diff.py` (harness 完備)。
   → CAB-232/233 の liftdiff 本格採点で原因特定を推奨。
2. **D12 (Delphi landing pad, 879 site)** は未対応 — CAB-227 の範囲。SEH/例外経路に入る関数は fail-fast。
3. x87 は制御命令のみのモデル (x87_cw/x87_sw)。FLEngine lift 集合に x87 演算は出現しないことを確認済みだが、
   集合外関数には x87 演算が残る。ldmxcsr/stmxcsr は値の退避のみ (FTZ/DAZ 等の演算反映は未実装)。
4. cpuid/rdtsc/xgetbv は固定値モデル (CPUID leaf1 = 0x178bfbff/1, XCR0 = 7)。CPU 特性分岐は SSE2 側に寄る。
5. .text は原則 data 敷設せず jump table 窓 (1) + rip-rel textref 窓 (3,225) のみ。.text をデータとして
   読む経路が他にあれば fail-fast で顕在化する。
6. FastMM boot (`_InitLib` 8 引数含む unit init 連鎖) は未実施 — M11 (CAB-5) の領域。本 ticket は lift 基盤。
7. native spot diff は single-thread 前提 (lock 系非 atomic)。

## 7. M11 chain への接続方針 (チケット要件 4)

- x64c lift の産物 (flel.wasm) は **恒等写像 (VA = guest address)** のため、M11 の image 敷設 (0x400000 ベース)
  とそのまま合流できる。dispatch 関数 `ott_dispatch` が 7,031 関数 + IAT pseudo-VA を網羅する。
- M11 unit#18 連鎖 (455790 → 44bb70 → 446400 → 4133f0) の leaf (_UStrAsg) とその内部経路 (lock xadd,
  zero-disp load, Move) は全て bit 一致済み (§5.3/5.4)。**M11 が RetDec で到達できなかった stage 4 の
  直接原因 (`_UStrAsg` 旧値読出し欠落 / record 縮退) は x64c では構造的に存在しない**。
- 次接続: (1) `fle_data_install` + Delphi unit init 連鎖 (memory manager table 設定) を M11 e2e に接続し、
  (2) unit #18 以降の unit init を x64c lift 関数で実行 → survey trap の解消を確認 (CAB-5/M11 再開時)。
- **実施済み (FLE-2, tools/flelift/boot/)**: boot 連鎖は DllMain → _InitLib → InitUnits まで実働
  (17 unit dispatch / 16 完走、unit#17 で FreeMem 失敗 raise)。survey 942 隔離 = ok 808 / oob 66 / unlifted 12 /
  halt0 9。詳細は **tools/flelift/boot/REPORT.md**、liftdiff FORMAT 記録は boot/results/verdict_boot.jsonl。

## 8. 再現

```sh
bash tools/flelift/fle_e2e.sh        # 約 2.7 分: lift → build → smoke → spot diff → D9 (全部)
python3 tools/flelift/probe_d9_disp.py            # D9 のみ (約 40 秒)
python3 tools/flelift/fle_diff.py                 # spot diff のみ (約 40 秒)
bash tools/flelift/fle_lift.sh                    # lift + build のみ (約 60 秒)
node tools/flelift/t_ustrasg.mjs                  # smoke のみ
bash tools/ott/ott_e2e.sh                         # OTT 回帰 (読取のみ, 約 15 秒)
```
前提: python3 (capstone, pefile), emsdk 6.0.12, node, gcc, setarch。PE は
`docs/REFERENCES.md` `[WIN64]` の `extracted/block00031_PE.bin` (FLE_PE で差し替え可)。
