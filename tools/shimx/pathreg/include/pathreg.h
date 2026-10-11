/* pathreg — shimx パス写像 + レジストリ永続化インタフェース (CAB-168)
 *
 * 役割 (実装はインタフェース接続のみ。仮想FS本体 = CAB-104/asset-vfs (E), 実キー確定 = CAB-213, 実FL結線 = CAB-101):
 *   1. パス写像: FL が扱う Windows パス → 仮想 FS (Emscripten FS / OPFS / asset bundle) への写像。
 *      shimx の既定写像 (file.c: C:\x → /c/x) を pathreg_map() で上書きする。
 *      登録は shimx_set_path_mapper(pathreg_map) — shimx_path_mapper_fn と同一署名。
 *      未登録領域は <0 を返して shimx 既定写像にフォールバック (M4 互換の POSIX 絶対パス素通しも維持)。
 *   2. レジストリ永続化: shimx reg.c の Reg* 読み書きと vreg (CAB-94) の IndexedDB 永続化をつなぐ
 *      契約 (フック署名 / シリアライズ形式 / flush タイミング)。C 側は変更検出 (hash) と seed 投入口のみ。
 *      永続化の実体は JS 側 js/regbridge.mjs (Vreg 互換レコードを書く)。
 *
 * ビルド: shimx のソース群と一緒に本 dir の src (C ファイル) をリンクする (下流は build.sh 参照)。
 *   ※ CAB-214 で vreg reg.c の拡張 (vreg_* 運用フック) が shimx reg.c に取込済みで、vreg/src/reg.c は退役 (reg.c は shimx 1 本)。
 *     下流は「vreg_* フックを export して通知で運用」(推奨) か「フック非 export」(後述の flush 時スナップショット差分で運用)
 *     のどちらか (リンクするソースは同一)。
 */
#ifndef PATHREG_H
#define PATHREG_H

#include "shimx.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- マウント表 ---- */
#define PATHREG_RO      0x1u   /* 読取専用 (asset bundle。E は /fl に mount, 書込は EPERM) */
#define PATHREG_PERSIST 0x2u   /* 永続化対象 (OPFS/IDBFS 由来の領域) */
#define PATHREG_TMP     0x4u   /* セッション内のみ (MEMFS) */

typedef struct PathRegMount {
    const char* winPrefix;   /* Win パス接頭辞 (例 "C:\\Program Files\\Image-Line\\FL Studio 2026") */
    const char* vfsTarget;   /* FS 側 (/ 区切り絶対パス, 例 "/fl") */
    uint32_t flags;          /* PATHREG_* */
} PathRegMount;

/* FL が参照する実パス群 (stub_plan §4 / vreg seed paths / nfo REPORT §5 配置規則と整合)。
 * pathreg_set_paths() で一括設定 (未設定項目は既定値のまま)。 */
typedef struct PathRegPaths {
    const char* installDir;      /* FL インストール dir。→ vfsInstall。既定 C:\Program Files\Image-Line\FL Studio 2026 */
    const char* vfsInstall;      /* 既定 "/fl" (= E asset bundle mount 点, tools/assets/vfs/emscripten.ts) */
    const char* userProfile;     /* %USERPROFILE%。既定 C:\Users\webstudio (shimx SHGetFolderPathW / env / vreg seed 一致) */
    const char* vfsHome;         /* user profile の写像先。既定 "/c/home" */
    const char* sharedDataDir;   /* Shared data (Documents\Image-Line)。NULL = <userProfile>\Documents\Image-Line */
    const char* vfsSharedData;   /* 既定 "/c/home/Documents/Image-Line" */
    const char* vfsTmp;          /* %TEMP% 系の写像先。既定 "/c/tmp" */
} PathRegPaths;

/* マウント表の操作 (全て大小無視の最長一致)。pathreg_set_paths は表を再構築し、
 * 以降の add_mount は追加 (呼び出し順で後勝ちではなく「最長一致優先・同長は後勝ち」)。戻り 0=OK / -1=引数不正・満杯
 * 注意 (CAB-271): pathreg_set_paths() は「明示設定」。実行以降は既定マウント表の遅延ロードは起こらない
 * (旧実装では set_paths 直後の初回 pathreg_map() が既定表を作り直して上書きしていた)。
 * 既定表を使いたい経路は set_paths を一度も呼ばないこと (そのときだけ遅延ロードされる)。 */
