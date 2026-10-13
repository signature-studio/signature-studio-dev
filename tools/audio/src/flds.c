/* flds.c — DirectSound 互換 (secondary 循環バッファ + pump → SAB ring)。設計: docs/PROTOCOL.md §8。
 *
 * カーソル模型 (すべて「Play 開始からの絶対フレーム数」を基準, 位置 = (base + abs) mod size):
 *   read_abs  = worklet が消費した総フレーム (ctl.out_read を 64bit に拡張) → play cursor
 *   conv_abs  = pump が secondary から ring へ変換済みの総フレーム (ring 内は凍結 = DS の「確定済み領域」)
 *   write cursor = conv_abs + pump_frames。これ以降の領域は pump が次ブロックを変換するまで書き換え可。
 *   underrun 中は worklet が無音を出して out_read は止まる (= play cursor も止まる; データは捨てない)。 */
#include "flds.h"
#include "flaudio.h"
#include <emscripten.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

#define LD(x) __atomic_load_n(&(x), __ATOMIC_SEQ_CST)
#define FLDS_MAX_NOTIFY 32

static struct {
    int created, coop;
    /* primary */
    int prim_made, prim_set;
    flds_wfx_t prim;
    /* secondary */
    int sec;
    uint8_t *buf;
    uint32_t size_bytes, size_frames, block, ch, sr, bits, is_float, caps;
    int locked; uint32_t lk_off, lk_n1, lk_n2;
    /* 再生 */
    int running; volatile int stop;
    pthread_t th; uint32_t ready;
    pthread_mutex_t mu;
    uint32_t cur_frame;             /* 停止中のカーソル (frames) */
    uint32_t base;                  /* 現 Play の開始位置 (frames) */
    uint64_t rd_hi; uint32_t rd_last;
    uint64_t conv_abs;              /* pump のみが書く (atomic) */
    /* notify */
    uint32_t nnot; uint64_t next[FLDS_MAX_NOTIFY]; uint32_t not_off[FLDS_MAX_NOTIFY];
    /* pump */
    uint32_t P, depth_cfg, T, latency_changes;
    float *pl[FLA_MAX_CH];
} D = { .mu = PTHREAD_MUTEX_INITIALIZER, .P = 256, .depth_cfg = 2 };

static void wake32(uint32_t *a) { __builtin_wasm_memory_atomic_notify((int *)a, 0x7fffffff); }

void flds_configure(uint32_t pump_frames, uint32_t depth) {
    if (D.sec) fla_failfast("flds_configure", "call before the secondary buffer is created");
    if (pump_frames < FLA_QUANTUM || pump_frames % FLA_QUANTUM || pump_frames > 4096) fla_failfast("flds_configure", "pump_frames must be a multiple of 128 in [128, 4096]");
    if (depth < 2 || depth > 8) fla_failfast("flds_configure", "depth in [2,8]");
    D.P = pump_frames; D.depth_cfg = depth;
}

FLDSHR flds_create(void) {
    if (D.created) return FLDSERR_ALLOCATED;
    D.created = 1;
    return FLDS_OK;
}
#define NEED_DS() do { if (!D.created) return FLDSERR_UNINITIALIZED; } while (0)

FLDSHR flds_set_cooperative_level(uint32_t level) {
    NEED_DS();
    if (level == FLDSSCL_EXCLUSIVE || level == FLDSSCL_WRITEPRIMARY)
        fla_failfast("flds_set_cooperative_level", "EXCLUSIVE/WRITEPRIMARY not supported (browser has no exclusive path)");
    if (level != FLDSSCL_NORMAL && level != FLDSSCL_PRIORITY) return FLDSERR_INVALIDPARAM;
    D.coop = (int)level;
    return FLDS_OK;
}

/* 受理する形式: PCM 16bit / IEEE float 32bit (WAVE_FORMAT_EXTENSIBLE の SubFormat も可)。FL の組立 0x674e10 / 0x674e50 と同形 */
static const uint8_t SUB_FLOAT[16] = { 3, 0, 0, 0, 0, 0, 0x10, 0, 0x80, 0, 0, 0xaa, 0, 0x38, 0x9b, 0x71 };
static const uint8_t SUB_PCM[16]   = { 1, 0, 0, 0, 0, 0, 0x10, 0, 0x80, 0, 0, 0xaa, 0, 0x38, 0x9b, 0x71 };

