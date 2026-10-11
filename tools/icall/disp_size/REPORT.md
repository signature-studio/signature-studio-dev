# tools/icall/disp_size — capstone `disp_size` 誤り (D9) 水平展開監査 (CAB-229)

## 0. 結論 (先出し)

- **D9 の正体は「66 prefix」であって F2 ではない**。capstone の x86 `disp_size` は、**REX.W 無しで 0x66 を伴う disp32 メモリ命令**
  (rip 相対 / `[reg+disp32]` / SIB / `[abs32]` の全部) で **2 を返す**。VEX2 (`C5`) の pp=66 でも同じ。F2/F3/F0/67/segment/REX 単独は無害。
  disp_offset・`mem.disp` 値・imm_offset/imm_size は全 case 正しい (§1)。チケット記載の「66/F2」は 66 起因の SSE (`66 0f ..`, `f2 66`) の混同。
- **上流で既に修正済み**: capstone `next` に PR #3105 (2026-10-08, closes #2613) が merge 済み。ただし **PyPI 全版 (5.0.5〜5.0.9, 6.0.0a11) は未修正**で、
  我々の環境 (pip 5.0.9 だが `capstone.__version__` は "5.0.7" と出る) は再現する (§2)。`next` HEAD を実ビルドして matrix 0 誤りを確認。
- **規模**: 全 12 サンプルで誤りの原因は 66 prefix 1,903,831 件 + VEX2.pp66 3,306 件のみ (その他 0)。rip 相対の誤り率は OTT F **10.5%** (103/985, チケット値 103 に一致),
  KH HeartCore closure 9.6%, Fresh Air closure 6.9%, Balance closure 6.9%, FLEngine 全 1.9%, Delphi 133 DLL 3.1%。**関数 fingerprint は 133 Delphi DLL の 2.81% (51,645 関数) の hash が変わる** (§3)。
  一方 `mem.disp` 値だけを使うコード (x64c / liftlib / khmach / ldmach ほか 43 ファイル) は 6,339,109 件検証して不一致 0 = **無影響**。
- **共通 helper `dispfix.py`** を提供: prefix/opcode map/VEX/EVEX/modrm/SIB を自前解析して disp 位置・長さを確定。1,695,726 case の matrix で不一致 0、
  binutils objdump の命令長と 35,822 件一致/0 不一致、**修正済み capstone (next HEAD) でも不一致 0 (前方互換)** (§4)。
- **適用**: fw_overlap.py / kernel_matrix.py / mac_funcs.py に直接適用。win_funcs.py は **opt-in (`WINFUNCS_DISPFIX=1`, 既定 OFF)**: 同規約を framework/fw_prep.py (CAB-194 稼働中・編集禁止) が
  再計算して突合するため片側だけ変えると framework 判定が静かに縮む。fw_prep.py の差分と lockstep 移行手順は §5。
- **回帰**: p0c kernel 表 hash 突合 **(79/80 + 1 mismatch) × 129 DLL → 80/80 × 130/130 DLL** (kernel_va_map の未対応 129→0, 呼出 site 3,763→3,763 不変)。
  tools/ott `ott_e2e.sh` PASS (89 scenario / 50,236 cell 全て native と bit 一致, state 差 0; ott は無変更), tools/icall `tests/test_icall.py` と `icall_e2e.sh` も PASS (§6)。

## 1. 再現 (prefix × opcode map × modrm 形式の全組合せ)

`python3 repro_min.py` (13 case, 1 秒) / `python3 prefix_matrix.py --jobs 14 --objdump 100000` (約 10 秒)。

オラクル = 構築時に既知の位置 (prefix* [REX] opcode modrm [sib] disp imm を自分で組む。capstone 値は不使用)。補助オラクル = binutils objdump の命令長。
prefix: {66, F2/F3, F0, 67, seg} の直積+逆順 / REX 7 種 / map {1B, 0F, 0F38, 0F3A} 全 256 opcode / VEX2・VEX3・EVEX (pp×L×W×map) / modrm 形式 7 (rip, d8, d32, SIB d8/d32/無base, disp 無し)。

