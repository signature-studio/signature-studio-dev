# #484 (LD-8): ldfix が 5c0270 の D4 脱落を検出できなかった理由と、同型残存の全数調査

**判定: 受入条件 1・2 達成、3 は「一覧化 + 検出器 + ネガコン」まで達成・「起票」は PM 依頼 (§7)**。
先行 PR #481 (`dd9ba2c`, #474) の `tools/m11/trap_triage/REPORT_474.md` §6 の未解決
「`5c0270` の D4 脱落が `boot_final3.ll` に残っていた (ldfix の検出漏れ全数)」への回答。base = #481 の `dd9ba2c` (この上に積んだ stacked PR。マージ順 #414 → #444 → #481 → 本 PR)。検証起点 commit は §5。

既知類型との関係 (`docs/DEFECTS.md`): **D4 (DEFECTS.md)** の再発 (disp=0 の 1 段 deref 脱落)。新規類型なし。
ただし D4 の store 形に ldfix の**検出漏れ 3 種**があった (§2)。`tools/icall/REPORT.md` §4 の D7 とは別体系 (参照時は併記)。

素材: `fl-win64` を取得していないため **PE (`block00031_PE.bin`) は無い**。ldfix / 機械語突合は
`work/m11_image.bin` (.text を敷いた生イメージ) と `work/boot*.drc.config.json` (RetDec の関数区間) で動かす
shim (`ldmach_img.py`) に置換した。同値性は §4。

## 1. 結論 (実測)

| 受入条件 | 結果 |
|---|---|
| ldfix の検出条件と 5c0270 の IR 形の差を実測で特定 | **達成** (§2)。`fix_f3c` の門 G1〜G5 を 5c0270 の 2 site で評価: 両 site とも **G2 (base→argN 解決) と G4 (rB の store 無し) で落ち**、site B はさらに G5 (同一 IR ブロック内の store) でも落ちる |
| 同型の関数を `boot_final3.ll` 全数で列挙 (独立再計算付き) | **達成** (§3)。`audit_lsf.py` (ldfix と別算法) が **8 関数 / 11 site** を列挙 (7421 関数中)。8 関数を機械語 site と IR 行で目視確認し 8/8 が真の脱落 (409c80 は ldfix `REPORT.md` §1 の既知残存「4B/2B path」と一致) |
| 検出を拡張するか残存を一覧化して起票 (ネガコン必須) | **一覧化 + 検出器 + ネガコン 4 本 = 達成**。ldfix.py 本体は**無改変** (survey 結果を動かさないため)。起票は §7 を PM に依頼 |

- ldfix は `boot_final3.ll` に**適用済み**だった (`ldfx` マーカー 3335 行。PE 版 `work/ldfix_report.json` は F3c 16 関数)。5c0270 は F3c の対象形だが門で落ちた。
- 8 関数 / 11 site の脱落原因は 3 種 (§3 表)。(a) load の base が rcx/rdx/r8/r9 でない: 5 関数・7 site。(b) `mov rcx,[rcx]` の自己上書き: 2 関数・3 site (5c0270, 41a670)。(c) IR と機械語のブロック不一致: 409c80 の 4B path 1 site (5c0270 site B も (c) だが (b) に計上済み)。7 + 3 + 1 = 11。

## 2. ldfix が 5c0270 を検出できなかった理由

### 2.1 IR 形と機械語 (入力 = `m11_gen_ir2.sh` で再生成した修復前 IR。`boot_final3.ll` の 5c0270 と同形)

| site | 機械語 (逆アセンブル: `m11_image.bin`) | 正しい IR | 実際の IR (`boot_final3.ll`) |
|---|---|---|---|
| A (head 一致) | `5c02f7 mov rcx,[rbp+0x88]` (= node = arg2) → `5c02fe mov rcx,[rcx]` → `5c0301 mov [rax+8],rcx` | `store (load [arg2]), [self+8]` | `store i64 %arg2, ptr %13` (`dec_label_pc_5c0332.thread1`) |
| B (前任走査後) | `5c0325 mov rcx,[rbp+0x88]` → `5c032c mov rcx,[rcx]` → `5c032f mov [rax],rcx` | `store (load [arg2]), [prev]` | `store i64 %arg2, ptr %18` (`dec_label_pc_5c0332`) |

