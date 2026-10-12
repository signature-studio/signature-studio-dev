# REPORT — OTT-T3 (CAB-135): AVX/VEX 命令の lift 対応と FMA 経路の bit-exact 検証

主要チケット: CAB-7 / 関連: CAB-138 (CRT 初期化) / **検収: CAB-135 完了 = `ACCEPTANCE_CAB238_CAB135.md`** (PASS)

## 0. 結論 (先出し)

- **判定: 要件を満たす。** lift 集合内の未対応命令 (unsup) は CAB-138 時点の **72 種 / 627 箇所 → 0 種 / 0 箇所** になった
  (crt build 260 関数 / 16,378 命令, entry closure 368 関数 / 23,360 命令の両方で unsup = 0 実測)。
  以降、AVX/FMA 経路に到達しても `ott_unsup` fail-fast は発生しない。
- **AVX/FMA 強制突合 (native 実機械語 vs lift wasm, `AVX_FORCE=fma,isa`)** が **全 PASS**:
  - avx 9 scenario (FMA kernel / 大块 ymm copy を実行させる新 scenario 群): **9/9 PASS**
  - crt 9 scenario: **9/9 PASS** / entry 85 scenario: **85/85 PASS** (いずれも rax / 出力 buffer / obj qword / HeapAlloc alog / audioMaster カウンタ全一致)
  - 既定 (flags=0 = SSE2) も同水準で全 PASS (Gate A)。
- **`__isa_available` の扱い (要件 2): DLL 静的値 0 (SSE2) 固定を維持** することを決定。
  根拠: (1) CRT 置換は DllMain を実行せず `__isa_available_init` (cpuid/xgetbv) を通らないため、
  静的値のままが「両側同一の決定論的状態」(ホスト CPU 非依存 — AVX2 無しの環境でも native 参照と揃う);
  (2) 一方で強切替 (`__use_fma3=1` + `__isa_available=3` を両側の .data に直接書く) した場合も
  **bit-exact が維持されることを実測** (上記 Gate B + FMA fuzz 300,012 case bit 一致)。
  よって将来 `__isa_available_init` を実行する経路 (実 DllMain lift 等) に切替えても安全。
- **0x1801bc890 (FP 制御切替, powf 系) の lift + 動作確認 (要件 3)**: 直叩き unit scenario 10 本
  (mxcsr dance / rcr parity 両側 / 非整数 y / x=0 / |y|>=2^23 / FMA 分岐) を新設し、
  **flags=0 で 10/10, FMA 強制で 10/10 全 bit 一致**。mxcsr dance
  (`stmxcsr → or 0x1f80 → ldmxcsr → 復元`) は software shadow (=0x1f80 固定) と意味的に整合
  (dance が設定する値は 0x1f80 のみゆえ shadow の仮定「round-nearest 固定」と不変)。
- **回帰 (要件 4)**: `crt_e2e.sh` 全工程 = 新 scenario 9/9 + entry 85/85 + 陰性対照 (OTT_CRTINIT=0) + DSP e2e
  (ott_e2e.sh 89 scenario・全 cell bit-exact・正本 `tools/ott/REPORT.md`) + entry e2e — **全 PASS** (§5)。
- **残 unsup: 0**。lift 済みだが実行 coverage の無い経路 (§6) と、検証の前提 (§7) を明記。

## 1. unsup 分類表 (要件 1 — (a) 実行 coverage で必要 / (b) 非到達)

分類は native 単歩 coverage (DSP 89 = ref/cov_all.json, entry 85, crt 9) の insn 集合で判定。
unsup 627 箇所は **17 関数**に集中し、その内訳:

