# REPORT_2144 — FRAME_IN_ESCAPED 未修復 48 関数の判定・ポインタ値 read の分類 (#2144 / 親 #1866)

## 1. 測定条件

- 測定 commit: `84b8faa7` (ポインタ分類を含む `audit_frame_store_verdict.py` 追加後に測定)。
  コード変更の commit は `cdc67bb8` (dest 監査のポインタ分類) → `84b8faa7` (判定スクリプト)。
- 入力 IR: `work-m11` 素材の `tools/m11/work/*.norm0.ll` (`boot0〜4` + `miniind`)。
  `m11_gen_ir2.sh` による再生成は**未実施** (本 run の 60 分内に収まらないため)。
- PE: `fl-win64` の `block00031_PE.bin` (sha256 は未記録)。
- 監査 `audit_undefload_dest.py` (6 入力): 57 秒、load average 0.3〜0.8 (4 vCPU)、rc 0。
- 判定 `audit_frame_store_verdict.py` (48 関数): 0.1 秒、rc 0。
- 結果 JSON: `results/audit_undefload_dest_2144.json`・`results/frame_store_verdict_2144.json`。

## 2. 結果

### 2.1 受入条件 1: FRAME_IN_ESCAPED 未修復 48 関数の判定

- 母集合: `audit_undefload_564_full.json` の FRAME_IN_ESCAPED 53 関数から、F4 修復済み 5 関数
  (41ca30 / 52a7f0 / 666c30 / 71dd80 / 864f60) を除いた **48 関数**。
- 機械判定 (`audit_frame_store_verdict.py`): 同じ frame slot への書き込みが、読みの直前の straight-line 区間 (call/ret/jmp/条件分岐を挟まない) にあるかを見た。
  - `STORE_IN_BLOCK_FN` **2 関数**: 10628a0 / c38bd0。手で逆アセンブルを確認した。
    - 10628a0: `10628bc mov word [rbp+0x4e],ax` → `10628c0 movzx rax,word [rbp+0x4e]` (間に call なし)。
    - c38bd0: `c38c04 mov [rbp+0x78],rax` → `c38c08 cmp [rbp+0x78],0` (間に call なし)。
    - 機械語上は store があるのに IR の読みが undef になった候補。**真の脱落候補**。IR 側の確認は未実施。
  - `UNDETERMINED` **46 関数**: 直前区間に store が無い。ただし**ブロック境界より前の store は見ていない**ので、live-in とは断定しない。判定は未了。

48 関数の一覧 (判定付きは `results/frame_store_verdict_2144.json`):

```
1006ec0 103aa50 10628a0(DROP) 11e6e20 129df10 12cb2e0 13105d0 1354630 4078c0 412160 418b40 441730 4488f0 454090 45c170 45cda0 45d8b0 45db40 45dc20 5c4dc0 5cb210 639c70 694c80 695640 6c01a0 6c7610 6c7ca0 6ca580 6ca6c0 6ced00 7e45e0 808930 808c80 81bfd0 81c0d0 820d60 824020 864f80 867220 92ea90 bf8b40 c38bd0(DROP) c3b340 c9cf70 da5400 da5510 e8fba0 f61710
```

### 2.2 受入条件 2: ポインタ値 read の分類

- 決定: **別クラス `DEST_FRAME_PTR_ESCAPED` に分ける** (`audit_undefload_dest.py`、commit `cdc67bb8`)。
- 根拠: 値 read (`cmp`・`test`・`add` 等) は値そのものの脱落を見る。ポインタ read は frame 値を**次のメモリ操作のアドレス**に使う。
  同じ「frame から読んだ値」でも、脱落時に壊れ方が違う (値なら誤った分岐、ポインタなら誤アドレスへの store)。分けないと件数で混ざる。
- 結果 (dest 監査 6 入力): `DEST_FRAME_PTR_ESCAPED` **3 site**。
  - `4425f0` (i128): `442655 movsd [rax],xmm0` ← `442651 mov rax,[rbp+0x60]`
  - `783d00` (i64): `78417b mov word [rax+0x2c],0x3d` ← `784174 mov rax,[rbp+0xb0]`
  - `e9d8a0` (i1): `e9d8f3 movsq [rdi],[rsi]` ← `e9d8ef mov rsi,[rbp+0x68]`
- 分割後も合計は不変 (`DEST_FRAME_IN_ESCAPED` 15 + `DEST_FRAME_PTR_ESCAPED` 3 = 18)。

### 2.3 受入条件 3: SUSPECT 件数の再計測

| 監査 | 入力 | sites | 主な分類 |
|---|---|---|---|
| dest 版 (本 run) | `work-m11` norm0 6 入力 | **2,731** | REGLIVE 2,503 / NOADDR 194 / DEST_FRAME_IN_ESCAPED 15 / DEST_FRAME_OTHER 9 / DEST_FRAME_PTR_ESCAPED 3 / DEST_MEMREAD 6 / DEST_RIPREAD 1 |
| dest 版 (REPORT_1866) | 再生成 IR 6 入力 | 2,737 | DEST_FRAME_IN_ESCAPED 18 (ポインタ分割前) |

- **注意**: sites 2,731 と REPORT_1866 の 2,737 (差 6) は、入力 IR の出所 (`work-m11` の norm0 と REPORT_1866 の再生成 IR) の差による。同一 IR での比較はしていない。
- 上の件数は dest 版の class 件数であり、SUSPECT の再計測値ではない。SUSPECT の再計測は §2.4。
- 測定 commit `84b8faa7` と HEAD までのコード差分は §4 に記載。

### 2.4 受入条件 3: SUSPECT 件数の再計測 (測定 commit `26f90ada`)

