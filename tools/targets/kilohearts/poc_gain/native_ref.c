/* kHs Gain (gain::GainDsp::process, HeartCore.core_64 VA 0x1804b0380) native 参照ドライバ。
 * 実物の x86-64 機械語を VA 通り (ImageBase 0x180000000) に敷設し MS x64 ABI で直接実行する
 * (tools/m5/native_fx.c の方式を踏襲)。入力ベクタと期待出力 (ビット) を vectors.json に吐く。
 *
 *   native_ref <HeartCore.core_64> <vectors.json>
 *
 * ctx レイアウト (process 逆アセンブルから推定した最小形):
 *   ctx+0x3180 int  id            ctx+0x3188 P* {int mode; float v; float meterL; float meterR}
 *   ctx+0x3198 Q* {.. float q28@0x28, u8 dirtyL@0x5c, u8 dirtyR@0x7c}
 *   ctx+0x31b0 V* {.. end@0x68, cap@0x70}  (変更通知 vector<int> の push 先)
 * this (GainDsp state, 0xA0 B): [0x64]pos [0x68]inc [0x6c]a [0x70]b [0x74]cur [0x78]first [0x84,0x94]meter coef [0x88,0x98]meter
 * buf: {float* ch0 @0; float* ch1 @8; int n @0x28}
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#define IMG 0x180000000UL
#define FN_GAIN_PROCESS 0x1804b0380UL

typedef void (__attribute__((ms_abi)) *proc_t)(void*, void*, void*);

static void map_image(const char* path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) { perror("open"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    uint8_t* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    uint32_t pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t ns, osz; memcpy(&ns, f + pe + 6, 2); memcpy(&osz, f + pe + 20, 2);
    uint32_t soff = pe + 24 + osz, imgsz; memcpy(&imgsz, f + pe + 24 + 56, 4);
    void* b = mmap((void*)IMG, imgsz, PROT_READ | PROT_WRITE | PROT_EXEC,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
    if (b != (void*)IMG) { fprintf(stderr, "cannot map image at %lx\n", IMG); exit(3); }
    for (int i = 0; i < ns; i++) {
        uint32_t vs, va, rs, rp; uint8_t* e = f + soff + i * 40;
        memcpy(&vs, e + 8, 4); memcpy(&va, e + 12, 4); memcpy(&rs, e + 16, 4); memcpy(&rp, e + 20, 4);
        uint32_t n = rs < vs ? rs : vs;
        memcpy((void*)(IMG + va), f + rp, n);
    }
}

static uint32_t rng = 0x12345678u;
static float rnd(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return ((int32_t)rng) / 2147483648.0f; }
static uint32_t bits(float x) { uint32_t u; memcpy(&u, &x, 4); return u; }

static void hexs(FILE* o, const void* p, size_t n) { const uint8_t* b = p; for (size_t i = 0; i < n; i++) fprintf(o, "%02x", b[i]); }

typedef struct { int mode; float gain_p; float q28; float coef; int n; int dirty; int vcap_room; } Blk;

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage\n"); return 2; }
    map_image(argv[1]);
    proc_t proc = (proc_t)FN_GAIN_PROCESS;

    /* シーケンス (1 DSP インスタンスを通して状態を引き継ぐ) */
    Blk seq[] = {
        {0, 1.0f, 0.0f, 0.01f, 64, 0, 4},   /* first: 即値初期化 */
        {0, 0.5f, 0.0f, 0.01f, 64, 0, 4},   /* gain 変化 → ramp */
        {0, 0.5f, 0.0f, 0.01f, 64, 0, 4},   /* 変化なし (|d|<eps) */
        {1, 0.0f, 1.25f, 0.01f, 129, 1, 4}, /* mode==1 経路 (2*q28), 奇数 n */
        {0, 3.0f, 0.0f, 0.02f, 0, 0, 4},    /* n=0 */
        {0, 0.0f, 0.0f, 0.02f, 33, 1, 0},   /* 通知 vector 満杯だが dirty 済みで push 経路を踏まない (realloc 経路は PoC 対象外) */
    };
    int nb = sizeof(seq) / sizeof(seq[0]);

    uint8_t* self = calloc(1, 0xB0);
    uint8_t* ctx = calloc(1, 0x3200);
    uint8_t P[16] = {0}, Q[0x80] = {0}, V[0x80] = {0};
    int vec[8] = {0};
    *(void**)(ctx + 0x3188) = P; *(void**)(ctx + 0x3198) = Q; *(void**)(ctx + 0x31b0) = V;
    *(int*)(ctx + 0x3180) = 100;
    self[0x78] = 1;
    *(float*)(self + 0x84) = 0.01f; *(float*)(self + 0x94) = 0.01f;

    FILE* o = fopen(argv[2], "w");
    fprintf(o, "{\"image\":\"%s\",\"fn\":\"0x%lx\",\"blocks\":[\n", "HeartCore.core_64", FN_GAIN_PROCESS);
    for (int bi = 0; bi < nb; bi++) {
        Blk* k = &seq[bi];
        int n = k->n;
        float* L = calloc(n + 4, 4); float* R = calloc(n + 4, 4);
        for (int i = 0; i < n; i++) { L[i] = rnd(); R[i] = rnd(); }
        uint8_t buf[0x30] = {0};
        *(float**)(buf + 0) = L; *(float**)(buf + 8) = R; *(int*)(buf + 0x28) = n;
        *(int*)(P) = k->mode; *(float*)(P + 4) = k->gain_p;
        *(float*)(Q + 0x28) = k->q28;
        Q[0x5c] = Q[0x7c] = (uint8_t)k->dirty;
        *(float*)(self + 0x84) = k->coef; *(float*)(self + 0x94) = k->coef;
        *(int**)(V + 0x68) = vec; *(int**)(V + 0x70) = vec + (k->vcap_room ? 8 : 0);
        if (!k->vcap_room) *(int**)(V + 0x68) = vec; /* end==cap → 通知 push が必要な場合のみ realloc 経路 (dirty=1 で回避) */
        fprintf(o, "%s{\"n\":%d,\"mode\":%d,\"gain_p\":%u,\"q28\":%u,\"coef\":%u,\"dirty\":%d,\"vroom\":%d,\"inL\":\"",
                bi ? ",\n" : "", n, k->mode, bits(k->gain_p), bits(k->q28), bits(k->coef), k->dirty, k->vcap_room);
        hexs(o, L, (size_t)n * 4); fprintf(o, "\",\"inR\":\""); hexs(o, R, (size_t)n * 4);
        fprintf(o, "\",\"self_in\":\""); hexs(o, self, 0xA0);
        proc(self, ctx, buf);
        fprintf(o, "\",\"outL\":\""); hexs(o, L, (size_t)n * 4);
        fprintf(o, "\",\"outR\":\""); hexs(o, R, (size_t)n * 4);
        fprintf(o, "\",\"self_out\":\""); hexs(o, self, 0xA0);
        fprintf(o, "\",\"P\":\""); hexs(o, P, 16);
        fprintf(o, "\",\"Q\":\""); hexs(o, Q, 0x80);
        fprintf(o, "\",\"vpushed\":%ld,\"vec\":\"", (long)(*(int**)(V + 0x68) - vec)); hexs(o, vec, 32);
        fprintf(o, "\"}");
        free(L); free(R);
    }
    fprintf(o, "\n]}\n");
    fclose(o);
    return 0;
}
