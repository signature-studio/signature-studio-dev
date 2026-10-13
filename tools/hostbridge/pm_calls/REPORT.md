# REPORT — HB-H18: Fruity Wrapper が呼ぶ PluginManager 機能の実測列挙 (#788)

## 0. 結論

- **Wrapper が PluginManager 由来の機能を呼ぶ証拠は、静的解析の範囲では 0 件**。PluginManager 固有文字列 0 件、PluginManager.exe / InterprocessPluginScan の import・起動痕跡 0 件。
- よって「列挙した機能の代替を実装する」対象は**空集合**。代替実装は作らない (推定で足さない)。
- 未確定: Wrapper の `CreateProcessW` 1 箇所の起動先 (引数が実行時組立のため静的には特定不能)。起動先が `ilbridge.exe` か別の exe かは未実測。
- 注意: HOSTBRIDGE.md §2.11 の「PluginManager 代替走査」は FLEngine 側 (`fle:0xabba70` 系、FL 本体が PluginManager を起動する経路) の話であり、Wrapper 由来ではない。FL 側の代替は本 REPORT の範囲外。

## 1. 数え方の定義

| 項目 | 定義 |
|---|---|
| PM 固有文字列 | `PluginManager` / `Plugin Manager` / `Plugin database` / `deepscan` / `vstpath` / `InterprocessPluginScan` / `-flcaption` の ASCII・UTF-16LE 出現数 (バイナリ全体) |
| 起動/ロード API 呼出 | `.text` 内で IAT の `CreateProcessW` / `ShellExecuteA` / `ShellExecuteW` / `ShellExecuteExW` / `CreateProcessA` / `WinExec` を指す `E8` (import thunk 経由) または `FF 15` (直接 IAT) の call 箇所数 |
| 陽性対照 | `block25160_PE.bin` (PluginManager.exe 本体)。PM 固有文字列が検出されなければ検出器は盲目 |

## 2. 実測 (`count_pm_calls.py`、FL win64 26.1.7.5653 の block 抽出)

| バイナリ | PM 固有文字列 | 起動/ロード API 呼出 |
|---|---|---|
| `block19091` Fruity Wrapper (Effects) | 0 件 | `CreateProcessW` 1 (0x74c9a5), `ShellExecuteA` 1 (0x69f093) |
| `block23676` Fruity Wrapper (Generators) | 0 件 | `CreateProcessW` 1 (0x74c9f5), `ShellExecuteA` 1 (0x69f0e3) |
| `block25160` PluginManager.exe (陽性対照) | `PluginManager` 3/1, `Plugin Manager` 5/3, `Plugin database` 6/4, `deepscan` 0/2, `vstpath` 0/2, `-flcaption` 0/2 | `CreateProcessW` 1, `ShellExecuteA` 1, `ShellExecuteW` 1 |

- Wrapper の 2 本とも `CreateProcessW` は `.text` の 1 箇所、引数は `[rsp+0x20..]` へ実行時に積まれる。
- `ShellExecuteA` の lpFile は定数 `charmap` (`0x69f0a0` 近傍の ASCII) を確認。PluginManager ではなく文字コード表ツールの起動。
- `CreateProcessW` の直前 lea 先は `PPPP...` 系の数値テーブル (`0x74c5b0`/`0x74c5c0`)。コマンドライン文字列の出所は未解決。
- `ilbridge` の UTF-16 文字列は Wrapper に存在する (`32bit\ilbridge.exe` / `64bit\ilbridge.exe`) が、`lea rip` で直接参照する箇所は見つからず (0 件)。実行時に組み立てられる可能性が高い。

## 3. 再現

```
python3 tools/hostbridge/pm_calls/count_pm_calls.py <block19091_PE.bin> <block23676_PE.bin> <block25160_PE.bin>
```

素材: `$HOME/artifacts/fl-win64.tar.zst` の `extracted/block19091_PE.bin` 等 (`tar --zstd -xf ... --wildcards 'extracted/block19091*'`)。依存: `pefile`。

## 4. 未解決

1. Wrapper `CreateProcessW` (0x74c9a5 / 0x74c9f5) の起動先の確定。動的解析 (Wine 等) が要る。起票先: 未起票。HB-H4 (#94) の「bridged 無効化・CreateProcessW fail-fast」受入で扱うのが妥当 (#94 へのコメントで依頼予定)。
2. Wrapper が PluginManager を名指しせず FL 本体経由で間接に呼ぶ経路の有無は、Wrapper 単体の解析では判定できない。FL 側 (`fle:0xabba70` 系) の解析範囲。起票先: 未起票 (#94 配下で扱う想定)。
