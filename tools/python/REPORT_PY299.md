# PY-299 (#4107): 効果関数 `0x1046a30` の負の key 群 9 枝の n 書込み先 (部分)

既知類型との関係: 該当なし (lift 作業ではない。PE の逆アセ解析)。親: #3282 (PY-181)・#3252 (PY-175)。前段: `tools/python/REPORT_PY181.md` §2 (表 2 の候補列挙)、`tools/python/REPORT_PY175.md` §5〜§6。

## 結論

- 確定 (式): 負の key 9 枝のうち `0x104b739` と `0x104bd22` は、n の格納先を store 命令の base・offset・添字の式まで確定した (下表 3・4)。
- 未確定: 残り 7 枝 (`0x104ae3d`・`0x104b1fd`・`0x104c2a6`・`0x104c4af`・`0x104c64f`・`0x104c919`・`0x104caae`) は、store の base の出所が global 経由の動的ポインタで、式まで確定していない。子 issue へ (下記 §5)。
- 注意: base の実アドレス (VA で書く値) は、global 変数の実行時の値に依存するため、PE の静的解析だけでは確定しない。本 REPORT は「式」まで確定し、実値は確定していない。

## 測定

- 測定 commit: `d61c577dc` (origin/main、PR #4115 merge 後)。解析コードは変更していない。
- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` の実在を確認。`extracted/block00031_PE.bin` (22,227,016 バイト) を展開。
- 実行 (全て終了 0):
  - `analysis/flapi/pe_disasm.py 1046a30 4700` → 4,679 行。
  - `analysis/flapi/pe_disasm.py <枝 VA> 400` (9 枝それぞれ)。
  - `analysis/flapi/pe_iat_name.py 4232e0,423980` → `EnterCriticalSection`・`LeaveCriticalSection` (thunk)。
- 差分の証跡 (`docs/WORKFLOW.md` §6): `git diff d61c577dc HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力は 0 行 (本 PR は解析コードを変えていない)。

## 1. 共通の構造

- `[rbp+0x570]` = key 下位 16bit 相当の値 (負の key 入口で正規化済み)。`[rbp+0x578]` = chan の添字、`[rbp+0x574]` = 副添字。
- 配列要素のアドレスは `base + ([rbp+0x578]·0x28f)·8` の形 (0x28f = 655)。
- `0x4232e0` (EnterCriticalSection) と `0x423980` (LeaveCriticalSection) は store の前後の lock/unlock。store 自体は lock 区間の中にある。

## 2. 枝 `0x104b739` (key − 0x70001fc0)

| 項目 | 内容 |
|---|---|
| 添字 | `[rbp+0x580] = key_low16 − 0x70001fc0` (`0x104b744`) |
| base | `[rbp+0x3c0] = [[rip+0x594ddf]] + ([rbp+0x578]·0x28f)·8` (`0x104b8ba`〜`0x104b8d3`)。global `[rip+0x594ddf]` の指す先は VA `0x15e06a0` (静的に確定) |
| store | `0x104b8fa`: `mov dword ptr [rax + rcx*4 + 0x384], edx` (`rax=[rbp+0x3c0]`、`rcx=[rbp+0x580]`、`edx=[rbp+0x5b8]` = n) |
| 確定した式 | `*(int32*)(base + 0x384 + (key_low16 − 0x70001fc0)·4) = n`。base は chan 配列要素 |
| 直前の lock | `0x104b8e1` で `EnterCriticalSection` (`[[rip+0x59845f]]` を引数) |
| 注記 | store 時の n は `[rbp+0x5b8]` の値。`0x104b843` で `0x10469f0` の戻り値を代入する経路 (`0x104b7f2` の flags `0x20` 分岐) と、`0x104b7f9` 以降の n を使う経路がある。どちらの経路で `0x104b8fa` に入るかは未確認 |

## 3. 枝 `0x104bd22` (key − 0x70001fd0)

| 項目 | 内容 |
|---|---|
| 添字 | `[rbp+0x580] = key_low16 − 0x70001fd0` (`0x104bd2d`)。`[rbp+0x568] = (rbp+0x580) & 0x80000007` の符号補正付き (`0x104bd39`〜`0x104bd49`)。0〜7 の値 |
| base | `[rbp+0x3a8] = [[rip+0x594763]] + ([rbp+0x578]·0x28f)·8` (`0x104bf36`〜`0x104bf4f`) |
| store | `0x104bf8f`: `mov dword ptr [rax + rcx*4], edx`。`rax = [rbp+0x3a8] + ([rbp+0x568]·17)·8 + 0x1d4`、`rcx = [rbp+0x580]`、`edx = [rbp+0x5b8]` = n (`0x104bf82`〜`0x104bf89`) |
| 確定した式 | `*(int32*)([rbp+0x3a8] + (k·17)·8 + 0x1d4 + (key_low16 − 0x70001fd0)·4) = n` (k = (key_low16 − 0x70001fd0) & 7 の符号補正値)。`[rbp+0x580]` と `[rbp+0x568]` の両方が key 由来で、同じ key の 2 つの添字 |
| 直前の lock | `0x104bf56` で `EnterCriticalSection` |

## 4. 残り 7 枝の状態 (未確定。子 issue へ)

| 枝 | 候補 store | 未確定の理由 |
|---|---|---|
| `0x104ae3d` | `0x104af7f` (`mov [rbp+0x5b8], ecx`) は n の再計算。`0x104b093`・`0x104b305` は別経路 | store 先が `[rbp+0x5b8]` (ローカル) で、外部への書込みは未確認 |
| `0x104b1fd` | `0x104b3bc` (`mov [rax], ecx`、`rax = [rbp+0x3d8]`)。`[rbp+0x3d8] = [rbp+0x3e0] + ([rbp+0x580])·8 + 0x394` (`0x104b37c`〜`0x104b392`)、`[rbp+0x3e0] = [[rip+0x5953d4]] + ([rbp+0x578]·0x28f)·8` (`0x104b2c5`〜`0x104b2de`) | 式は取れた (store 先の VA は global の実値が要る)。添字 `[rbp+0x580]` の上限は `0x104b2b0` の比較 (`cmp ecx, [[rip+0x596ee1]]`) で、上限の実値が未確定 |
| `0x104c2a6` | `0x104c335`・`0x104c3ca` (`mov [rax], ecx`)。`rax` は `0x4232e0` の戻り値 (lock 後の global) | 戻り値の global の実値が必要 |
| `0x104c4af` | 候補なし (`0x104c61b` 付近は関数呼出し) | 格納が呼出し先にある可能性。未確認 |
| `0x104c64f` | `0x104c6ea` (`mov [rax], ecx`)。`rax` は `[rip+0x59656c]` | global の実値が必要 |
| `0x104c919` | `0x104c9c0` (`mov [rax], ecx`)。`rax = [rip+0x595f0e]` | global の実値が必要 |
| `0x104caae` | 終端。`0x104cb89`・`0x104cc10` は `[rax+rcx*8]` の配列 push | n の格納ではなく終端処理 (REPORT_PY181 §3 と同じ) |

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 負の key の残り 7 枝 (`0x104ae3d`・`0x104b1fd`・`0x104c2a6`・`0x104c4af`・`0x104c64f`・`0x104c919`・`0x104caae`) の store 先の式 | 負の key の n の格納先の全量 | 子 issue (本 run で起票。番号は §6) |
| 上記の global ポインタ (`[rip+0x594f4f]`・`[rip+0x594763]`・`[rip+0x5953d4]`・`[rip+0x59656c]`・`[rip+0x595f0e]`) の実値 | 式を VA に落とせない | 同上 (初期化経路の追跡) |
| `0x104b1fd` の添字 `[rbp+0x580]` の上限 (`0x104b2b0` の比較) | 配列境界の確定 | 同上 |

## 6. 子 issue

- [PY-306] #4150: 負の key 群の残り 7 枝 (§4) の n 書込み先と、base の global 実値の確定。`親: #4107`。
