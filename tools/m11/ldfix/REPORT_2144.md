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
- SUSPECT の正式な定義 (dest 版) は本 run でも決めていない。上の件数を SUSPECT の再計測値とはみなさない。
- 測定 commit `84b8faa7` と HEAD までのコード差分は §4 に記載。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 48 関数のうち 46 関数の判定 (直前ブロックの store を見る拡張が必要) | 脱落か live-in かが未確定 | #2185 [LD-81] |
| 10628a0 / c38bd0 の IR 側確認 (IR で該当 read が undef か) | DROP 候補の確定 | #2186 [LD-82] |
| 入力 IR を `m11_gen_ir2.sh` で再生成して sites 2,737 と突き合わせる | 2,731 と 2,737 の差 (6 site) の原因未確認 | #2186 [LD-82] |
| dest 版の SUSPECT 定義と件数の正式化 | 受入条件 3 の SUSPECT 件数が未定義 | 本 issue #2144 (未達。SUSPECT を定義するには DROP 判定 (#2185) が要る) |

## 4. コード差分

測定 commit `84b8faa7` から、この REPORT を含む HEAD までの `tools/m11/ldfix` の差分は、
REPORT・結果 JSON の追加のみで `.py` の差分は 0 行 (`git diff --stat 84b8faa7 HEAD -- tools/m11/ldfix` の出力で確認)。

## 5. 参照

- 親: `REPORT_1866.md` (§4 の受入条件、§5 のポインタ候補)。
- 前提: `REPORT_564.md` (FRAME_IN_ESCAPED 53 関数・F4 の定義)。
