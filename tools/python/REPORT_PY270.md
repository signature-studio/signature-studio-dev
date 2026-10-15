# PY-270 (#3903): 0x12ac210 の第 4 引数 r9 (WheelDelta と推定) の発火側の探索 (未確定)

親: #3616 (PY-220)。前段: `tools/python/REPORT_PY203.md` §1 (0x12ab710 の r9d は 0x12ac210 の第 4 引数のまま)・§5 (未解決)。
既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセンブルによる解析)。

**受入条件は未達。** 発火側の呼出し元と r9 の出どころは確定していない。確定したのは「0x12ac210 への直接の参照が無い」ことと、
WM_MOUSEWHEEL の受取の連鎖の一部である。検証スクリプト `tools/python/analysis/flapi/pe_py220_methods.py` は main 取り込み (`a9afb18ec`) 後は存在し、
検証 HEAD で 11/11 PASS (issue 本文の 10 件と件数が違う。#3616 へ報告: https://github.com/signature-studio/signature-studio-dev/issues/3616#issuecomment-6185429594)。

## 0. 対象と前提

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` (2.3 GB、実在を確認) から `tar --zstd -xf ... --wildcards '*block00031_PE.bin'`
  で `$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin` を展開 (1.7 秒)。
- 検証起点 commit: `396f9f8b6` (着手時の origin/main)。測定 commit は §5。
- 逆アセは `pe_callgraph.py` の線形走査 (capstone)。VA は ImageBase `0x400000` 基準の絶対 VA。
- 限界: 線形走査の限界は PY-203 §0 と同じ。6 引数候補の判定は「直前 22 命令・同一関数内」の窓で行うため、
  窓より前で設定された引数は見逃す。候補の網羅性は保証しない。

## 1. 公開表のスロットと直接の参照

| 項目 | 結果 | 確認 |
|---|---|---|
| 8 バイト値 0x12ac210 の出現 (ファイル全体の生バイト走査) | 1 件 (VA 0x1279c35・`.text` 内) | `pe_py270_wheel_source.py` 1 |
| スロット直後の ShortString | 長さ 0x16、`TracksPanelMMouseWheel` | 同 2 |
| 同じ表の隣接エントリ | `FXViewModeSelectBeforePopup` (スロットから 0x80 バイト以内) | 同 3 |
| 0x12ac210 への直接 call (E8) | 0 件 | 同 4 |
| 0x12ac210 への RIP 相対参照 | 0 件 | 同 5 |
| 0x12ab710 への直接 call | 1 件 (0x12ac257、in 0x12ac210) | 同 6 |
| 0x12ac210 の内部で r9 への書込み | 0 件 (第 4 引数のまま、PY-203 §1 の続き) | 逆アセ (0x12ac210–0x12ac2ad) |

解釈 (推定): 0x12ac210 は公開表から名前で引かれ (RTL の MethodAddress 相当)、メソッドポインタに変換されてから
イベント用のフィールドへ入る。その格納は generic な経路で、0x12ac210 を直接指すコードは無い。
所属クラスが TFXForm であることは issue の記述による (本 REPORT では未確認)。

## 2. WM_MOUSEWHEEL の受取の連鎖 (確認できた範囲)

- **0x612aa0** (0x612c0d・0x612c48・0x612c59 はいずれも関数 0x612aa0 の内側): `cmp dword ptr [rsi], 0x20a` (0x612c0d)・`cmp eax, 0x20a` (0x612c48) で
  WM_MOUSEWHEEL を分岐し、`call 0x60c220` (0x612c59) を edx = msg、r8 = `[rsi+8]` (wParam)、r9 = `[rsi+0x10]` (lParam) で呼ぶ。
- **0x60c220** (25 命令): `[rbp+0x20]` = msg、`[rbp+0x28]` = wParam、`[rbp+0x30]` = lParam、`[rbp+0x38]` = 0 の記録を作り、
  `call qword ptr [rbx+0x80]` を rcx = `[rbx+0x88]`、rdx = 記録のアドレスで呼ぶ (TMessage 相当の仮想 dispatch。推定)。
- **0x60dc10**: `movzx rax, word ptr [rsi+8]` の `test ax, 0x40` で分岐し、`movsx rax, word ptr [rsi+0xa]` (WheelDelta) を
  float に換算する (呼出し先は未追跡)。WheelDelta は wParam の HIWORD (符号付き 16 bit) に当たる。

WheelDelta として読まれる `movsx ..., word ptr [reg+0xa]` は 11 箇所・9 関数 (`pe_py270_wheel_source.py` の 10 番目の検査):

| 読込み VA | 命令 | 所属関数 |
|---|---|---|
| 0x56f86d | movsx r9, word ptr [rdi+0xa] | 0x56f7d0 |
| 0x60dc34・0x60dc63 | movsx rax, word ptr [rsi+0xa] | 0x60dc10 |
| 0x67aac8 | movsx r10, word ptr [rax+0xa] | 0x67a9c0 |
| 0x67b01a | movsx r8, word ptr [rcx+0xa] | 0x67ad30 |
| 0x806010 | movsx r8, word ptr [rsi+0xa] | 0x805f60 |
| 0x820153 | movsx r8, word ptr [rsi+0xa] | 0x820110 |
| 0x85908d | movsx rbx, word ptr [rax+0xa] | 0x859060 |
| 0x8593ec・0x85942c | movsx rdx, word ptr [rax+0xa] | 0x8590c0 |
| 0xa0a510 | movsx rax, word ptr [rsi+0xa] | 0xa0a390 |

## 3. 発火側の候補の探索

0x12ac210 と同じ引数の形 (rdx = Sender、r8w = Shift、r9d = WheelDelta、スタック 5 番目 = MousePos のポインタ、6 番目 = `var Handled`)
の間接 call を探した。判定は「直前 22 命令内に、スタック 0x20・0x28 への書込みと lea があり、直前 22 命令内に movsx/movsxd で r9 を設定する命令がある」。
(0x6c99af は窓内の `movsxd r9` (dword 読込み) に掛かるが、call 時の r9 は `mov r9d, dword ptr [rdx+0x78]` で、WheelDelta ではない。)

| 条件 | 件数 | 結果 |
|---|---|---|
| 形の条件のみ (r9 の符号付き条件を外す) | 618 | 負の対照。条件の一部を外すと候補は大きく増える (条件が効いている) |
| 形 + r9 の符号付き読込み | 2 | 0x61fed9 (in 0x61fdb0) と 0x6c99af (in 0x6c9840) |
| 上の 2 件のうち WM_MOUSEWHEEL (0x20a) を含む関数 | 0 | 下で除外 |

- **0x61fed9 (in 0x61fdb0)**: 関数はマウスボタンのメッセージ (0x201・0x202・0x204・0x205 の比較) を振り分ける。
  r9 = `movsx r9, word ptr [rsi+0x10]` は X 座標 (lParam の LOWORD)。WheelDelta ではない。
- **0x6c99af (in 0x6c9840)**: `imul` でストライドを掛けて画素のアドレスを求める描画処理。WheelDelta ではない。
- **0x56f86d (in 0x56f7d0)**: r9 は WheelDelta の形 (`movsx r9, word ptr [rdi+0xa]`) だが、続く call 0x5666b0 (0x56f8a7) は
  直接 call で、引数は 10 個前後。6 引数のメソッドポインタの形ではない。0x5666b0 の内部には間接 call `call qword ptr [rbx+0x48]`
  (0x56691e) がある。ここが発火側である可能性は未検証 (次の一手)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x12ac210 を呼ぶ発火側 (メソッドポインタの call) の特定。0x60c220 の `[rbx+0x80]` の対象 (`[rbx+0x88]` のクラス) と、その Dispatch → DMT → WMMouseWheel 相当 → 発火の経路が未追跡。0x56f7d0・0x5666b0 の経路は未検証 | 受入 1 (r9 の出どころの確定) と受入 2 (WheelDelta の検証) が未達 | #3903 (Refs のため open のまま。次の run で継続) |
| `pe_py220_methods.py` の件数が issue 本文の 10 件と違う (検証 HEAD で 11/11 PASS) | 『10 件 PASS を保つ』の前提と件数が一致しない | #3616 (PY-220) へ報告済み: https://github.com/signature-studio/signature-studio-dev/issues/3616#issuecomment-6185429594 (件数の扱いは PM 判断) |
| 6 引数候補の窓 (22 命令) と線形走査の限界 | 候補の網羅性は保証されない | 親 #3476 への提案 (PY-203 §5 と同じ。未起票) |

## 5. 検証

- 測定 commit: `8e2540ebe` (プローブを追加した最後のコード commit)。
- 検証 HEAD: `d9417da68` (origin/main `a9afb18ec` を取り込んだ競合解消後のマージ commit)。以下の再測定は検証 HEAD で行った。
- `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/python/analysis/flapi/pe_py270_wheel_source.py` → 13/13 PASS・終了 0。
  検証 HEAD で所要 44.17 秒 (load average 1 分 0.37 → 0.71)。測定 commit `8e2540ebe` では n=3 で 24.14・24.67・24.82 秒、3 回の出力は一致。
- 前提の `pe_py203_probe.py` → 27/27 PASS・終了 0。検証 HEAD で所要 153.74 秒 (load 0.41 → 0.95)。PY-203 の結論は変えていない。
- 検証スクリプト `pe_py220_methods.py` → 11/11 PASS・終了 0・15.13 秒 (検証 HEAD)。issue 本文の 10 件とは件数が違う (#3616 へ報告)。
- 負の対照: 形の条件から r9 の符号付き条件を外すと 2 → 618 件 (スクリプトの判定 `loose`)。
- 差分 0 の証跡 (実行されるコード): `git diff 8e2540ebe HEAD -- tools/python/analysis/flapi/pe_py270_wheel_source.py tools/python/analysis/flapi/pe_callgraph.py` は 0 行。
  flapi 全体の `git diff 8e2540ebe HEAD -- tools/python/analysis/flapi` は 163 行で、main 由来の `pe_py220_methods.py` の追加 (163 insertions) のみ。

## 6. 次の一手 (推定・未検証)

1. 0x60c220 の `call qword ptr [rbx+0x80]` の対象を、`[rbx+0x88]` のクラスの VMT から特定する (`pe_vmt_probe.py` の使用)。
2. 0x56f7d0 → 0x5666b0 → 0x56691e (`call qword ptr [rbx+0x48]`) の引数の形を確かめる。
3. 上の 2 で発火側が見つかれば、r9 の出どころ (`movsx r9, [msg+0xa]` からの値の流れ) と Shift (r8w) の出どころを確定する。
