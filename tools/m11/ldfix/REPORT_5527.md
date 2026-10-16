# REPORT_5527 — NONFRAME 規則を call 戻り値まで広げる・5cb210 / 5cb4aa の判定 (#5527 / 親 #4288 / #5143)

## 1. 結論

- 受入 1 を達成した。判定器 `audit_frame_store_alias_2211.py` の NONFRAME 規則 (6) を call 戻り値へ広げた。call の戻り値 `rax` は、呼び出し先の全 `ret` の `rax` が frame 派生でないと示せるときだけ非 frame とする。PE 外の import (IAT 経由) は「未確定 (外部)」として扱い、False にする。
- `5cb210` の `5cb4aa` (`cmp qword ptr [rbp+0xc0], 0`) の打ち切り理由は `ALIAS_FRAME_PTR` (`5cb47d`) から `LEAK_STORE` (`5cb456 movsq`) に移った。`5cb456` の基底 `rdi` は `5cb3d3 call 0x409410` の戻り値で、`rax` を辿ると `0x409410` の間接 call (`.data` の関数ポインタ) に行き着くため、非 frame と示せず UNDETERMINED のままになる (§3)。
- 受入 2 を達成した。変更前後で verdict は全 48 関数・全 51 site で不変 (§2)。打ち切り位置 (barrier の番地または outcome) が変わったのは 3 site (`5cb210`・`7e45e0`・`f61710`)。
- issue 本文の前提は一部違った。`5cb3d3` の呼び出し先 `0x409410` は import ではなく PE 内の関数で、その中の `call qword ptr [rip+0xf9c86c]` は IAT ではなく `.data` (RVA `0xfa5c90`、VA `0x13a5c90` = image base `0x400000` + RVA) の関数ポインタを指す。以下、`.data` の位置は VA で書く。その値は `0x407a50` (REPORT_5141 の関数) で、戻り値は `4073c0` (VirtualAlloc) に依る。これは REPORT_5141 の「外部依存」と同じ結論になる。

## 2. 測定

