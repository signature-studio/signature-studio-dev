# #2396 (LD-111): 変位形の検出信号を audit_lsf.py に統合し、残 SUSPECT 3 件を機械語と突合

既知類型との関係: `docs/DEFECTS.md` D20 (wrong-value reuse。load の offset が機械語と違う SSA 値の store への再利用)。親: #2316 (LD-108)。

**判定: 全て達成 (受入 3 項目)**。
- `audit_lsf.py` が変位形 (`SUSPECT_DISP_VAS`) を既存 3 判定の後に並べて出力する。`--no-disp` の出力は統合前と byte 一致、既定でも既存 3 行は一致 (§2)。
- 残 SUSPECT 3 件 (`6677a0` / `d237e0` / `de1da0`) は**全て誤検出**。原因は機械語側の列挙漏れ (文字列転送 `movsq`/`movsd` と `lea` 経由の変位)。IR は機械語の `movs` を忠実に lift している (§3)。
- 列挙を拡張した結果、`boot_final.ll` の変位形 SUSPECT は 4 → 1 件 (`41a670` のみ)。`fix_ld108.py` 適用後は 0 件 (§4)。ldfix 適用後の IR では既存判定の SUSPECT_VAS が 0 件になる一方、変位形は `41a670` を残す = 既存判定が拾わず変位形だけが拾う (§2)。
- `docs/DEFECTS.md` の D20 行の検出信号欄に反映した (§5)。

