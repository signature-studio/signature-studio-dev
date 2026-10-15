# Fresh Air REPORT 付録 (#4071 / FA-51): KH のみ snap-in `vocalfilter` の SC 側との同一入力差分 (C4〜C6)

- 親: #3741 (FA-45)・#52 (FA-5)。判定基準: [REPORT_APPENDIX_2739.md](REPORT_APPENDIX_2739.md) §1 (版 1)。前段: [REPORT_APPENDIX_FA45.md](REPORT_APPENDIX_FA45.md) §5。

## §1. 結論

| 項目 | 結果 |
|---|---|
| SC 側の root | `0x1808e1fa0` (process 本体)。FA-45 が使った `0x1808e1f30` は deleting destructor で process ではなかった (§2) |
| KH 側の root | `0x18085a730` (formant process, `snapins.json` の `formant`・ns `vocalfilter`) |
| C4 同一入力 | 同一 seed `0x5F17E4`・N=200・600 call。param 写像は機械語の読みに基づく (§2) |
| L/R (C5) | **600/600 call で bit 一致** |
| state (C5) | **591/600 call で不一致** (比較窓 0x80 B の先頭付近の仮数部の下位ビット)。判定は「bit 不一致の確定のみ」(C6) |
| 意味の同一性 | **未判定**。state 窓の配置が未確定 (§4) |

## §2. param 写像の根拠 (機械語の読み)

- SC `0x1808e1fa0`: `this+0x90` から P を取り、`P+0x9dc4` (f32, freq A 相当)・`P+0x9e0c` (f32)・`P+0x9e54` (f32, Q)・`P+0x9e9c` (u8 ≠ 0 で分岐)・`P+0x9ee4` (u8, `neg`/`sbb` で 0/1 化)・`S+0x98` (f32, sr) を読む。
- KH `0x18085a730`: `ctx+0x3188` から P を取り、`P+0` (int, type の `&1`)・`P+4` (f32)・`P+8` (f32, Q, `log10f` へ)・`P+0xc` (u8, `&1`)・`P+0x10` (u8, `&1`)・`this+0x60` (sr) を読む。
- 写像: SC `0x9dc4→KH P+0`・`0x9e0c→P+4`・`0x9e54→P+8`・`0x9e9c→P+0xc`・`0x9ee4→P+0x10`。`this+0x60` ↔ `S+0x98`。
- 判定ルール: flag は 0/1 のみ書く (SC は非 0 判定、KH は `&1` で読むので、2 以上は両側で一致しない)。
- 機械語の読みは `objdump -d` の逆アセンブル (SC: `SlateCore.core_64`・KH: `HeartCore.core_64`) による。

## §3. 測定 (コミット済み HEAD で再現)

- 測定 commit: `6e5a837a6` (root の訂正と差分ハーネスを commit した最後の commit)。nproc=4・load 1 分値 0.03〜0.11 (08:49〜08:50)。
- 実行: `SC_CORE=<SlateCore.core_64> KH_CORE=<HeartCore.core_64> bash tools/targets/freshair/ks_semantic_vf_scen.sh 200 0x5F17E4 0`
- 実測: fma=0 `real 0.617 s`・`user 0.530 s`・EXIT=0。fma=1 `real 0.622 s`・`user 0.531 s`・EXIT=0。
- SC の出力は fma=0 と fma=1 でバイト一致 (`cmp`)。このシナリオでは fma の差が出力に出ない。
- smoke (`ks_sc_vf_smoke.sh 20`・root 訂正後): fma=0/1 とも rows=20・ERR=0・stderr=0 B。

| 比較 | 結果 |
|---|---|
| L/R (600 call) | bit 不一致 0 |
| sr (`S+0x98` / `this+0x60`) | 不一致 0 |
| `S+0x4a0` / `this+0x470` (0x200 B) | 不一致 0 |
| `S+0xa0` / `this+0x70` (0x200 B) | 591/600 call 不一致 (語 4417 個・相対差 >1e-3 は 389 語) |
| `S+0xca0` / `this+0xc70` (0x670 B) | 600/600 call 不一致 (語 1200 個・相対差 >1e-3 は 1200 語) |

- 不一致の先頭位置は、多くが `S+0xa0` 以降の数十バイト目 (例: `104`・`32`)。仮数部の下位ビット付近の差に見える。ただし判定基準 C5 は ulp 許容なしのため、不一致として記録する。
- 比較窓は `ks_filter_scen_cmp.py` (Filter 用) をそのまま使っている。VocalFilter の状態の配置 (`this+0x70..+0xf0` = DF2 状態 16 B × 8 の f64 ペア、KH 注記) は未検証で、窓の位置・順序が一致しているとは言えない。

## §4. 限界と未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| state 比較窓の確定 (VocalFilter の DF2 状態の配置・f64 ペアの順序で比べ直す) | state の 591/600 不一致が「実差」か「比較窓の誤り」か未判定 | 子 issue (起票先は §5) |
| 不一致の原因の機械語レベルの特定 (f64 ペアの丸め・順序) | 意味の同一性の判定ができない | 子 issue |

## §5. 受入条件への対応

- 受入 1 (KH param 写像の機械語読みで確定・根拠): 達成 (§2)。
- 受入 2 (同一 seed・N=200 の bit 一致の実測 C5): 実施済み。L/R は一致、state は不一致 (§3)。state の判定は窓の確定が前提のため未達。
- 受入 3 (REPORT_APPENDIX_FA45 の後続節に実測): 本付録に記載 (FA45 は smoke の訂正のみ、§6)。

## §6. FA-45 §5 の訂正

- FA-45 の smoke (`0x1808e1f30`) は deleting destructor を実行していた。`ERR 0・20 行 × 2`・fma 間で同一の結果は process の実行の証拠にならない。
- 本 PR で root を `0x1808e1fa0` に直し、smoke を再実行した (§3)。
