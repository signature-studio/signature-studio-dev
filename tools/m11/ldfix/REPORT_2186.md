# REPORT_2186 — DROP 候補 10628a0 / c38bd0 の IR 側確認と m11_gen_ir2 再生成で sites 2,737 を再現 (#2186 / 親 #2144)

## 1. 測定条件

- 測定 commit: `9d2fe0fb` (origin/main)。監査スクリプト・ldfix・`m11_gen_ir2.sh`・`m11_lift.sh` は無変更。
- 素材: `fl-win64` (PE `extracted/block00031_PE.bin`、sha256 `b2c64da4…9496d`)・`toolchain-retdec` (RetDec v5.0)・
  `work-m11` (`tools/m11/work/`)・`work-liftdiff`。`fl-win64` と `toolchain-retdec` は `$RUNNER_TEMP` 配下に展開し、
  `FL_WIN64_DIR` / `RETDEC_ROOT` に設定した。`toolchain-emsdk` は展開のみ (本件では未使用)。
- IR の作り方:
  - `boot0〜4.lift.ll` は `work-m11` の既存物を再利用した (`m11_lift_all.sh` による全 lift の再実行はしていない)。
  - `boot5.lift.ll` は `m11_lift.sh m11_extra_ranges5.txt boot5 600` で作り直した (RetDec, 7.6 秒, rc 0)。`work-m11` には boot5 が無いため。
  - `m11_gen_ir2.sh` を 2 回実行した (boot5 lift の前後。どちらも rc 0、41 秒)。ldfix は両回とも F1=902 / F1v=4 / F2=30 / F3a=3 / F3b=5 / F3c=36 / F4=10 (errors=0)。
    最終的な `boot_final.ll` は 492,784 行、`ir_sha256=b61a91d3…cff9ff3`。
- 監査 `audit_undefload_dest.py` の入力は **`*.norm0.ll`** (`m11_gen_ir2.sh` は norm0 を作らない)。
  したがって、再生成が監査の入力を変えるのは boot5 の norm0 だけである。
- 監査の実行: 1 回 57 秒 (load average 1.1 前後、4 vCPU)、いずれも rc 0。
  - (a) `boot0〜5.norm0.ll` (6 入力): **sites 2,737**
  - (b) `work-m11` の `boot0〜4.norm0.ll` + `miniind.norm0.ll` (6 入力): **sites 2,731**
  - (c) `boot0〜4.norm0.ll` (5 入力): **sites 2,729**
- 結果 JSON: `results/audit_undefload_dest_2186.json` (a)・`results/audit_undefload_dest_2186_wm11.json` (b)・
  `results/audit_undefload_dest_2186_b0to4.json` (c)・`results/ldfix_report_2186.json` (boot5 lift 後の ldfix 報告)。

## 2. 結果

### 2.1 受入条件 1: 10628a0 / c38bd0 の IR 側確認

両関数とも、該当 frame read は **store の無い alloca からの load** (= undef 相当) になっていた。
`boot*.norm0.ll`・`boot*.drc.ll` (RetDec の生出力)・`boot*.lift.ll`・`boot_final.ll` を確認した。

- **10628a0** (`boot3.norm0.ll`):
  - `%0 = alloca i16` の `%1 = load i16, ptr %0` に対応する store が関数内に無い。`ret` は `zext i16 %1`。
  - 機械語は `10628b7 movzx rax,[rbp+0x38]` → `10628bc mov [rbp+0x4e],ax` → `10628c0 movzx rax,[rbp+0x4e]`。
    IR には `[rbp+0x38]` の読みも `[rbp+0x4e]` への store も無い。store の欠落が起きている。
  - `boot3.lift.ll` では `%1 = xor i16 0, 0`。
  - `boot_final.ll` / `boot_final3.ll` では同じ `xor i16 0, 0` (両方に 36 箇所)。
- **c38bd0** (`boot2.norm0.ll`):
  - `%1 = load i64, ptr %0` (`%0 = alloca i64`) に対応する store が無い。`%2 = icmp eq i64 %1, 0` で分岐を決める。
  - 機械語は `c38c04 mov [rbp+0x78],rax` → `c38c08 cmp [rbp+0x78],0`。`c38c04` の store は IR に無い。
  - `boot2.lift.ll` では `%1 = xor i64 0, 0` で、`icmp` が定数に畳まれる。
