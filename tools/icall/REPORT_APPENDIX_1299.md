# 付録: icall #1299 (ICALL-25) — Fresh Air SlateCore の native 実行ハーネス

> 親: #1067 / #1026。本付録は ICALL-25 の部分達成 (受入条件 1 の一部) を記録する。wasm 化と native 差分 (受入条件 2・3) は未実施で、子 issue に残す。

## 1. 結論

- Fresh Air SlateCore (`SlateCore.core_64`) を、OTT 用ネイティブローダ `tools/ott/native/ott_native.c` で **ロードできる** (`ott_load` rc 0。ImageBase 0x180000000 が一致、IAT 252 件・DLL 7 個)。
- 新規 `tools/icall/diff/fa_nat.py` で任意 VA の関数を実機械語として呼べる。
- ただし **呼べるのは一部の関数のみ**。CRT 初期化 (DllMain・グローバル初期化) を走らせていないため、グローバル状態に依存する関数は SIGSEGV する。
- wasm 側との bit 比較は未実施。差分ゼロ / 非ゼロの件数は本 run では出していない。

## 2. 実測

測定 commit: `36ba67a6` (`tools/icall/diff/fa_nat.py` を追加した commit。以降は付録のみ)。素材: `plugins-freshair` を `$RUNNER_TEMP/plugins-freshair` に展開し `tools/targets/freshair/fetch.sh` で `work/win/Fresh Air/...SlateCore.core_64` を取得 (factory .epf 8 本・mac 0 件)。

| 試行 | 入力 | 結果 |
|---|---|---|
| `ott_load` (SlateCore) | パス指定 | rc 0 |
| `fa_nat.py 1803b3d10 --n 3` | xmm0 = 乱数 double, rcx..r9 = 乱数ヒープ 0x400 バイト | 3 件実行、rc 0 |
| `fa_nat.py 1803b3fc0 --n 3` | 同上 | SIGSEGV (rip が image 外 `0x7ffff7...`、関数ポインタ経由の未初期化 global 参照と見られる・未切り分け)、rc 95 |
| 引数 rcx=0 で `1803b3d10` | 作業履歴 (測定結果ではない)。初版 (ヒープ確保なし) | SIGSEGV addr=0x10、初版の入力を改修 |

### 3.1 差し戻し後の fix run (本 run の記録)

- 測定 commit: 本 run の fix commit (docstring のみの変更。実行コードの差分は無し)。
- 素材: 本 run は `fl-win64` のみ取得 (`$HOME/artifacts` に `fl-win64.tar.zst` のみ)。`plugins-freshair`・`toolchain-*`・`work-*` は無い。
- `tools/ott/native/build.sh` は OK (`work/libottnative.so` を生成)。
- `python3 tools/icall/diff/fa_nat.py 1803b3d10 --n 3` は `RuntimeError: ott_load failed -1` で rc 1 (DLL パス未指定・未展開のため)。
- 上記 §2 の rc 0 / 3 件出力 / SIGSEGV の再現は**この run では未実施**。次の run で `oc_artifacts` の素材を取得してから再測定する。

## 3. 未解決 (子 issue)

- wasm route (SlateCore closure の RetDec → icall 復元 → emcc) と native との xmm0 bit 比較。closure 範囲は既存の `tools/icall/work/fa_ranges.txt` (3,143 字) を使う想定 (本 run で再生成していない)。子 issue: #1451 (ICALL-28)。
- CRT 初期化 (SlateCore の `.data` / グローバル初期値の install) を native 側で再現しないと、グローバルを参照する関数は実行できない。OTT の `ott_native.c` は DllMain を走らせない方針。Fresh Air 側でも同じ前提が成立するかは未確認。
- 検証方法: `python3 tools/icall/diff/fa_nat.py <VA> --n N` (native のみ)。wasm との比較は未実装。
- 起票: #1451 (ICALL-28、親 #1299)。受入条件 2・3 と CRT 初期化の再現を含む。