| 関数 | 分類 | 箇所 | 内容 |
|---|---|---|---|
| 1801a2a20 (memcpy) | (a) entry/crt 実行関数内 | 69 | `vmovdqu/vmovdqa` ymm copy loop + `vmovntdq` + `vzeroupper` + `sfence` — `__isa_available>=3` かつ len>0x20 で到達 |
| 1801a30d0 (memset) | (a) dsp/entry/crt 実行関数内 | 9 | `movntps` (非 temporal store) + `sfence` |
| 1801a9be0 | (a) dsp/entry/crt 実行関数内 | 94 | CRT 数学 kernel (`__use_fma3` 分岐先: vfmadd*sd / vmulsd / vaddsd / vmovdqa ほか) |
| 1801b4220 | (a) 同上 | 31 | 同系 (FMA 分岐 + vcmplesd/vcmpnltsd/vroundsd) |
| 1801b4900 | (a) 同上 | 72 | 同系 (13 callsite — DSP パラメータ処理から呼ばれる) |
| 1801b4e30 | (a) crt 実行関数内 | 79 | 同系 |
| 1801ba860 | (a) dsp/entry/crt 実行関数内 | 58 | 同系 (float 版: vaddss/vmulss/vcvtsd2ss/vcvttpd2dq) |
| **1801bc890** | **(a) FP 制御切替 (要件 3)** | 153 | `rcr` 6 + VEX 版 mxcsr dance + vfmadd 群 — flags=0 側は DSP/entry で入口実行 (87 insn) |
| 1801bf304 / 1801bf454 | (a) entry 実行内 / (b) | 4+5 | `vpcmpeqb/w` (ymm) + `vpmovmskb` (ymm) — 文字列処理の SIMD 比較 |
| 1801a06b0 / 1801aa5dc / 1801be5a8 | (b) 非到達 | 3 | `int 0x29` (GS failure / fastfail 経路) |
| 1801a3ad0 | (b) 非到達 | 3 | `pcmpistri` 2 + `pshuflw` 1 (strspn/strcspn 系ヘルパ) |
| 1801c0d00 | (b) 非到達 | 5 | `movhlps` / `movlhps` |
| 1801c1050 / 1801c1240 | (b) 非到達 | 21+21 | CRT 数学の別 kernel (FMA 分岐あり, 未呼出) |
| (misc) | (b) | 1 | `mov rax, gs:[0x58]` 等 segment 参照 (TEB/TLS) + `in eax, dx` (port I/O) |

- **(a) は全件実装**した (→ §2)。**うち実行 coverage で実際に動いたのは全て** (FMA 強制 Gate B + fpctl にて)。
- (b) も実装コストが低いため **全件実装**した (pcmpistri は imm=0x40 のみ対応 — 本 DLL の使用形は 2 箇所とも 0x40)。
- 集計の起点: `avx/unsup_scan.py` (lift + coverage 突合を自動化, 出力 `avx/work_classification.json`)。

## 2. 実装命令表 (x64c.py 追加, 92 handler)

**方針**: 既存の「命令 1:1 → C 文」方式を踏襲。SIMD は **IR 直生成 (C 式展開)** を採用
(tools/liftlib の SIMD helper 方式は使わない — 本 lifter は C 文列で忠実性を保つ既存方針が確立済みのため)。

