# REX side module (T-SH-47 #2896) 付録 — 旧測定 (測定 commit `105733875`)

本付録は `REPORT.md` §10 の旧版の全文 (main 取り込み前・本検査 133 件版)。最新の測定は REPORT §10。

## A. 所有者限定 tier の side module 分離とビルドフラグ除外 — T-SH-47 (#2896)

測定 commit: `105733875` (`tools/shared/lift/rex/` の最後のコード変更)。以降の差分は本 REPORT のみ。既知類型との関係: 該当なし (配信物の分離とフラグのみ。本検査の不一致 0)。

### A.1 結論と方法
- **結論 (1 行)**: 部分。REX の standalone wasm を所有者限定 tier の `owner/rex_side.wasm` に複製し、`REX_SIDE=0` で `owner/` から除外できるようにした。`REX_SIDE=1`・`0` の両方で `lift_x64c.sh all` が ALL OK。**SIDE_MODULE 形式 (dlopen 形) は未達** (§A.3 (a)・子 #3630)。**公開 tier への結線は未実施** (§A.3 (b))。
- フラグ `REX_SIDE` (既定 `1`、0/1 以外は exit 2)。`1` = 配信物 `$W/owner/` に `rex_side.wasm` (`rex.wasm` の複製。`cmp` で一致確認)。`0` = 空。`$W` = `tools/shared/work/lift/rex` (gitignore)。glue (`rex_glue.c`・`fle_cpu.c`) は wasm に静的に入るため別ファイルにしない。`rex.wasm` は両フラグとも `$W` 直下に生成される (`REX_SIDE=0` でも残る)。フラグが切り替えるのは `owner/` への複製だけで、§A.1 の「分離」と §A.3 の「組み込みを切り替える単位」はこの範囲に限る。
- `ok`: 本検査 PASS 後に `rm -rf "$W/owner"` して作り直し、`owner_list.txt` (`cd "$W" && find owner -type f | sort`) を期待値と突合 (`1` で `owner/rex_side.wasm` の 1 行、`0` で 0 行。`0` では `*rex*`・`*glue*`・`*.c` も 0 件)。不一致は rc=1。`neg-owner` は `ok` と同じ配信物に `owner/rex_glue.c` (ダミー) を足して突合し、FAIL を検出すれば exit 0。判定後はダミーを消して `ok` と同じ状態に戻す。`all` = `ok neg-cmp neg-ctx neg-owner`。

### A.2 実測 (測定 commit `105733875`・各フラグで `all` を 3 回。n=3)
| 項目 | `REX_SIDE=1` | `REX_SIDE=0` |
|---|---|---|
| `all` の wall (`time` の real) / rc | 8.95–9.25 s / 0 (3 回) | 8.87–8.99 s / 0 (3 回) |
| 各モードの elapsed (min–max: ok / neg-cmp / neg-ctx / neg-owner) | 2–2 / 2–2 / 2–3 / 2–3 s | 2–2 / 2–2 / 3–3 / 2–2 s |
| load (1 分値, `all` 開始時。直前 run の負荷が残る) | 0.23–0.59 | 0.60–0.71 |
| 本検査 `ok` (diff_test) | 133/133 一致・不一致 0・除外 67 (3 回とも) | 同左 |
| 配信物の一覧 (`[rex] owner tier` 行) | `owner/rex_side.wasm` (3 回とも) | 空 (3 回とも) |
| sha256 | `rex.wasm` = `owner/rex_side.wasm` = `76dce05e57616cdf87e999b4dab55bd3934eb7931113e4e9826b7608bc2efca0` (sha256sum と python `hashlib` で一致) | `owner/` は空 |
| neg-cmp / neg-ctx (diff_test の不一致) | 1 件 / 133 件 → 両方 FAIL (期待どおり) | 同左 |
| neg-owner (一覧突合) | `owner/rex_glue.c owner/rex_side.wasm` ≠ 期待 → FAIL (期待どおり) | `owner/rex_glue.c` ≠ 期待 (空) → FAIL (期待どおり) |
| 直前の HEAD `03d3291a0` (コード差分 0) で `all` を 1 回再実行 | rc 0・ALL OK・wall 7.02 s・本検査 133/133 一致 | rc 0・ALL OK・wall 7.21 s・本検査 133/133 一致 |

### A.3 検証範囲 / 範囲外 / 未解決
- 検証した: 2 フラグ × 3 回の `all` (本検査・配信物の一覧・`cmp`・sha256・ネガコン 3 種)。独立検算は §A.4 の 1 行 (`hashlib` で `owner/` の一覧とハッシュを再計算し、`sha256sum` と照合)。
- 受入 1 は**部分**: 範囲外・未達は次のとおり。`owner/rex_side.wasm` は `-sSTANDALONE_WASM=1 --no-entry` でビルドした `rex.wasm` の同一バイト複製で、side module 形式ではない。(a) `-sSIDE_MODULE=2` の dlopen 形は作っていない (固定 VA 0x30000000 の画像と global 配置の再配置を要する)。(b) 公開 tier の配信 (`deploy/`・release guard) への結線は無い。(c) 配信側の host (組み込み先) は未実装。本検査の範囲 (§7.5) は変えていない。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| (a) dlopen 形 (`-sSIDE_MODULE=2`・固定 VA・global 再配置)、(c) 組み込み先 host の実装 | side module の形式と結線が未決。`rex_side.wasm` を読む経路が無い | 子 #3630 [T-SH-91] (PM agent の判断待ち。既定案は現状の standalone 複製) |
| (b) 公開 tier の配信 (`deploy/`・release guard の deny-list) への結線 | `REX_SIDE=1` の配信物が公開 tier に載る経路は塞がれていない | PM (#2896 本文の「範囲外の PM 作業」・D11) |

### A.4 再現
- `FL_WIN64_DIR=<fl-win64 展開先> REX_SIDE=1 bash tools/shared/lift/rex/lift_x64c.sh all` (`REX_SIDE=0` も同じ)。配信物の確認は `cd tools/shared/work/lift/rex && find owner -type f | sort && sha256sum rex.wasm owner/rex_side.wasm`。
- 独立検算 (一覧とハッシュを python で再計算): `cd tools/shared/work/lift/rex && python3 -c "import hashlib,pathlib; [print(hashlib.sha256(p.read_bytes()).hexdigest(), p) for p in sorted(pathlib.Path('owner').rglob('*')) if p.is_file()]"`。`REX_SIDE=1` では `owner/rex_side.wasm` 1 行に `76dce05e…` が出れば一致。

### A.5 測定後のコード差分 (差分 0 の証跡)
`git diff 105733875 HEAD -- tools/shared/lift/rex tools/flelift tools/shared/env.sh ':(exclude)*.md'` の出力: 行数 0 (0 = コード差分なし)。HEAD は本 REPORT を含む commit (commit 2 は `845592bbc`)。
