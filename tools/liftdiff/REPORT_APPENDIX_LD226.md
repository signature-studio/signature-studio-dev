# liftdiff REPORT 付録: LD-226 (#4590) sta_img にスタック復元を足すと効果が消える機構

親 #3384 (LD-155)。前提は `REPORT_APPENDIX_LD126.md` §3・§3.1 (sta_img で match 4 件、スタック復元 (`all`) で 0 件)。

測定 commit: **`7a9c41e56`** (コードを変えた最後の commit。`rt/ld_wasm.c` と `ld126_wasm_state.py`)。

## 結論

- 機構は**未特定**。受入条件は未達 (部分達成)。
- スタックを SP 基準で 3 区間に分けて、`sta_img` に足すと、深い区間 (`deep`)・SP 直下 128K の窓 (`win`) のどちらを足しても match 4 件は残る。**効果を消すのは、これらの区間ではない**。
- SP より上の区間 (`hi`) を足すと match が 0 件になるが、戻した差分が 587,202,032 B (8 MiB の stack より大きい) と異常で、**区間の計算か差分の数え方に誤りがある**。この結果は根拠にできない。原因は未特定 (下の未解決)。
- 戻しの証跡は取れた: RESET が返す `diff` (戻したバイト数) が 0 でない (`sta_img` の初回 RESET で 15,321,005 B)。`all` = `none` の一致の切り分けは未完 (§4)。

## 1. 測定条件

- 素材: `fl-win64` (`extracted/block00031_PE.bin`)・`work-liftdiff`・`work-m11`。`toolchain-emsdk` は runner 既存。
- wasm: `build_wasm.build(m11, False)`。`wasm_size` = 4464588 (前付録の 4459215 とはビルドの差がある)。
- 機: 4 vCPU・RAM 15 GiB。5 条件を同時に流した (`xargs -P 5`)。wall 241〜283 s。実行前の load 0.81〜1.28 (12:00 前後)。
- 対象: shard 1 の chunk 1 の対象件数は **17**。REPORT の 18 件と 1 件違う (`0x959a40` は chunk 1 に入るが、本測定の対象 aud 集合では 17 件として数えた。`0x44ec40`・`0x5d19e0` は chunk 1 の外)。件数の食い違いは未確認 (未解決)。

## 2. 方法

- `ld_w_snapshot` で、スタックを 3 区間に分けて複製する:
  - `deep` (mask 128): `[stack_end, SP−128K)`
  - `win` (mask 512): `[SP−128K, SP)` (case 開始時の 0 埋め窓)
  - `hi` (mask 256): `[SP, stack_base)`
- `sta_img` は mask 6 (sta + img)。`sta_img_deep`・`sta_img_win`・`sta_img_hi` は、それぞれ 6 に上の 1 区間を足した mask。`all` = 7 (従来どおり)。

## 3. 結果 (コミット済み HEAD・n=1・対象 17 件)

| 条件 | match | mismatch | RESET 差分の先頭 4 件 (B) |
|---|---|---|---|
| `sta_img` (6) | 4 | 13 | 15,321,005 / 39,744 / 9,659 / 193,698 |
| `sta_img_deep` (6+128) | 4 | 13 | 15,321,011 / 39,752 / 9,659 / 193,698 |
| `sta_img_win` (6+512) | 4 | 13 | 15,451,810 / 40,026 / 9,964 / 324,289 |
| `sta_img_hi` (6+256) | 0 | 17 | 587,202,032 (異常) |
| `all` (7) | 0 | 17 | 587,202,032 (異常) |

- match 4 件は `sta_img`・`deep`・`win` で同じ (`0x4bf600`・`0x50ab90`・`0x7850d0`・`0xb77200`)。全件の verdict は `results/ld226_sta_img_stack.tsv`。
- `hi` と `all` の差分が同じ 587,202,032 である点は、`hi` が `all` の効果の大半を担うことを示す可能性がある。ただし値が異常なので、現時点では解釈しない。

## 4. 読み取り

- スタック復元が効く部分は、SP より上 (`hi`) の可能性がある。ただし `hi` の差分量が異常で、区間の計算か差分の数え方に誤りがあるため、この読みは未確認。
- `deep` と `win` を足しても効果は消えない。このため「SP より深い死んだフレーム」と「case 開始時の 0 埋め窓」は、単独では効果を消さない。
- `all` = `none` の一致は未確認 (RESET の効きの証跡は、差分量が取れたことで一部確認した)。

## 5. 再現

```sh
export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
cd "$(git rev-parse --show-toplevel)/tools/liftdiff"
python3 -c "from ldlib import build_wasm as b; b.build(b.load_target('targets/m11.json'), False)"
printf '%s\n' sta_img sta_img_deep sta_img_hi sta_img_win all | xargs -P 5 -I{} sh -c 'python3 ld126_wasm_state.py --reset {} --out work/ld226/{}.jsonl > work/ld226/{}.log 2>&1'
```

- 生データは `work/ld226/` (gitignore)。集計 TSV `results/ld226_sta_img_stack.tsv` は、各 `work/ld226/<条件>.jsonl` の verdict と `.reset.json` の差分から作った (集計の手順は本付録の一時スクリプトで、repo には入れていない)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `hi` 区間の差分量 587 MB の原因 (区間の計算か差分の数え方の誤り。`ld_w_reset` の戻しが stack 外に及ぶ可能性) | `hi` 結果の信頼性・機構の特定 (受入条件) | #4801 (`[LD-240]`・子 issue。本 PR の範囲外) |
| 対象件数 17 と REPORT の 18 の食い違い | 対象集合の確定 | #3384 (LD-155) |
| n=2 反復 | 結論の再現性 | #3384 (LD-155) |
