/*
 * Host acceptance for official NNUE decode artifacts.
 * Loads mlp_stack00.pfb1 and runs Stage-B propagate on a fixed u8 pattern.
 */

#include "../pikafish_mlp_stage_b/pf_mlp_stage_b.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#pragma pack(push, 1)
typedef struct {
    uint32_t magic;
    uint32_t version;
    uint16_t l1;
    uint16_t l2;
    uint16_t l3;
    uint16_t weight_scale_bits;
    uint32_t flags;
    uint32_t crc32;
} pfb1_file_header_t;

typedef struct {
    uint32_t magic;
    uint32_t version;
    uint16_t l1;
    uint16_t tile_width;
    uint16_t tile_count;
    uint16_t max_active;
    uint32_t feature_rows;
    uint32_t flags;
    uint32_t weight_bytes;
    uint32_t crc32;
} pfa1_file_header_t;
#pragma pack(pop)

static int g_fail;
static int g_pass;

static void expect(int ok, const char *name) {
    if (ok) {
        printf("PASS %s\n", name);
        g_pass++;
    } else {
        printf("FAIL %s\n", name);
        g_fail++;
    }
}

static unsigned char *read_file(const char *path, size_t *out_len) {
    FILE *f = fopen(path, "rb");
    unsigned char *buf;
    long sz;
    if (!f)
        return NULL;
    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return NULL;
    }
    sz = ftell(f);
    if (sz < 0) {
        fclose(f);
        return NULL;
    }
    rewind(f);
    buf = (unsigned char *)malloc((size_t)sz);
    if (!buf) {
        fclose(f);
        return NULL;
    }
    if (fread(buf, 1, (size_t)sz, f) != (size_t)sz) {
        free(buf);
        fclose(f);
        return NULL;
    }
    fclose(f);
    *out_len = (size_t)sz;
    return buf;
}

static int pfa1_header_ok(
    const pfa1_file_header_t *h, uint32_t expect_rows, size_t file_len) {
    if (h->magic != 0x31414650u || h->version != 0x00010000u)
        return 0;
    if (h->l1 != 1024 || h->tile_width != 256 || h->tile_count != 4)
        return 0;
    if (h->feature_rows != expect_rows)
        return 0;
    if (h->weight_bytes != expect_rows * 1024u)
        return 0;
    if ((h->flags & 1u) == 0u)
        return 0;
    if (file_len != sizeof(pfa1_file_header_t) + (size_t)h->weight_bytes)
        return 0;
    return 1;
}

static int check_pfa1(const char *path, uint32_t expect_rows) {
    size_t len = 0;
    unsigned char *buf = read_file(path, &len);
    const pfa1_file_header_t *hdr;
    int ok;
    if (!buf)
        return 0;
    if (len < sizeof(pfa1_file_header_t)) {
        free(buf);
        return 0;
    }
    hdr = (const pfa1_file_header_t *)buf;
    ok = pfa1_header_ok(hdr, expect_rows, len);
    free(buf);
    return ok;
}

static int load_pfb1(const char *path, pf_mlp_model_t *model, unsigned char **owned) {
    size_t len = 0;
    unsigned char *buf = read_file(path, &len);
    const pfb1_file_header_t *hdr;
    const int8_t *p;
    size_t need;
    const int8_t *fc0_w;
    const int32_t *fc0_b;
    const int8_t *fc1_w;
    const int32_t *fc1_b;
    const int8_t *fc2_w;
    const int32_t *fc2_b;

    if (!buf)
        return 0;
    if (len < sizeof(pfb1_file_header_t)) {
        free(buf);
        return 0;
    }
    hdr = (const pfb1_file_header_t *)buf;
    if (!pf_mlp_pack_header_valid((const pf_mlp_pack_header_t *)hdr)) {
        free(buf);
        return 0;
    }

    need = sizeof(pfb1_file_header_t)
         + (size_t)PF_MLP_L2 * PF_MLP_L1
         + (size_t)PF_MLP_L2 * sizeof(int32_t)
         + (size_t)PF_MLP_L3 * PF_MLP_FC1_IN
         + (size_t)PF_MLP_L3 * sizeof(int32_t)
         + (size_t)PF_MLP_FC2_IN
         + sizeof(int32_t);
    if (len != need) {
        printf("INFO pfb1 size got=%zu expect=%zu\n", len, need);
        free(buf);
        return 0;
    }

    p = (const int8_t *)(buf + sizeof(pfb1_file_header_t));
    fc0_w = p;
    fc0_b = (const int32_t *)(fc0_w + PF_MLP_L2 * PF_MLP_L1);
    fc1_w = (const int8_t *)(fc0_b + PF_MLP_L2);
    fc1_b = (const int32_t *)(fc1_w + PF_MLP_L3 * PF_MLP_FC1_IN);
    fc2_w = (const int8_t *)(fc1_b + PF_MLP_L3);
    fc2_b = (const int32_t *)(fc2_w + PF_MLP_FC2_IN);

    if (!pf_mlp_model_bind(model, (const pf_mlp_pack_header_t *)hdr,
                           fc0_w, fc0_b, fc1_w, fc1_b, fc2_w, fc2_b)) {
        free(buf);
        return 0;
    }
    *owned = buf;
    return 1;
}

int main(int argc, char **argv) {
    const char *outdir = (argc > 1) ? argv[1] : "out";
    char path[512];
    pf_mlp_model_t model;
    unsigned char *owned = NULL;
    uint8_t *x;
    int32_t score = 0;
    int i;

    g_fail = 0;
    g_pass = 0;
    memset(&model, 0, sizeof(model));

    snprintf(path, sizeof(path), "%s/mlp_stack00.pfb1", outdir);
    expect(load_pfb1(path, &model, &owned), "load_mlp_stack00");

    snprintf(path, sizeof(path), "%s/official_psq.pfa1", outdir);
    expect(check_pfa1(path, 16536u), "pfa1_psq_header");

    snprintf(path, sizeof(path), "%s/official_threat.pfa1", outdir);
    expect(check_pfa1(path, 45547u), "pfa1_threat_header");

    if (owned) {
        x = (uint8_t *)malloc(PF_MLP_L1);
        if (!x) {
            expect(0, "alloc_x");
        } else {
            for (i = 0; i < (int)PF_MLP_L1; i++)
                x[i] = (uint8_t)(i & 127);
            expect(pf_mlp_propagate(&model, x, NULL, NULL, &score) != 0, "propagate");
            printf("INFO SCORE_STACK0=%d\n", (int)score);
            free(x);
        }
        free(owned);
    }

    printf("SUMMARY pass=%d fail=%d\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