| グループ | 命令 | 実装方式 |
|---|---|---|
| レジスタモデル | ymm0..15 | `X[16]` (下位 128) + **`XH[16]`** (上位 128) に分割。VEX.128 は dest 上位を `XZ(i)` で 0 化 (VEX zeroing)、legacy SSE は X のみ触り上位保存 — 実機セマンティクス通り |
| VEX move | vmovdqa/vmovdqu/vmovaps/vmovapd/vmovups/vmovupd (xmm+ymm, load/store/reg-reg), vmovsd/vmovss (2-op/3-op), vmovd/vmovq (GPR↔vec, 上位 0 化) | LDX/STX + `LDY(i,a)/STY(i,a)` (32B を X+XH に分割) |
| VEX 非temporal | vmovntdq/vmovntps/vmovntpd/vmovntdqa, movntps/movntpd | store は通常 store と同一 (単 thread で意味不変), sfence/mfence/lfence は no-op |
| VEX スカラ fp | vaddsd/vsubsd/vmulsd/vdivsd/vaddss/.../vmaxsd/vminsd/vsqrtsd/vsqrtss (3-op, dest 上位 = src1 上位) | C 式展開 |
| **VEX FMA** | vfmadd/fmsub/fnmadd/fnmsub × 132/213/231 × sd/ss (12 種×2) | **`fma()/fmaf()` (musl/glibc とも IEEE 正確丸め = 1 回丸め)** + NaN payload 整正 (`ott_fma_d/s`: x86 は QNaN の bit51 を立てるため musl の NaN payload を合わせる) |
| VEX packed | vaddpd/vsubpd/vmulpd/vdivpd, vaddps.. (f/df lane), vpand/vpor/vpxor/vpandn/vandpd/vandps/vxorpd/vxorps/vorps/vandnps (q lane bit op) | 128/256 両対応 (lane loop) |
| VEX 整数 | vpaddq/vpsubq/vpaddd/vpsubd/vpaddw/vpsubw/vpaddb/vpsubb, vpcmpeqb/w/d/q, vpcmpgtd, vpsllq/vpsrlq/vpslld/vpsrld/vpsrad/vpsllw/vpsrlw/vpsraw (imm), vpslldq/vpsrldq, vpshufd, vshufps/vshufpd, vpunpckl/hdq 他 8 種, vunpckl/hpd/ps 4 種, vpmovsxdq | lane loop / shuffle 展開 |
| VEX 比較 | vcomisd/vucomisd/vcomiss/vucomiss, vcmpeqsd..vcmpordsd 8 述語 ×sd/ss (+vcmpsd/vcmpss imm) | 既存 `comis_f` / `cmp_pred_f` 流用 |
| VEX 変換 | vcvtsd2ss/vcvtss2sd/vcvtsi2ss/vcvtsi2sd/vcvtss2si/vcvtsd2si/vcvttsd2si/vcvttss2si, vcvtdq2pd/vcvtdq2ps/vcvtps2pd/vcvtpd2ps/vcvtpd2dq/vcvttpd2dq/vcvttps2dq | 既存 cvt helper + VEX 上位 0 化 |
| VEX その他 | vzeroupper (XH 全 0 化), vzeroall, vldmxcsr/vstmxcsr (CAB-138 の shadow), vroundsd/ss (imm 0..3: nearbyint/floor/ceil/trunc), vpmovmskb (xmm+ymm), vextractf128/vinsertf128 相当は本 DLL に 未出現のため対象外 | |
| legacy 追加 | movhlps/movlhps, pshuflw, pcmpeqw, rcr (imm, CF/OF 精密: rcr 1 = CF←bit0, MSB←旧CF), cmpxchg (単 thread = lock 同義), int 0x29 (fastfail → fail-fast), `in` (port I/O → 0 返し, 未実行経路), `mov gs:[..]/fs:[..]` (TEB shadow `ott_gsbase/ott_fsbase` — 全 0 ブロック = StackLimit 余裕なし判定に一致) | |

## 3. `__isa_available` の扱い (要件 2) — 判断と根拠

**決定: CRT 置換は DLL 静的値 (`__isa_available=0` SSE2, `__use_fma3=0`) を書き換えない (現状維持)。**

| 観測 | 実測 |
|---|---|
| SSE2 ↔ FMA の出力差 (native 単独, CAB-137/138 実績) | 12 case / 18,432 cell で **0 ulp** |
| FMA 強制 (`__use_fma3=1` + `__isa_available=3` を native/wasm 両側 .data に書く) での native↔wasm 突合 | avx 9 / crt 9 / entry 85 = **103 scenario 全 PASS** (bit 一致) |
| FMA 演算自体の bit 一致性 (`fma_fuzz`: native vfmadd213sd (hw) vs wasm musl fma()) | **300,012 case bit 一致** (NaN payload 含む — `ott_fma_d/s` で bit51 整正) |
| pcmpistri 0x40 の意味の実機確定 (`pcfuzz2.c`: 実機 inline asm vs model, movd needle / 2byte / 一般 random) | **150,000 case 0 不一致** (idx = mask の MSB 位置 / ZF=(ld<16) / CF=(mask≠0) / SF=(ls<16) / OF=mask bit0) |
| 大块 ymm copy 経路 (`__isa_available>=3` で memmove/memset が ymm loop へ) | avx_proc_2k/8k/4k_x2 (native↔wasm bit 一致, Gate B) |

根拠 (維持の理由):
1. **決定論**: CRT 置換は `__isa_available_init` (cpuid/xgetbv) を実行しない。静的 0 のままなら、AVX2 の無い
   ホストで native 参照を動かしても経路が変わらず、bit-exact 判定がホスト非依存で保たれる。