static int parse_fmt(const flds_wfx_t *w, uint32_t *ch, uint32_t *sr, uint32_t *bits, uint32_t *is_float) {
    if (!w) return 0;
    uint32_t tag = w->wFormatTag, bps = w->wBitsPerSample;
    int fl;
    if (tag == FLDS_WAVE_FORMAT_EXTENSIBLE) {
        if (w->cbSize < 22) return 0;
        if (!memcmp(w->SubFormat, SUB_FLOAT, 16)) fl = 1;
        else if (!memcmp(w->SubFormat, SUB_PCM, 16)) fl = 0;
        else return 0;
        if (w->wValidBitsPerSample > bps) return 0;
    } else if (tag == FLDS_WAVE_FORMAT_PCM) fl = 0;
    else if (tag == FLDS_WAVE_FORMAT_IEEE_FLOAT) fl = 1;
    else return 0;
    if (fl ? bps != 32 : bps != 16) return 0;
    if (w->nChannels < 1 || w->nChannels > FLA_MAX_CH) return 0;
    if (w->nSamplesPerSec < 8000 || w->nSamplesPerSec > 192000) return 0;
    if (w->nBlockAlign != w->nChannels * bps / 8 || w->nAvgBytesPerSec != w->nSamplesPerSec * w->nBlockAlign) return 0;
    *ch = w->nChannels; *sr = w->nSamplesPerSec; *bits = bps; *is_float = (uint32_t)fl;
    return 1;
}

FLDSHR flds_primary_set_format(const flds_wfx_t *wfx) {
    NEED_DS();
    if (!D.prim_made) return FLDSERR_INVALIDCALL;
    if (D.coop < (int)FLDSSCL_PRIORITY) return FLDSERR_PRIOLEVELNEEDED;
    uint32_t ch, sr, bits, fl;
    if (!parse_fmt(wfx, &ch, &sr, &bits, &fl)) return FLDSERR_BADFORMAT;
    if (D.sec) return FLDSERR_INVALIDCALL;   /* 再生系が開いている間は変更不可 (ring を作り直さない) */
    D.prim = *wfx; D.prim_set = 1;
    return FLDS_OK;
}
FLDSHR flds_primary_get_format(flds_wfx_t *out) {
    NEED_DS();
    if (!D.prim_made || !out) return FLDSERR_INVALIDPARAM;
    if (D.prim_set) { *out = D.prim; return FLDS_OK; }
    memset(out, 0, sizeof *out);   /* 既定: 48000Hz / 2ch / 16bit PCM */
    out->wFormatTag = FLDS_WAVE_FORMAT_PCM; out->nChannels = 2; out->nSamplesPerSec = 48000; out->wBitsPerSample = 16;
    out->nBlockAlign = 4; out->nAvgBytesPerSec = 48000 * 4;
    return FLDS_OK;
}

