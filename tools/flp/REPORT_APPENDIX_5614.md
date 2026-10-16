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
| 命中 (gdb の break・WAIT_SEC=200) | 8,066 回 (本 run の 1 実行。前回の 15,069 回とは実行ごとに数が変わる) |
| `dl` (rdx の下位 8 bit) | `0x00` 6,569 回・`0x01` 1,497 回 |
| 呼出し元 (戻り先) | `0x7aa6d107` (= VA `0x73d107`・直接 call 元 `0x73d102`) 8,043 回・`0x7aa6d2a7` (= VA `0x73d2a7`・直接 call 元 `0x73d2a2`) 23 回 |
| 静的解析との対応 | `tools/python/REPORT_PY388.md` §5b の直接 call 元 `0x73d102`・`0x73d2a2` と一致。`0x79fd44` は 1 回も命中しなかった |

**`dl` × 呼出し元の交差表** (本 run の `$RUNNER_TEMP/s10_gdb_session.txt` の `HIT` 行を集計。命中の合計 8,066):

| dl | 呼出し元 `0x73d102` (ret `0x7aa6d107`) | 呼出し元 `0x73d2a2` (ret `0x7aa6d2a7`) | 計 |
|---|---|---|---|
| `0x00` | 6,551 | 18 | 6,569 |
| `0x01` | 1,492 | 5 | 1,497 |
| 計 | 8,043 | 23 | 8,066 |

集計コマンド: `grep '^HIT ' s10_gdb_session.txt | sed -E 's/.*dl=(0x[0-9a-f]+).* ret=(0x[0-9a-f]+)/\1 \2/' | sort | uniq -c`。
`dl=0x00` と `dl=0x01` は両方の呼出し元から来る (`0x73d2a2` 経由は 0 と 1 の両方を含む)。

命中の件数は `WAIT_SEC` (gdb の打切り) と実行ごとの揺れで変わる。今回の 1 実行で、`dl` は 2 値・呼出し元は 2 件だった (前回の 2 実行も呼出し元は同じ 2 件)。

## 4. cfg の型と VMT (受入 1・2 は未達)

- probe の取得: 命中時に `rcx` (this) の先頭 qword (vptr 候補)。
- 結果: 命中時の `*rcx` (vptr 候補) の内訳 (本 run の `HIT` 行を集計): `0x7aa64d10` 8,041 件 (呼出し元 `0x73d102`)・`0x7aa65908` 23 件 (呼出し元 `0x73d2a2`)・`0x7b311e60` 1 件・`0x7b3121d8` 1 件 (どちらも呼出し元 `0x73d102`)。`0x7aa64d10`・`0x7aa65908` は FLEngine の `.text` を指す。`0x7b...` の 2 値は FLEngine の範囲外 (ImageBase `0x7a730000` の外)。
- 所属 section の確認 (`fl-install/FLEngine_x64.dll` に対し、`pefile` で `get_section_by_rva`。RVA = 実行時 VA − `0x7a730000`): `0x7aa64d10` (RVA `0x334d10`)・`0x7aa65908` (RVA `0x335908`)・`0x7aa6d107` (RVA `0x33d107`)・`0x7aa6d2a7` (RVA `0x33d2a7`)・`0x7aa67560` (RVA `0x337560`) は全て `.text` (Characteristics `0x60000020` = CODE・EXECUTE・READ)。`.rdata` (`0x40000040`) ではない。
- 確認コマンド: `python3 -c "import pefile; pe=pefile.PE('fl-install/FLEngine_x64.dll', fast_load=True); print(pe.get_section_by_rva(0x334d10).Name)"` (`fl-install` は `s1_wine_probe.sh` が組み立てる。`$RUNNER_TEMP` 配下)。
- 判定: C++ の VMT なら .rdata を指すはず。`.text` を指すことは、`rcx` が this でない (呼出し規約の前提違い)・あるいはオブジェクト先頭が vptr でないことを示す。よって VMT の所属はこの方法では確定しない。cfg の型も確定しない。
- 次に要るもの (未達の範囲): 呼出し元 (`0x73d102`・`0x73d2a2`) の `this` を、呼出し元のレジスタ (`0x73d0e0`・`0x73d280` の `rcx`) から逆に辿って採る。または `0x737560` の this が指すオブジェクトの生成元 (ctor) にブレークを張る。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| cfg (`+0x49e` のクラス) の型 | `+0x49e` の名前付け (REPORT_PY388 §5a) | #5614 (受入 1 の残り・部分達成のため open のまま) |
| `0x737560` の所属 VMT | 同上 | #5614 (同上) |
| `0x79fd44` 経由の呼出しの `dl` 値 | この観測では命中なし | #5614 (同上) |

## 6. 再現

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
sudo apt-get install -y wine64 gdb && sudo sysctl -w kernel.yama.ptrace_scope=0
bash tools/flp/s1_wine_probe.sh          # $RUNNER_TEMP/fl-win64/extracted を読み、$RUNNER_TEMP/fl-install を組む
WAIT_SEC=200 bash tools/flp/s10_setter_hit_probe.sh   # 出力: $RUNNER_TEMP/s10_gdb_session.txt
python3 -c "import pefile; pe=pefile.PE('$RUNNER_TEMP/fl-install/FLEngine_x64.dll', fast_load=True); print([pe.get_section_by_rva(r-0x7a730000).Name for r in (0x7aa64d10,0x7aa65908,0x7aa6d107,0x7aa6d2a7)])"
grep '^HIT ' "$RUNNER_TEMP/s10_gdb_session.txt" | sed -E 's/.*dl=(0x[0-9a-f]+).* ret=(0x[0-9a-f]+)/\1 \2/' | sort | uniq -c
```

測定 commit: `2e588bd3e` (コードを変えた最後の commit)。`git diff 2e588bd3e HEAD -- tools/flp ':!tools/flp/REPORT_APPENDIX_5614.md'` の出力は空 (コード差分 0。変わったのは本 REPORT だけ)。
