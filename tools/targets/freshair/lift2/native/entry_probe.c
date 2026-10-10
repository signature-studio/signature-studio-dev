/* entry_probe.c — FA-2c: VST2 エントリ (AEffect wrapper ctor + thunk 群) を実機機械語で実行する探索/参照ハーネス。
 *   ./entry_probe <core>          # 探索 (ctor + AEffect ダンプ + thunk 呼出し)
 * 環境: FA_OPS="op:idx:val:ptr:opt,..." (16 進数, 空文字で 0) — thunk 呼出しの scenario 指定 */
#include "pe_map.h"
#include "native_shim.h"
#include "am_host.h"
#define GUARD(stmt) do { g_in_guard = 1; sigguard = 0; if (sigsetjmp(g_jb, 1) == 0) { stmt; } else { sigguard = 1; } g_in_guard = 0; } while (0)

typedef long long (__attribute__((ms_abi)) *vst_main_t)(void*);
typedef long long (__attribute__((ms_abi)) *ctor4_t)(void*, void*, int, int);
typedef long long (__attribute__((ms_abi)) *disp_t)(void*, int, int, long long, void*, float);
typedef void (__attribute__((ms_abi)) *setp_t)(void*, int, float);
typedef float (__attribute__((ms_abi)) *getp_t)(void*, int);
typedef void (__attribute__((ms_abi)) *proc_t)(void*, float**, float**, int);

#define VST_MAIN 0x1803b4b30ULL
#define WRAP_CTOR 0x180dace80ULL     /* 派生 wrapper ctor: (this, audioMaster, numPrograms, numParams) */