FLDSHR flds_create_sound_buffer(const flds_bufdesc_t *d) {
    NEED_DS();
    if (!d || d->dwSize < 20) return FLDSERR_INVALIDPARAM;
    if (d->dwFlags & FLDSBCAPS_PRIMARYBUFFER) {
        if (D.prim_made) return FLDSERR_ALLOCATED;
        D.prim_made = 1;
        return FLDS_OK;
    }
    if (D.sec) return FLDSERR_ALLOCATED;   /* FL は secondary を 1 本だけ作る (実測 CreateSoundBuffer×2 = primary + secondary) */
    if (d->dwFlags & FLDSBCAPS_LOCHARDWARE) return FLDSERR_ALLOCATED;   /* ハードウェアボイスなし */
    uint32_t ch, sr, bits, fl;
    if (!parse_fmt(d->lpwfxFormat, &ch, &sr, &bits, &fl)) return FLDSERR_BADFORMAT;
    if (D.prim_set) {   /* DS は primary 形式へミックスするが、本 shim は再サンプル/ch 変換をしない */
        uint32_t pch, psr, pb, pf;
        parse_fmt(&D.prim, &pch, &psr, &pb, &pf);
        if (pch != ch || psr != sr) return FLDSERR_BADFORMAT;
    }
    uint32_t block = ch * bits / 8;
    if (d->dwBufferBytes < 4 || d->dwBufferBytes % block) return FLDSERR_INVALIDPARAM;
    uint32_t frames = d->dwBufferBytes / block;
    if (frames < 2 * D.P) return FLDSERR_INVALIDPARAM;   /* pump 2 ブロック未満の極小バッファは非対応 */
    int rc = fla_open(sr, ch, 0, D.P, D.depth_cfg, FLA_F_DECLICK);
    if (rc != 0) return rc == FLA_E_BURST_TOO_LARGE ? FLDSERR_OUTOFMEMORY : FLDSERR_NODRIVER;
    D.T = fla_ctl()->depth * D.P;
    if (frames < D.T + 2 * D.P) { fla_close(); return FLDSERR_INVALIDPARAM; }   /* 確定済み領域 (T) + pump 余裕より小さい循環バッファは再生中に自分の未再生領域へ回り込む */
    D.buf = calloc(1, d->dwBufferBytes);
    for (uint32_t c = 0; c < ch; c++) D.pl[c] = calloc(D.P, sizeof(float));
    int ok = D.buf != NULL;
    for (uint32_t c = 0; c < ch; c++) ok = ok && D.pl[c] != NULL;
    if (!ok) {
        fla_close();
        free(D.buf); D.buf = NULL;
        for (uint32_t c = 0; c < ch; c++) { free(D.pl[c]); D.pl[c] = NULL; }
        return FLDSERR_OUTOFMEMORY;
    }
    D.size_bytes = d->dwBufferBytes; D.size_frames = frames; D.block = block; D.ch = ch; D.sr = sr; D.bits = bits; D.is_float = fl;
    D.caps = d->dwFlags; D.cur_frame = 0; D.nnot = 0; D.latency_changes = 0;
    fla_reset_indexes();
    D.sec = 1;
    return FLDS_OK;
}
#define NEED_SEC() do { NEED_DS(); if (!D.sec) return FLDSERR_INVALIDCALL; } while (0)

static uint64_t read_abs_locked(void) {
    uint32_t lo = LD(fla_ctl()->out_read);
    if (lo < D.rd_last) D.rd_hi++;
    D.rd_last = lo;
    return (D.rd_hi << 32) | lo;
}
static uint64_t read_abs(void) {
    pthread_mutex_lock(&D.mu);
    uint64_t r = read_abs_locked();
    pthread_mutex_unlock(&D.mu);
    return r;
}

FLDSHR flds_buf_get_current_position(uint32_t *play, uint32_t *write) {
    NEED_SEC();
    uint64_t base, rd, cv;
    int running;
    pthread_mutex_lock(&D.mu);
    running = D.running;
    base = running ? D.base : D.cur_frame;
    rd = running ? read_abs_locked() : 0;
    cv = running ? __atomic_load_n(&D.conv_abs, __ATOMIC_SEQ_CST) : 0;
    pthread_mutex_unlock(&D.mu);
    uint64_t p = (base + rd) % D.size_frames;
    uint64_t w = running ? (base + cv + D.P) % D.size_frames : p;
    if (play) *play = (uint32_t)(p * D.block);
    if (write) *write = (uint32_t)(w * D.block);
    return FLDS_OK;
}

FLDSHR flds_buf_set_current_position(uint32_t pos) {
    NEED_SEC();
    if (D.running) return FLDSERR_INVALIDCALL;   /* 再生中の移動は非対応 (FL は Play 前にのみ呼ぶ: 0x12afaf0) */
    if (pos >= D.size_bytes || pos % D.block) return FLDSERR_INVALIDPARAM;
    D.cur_frame = pos / D.block;
    return FLDS_OK;
}

FLDSHR flds_buf_get_status(uint32_t *st) {
    NEED_SEC();
    *st = D.running ? (FLDSBSTATUS_PLAYING | FLDSBSTATUS_LOOPING) : 0;
    return FLDS_OK;
}