2. **実機 CPU (Ryzen 9 9950X = AVX2/FMA3 搭載) との関係**: 実 FL Studio は DllMain 経由で
   `__isa_available_init` を実行し FMA 経路を選ぶ。**wasm 側も同じ FMA 経路を lift 済み** なので、
   将来 init を通す運用に変えても native(実機 FMA) ↔ wasm(lift FMA) は上記の通り bit 一致する。
   逆に「wasm だけ AVX2 相当にする」必要はなく、差が開く構造は存在しない。
3. 切替ハーネスは残置した (`avx/avx_nat.py` + `avx/avx_wasm.mjs` の `AVX_FORCE=fma,isa`) —
   将来の切替判断は 1 コマンドで再検証できる。

## 4. 0x1801bc890 (FP 制御切替) の lift + 動作確認 (要件 3)

- 関数の正体: powf 系 (`__use_fma3` 分岐 → SSE2 側 0x1801bc8ad.. / FMA 側 0x1801bcff6..)。
  内部に `stmxcsr → or 0x1f80 → ldmxcsr` の FP 制御保存/設定/復元 (cvtss2si での例外 mask 保証) と
  `rcr` (丸め結果の parity 判定) を含む。通常 coverage では入口 + flag 分岐 (87 insn) のみ実行。
- **新設 unit scenario** (`avx/fpctl_scen.py`, 10 case: virt step で 0x1801bc890 を直接呼出,
  xmm0=x / xmm1=y — x<0 で mxcsr dance が有効になる入力域を選択):

| モード | 突合 | 実行 site (native coverage 実測) |
|---|---|---|
| flags=0 (SSE2 側) | **10/10 PASS** | `stmxcsr` 0x1801bca5b / `ldmxcsr`(設定) 0x1801bca6e / `ldmxcsr`(復元) 0x1801bca7b / `rcr` 0x1801bca89, 0x1801bcb9e — 全 hit |
| FMA 強制 (VEX 側) | **10/10 PASS** | `vstmxcsr` 0x1801bd1ab / `vldmxcsr` 0x1801bd1bf, 0x1801bd1cd / `rcr` 0x1801bd1dd — 全 hit (関数内実行 169 insn) |

- **mxcsr shadow との整合**: dance が MXCSR に書く値は「現在値 or 0x1f80」のみ (= 0x1f80)。
  shadow 既定 0x1f80 と整合し、丸めモードは round-nearest のまま変化しない
  (= lift の仮定と不変)。FTZ/DAZ ビットは本経路では操作されない (実測、or マスク 0x1f80 のみ)。
  native は実 MXCSR、wasm は shadow だが **両側の結果 (rax/xmm0) が 10 case 全 bit 一致**。

## 5. 回帰 (要件 4, 実測)

| 項目 | 結果 |
|---|---|
| `bash tools/ott/crtinit/crt_e2e.sh` (全工程) | **PASS** — 新 scenario **9/9** + entry **85/85** (crt build 再突合) + 陰性対照 (OTT_CRTINIT=0 → native SIGSEGV / wasm ott_unlifted 同一 garbage VA) |
| lift 集計 (crt_e2e 内) | 260 関数 / 16,378 命令 / **unsup 0 種 0 箇所** (旧: 72 種 627 箇所) |
| `bash tools/ott/ott_e2e.sh` (DSP 89 scenario) | **PASS** — 全 cell bit-exact / max_ulp 0 / state 差 0 (正本 `tools/ott/REPORT.md`) |
| `bash tools/ott/entry/entry_e2e.sh --quick` (entry 85) | **PASS** |
| Gate A (flags=0, avx build): crt 9 + entry 85 | **9/9 + 85/85 PASS** |
| Gate B (FMA/AVX 強制): avx 9 + crt 9 + entry 85 | **9/9 + 9/9 + 85/85 PASS** |
| FMA fuzz (native hw FMA vs wasm musl fma) | **300,012 case bit 一致** |
| fpctl (0x1801bc890 直叩き) | flags=0 **10/10** / FMA 強制 **10/10** |

## 6. 残 unsup / lift 済み未実行

