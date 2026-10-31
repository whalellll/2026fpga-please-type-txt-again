#ifndef PIKAFISH_EMBEDDED_H
#define PIKAFISH_EMBEDDED_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    PIKAFISH_EMBEDDED_IDLE = 0,
    PIKAFISH_EMBEDDED_LOADING = 1,
    PIKAFISH_EMBEDDED_READY = 2,
    PIKAFISH_EMBEDDED_FAILED = 3
};

typedef struct {
    char bestmove[8];
    char ponder[8];
    int32_t score_cp;
    uint32_t nodes;
    uint32_t wins;
    uint32_t draws;
    uint32_t losses;
    uint32_t elapsed_ms;
    int have_score;
    int have_wdl;
} pikafish_embedded_result_t;

int pikafish_embedded_start(const char *model_path, unsigned int hash_mib);
int pikafish_embedded_status(void);
int pikafish_embedded_search(const char *fen, unsigned int movetime_ms,
                             pikafish_embedded_result_t *result);
int pikafish_embedded_search_nodes(const char *fen, uint64_t nodes,
                                   pikafish_embedded_result_t *result);
int pikafish_embedded_search_nodes_with_moves(const char *fen, const char *moves,
                                              uint64_t nodes,
                                              pikafish_embedded_result_t *result);
void pikafish_embedded_new_game(void);
void pikafish_embedded_stop(void);

#ifdef __cplusplus
}
#endif

#endif