FLDSHR flds_buf_lock(uint32_t off, uint32_t bytes, void **p1, uint32_t *n1, void **p2, uint32_t *n2, uint32_t flags) {
    NEED_SEC();
    if (!p1 || !n1) return FLDSERR_INVALIDPARAM;
    if (D.locked) return FLDSERR_INVALIDCALL;
    if (flags & FLDSBLOCK_ENTIREBUFFER) { off = 0; bytes = D.size_bytes; }
    else if (flags & FLDSBLOCK_FROMWRITECURSOR) { uint32_t w; flds_buf_get_current_position(NULL, &w); off = w; }
    if (off >= D.size_bytes || bytes > D.size_bytes) return FLDSERR_INVALIDPARAM;
    uint32_t a = D.size_bytes - off < bytes ? D.size_bytes - off : bytes;
    *p1 = D.buf + off; *n1 = a;
    if (p2) *p2 = a < bytes ? (void *)D.buf : NULL;
    if (n2) *n2 = bytes - a;
    D.locked = 1; D.lk_off = off; D.lk_n1 = a; D.lk_n2 = bytes - a;
    return FLDS_OK;
}
FLDSHR flds_buf_unlock(void *p1, uint32_t n1, void *p2, uint32_t n2) {
    NEED_SEC();
    if (!D.locked) return FLDSERR_INVALIDCALL;
    if (p1 != (void *)(D.buf + D.lk_off) || n1 > D.lk_n1 || n2 > D.lk_n2 || (n2 && p2 != (void *)D.buf)) return FLDSERR_INVALIDPARAM;
    D.locked = 0;
    return FLDS_OK;
}

FLDSHR flds_notify_set_positions(uint32_t n, const flds_notify_pos_t *pos) {
    NEED_SEC();
    if (!(D.caps & FLDSBCAPS_CTRLPOSITIONNOTIFY)) return FLDSERR_INVALIDCALL;
    if (D.running) return FLDSERR_INVALIDCALL;
    if (n > FLDS_MAX_NOTIFY || (n && !pos)) return FLDSERR_INVALIDPARAM;
    for (uint32_t i = 0; i < n; i++) if (pos[i].offset >= D.size_bytes) return FLDSERR_INVALIDPARAM;
    for (uint32_t i = 0; i < n; i++) D.not_off[i] = pos[i].offset / D.block;
    D.nnot = n;
    return FLDS_OK;
}

static void convert_block(uint32_t frames) {
    uint64_t cv = __atomic_load_n(&D.conv_abs, __ATOMIC_SEQ_CST);
    uint32_t p = (uint32_t)((D.base + cv) % D.size_frames), ch = D.ch;
    for (uint32_t i = 0; i < frames; i++) {
        const uint8_t *s = D.buf + (size_t)p * D.block;
        if (D.is_float) for (uint32_t c = 0; c < ch; c++) memcpy(&D.pl[c][i], s + c * 4, 4);
        else for (uint32_t c = 0; c < ch; c++) { int16_t v; memcpy(&v, s + c * 2, 2); D.pl[c][i] = (float)v * (1.0f / 32768.0f); }
        if (++p == D.size_frames) p = 0;
    }
    fla_out_write((const float *const *)D.pl, frames);
    __atomic_store_n(&D.conv_abs, cv + frames, __ATOMIC_SEQ_CST);
}

static void *pump_fn(void *arg) {
    (void)arg;
    fla_ctl_t *c = fla_ctl();
    uint32_t P = D.P, T = D.T, T0 = T, esc = 0, last_u = 0;
    while (__atomic_load_n(&D.conv_abs, __ATOMIC_SEQ_CST) < T) convert_block(P);   /* prefill (go 前) */
    fla_go();
    __atomic_store_n(&D.ready, 1, __ATOMIC_SEQ_CST);
    wake32(&D.ready);
    const uint32_t Tmax = c->ring_frames - 2 * P;
    while (!D.stop) {
        /* 目標充填 T の動的調整は flasio と同則: burst*1.25+P を下限に、underrun 毎に +P */
        uint32_t burst = LD(c->burst_obs);
        uint32_t need = (burst + burst / 4 + P + P - 1) / P * P;
        uint32_t u = LD(c->underruns);
        if (u != last_u) { esc += P; last_u = u; }
        uint32_t Tn = (need > T0 ? need : T0) + esc;
        if (Tn > Tmax) Tn = Tmax;
        if (Tn > T) { T = Tn; c->depth = T / P; D.T = T; D.latency_changes++; }
        int rc = fla_out_wait_fill_le(T - P, 50);
        if (rc < 0) break;
        if (rc == 1 || D.stop) continue;
        convert_block(P);
        read_abs();   /* out_read の 32bit 折返しを取りこぼさないため定期的に拡張値を更新 */
    }
    return NULL;
}