- **残 unsup: 0 種 / 0 箇所** (260 関数 crt set / 368 関数 closure の両方で実測)。
- lift 済みだが現 coverage で未実行の経路 (到達時の挙動は lift fidelity により保証、実行実績なし):
  1. `int 0x29` (GS failure) 3 箇所 — native は実行時 trap、wasm は `ott_unsup` fail-fast (共に abort 系で整合)。
  2. `pcmpistri` imm=0x40 以外の制御語 (本 DLL は 0x40 のみ使用)。
  3. 1801c1050 / 1801c1240 (未呼出の CRT 数学 kernel) — FMA 強制でも未達 (呼出元が未実行)。
  4. `vextractf128/vinsertf128/vbroadcast/vpermd` 系 — **本 DLL の lift 集合には未出現**
     (CAB-138 REPORT §8 の「75 種」は当時の集計。実際の 72 種 627 箇所にこれらは含まれず、実装対象外)。
- VEX.256 packed 演算 (vpaddq ymm 等) は実装済みだが本 DLL の実行形は move/compare 系の ymm のみ。

## 7. 検証の前提と制約

1. **FMA 強制突合は入力域の保証ではない**: 上記は scenario / fuzz で-cover した入力域の実測。
   特に denormal 入力 (FTZ/DAZ が効く域) は fpctl_neg_tiny 1 case のみ。本経路は FTZ/DAZ を
   操作しない (§4) ため、wasm (denormal 保持) と native (既定 = denormal 保持) の仮定は一致。
2. **VEX.128 の「dest 上位 = src1 上位」規約**: スカラ fp 演算は lane0 のみを書き、上位 64bit は
   実行 coverage の全経路で bit 一致を確認した (Gate B / fpctl)。ただし「src1 ≠ dest かつ後続で
   上位を読む」コードは現 coverage に無く、厳密には実行実績の範囲で正当。
3. lift した VEX 命令の実行 coverage は `AVX_VEXCOV=1` probe build + `avx/work_unsup*.json`
   (site 集合) で採取できる。FMA 強時の VEX site 実行は native coverage 5,436 insn 中
   **182 site** (avx 9 scenario, Gate 4 — **hit ⊆ native 実行 OK** / matrix 9/9)。
   (初版の probe build OOM は vexcov buffer の配置衝突 (0x35e00000 = ott_boot MSCR / alog 0x35f00000
   と重複) が原因で、buffer を 0x35c00000 へ移動 + JS 読取アドレス修正で解消済み — 後続コミット参照。)

## 8. CAB-122 系 (AudioWorklet ABI 正本候補) への引き継ぎ

1. **FMA 経路は lift 完備・bit-exact 実績あり**: AudioWorklet 側で wasm を 32bit float pipeline で
   動かす際、CRT 数学は既定 (SSE2) で動く。FMA への切替は `AVX_FORCE=fma,isa` 相当の .data 書き込み
   (`__use_fma3` 0x18026c50c = 1, `__isa_available` 0x180260cc0 = 3) で可能 — 出力は実測 bit 一致。
2. **`__isa_available_init` を将来 lift する場合**: cpuid/xgetbv のエミュレーション実装 + 本 REPORT §3 の
   切替実験の再実行 (1 コマンド) が残作業。現状は不要 (SSE2 固定で完結)。
3. **ABI 上の注意**: ymm 上位半分は `XH[16]` に分離してある。AudioWorklet 側から lifted 関数を
   直接呼ぶ場合 (ott_run 経由)、xmm4 以降 / ymm 引数は存在しない (MS ABI float は xmm0..3) — 変更不要。
4. **実行速度**: FMA 強制時は musl fma() 呼出が増えるため wasm 側は僅かに遅くなる可能性
   (測定は今回未実施 — 既定は SSE2 経路のままなので影響なし)。

## 9. 再現