5c0270 は `-O0` 系 (frame あり・引数を `[rbp+0x80]`/`[rbp+0x88]` に退避)。IR には `load ... %arg2` が 0 件、`store i64 %arg2` が 2 件。

### 2.2 `fix_f3c` の門の実測 (`f3c_gate_probe.py`, `fix_f3c` と同じ補助関数・同じ条件式を評価するだけで IR は書き換えない)

| 門 | 内容 (ldfix.py) | site A (5c02fe) | site B (5c032c) |
|---|---|---|---|
| G1 | ブロック内の zero-disp load (base ∈ rcx/rdx/r8/r9) が恰好 1 本 | PASS (1) | PASS (1) |
| G2 | `base_resolves_to_arg(.., upto=load 自身を含む)` が argN を返す | **FAIL** (None。load 直前までなら 2) | **FAIL** (None。同上) |
| G3 | IR ブロック内に argN からの既存 load 無し | PASS | PASS |
| G4 | 機械語に rB の生 store 無し | **FAIL** (`5c0301 mov [rax+8],rcx`) | **FAIL** (`5c032f mov [rax],rcx`) |
| G5 | 同一 IR ブロック内に argN 値 store あり | PASS (※) | **FAIL** (0 件) |

原因 3 種:
1. **G2: `mov rcx,[rcx]` の自己上書き** — `idx = mins.index(insL) + 1` で load 命令自身まで走査するため、load の dest (= rcx) が base と同じだと `cur='unk'` になり argN を見失う (`mov edi,[rcx]` など dest ≠ base の 4123c0 型は通る)。
2. **G4: 順序を見ない** — 「rB を store する命令が機械語にある → ポインタ store は正当」と判定するが、5c0301/5c032f の rcx は load **後**の値 (= `node.next`) で、ポインタ store ではない。
3. **G5: IR と機械語のブロック対応の崩れ** — IR 側は 5c0332 を `.thread`/`.thread1` に複製し、fallthrough の命令 (5c0321〜5c032f) を 5c0332 ブロックへ sink している。site B の store は機械語ブロック 5c0311 ではなく IR ブロック 5c0332 にある。
   加えて `BLK_RE` は `dec_label_pc_5c0332.thread:` のような**サフィックス付きラベルを認識せず**直前のブロックに併合する (5c0270 の IR ラベル 11 個中 2 個)。site A の G5 が PASS なのは `.thread1` の store が 5c02dc に併合されたためで偶然。
- ほかの 5 関数 (417b70 / 66e080 / 7e5240 / 806740 / c62780) は **G1 の前提**で落ちる: load の base が `rax`/`rbx`/`rsi`/`rdi` (引数のコピーや `[rbp+0xc8]` 経由) で、`ARGREG_ARG` (rcx/rdx/r8/r9) に入らない。

## 3. 同型残存の全数調査 (`audit_lsf.py`, 独立再計算)

**形 (LSF = load→store 転送)**: 機械語 `mov rD,[rB]` (disp 0, rB は argN に解決) の値が rD を壊さずそのまま `mov [m],rD` される。脱落形は IR が load を落とし `store iW %argN` (ポインタ自身) を書く。
**算法** (`fix_f3c` のブロック単位対応を使わない): 機械語は関数ごとに CFG 上の前向きデータフロー (reg / frame slot → `arg n` | `ld n w`、join は一致値のみ残す)、IR は `store iW %argN` (alloca 宛除外、trunc/zext 経由含む) を数え、
`SUSPECT ⇔ M_lsf[n,w] ≥ 1 かつ IR_store[n,w] > M_ptr[n,w]` (M_ptr = 機械語の正当なポインタ store 数、frame 宛除外)。
単位: 関数 (`define @function_*` 7421 本) と site (機械語の store 命令)。

| 入力 | 関数 | 機械語 LSF site (argN 解決) | SUSPECT 関数 | SUSPECT site |
|---|--:|--:|--:|--:|
| 修復前 IR (`m11_gen_ir2.sh` 再生成) | 7421 | 90 | 8 | 12 |
| `boot_final3.ll` (ldfix 適用後) | 7421 | 90 | **8** | **11** |

修復前→後で減ったのは 409c80 の 8B path 1 site のみ (F3c が修復。ldfix `REPORT.md` §1 の記述と一致)。

