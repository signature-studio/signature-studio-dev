# #509 (LD-9): ldfix F3c 門の拡張と LSF 脱落 8 関数 / 11 site の IR 修復

**判定: 部分達成**。store 形の脱落 8 関数 / 11 site に IR 修復を入れ、`audit_lsf.py` の store 形 SUSPECT は 12 → **0** (§3)。survey の ok 退行は 0。
ただし **SUSPECT 0 は「修復が正しい」の証明ではない**。`audit_lsf.py` は件数で数えるため、値の取り違えを検出しない。実際、次の 2 点は修復後も誤りが残る (機械語との突合は oc-reviewer の逆アセンブル確認による。§4.4・§7):
- **41a670 の 41a6a3 は未修復**。修復後 IR は head 解除経路で `store i64 %2, ptr @head` (`%2 = load [arg1+8]`) のままで、機械語 (41a69c〜41a6a3: `mov rax,[rbp+0x50]; mov rax,[rax]; mov [head],rax`) は `*arg1` を書く。head 解除経路を head=N, N.next=0x2222 で呼ぶと head=0 (期待 0x2222) という観測は本 REPORT 初版 §6 の記録による。§4.4 の動的確認 (O.next 更新経路、PASS) はこの経路を測っていない。
- **666a60 のループ内 store も誤り**。5 行の置換 (`%26`・`%15` 以降の N 基準) は機械語と一致するが、ループ内 `store i64 %29, ptr %36` はスロットアドレスを書いている。機械語 666b0c〜666b13 (`mov r8,[rbp+0x28]; mov r8,[r8]; mov [rcx+0x10], r8`) は `*arg1` (= N) を書く。666a60 は**部分修復・残存誤りあり**。
未達は (1) 消費者形 (666a60 型) の監査が残 30 関数 + 自動修復対象外 118 関数、(2) liftdiff での動的確認 (native 側に fl-win64 の PE が要る)、(3) 上記 41a670 / 666a60 の残存誤り。→ §6 の起票先 (#734〜#737、#510 追記) に列挙。PR は `Refs #509` (Closes しない)。
先行: #484 (`REPORT_484.md`)。base = `009e823`。

既知類型との関係 (`docs/DEFECTS.md`): **D4 (DEFECTS.md)** の再発 (store 形 + 今回は消費者形)。新規候補 1 件 (§7: 41a670 の 41a6a3 は load 脱落ではなく別 offset の SSA 値の再利用)。
`tools/icall/REPORT.md` §4 の D4 とは別体系。

素材: `fl-win64` は取得していない (依頼の `oc_artifacts` は toolchain-retdec / toolchain-emsdk / work-m11 / work-liftdiff)。PE は無く、#484 と同じ PE 無し shim (`ldmach_img.py`) で動かした。

## 1. 結論 (受入条件別)

| 受入条件 | 結果 |
|---|---|
| F3c 門の拡張 (G2 / G4 / G5 / base 追跡 / `BLK_RE`・`Fn.blocks()`) | **達成** (§2)。ldfix の全 pass を同一入力で旧版と突合: 出力が変わった関数は 26 / 7421 のみ、関数外テキストは byte 一致 |
| 666a60 の 666a9b (消費者が address base) を対象に含める | **達成** (対象に含めた)。`audit_lsf.py` に消費者形を追加 (§2.3)、ldfix に F3c-use を追加 (§2.2)。666a60 は 5 行を `[arg1]` の load 値へ置換。ただし**ループ内 store は残存誤りあり** (§1 冒頭・§6) |
| 修復後 `audit_lsf.py` の SUSPECT 0 (独立算法) / ok→非 ok の退行 0 | **一部**。store 形の件数は **0** (修復前 8 関数 / 12 site、#484 の post は 8 / 11)。ただし件数 0 は 41a670 の 41a6a3 (未修復) と 666a60 のループ内 store (誤り残存) を検出しない (§1 冒頭)。消費者形 (pure) は 52 → **30** 関数、mixed は 124 → 118 関数が残る (自動修復の対象外、§6)。survey の ok 退行は **0** (§4.2) |
| 8 関数の動的到達 (survey) と liftdiff での脱落の動的確認 | **一部**。動的到達は計装で実測 (§4.3: 8 関数中 survey で実行されるのは 41a670 と 409c80 の 2 関数)。liftdiff は PE が無く未実施。代わりに修復前後の wasm を直接呼ぶ動的確認 5 件を実施 (§4.4: 修復前 5/5 FAIL → 修復後 5/5 PASS) |
| ネガコン (修復を外すと SUSPECT が戻る) | **達成** (§4.5) |
| audit_lsf.py の docstring を実装に合わせる | **達成** (CFG 上の不動点データフローと、消費者形の定義を記載) |

## 2. 実装 (`tools/m11/ldfix/`)

### 2.1 F3c の門の拡張 (`ldfix.py` `fix_f3c_fn` / `f3c_track`)

#484 の原因 3 種 (G2 / G4 / G5) に対応:

| 門 (#484 §2.2) | 旧 | 新 |
|---|---|---|
| G1 | ブロック内の zero-disp load が恰好 1 本 | 不要。機械語を命令列の基本ブロックごとに記号実行し、`mov rD,[rB]` (rB は argN) の値が `mov [m],rD` で同幅 store される site を全部数える |
| G2 base → argN | load 自身を含めて解決 (自己上書き `mov rcx,[rcx]` で見失う) / rcx,rdx,r8,r9 のみ | load **直前**の状態で解決。引数 reg は「entry から到達するどの経路でも書かれていない」ブロックでだけ argN。entry の直線部で 1 回だけ代入された callee-saved reg (`mov rbx,rcx`) と 1 回だけ書かれる frame home (`mov [rbp+d],rcx`) を全ブロックへ持ち込む (reg コピー・frame slot 経由) |
| G4 順序 | 機械語に rB の生 store があれば全部見送り | argN **自身**を非 frame 宛に store する数 (`ptr`) で判定。load 後の値 (node.next) の store は数えない |
| G5 | 同一 IR ブロック内に argN 値 store | 関数単位の収支: `ptr[n,w]` = 0 なら、関数内の `store iW %argN` (trunc/zext 経由・alloca 宛除外) を全て `load` 経由に置換。`.thread` による IR ブロック複製・sink と無関係 |

従来の block-local 門は `fix_f3c_block` として**挙動を変えずに残した** (旧 16 関数の出力は byte 一致)。新旧の門は同じ関数で順に走る (`fix_f3c`)。
新門だけで旧 16 関数を再検出できたのは **1 / 16** (409c80)。残り 15 関数は `store i64 %arg1, ptr %rax.0.reg2mem` 型 (戻り値 reg の store) で LSF の形ではない — 例 5c1030 は機械語 `mov rax,rcx` (ポインタのコピー) と `mov rbx,[rcx]; call [rbx+0x18]` (D15 の脱落 call) で、旧 F3c の「修復」は戻り値を `[arg1]` に変える。**正しさ未検証** (§6)。

`BLK_RE` は `dec_label_pc_<VA>.thread:` / `.dec_label_pc_*_crit_edge:` を VA 付きブロックとして認識、`Fn.blocks()` は `; preds = ...` 付きの一般ラベルも新ブロックにする。**全 pass の点検**: 同じ修復前 IR に旧版/新版を適用し、`f3c` 以外の report キーは `f3b_base_unresolved` 57 → 56 のみ (出力に影響なし)、関数本体は 26 関数以外 byte 一致、関数外テキスト一致 (§4.1)。F1 / F1v / F2 / F3a / F3b の修復関数数 (902 / 4 / 30 / 3 / 5) は不変。

### 2.2 消費者形 (`fix_f3c_use`)

load した値の消費者が store でない形 (cmp・call 引数・address base・演算)。条件 (全部): (a) 機械語の argN を base にした zero-disp load が全て 64bit で最初の 1 本が entry ブロックにある /
(b) argN の生の使用 (引数 reg を読む call・ptr store 等。call は呼び先の IR 引数個数ぶんの引数 reg) が全て最初の load より前 / (c) IR に argN からの zero-offset load が 1 本も無い / (d) argN が i64 引数。
満たすとき IR の `%argN` の使用行のうち、生の使用の数だけ先頭側を残し、残りを `%ldfxu = load i64, [%argN]` の値に置換する (load は置換する最初の行の直前、生の使用が無ければ entry の alloca 群の直後)。

結果: 19 関数を修復 (417b70 / 666a60 と、監査対象外だった 17 関数 `1062c50 1063090 12cb4f0 12f9730 4087a0 40ffe0 447ee0 44f110 44f1d0 44f2c0 44f740 6074b0 7763d0 8239d0 86a7c0 8c7710 f3dd20`)。置換行 55。
17 関数は機械語と目視で突合し、全て `mov rD,[rB]` の rD を IR が `%argN` で代用していた (例 1063090: `mov rax,[rcx]; test rax,rax` が `icmp eq %arg1, 0`)。

### 2.3 `audit_lsf.py` の拡張 (独立算法)

store 形は #484 と同じ。消費者形を追加: `M_deref[n]` (機械語: argN を base にした zero-disp load の数)、`M_raw[n]` (load 以外の読み。reg→reg コピー・frame spill は数えない)、
`IR_use[n]` (`%argN` を参照する IR 行数) / `IR_ld[n]` (argN からの load 行数)。`SUSPECT_USE ⇔ M_deref ≥ 1 ∧ IR_ld = 0 ∧ IR_use > M_raw ∧ 最初の deref より後に生の使用なし`、後ろにも生の使用があるものは `SUSPECT_MIXED` (件数のみ)。
機械語側は CFG の不動点データフロー (join = 一致値のみ) で、ldfix の「到達閉包 + 静的 def」とは別実装。ただし (c) の条件は両者に共通する (§5)。
docstring は「straight-line」から実装に合わせて書き直した。

## 3. 結果 (実測、`audit_lsf.py` は 7421 関数)

| 入力 | store 形 SUSPECT (関数 / site) | 消費者形 pure (関数) | mixed (関数) |
|---|--:|--:|--:|
| 修復前 IR (`m11_gen_ir2.sh` 再生成) | 8 / 12 | 52 | 124 |
| 旧 ldfix 出力 (`009e823`) | 8 / 11 | 49 | 120 |
| **新 ldfix 出力** | **0 / 0** | **30** | **118** |

store 形の 11 site: 5c0270 ×2、41a670 ×1、66e080 ×3、7e5240 ×1、806740 ×1、c62780 ×1、409c80 ×1 (4B path)、417b70 ×1 (arg4 = count の pointer。load が全滅していたため消費者形で 14 行置換)。
ただし 41a670 の 1 site は「IR 修復済み」でなく値の取り違えが残る (§1 冒頭・§7)。666a60 は store 形ではなく消費者形で修復しており、そのループ内 store に誤りがある (§1 冒頭)。
`fix_f3c_fn` の store 置換は 10 行 (7 関数)、`fix_f3c_use` は 19 関数。機械語 LSF site 総数は 90 のまま (機械語は不変)。

`f3c_no_store` (block-local 門で「IR ブロックに `store %argN` が無い」として見送った site): 旧 150 → 新 158 (`BLK_RE` の分割でブロックが増えただけ)、関数数 124。
この 124 関数のうち、修復前は消費者形 pure 10 + mixed 18 の 28 関数が脱落形 — つまり `f3c_no_store` の約 2 割は store 以外の消費者に流れる D4 だった。修復後は pure 4 + mixed 18。

残る pure 30 関数 (33 引数) の理由 (`use_residual_509.py`): 最初の deref が entry ブロック外 13 / ptr 型引数 10 / 前記 2 つ 4 / 前記 + 32bit deref 2 / ldfix の記号実行が deref を見ない 3 / 門に掛からない 1 (5c44b0)。

## 4. 検証

### 4.1 旧版/新版の突合 (`ldfix_509_e2e.sh` 2/7, 4/7)
- 同じ修復前 IR に旧版 (`009e823`) と新版を適用: 本体が異なる関数 **26 / 7421**、関数外テキスト一致、F3c 関数 16 → 41 (旧 16 を全て含む)。
- 既に ldfix 済みの `work/boot_final.ll` へ `--passes f3c` で F3c だけ重ねると 26 関数が変わり、26/26 が新版出力と (alloca 行を除いて) 同一。→ 生成物 IR を作り直さずに同じ修復を適用できる。

### 4.2 survey 前後 (wasm 再ビルド、942 unit)
前後とも `ok 852 / oob 26 / halt0 17 / miss 46 / noproc 1` (trap 43)。unit ごとの遷移は全て対角、**ok 退行 0**。
wasm hash と frame の offset を除いて unit 記録 (kind・msg・frame・stub 呼出・va_mb) を比べても差 **0** unit。
survey に差が出ない理由は §4.3: 修復した関数の大半は survey で実行されない。

### 4.3 動的到達 (`reach_509.sh`: 関数入口へ `m11_fnhit` を挿入した wasm で 942 unit を実行)

| 関数 | 実行された unit 数 | 入口通過 |
|---|--:|--:|
| 41a670 | 17 | 17 |
| 409c80 | 44 | 79100 |
| 40ffe0 / 447ee0 | 各 1 (unit 895 / 17) | 1 |
| 5c0270 / 417b70 | 0 (`m11_ov.c` が C で上書き。IR 版は実行されない) | 0 |
| 66e080 / 7e5240 / 806740 / c62780 / 666a60 ほか 19 関数 | 0 | 0 |

(判定基準: 関数の入口を通った回数。unit 0..941 を `_m11_call_unit` で 1 本ずつ実行、`InitUnits` 抑止。boot 後の通常実行・GUI/audio 経路は範囲外。)

### 4.4 動的確認 (`dyn_509.mjs`: 修復前/後の wasm を直接呼び、機械語から決めた期待値と比較)

| 関数 | 機械語から決めた期待 | 修復前 | 修復後 |
|---|---|---|---|
| c62780 | `array[idx*16+8] = *arg3` (0x1122334455667788) | 0x11e00100 (arg3 のポインタ) FAIL | PASS |
| 7e5240 | `dst[1] = src[0]` (0xdeadbeef) | 0x11e00300 (arg3 の下位 32bit) FAIL | PASS |
| 409c80 (len=5, 4B path のみ) | 先頭 4B = 0x13121110 | 0x13121100 FAIL | PASS |
| 41a670 | unlink で `O.next = N.next` (0x1111) | 0x11e00600 (N のポインタ) FAIL | PASS |
| 1063090 (消費者形) | `**pp` 相当の戻り値 0xabcd | 0x0 FAIL | PASS |

liftdiff の既存判定 (`results/m11_closure_verdicts.tsv`) では 5c0270 / 41a670 は `match`、806740 / c62780 / 417b70 は `unexec` (native 側が NULL deref)。
patterns が零埋めのため脱落が見えなかったと読めるが、liftdiff を再実行していないので推定。

### 4.5 ネガティブコントロール (`ldfix_509_e2e.sh` 5/7)

| 壊し方 | 期待 | 実測 |
|---|---|---|
| 修復を外す (旧 ldfix の出力) | store 形 SUSPECT 8 関数 / 11 site | 8 関数 / 11 site |
| 新出力の 806740 の修復 store を `%arg3` に戻す | 806740 が戻る | 1 関数 / 1 site (806740) |
| 新出力の 1063090 の置換を戻す | 消費者形 pure に 1063090 が戻る | 30 → 31 関数 (1063090 が戻る) |
| 修復前 wasm で動的確認 | 5/5 FAIL | 5/5 FAIL (§4.4) |

### 4.6 再現・所要

検証起点 commit = `5f28f67` (以降の commit は REPORT と `results/` のみ)。コミット済み HEAD で `bash tools/m11/ldfix/ldfix_509_e2e.sh` (`M11_WORK` = work-m11 展開先、`PY` = capstone + pefile 入り python):
n=3 の所要 **146 / 147 / 147 s** (並列数 1、4 コア)、終了時 load average (1 分値) 1.14 / 1.20 / 1.39、3 回とも標準出力が byte 一致。内訳: 修復前 IR 再生成 + ldfix 2 版 + 監査 3 本 + ネガコン 3 本 + wasm 2 回ビルド + survey 2 回 + 計装ビルド + 動的確認。
#484 の `audit_lsf_e2e.sh` も同 HEAD で再実行して完走 (95.2 s)。PE 版 `ldfix_report.json` とのキー不一致は `f3c*` 以外で `f3b_base_unresolved` 57 → 56 の 1 件のみ (§2.1。修復関数リストと出力 IR には影響なし)。

### 4.7 e2e 修正 (#4039・a7d3646be) の実測と IR 条件

測定 commit: `a7d3646be` (`ldfix_509_e2e.sh` の prev 依存と修復後 wasm の build 条件を揃えた commit)。
`git diff --stat a7d3646be HEAD -- tools/m11` は 20 files / +1216 −17。大半は main 取り込みで入った別 issue の REPORT・補助 script (`REPORT_1325.md`・`REPORT_3195.md`・`residual_3195.py`・`u3_check_4040.py` ほか)。
e2e の本体 `tools/m11/ldfix/ldfix_509_e2e.sh` は `a7d3646be → HEAD` で 13 行追加・12 行削除 (`|| { ...; FAIL=1; }` の追加、`FAIL=0` の位置の移動、コメント追加)。値を生成する経路 (`ldfix.py`・`ldmach*.py`・`ldframe.py`・`ldfix_img.py`・`audit_lsf.py`・`reach_509.sh`・`dyn_509.mjs`・`m11_build.sh`・`m11_cond.py`・`trap_triage/survey_*`・`tools/shim`・`tools/shared`) は `a7d3646be → HEAD` で差分 0。
ただし上の実測 (rc=0) は FAIL 伝播が無い `a7d3646be` の版のもの。`HEAD` の rc 挙動は未実測。

| 項目 | 結果 |
|---|---|
| e2e `ldfix_509_e2e.sh` (`PREV_REF=HEAD`、測定 commit `a7d3646be`) | rc=0、4 分 5 秒、load (1 分値) 終了時 1.18 (FAIL 伝播前の版) |
| e2e (`PREV_REF=009e823`、既定、測定 commit `a7d3646be`) | rc=0、3 分 38 秒、load 終了時 1.18 (FAIL 伝播前の版) |
| 直接呼び出し 5 関数 (c62780・7e5240・409c80・41a670・1063090) | 修復前 wasm FAIL 5/5、修復後 wasm PASS 5/5 (`DYN_SUMMARY after_fail=0/5`) |
| 旧版 009e823 の ldfix 出力 (`NC:prev`) | store 形 SUSPECT 8 関数 / 11 site (§4.5 と一致) |
| 修復後 wasm の survey | ok 871 → 873、ok 退行 0 |

- 上の実測は測定 commit `a7d3646be` のもの。本 REPORT の文言修正 (次行の注) の後の HEAD では e2e を再実行していない。
- ネガコン 2 件 (`nc_store`・`nc_use`) は `AssertionError` で止まり、SUSPECT 値を取れていなかった (a7d3646be の実測)。ネガコンの正規表現が現在の IR と合わない (ネガコンの正規表現の修正は #3194 の残件)。
- **HEAD の e2e は step 5 の assert で rc≠0 になる**: step 5 の IR 作成 heredoc は `|| { ...; FAIL=1; }` で包まれており、上の AssertionError がそのまま `FAIL=1` になり、step 7 の前で rc≠0 として終わる。これは HEAD のコードからの判定で、HEAD での実行は未実測。rc≠0 は FAIL を rc に反映するための意図どおりの結果。
- 修復前 wasm の IR 条件: `M11_LDFIX=0` で生成 (`ldfix=disabled`)。`ld108`・`ld115`・`r8b`・`src412770` は適用していない (`m11_gen_ir2.sh` の ldfix 分岐の外側)。build は `M11_ALLOW_LDFIX_DISABLED=1` の opt-in のみ。
- 修復後 wasm の IR 条件: 修復前 IR に `ldfix.py --pe` のみを適用 (`ldfix=applied`)。`ld108`・`ld115`・`r8b`・`src412770` は未適用 (`ld108=disabled`・`r8b=disabled`・`ld115=disabled` を記録し、build は `M11_ALLOW_LD108_DISABLED=1 M11_ALLOW_R8B_DISABLED=1 M11_ALLOW_LD115_DISABLED=1` で opt-in)。通常パイプラインの wasm (`m11_gen_ir2.sh` の全 fix 適用) とは別物で、この 2 つの wasm の比較は `ldfix` の寄与だけを測るものではない (ld108・ld115・r8b・src412770 の寄与を含まない)。
- `FL_WIN64_DIR="$(dirname "$(dirname "$PE_QS")")"` は `PE_QS` が `extracted/` 配下の場合のみ正しい。

## 5. 検証範囲 / 範囲外
- 範囲: `work-m11` 時点 (2026-10-10 生成) の `boot_final.ll` / `boot_final3.ll` 7421 関数。PE 無し shim (`ldmach_img.py` に `cover()` を追加し、RetDec config の区間が IR ラベルより短い関数を最大ラベルから最初の ret まで延長)。
- 消費者形の監査と修復は (c) 「IR に argN からの load が 1 本も無い」を共有するので、load が一部だけ残った関数は両方とも見ない。独立なのは機械語側の追跡法と IR 側の数え方。
- `m11_gen_ir2.sh` を PE 付きで再実行して生成物 IR を作り直す手順は未実施 (#351)。work の `boot_final.ll` は `--passes f3c` の重ねで検証した。
- 消費者形の修復は「最初の deref の値を以降の全使用に使う」近似 (deref 間にその領域への store があっても再読込しない)。417b70 の arg4 のように deref が 1 本の関数では厳密。複数 deref の関数は 666a60 (2 本目はループ内で IR が別値) 等。
- 動的確認は 5 関数のみ。66e080 (xmm 引数)・806740・417b70・5c0270 (C 上書き)・666a60 は未確認。liftdiff 未実施。
- 409c80 の動的確認は 4B path (len=5) のみ。8B path (409cac 以降) は未確認。
- `audit_lsf_e2e.sh` は `f3c*` キーを除外して旧版と比べるため、F3c 系の出力は等価性検査の対象外。F3c 系の差分は §4.1 の旧版/新版突合 (本体 26 関数) でだけ見ている。

## 6. 未解決 (起票依頼)

起票先は PM が採番した issue 番号で示す (#734 = LD-12、#735 = LD-13、#736 = LD-14、#737 = LD-15。消費者形 mixed は既存の #510)。実装 agent は issue を起票・採番しない (WORKFLOW §2)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 消費者形 pure の残 30 関数 (33 引数、§3 の内訳)。ptr 型引数 (型変換が要る) と、最初の deref が entry 外 (IR ブロックの支配関係が要る) | 脱落形のまま (survey で実行されるかは未測定) | #734 (LD-12。親 #509 の子)。`reach_509.sh` に VA を渡して到達を測る |
| 消費者形 mixed 118 関数: argN をポインタとしても deref した値としても使う (例 408540: `mov rdx,[rcx]` の rdx を IR が `%arg1` で代用し、`[rcx-8]` の rcx も `%arg1`) | IR のどの使用が値側かは reg ↔ IR 値の対応 (SSA 対応) が要る | #510 (SSA 対応 or 動的差分) に追記 (PM 判断) |
| 41a670 の 41a6a3: `mov rax,[rax]` (rax = arg1 の home) が、直前の `mov rcx,[rax+8]` の SSA 値 (`%2`) に化けている (§7)。head 解除経路で head=N, N.next=0x2222 で呼ぶと head=0 (期待 0x2222)。 | 41a670 は修復後も 1 site が誤り。survey で 17 unit が通るが結果は不変 | #735 (LD-13。新規類型候補。DEFECTS.md 行案は §7) |
| 666a60 のループ内 store (IR `store i64 %29`) が 41a670 と同型の誤り (機械語 666b0c〜666b13 との突合は oc-reviewer の逆アセンブル確認による、§1) | 修復後も 1 site が誤り | #735 (LD-13。41a670 と同型として 1 件にまとめた) |
| 旧 F3c (block-local) の 16 関数のうち 15 は LSF の形ではなく (§2.1)、「修復」の正しさが未検証 | 戻り値が `[arg1]` に変わっている可能性 (survey には差が出ていない) | #736 (LD-14。`fix_f3c_block` の門の再点検。動的確認が要る) |
| liftdiff での脱落の動的確認 (native 側に PE が要る)。66e080・806740・666a60 の動的確認 | 受入条件 4 の後半が未達 | #737 (LD-15。動的確認の再実行時に `oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff` + numpy を足す) |
| 修復した 26 関数のうち survey で実行されるのは 4 関数。残り 22 関数 (5c0270 / 417b70 は C 上書き) の効果は survey では測れない | 修復の波及先 (trap/halt0 の減少) は不明 | #130 (M11-N2)。`ldfix_509_e2e.sh` の IR を `m11_gen_ir2.sh` (PE 付き) の出力へ反映する運用は #351 |
| `f3c_no_store` 124 関数のうち pure 4 + mixed 18 が残る | 上記と同じ | 上記 pure / mixed のチケットに含める |

## 7. DEFECTS.md 行案 (編集は PM 判断)

- **D4 (DEFECTS.md) の観測例に追記**: 「消費者形: `1063090` / `4087a0` / `40ffe0` / `44f110` / `6074b0` / `8239d0` / `86a7c0` / `8c7710` / `666a60` ほか: `mov rD,[rB]` の rD を cmp・call 引数・address base に使う形で、IR が load を落として `%argN` (ポインタ自身) を使う。検出信号: `audit_lsf.py` の SUSPECT_USE (機械語の argN deref ≥ 1 かつ IR に argN からの load が無く、`%argN` の使用行が機械語の生の使用より多い)。修復: `ldfix.py` `fix_f3c_use`」。
- **新規候補 (wrong-value reuse)**: 「`41a670` 41a6a3: `mov rax,[rax]` が直前の別 offset の load (`mov rcx,[rax+8]`) の SSA 値に化ける。症状: store される値が node.next でなく node.child。根本原因: 不明 (RetDec の値番号付けか)。観測: wasm 直接呼びで head=0 (期待 0x2222)。検出信号: 未定 (機械語の値 ld(n,w) の store に対し、IR の store 値が argN からの load でない)。修復: 未実装」。

## 8. 成果物 (`tools/m11/ldfix/`)

| パス | 役割 |
|---|---|
| `ldfix.py` | `fix_f3c` = `fix_f3c_block` (従来) + `fix_f3c_use` + `fix_f3c_fn`、`--passes`、`BLK_RE` / `Fn.blocks()` |
| `ldmach_img.py` | `ImageMachine.cover()` (区間延長) |
| `audit_lsf.py` | 消費者形 (SUSPECT_USE / SUSPECT_MIXED) を追加、docstring を実装に合わせた |
| `ldfix_509_e2e.sh` | 1 コマンド再現 (§4 の全部) |
| `reach_509.sh` / `reach_survey.mjs` | 動的到達 (関数入口の計装) |
| `dyn_509.mjs` | 修復前後の wasm を直接呼ぶ動的確認 |
| `use_residual_509.py` | 消費者形の残件を門ごとに分類 |
| `results/audit_509_pre.json` / `audit_509_post.json` / `reach_509.json` | 修復前 / 新 ldfix 出力の監査詳細、動的到達 (unit ごと) |