測定 commit: `c9a97944` (コードを変えた最後の commit。`audit_lsf.py` / `audit_lsf_disp.py` / `triage_ld111.py` / `negctl_484.sh` は `d3403ab2`、`ld111_e2e.sh` は `c9a97944`)。
`git diff c9a97944 HEAD -- tools/m11/ldfix/audit_lsf.py tools/m11/ldfix/audit_lsf_disp.py tools/m11/ldfix/triage_ld111.py tools/m11/ldfix/ld111_e2e.sh tools/m11/ldfix/negctl_484.sh` の出力は空 (§7)。
入力は素材 `work-m11` の `boot_final.ll` / `boot_final3.ll` / `m11_image.bin` / `boot*.drc.config.json` (PE 不要。`work-m11` は #516 qstore 以前の旧版 snapshot で `ir_conditions.json` 無し。`docs/WORKFLOW.md` §11・#680)。

## 1. 受入条件

| 受入条件 | 結果 |
|---|---|
| `audit_lsf_disp.py` の検出信号を `audit_lsf.py` の既存判定と並べて出力し、既存判定への影響を再測定 (件数・関数名) | **達成** (§2) |
| 残る SUSPECT 3 件を機械語の逆アセンブルと突合し、誤検出か列挙漏れかを判定 | **達成**。3 件とも誤検出 = 機械語の列挙漏れ (§3) |
| 判定結果を `docs/DEFECTS.md` の D20 行の検出信号欄に反映 | **達成** (§5) |

## 2. 統合と既存判定への影響

実装 (`audit_lsf.py`): 既存の関数ループの中で `audit_lsf_disp.disp_suspects(mach, va, body)` を呼び、結果を既存 4 行の**後ろ**に足す。`--no-disp` で変位形を省く。既存 3 判定 (`SUSPECT_VAS` / `SUSPECT_USE_VAS` / `SUSPECT_MIXED_VAS`) の算出・出力順・JSON の既存キーと順序は変えない。

```
SUSPECT_DISP_VAS 41a670
SUSPECT_DISP_ONLY_VAS   (SUSPECT_VAS・SUSPECT_USE_VAS のどちらにも無い変位形の関数)
```

JSON (`--json`) には `suspects_disp` と集計 (`disp_mach_fns` / `suspect_disp_fns` / `suspect_disp_keys` / `suspect_disp_and_store_fns` / `suspect_disp_and_use_fns` / `suspect_disp_only_fns`) を足す。`audit_lsf_disp.py` の単体実行は残す (判定の本体を共有)。

既存判定への影響 (`ld111_e2e.sh` 1/4・2b/4・2c/4。件数の単位は関数、分母は IR 内の全 7421 関数):

| IR | 既存 3 判定の出力 (統合前 `14150b46` の audit_lsf.py との比較) | SUSPECT_VAS | SUSPECT_USE_VAS | SUSPECT_MIXED_VAS | SUSPECT_DISP_VAS | DISP_ONLY |
|---|---|--:|--:|--:|---|--:|
| `boot_final.ll` | `--no-disp` は stdout が byte 一致。既定は既存 3 行と JSON 既存 13 キーが一致 | 8 | 49 | 120 | `41a670` | 0 |
| `boot_final3.ll` | 同上 | 8 | 49 | 118 | `41a670` | 0 |
| `boot_final.ll` + `fix_ld108.py` | (統合前との比較は無し。修復で IR が変わる) | 8 | 48 | — | なし | 0 |
| `boot_final.ll` + ldfix (`ldfix_img.py`、F3c 等を適用) | (同上) | 0 | 23 | 118 | `41a670` | **1** (`41a670`) |

- SUSPECT_VAS (store 形・両 IR で同一): `409c80 417b70 41a670 5c0270 66e080 7e5240 806740 c62780`。
- SUSPECT_USE_VAS (消費者形) の 49 関数は `boot_final.ll` / `boot_final3.ll` で同一: `4087a0 40fe90 40ffe0 41a670 41b8d0 41b970 447ee0 449550 44cf40 44f040 44f110 44f1d0 44f2c0 44f740 44fb40 4506e0 46b4d0 47ad70 4a27c0 5c44b0 6074b0 666a60 6905f0 6ca580 6ca6c0 75a180 7763d0 784ed0 786d50 787380 806740 8239d0 86a7c0 8c7710 c40420 db6480 dc27c0 ddd4d0 de4120 f3dd20 f552a0 101d180 1050f90 10626e0 10628d0 1062c50 1063090 12cb4f0 12f9730`。`fix_ld108.py` 適用後は `41a670` だけが消える (修復で `load [arg1+0]` が入り「argN の load が全滅」でなくなるため)。
- `work-m11` の `boot_final.ll` / `boot_final3.ll` は ldfix (F3c) の適用前の IR (`ldfix_img.py` を当てると SUSPECT_VAS が 8 → 0)。この段階では `41a670` は 3 判定すべてに入るが、**別の site** を見ている: 変位形は head 解除 (`41a6a3`)、SUSPECT_VAS は `41a6d6` の `store i64 %arg1` (D4 形脱落。REPORT_484 の TP で F3c が直す)、SUSPECT_USE_VAS は arg1 の load 全滅 (`fix_ld108.py` 適用後は消える)。
- **ldfix 適用後の IR (現行の修復経路) では、既存判定が拾わず変位形だけが `41a670` を拾う** (DISP_ONLY 1 件)。head 解除の誤り (`41a6a3`) は F3c で直らず、REPORT_509 冒頭のとおり件数ベースの SUSPECT 0 件でも残る。変位形はその残存を示す唯一の信号になる。変位形だけが拾う関数は、ldfix 適用前の IR 2 本では 0 件。

所要 (`boot_final.ll`、`audit_lsf.py` 単体、n=3): `--no-disp` 9.0–9.2 秒、既定 18.2–18.5 秒 (load 0.87–0.96)。変位形が機械語の CFG 不動点をもう 1 回解くため約 2 倍。

## 3. 残 SUSPECT 3 件の機械語突合

audit_lsf_disp の機械語側は `mov` の load 値だけを追い、`lea` と文字列転送 `movs` を追わない。3 件はいずれも機械語に `lea rsi,[argN+k]; movsq/movsd` があり、IR の `load (argN+k)` → store はそれを lift したもの。

| VA | IR の miss | 機械語 (逆アセンブル。`rbx`=arg1・`r13`=arg2 は `mov rbx,rcx` / `mov r13,rdx`) | 判定 |
|---|---|---|---|
| `6677a0` | `arg2+36` (i64 の store 1 本の出元) | `6677c9 lea rdi,[rbx+0x24]` / `6677cd lea rsi,[r13+0x24]` / `6677d1..6677d7 movsq ×4` / `6677d9 movsd`。[arg2+36 から 36 バイト] を [arg1+36] へ。IR は `load [arg2+36]` → `store [arg1+36]`、続く 44・52・60 (i64)・68 (i32) は `select i1 %4, i64 -8, i64 8` (%4 = DF = 0 で +8) 経由 | 誤検出 (列挙漏れ) |
| `d237e0` | `arg2+36` | `d239fc..d23a00`・`d23a11..d23a15`・`d23a26..d23a2a` の 3 組が `lea rdi,[arg1+K]; lea rsi,[arg2+0x24]; movsq ×2; movsd` (K = 0x278・0x50・0x3c。arg1・arg2 は `[rbp+0x20]`・`[rbp+0x28]` の home から読み直す)。IR は同じ `%127` (`arg2+36`) を 3 回 load し、`arg1+632`・`+80`・`+60` へ store (REPORT_735 §2b の「load 値は捨てられていない」と一致) | 誤検出 (列挙漏れ) |
| `de1da0` | `arg1+244` | `de221e lea rsi,[arg1+0xf4]` / `de2225 movsq` / `de2227 movsq` → `[g+0xc4]` へ 16 バイト (`de2213 lea rdi,[rax+0xc4]`、rax はグローバル経由で arg 由来でない)。IR は `%222 = arg1+244` を `load i64` → `store [g+196]`、続く 8 バイトは `select` 経由。IR 内の他の `arg1+244` は、`%113` (i32 の store 先) が `de1f67 mov [rcx+0xf4],eax` (書き込み)、`%222` の call 引数が `de216d lea rdx,[rax+0xf4]` に対応 | 誤検出 (列挙漏れ) |

IR 側は 3 件とも機械語どおり (wrong-value ではない)。`ir_off_stores` は `add %argN, c` → `inttoptr` → `load` の直結形だけを拾うため、各 `movs` 連鎖の先頭 1 本だけが c として見え、機械語側の disp 集合に無いと SUSPECT になっていた。

**別算法の突合 (`triage_ld111.py`)**: audit の CFG 不動点とは別に、関数の線形 disasm を 1 回なめて reg / frame slot を `argN+off` として持ち、`argN+c` を実効アドレスに持つ全メモリオペランド (`mov` 以外・`movs` の暗黙オペランドを含む) を列挙し、その値が非 frame メモリへ store されるかを見る。

| 対象 | 結果 | 根拠の命令 |
|---|---|---|
| `41a670` arg1+8 | **READ** (store されない = wrong-value) | `41a685 mov rcx,[rax+8]` (call 引数。head には書かれない) |
| `6677a0` arg2+36 | **LSF** (誤検出) | `6677d1 movsq` |
| `d237e0` arg2+36 | **LSF** (誤検出) | `d239fc` / `d23a11` / `d23a26` の `movsq` |
| `de1da0` arg1+244 | **LSF** (誤検出) | `de2225 movsq` ほか |

## 4. 検出信号の拡張と陰性対照

`audit_lsf_disp.transfer` に 2 つ足した (`--no-strmov` で #2316 時点の列挙に戻せる)。(1) `lea rD,[argN+k]` → 状態 `('argoff', n, k)`、そこからの `mov r,[rD+d]` は disp = k+d の load。(2) rep 無しの `movsq`/`movsd` (オペランドが `[rdi]`・`[rsi]` の MEM 2 個) → `rsi` が `argoff` なら (n, 幅, disp) を LSF site に追加し、`rsi`・`rdi` を幅ぶん進める (DF=0 は Win64 ABI の前提)。`rdi` が frame 宛 (`lea rdi,[rbp|rsp+..]`) なら store 先が alloca とみなして除く。

| IR | 列挙 | 機械語 LSF のある関数 | SUSPECT_DISP_VAS |
|---|---|--:|---|
| `boot_final.ll` | `--no-strmov` (#2316 時点) | 135 | `41a670 6677a0 d237e0 de1da0` |
| `boot_final.ll` | 既定 | 209 | `41a670` |
| `boot_final3.ll` | `--no-strmov` / 既定 | 135 / 209 | 上と同じ (4 件 / 1 件) |
| `boot_final.ll` + `fix_ld108.py` | `--no-strmov` / 既定 | — | `6677a0 d237e0 de1da0` / なし |

列挙の拡張で新たに判定対象になった 74 関数 (209 − 135) からの新規 SUSPECT は 0 件。

陰性対照 (`ld111_e2e.sh` 4/4。`--only 41a670,6677a0,d237e0,de1da0`。1 件ずつ壊して判定が動くことを確認):

| NC | 操作 | 期待 → 実測 (SUSPECT_DISP_VAS) |
|---|---|---|
| NC0 | 無改変 | `41a670` → `41a670` |
| NC1 | `--no-strmov` | 4 件 → `41a670 6677a0 d237e0 de1da0` (3 件の消去は movs 列挙による) |
| NC2 | 機械語 `6677d1..6677d9` の movs 5 命令を nop | `6677a0` が復活 → `41a670 6677a0` (列挙で「何でも消す」のではない) |
| NC3 | `6677a0` の IR の load 変位を 36 → 40 | `6677a0` が復活 → `41a670 6677a0` (movs 連鎖でも IR の誤った offset は検出する) |
| NC4 | `fix_ld108.py` で `41a670` を修復した IR | 検出なし → なし |
| NC5 | `41a670` の機械語の arg1 zero-disp load 2 site (`41a69c..41a6aa`・`41a6d3..41a6d6`) を nop | 検出なし → なし (IR だけでは判定しない) |

## 5. DEFECTS.md への反映

D20 行の「検出信号」欄を更新した (SUSPECT_DISP_VAS の定義・`41a670` だけを検出・旧 3 件は `movs` の列挙漏れによる誤検出)。測定値は本 REPORT だけに置き、DEFECTS 側は結論とリンクにした。

## 6. 検証範囲 / 範囲外 / 限界

- 範囲: 素材 `work-m11` の IR 2 本 (`boot_final.ll`・`boot_final3.ll`) と、`fix_ld108.py` 適用後の `boot_final.ll`。いずれも全 7421 関数。
- 範囲外: 本番の IR 生成経路 (`m11_gen_ir2.sh`) の出力への適用 (`ir_conditions.json` が素材に無く照合不能。`fix_ld108.py` の本番配線は #2402)。wasm の動的確認 (本 issue は検出信号のみ)。
- 限界: 変位形は (arg, 幅) ごとの disp の**集合**判定。機械語に同じ disp があれば、IR が別 site でその disp を取り違えても検出できない。`rep movs*`・SIMD 転送 (`movups` 等)・加算済みポインタ経由の load は列挙しない (現 IR では誤検出 0 件)。`lea` の追跡は 32 bit 版 (`lea eax,[..]`) を 64 bit 版と区別しない (影響は未測定。`ops[0].size == 8` の条件を足せば除ける)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `fix_ld108.py` と ldfix の両方を適用した IR での変位形 (0 件の見込み) は未測定 (本 REPORT は片方ずつ) | 本番 build の IR での最終確認が未了 | #2402 (LD-112) にコメントで提案 (子は起票しない) |
| 変位形の限界 (集合判定・`rep movs`・SIMD) | 他 IR では誤検出・見逃しの可能性 | 起票しない (現 IR で誤検出 0 件。REPORT_2316 §5 の `666a60` の行と同じく親 #2316 側で扱う) |

## 7. 再現・検証

```
bash tools/m11/ldfix/ld111_e2e.sh      # 前提: tools/m11/work に work-m11 を展開 (PE 不要)。出力は 1/4〜4/4 と 2b/4・2c/4
python3 tools/m11/ldfix/triage_ld111.py tools/m11/work/m11_image.bin 'tools/m11/work/boot*.drc.config.json' 6677a0:2:36
python3 tools/m11/ldfix/audit_lsf.py IR.ll IMAGE.bin 'CONFIG_GLOB' [--no-disp] [--no-strmov]
```

- `ld111_e2e.sh` の実測 (commit `c9a97944`、n=3): 全体 229–234 秒 (load average 1.00–1.05、並列数 1)。step 1 の audit_lsf 3 回分 (統合前・`--no-disp`・既定) は IR ごとに 36–38 秒。出力は 3 回とも (所要行を除き) 同一。
- `negctl_484.sh` (`audit_lsf.py` を呼ぶ既存の陰性対照) は、`run()` の `tail -2 | head -1` が出力行数に依存するため `--no-disp` を付けた。NC0〜NC4 の suspects (8 / 7 / 8 / 7 / 7 関数) は統合前の期待と同じ。
- `git status --porcelain=v1 -- tools/m11/ldfix docs/DEFECTS.md docs/DOC_MAP.md`: 本 PR の変更ファイルのみ。`find tools/m11/ldfix -type f -size +20M -not -path '*/work/*'` は空。
- REPORT の行数は `wc -l` で 250 行以内。