| 関数 | site (機械語) | IR 脱落行 | 原因 (§2) | 静的 caller (IR の `call @function_X(` 行数) | 確認 |
|---|---|---|---|--:|---|
| `5c0270` | 5c0301, 5c032f | `store i64 %arg2` ×2 | (b)(c) | 2 | TP (#481 で m11_ov.c に転記済み。IR は未修復) |
| `41a670` | 41a6d6 (+ 41a6a3 は IR 正常) | `store i64 %arg1` ×1 | (b) | 2 | TP (5c0270 と同じ単方向リスト unlink。global head 版) |
| `66e080` | 66e1b2, 66e209, 66e210 | `store i64 %arg1` ×3 | (a) | 3 | TP (`movsd [rbx],xmm0` の直後に `mov rax,[rbx]; mov [rbx+8],rax` → IR は double でなく `arg1` を書く) |
| `7e5240` | 7e526a | `store i32 %15` (= trunc %arg3) | (a) | 2 | TP (`mov eax,[rsi]; mov [rdx+4],eax`) |
| `806740` | 806792 | `store i64 %arg3` | (a) | 3 | TP (`mov rax,[rdi]; mov [rbx+0x6bc],rax`, rdi = r8) |
| `c62780` | c627ae | `store i64 %arg3` | (a) | 2 | TP (`mov rcx,[rsi]; mov [rax+rdx*8+8],rcx`) |
| `417b70` | 417bb4 | `store i64 %arg4` + `icmp slt .., %arg4` | (a) | 7 | TP。値は frame slot `[rbp+0x60]` 経由で多数の消費者に流れる (自動修復は consumer の伝播が要る) |
| `409c80` | 409cc0 (4B path) | `store i32 %32` (= trunc %arg1) | (c) | 137 | TP (ldfix `REPORT.md` §1 の既知残存「4B/2B path」) |

「静的 caller」は `grep -c "call [^@]*@function_<VA>(" boot_final3.ll` (関数ごとの IR 行数。動的な到達は未測定)。

## 4. PE 無し shim の同値性 (`ldmach_img.py`, `ldfix_img.py`)

`ldfix.py` を無改変のまま `Machine` だけ差し替えて、`m11_gen_ir2.sh` で再生成した修復前 IR に適用し、PE 版の `work/ldfix_report.json` と比較:
**キー 32/32 が一致 (不一致 0)** — 修復関数 VA リスト (F1 902 / F1v 4 / F2 30 / F3a 3 / F3b 5 / F3c 16) と全スキップ計数を含む。
出力 IR と `work/boot_final.ll` (alloca 縮退済み) の差は 108 行 (`<`/`>` 行の数)、うち `%… = alloca` 宣言でない行は 0 (別段 `tools/m11/alloca` の差)。

区間表の差 (PE の `.pdata` ではなく RetDec config): `audit_lsf.py` の集計で **534 / 7421 関数が config の endAddr より先に IR ラベルを持つ**、15 関数は区間 ≤ 2 B。
`audit_lsf.py` は entry + IR ラベルを root とする再帰降下で補った (IR ラベルは全関数で被覆済)。降下版と config 区間版で SUSPECT は同一 (8 関数)。

## 5. 検証

検証起点 commit = `e8ac5ab` (スクリプト一式。以降の commit は docs と `results/` のみ)。コミット済み HEAD で `bash tools/m11/ldfix/audit_lsf_e2e.sh` (M11_WORK = work-m11 展開先)。n=3 の所要 **98.01–98.40 s**、終了時 load average 1.00–1.09 (1 分値)、3 回とも標準出力が byte 一致。

ネガティブコントロール (`negctl_484.sh`、基準 = SUSPECT 8 関数 / 11 site):

| 壊し方 | 期待 | 実測 (関数 / site) |
|---|---|---|
| NC1 5c0270 の脱落 store 2 本に `load` を足す | 5c0270 が消える | 7 / **9** (5c0270 のみ消滅) |
| NC2 409c80 の F3c 修復 store を `%arg1` に戻す | 409c80 の w64 が増える | 8 / **12** (409c80 に w32 と w64 の 2 項目) |
| NC3 image の 5c0270 区間を nop に潰す (機械語側) | 5c0270 が消える | 7 / **9** (LSF site 90→88) |
| NC4 5c0270 の arg2 store を定数 store にする (IR 側) | 5c0270 が消える | 7 / **9** |

IR のみ・機械語のみのどちらを壊しても判定が落ちる (両方の証拠を要求する設計が効いている)。

## 6. 検証範囲 / 範囲外

- 範囲: `work-m11` 時点 (2026-10-10 生成) の `boot_final3.ll` 7421 関数。base は `dd9ba2c` (#481)。`tools/m11` の既存ファイルは**無変更**。wasm の再ビルドと survey は**未実行** (IR を変えていないため数値は #481 と同一)。
- 範囲外 (弱い主張): (1) base が argN に解決できない load→store は判定不能 — **370 site / 169 関数** (`lsf_unresolved_base_sites` / `fns_with_unresolved_base`)。(2) 消費者が store でない D4 (vtable load → `call [rbx+0x18]` など) は F3c の担当で本調査の形ではない。(3) 動的到達 (どの関数が survey で実行されるか) は未測定。(4) `M11_LB_BASE != 0`・fl-win64 の PE 実体との突合は未実行 (PE 無し)。(5) 8 関数の「真の脱落」判定は目視 (機械語 + IR 行) で、liftdiff での動的確認は未実施。

## 7. 未解決 (起票依頼)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| §3 の 8 関数 / 11 site の IR 修復 (ldfix の F3c 門の拡張: G2 を load 直前までで解決 / G4 を順序考慮 / G5 を関数単位収支に / base を reg コピー・frame slot 経由まで追跡 / `BLK_RE` を `.thread` 接尾ラベル対応に)。417b70 は consumer 伝播が要る | 5c0270 は m11_ov.c の手転記で回避済み。残り 7 関数は IR が誤ったまま | 新規子チケット (`[LD-n]`/`[M11-n]` は PM 採番)。改修後は `audit_lsf.py` の SUSPECT 0 が受入条件 |
| 8 関数の動的到達 (survey で実行されるか) と、liftdiff での脱落の動的確認 | 未測定のため、どの trap/halt0 に効くか不明 | 上の子チケットに含める |
| 範囲外 (1) の 370 site / 169 関数 (base が引数由来でない load→store) | IR 側の判定軸が無く現行算法では見えない | 新規子チケット (SSA 対応が要る。または liftdiff 動的差分に委ねる) |
| `5c0270` の `call [rbx]` (`5c037e`) 脱落 (D15 (DEFECTS.md)) | #481 REPORT §1 のとおり IR に無い | #481 の未解決 (`5c03d0` の `call [rbx+0x18]` と同じ起票) に追記 |
| `BLK_RE` / `Fn.blocks()` がサフィックス付きラベルを併合する (ldfix 全 pass に共通) | F1〜F3c の block-local 対応が他にも崩れている可能性 (F3c の `f3c_no_store` 150 は未検証) | 上の子チケットで全 pass を点検 |
| `m11_gen_ir2.sh` / `m11_e2e.sh` が PE 無しだと ldfix を **黙って skip** (stderr の WARNING のみ) | PE の無い環境で生成した `boot_final.ll` は ldfix 未適用 | #351 (`/home/ubuntu` 絶対パス除去) に追記 |

## 8. DEFECTS.md 行案 (編集は PM 判断)

D4 の観測例に追記: 「`5c0270` / `41a670` (Delphi 単方向リスト unlink): `mov rcx,[rcx]` (rD = rB の自己上書き load) が `store i64 %arg` に化ける。`66e080`: `movsd [rbx],xmm0; mov rax,[rbx]; mov [rbx+8],rax` が `store i64 %arg1`。検出信号: `audit_lsf.py` (機械語 LSF site 数 < IR の `store %argN` 数)」。新規類型なし。

## 9. 成果物 (`tools/m11/ldfix/`)

| パス | 役割 |
|---|---|
| `audit_lsf.py` | LSF 脱落の全数監査 (別算法)。`--json` で site 詳細。`--pe` で PE 版 `Machine` に切替可 |
| `f3c_gate_probe.py` | `fix_f3c` の門 G1〜G5 を 1 関数ずつ表示 (IR 無変更) |
| `ldmach_img.py` / `ldfix_img.py` | PE 無し shim / `ldfix.py` を無改変で動かすラッパ |
| `negctl_484.sh` / `audit_lsf_e2e.sh` | ネガコン 4 本 / 1 コマンド再現 (§4 の同値性検証 + 門 + 監査 + ネガコン) |
| `results/audit_484_post.json` / `results/audit_484_pre.json` | SUSPECT の site 詳細 (`boot_final3.ll` / 修復前 IR) |
