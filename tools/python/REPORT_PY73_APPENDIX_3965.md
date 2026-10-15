# PY-278 付録 (#3965): 0xfff070・0xd1af20・0x1262970 の間接呼出し元 (親 #3649)

親: #3649 (PY-283)。前段: `tools/python/REPORT_PY73_APPENDIX_3649.md` §1-1・§1-2・§3-3。本体: `tools/python/REPORT_PY73.md` §8-3。
既知類型との関係: 該当なし (lift 作業ではない。逆アセンブルと格納先の逆引き)。
実装: 0 件 (`provider/`・`host/`・`tests/` は未変更)。製品 KPI: 対象外 (起動・GUI に関わらない解析)。

## 結論

- **3649 付録 §1-2 の「`0xd1af20` の関数ポインタ格納 0 件」は誤りだった。** `0xd1af20` は `lea rax, [rip+disp]` で 2 箇所 (`0xd16123`・`0xd16163`) から参照され、コールバック用の構造体 (`[rbp+0x30]`・`[rdx+0x30]`) に格納されて `0x526190` に渡される。直接 call 0 件・末尾 jmp 0 件は正しいが、この経路で関数に届く。
- **`0xfff070` は関数ポインタ表 `0xfe2c80`〜`0xfe2ea0` の 57 番目 (`0xfe2e48`) にだけ格納される。** 表を指す RIP 相対参照・絶対参照は 0 件。PE 全体の 8 byte LE 走査でも `.text+0xbe2e48` の 1 箇所だけ。表を読む呼出し元は未特定。
- **`0x1262970` は `V = 0x125b1c0` の vtable の +0x60 (`0x125b220`) にだけ格納される。** PE 全体の走査で `.text+0xe5b220` の 1 箇所。`[reg+0x60]` の間接 call 517 件のうち、どのオブジェクトの vtable かは未特定。
- **`0xd1af20` の呼出し元の確定は子へ。** 格納先の構造体を受け取る `0x526190` の呼出し元は 17 箇所 (14 関数) で、うち `0xd160b7`・`0xd16136`・`0xd16176` は `0xd16080`・`0xd160e0` の内側。その上流は未追跡。

## 測定

- 素材: `$ARTIFACTS_DIR/fl-win64.tar.zst` を `tar --zstd -xf --wildcards '*block00031_PE.bin'` で `work/extracted/` に展開 (22,227,016 B・1.66 秒)。
- 新規スクリプト: `tools/python/analysis/flapi/pe_py278_indirect_probe.py` (rip・abs・raw の 3 検査)。
- 再現: `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/pe_py278_indirect_probe.py`。実測 96.4 秒 (real)・並列 1。
- 既存の検査 `pe_flag_scope_check.py` の再現も実施: 21.4 秒・出力は 3649 付録 §1・§3 と一致 (0/12 到達・517・333)。
- 測定 commit: 本付録と `pe_py278_indirect_probe.py` を入れた commit (コードを変えた最後の commit)。

## 1. 格納による間接参照 (PE 全体の逆引き)

| 対象 VA | 参照の種類 | 格納・参照箇所 (RVA) | 件数 |
|---|---|---|---|
| `0xd1af20` | `lea` (RIP 相対) → 構造体へ格納 | `0xd16123` (`[rbp+0x30]`)・`0xd16163` (`[rdx+0x30]`) | 2 |
| `0xd1af20` | PE 全体の 8 byte 格納 | なし | 0 |
| `0xfff070` | 8 byte 格納 (関数ポインタ表) | `.text+0xbe2e48` (表 `0xfe2c80` の 57 番目) | 1 |
| `0x1262970` | 8 byte 格納 (vtable) | `.text+0xe5b220` (`V+0x60`) | 1 |

- `0xfff070` の表 `0xfe2c80`〜`0xfe2ea0` は `.text` 内・RVA 0xfe2c80。表への RIP 相対参照・絶対参照は 0 件 (`pe_py278_indirect_probe.py` の rip・abs 検査)。表を使う呼出しは静的に追えない。
- `0x1262970` の vtable `V = 0x125b1c0` の格納箇所は 2 件 (`.text+0xe5b0f8`・`.text+0xe5b2d0`) で、`V+0x60` は `0x125b220` (`.text+0xe5b220`) のみ。

## 2. `0xd1af20` の格納文脈 (確定)

```
0xd16118  mov rax, [rip+0x9a2cf9]   ; 値 (前段で得た値)
0xd1611f  mov [rbp+0x38], rax
0xd16123  lea rax, [rip+0x4df6]     ; = 0xd1af20
0xd1612a  mov [rbp+0x30], rax       ; 構造体 +0x30 に関数ポインタ
0xd1612e  mov rcx, [rbp+0x50]
0xd16132  lea rdx, [rbp+0x30]       ; 構造体の先頭を第 2 引数に
0xd16136  call 0x526190
```

```
0xd16158  mov rax, [rip+0x9a2cb9]
0xd1615f  mov [rdx+0x38], rax
0xd16163  lea rax, [rip+0x4db6]     ; = 0xd1af20
0xd1616a  mov [rdx+0x30], rax
0xd16172  lea rdx, [rdx+0x30]
0xd16176  call 0x526190
```

- `0x526190` は `[rbp+0x30]` 側の構造体を `0x415610`・`0x525380`・`0x525ec0`・`0x415c30` に渡す (逆アセンブル `0x526190`〜`0x5261f9`)。その中で `0xd1af20` が呼ばれるかどうかは未確定 (`0x525380`・`0x525ec0` の中を未読)。
- `0xd16123` の属する関数 (`func` 推定 `0xd160e0`) の直接呼出し元は 0 件。`0xd16150` (2 つ目の入口) の直接呼出し元も 0 件。

## 3. 未確定 (子 issue へ)

- `0xfff070` の表 `0xfe2c80` を読む呼出し元 (表のインデックス計算を含む)。
- `0x1262970` (vt+0x60) を呼ぶオブジェクトのクラス。`[reg+0x60]` 517 件の中で、`V` (= `0x125b1c0`) を指すオブジェクトに限った絞り込み。
- `0xd1af20` を呼ぶ `0x526190` 配下の経路 (`0x525380`・`0x525ec0` の中身)。
- 書込み 18 件のゲート (`0xd5c858`) との前後判定。

## 差分 0 の証跡

- 測定 commit: 本付録と probe を入れた commit (下の「測定 commit」に記載の hash)。
- 差分は `git diff <測定 commit> HEAD -- tools/python/analysis tools/python/provider tools/python/host tools/python/tests` の出力 (0 行を期待)。commit 後に記入する。

## 4. 受入条件の判定

- [ ] `0xfff070`・`0xd1af20`・`0x1262970` の呼出し元 (間接経路を含む) を PE 解析箇所つきで残す → **部分**。格納箇所と `0xd1af20` の構造体経路は §1・§2 に残した。呼出し元の確定は §3 (子)。
- [ ] 書込み 18 件のゲート前後判定 → **未** (子)。
- [x] 推測の状態モデルでは実装しない (provider・mock は未変更)。