int main(int argc, char** argv) {
    uint8_t* im = pe_map(argv[1]); guard_install();
    static const unsigned long long stubs[] = {0x18103d37c, 0x18103d47c, 0x18102f728};
    for (unsigned k = 0; k < sizeof stubs / sizeof *stubs; k++) im[stubs[k] - 0x180000000ULL] = 0xCC;
    { unsigned char* p = im + (0x18100c72cULL - 0x180000000ULL);
      if (p[0] == 0x65 && p[1] == 0x4c && p[2] == 0x8b && p[3] == 0x1d) {
          static const unsigned char GS_NEW[8] = {0x45, 0x31, 0xdb, 0x90, 0x90, 0x90, 0x90, 0x90};
          memcpy(p, GS_NEW, 8);
      }
      unsigned char* q = im + (0x18100c738ULL - 0x180000000ULL); if (q[0] == 0x73) q[0] = 0xEB; }
    patch_iat(getenv("FA_IAT") ? getenv("FA_IAT") : "iat_slots.txt");
    patch_iat_all();
    patch_pokes(getenv("FA_POKES") ? getenv("FA_POKES") : "pokes.txt");

    /* ---- 1. VSTPluginMain (framework 全体経路。CRT/locale 未初期化で途中失敗する可能性あり) ---- */
    am_reset();
    g_in_guard = 1;
    unsigned char* ae = NULL;
    if (sigsetjmp(g_jb, 1) == 0) {
        ae = (unsigned char*)((vst_main_t)VST_MAIN)((void*)(uintptr_t)&am_callback);
    } else {
        printf("STEP1: VSTPluginMain sig=%d rip=%llx addr=%llx (framework 経路は native 参照として不成立の可能性)\n",
               g_fault_sig, g_fault_rip, g_fault_addr);
        am_dump(0);
    }
    g_in_guard = 0;
    if (ae) {
        printf("STEP1: VSTPluginMain OK AEffect=%llx magic=%08x numProg=%d numParam=%d numIn=%d numOut=%d flags=%08x\n",
            (unsigned long long)(uintptr_t)ae, *(unsigned*)ae, *(int*)(ae+0x28), *(int*)(ae+0x2c),
            *(int*)(ae+0x30), *(int*)(ae+0x34), *(unsigned*)(ae+0x38));
        printf("STEP1 thunk rva: disp=%llx proc=%llx setp=%llx getp=%llx procR=%llx procD=%llx obj=%llx\n",
            *(unsigned long long*)(ae + 8) - 0x180000000ULL, *(unsigned long long*)(ae + 0x10) - 0x180000000ULL,
            *(unsigned long long*)(ae + 0x18) - 0x180000000ULL, *(unsigned long long*)(ae + 0x20) - 0x180000000ULL,
            *(unsigned long long*)(ae + 0x78) - 0x180000000ULL, *(unsigned long long*)(ae + 0x80) - 0x180000000ULL,
            *(unsigned long long*)(ae + 0x60) - 0x180000000ULL);
    }

    /* ---- 2. AEffect wrapper ctor を直接実行 (framework/locale 非依存) ---- */
    unsigned char* w = gr_alloc(0x200);
    memset(w, 0, 0x200);
    am_reset();
    unsigned char* we = NULL;
    g_in_guard = 1;
    if (sigsetjmp(g_jb, 1) == 0) {
        we = (unsigned char*)((ctor4_t)WRAP_CTOR)(w, (void*)(uintptr_t)&am_callback, 1, 3);
    } else {
        printf("STEP2: wrapper ctor sig=%d rip=%llx addr=%llx\n", g_fault_sig, g_fault_rip, g_fault_addr);
    }
    g_in_guard = 0;
    printf("STEP2: wrapper=%llx ctor-ret=%llx\n", (unsigned long long)(uintptr_t)w, (unsigned long long)(uintptr_t)we);
    unsigned char* e = w + 0x30;
    printf("STEP2 AEffect: magic=%08x disp=%llx proc=%llx setp=%llx getp=%llx\n",
        *(unsigned*)(e), *(unsigned long long*)(e + 8) - 0x180000000ULL, *(unsigned long long*)(e + 0x10) - 0x180000000ULL,
        *(unsigned long long*)(e + 0x18) - 0x180000000ULL, *(unsigned long long*)(e + 0x20) - 0x180000000ULL);
    printf("STEP2 fields: numProg=%d numParam=%d numIn=%d numOut=%d flags=%08x initDelay=%d ioRatio=%08x\n",
        *(int*)(e + 0x28), *(int*)(e + 0x2c), *(int*)(e + 0x30), *(int*)(e + 0x34), *(unsigned*)(e + 0x38),
        *(int*)(e + 0x50), *(unsigned*)(e + 0x5c));
    printf("STEP2 fields2: object=%llx uniqueID=%08x version=%d procR=%llx procD=%llx\n",
        *(unsigned long long*)(e + 0x60) - 0x180000000ULL, *(unsigned*)(e + 0x70), *(int*)(e + 0x74),
        *(unsigned long long*)(e + 0x78) - 0x180000000ULL, *(unsigned long long*)(e + 0x80) - 0x180000000ULL);
    printf("STEP2 ae+0x00..0xa8: "); for (int i = 0; i < 0xa8; i += 8) printf("%016llx ", *(unsigned long long*)(e + i)); printf("\n");
    printf("STEP2 am calls: %llu\n", (unsigned long long)am_count());
    iat_report();

    /* ---- 3. thunk 呼出し (FA_OPS)。op: "D:op,idx,val,ptrofs,opt" / "G:idx" / "S:idx,valbits" / "R:n" / "P:n" ---- */
    {
        static char buf[4096];
        float* in1 = (float*)calloc(4, 256); float* in2 = (float*)calloc(4, 256);
        float* out1 = (float*)calloc(4, 256); float* out2 = (float*)calloc(4, 256);
        float* ins[2] = {in1, in2}; float* outs[2] = {out1, out2};
        for (int i = 0; i < 256; i++) { in1[i] = 0.25f * (float)((i % 7) - 3); in2[i] = -in1[i]; }
        const char* ops = getenv("FA_OPS");
        if (!ops) ops = "G:0,G:1,G:2,S:1,40200000,G:1,R:8,R:64,P:8,D:0,-1,0,0,0";
        snprintf(buf, sizeof buf, "%s", ops);
        for (char* tok = strtok(buf, ","); tok; tok = strtok(NULL, ",")) {
            char kind = tok[0];
            char* rest = tok[1] == ':' ? tok + 2 : NULL;
            if (!rest) continue;
            g_in_guard = 1;
            long long ret = 0; float fx = 0.0f;
            if (sigsetjmp(g_jb, 1) == 0) {
                switch (kind) {
                case 'D': { long long a[5] = {0,0,0,0,0}; int argc = 0; char* p = strtok(rest, ",");
                            while (p && argc < 5) { a[argc++] = strtoll(p, NULL, 16); p = strtok(NULL, ","); }
                            printf("OP D op=%llx idx=%llx val=%llx ptr=%llx -> ", (unsigned long long)a[0], (unsigned long long)a[1],
                                   (unsigned long long)a[2], (unsigned long long)a[3]);
                            ret = ((disp_t)*(void**)(e + 8))(e, (int)a[0], (int)a[1], a[2], (void*)(uintptr_t)a[3], 0.0f);
                            break; }
                case 'G': { int idx = strtoul(rest, NULL, 16);
                            printf("OP G %x -> ", idx);
                            fx = ((getp_t)*(void**)(e + 0x20))(e, idx);
                            break; }
                case 'S': { int idx; unsigned vb; sscanf(rest, "%x,%x", &idx, &vb); float f; memcpy(&f, &vb, 4);
                            printf("OP S %x %08x -> ", idx, vb);
                            ((setp_t)*(void**)(e + 0x18))(e, idx, f);
                            break; }
                case 'R': { int n = strtoul(rest, NULL, 16);
                            printf("OP R %d -> ", n);
                            ((proc_t)*(void**)(e + 0x78))(e, ins, outs, n);
                            break; }
                case 'P': { int n = strtoul(rest, NULL, 16);
                            printf("OP P %d -> ", n);
                            ((proc_t)*(void**)(e + 0x10))(e, ins, outs, n);
                            break; }
                default: printf("OP ?%c\n", kind); break;
                }
            }
            g_in_guard = 0;
            if (g_fault_sig) { printf("ERR sig=%d rip=%llx addr=%llx\n", g_fault_sig, g_fault_rip, g_fault_addr); g_fault_sig = 0; continue; }
            if (kind == 'G') printf("xmm0=%08x  ", *(unsigned*)&fx);
            else printf("rax=%llx  ", ret);
            printf("out0=%08x out1=%08x am=%llu\n", ((unsigned*)outs[0])[0], ((unsigned*)outs[1])[0], (unsigned long long)am_count());
        }
    }
    return 0;
}
