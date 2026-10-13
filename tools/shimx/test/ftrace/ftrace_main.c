/* SHX-T12 (#789): 構造化 file trace の実行ドライバ。ftrace_test.sh から呼ぶ。
 *   node x.cjs traced   : shimx_set_trace_file で JSON Lines を有効化して操作し、トレースを stdout に出す
 *   node x.cjs untraced : 同じ操作をトレース無効で実行 (ネガコン: トレース行が出ないこと)
 * 注: 既定の emscripten (MEMFS) ビルドでは guest の getenv から SHIMX_TRACE_FILE は見えないため
 *     (NODERAWFS でのみ見える)、このテストは API 経由 (shimx_set_trace_file) で有効化する。
 */
#include "../test_common.h"

static const char* TRACE_PATH = "/ftr.jsonl";   /* MEMFS 上の仮想パス (host の FS には書かない) */

static void mkfile(const char* posix, const char* body) {
    FILE* f = fopen(posix, "w");
    CHECK(f);
    fputs(body, f);
    fclose(f);
}

static void ops(void) {
    shimx_init();
    mkdir("/c/ftr", 0755);
    mkdir("/c/ftr/dir", 0755);
    mkfile("/c/ftr/in.txt", "hello");
    mkfile("/c/ftr/dir/a.txt", "a");
    mkfile("/c/ftr/dir/b.txt", "b");

    HANDLE h = CreateFileW(W("C:\\ftr\\in.txt"), GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(h != INVALID_HANDLE_VALUE);
    char buf[16]; DWORD n = 0;
    CHECK(ReadFile(h, buf, sizeof buf, &n, NULL));
    CHECK(ReadFile(h, buf, sizeof buf, &n, NULL));
    CloseHandle(h);

    HANDLE miss = CreateFileA("C:\\ftr\\none.txt", GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(miss == INVALID_HANDLE_VALUE);

    HANDLE w = CreateFileW(W("C:\\ftr\\out.txt"), GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    CHECK(w != INVALID_HANDLE_VALUE);
    CloseHandle(w);

    CHECK(GetFileAttributesW(W("C:\\ftr\\in.txt")) != INVALID_FILE_ATTRIBUTES);
    CHECK(GetFileAttributesW(W("C:\\ftr\\none.txt")) == INVALID_FILE_ATTRIBUTES);

    WIN32_FIND_DATAW fd;
    HANDLE fh = FindFirstFileW(W("C:\\ftr\\dir\\*.txt"), &fd);
    CHECK(fh != INVALID_HANDLE_VALUE);
    int found = 1;
    while (FindNextFileW(fh, &fd)) found++;
    FindClose(fh);
    CHECK(found == 2);

    HANDLE none = FindFirstFileW(W("C:\\ftr\\dir\\*.zzz"), &fd);
    CHECK(none == INVALID_HANDLE_VALUE);
}

int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "traced";
    if (!strcmp(mode, "env")) {                       /* NODERAWFS ビルド専用: 環境変数だけで有効化されることを確認 */
        shimx_init();
        HANDLE h = CreateFileW(W("C:\\ftr_env_probe.txt"), GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
        CHECK(h == INVALID_HANDLE_VALUE);
        printf("env ok\n");
        return 0;
    }
    if (!strcmp(mode, "untraced")) {
        ops();
        printf("ops ok\n");
        return 0;
    }
    if (!strcmp(mode, "stderr")) {
        shimx_set_trace(1);
        ops();
        printf("ops ok\n");
        return 0;
    }
    CHECK(shimx_set_trace_file(TRACE_PATH) == 0);
    ops();
    shimx_set_trace_file(NULL);
    printf("ops ok\n");
    FILE* tf = fopen(TRACE_PATH, "r");
    CHECK(tf);
    printf("--TRACE-BEGIN--\n");
    char line[4096];
    while (fgets(line, sizeof line, tf)) fputs(line, stdout);
    printf("--TRACE-END--\n");
    fclose(tf);
    return 0;
}