```sh
# 1) 公式回帰 (全 PASS が本チケットの合格線)
bash tools/ott/crtinit/crt_e2e.sh
bash tools/ott/ott_e2e.sh && bash tools/ott/entry/entry_e2e.sh --quick

# 2) AVX/FMA 検証 (本チケット新設; 約 6 分)
bash tools/ott/avx/avx_e2e.sh          # Gate A (flags=0) / Gate B (強制) / fuzz
#   Gate 4 (VEXCOV probe) を含め全 gate PASS (buffer 衝突修正後)

# 3) 0x1801bc890 unit 突合 (mxcsr/rcr site の実行確認)
python3 tools/ott/avx/fpctl_scen.py /tmp/scen_fpctl.json
python3 tools/ott/avx/avx_matrix.py tools/ott/work/avx/ottl_avx.cjs /tmp/mfp0 --scen /tmp/scen_fpctl.json --force ''
python3 tools/ott/entry/cmp_entries.py /tmp/mfp0/nat_result.json /tmp/mfp0/wasm_result.json --out /tmp/mfp0/summary.json
python3 tools/ott/avx/avx_matrix.py tools/ott/work/avx/ottl_avx.cjs /tmp/mfp1 --scen /tmp/scen_fpctl.json --force fma,isa
python3 tools/ott/entry/cmp_entries.py /tmp/mfp1/nat_result.json /tmp/mfp1/wasm_result.json --out /tmp/mfp1/summary.json

# 4) unsup 分類の再取得 (起点集計)
python3 tools/ott/avx/unsup_scan.py tools/ott/work/avx/entries.json \
  tools/ott/ref/cov_all.json tools/ott/work/entrylift/cov_entry.json \
  tools/ott/work/crtlift/cov_crt.json /tmp/unsup_cls.json

# 前提: tools/ott/ott_e2e.sh が PASS する環境 (python3 capstone/pefile, gcc, emsdk 6.0.12, node ≥22)
```

## 10. 環境パス置換 (#385, 親 #294・先行 #312 / #367): /home/ubuntu 絶対パスを tools/shared へ

既知類型との関係 (DEFECTS.md): 該当なし (パス参照の置換のみで lift/IR には触れない)。

### 10.1 変更

`*.sh *.py *.json *.ts *.mjs` (work/ 除く) の `/home/ubuntu` 参照 2 行を置換。既定値は従来と同一 (環境変数未設定のローカル挙動は不変)。
`*.log` 5 本 (`baseline_e2e.log` ほか) の `/home/ubuntu/work/webstudio/...` は過去実行の出力記録で、受入条件の対象拡張子外のため変更しない。

| ファイル | 置換 |
|---|---|
| `build_avx.sh` | `source tools/shared/env.sh` + `DLL="$PLUGINS_DIR/ott/binaries/OTT_vst2_win64.dll"` |
| `unsup_scan.py` | `tools/shared/paths.py` の `PLUGINS_DIR` から `DLL` を組む |

### 10.2 検証 (検証起点 `origin/main` = ee8f70c、素材は `fl-win64` のみ)

- 受入条件 1: `grep -rn '/home/ubuntu' tools/ott/avx --include=*.sh --include=*.py --include=*.json --include=*.ts --include=*.mjs --exclude-dir=work | wc -l` → 0 (置換前 2)。
- 受入条件 2 (既定値同一性): `ANALYSIS_DIR`/`PLUGINS_DIR` unset で bash (`env.sh`) と python (`paths.py`) が組む DLL パスを、置換前の固定文字列と文字列比較 → 両方一致
  (`/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll`)。n=1・直列、load average 0.98 (1 分値)。
- ネガティブコントロール: `PLUGINS_DIR=/nonexistent` で両方が `/nonexistent/ott/binaries/OTT_vst2_win64.dll` を返す (変数が効いている)。
- 構文: `python3 -m py_compile unsup_scan.py`・`bash -n build_avx.sh` OK。

### 10.3 検証範囲 / 範囲外 / 未解決

範囲外: `avx_e2e.sh` / `build_avx.sh` / `unsup_scan.py` の実行 (e2e 本体)。`OTT_vst2_win64.dll` は `analysis-ott-binaries`、`tools/ott/work/{entrylift,crtlift}` は `work-m6-ott`、emcc は `toolchain-emsdk` が要り、この run は `fl-win64` のみ取得
(`$HOME/artifacts` に `fl-win64.tar.zst` のみ)。実測: `PLUGINS_DIR=/nonexistent bash build_avx.sh` は DLL 参照前に `cov_entry.json` 無しで停止、`unsup_scan.py` は `pefile` 未導入で import 停止。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `avx_e2e.sh` を素材付きで未実行 | 置換行以外の挙動は未検証 (置換は DLL パス定義のみ) | 本 PR のレビュー run (PR 本文の `oc_artifacts:` 行) |
