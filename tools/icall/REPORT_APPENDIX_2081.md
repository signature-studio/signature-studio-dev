# 付録: icall #2081 (ICALL-57) — SlateCore encoded 関数ポインタ表の範囲の静的解析

> 親: #2009 (ICALL-55)。前付録: `REPORT_APPENDIX_2009.md`・`REPORT_APPENDIX_1921.md`。
> 本 run は受入条件 1 (範囲と数) は**未達**。受入条件 2 (既知 12 slot の包含確認) は**部分達成**。

## 1. 結論

- 受入条件 1 (表の連続範囲 (開始・終了 VA) と entry 数): **未達**。静的解析では表の境界を決められなかった。
- 受入条件 2 (既知 12 slot が表に含まれるか): **部分達成**。下記 §3 の通り、12 slot はすべて zero-fill 部
  (`0x18128f400`〜`0x18130a000`) の参照として現れる。ただし「表に含まれる」の判定には表の境界が要るため未確定。
- 受入条件 3 (OTT の api-set 表 `0x18026c9f0` との形式比較): **未達**。形式 (cookie で encode・zero-fill) の一致は
  §2 で確認済みだが、表の範囲が確定していないため比較を閉じられない。
- 境界の確定には**実行時トレース** (decode 関数が読む slot の VA 列の採取) が必要。§5 に子 issue として切り出す。

## 2. 確認できたこと (SlateCore.core_64, image base 0x180000000)

| 項目 | 値 | 確認方法 |
|---|---|---|
| security cookie | VA `0x18125eaa8` | PE load config の `SecurityCookie` と一致 (1921 と同じ) |
| `.data` | VA `0x18125c000`〜`0x18130a000`・raw 末尾 `0x18128f400` | `pefile` |
| zero-fill 部 | `0x18128f400`〜`0x18130a000` (0x7ac00 bytes) | 同上 |
| decode 形式 | `mov r10,[cookie]` → `xor r10,[slot]` → `ror r10,cl` (cl = cookie & 0x3f) | `objdump -d -M intel` の `18103d3e3`〜`18103d3fd` |
| decode 関数の例 | `0x181055400`: cookie を読み `xor rbx,[0x1813068f8]` → `ror rbx,cl` → 戻り値 | `objdump` の `181055400`〜`181055421` |
| `ror ,cl` の総数 | 26 箇所 | `objdump` (`ror .*,cl$`) |
| cookie 参照の総数 | 5,241 箇所 | 大半は `mov rax,[cookie]` (スタック保護) |

- objdump の出力では RIP 相対参照先が `# 0x...` で出る。capstone の線形スイープは `.text` の途中で停止するため、
  この解析には使わない (`objdump` は約 2 秒で全 `.text` を読めた)。

## 3. 既知 12 slot の参照 (`objdump` 全文の RIP 相対参照)

`tools/icall/slatecore_fptr_table.py` (本 run で追加) の出力より。`decode=True` は「`ror ,cl` の直前 8 命令内に
その slot の `xor` がある」もの。

| slot | 参照数 | 命令種別 | decode の xor 直後の ror | 備考 |
|---|---:|---|:---:|---|
| `0x1813068d0` | 2 | mov (書込), xor | ✓ | encode 側 `18103d374` |
| `0x1813068f8` | 2 | mov (書込), xor | ✓ | encode 側 `1810553c8`・decode `181055400` |
| `0x181306900` | 2 | xchg, mov | | |
| `0x181306908` | 2 | mov, mov (書込) | | |
| `0x181306910` | 2 | cmp, mov (書込) | | |
| `0x1813072b0` | 4 | lea, mov, xor | ✓ | |
| `0x1813073f0` | 7 | and, mov | | |
| `0x1813073f8` | 2 | lea, mov | | |
| `0x181307400` | 2 | lea, mov | | |
| `0x181307408` | 3 | lea, mov, xor | ✓ | |
| `0x181307410` | 2 | lea, mov | | |
| `0x181307418` | 3 | mov, xor | ✓ (x2) | |

- 12 件のうち decode の xor が直接確認できたのは 5 件 (`0x1813068d0`・`0x1813068f8`・`0x1813072b0`・`0x181307408`・`0x181307418`)。
  残る 7 件は `lea`/`mov`/`cmp` のみで、decode 経路は別の間接参照 (表の添字アクセス) で読まれている可能性がある。
- `0x181306900`〜`0x181306910` の 3 件は `xchg`・`cmp`・書込で触られており、初期化・状態変数の可能性がある。

## 4. 表の境界を決められなかった理由

- zero-fill への RIP 相対参照先は 5,189 種ある (`slatecore_fptr_table.py`)。大半は `lea`・`mov` の
  グローバル変数・状態変数で、表の要素だけではない。
- 8 byte 単位で隣接する参照 (gap ≤ 0x40) を連結すると、144 個の小さなクラスタに割れた。表の要素が
  連続するなら 1 本の長いクラスタになるはずだが、そうはならなかった。
- 表の要素は RIP 相対参照ではなく **`[base + index*8]` の添字アクセス**で読まれている可能性が高い。
  その場合、静的な参照先列挙では表の範囲が見えない。
- したがって、範囲の確定には `decode 関数 (0x181055400 など)` が実行時に読む VA 列の採取が要る。

## 5. 残りの作業 (子 issue として起票)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| decode 関数の実行時トレースから、encoded slot の読み出し VA 列を採取し、表の開始・終了・entry 数を確定する | 受入条件 1・3 | #2120 (ICALL-59) |

## 6. 再現

```
objdump -d -M intel --no-show-raw-insn "<SlateCore.core_64>" > "$RUNNER_TEMP/sc_text.s"   # 約 2 秒
python3 tools/icall/slatecore_fptr_table.py "$RUNNER_TEMP/sc_text.s"
```

素材: `plugins-freshair` (`FA_DL=$RUNNER_TEMP/plugins-freshair bash tools/targets/freshair/fetch.sh` で
`work/win/Fresh Air/.../SlateCore.core_64` が出る)。`fl-win64` は本 appendix の解析では不要。
