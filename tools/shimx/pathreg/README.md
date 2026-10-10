# pathreg — shimx パス写像 + レジストリ永続化インタフェース (CAB-168)

shimx (CAB-11/211) の Win32 ファイル API とレジストリ API を、仮想 FS (CAB-104/asset-vfs (E)) と
vreg の IndexedDB 永続化 (CAB-94) に接続するための**インタフェース層**。FL 側 C コードから見た
Win パス/レジストリの意味論は変えず、ブラウザ側の実体 (OPFS / asset bundle / IndexedDB) への
写像と保存だけを担う。仕様の詳細は **`REPORT.md`** と **`include/pathreg.h`** (契約コメント付き)。

## 構成

| パス | 内容 |
|---|---|
| `include/pathreg.h` | C インタフェース + ホストブリッジ (JS) フック契約 (署名 / シリアライズ形式 / flush タイミング) |
| `src/pathmap.c` | パス正規化 (参照実装) + マウント表 + `shimx_path_mapper_fn` 互換写像フック |
| `src/regpersist.c` | レジストリ変更検出 (export → FNV-1a 64bit hash) + seed 投入口 |
| `js/pathmap.mjs` | pathmap.c の JS ミラー (glue が起動前に配置先を計算する用) |
| `js/regbridge.mjs` | Reg* ↔ vreg store (IndexedDB) ブリッジ。vreg_* 通知フック結線 / フック非 export (hash 差分) 両対応 |
| `test/`, `scripts/` | C 単体 (ST/MT) / JS 単体 / e2e (モック永続化層) + 1 コマンド検収 |

## 検収

```sh
bash tools/shimx/pathreg/scripts/e2e.sh   # 約 9 秒, exit 0
```

既存検収への影響なし: `bash tools/shimx/test.sh --quick` PASS (shimx 既存ファイルは無変更)。