- 測定 commit: `9bd4afd27` (`feat(ldfix): NONFRAME 規則を call 戻り値まで広げる (#5527)`)。変更前の基準は `b63a95501` (origin/main 取得時点) の判定器。
- 入力: `fl-win64` の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`。issue の値と一致)。`results/audit_undefload_564_full.json`・`results/f4_564_post.json` (判定器の 2 入力)。
- 実行: `python3 audit_frame_store_alias_2211.py <PE> results/audit_undefload_564_full.json results/f4_564_post.json <OUT>`。0.32 s (real)・exit 0・load average 0.22 (開始時)。

| 項目 | 変更前 (b63a955) | 変更後 (9bd4afd) |
|---|---|---|
| 関数 | 48 (UNDETERMINED 44 / DROP 3 / LIVE-IN 1) | 48 (同じ) |
| site | 51 (UNDETERMINED 46 / DROP 3 / LIVE-IN 1 / PTR_READ 1) | 51 (同じ) |
| verdict の差 (関数) | — | **0** |
| verdict の差 (site) | — | **0** |
| 打ち切り位置の差 (site) | — | **3** (下表) |
| `nonframe_stores` の差 (関数) | — | **0** |

打ち切り位置の差 (site 単位・旧 `b63a955` と新 `9bd4afd` の `sites[].barrier_addrs`・`outcomes` を `(fn, addr)` で突き合わせた結果。verdict は 3 site とも UNDETERMINED のまま変わらない):

| site (fn / addr) | 変更前 | 変更後 |
|---|---|---|
| `5cb210` / `5cb4aa` | barrier `5cb47d` `ALIAS_FRAME_PTR` | barrier `5cb456` `LEAK_STORE` |
| `7e45e0` / `7e48d6` | barrier `7e48ce` `ALIAS_FRAME_PTR` | barrier `7e4629` `ALIAS_FRAME_PTR`、新たに outcome `STORE` (`7e4659 mov dword ptr [rbp+0x6c], eax`) |
| `f61710` / `f61ce6` | barrier `f61c6b` `ALIAS_FRAME_PTR` | barrier `f6192b` `ALIAS_FRAME_PTR`、新たに outcome `ENTRY_AFTER_CALL` |

- 対照 (既存結果との byte 一致): `audit_frame_store_callee_3228.py` (同じ判定器を import) の出力は `results/frame_store_callee_3228_head_4238.json` と `cmp` で一致。`alias_evidence_4167.py` の出力は `results/alias_evidence_4167.json` と `cmp` で一致。判定器の変更が既存の判定を変えていないことを確かめた。
- 免除だけの実験 (call 戻り値の規則なし、`ALIAS_FRAME_PTR` を NONFRAME の store で免除) でも verdict は変わらなかった。打ち切りは `5cb456` (LEAK_STORE) へ移った。

## 3. 5cb210 / 5cb4aa の機械語単位の判定

`5cb4aa` の `[rbp+0xc0]` の読みを逆向きに辿ると、`5cb456 movsq [rdi],[rsi]` (LEAK_STORE) に当たる。`rdi` の定義は次のとおり。

| 番地 | 命令 | 意味 |
|---|---|---|
| `5cb3ce` | `mov ecx, 0x42c` | 引数 |
| `5cb3d3` | `call 0x409410` | 呼び出し先 (PE 内) |
| `5cb3d8` | `mov [rbp+0x148], rax` | 戻り値を slot に保存 |
| `5cb43c` | `mov rdi, [rbp+0x148]` | `rdi` に入る |

`0x409410` の `ret` の `rax` は `rbx` (`mov rax, rbx`) で、`rbx` は `409424 mov rbx, rax` (`409418`〜の `call qword ptr [rip+0xf9c86c]` の戻り値)、または 0 (`40941a`)。

| 呼び出し | 解決先 | 判定 |
|---|---|---|
| `409410` の `call qword ptr [rip+0xf9c86c]` (`40941e`) | `.data` (VA `0x13a5c90`) の値 `0x407a50` (IAT ではない) | 間接 call。判定器は解決せず False (保守的) |
| `0x407a50` の戻り値 | REPORT_5141 §3・§4 のとおり `4073c0` (VirtualAlloc) の戻り値に依る | **未確定 (外部)** |

- 判定器は間接 call を解決しない。`call_ret_nonframe` は直接 call (`CS_OP_IMM`) だけを追う。したがって `5cb456` の `rdi` は「非 frame と示せない」で、`5cb4aa` は UNDETERMINED。
- 結論は REPORT_5141 と同じ「未確定 (外部)」だが、経路は違う。issue が想定した「IAT の import」ではなく、`.data` の関数ポインタ経由の PE 内関数 `0x407a50` である。

## 4. 方式 (受入 1)

- 規則 (6)' (`call_ret_nonframe`): `call` の戻り値 `rax` は、直接 call 先 `f` の全 `ret` で `reg_nonframe(rax)` が成り立つときだけ非 frame。`f` が PE 外 (IAT・`.pdata` 外・間接 call) なら False。深さは `depth - 1` で再帰を止める。
- `ALIAS_FRAME_PTR` の打ち切りは、store が NONFRAME (規則 6) に入るときは免除する (`effect`)。NONFRAME は glk 関数の store に限る。
- `rax` 以外 (`CALLER_SAVED` の rcx・rdx 等) の call は従来どおり False。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 間接 call (`call qword ptr [rip+X]` で `.data` の関数ポインタを呼ぶ) を解決しない | `409410` 経由の `rdi` は「非 frame と示せない」。`5cb456` の LEAK_STORE は残る。`0x407a50` の戻り値は REPORT_5141 でのみ外部と判定 | 親 #4288 の本文に残す (本 PR では扱わない) |
| `5cb4aa` の verdict | UNDETERMINED のまま (`LEAK_STORE` 5cb456)。判定を DROP/LIVE-IN に変えるには `0x407a50` の戻り値を frame に依らないと示す必要がある | 親 #4288 (未解決の受入) |
| 旧 JSON `frame_store_callee_3228.json` と HEAD の不一致 | #4238 §4 と同じ。本 PR は書き換えない | 親 #4288 |

## 6. 再現

- `python3 tools/m11/ldfix/audit_frame_store_alias_2211.py <block00031_PE.bin> results/audit_undefload_564_full.json results/f4_564_post.json <OUT>` の出力を変更前 (`b63a955`) と比べる。
- 入力 PE の展開: 素材 `fl-win64` の `extracted/block00031_PE.bin` を `tar --zstd -xf` で取り出す (WORKFLOW §11)。
- `0x409410` の逆アセンブル: `python3 tools/m11/ldfix/pe_disasm_va.py <block00031_PE.bin> 0x409410 40`。IAT 解決は `.data` の値を直接読む (import 表の `address` とは一致しない)。