void pathreg_paths_init(PathRegPaths* p);                 /* p を既定値で埋める */
int  pathreg_set_paths(const PathRegPaths* p);            /* 既定マウント表を p 由来で再構築 */
int  pathreg_add_mount(const char* winPrefix, const char* vfsTarget, uint32_t flags);
int  pathreg_remove_mount(const char* winPrefix);
void pathreg_clear_mounts(void);
int  pathreg_mount_count(void);
int  pathreg_get_mount(int idx, PathRegMount* out);       /* idx 番目を複写 (監査/テスト用) */

/* ---- パス正規化 (参照実装) ----
 * Win 形の正準化: '/'→'\'、\\?\ / \\.\ プレフィクス剥がし、ドライブレター大文字化、
 * 連続区切りの圧縮、'.' '..' の畳み込み、終端 '\' 除去 (ルート "C:\" は保持)。
 * 相対パスは触らない (shimx file.c が Win cwd 基準で解決)。戻り 0=OK / -1=エラー (outSize 不足含む) */
int pathreg_normalize(const char* winUtf8, char* outWin, size_t outSize);

/* ---- 写像 (shimx_path_mapper_fn 互換: shimx_set_path_mapper に渡せる) ----
 * 正規化 → マウント表を大小無視で最長一致照合 → vfsTarget + 残り ('/' 区切り) を outPosix へ。
 * 戻り 0=写像した (outPosix に書いた) / <0=非対応 (shimx 既定写像にフォールバックさせる)。
 * 非対応 = Win 形絶対パスでないもの (POSIX 絶対/相対) と表に無い接頭辞。 */
int pathreg_map(const char* winPathUtf8, char* outPosix, size_t outSize);
void pathreg_install(void);                               /* shimx_set_path_mapper(pathreg_map) */

/* 逆写像 (FS パス → Win パス) GetModuleFileName 等の FS→Win 復元用。未登録は -1 */
int pathreg_unmap(const char* posixPath, char* outWin, size_t outSize);

/* ---- レジストリ永続化 (C 側口) ----
 * 変更検出: shimx_reg_export_text() の内容を FNV-1a 64bit でハッシュし前回 mark_saved と比較する。
 * 呼び出しは flush 点のみ (下記契約)。export+hash なので O(レジストリ全体)、高頻度ポーリングはしないこと */
int      pathreg_reg_hash(uint64_t* outHash);             /* 0=OK (outHash に 64bit hash) / -1=export 失敗 */
int      pathreg_reg_changed(void);                       /* 1=前回 mark_saved から変化 / 0=無変更 */
void     pathreg_reg_mark_saved(void);                    /* 保存完了時刻のハッシュを基準に更新 */
uint64_t pathreg_reg_saved_hash(void);                    /* 基準ハッシュ (デバッグ用) */
int      pathreg_reg_seed_text(const char* regTextUtf8);  /* .reg テキスト投入 (shimx_reg_import_text 委譲, 成功数を返す) */