- **変換の段**: norm0 の `load` が lift で `xor 0,0` になるのは `m5/ir5_patch.py` の B1 (「未初期化 alloca load → 値 0」) の説明と一致する。
  `ldfix_report.json` には 10628a0 / c38bd0 の VA が無い。ldfix はこの 2 関数に触れていない。
- **結論**: DROP 候補は IR 側でも確認できた。機械語上の store (`10628bc` / `c38c04`) が IR に無く、その読みは undef → B1 で 0 に固定される。
  値の供給元 (`[rbp+0x38]` 側) が IR のどの段で落ちたかは未特定 (本 REPORT の範囲外)。

### 2.2 受入条件 2: `m11_gen_ir2.sh` 再生成と sites の再現

- 6 入力 (boot0〜5) の監査で **sites 2,737** を再現した。REPORT_1866 の 2,737 と一致。
- 内訳 (a): `DEST_FRAME_IN_ESCAPED` 15 / `DEST_FRAME_PTR_ESCAPED` 3 / `DEST_FRAME_OTHER` 10 / `DEST_MEMREAD` 6 / `DEST_RIPREAD` 1 / `REGLIVE` 2,506 / `NOADDR` 196。
- REPORT_1866 の `DEST_FRAME_IN_ESCAPED` 18 は、ポインタ分割前の値で、今の 15 + 3 (PTR_ESCAPED) に当たる。内訳も一致する。
- 10628a0 / c38bd0 は `DEST_FRAME_IN_ESCAPED` の関数集合に含まれない (両方とも上の undef 読みは、consumer の直接 memop 判定を通る site ではない)。

### 2.3 受入条件 3: 再生成 IR と work-m11 IR の差 (6 site) の原因

| 入力 | sites |
|---|---|
| (c) 5 入力 `boot0〜4` | 2,729 |
| (b) 6 入力 `boot0〜4` + `miniind` (`work-m11` の既定) | 2,731 (+2) |
| (a) 6 入力 `boot0〜4` + `boot5` (再生成) | 2,737 (+8) |

- `boot0〜4.norm0.ll` は (a)・(b)・(c) で同じファイル (`work-m11` 由来)。差は **6 入力目が `miniind` か `boot5` か** だけである。
- よって 6 site の差 (2,737 − 2,731) は、6 入力目を `miniind` から `boot5` に差し替えたことによる (5 入力からの増分が +2 と +8)。
  REPORT_2141 が推定していた「boot5 欠落」と整合する。boot5 を再 lift して 6 入力に入れたことで 2,737 が再現した。
- 差の分類: (a) と (b) の `DEST_FRAME_IN_ESCAPED` と `DEST_FRAME_PTR_ESCAPED` はどちらも 15 / 3 で同じ。増えた site は REGLIVE・NOADDR・DEST_FRAME_OTHER に入っている。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 10628a0 / c38bd0 の store 欠落の起点 (値の供給元 `[rbp+0x38]` / `[rbp+0x78]` が IR のどの段で落ちるか) と修復 | DROP は IR 側で確認したが、起点と修復の方式は未決。コード変更は本 issue の範囲外 | #2144 (親・未起票。修復の起票は PM 判断) |
| 48 関数のうち 46 関数の判定 (直前ブロックの store を見る拡張) | 脱落か live-in かが未確定 | #2185 [LD-81] (既存) |
| `boot0〜4` の lift を `m11_lift_all.sh` から作り直した場合との一致 | 本 REPORT の boot0〜4 は `work-m11` の既存 lift を再利用。測定条件の注記であり、受入条件には含まれない | 未起票 (必要なら PM が判断) |
| dest 版の SUSPECT 定義と件数の正式化 | 受入条件 3 の SUSPECT 件数が未定義 | #2144 (既存) |

## 4. コード差分

測定 commit `9d2fe0fb` から、この REPORT を含む HEAD までの `tools/m11/ldfix` のコード差分は 0 行。
追加は REPORT (`REPORT_2186.md`) と結果 JSON のみ。

```
git diff --stat 9d2fe0fb HEAD -- tools/m11/ldfix
```

(出力は、この REPORT と results の追加分のみ。`.py` / `.sh` の差分は 0 行)

## 5. 参照

- 親: `REPORT_2144.md` (§2.1 の 10628a0 / c38bd0 の機械語確認)。
- 前提: `REPORT_2141.md` (boot5 欠落の推定 — 本 REPORT §2.3 で確認)、`REPORT_1866.md` (2,737 の元データ)。
