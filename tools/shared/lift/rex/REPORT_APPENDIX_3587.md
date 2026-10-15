# tools/shared/lift/rex 付録 — REPORT §11 (T-SH-88 / #3587)

## 11. REXGetInfo (fn=1) の成功経路 (戻り値 1) の arena 書込の一致 — T-SH-88 (#3587, 部分達成)

測定 commit: `142df3b53` (`tools/shared/lift/rex/` の最後のコード変更。`main` 取り込みの merge)。前回測定 `92b617bdf` の後に main の rex 変更 (#3588 の `native_ref.c`・`crash_class.py` 等) が入ったため再測定した。以降の差分は本付録と REPORT のみ (差分 0 の証跡は §11.8)。
既知類型との関係: 該当なし (不一致 0)。

### 11.1 結論 (1 行)
REXGetInfo の成功経路 (戻り値 1) に入る fn=1 の入力 48 件を追加し、arena 書込を含めて元の機械語と全バイト一致した (比較 223 件・不一致 0)。**`.data` への書込は、REXGetInfo / REXGetCreatorInfo の閉包からは到達せず、比較した 223 件すべてで 0 件**。受入 2 の `.data` 部分は未達で、子 #3850 (T-SH-92) に移した。

### 11.2 方法
- 入力 (`gen_cases.py` の末尾 SUCC1 = 48 件・seed 3587・fn=1): REXGetInfo wrapper (0x1130) は 0x1380 で ctx 大域 (RVA 0x49e08) を取り、0x2080 へ tail jump する。0x2080 は (1) 0x1de0 が真 (ctx+0x20 の連結リストを key = key_of(a0) で探す)、(2) a2 ≠ NULL、(3) a1 ≥ 0x20 の順に通ると、O = key_of(a0) を基に出力を書いて戻り値 1 を返す。
- a0 = key_of(OBJ) (key_of は対合)。ノードの key = OBJ。O+0x630 = S、O+0x690 = B、O+0x20 = Z。OBJ・S・B・Z の各 0x700 バイトは dword 1 で埋め、ポインタ項目だけ有効なアドレスに向ける。B+0x62c = 0 (0x4500 が 1 を返す)。ctx+8 = ロック構造 LK (0x16030 が `[[ctx+8]]` を読む)。S+4 は 0x21a1 の jump table の入力 (1 / 8 / 9 / 0x10 / 0x14 / 0x16 / 0x18 / 0x20 から選ぶ)。a1 ∈ {0x20, 0x23, 0x24, 0x100, 0x7ff}。a2 は a1 バイトが arena 内に収まる位置。
- 作り方: 最初は NULL 参照 (0x16039: ctx+8 が 0) → 0x18186 (B+0x62c ≠ 0 で 0x18180 へ進み、dword 1 をポインタとして読む) → 0x1788f (0x4324 経由の除数 = B+0x5ec が 0)。各段で、落ちた RIP を出す一時版の native 参照 (リポジトリ外・未コミット) で特定し、該当フィールドを設定した。

### 11.3 実測 (測定 commit `142df3b53`・`bash tools/shared/lift/rex/lift_x64c.sh all` を 3 回。wasm は上流 emsdk 6.0.12 (`tools/m1/flags.sh` の pin) を `$RUNNER_TEMP` に入れて `EMSDK_ENV` で指定。`toolchain-emsdk` 素材は本 run に無い)
| 項目 | 値 |
|---|---|
| 本検査 `ok` | PASS (3 回とも)。cases 296 (通常 200 + 成功経路 48 + fn=1 成功経路 48)・比較 223・一致 223・不一致 0・除外 73 (SIGSEGV/SIGBUS 72・SIGALRM 1) |
| 戻り値の分布 (比較対象) | 0x1 (成功) 77 (従来 29 + 新規 48 = 全 48 件が成功) / 0x3 13 / 0xca 44 / 0xcb 48 / 0xcc 41 |
| 書込 (比較対象) | arena 書込 90 件 (従来 42 + 新規 48・全件一致)・`.data` 書込 0 件 |
| ネガコン | neg-cmp: 不一致 1 件 → FAIL / neg-ctx: 223 件不一致 → FAIL / neg-owner: FAIL (いずれも期待どおり) |
| `all` の wall / rc | 12.59 / 12.55 / 12.21 s / rc 0 (3 回とも `ALL OK`) |
| 各 mode の elapsed | ok 3〜4 s・neg-cmp 3 s・neg-ctx 3〜4 s・neg-owner 3 s |
| load (1 分値) | `all` の開始 0.30〜0.45、終了 0.41〜0.57 (nproc 4) |

### 11.4 `.data` の調査 (受入 2 の `.data` 部分)
- 静的 (`tools/shared/lift/rex/rex_closure.py --json` の出力。直接 call と関数外への直接 jmp の閉包。関数境界は `.pdata`、無い領域は次の `.pdata` 先頭まで近似): REXGetInfo (0x1130) の閉包は 39 関数 (うち近似 27・命令 1238)、REXGetCreatorInfo (0x11c0) の閉包は 22 関数 (うち近似 12・命令 924)。関数数は閉包で到達した関数入口の数。両閉包から `.data` (RVA 0x47000〜0x621d8) への rip 相対の書込は到達しない。**限界**: REXGetInfo の閉包には間接 `jmp rcx` が 1 件あり (0x21bc。§11.2 の 0x21a1 の jump table 分岐)、その先は辿っていない。したがって「閉包から書込が無い」は、この分岐の先を含まない静的な結論 (下限側)。分岐先の動的な確認は比較 223 件 (下の動的) のみ。
- 閉包の走査で出た書込候補 (`mov [rip+X], rcx` at 0x1c9dc・0x1f4a8) は、`int3` の後ろにある独立の stub で、直接呼出は 0x1facd・0x1fadd (関数 0x1fabc) だけ。
- 0x1fabc の直接呼出元は 0x22636 (関数 0x22630・初期化系)。0x22630 の直接呼出元は 0x1fb44 (関数 0x1fb24)。0x1fb24 は 0x1fc60 から呼ばれ、0x1fc60 は DllMain (PE の AddressOfEntryPoint = 0x1fd78) から `edx` (理由) を渡して呼ばれる。0x1fb24 は `edx == 1` (DLL_PROCESS_ATTACH) の経路で 0x22630 (初期化) を呼ぶ。つまり `.data` への書込は DllMain の読込時初期化で起きる。harness は export だけを呼ぶので、この経路は通らない。
- 動的: 比較した 223 件のすべてで、`.data` (ctx 大域を除く) は native・wasm とも初期値のまま (`writes data=0`)。`.data` の全バイト比較は毎 case で実施している。比較値が初期値のままなので、`.data` に書く経路の一致は検証していない。

### 11.5 検証範囲 / 範囲外
- 検証した: fn=1 成功経路 (戻り値 1) の arena 書込 (48 件) の全バイト一致 (native と wasm)、ネガコン 3 件の FAIL、比較対象の全件で `.data` が不変なこと。
- 範囲外: `.data` 書込を伴う経路 (0x22630 系) の到達元の特定と比較 (子 #3850)。中核閉包 (#2734)。落ちる case の分類 (#3588)。movnti (#3589)。side module 化 (#2896)。

### 11.6 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.data` へ書く経路 (0x1c9dc・0x1f4a8 の stub) の到達元と、その経路を通る入力での `.data` 全バイト比較。REXGetInfo 閉包の間接 jmp (0x21bc) の先の静的な列挙を含む | 受入 2 の `.data` 部分が未検証。閉包の書込なしは下限側の結論 | #3850 (T-SH-92・親: #3587) |
| 落ちる case 73 件のうち未分類 37 件 | 比較数 223/296 | #3588 (T-SH-89) |
| movnti 24 箇所の到達 | 到達すると fail-fast。x64c 対応の要否は未決 | #3589 (T-SH-90) |
| side module 化 (dlopen 形) | `REX_SIDE` の配信形式が未決 | #3630 (T-SH-91) |

### 11.7 再現
```
FL_WIN64_DIR=<fl-win64 展開先> EMSDK_ENV=<emsdk_env.sh> bash tools/shared/lift/rex/lift_x64c.sh all
FL_WIN64_DIR=<fl-win64 展開先> python3 tools/shared/lift/rex/rex_closure.py --json OUT.json   # §11.4 の閉包数
```
`<fl-win64 展開先>` は `extracted/block24351_PE.bin` を含むディレクトリ (`tar --zstd -xf fl-win64.tar.zst -C <dir> extracted/block24351_PE.bin`)。`<emsdk_env.sh>` は `toolchain-emsdk` の展開先、無ければ上流 `emsdk install 6.0.12` の `emsdk_env.sh`。生成物は `tools/shared/work/lift/rex/` (gitignore)。

### 11.8 測定後のコード差分 (差分 0 の証跡)
`git diff 142df3b53 HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (0 = コード差分なし。以降は本付録と REPORT の文言のみ)。