FLDSHR flds_buf_play(uint32_t reserved, uint32_t priority, uint32_t flags) {
    NEED_SEC();
    (void)reserved; (void)priority;
    if (!(flags & FLDSBPLAY_LOOPING)) fla_failfast("flds_buf_play", "non-looping Play not supported (FL passes DSBPLAY_LOOPING)");
    if (D.running) return FLDS_OK;
    fla_halt();
    fla_reset_indexes();
    pthread_mutex_lock(&D.mu);
    D.base = D.cur_frame; D.rd_hi = 0; D.rd_last = 0;
    __atomic_store_n(&D.conv_abs, 0, __ATOMIC_SEQ_CST);
    for (uint32_t i = 0; i < D.nnot; i++) {
        uint32_t d = (D.not_off[i] + D.size_frames - D.base) % D.size_frames;
        D.next[i] = d ? d : D.size_frames;   /* 開始位置自身は「通過」に数えない */
    }
    D.stop = 0; D.ready = 0;
    D.running = 1;
    pthread_mutex_unlock(&D.mu);
    if (pthread_create(&D.th, NULL, pump_fn, NULL) != 0) { D.running = 0; return FLDSERR_GENERIC; }
    while (!__atomic_load_n(&D.ready, __ATOMIC_SEQ_CST))
        __builtin_wasm_memory_atomic_wait32((int *)&D.ready, 0, 50 * 1000000LL);
    return FLDS_OK;
}

FLDSHR flds_buf_stop(void) {
    NEED_SEC();
    if (!D.running) return FLDS_OK;
    D.stop = 1;
    wake32(&fla_ctl()->out_read);
    pthread_join(D.th, NULL);
    fla_halt();
    pthread_mutex_lock(&D.mu);
    uint64_t rd = read_abs_locked();
    D.cur_frame = (uint32_t)((D.base + rd) % D.size_frames);
    D.running = 0;
    pthread_mutex_unlock(&D.mu);
    return FLDS_OK;
}

int flds_wait_notify(uint32_t timeout_ms, uint32_t *mask) {
    NEED_SEC();
    double t0 = emscripten_get_now();
    static uint32_t dummy;
    for (;;) {
        uint32_t m = 0; uint64_t soonest = ~0ull, rd;
        pthread_mutex_lock(&D.mu);
        if (!D.running) { pthread_mutex_unlock(&D.mu); return -1; }
        rd = read_abs_locked();
        for (uint32_t i = 0; i < D.nnot; i++) {
            if (rd >= D.next[i]) { m |= 1u << i; D.next[i] += (uint64_t)D.size_frames * (1 + (rd - D.next[i]) / D.size_frames); }   /* 取りこぼしは合体 */
            if (D.next[i] < soonest) soonest = D.next[i];
        }
        pthread_mutex_unlock(&D.mu);
        if (m) { if (mask) *mask = m; return 0; }
        double elapsed = emscripten_get_now() - t0;
        if (elapsed >= timeout_ms) return 1;
        double ms = soonest == ~0ull ? 4.0 : (double)(soonest - rd) * 1000.0 / D.sr * 0.5;
        if (ms < 0.25) ms = 0.25;
        if (ms > 4.0) ms = 4.0;
        if (ms > timeout_ms - elapsed) ms = timeout_ms - elapsed;
        __builtin_wasm_memory_atomic_wait32((int *)&dummy, 0, (int64_t)(ms * 1e6));
    }
}

void flds_get_stats(flds_stats_t *s) {
    memset(s, 0, sizeof *s);
    if (!D.sec) return;
    fla_ctl_t *c = fla_ctl();
    s->pump_frames = D.P; s->depth = D.T / D.P; s->T = D.T; s->ring_frames = c->ring_frames;
    s->underruns = LD(c->underruns); s->silence_frames = LD(c->silence_frames); s->quanta = LD(c->quanta);
    s->latency_changes = D.latency_changes;
    s->bytes_unlocked = (uint64_t)__atomic_load_n(&D.conv_abs, __ATOMIC_SEQ_CST) * D.block;
}

FLDSHR flds_release_buffer(void) {
    if (!D.sec) return FLDS_OK;
    flds_buf_stop();
    fla_close();
    free(D.buf); D.buf = NULL;
    for (uint32_t c = 0; c < D.ch; c++) { free(D.pl[c]); D.pl[c] = NULL; }
    D.sec = 0; D.locked = 0; D.nnot = 0;
    return FLDS_OK;
}
FLDSHR flds_release(void) {
    flds_release_buffer();
    uint32_t P = D.P, dc = D.depth_cfg;
    memset(&D, 0, sizeof D);
    D.mu = (pthread_mutex_t)PTHREAD_MUTEX_INITIALIZER;
    D.P = P; D.depth_cfg = dc;
    return FLDS_OK;
}
