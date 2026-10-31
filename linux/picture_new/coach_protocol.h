#ifndef XQCOACH_PROTOCOL_H
#define XQCOACH_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>

#define XQCOACH_MAX_CANDIDATES 300u
#define XQCOACH_PACKET_BYTES 65536u
#define XQCOACH_BACKEND "rv32-v321-coach"
#define XQCOACH_CANCELLED 9u
#define XQCOACH_IDLE "XQ_COACH_IDLE\n"

typedef struct {
    uint64_t token;
    uint32_t frame,crc;
    char backend[32];
} xqcoach_identity;
typedef struct {
    uint8_t class_id,file,rank; /* XQV classes; red home rank=0. */
    uint16_t confidence;       /* floor(real fused score * 1000), not a constant. */
    float score,x0,y0,x1,y1;
} xqcoach_candidate;
typedef struct {
    xqcoach_identity identity;
    unsigned status,count,estimated; /* Strict status0 and estimated status5 remain distinct. */
    double corners[4][2];  /* Original GUI a0,i0,i9,a9 order, 1280x720 pixels. */
    xqcoach_candidate candidates[XQCOACH_MAX_CANDIDATES];
} xqcoach_result;
typedef enum {
    XQCOACH_INVALID=-1, XQCOACH_REJECTED=0, XQCOACH_ACCEPTED=1
} xqcoach_parse_status;

int xqcoach_identity_init(xqcoach_identity *,uint64_t token,uint32_t frame,uint32_t raw_crc);
size_t xqcoach_encode_request(const xqcoach_identity *,char *,size_t);
int xqcoach_parse_request(const char *,size_t,xqcoach_identity *);
/* Producer boundary only: legacy native geometry stages 2/5/6 share the
 * coach wire's retryable geometry status 5. Diagnostics retain native stages.
 * Graph/driver failures 1/3/4 and raw-frame CRC failure 7 stay failures. */
unsigned xqcoach_native_status(unsigned native_status);
/* Result body has an independent CRC32. Old XQ_MODEL_RESULT_V1/FEN packets
 * are never accepted. Every returned candidate remains un-repaired; caller
 * must run delete-only xy_repair, then legality, before recommending a move.
 * On INVALID or REJECTED, *out is byte-for-byte untouched (keep prior board).
 * remote_status is updated only after a fully validated packet.
 * Status 9 is an empty release/cancellation acknowledgement, with the old
 * verified identity, only after all work for that request has returned.
 * A resident client unlinks request.txt then waits for both status 9 and the
 * flushed XQ_COACH_IDLE line before publishing another request. */
size_t xqcoach_encode_result(const xqcoach_result *,char *,size_t);
xqcoach_parse_status xqcoach_parse_result(const char *,size_t,const xqcoach_identity *,
                                          xqcoach_result *out,unsigned *remote_status);
int xqcoach_write_result_atomic(const char *path,const xqcoach_result *);
/* Separate unmapped diagnostic wire. Only status5, nonempty candidates and
 * file=rank=255 are allowed. Never accepted by parse_result or used as a board. */
size_t xqcoach_encode_partial(const xqcoach_result *,char *,size_t);
xqcoach_parse_status xqcoach_parse_partial(const char *,size_t,const xqcoach_identity *,xqcoach_result *);
int xqcoach_write_partial_atomic(const char *,const xqcoach_result *);
xqcoach_parse_status xqcoach_read_result(const char *path,const xqcoach_identity *,
                                         xqcoach_result *,unsigned *remote_status);
#endif