| opsize 区分 | case 数 | capstone disp_size 誤り | disp_offset 誤り | imm 誤り | dispfix 不一致 |
|---|--:|--:|--:|--:|--:|
| 無 66 (VEX2 pp=66 を含む) | 846,947 | 9,400 (全て VEX2.pp66: 9,400/15,040) | 0 | 0 | 0 |
| 66, REX.W 無し | 405,036 | **252,028 (disp32 系 4 形式は 100%)**, disp8/disp 無しは 0 | 0 | 0 | 0 |
| 66 + REX.W | 443,743 | 0 | 0 | 0 | 0 |

- 採用 1,695,726 case / `mem.disp` 値の検証 1,440,808 件で値誤り 0。VEX3/EVEX の pp=66 は無害 (0/37,920, 0/35,020)。
- objdump 照合: 35,822 件一致・**不一致 0** (別途 6,482 件は objdump が不正 prefix 組合せ `(bad)` として拒否 = F2+66 mandatory 衝突等で比較対象外)。
- 例: `66 0f 2f 05 10 00 00 00` (comisd xmm0,[rip+0x10]) → `disp_size=2 disp_offset=4` (正: 4/4)。`66 8b 80 44 33 22 11` (mov ax,[rax+disp32]) も 2。

## 2. 原因と upstream 調査メモ

- 原因 (capstone v5 `arch/X86/X86DisassemblerDecoder.c`): 64bit mode の prefix 処理が `displacementSize = (hasOpSize ? 2 : 4)` (REX.W 無しの枝) を設定するが、
  disp32 を実際に読む `readDisplacement()` は `eaDisplacement` を見るだけで **displacementSize を更新しない** (disp8 は別所で 1 に上書きされるので正しい)。
  `disp_size` は `consumedDisplacement` 時のみ公開されるため、66 付き disp32 命令だけ 2 が露出する。VEX2 pp=01 は hasOpSize 扱いで同経路。
- 副作用の可能性: `translateImmediate` は rel 即値の符号拡張に `displacementSize` を使う (66 付き rel 命令は E8/E9/0F8x が特例処理済み。他経路は未調査)。
- 既存 issue: #1640 (2020-06-04, open, rip 相対+0x66), #1775 (2021-07-29, open, 同症状), **#2613 (2025-01-27 → 2026-10-08 closed)**。
  修正 = PR #3105 "X86: Fix displacement size with 0x66 prefixes" (next, 2026-10-08, merge 454d9ae): `readDisplacement()` の各 case で `displacementSize = 1/2/4` を設定 (3 行) + issues.yaml に回帰試験。
- **版別再現** (`bash check_versions.sh`; wheel の .so sha256 で識別): 5.0.5 / 5.0.6 / 5.0.7 / 5.0.8 / 5.0.9 / 6.0.0a11 は全て 7/13 case 誤報告、`next` HEAD (81497779, 2026-10-09 を cmake ビルド) は 0/13。
  `prefix_matrix.py` を next に当てると 1,429,044 case で 66 起因・VEX2 起因とも誤り 0。PyPI 最新は 6.0.0a11 (2026-09-21) で未収録 → **リリース版を待つなら dispfix 継続**、急ぐなら next ビルドか 3 行 backport。