- SUSPECT は `audit_lsf.py` の既存判定を使う (SUSPECT_VAS = store 形 / SUSPECT_USE_VAS = 消費者形 / SUSPECT_MIXED_VAS / SUSPECT_DISP_VAS (#2396))。
  `audit_undefload_dest.py` には SUSPECT 定義が無いので、dest 版は §2.3 と同じく class 件数として別掲する。
  この定義の選択は本 run の判断。dest 版に別の SUSPECT 定義が要るなら、PM が別 issue にする。
- IR: `m11_gen_ir2.sh` で再生成した。`boot0〜4` は work-m11 の既存 lift、`boot5` は `m11_lift.sh m11_extra_ranges5.txt boot5 600` で作り直した (7.98 秒、rc 0)。
  gen_ir2 は 41 秒、rc 0。ldfix・ld108 を適用。`boot_final.ll` は 492,765 行、sha256 `e4255f53…`。同じ手順の 2 回目の再生成で sha256 が一致した。
  比較用の ldfix 無し IR は `M11_LDFIX=0 M11_FIX_LD108=0` で生成 (sha256 `2622357b…`)。
- 監査 `audit_lsf.py`: 1 回 20 秒、rc 0。worktree の HEAD で再実行し、結果 JSON (`results/audit_lsf_2144_post.json`) とバイト一致した。

| 判定 (audit_lsf.py) | ldfix 無し (`results/audit_lsf_2144_pre.json`) | ldfix 適用 (`results/audit_lsf_2144_post.json`) |
|---|---|---|
| SUSPECT_VAS (store 形) | 8 関数 (409c80 417b70 41a670 5c0270 66e080 7e5240 806740 c62780) | **0** |
| SUSPECT_USE_VAS (消費者形) | 52 関数 / 56 引数 | **23 関数 / 24 引数** |
| SUSPECT_MIXED_VAS | 124 関数 | 119 関数 |
| SUSPECT_DISP_VAS (#2396) | 1 (41a670) | 0 |

- 48 関数 (§2.1 の一覧) との交差: SUSPECT_VAS・MIXED・DISP は両 IR で 0 件。SUSPECT_USE_VAS は ldfix 無しで 2 件 (6ca580 / 6ca6c0。判定は UNDETERMINED)、ldfix 適用で 0 件。
- 読み方: SUSPECT は引数 (argN) 経由の load 脱落の形を見る判定で、FRAME_IN_ESCAPED の 48 関数とは交差しない。
  SUSPECT 件数は本件型 (frame slot の読み脱落) の残存を示さない。48 関数の判定は §2.1・§2.2 の DROP / LIVE-IN で行う。
- dest 版 (`audit_undefload_dest.py`、boot0〜5 の norm0 6 入力、57 秒、rc 0。`results/audit_undefload_dest_2144_regen.json`):

| class | sites |
|---|---|
| REGLIVE | 2,505 |
| NOADDR | 196 |
| DEST_FRAME_IN_ESCAPED | 15 |
| DEST_FRAME_OTHER | 10 |
| DEST_FRAME_PTR_ESCAPED | 3 |
| DEST_MEMREAD | 6 |
| DEST_RIPREAD | 2 |
| 合計 | 2,737 |

  合計 2,737・DEST_FRAME_IN_ESCAPED 15・DEST_FRAME_PTR_ESCAPED 3 は REPORT_2186 §2.2 (a) と一致する。
  REGLIVE と DEST_RIPREAD が各 1 ずれる。9d2fe0fb 以降に `audit_undefload_dest.py` が 124 行変わっているので、その差による可能性がある (未切り分け)。
- IR の sha256 は REPORT_2186 (`b61a91d3…`・492,784 行) と一致しない。9d2fe0fb 以降に `m11_gen_ir2.sh` (13 行) と ldfix が変わっているため。REPORT_2186 の IR は再現していない。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 48 関数のうち 46 関数の判定 (直前ブロックの store を見る拡張が必要) | 脱落か live-in かが未確定 | #2185 [LD-81] |
| 10628a0 / c38bd0 の IR 側確認 (IR で該当 read が undef か) | DROP 候補の確定 | #2186 [LD-82] |
| 入力 IR を `m11_gen_ir2.sh` で再生成して sites 2,737 と突き合わせる | 2,731 と 2,737 の差 (6 site) の原因未確認 | #2186 [LD-82] |
| dest 版に SUSPECT 定義が無い (本 PR は `audit_lsf.py` の既存 SUSPECT で計測。48 関数とは交差 0 (§2.4)) | 本件型の残存は SUSPECT では見えない | PM が dest 版の SUSPECT 定義を求める場合のみ別 issue (未起票) |

## 4. コード差分

測定 commit `84b8faa7` から、この REPORT を含む HEAD までの `tools/m11/ldfix` の差分は、
REPORT・結果 JSON の追加のみで `.py` の差分は 0 行 (`git diff --stat 84b8faa7 HEAD -- tools/m11/ldfix` の出力で確認)。

§2.4 の SUSPECT 再計測の測定 commit は `26f90ada` (main HEAD)。そこから本 PR の HEAD までの `tools/m11/ldfix` の差分は REPORT と結果 JSON の追加のみ。
`git diff --stat 26f90ada HEAD -- tools/m11/ldfix ':!tools/m11/ldfix/REPORT_2144.md' ':!tools/m11/ldfix/results'` の出力は空 (コード差分 0 行)。

## 5. 参照

- 親: `REPORT_1866.md` (§4 の受入条件、§5 のポインタ候補)。
- 前提: `REPORT_564.md` (FRAME_IN_ESCAPED 53 関数・F4 の定義)。
