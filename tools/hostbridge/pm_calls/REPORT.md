# REPORT — HB-H18: Fruity Wrapper が呼ぶ PluginManager 機能の実測列挙 (#788)

## 0. 結論

- **Wrapper が PluginManager 由来の機能を呼ぶ証拠は、静的解析の範囲では 0 件**。PluginManager 固有文字列 0 件。PluginManager.exe / InterprocessPluginScan は静的文字列・import 上 0 件 (CreateProcessW の対象は未確定のため起動の有無は未判定)。
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
- `CreateProcessW` (0x74c9a5) の引数 (Capstone で rcx/rdx/r8/r9 の代入を追跡・Generators 0x74c9f5 も同形): `lpApplicationName` (rcx) = 0 (`xor ecx,ecx`)。`lpCommandLine` (rdx) は `0x413840` の戻り値。`0x413840` は引数 (rcx) が非 0 ならそれを返し、0 ならグローバル変数の値 + 0x10 を返す。rcx の `[rbp+0x78]` に入る値を `0x413d90` が設定する経路は未追跡 (この関数の内部までは見ていない)。`0x413d90` の第 5 引数 (スタック) は関数引数 `[rbp+0x60]`。直前の `lea` はスタック上 (`[rbp+0x98]`・`[rbp+0x80]`) を指す。
- `.text` に `0x74c5b0` / `0x74c5c0` を指す `lea rip` 参照は 0 件 (全 `.text` を Capstone で走査)。両アドレスの中身は `ff 25 ...` (`jmp [IAT]`) の thunk で、数値テーブルではない。`0x413d90` 直前の `lea r9` 先は `0x74ca24` (`.text` 内の 4 byte 定数 `0x20` + 次関数のプロローグ)。
- よって `lpCommandLine` は定数に解決できず、この関数の引数由来で呼出元が組み立てる。コマンドラインの内容は未解決。
- `ilbridge` の UTF-16 文字列は Wrapper に存在する (`32bit\ilbridge.exe` / `64bit\ilbridge.exe`) が、`lea rip` で直接参照する箇所は見つからず (0 件)。実行時に組み立てられる可能性が高い。

## 3. 再現

```
python3 tools/hostbridge/pm_calls/count_pm_calls.py <block19091_PE.bin> <block23676_PE.bin> <block25160_PE.bin>
```

素材: `$HOME/artifacts/fl-win64.tar.zst` の `extracted/block19091_PE.bin` 等 (`tar --zstd -xf ... --wildcards 'extracted/block19091*'`)。依存: `pefile`。

## 4. 未解決

1. Wrapper `CreateProcessW` (0x74c9a5 / 0x74c9f5) の起動先の確定。`lpCommandLine` は呼出元で組み立てられ静的には確定しない。動的解析 (Wine 等) が要る。起票先: #94 (HB-H4) へのコメント https://github.com/signature-studio/signature-studio-dev/issues/94#issuecomment-6149376030 (項目 1)。
2. Wrapper が PluginManager を名指しせず FL 本体経由で間接に呼ぶ経路の有無は、Wrapper 単体の解析では判定できない。FL 側 (`fle:0xabba70` 系) の解析範囲。起票先: 同コメント (項目 2)。
