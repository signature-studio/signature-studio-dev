# REPORT_APPENDIX_1989 — KH-31 (#1989): Resonator emcc の未関数化 callee 閉包

親 #1926 (KH-30)。前任 #1405 (closed)。既知類型との関係: 該当なし (DEFECTS.md の類型ではなく、converter の callee 解決の範囲の問題)。
本付録は REPORT_APPENDIX.md §10-7r の全文。

## 結論
- **閉包は確定できた**: `ghidra_route/closure.py` の不動点反復で **8 反復・閉包 38 関数** (proc 1 + callee 37)。decompile FAIL **0**。
  閉包外の参照は IAT thunk の 2 件 (`0x180fd81e4`・`0x180fd81ec`) のみで、これは converter の THUNK 規則で stub 化する対象。
- **閉包 37 件を `also` に入れると emcc 件数が増える (7 → 54)**。受入 2 (件数が増えない) を満たさないため、
  `ghidra_to_c.py` の resonator `also` は**現行 16 件のまま**にした (本 PR では変更しない)。
- 未宣言 4 件 (`FUN_180fd51cc`・`FUN_180fd2d38`・`FUN_180fd4f30` ×2) は閉包に入れると消える。
  増える 54 件は閉包 callee 由来の別種の欠陥で、件数の内訳は下の表 (次の子 issue の対象)。
- Gain/Haas/Gate の突合は HEAD で 1000/1000 bit-exact (converter 未変更)。

## 環境 (実測・run 内で用意)
- Ghidra 12.1.4: `ghidra_12.1.4_PUBLIC_20260921.zip` を `https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/` から `$RUNNER_TEMP/ghidra` に取得。sha256 `ddac49f9…d2db` 一致 (fail-closed 検査を通過)。`GHIDRA_HOME=$RUNNER_TEMP/ghidra/ghidra_12.1.4_PUBLIC`。
- JDK 21 = `[JDK21]` (`docs/REFERENCES.md`)。emsdk = `[EMSDK]` (6.0.12)。
- 素材 `plugins-kilohearts`: `tar --zstd -xf` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/*` → `HeartCore.core_64` (76,642,304 B)。dmg は使わない。

## 閉包の確定手順 (受入 1 の「手順」)
1. 初期集合 S = `SNAPINS['resonator']` の proc + `also` (16 件)。
2. S のうち未 decompile の VA を `scripts/ghidra/DecompEach.java` (`analyzeHeadless -noanalysis`) で decompile し、`<va>.c` を作る。
3. OK の `.c` の本文から呼出先を集める: `FUN_<va>`・`thunk_FUN_<va>` (jmp thunk の飛び先 = converter の書換えと同じ)・`func_0x000<va>`。
4. IAT thunk (`THUNK`) と STUB に当たるものは閉包に入れず、新規分だけを S に足す。
5. 新規 0 件で止める (不動点)。FAIL が 1 件でもあれば exit 1 (閉包は未確定扱い)。

実行: `GHIDRA_HOME=… python3 tools/targets/kilohearts/ghidra_route/closure.py resonator work/ghidra/out_res work/winpkg/HeartCore.core_64`
出力: `work/ghidra/out_res/closure_resonator.json` (commit 版は `ghidra_route/closure_resonator.json`)。

| 反復 | decompile 件数 | 新規 callee | 集合 (累計) |
|---|---|---|---|
| 1 | 17 | 3 | 20 |
| 2 | 3 | 5 | 25 |
| 3 | 5 | 4 | 29 |
| 4 | 4 | 3 | 32 |
| 5 | 3 | 4 | 36 |
| 6 | 4 | 1 | 37 |
| 7 | 1 | 1 | 38 |
| 8 | 1 | 0 | 38 (不動点) |

- 所要: 8 回の analyzeHeadless (HeartCore import + DecompEach) の合計 **216 s** (03:38:53 → 03:42:29 UTC)。load average は未計測。
- 検算 (別アルゴリズム): decompile 済み 38 ファイルの本文を grep で集計した呼出名の集合 − 閉包 = `{0x180fd81e4, 0x180fd81ec}` (IAT thunk の 2 件のみ)。閉包のファイル集合 = 閉包 38 (一致)。

## emcc 件数 (既定フラグ `emcc -c -ferror-limit=0 -I ghidra_route resonator.c`・修復なし・`grep -c 'error:'`)
| 条件 | 件数 | 内訳 |
|---|---|---|
| HEAD (`also` 16 件・測定 commit `120fcf606` の converter = main と同一) | **7** | 未宣言 4 (`FUN_180fd51cc` 1・`FUN_180fd2d38` 1・`FUN_180fd4f30` 2) + ポインタ型不一致 3 (`resonator.c:530`・`617`・`745`) |
| 閉包 37 件を `also` に入れた試行 (未コミット・採用せず) | **54** | 引数数不足・不一致 25 / int↔pointer 変換 19 / ポインタ型不一致 6 / float を整数・ポインタとして扱う 2 / `DAT_` 未定義 2 (`DAT_184162358`・`DAT_182989680`) / 未宣言 0 |

- 未宣言 4 件は閉包で消える (試行の内訳に未宣言は 0 件)。ただし閉包由来の 54 件が残るため件数は増える。
- 注: issue 本文は「未宣言 5 件」と書くが、HEAD の実測は未宣言 4 件 (`FUN_180fd4f30` が 2 件)。
- 注: issue 本文の前提「LOCK/UNLOCK は fail-fast」は現行 shim と合わない。`ghidra_shim.h` は LOCK/UNLOCK を no-op (`((void)0)`・#3072 の決定) とし、`HeapAlloc`/`HeapFree` は fail-fast (`kh_api_fail`) である。閉包内の LOCK/UNLOCK は 17 箇所、HeapAlloc 1・HeapFree 2 箇所。

## 回帰 (HEAD の converter・1000 trial / seed 7・`build_cmp.sh` と同じ fix `bitcast,intload,stackpair,assoc,concat`)
- Gain **1000/1000** bit-exact (calls 4999/4999・wasm 15,161 B)
- Haas **1000/1000** bit-exact (calls 5500/5500・wasm 16,878 B)
- Gate **1000/1000** bit-exact (calls 4999/4999・wasm 17,367 B)
- 10 関数の decompile (`run_all.sh` の集合) は 10/10 OK。wasm サイズは §10-7o・§10-7m と一致。

## 残件 (起票先付き)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 閉包 37 件を `also` に入れると emcc 7 → 54 (引数数不一致 25・int↔pointer 19・ポインタ型 6・float 2・DAT_ 2) | 受入 1 の `also` 閉包化・受入 2 (件数が増えない) が未達 | 子 #3764 (KH-63) |
| Resonator の native 全バイト突合・ネガコン・ablation (emcc 未通過のため未実施) | 突合の受入範囲外 | 子 #3764 (KH-63)・親 #1926 |
| `DAT_` 接頭の未定義グローバル (`gd_` 規則が `_DAT_`・`_UNK_` のみ対象) | 2 件 | 子 #3764 (KH-63) |

## 測定の対象
- 測定 commit: `120fcf606` (`closure.py` と `closure_resonator.json` を追加した commit。converter は HEAD = main の `1bb93134e` と同一)。
- `git diff 120fcf606 HEAD -- tools/targets/kilohearts/ghidra_route` の出力は 0 行 (本付録の commit は docs のみ)。
