# REPORT_5143 — NONFRAME の store を ALIAS_FRAME_PTR で打ち切らない・5cb4aa の打ち切り理由 (#5143 / 親 #4288 / #4238)

## 1. 結論

- 受入 1 (`407a50` の戻り値 `rax` の全経路) は #5141 (PR #5152・merge 済み) で達成済み。本 PR では扱わない (REPORT_5141 §3)。
- 判定器 `audit_frame_store_alias_2211.py` の `effect()` で、NONFRAME の store (規則 6) を `ALIAS_FRAME_PTR` で打ち切らないようにした (1 行)。判定 (DROP / LIVE-IN / UNDETERMINED) は全 48 関数・全 site で変わらない。変わったのは `5cb210` `5cb4aa` の打ち切り理由だけ (`BARRIER(ALIAS_FRAME_PTR)` → `BARRIER(LEAK_STORE)`)。
- `5cb4aa` は UNDETERMINED のまま。残りの打ち切り `5cb456 movsq [rdi],[rsi]` (LEAK_STORE) の `rdi` は `5cb3d3 call 0x409410` の戻り値で、`409410` の戻り値は `call qword ptr [rip+0xf9c86c]` (import) の戻り値 `rbx` に依存する。import の先は PE 外なので、#5141 §5 の方式で「未確定 (外部)」になる。NONFRAME 規則を call 戻り値へ広げる実装は本 PR では行っていない。その場合でも、この `rdi` 経路は「未確定 (外部)」で止まると推定する (未実測・§3.2)。
- 旧 JSON `frame_store_callee_3228.json` (3 / 35 / 10) は書き換えず旧値のまま残す (§3.3)。

## 2. 測定条件・コード変更

- 測定 commit (コードを変えた最後の commit): `5c5351a31` (`fix(ldfix): NONFRAME store is not an ALIAS_FRAME_PTR barrier (#5143)`)。
- 入力: `results/audit_undefload_564_full.json`・`results/f4_564_post.json` (#2211・#3228・#4238 と同じ)。PE は fl-win64 の `extracted/block00031_PE.bin` (sha256 先頭 16 桁 `b2c64da40921cf26`)。素材 `fl-win64.tar.zst` から `tar --zstd -xf` で展開 (`$RUNNER_TEMP` 下)。
- 変更: `effect()` の `ALIAS_FRAME_PTR` 判定に `and ins.address not in NONFRAME` を追加。規則 6 のコメントに 2 行追記。
- 実行 (測定 commit `5c5351a31`・run 時 load 0.04〜0.22):
  - `audit_frame_store_alias_2211.py` (既定): 0.29 s・rc=0。
  - `audit_frame_store_callee_3228.py`: 0.29 s・rc=0。出力は `results/frame_store_callee_3228_head_4238.json` と `cmp` 一致。

## 3. 結果

### 3.1 HEAD (変更前) と変更後の比較

| 比較 | 結果 |
|---|---|
| 関数判定 (`verdict`) 変更前 vs 変更後 | 差分 0 (48 関数) |
| site 判定 (`verdict`) | 差分 0 (DROP 3・LIVE-IN 1・UNDETERMINED 44 関数。site は UNDETERMINED 46・DROP 3・LIVE-IN 1・PTR_READ 1) |
| `5cb210` `5cb4aa` の `why` | `BARRIER(ALIAS_FRAME_PTR)` → `BARRIER(LEAK_STORE)` (barrier は `5cb47d` → `5cb456`) |
| 判定器 3228 の出力 | `results/frame_store_callee_3228_head_4238.json` と byte 一致 |
| `--negctl-noprov` (規則 6 を無効化) | 変更前 HEAD の出力と byte 一致 (規則 6 が効いていることの確認。規則 6 を消すと変更前の判定に戻る) |

### 3.2 5cb4aa の打ち切り位置 (機械語)

- `5cb4aa cmp qword ptr [rbp+0xc0], 0` の読み位置から逆向きに辿ると、`5cb47d mov dword ptr [rax+8], ecx` (NONFRAME 集合に入る store) で打ち切られていた (HEAD)。`rax` は `[rbp+0x198]` で、その slot の書きは入口引数 (`5cb237`) だけ。
- 変更後は `5cb47d` を通過し、次の打ち切り `5cb456 movsq [rdi],[rsi]` (LEAK_STORE) で止まる。`rdi` は `5cb43c mov rdi,[rbp+0x148]`、`[rbp+0x148]` は `5cb3d3 call 0x409410` の戻り値。
- `409410` (`pe_disasm_va.py` で逆アセンブル): `test rcx,rcx` が 0 なら `rbx=0`。非 0 なら `call qword ptr [rip+0xf9c86c]` の戻り値を `rbx` に取る。`rbx` が 0 のときだけ `call 0x409730` を呼ぶ。
- `[rip+0xf9c86c]` の先は import 表に無い (IAT slot RVA `0xfa5c90`・pefile の import 表と照合して該当なし。REPORT_4238 §3.3 と同じ)。PE 内で決まらないので「未確定 (外部)」(REPORT_5141 §5 の方式)。
- よって `5cb4aa` の判定 (DROP / LIVE-IN) は、#5141 の方式では確定しない (推定。call 戻り値の拡張は未実装)。UNDETERMINED のまま。

### 3.3 旧 JSON と 3228 の値 (受入 3 の決定)

| 出力 | DROP | LIVE-IN | UNDETERMINED | 扱い |
|---|---|---|---|---|
| 旧 `results/frame_store_callee_3228.json` (`b765aa322`・#4090 以前) | 3 | 35 | 10 | 書き換えない。旧値として残す |
| HEAD (`results/frame_store_callee_3228_head_4238.json`・本 PR 後も同じ) | 3 | 1 | 44 | 現行の判定 |

- 決定: 旧 JSON は書き換えず残す。HEAD の値とは別物として扱う (REPORT_4238 §3.1 と同じ)。差が出る理由は #4090 の `lea` 修正 (判定器の変更) による。

### 3.4 既存の結果ファイルとの不一致 (変更前から)

- HEAD の `audit_frame_store_alias_2211.py` 既定出力は `results/frame_store_verdict_4090.json` と一致しない (site 5 件の `why` が違う: `1006ec0 1007021`・`5cb210 5cb4aa`・`694c80 6951c8`・`7e45e0 7e48d6`・`f61710 f61ce6`)。この不一致は本 PR の変更前から存在する (本 PR は `frame_store_verdict_4090.json` を書き換えない)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `5cb4aa` の判定 (`rdi` = `409410` の戻り値 = import `[rip+0xf9c86c]` の先) | `5cb4aa` は UNDETERMINED のまま。NONFRAME 規則の call 戻り値への拡張 (受入 2 の後半) は、import の先が PE 外のため「未確定 (外部)」で止まる | 親 #4288 の本文に追記 (受入 2 の後半) |
| `frame_store_verdict_4090.json` と HEAD の 5 site の不一致 | 既存の結果ファイルの扱い。判定 (verdict) は一致 | 親 #4288 の本文に追記 |

## 5. 差分 (WORKFLOW §6)

- 測定 commit `5c5351a31` から HEAD までのコード差分: `git diff 5c5351a31 HEAD -- tools/m11/ldfix` は本 REPORT と `REPORT_5143.md` 以外に変更なし (判定器のコードは測定 commit と同じ)。
