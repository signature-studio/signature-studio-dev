# M1: 極小 PE→wasm PoC の E2E 自動化

戦略文書 (`/home/ubuntu/work/analysis/strategy.md`) §4 M1 / §2.1 パイプラインの検証条件を満たすため、
toolchain_setup.md の E2E 実証 (`/opt/_test/`) を **1 本のスクリプトで再生産可能** にしたもの。

## 使い方

```sh
bash tools/m1/m1.sh          # 成功: "[M1] E2E OK" を出力して exit 0 / 失敗: 非ゼロ終了
M1_STRICT=1 bash tools/m1/m1.sh   # 固定バージョンと不一致なら失敗させる CI 向けモード
```

成果物は `tools/m1/build/` (トップレベル `.gitignore` の `build/` で除外)。`versions.txt` に実行時の toolchain バージョンを記録する。

## パイプライン (m1.sh の各ステップ)

| # | 処理 | 実体 |
|---|------|------|
| 1 | 極小 C プログラムを x64 ELF + x86_64 PE にビルド | `poc_main.c` を `gcc -O0` / `x86_64-w64-mingw32-gcc -O0` |
| 2 | native 実行 → 比較 reference 採取 | `build/ref.out` (PE は実行環境がないため ELF native 出力を reference にする) |
| 3 | RetDec 逆コンパイル | RetDec v5.0 `-o`: ELF → `retdec_elf.c`, PE → `retdec_pe.c` |
| 4 | 必要関数抽出 | `extract_main.awk` で `main` 定義ブロックのみ抽出。PE 固有の後処理: `__mingw_printf` → `printf` 置換、`__main()` 行除去 |
| 5 | emcc 再コンパイル → wasm | `flags.sh` の `EMCC_FLAGS_M1` (toolchain_setup.md 実績値) |
| 6 | node 実行 | emcc が生成した JS glue を node で実行 |
| 7 | 出力比較 | `compare.sh ref.out wasm_elf.out wasm_pe.out` (3-way: native ELF = wasm ELF = wasm PE) |

## ファイル一覧

- `m1.sh` — E2E 本体 (set -euo pipefail、失敗は stderr + 非ゼロ終了)
- `poc_main.c` — ELF/PE 共通の極小プログラム (`printf("hello from e2e, answer=%d\n", 42)`)
- `extract_main.awk` — RetDec 出力から任意関数の定義ブロックを抽出
- `flags.sh` — 定型フラグ。M1 用 `EMCC_FLAGS_M1` (実績値) と **§2.1 本番用 `CLANG_FLAGS` / `EMCC_FLAGS`** (M1 検証条件 3 の「独立ファイル化してコミット」対象)、固定バージョン pin
- `compare.sh` — 出力比較 (単体でも再利用可)
- `README.md` — 本書

## 固定バージョン (M1 検証条件 1)

| tool | version |
|------|---------|
| emcc (emsdk) | 6.0.12 |
| RetDec | v5.0 (commit 53e55b4) |
| mingw-w64 gcc (PE ビルド用) | 13-win32 (= GCC 13 系, runtime 13.2.0 ベース) |
| node | 18+ (emsdk 同梱 24 / 本環境 26 のどちらでも可) |

## 定型フラグ

toolchain_setup.md 実績値 (M1 で検証済):

```
-emcc: -w -Wno-error=int-conversion -Wno-implicit-function-declaration -sERROR_ON_UNDEFINED_SYMBOLS=0
```

§2.1 本番用 (`CLANG_FLAGS` / `EMCC_FLAGS`) は `flags.sh` を参照 (M3 以降の lifter→wasm 化で使用)。

## ハマりどころ・形式 (PE/ELF) 特有の問題 — 実測メモ

- **mingw CRT の全体展開**: `x86_64-mingw32-gcc` でビルドした PE32+ を RetDec に通すと、CRT 一式まで C コードとして再構築され出力は 230KB+。wasm 直リンクは非現実的なので **`main` だけ抽出 → 最小ハーネスに結合** するのが確実 (strategy.md §2.2 の「lifter 品質リスク」とも整合)。
- **`__mingw_printf`**: RetDec は mingw の `printf` 実装を CRT 内部ラッパ名 (`__mingw_printf` 系) で復元する。抽出側で一律 `printf` に置換して emcc libc に落とす。
- **`__main()`**: mingw C runtime 固有の CRT 初期化呼び出し。wasm 化では意味を持たない (グローバルコンストラクタ登録経路) ので行ごと除去。
- **`__stdcall` / `dllexport` / `dllimport`**: x64 PE では呼出規約が x64 ABI に一元化されるため `__stdcall` は no-op。今回の `main` は裸シグネチャで出力され declspec 由来の問題は発生しなかった。RetDec は装飾名 (`__imp_` 接頭など) を原型名に復元済みで、IAT 参照は通常の関数呼び出しとして落地する。ただし **32bit PE や明示 `__declspec(dllexport)` を付けた DLL 形式では名前装飾 (mangling) の差が出得るため、M2 以降の抽出では要再確認**。
- **ELF 側**: RetDec 出力には `_start` (が呼ぶ `__libc_start_main` と `__asm_hlt`) が含まれる。全体コンパイルでも実績フラグ (`-Wno-implicit-function-declaration` + `-sERROR_ON_UNDEFINED_SYMBOLS=0`) で通るが、**`main` を抽出した方が `_start`/CRT を丸ごと避けられてクリーン** (本スクリプトは両フォーマットをこの統一路線にしている)。
- **emcc glue は CommonJS**: 本リポジトリは `package.json` が `"type":"module"` のため、emcc が生成する JS (CommonJS) を `.js` のまま node で実行すると ESM と誤解釈され `require is not defined` で落ちる。**出力を `.cjs` に改名してから node 実行**することで回避した (m1.sh の 5/7)。
- **抽出は RetDec 出力フォーマット依存**: 「定義行がカラム 0・終端 `}` が単独行」という v5.0 フォーマットを前提とする awk。RetDec を更新したら要再検証。

## 制限 (M1 スコープ外)

- `main` から複数の内部関数を呼ぶプログラム (クロージャ的に抽出) には未対応。M2 以降の「関数レベル抽出 + IR pass」で置き換わる。
- 検証は node の stdout 比較のみ。bit-exact DSP 数値照合は M3 以降。
