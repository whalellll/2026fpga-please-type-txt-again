#define _POSIX_C_SOURCE 200809L

#include "pango_audio_uapi.h"
#include "xqvoice_assembler.h"
#include "xqvoice_client.h"
#include "xqvoice_features.h"
#include "xqvoice_model.h"
#include "xqvoice_accel.h"

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define DEFAULT_AUDIO_DEVICE "/dev/pango-audio0"
#define DEFAULT_MODEL_PATH "/opt/xqvoice/tts-candidate.xqt"
#define CLIENT_SOCKET_TEMPLATE "/run/xqvoice-recognizer-%ld.sock"
#define CHUNK_SAMPLES 160u
#define PREROLL_CHUNKS 10u
#define START_CHUNKS 3u
#define END_SILENCE_CHUNKS 30u
#define MIN_UTTERANCE_CHUNKS 30u
#define COMMAND_TIMEOUT_CHUNKS 500u

static volatile sig_atomic_t stop_requested;

static void on_signal(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static uint32_t mean_absolute(const int16_t *samples, size_t count)
{
    uint64_t sum = 0;
    size_t index;

    for (index = 0; index < count; ++index) {
        int32_t value = samples[index];
        sum += value < 0 ? (uint32_t)(-value) : (uint32_t)value;
    }
    return (uint32_t)(sum / count);
}

static int read_chunk(int fd, int16_t samples[CHUNK_SAMPLES])
{
    uint8_t *output = (uint8_t *)samples;
    size_t bytes = CHUNK_SAMPLES * sizeof(samples[0]);
    size_t done = 0;

    while (done < bytes && !stop_requested) {
        ssize_t received = read(fd, output + done, bytes - done);
        if (received > 0)
            done += (size_t)received;
        else if (received < 0 && errno == EINTR)
            continue;
        else
            return 0;
    }
    return done == bytes;
}

static void copy_preroll(const int16_t ring[PREROLL_CHUNKS][CHUNK_SAMPLES],
                         unsigned int next, int16_t *utterance,
                         size_t *utterance_samples)
{
    unsigned int chunk;

    *utterance_samples = 0;
    for (chunk = 0; chunk < PREROLL_CHUNKS; ++chunk) {
        unsigned int source = (next + chunk) % PREROLL_CHUNKS;
        memcpy(utterance + *utterance_samples, ring[source],
               CHUNK_SAMPLES * sizeof(int16_t));
        *utterance_samples += CHUNK_SAMPLES;
    }
}

static void publish_display(xqvoice_client_t *client, uint32_t *sequence,
                             xqvoice_display_state_t state,
                             const uint8_t *tokens, uint8_t count,
                             uint16_t score)
{
    xqvoice_command_t event;
    unsigned int index;
    int sent;
    memset(&event, 0, sizeof(event));
    event.sequence = ++*sequence;
    event.type = XQVOICE_COMMAND_DISPLAY;
    event.display_state = state;
    event.confidence_permille = score;
    event.token_count = count;
    for (index = 0; index < count; ++index)
        event.tokens[index] = tokens[index];
    sent = xqvoice_client_send(client, &event, NULL, 0, 0);
    printf("XQVOICE_DISPLAY sequence=%u state=%s score=%u sent=%d text=",
           event.sequence, xqvoice_display_state_name(state), score, sent);
    for (index = 0; index < count; ++index)
        fputs(xqvoice_token_text(tokens[index]), stdout);
    putchar('\n');
}

int main(int argc, char **argv)
{
    const char *device_path = argc > 1 ? argv[1] : DEFAULT_AUDIO_DEVICE;
    const char *model_path = argc > 2 ? argv[2] : DEFAULT_MODEL_PATH;
    uint32_t start_threshold = argc > 3 ? (uint32_t)strtoul(argv[3], NULL, 10) : 200u;
    uint32_t stop_threshold = argc > 4 ? (uint32_t)strtoul(argv[4], NULL, 10) : 160u;
    uint32_t token_threshold = argc > 5 ? (uint32_t)strtoul(argv[5], NULL, 10) : 500u;
    int16_t preroll[PREROLL_CHUNKS][CHUNK_SAMPLES];
    int16_t utterance[XQVOICE_MAX_SAMPLES];
    int8_t features[XQVOICE_MAX_FRAMES * XQVOICE_FEATURE_BINS];
    xqvoice_model_t model;
    xqvoice_client_t client;
    xqvoice_assembler_t assembler;
    char client_socket[64];
    struct pango_audio_info info;
    struct pango_audio_stats stats;
    char error[128];
    unsigned int preroll_next = 0;
    unsigned int voiced_chunks = 0;
    unsigned int silent_chunks = 0;
    size_t utterance_samples = 0;
    uint32_t capture_overflows = 0;
    uint32_t sequence = 0;
    uint32_t stream_chunks = 0;
    uint32_t last_token_chunk = 0;
    int capturing = 0;
    int audio_fd;
    const char *backend = getenv("XQVOICE_BACKEND");
    int hardware = backend && strcmp(backend,"hardware")==0;
    xqvoice_accel_t accelerator;
    uint32_t chunk_end=0,utterance_begin=0;
    unsigned warmup_chunks=0;

    setvbuf(stdout, NULL, _IOLBF, 0);

    if (!start_threshold || stop_threshold >= start_threshold ||
        token_threshold > 1000u) {
        fprintf(stderr, "xqvoice: invalid VAD thresholds\n");
        return 2;
    }
    if (!xqvoice_model_load(model_path, &model, error, sizeof(error))) {
        fprintf(stderr, "xqvoice: model load failed: %s\n", error);
        return 3;
    }
    memset(&accelerator,0,sizeof(accelerator));accelerator.fd=-1;
    if(hardware) {
        if(!xqvoice_accel_open(&accelerator,"/dev/pango-voice0",&model)){
            perror("xqvoice: open accelerator");xqvoice_model_unload(&model);return 4;
        }
        audio_fd=-1;
    } else audio_fd = open(device_path, O_RDONLY);
    if (!hardware && audio_fd < 0) {
        perror("xqvoice: open audio");
        xqvoice_model_unload(&model);
        return 4;
    }
    memset(&info, 0, sizeof(info));
    if (!hardware && (ioctl(audio_fd, PANGO_AUDIO_IOC_GET_INFO, &info) < 0 ||
        info.abi_version != PANGO_AUDIO_ABI_VERSION ||
        info.device_id != PANGO_AUDIO_ID ||
        info.device_version != PANGO_AUDIO_VERSION ||
        info.sample_rate_hz != 16000 || info.channels != 1 ||
        info.sample_format != PANGO_AUDIO_FORMAT_S16_LE)) {
        fprintf(stderr, "xqvoice: audio ABI mismatch\n");
        close(audio_fd);
        xqvoice_model_unload(&model);
        return 5;
    }
    (void)snprintf(client_socket, sizeof(client_socket),
                   CLIENT_SOCKET_TEMPLATE, (long)getpid());
    if (!xqvoice_client_open(&client, client_socket, XQVOICE_GUI_SOCKET)) {
        perror("xqvoice: command socket");
        close(audio_fd);
        xqvoice_accel_close(&accelerator);
        xqvoice_model_unload(&model);
        return 6;
    }
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    memset(preroll, 0, sizeof(preroll));
    xqvoice_assembler_reset(&assembler);
    if(!hardware)(void)ioctl(audio_fd, PANGO_AUDIO_IOC_CLEAR);
    printf("XQVOICE_READY backend=%s model=%s audio=%s sample_rate=16000 "
           "mode=display-only single-token start=%u stop=%u token_threshold=%u\n",
           hardware?"hardware":"cpu",model_path, device_path, start_threshold, stop_threshold,
           token_threshold);
    publish_display(&client, &sequence, XQVOICE_DISPLAY_LISTENING,
                    NULL, 0, 0);

    while (!stop_requested) {
        int16_t chunk[CHUNK_SAMPLES];
        uint32_t level;

        if(hardware){
            memset(chunk,0,sizeof(chunk));
            if(!xqvoice_accel_level(&accelerator,&level,&chunk_end))break;
        } else {
            if(!read_chunk(audio_fd,chunk))break;
            level=mean_absolute(chunk,CHUNK_SAMPLES);chunk_end+=160;
        }
        ++stream_chunks;
        if (xqvoice_assembler_pending(&assembler) &&
            stream_chunks - last_token_chunk >= COMMAND_TIMEOUT_CHUNKS) {
            xqvoice_assembler_reset(&assembler);
            printf("XQVOICE_ASSEMBLER_RESET reason=timeout\n");
            publish_display(&client, &sequence, XQVOICE_DISPLAY_LISTENING,
                            NULL, 0, 0);
        }
        memcpy(preroll[preroll_next], chunk, sizeof(chunk));
        preroll_next = (preroll_next + 1u) % PREROLL_CHUNKS;
        /* Match the full ten-chunk preroll on both paths. */
        if(warmup_chunks<PREROLL_CHUNKS)++warmup_chunks;
        if(warmup_chunks<PREROLL_CHUNKS)continue;

        if (!capturing) {
            voiced_chunks = level >= start_threshold ? voiced_chunks + 1u : 0u;
            if (voiced_chunks < START_CHUNKS)
                continue;
            copy_preroll(preroll, preroll_next, utterance,
                         &utterance_samples);
            utterance_begin=chunk_end-PREROLL_CHUNKS*CHUNK_SAMPLES;
            memset(&stats, 0, sizeof(stats));
            if(hardware)stats.fifo_overflows=accelerator.overflows+accelerator.discontinuities;
            else if (ioctl(audio_fd, PANGO_AUDIO_IOC_GET_STATS, &stats) < 0)
                break;
            capture_overflows = stats.fifo_overflows;
            silent_chunks = 0;
            capturing = 1;
            publish_display(&client, &sequence, XQVOICE_DISPLAY_CAPTURING,
                            assembler.tokens, assembler.count, 0);
            continue;
        }

        if (utterance_samples + CHUNK_SAMPLES <= XQVOICE_MAX_SAMPLES) {
            memcpy(utterance + utterance_samples, chunk, sizeof(chunk));
            utterance_samples += CHUNK_SAMPLES;
        }
        silent_chunks = level <= stop_threshold ? silent_chunks + 1u : 0u;
        if (utterance_samples < MIN_UTTERANCE_CHUNKS * CHUNK_SAMPLES ||
            (silent_chunks < END_SILENCE_CHUNKS &&
             utterance_samples + CHUNK_SAMPLES <= XQVOICE_MAX_SAMPLES))
            continue;

        memset(&stats, 0, sizeof(stats));
        if(hardware)stats.fifo_overflows=accelerator.overflows+accelerator.discontinuities;
        else if (ioctl(audio_fd, PANGO_AUDIO_IOC_GET_STATS, &stats) < 0)
            break;
        if (stats.fifo_overflows != capture_overflows) {
            fprintf(stderr, "XQVOICE_DROP reason=audio-overflow before=%u after=%u\n",
                    capture_overflows, stats.fifo_overflows);
            xqvoice_assembler_reset(&assembler);
            publish_display(&client, &sequence, XQVOICE_DISPLAY_OVERFLOW,
                            NULL, 0, 0);
        } else {
            size_t frames = hardware ? xqvoice_accel_features(&accelerator,utterance_begin,
                chunk_end,features,sizeof(features)) : xqvoice_extract_features(
                utterance, utterance_samples, &model, features,
                sizeof(features));
            uint8_t token = 0;
            uint16_t confidence = 0;

            if(hardware)(void)snprintf(error,sizeof(error),"hardware inference failed or selected blank");

            if (!frames)
                (void)snprintf(error, sizeof(error),
                               "feature extraction failed");
            if (frames && (hardware ? xqvoice_accel_infer(&accelerator,features,frames,&token,&confidence) : xqvoice_model_infer_token(
                              &model, features, frames, &token, &confidence,
                              error, sizeof(error)))) {
                xqvoice_command_t command;
                int assembled;

                printf("XQVOICE_TOKEN token=%u confidence=%u slot=%u\n",
                       token, confidence, assembler.count);
                if (confidence < token_threshold) {
                    publish_display(&client, &sequence,
                                    XQVOICE_DISPLAY_LOW_CONFIDENCE,
                                    &token, 1, confidence);
                    xqvoice_assembler_reset(&assembler);
                    printf("XQVOICE_REJECT reason=low-token-confidence "
                           "token=%u confidence=%u\n", token, confidence);
                } else {
                    uint8_t preview[4];
                    uint8_t count;
                    if (token >= 22 || (token >= 1 && token <= 9)) {
                        preview[0] = token;
                        count = 1;
                    } else {
                        count = assembler.count;
                        memcpy(preview, assembler.tokens, count);
                        preview[count++] = token;
                    }
                    assembled = xqvoice_assembler_feed(
                        &assembler, token, confidence, sequence + 1u,
                        &command, error, sizeof(error));
                    if (assembled == 0) {
                        publish_display(&client, &sequence,
                                        XQVOICE_DISPLAY_PARTIAL,
                                        preview, count, confidence);
                        last_token_chunk = stream_chunks;
                        printf("XQVOICE_ASSEMBLER_WAIT slots=%u\n",
                               assembler.count);
                    } else if (assembled > 0) {
                        publish_display(&client, &sequence,
                                        XQVOICE_DISPLAY_COMPLETE,
                                        preview, count,
                                        command.confidence_permille);
                        printf("XQVOICE_COMMAND_NOT_EXECUTED type=%u\n",
                               command.type);
                    } else {
                        publish_display(&client, &sequence,
                                        XQVOICE_DISPLAY_REJECTED,
                                        &token, 1, confidence);
                        printf("XQVOICE_REJECT reason=%s token=%u\n",
                               error, token);
                    }
                }
            } else {
                xqvoice_assembler_reset(&assembler);
                publish_display(&client, &sequence, XQVOICE_DISPLAY_ERROR,
                                NULL, 0, 0);
                printf("XQVOICE_REJECT reason=%s frames=%u\n", error,
                       (unsigned int)frames);
            }
        }
        capturing = 0;
        utterance_samples = 0;
        voiced_chunks = 0;
        silent_chunks = 0;
        if(!hardware){
            (void)ioctl(audio_fd, PANGO_AUDIO_IOC_CLEAR);
            chunk_end=0;warmup_chunks=0;
        }
    }

    xqvoice_client_close(&client);
    close(audio_fd);
    xqvoice_accel_close(&accelerator);
    xqvoice_model_unload(&model);
    puts("XQVOICE_STOPPED");
    return stop_requested ? 0 : 7;
}
