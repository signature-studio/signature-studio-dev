# flp #5614: `0x737560` (+0x49e の setter) の実行時観測

親: #5376 / 前提: #5649 (PR #5652) / 受入 1 の子 (PY-5373)。本ファイルは #5614 の実測だけを扱う。

## 1. 受入の状況

| 受入 | 結果 | 根拠 |
|---|---|---|
| cfg (`+0x49e`) の型 | 未達 | §4 (this の型は実測で決まらなかった) |
| `0x737560` の所属 VMT | 未達 | §4 (呼出し時の this の先頭 qword が .text を指し、VMT (.rdata) と読めない) |
| 呼出し元で `dl` に入る値 | 達成 (観測範囲) | §3。`dl` は 0 と 1 の 2 値。呼出し元 2 件のみ命中 |

## 2. 環境

- 素材: `fl-win64.tar.zst` を `tar --zstd -xf` で展開 (real 7.3 s・展開先 `$RUNNER_TEMP/fl-win64/extracted`・エントリ 25,166 件)。
- 導入: `apt-get install wine64 gdb xvfb` (apt、rc=0。wine64 は `/usr/lib/wine/wine64` に入る)。`kernel.yama.ptrace_scope=0` (sudo sysctl)。
- インストール木: `tools/flp/s1_wine_probe.sh` (前回と同じ)。結果 `S1 rc=124` (120 s で終了せず GUI 継続)・`MSGBOX_OnInit=0`・`native-load=0`。real 2 m 6.6 s。
- S10: `WAIT_SEC=200 bash tools/flp/s10_setter_hit_probe.sh` を foreground で実行。real 3 m 21.3 s・gdb rc=124 (打切り)・`flengine_base=0x7a730000`・`Breakpoint 1 at 0x7aa67560`・hits=15,069。命中数は §3。
- S11: `WAIT_SEC=200 bash tools/flp/s11_setter_obj_probe.sh` を foreground で実行。real 3 m 21.2 s・hits=15,045。gdb の rc は未取得 (出力の tail で切れた)。数値は §6。
- ブレーク先の換算: FLEngine_x64.dll の ImageBase は `0x400000` (`FL64.exe` は `0x140000000`)。`0x737560` は FLEngine の VA なので、実行時は `FLEngine base + 0x337560` (base は `mapping PE file ... FLEngine_x64.dll` の行から取る)。前回の probe は FL64.exe の VA (`0x140006eaf`) を使っていたため、命中しなかった。

## 3. 命中と dl の値 (受入 3)

probe: `tools/flp/s10_setter_hit_probe.sh` (gdb `-x tools/flp/s10_setter_hit.gdb`)。

| 項目 | 値 |
|---|---|
| 命中 (gdb の break・WAIT_SEC=200) | 15,069 回 (本 run の 1 実行。命中数は実行ごとに変わる) |
| `dl` (rdx の下位 8 bit) | `0x00` 12,280 回・`0x01` 2,789 回 |
| 呼出し元 (戻り先) | `0x7aa6d107` (= VA `0x73d107`・直接 call 元 `0x73d102`) 14,959 回・`0x7aa6d2a7` (= VA `0x73d2a7`・直接 call 元 `0x73d2a2`) 110 回 |
| 静的解析との対応 | `tools/python/REPORT_PY388.md` §5b の直接 call 元 `0x73d102`・`0x73d2a2` と一致。`0x79fd44` は 1 回も命中しなかった |

**`dl` × 呼出し元の交差表** (本 run の `$RUNNER_TEMP/s10_gdb_session.txt` の `HIT` 行を集計。命中の合計 15,069):

| dl | 呼出し元 `0x73d102` (ret `0x7aa6d107`) | 呼出し元 `0x73d2a2` (ret `0x7aa6d2a7`) | 計 |
|---|---|---|---|
| `0x00` | 12,240 | 40 | 12,280 |
| `0x01` | 2,719 | 70 | 2,789 |
| 計 | 14,959 | 110 | 15,069 |

