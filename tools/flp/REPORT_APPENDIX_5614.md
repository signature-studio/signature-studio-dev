# flp #5614: `0x737560` (+0x49e の setter) の実行時観測

親: #5376 / 前提: #5649 (PR #5652) / 受入 1 の子 (PY-5373)。本ファイルは #5614 の実測だけを扱う。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| cfg (`+0x49e`) の型 | 未達 | §4 (this の型は実測で決まらなかった) |
| `0x737560` の所属 VMT | 未達 | §4 (呼出し時の this の先頭 qword が .text を指し、VMT (.rdata) と読めない) |
| 呼出し元で `dl` に入る値 | 達成 (観測範囲) | §3。`dl` は 0 と 1 の 2 値。呼出し元 2 件のみ命中 |

## 2. 環境

- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開 (real 5.7 s・展開先 `$RUNNER_TEMP/fl-win64/extracted`・25,166 件)。
- 導入: `apt-get install wine64 gdb` (apt、rc=0)。`kernel.yama.ptrace_scope=0` (sudo sysctl)。
- インストール木: `tools/flp/s1_wine_probe.sh` (前回と同じ)。結果 `S1 rc=124` (120 s で終了せず GUI 継続)。real 2 m 13 s。
- ブレーク先の換算: FLEngine_x64.dll の ImageBase は `0x400000` (`FL64.exe` は `0x140000000`)。`0x737560` は FLEngine の VA なので、実行時は `FLEngine base + 0x337560` (base は `mapping PE file ... FLEngine_x64.dll` の行から取る)。前回の probe は FL64.exe の VA (`0x140006eaf`) を使っていたため、命中しなかった。

## 3. 命中と dl の値 (受入 3)

probe: `tools/flp/s10_setter_hit_probe.sh` (gdb `-x tools/flp/s10_setter_hit.gdb`)。

| 項目 | 値 |
|---|---|
| 命中 (gdb の break を 120 s 〜 200 s 継続) | 15,067 〜 15,069 回 (2 回の実行で同数程度) |
| `dl` (rdx の下位 8 bit) | `0x00` 12,280 回・`0x01` 2,787〜2,789 回 |
| 呼出し元 (戻り先) | `0x7aa6d107` (= VA `0x73d107`・直接 call 元 `0x73d102`) 14,957 回・`0x7aa6d2a7` (= VA `0x73d2a7`・直接 call 元 `0x73d2a2`) 110 回 |
| 静的解析との対応 | `tools/python/REPORT_PY388.md` §5b の直接 call 元 `0x73d102`・`0x73d2a2` と一致。`0x79fd44` は 1 回も命中しなかった |

`dl` の値ごとの呼出し元の内訳は、この取得 (`printf` の 1 行) では記録していない。`dl=0x00` と `dl=0x01` の両方が同じ 2 呼出し元から来たかは未確認。

## 4. cfg の型と VMT (受入 1・2 は未達)

- probe の取得: 命中時に `rcx` (this) の先頭 qword (vptr 候補)。
- 結果: vptr 候補は `0x7aa64d10` (= VA `0x734d10`・14,955 件) と `0x7aa65908` (= VA `0x735908`・110 件)。この 2 つは FLEngine の `.text` を指す (`pefile` の section 判定で確認)。
- 判定: C++ の VMT なら .rdata を指すはず。`.text` を指すことは、`rcx` が this でない (呼出し規約の前提違い)・あるいはオブジェクト先頭が vptr でないことを示す。よって VMT の所属はこの方法では確定しない。cfg の型も確定しない。
- 次に要るもの (未達の範囲): 呼出し元 (`0x73d102`・`0x73d2a2`) の `this` を、呼出し元のレジスタ (`0x73d0e0`・`0x73d280` の `rcx`) から逆に辿って採る。または `0x737560` の this が指すオブジェクトの生成元 (ctor) にブレークを張る。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| cfg (`+0x49e` のクラス) の型 | `+0x49e` の名前付け (REPORT_PY388 §5a) | #5614 (受入 1 の残り・部分達成のため open のまま) |
| `0x737560` の所属 VMT | 同上 | #5614 (同上) |
| `0x79fd44` 経由の呼出しの `dl` 値 | この観測では命中なし | #5614 (同上) |
| `dl=0x00`/`0x01` の呼出し元別の内訳 | 呼出し元ごとの値の分布 | #5614 (同上・取得 1 行の追加で可) |

## 6. 再現

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
sudo apt-get install -y wine64 gdb && sudo sysctl -w kernel.yama.ptrace_scope=0
FL_WIN64_DIR="$RUNNER_TEMP/fl-win64" bash tools/flp/s1_wine_probe.sh
WAIT_SEC=200 bash tools/flp/s10_setter_hit_probe.sh
```
