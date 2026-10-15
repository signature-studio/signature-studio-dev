# REPORT_2211 — FRAME_IN_ESCAPED 未判定 44 関数の別名・呼び出し越えの判定 (#2211 / 親 #2185)

## 1. 測定条件

- 測定 commit: `32925d7f` (判定器 `audit_frame_store_alias_2211.py`・結果 JSON・negctl 結果を含む commit)。前版 `92f55325` からの変更は §2 の区間条件の 1 行だけで、判定結果は両版で同一 (sites・fn_info が一致)。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2185 と同じ)。#2185 の結果 JSON は `detail` を持たず入力にできないため、同じ入力を使う。
- PE: fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`、#2185 と同じ)。
- 再現確認: 作業の前に #2185 の判定器 `audit_frame_store_verdict.py` を再実行し、`results/frame_store_verdict_2185.json` と一致 (DROP 3・LIVE-IN 1・UNDETERMINED 44)。
- 判定器 `audit_frame_store_alias_2211.py`: 0.24 秒 (測定 commit で再実行、rc 0)。load average 0.22 (4 vCPU)。
- #2185 の判定器 `audit_frame_store_verdict.py` は変更しない。

## 2. 方式 (#2185 からの変更点)

#2185 と同じ CFG 逆向き探索と 3 値判定 (DROP / LIVE-IN / UNDETERMINED) を使う。変更は次の 5 点。

| # | 規則 | #2185 | #2211 |
|---|---|---|---|
| 1 | 読み書きの判定 | mem の位置を見ず RMW として書きと扱った (`sub ecx, [rax]` で打ち切り) | mem が第 1 オペランドのときだけ書き。`cmpxchg` は書き |
| 2 | 読み | frame 基底の重なる読みで打ち切り | 読みは定義にならないので透過 |
| 3 | 漏出 (glk) | 規則なし | frame 派生値 F (rbp/rsp と lea・mov・算術で得た値) が、メモリへ書かれる / call の引数 (rcx・rdx・r8・r9) に入る / rax で ret する、のいずれかで関数全体を glk とする |
| 4 | glk 無しの関数 | escaped なら全ポインタ store と call で打ち切り | ポインタ store と call は frame に届かないので透過 |
| 5 | rsp/rbp の混在 | 全て打ち切り (MIXED_BASE) | 区間 (`mov rbp, rsp` から `lea rsp, [rbp+N]` まで。rsp のみの関数は `sub rsp, N` から `add rsp, N` まで) の内側では rsp と rbp を同じ frame 座標として比べる。区間内で rsp・rbp が書かれず、push/pop が無く、区間の外から区間内へ飛び込む分岐も、区間より前の分岐も無いときだけ成立 |

打ち切り理由は ALIAS_FRAME_PTR (F 派生ポインタへの store)・LEAK_STORE (glk 関数のポインタ store)・MIXED_BASE・INDEXED・PARTIAL_OR_RMW・CALL (glk 関数の call) に分けて記録する。区間は 48 関数すべてで成立した。glk 関数は 11 関数。

仮定 (未検証): 呼び出し先が frame を得る経路は、引数・戻り値・メモリ (漏出) だけ。保存レジスタ rbp を呼び出し先が読んで外へ出す経路は見ない。戻り値は rax のみ見る。`push` は漏出と数えない。frame アドレスを frame 自身に書く store (`mov [rbp+X], rbp`) は、読み戻されてポインタとして使われる可能性を保守的に漏出と数える。

- 呼び出し先が caller の rsp 相対領域 (home 領域・stack 引数) を書く経路は見ていない。この経路があると、call を越えた先の読みの判定は誤り得る。
- DROP の探索は call を越える (glk 関数でも。call は ENTRY_AFTER_CALL の印を付けるだけで打ち切らない。#2185 の設計)。call の先で slot が書き換わる経路は見ていないので、DROP は store と read の間に call が無いことを前提にする。現行の DROP 3 site (10628a0・13105d0・c38bd0) は、store と read の間が直線で call が無く、判定は変わらない (機械語で確認)。

## 3. 結果

### 3.1 関数単位 (受入 1・2)

| 判定 | #2185 | #2211 |
|---|---|---|
| DROP | 3 | 3 |
| LIVE-IN | 1 | 35 |
| UNDETERMINED | 44 | 10 |

未判定 44 関数のうち 34 関数が LIVE-IN になった。残る 10 関数は §3.4 の子 issue へ移す。

### 3.2 site 単位の遷移

| #2185 の理由 | 件数 | #2211 の判定 (件数) |
|---|---|---|
| ONLY_ENTRY_AFTER_CALL | 27 | LIVE-IN 23・UNDETERMINED (ONLY_ENTRY_AFTER_CALL) 4 |
| BARRIER | 19 | LIVE-IN 12・UNDETERMINED (BARRIER(LEAK_STORE)) 4・UNDETERMINED (ONLY_ENTRY_AFTER_CALL) 2・UNDETERMINED (MIXED) 1 |
| ALL_PATHS_STORE (DROP) | 3 | DROP 3 (変化なし) |
| NO_DEF_ON_ANY_PATH (LIVE-IN) | 1 | LIVE-IN 1 (変化なし) |
| NOSLOT | 1 | PTR_READ 1 (§3.5) |

51 site の合計: DROP 3・LIVE-IN 36・UNDETERMINED 11・PTR_READ 1。

### 3.3 BARRIER 19 site の別名判定 (受入 2)

#2185 で打ち切りになった機械語ごとに、#2211 の判定を示す。ALIAS_FRAME_PTR (F 派生ポインタへの store) は 51 site のどの経路にも現れなかった (0 件)。

| 関数 | #2185 の打ち切り (機械語) | 種類 | #2211 |
|---|---|---|---|
| 11e6e20 | `11e6f40 sub ecx, dword ptr [rax]` | 読み (誤分類) | LIVE-IN |
| 129df10 | `129e1b0 sub ebx, dword ptr [rax + 0x84]` | 読み (誤分類) | LIVE-IN (区間で rsp 混在も解消) |
| 12cb2e0 | `12cb38f sub r8d, dword ptr [rax]` | 読み (誤分類) | LIVE-IN |
| 1354630 | `1354745 mov qword ptr [rsp + 0x20], rax` | rsp/rbp 混在 | 区間で同一座標 → 残る経路は ENTRY_AFTER_CALL (§3.4) |
| 454090 | `454438` ほか 3 件 `mov qword ptr [rsp + 0x28], rax` | rsp/rbp 混在 | 同上 → ENTRY_AFTER_CALL (§3.4) |
| 45c170 | `45c195 mov word ptr [rsp + 0x20], 3` | rsp/rbp 混在 | LIVE-IN |
| 45cda0 | `45cdc5 mov word ptr [rsp + 0x20], 3` | rsp/rbp 混在 | LIVE-IN |
| 45db40 | `45db65 mov word ptr [rsp + 0x20], 0xb` | rsp/rbp 混在 | LIVE-IN |
| 6c01a0 | `6c01e8 mov qword ptr [rsp + 0x20], rax` | rsp/rbp 混在 | LIVE-IN |
| 6c7610 | `6c762c movsq qword ptr [rdi], qword ptr [rsi]` | ポインタ store (rdi は F 外) | LIVE-IN |
| 6c7ca0 | `6c7cc2 movsq qword ptr [rdi], qword ptr [rsi]` | ポインタ store (rdi は F 外) | LIVE-IN |
| 6ca580 | `6ca594 movsq qword ptr [rdi], qword ptr [rsi]` | ポインタ store (rdi は F 外) | LIVE-IN |
| 6ca6c0 | `6ca6d4 movsq qword ptr [rdi], qword ptr [rsi]` | ポインタ store (rdi は F 外) | LIVE-IN |
| f61710 | `f61c6b mov qword ptr [rcx + 0x6c8], rax` | ポインタ store (rcx は F 外) | LIVE-IN |
| 7e45e0 | `7e48ce movss dword ptr [rax + 0x518], xmm0` | ポインタ store (rax は `mov rax, [rbp+0x28]` の読み値) | 読み値は F 外。残るのは 7e48d6 の MIXED (§3.4) |
| 1006ec0 | `1006fe8 mov qword ptr [rax + 0x64], 0` | ポインタ store (glk) | LEAK_STORE → #3225 |
| 5cb210 | `5cb47d mov dword ptr [rax + 8], ecx` | ポインタ store (glk) | LEAK_STORE → #3225 |
| 694c80 | `695163 mov qword ptr [rax + 0x94], rcx` | ポインタ store (glk) | LEAK_STORE・STORE 混在 → #3225 |
| c3b340 | `c3b3f5 mov byte ptr [rcx + 0x20], al` | ポインタ store (glk) | LEAK_STORE → #3225 |

ポインタ経由の store が同じ slot を指すかの答え: 漏出の無い関数では、F 派生でないポインタ (rdi・rcx の値) への store は frame に届かないので透過する。BARRIER 19 のうち LIVE-IN になった 12 site の内訳は、読みの誤分類 3・rsp/rbp 区間 4・非派生ポインタ store 5。漏出のある 4 関数では、store 先が frame を指すかを判定できない (LEAK_STORE)。frame アドレスを frame 自身に保存する store が漏出の根で、その追跡は #3225 の範囲。

### 3.4 未判定 site (子 issue へ移す)

| 関数 | 読み (機械語) | #2211 の判定 | 残る経路・打ち切り | 漏出 (glk) の最初の命令 | 子 issue |
|---|---|---|---|---|---|
| 1006ec0 | `1006fb6 cmp dword ptr [rbp + 0x2c], 1` | ONLY_ENTRY_AFTER_CALL | ENTRY_AFTER_CALL | `1006ec8 mov qword ptr [rbp + 0x40], rcx` | #3228 |
| 1006ec0 | `1007021 cmp byte ptr [rbp + 0x2b], 0` | BARRIER(LEAK_STORE) | `1006fe8 mov qword ptr [rax + 0x64], 0` | 同上 | #3225 |
| 1354630 | `1354784 cmp word ptr [rbp + 0x1d2], 1` | ONLY_ENTRY_AFTER_CALL | ENTRY_AFTER_CALL | `13546f9 mov qword ptr [rbp + 0x188], rbp` | #3228 |
| 441730 | `44178f cmp word ptr [rbp + 0x6e], 0` | ONLY_ENTRY_AFTER_CALL | ENTRY_AFTER_CALL | `441738 mov qword ptr [rbp + 0x28], rbp` | #3228 |
| 4488f0 | `44892d cmp dword ptr [rbp + 0xd8], 0x1000` | ONLY_ENTRY_AFTER_CALL | ENTRY_AFTER_CALL | `4488fe mov qword ptr [rbp + 0x38], rcx` | #3228 |
| 454090 | `454637 cmp byte ptr [rbp + 0x16e], 1` | ONLY_ENTRY_AFTER_CALL | ENTRY_AFTER_CALL | `45409b mov qword ptr [rbp + 0x38], rbp` | #3228 |
| 5c4dc0 | `5c4e43 cmp dword ptr [rbp + 0x58], 0xc0c0c0` | ONLY_ENTRY_AFTER_CALL | ENTRY_AFTER_CALL | `5c4dcb mov qword ptr [rbp + 0x28], rbp` | #3228 |
| 5cb210 | `5cb4aa cmp qword ptr [rbp + 0xc0], 0` | BARRIER(LEAK_STORE) | `5cb47d mov dword ptr [rax + 8], ecx` | `5cb21e mov qword ptr [rbp + 0x68], rbp` | #3225 |
| 694c80 | `6951c8 movsd xmm1, qword ptr [rbp + 0xe8]` | BARRIER(LEAK_STORE)・STORE 混在 | `695163 mov qword ptr [rax + 0x94], rcx` | `694c94 mov qword ptr [rbp + 0x48], rbp` | #3225 |
| c3b340 | `c3b46f cmp dword ptr [rbp + 0x60], 0` | BARRIER(LEAK_STORE) | `c3b3f5 mov byte ptr [rcx + 0x20], al` | `c3b364 mov qword ptr [rbp + 0x48], rbp` | #3225 |
| 7e45e0 | `7e48d6 cvtsi2ss xmm0, dword ptr [rbp + 0x6c]` | MIXED_OR_UNREACHABLE (ENTRY・STORE) | store `7e4659 mov dword ptr [rbp + 0x6c], eax` と ENTRY 経路の混在 | なし | #3230 |

ONLY_ENTRY_AFTER_CALL の 6 site は、関数が漏出する (glk) ため call を越えて打ち切る。呼び出し先の書き込みはまだ見ていない (#3228)。

### 3.5 判定対象外: 7e47b6 (PTR_READ)

`7e47b6 sub eax, dword ptr [rcx + 0x4dc]` の基底は `rcx` で、`7e47b2 mov rcx, qword ptr [rbp + 0x28]` で読んだポインタ。frame slot を直接読まない。frame store の判定の対象ではないため PTR_READ に分類した (#2185 の NOSLOT)。

### 3.6 DROP / LIVE-IN の機械語根拠 (受入 4)

| 関数 | 読み (機械語) | #2185 の理由 | 全経路 | glk | 区間 |
|---|---|---|---|---|---|
| 10628a0 | `10628c0 movzx rax, word ptr [rbp + 0x4e]` (DROP: store `10628bc mov word ptr [rbp + 0x4e], ax`) | ALL_PATHS_STORE | STORE | F | 10628a5-10628c5 |
| 13105d0 | `1310837 add eax, dword ptr [rbp + 0x48]` (DROP: store `1310826 mov qword ptr [rbp + 0x44], rax`) | ALL_PATHS_STORE | STORE | T | 13105d8-1310a08 |
| c38bd0 | `c38c08 cmp qword ptr [rbp + 0x78], 0` (DROP: store `c38c04 mov qword ptr [rbp + 0x78], rax`) | ALL_PATHS_STORE | STORE | T | c38bd8-c38d45 |
| 412160 | `41217d cmp dword ptr [rbp + 0x170], 2` | NO_DEF_ON_ANY_PATH | ENTRY | F | 41216d-4122a1 |
| 103aa50 | `103ab59 add r14d, dword ptr [rbp + 0x38]` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 103aa5f-103ae87 |
| 11e6e20 | `11e6fdb movss xmm0, dword ptr [rbp + 0x108]` | BARRIER | ENTRY | F | 11e6e2f-11e702f |
| 12cb2e0 | `12cb416 mov r8d, dword ptr [rsp + 0x28]` | BARRIER | ENTRY | F | 12cb2e2-12cb498 |
| 4078c0 | `40792b and qword ptr [rbp + 0x38], 0xffffffffffff0000` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 4078cc-407a3c |
| 4078c0 | `40791e cmp dword ptr [rbp + 0x40], 0x10000` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 4078cc-407a3c |
| 418b40 | `418b57 cmp dword ptr [rbp + 0x40], 0x1000` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 418b45-418b68 |
| 45d8b0 | `45da5b cmp word ptr [rbp + 0x3e], 0` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 45d8b7-45dabf |
| 45dc20 | `45dc69 cmp word ptr [rbp + 0x28], 0` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 45dc28-45dc76 |
| 639c70 | `639c83 mov eax, dword ptr [rsp + 0x2c]` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 639c70-639cd4 |
| 695640 | `6956f9 cmp qword ptr [rbp + 0x38], 0` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 69564a-695799 |
| 6ced00 | `6ced14 mov eax, dword ptr [rbp + 0x28]` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 6ced05-6ced17 |
| 808930 | `80896d cmp dword ptr [rbp + 0x5c], 3` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 80893a-808a87 |
| 808c80 | `808ca4 cmp dword ptr [rbp + 0x2c], 3` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 808c85-808caf |
| 81bfd0 | `81bff3 mov eax, dword ptr [rsp + 0x2c]` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 81bfd0-81c05c |
| 81c0d0 | `81c118 mov eax, dword ptr [rbp + 0x2c]` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 81c0d6-81c146 |
| 820d60 | `820dba add dword ptr [rbp + 0x30], ecx` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 820d67-820ddf |
| 824020 | `824069 add dword ptr [rbp + 0x30], eax` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 82402a-824094 |
| 864f80 | `864f94 sub eax, dword ptr [rbp + 0x20]` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 864f85-864f97 |
| 867220 | `867245 cmp dword ptr [rsp + 0x2c], 0` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 867220-867251 |
| 92ea90 | `92eaaf cmp qword ptr [rsp + 0x48], 0` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | 92ea91-92eb0f |
| bf8b40 | `bf8b68 mov eax, dword ptr [rbp + 0xac]` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | bf8b4a-bf8dce |
| c9cf70 | `c9cf8f cmp qword ptr [rsp + 0x48], 0` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | c9cf71-c9cfef |
| da5400 | `da541f cmp qword ptr [rsp + 0x48], 0` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | da5401-da547f |
| da5510 | `da552f cmp qword ptr [rsp + 0x48], 0` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | da5511-da558f |
| e8fba0 | `e8fc08 sub dword ptr [rbp + 0x48], ecx` | ONLY_ENTRY_AFTER_CALL | ENTRY | F | e8fba8-e8fc55 |
| 45c170 | `45c1b5 mov eax, dword ptr [rbp + 0x40]` | BARRIER | ENTRY | F | 45c176-45c1b8 |
| 45cda0 | `45cdd9 movsxd rax, dword ptr [rbp + 0x40]` | BARRIER | ENTRY | F | 45cda6-45ce36 |
| 45db40 | `45db85 cmp word ptr [rbp + 0x40], 0` | BARRIER | ENTRY | F | 45db46-45db8d |
| 129df10 | `129e1d6 sub esi, dword ptr [rbp + 0x88]` | BARRIER | ENTRY | F | 129df1d-129e658 |
| 6c01a0 | `6c0207 mov r9d, dword ptr [rbp + 0x44]` | BARRIER | ENTRY | F | 6c01aa-6c02ee |
| 6c7610 | `6c7665 mov ecx, dword ptr [rbp + 0x44]` | BARRIER | ENTRY | F | 6c761a-6c7ac7 |
| 6c7ca0 | `6c7ccc mov edx, dword ptr [rbp + 0x84]` | BARRIER | ENTRY | F | 6c7cad-6c7dc9 |
| 6ca580 | `6ca5c2 add dword ptr [rbp + 0x64], eax` | BARRIER | ENTRY | F | 6ca588-6ca6af |
| 6ca6c0 | `6ca702 add dword ptr [rbp + 0x64], eax` | BARRIER | ENTRY | F | 6ca6c8-6ca798 |
| f61710 | `f61ce6 mov r8d, dword ptr [rbp + 0x94]` | BARRIER | ENTRY | F | f6171d-f61d34 |

LIVE-IN の全経路は「関数内で定義されない」 (ENTRY)。DROP の全経路は store に当たる (機械語は括弧内)。DROP 3 関数は #2185 の結果と同じ。

### 3.7 ネガティブコントロール (WORKFLOW §5)

| 条件 | 差し替え | DROP / LIVE-IN / UNDETERMINED (関数) | 変わった site (対 ctrl) |
|---|---|---|---|
| ctrl | なし | 3 / 35 / 10 | — |
| 壊す 1 (`--negctl-glk`) | 全関数の漏出を True にする | 3 / 1 / 44 | 35 |
| 壊す 2 (`--negctl-nosync`) | rsp/rbp の区間を無効にする | 3 / 28 / 17 | 7 |

壊す 1 の関数単位の結果は #2185 と一致する (漏出の規則を外すと #2185 の判定に戻る)。壊す 2 で変わるのは 7 site: rbp の区間の 5 site (129df10・45c170・45cda0・45db40・6c01a0) と、rsp のみの関数の 2 site (81bfd0・867220)。結果は `results/negctl_alias_2211_glk.json`・`results/negctl_alias_2211_nosync.json`。

### 3.8 差分 (WORKFLOW §6)

- 測定 commit: `32925d7f`。判定器・結果 JSON・negctl はこの commit で測定した。
- この commit から REPORT を含む HEAD までで `tools/m11/ldfix` に変わるのは `REPORT_2211.md` のみ。`git diff --stat 32925d7f HEAD -- tools/m11/ldfix` の出力は PR 本文の検証結果に載せる。
- 再実行: 修正前 HEAD (`a4480d15`) で判定器を再実行し、3 本の結果 JSON が commit 済みと byte 一致 (`cmp`)。判定器と JSON は本 issue の修正で変えていない。
- #2185 の判定器 `audit_frame_store_verdict.py` は本 issue で変更していない (差分 0 行)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 漏出 store (frame の自己ポインタ保存) の追跡 (1006fe8・5cb47d・695163・c3b3f5) | 関数 1006ec0・5cb210・694c80・c3b340 が UNDETERMINED | #3225 [LD-150] |
| 漏出関数の call 越え 6 site (1006fb6・1354784・44178f・44892d・454637・5c4e43) | 関数 1006ec0・1354630・441730・4488f0・454090・5c4dc0 が UNDETERMINED | #3228 [LD-151] |
| 7e48d6 の MIXED (store 7e4659 と ENTRY 経路の混在) | DROP にも LIVE-IN にも確定しない | #3230 [LD-152] |

## 5. 子 issue

- #3225 [LD-150] 漏出 store の別名判定 (親 #2211)
- #3228 [LD-151] 漏出関数の call 越え (親 #2211)
- #3230 [LD-152] 7e48d6 の IR 側確認 (親 #2211)