集計コマンド: `grep '^HIT ' s10_gdb_session.txt | sed -E 's/.*dl=(0x[0-9a-f]+).* ret=0x0*([0-9a-f]+)$/\1 \2/' | sort | uniq -c`。
`dl=0x00` と `dl=0x01` は両方の呼出し元から来る。

命中の件数は `WAIT_SEC` (gdb の打切り) と実行ごとの揺れで変わる。今回の 1 実行で、`dl` は 2 値・呼出し元は 2 件だった。

## 4. cfg の型と VMT (受入 1・2 は未達)

- probe の取得: 命中時に `rcx` (this) の先頭 qword (vptr 候補)。
- 結果: 命中時の `*rcx` (vptr 候補) の内訳 (本 run の S10 の `HIT` 行を集計): `0x7aa64d10` 14,957 件・`0x7aa65908` 110 件・`0x7b311e60` 1 件・`0x7b3121d8` 1 件。`0x7aa64d10`・`0x7aa65908` は FLEngine の `.text` を指す。`0x7b...` の 2 値は FLEngine の範囲外 (ImageBase `0x7a730000` の外)。
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

## 6. 追加実測 (s11: 命中時の this 周辺ダンプ)

probe: `tools/flp/s11_setter_obj_probe.sh` (gdb `-x tools/flp/s11_setter_obj.gdb`)。命中時に `x/10gx $rcx-0x20` で this 周辺と戻り先を出し、先頭 40 件だけダンプする。

| 項目 | 値 |
|---|---|
| 命中 (WAIT_SEC=200・real 3 m 21.2 s・gdb rc=124) | 15,045 回 (`hits=15045`) |
| `dl` (先頭 19 件) | 19 件すべて `0x01` |
| 戻り先 (先頭 40 件) | `0x7aa6d2a7` 39 件・`0x7aa6d107` 1 件 |
| `rcx` (this) (先頭 40 件) | `0x02c7c170`〜`0x03548120` (ヒープ。FLEngine の .text 外) |
| 先頭 qword (`*rcx`・先頭 40 件) | `0x7aa65908` 39 件・`0x7aa64d10` 1 件 |
| 先頭 qword の所属 | `.text` (RVA `0x335908`・`0x334d10`)。`.rdata` ではない |

判定: 命中時の this の先頭は .text のアドレスを指す。§4 と同じく .rdata の VMT としては読めない。この観測だけでは cfg の型と所属 VMT は確定しない。`*rcx` の指す先を逆アセンブルするか、this を生成する ctor (new の戻り) にブレークを張るのが次の手。

測定 commit: `29f45c13b` (本 run の HEAD。`tools/flp` のコードは `64ac5dc19` と同一)。
probe の 1 行 (s11 の結果 `hits`) は `grep -c '^HIT ' "$RUNNER_TEMP/s11_gdb_session.txt"` で再現できる。

## 7. 再現

```sh
mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
sudo apt-get install -y wine64 gdb xvfb && sudo sysctl -w kernel.yama.ptrace_scope=0
bash tools/flp/s1_wine_probe.sh          # $RUNNER_TEMP/fl-win64/extracted を読み、$RUNNER_TEMP/fl-install を組む
WAIT_SEC=200 bash tools/flp/s10_setter_hit_probe.sh   # 出力: $RUNNER_TEMP/s10_gdb_session.txt
WAIT_SEC=200 bash tools/flp/s11_setter_obj_probe.sh   # 出力: $RUNNER_TEMP/s11_gdb_session.txt
python3 -c "import pefile; pe=pefile.PE('$RUNNER_TEMP/fl-install/FLEngine_x64.dll', fast_load=True); print([pe.get_section_by_rva(r-0x7a730000).Name for r in (0x7aa64d10,0x7aa65908,0x7aa6d107,0x7aa6d2a7)])"
grep '^HIT ' "$RUNNER_TEMP/s10_gdb_session.txt" | sed -E 's/.*dl=(0x[0-9a-f]+).* ret=0x0*([0-9a-f]+)$/\1 \2/' | sort | uniq -c
```

測定 commit: `29f45c13b` (コードを変えた最後の commit は `64ac5dc19`。両者の `tools/flp` (本 REPORT を除く) は同一)。