/* ---- ホストブリッジ (JS) フック契約 — 詳細は REPORT.md / js/regbridge.mjs ----
 *
 * [構成] wasm (shimx Reg* + pathreg) ⇄ JS regbridge.mjs ⇄ store (vreg store.mjs 互換: load/save/delete)
 *          ⇄ IndexedDB (IdbStore: DB "webstudio-vreg" / store "profiles" / key = profile)
 *
 * [シリアライズ形式]
 *   - C ↔ JS ワイヤ: ".reg" テキスト v5.00 (UTF-8)。C: shimx_reg_export_text() (要 _free) / shimx_reg_import_text()。
 *     JS: vreg regfile.mjs parseToModel / serializeReg (全型・削除構文対応, vreg REPORT §3 往復 57/57 実績)。
 *   - 永続レコード (store.save の第2引数): vreg Vreg.flush() と同一 =
 *       { schema:1, seedVersion:<seed.json version>, machineGuid:<uuid>, savedAt:<epoch ms>,
 *         hkcu: { "<key>": { "<name>": { t:"REG_SZ"|"REG_DWORD"|..., v:<string|number> }, ... }, ... } }
 *     HKCU のみ永続 (HKLM 等は seed から毎回再構成)。これにより vreg Vreg アダプタと同一 profile を相互運用できる。
 *
 * [変更検出と flush 契約] (vreg REPORT §8-1 準拠)
 *   - vreg_* フック export 時 (推奨): C→JS 通知 vreg_set_notify(addFunction 'vi') で dirty 化 → 遅延 flush
 *     (flushDelayMs 既定 200ms) + 明示 flush 点。vreg_generation() で変化確認も可。
 *   - フック非 export: 通知口が使えないため flush 点で pathreg_reg_hash() (または export テキストの JS hash) を
 *     比較して差分時のみ保存。flush 点 = ① メッセージポンプの yield 点 ② pagehide / visibilitychange。
 *     ※ FL を Worker で回し Atomics.wait でブロックする間は JS タイマが走らない → setTimeout だけに頼らない
 *       こと (vreg REPORT §8-1)。regbridge は onYield() / onPageHide() を明示口として提供する。
 *
 * [C 側が JS に求めるエクスポート] (CAB-101 のモジュール EXPORTED_FUNCTIONS に追加すること)
 *   共通: _shimx_init,_shimx_reg_import_text,_shimx_reg_export_text,_shimx_reg_reset,_shimx_reg_set,
 *         _shimx_reg_set_sz,_shimx_reg_set_dword,_shimx_reg_stats,_pathreg_map,_pathreg_normalize,
 *         _pathreg_install,_pathreg_add_mount,_pathreg_reg_hash,_pathreg_reg_changed,_pathreg_reg_mark_saved,
 *         _malloc,_free + EXPORTED_RUNTIME_METHODS: UTF8ToString,stringToUTF8,lengthBytesUTF8,stringToUTF16,HEAPU32
 *   vreg_* フック export 時: 上記に加え _vreg_export_root,_vreg_clear_root,_vreg_generation,_vreg_set_notify,
 *         _vreg_probe_* (+ addFunction/removeFunction, -sALLOW_TABLE_GROWTH=1)
 *   削除反映 (フック非 export 構成) 用: _RegDeleteValueW,_RegDeleteKeyW (import_text が削除構文を解釈しないため)
 *
 * [写像の既定表] pathreg_paths_init + pathreg_set_paths の既定値 (stub_plan §4 整合):
 *   C:\Program Files\Image-Line\FL Studio 2026  → /fl                              (RO, E asset bundle)
 *   <profile>\Documents\Image-Line              → /c/home/Documents/Image-Line     (PERSIST, Shared data)
 *   <profile>\AppData\Roaming                   → /c/home/AppData/Roaming          (PERSIST, %APPDATA%)
 *   <profile>\AppData\Local\Temp\Image-Line     → /c/tmp                           (TMP)
 *   <profile>\AppData\Local                     → /c/home/AppData/Local            (PERSIST, %LOCALAPPDATA%)
 *   <profile>                                   → /c/home                          (PERSIST)
 *   C:\                                         → /c                               (PERSIST, shimx 既定と同じ形)
 *   UNC \\srv\share\x                           → /unc/srv/share/x                 (shimx 既定と同じ形)
 *   表に無い Win 絶対パス                        → <0 (shimx 既定写像 C:\x→/c/x に委譲)
 *   Plugin database の配置 (nfo REPORT §3/§5): C:\Program Files\Image-Line\FL Studio 2026 配下ではなく
 *   <Shared data>\FL Studio\Presets\Plugin database\Installed\{Effects|Generators}\{VST|VST3|AudioUnit|CLAP}\
 *   → 上記 <profile>\Documents\Image-Line ルールで /c/home/Documents/Image-Line/FL Studio/Presets/... に写像される。
 */

#ifdef __cplusplus
}
#endif
#endif /* PATHREG_H */