- 環境注意: `pip show capstone` = 5.0.9 だが `capstone.__version__` = "5.0.7" (5.0.8/5.0.9 の python binding が定数を更新していない)。ticket/REPORT の「5.0.7」はこの表示由来。版の判定は .so の sha256 (5.0.9 = a0897f809e06)。
- 本件を upstream へ新規報告する必要は無い (#2613/PR #3105 で解決済み)。

## 3. 影響棚卸し

`python3 consumers.py` (git 追跡+未追跡 tools/ 配下を走査; results/consumers.md) と `python3 census.py` (results/census.json, 12 サンプル)。
区分 A = `disp_size/disp_offset` を読む (要補正) / B = `imm_*`, `modrm_offset` を読む (実測で誤り 0) / C = `mem.disp` 値のみ (値は全て正)。

A の実コード (補正前): `inventory/fw_overlap.py`, `inventory/win_funcs.py`, `inventory/mac_funcs.py`, `p0c/kernel_matrix.py`, `framework/fw_prep.py` の 5 本。
`p0c/verify_table.py` は CAB-196 で個別回避済み (disp32 を命令末尾から逆算)、`icall_rewrite.py` は modrm から自前計算 (§4 で dispfix と一致)。B 7 ファイル / C 43 ファイルは補正不要。
`tools/flelift/probe_d9_disp.py` (flelift 担当・未コミット) が x64c への影響無しを別途検証している (私は未実行)。

| サンプル | 命令数 | disp 有 | rip 相対 | rip 誤り (率) | disp32 非 rip 誤り | 誤り計 (nop 除く) | 関数 誤り有/全 |
|---|--:|--:|--:|--:|--:|--:|--:|
| OTT F (icall closure 282 関数, 到達命令) | 17,789 | 5,134 | 985 | 103 (10.46%) | 29 | 132 (115) | 17/282 |
| OTT F 線形 sweep (参考) | 18,864 | 5,333 | 1,002 | 105 (10.48%) | 79 | 184 (117) | 20/282 |
| FLEngine M11 closure (7,421 関数) | 341,713 | 139,708 | 27,839 | 501 (1.80%) | 490 | 991 (988) | 264/7,421 |
| Fruity Balance closure (67 関数) | 4,216 | 1,501 | 203 | 14 (6.90%) | 12 | 26 (26) | 11/67 |
| Fresh Air SlateCore closure (131 関数) | 6,267 | 2,052 | 231 | 16 (6.93%) | 19 | 35 (26) | 8/131 |
| KH HeartCore gain+infra (196 関数) | 12,578 | 3,865 | 1,153 | 111 (9.63%) | 52 | 163 (135) | 27/196 |
| FLEngine_x64.dll (全 .pdata) | 2,566,540 | 1,058,904 | 136,207 | 2,542 (1.87%) | 4,877 | 7,419 (7,340) | 1,590/57,816 |
| Fresh Air SlateCore (全 .pdata) | 3,526,710 | 1,363,751 | 55,496 | 2,751 (4.96%) | 6,587 | 9,338 (6,026) | 2,877/25,063 |
| KH HeartCore (全 .pdata) | 4,995,580 | 1,682,527 | 125,547 | 4,439 (3.54%) | 16,724 | 21,163 (11,916) | 6,952/111,666 |
| Serum2 win64 vst3 (全 .pdata) | 2,515,362 | 807,737 | 91,724 | 3,751 (4.09%) | 19,289 | 23,040 (15,063) | 4,916/33,791 |
| Delphi plugin 133 DLL (全 .pdata) | 68,681,048 | 25,703,502 | 2,791,307 | 87,126 (3.12%) | 263,037 | 350,163 (340,853) | 53,640/1,837,410 |
| mac Fruity Mach-O x86_64 slice | 67,002,757 | 25,540,240 | 3,107,415 | 31,007 (1.00%) | 1,463,476 | 1,494,483 (143,620) | 739,006/1,274,001 |

- 「誤り計」の大半が mac の 1,350,863 個の `nopw 0x0(%rax,%rax,1)` (関数間パディング; disp は 0 で hash 無害)。nop を除いた実質の誤りは括弧内。
- OTT F の 103 はチケット値と一致 (分母はチケットの 916/959 でなく audit_icall の到達命令 985。数え方の違いで、916 は未特定)。
- 誤りの命令: Delphi は `movd/movdqa/pand/ucomisd`、OTT/KH は `comisd/vcomisd/vandpd/vmovapd/vpand`、mac は nopw 以外で `movdqa/movapd`。
- 全 sample 合計で rip 相対 `mem.disp` 値 6,339,109 件・imm_offset とも不一致 0。67 付き rip 相対 (capstone は base=EIP で `base==RIP` 判定を素通り) は 0 件、phantom disp 0 件。

ツール別 (対象命令 = そのツールが disp を見る命令):

| ツール | disp の使い方 | サンプル | 対象命令数 | capstone 誤り (率) | 関数 hash 変化 |
|---|---|---|--:|--:|--:|
| fw_overlap.py / kernel_matrix.py | disp_size==4 の全 disp32 をゼロ化 | Delphi 133 DLL | 10,153,246 | 350,163 (3.45%) | 51,645/1,837,410 (2.81%) |
| win_funcs.py | rip 相対 disp32 のみゼロ化 | 同 (hash は 180 PE) | 2,791,307 | 87,126 (3.12%) | 38,369/2,012,968 (1.91%) |
| framework/fw_prep.py (同規約・編集禁止) | 同上 | FLEngine 全 / Balance closure | 136,207 / 203 | 2,542 (1.87%) / 14 (6.90%) | Balance: 170/11,736 |
| mac_funcs.py | rip 相対のみ | mac Fruity slice | 3,107,415 | 31,007 (1.00%) | SimSynth で 20/340 (全体未計測) |
| icall_rewrite.py | modrm から自前算出 | OTT F | 985 | 影響 0 (icall_e2e 89/89 bit 一致, §6) | - |

fingerprint への影響 (`impact_hash.py`; legacy が stored 成果物を再現することを確認: fw_overlap.json 集計一致 / winfuncs/*.json hash 180/180 PE 一致):
- fw_overlap 規約: distinct hash **47,487→40,492** (同一関数が 66 disp 差で別 hash に割れていた), ≥13 DLL 共有 10,836→10,875, framework 関数/DLL 中央値 12,475→12,529,
  fw_fraction 中央値 0.958→0.966, Balance 関数 byte の他 DLL による被覆 中央値 0.961→0.970 (≥0.9 の DLL 120→124)。**CAB-196 以前の framework 共有度の数値は ~1% 低め**。
- win_funcs 規約: distinct 53,046→46,117, ≥13 DLL 共有 11,266→11,306, framework 判定の関数 1,755,661→1,762,730 (**非fw→fw 7,069 / fw→非fw 0**, +1.83MB)。Balance 単体: fw 関数 11,659→11,711 (+52), fw byte 1,614,463→1,627,995。
  → 誤差は一方向 (fw を取りこぼす側) なので既存 framework 集合は部分集合として有効だが、frontier 判定 (plugin_closure) は 0.35% 取りこぼしていた。

## 4. 共通対処モジュール `dispfix.py`

`import dispfix as D` (sys.path に `tools/icall/disp_size`)。capstone 非依存の部分 (`layout(raw)`) と CsInsn 向け API:

| API | 内容 |
|---|---|
| `D.disp_span(ins)` → `(offset,size)\|None` | 補正済み disp 位置/長さ。`ins.disp_offset/disp_size` の drop-in (66 / VEX2.pp66 を吸収) |
| `D.disp_size(ins)`, `D.disp_offset(ins)` | 同上を個別に |
| `D.zero_disp32(buf, insn_off, ins)` | 正規化 hash 用に disp32 をゼロ化 (旧 `if ins.disp_size==4: nm[..]=0` の置換え) |
| `D.is_rip_relative(ins)`, `D.rip_target(ins)` | mod=00 rm=101 判定 / address+size+disp (raw から再読込, 67 は 32bit 折返し) |
| `D.layout(raw, has_modrm_=None)` | prefix(legacy/REX/VEX2/VEX3/EVEX/XOP)・map・opcode・modrm・SIB・disp・moffs(A0-A3) を自前解析。modrm 有無は opcode 表 (`has_modrm`) か capstone `modrm_offset` |
| `D.opsize(lay)`, `D.immz_size(lay)`, `D.addrsize(lay)` | 実効オペランド長 (REX.W > 66 > 既定4) / Iz 長 (66→2) / アドレス長 (67→4) |
| `D.d9_affected(ins)`, `D.capstone_has_d9()` | その命令で capstone が誤っているか / 実行中 capstone に D9 があるか (起動時 canary; 修正済み版では False) |

検証: `tests/test_dispfix.py` (80 check: 手組 19 case × {disp_span, layout, rip 判定} + opsize/immz/addrsize + d9 API, **has_modrm 表 == capstone modrm_offset を 4,976 件で全一致**, `icall_rewrite.modrm_tail_len` と sib+disp 長が一致 = icall は D9 の影響外)。imm は補正不要 (imm_offset/imm_size 誤り 0)。
REX が legacy prefix の前にある場合 (REX 無効) も扱う (KH の data-in-code 1 命令で発覚し修正済み)。EVEX の disp8*N は disp_size=1 のまま (圧縮は値側の話)。未対応: 3DNow (0F 0F) 接尾 opcode, XOP の modrm 有無表。

## 5. 適用手順書

共通: `sys.path.insert(0, '<repo>/tools/icall/disp_size'); import dispfix as DF`。**判断基準** = ①disp の「バイト位置/長さ」を使う (ゼロ化・再配置・パッチ) → 要適用 ②`mem.disp` 値から VA を計算するだけ → 不要。

| パターン | 置換え | 状態 |
|---|---|---|
| hash 正規化 (全 disp32) `if ins.disp_size == 4: nm[o+ins.disp_offset : +4] = 0` | `DF.zero_disp32(nm, o, ins)` | **適用済**: fw_overlap.py, kernel_matrix.py |
| hash 正規化 (rip 相対のみ) `if ins.disp_size == 4: for op in ops: if MEM and base==RIP: range(ins.disp_offset, +4)` | `dsp = DF.disp_span(ins); if dsp and dsp[1] == 4:` … `range(dsp[0], dsp[0]+4)` | **適用済**: mac_funcs.py / **opt-in**: win_funcs.py (`WINFUNCS_DISPFIX=1`) / **未適用**: framework/fw_prep.py |
| 命令書換え (disp 再配置) | disp 位置は `DF.disp_span(ins)`。modrm の再構成は `layout()` の mod/rm/sib_offset | icall_rewrite は自前 (適用不要) |
| 新規パーサ | `ins.disp_size`/`disp_offset` を直接読まない。rip target は `DF.rip_target(ins)` | - |

**framework/fw_prep.py の lockstep 移行** (CAB-194 完了後に実施; 私は編集せず):
1. `fw_prep.py` 冒頭に `sys.path.insert(0, os.path.join(HERE, '..', '..', 'icall', 'disp_size')); import dispfix as DF` を追加し、71〜74 行を
   `dsp = DF.disp_span(ins)` / `if dsp and dsp[1] == 4:` / `nm[o + dsp[0]:o + dsp[0] + 4] = b'\0\0\0\0'` に置換 (win_funcs と同形)。
2. `win_funcs.py` の既定を ON にする (`DISPFIX = os.environ.get('WINFUNCS_DISPFIX') != '0'`)。
3. `work/winfuncs/*.json` と `work/fw_hash_counts.json` を再生成 (`python3 inventory/win_funcs.py` → `rm work/fw_hash_counts.json` → `plugin_closure.fw_counts()`)。
4. `plugin_closure.py --all` と `fw_prep.py` を再実行。**期待差**: framework 関数 +7,069 (Balance +52, fw byte +13,532)。3 を飛ばして 1 だけ入れると framework 判定が静かに縮む (hash 不一致)。
- 事前確認: `python3 impact_hash.py` が現状の legacy/fixed 差を再計算する。
- `tests/test_icall.py` の「capstone disp_size 誤り (66 prefix rip-rel) を検知」は D9 の canary (既存・未改変)。capstone を修正版へ上げると **FAIL になるのが正** (この時点で dispfix は不要化可能だが無害)。

## 6. 回帰 (実測)

| 項目 | 結果 |
|---|---|
| p0c kernel 表 hash 突合 (`p0c_regress.py`: 修正後 kernel_matrix.scan_dll を 181 PE に実走; Delphi かつ init 発見 130) | (kernels_hash_ok, bad) **(79,1)×129 + (80,0)×1 → (80,0)×130**。80/80 DLL 1→130。mismatch 件数 {1:129, 0:1}→{0:130}。kernel_va_map の未対応を含む DLL 129→0。init_va/nvars/nimpls 変化 0、呼出 site 3,763→3,763 |
| 参考: CAB-196 の個別回避版 `verify_table.py` | 130/130 で 80/80 (CAB-196 報告値; p0c の成果物を上書きするため本回は未再実行)。本回は kernel_matrix 本体の修正で同じ結論に到達 |
| tools/ott `bash tools/ott/ott_e2e.sh` | PASS (15 秒): scenarios 89, failed 0, cells 50,236 全て bit 一致 (max_ulp 0), state_diff 0, std 512/512。ott は無変更 (作業ツリーに他担当の未コミット変更 x64c.py / ott_cpu.[ch] が有り、それを含む状態での結果) |
| tools/icall `python3 tests/test_icall.py` / `bash tools/icall/icall_e2e.sh` | 単体 PASS (0 failed; OTT F rewrite sites 96, errors {}) / e2e PASS: 89 scenario 全て bit 一致 (50,236 cell, max_ulp 0, state 差 0)。e2e は /tmp が quota 超過 (他担当の大量一時ファイル) で emcc が失敗したため `TMPDIR`/`EMCC_TEMP_DIR` を実ディスクへ向けて実行 |
| tools/icall 既存ファイル | 変更 0 行 (`git diff --stat tools/icall` 空; 追加は disp_size/ のみ) |
| p0c の `work/kernel_matrix.json` | 上書きせず (回帰は import して `work/kernel_matrix_fixed.json` へ出力) |

## 7. CAB-55 (liftlib DEFECTS 信号) への引継ぎ

- liftlib/mc.py は `ci.address+ci.size+op.mem.disp` と `ci.bytes` しか使わず **D9 の影響を受けない** (値 6,339,109 件検証)。lift 結果自体には波及しない。
- ただし liftdiff/liftlib が将来 `disp_offset/disp_size` を読む (関数 fingerprint・relocation 風マスク・命令書換え) 場合に備え、DEFECTS に **メタデータ欠陥の信号**を追加することを提案:
  1. 起動時 canary: `DF.capstone_has_d9()` をレポートヘッダに記録 (capstone 更新で自動的に False になる)。
  2. 命令単位の信号: `DF.d9_affected(ins)` を `Insn` の flag にし、DEFECTS 集計で「D9 該当命令数 / 関数数」を出す (閾値無し・情報用)。
  3. 命名: 本件 D9 は icall の欠陥番号。`docs/DEFECTS.md` の D9 (`jmp reg` → `ret undef`) とは別物なので、レジストリでは `CS-D9 (capstone disp_size)` のように接頭辞で区別することを推奨。
- 66 prefix 起因の別の capstone 症状は未発見 (matrix で imm/offset/値は 0 誤り)。ただし `translateImmediate` が displacementSize を rel 符号拡張に使う点 (§2) は未検証。

## 8. 限界・次タスク

- hash 影響の全体値は Delphi 133 DLL 系のみ (mac_funcs は SimSynth 1 本)。mac 全体の hash 変化率・Serum2/KH の fingerprint 利用は未計測。
- matrix の網羅外: XOP, 3DNow (0F 0F), 16bit アドレス (67 in 32bit mode), MPX/ APX 拡張 REX2。実バイナリ 12 サンプルでは該当無し (原因 66/VEX2 以外 = 0)。
- census の KH 全 .pdata は dispfix の REX 修正後に単独再実行して差し替え (他 11 サンプルは修正前の同一コードの実走。差は 1 命令のみ)。
- 次タスク案: (a) CAB-194 完了後に §5 の lockstep 移行 (別チケット), (b) capstone を next 系へ更新するか判断 (PyPI 6.0.0 正式版待ち), (c) liftlib に §7 の信号 (CAB-55 派生), (d) mac_funcs 全体の再計測。

## 付録: 成果物と再現

`bash tools/icall/disp_size/disp_size_e2e.sh` (約 1 分) / `--full` (約 25 分: 全 .pdata census + impact_hash + p0c 回帰)。
`dispfix.py` 本体 / `repro_min.py` / `prefix_matrix.py` / `census.py` / `consumers.py` / `impact_hash.py` / `p0c_regress.py` / `check_versions.sh` / `report_tables.py` (表自動生成) / `tests/test_dispfix.py` / `results/*` (実測 JSON と表; 計 56KB)。
直接修正した既存ファイル: `tools/plugins/inventory/{fw_overlap,mac_funcs,win_funcs}.py`, `tools/plugins/p0c/kernel_matrix.py` (各 import 1 行+置換え数行; `git diff` 参照)。
