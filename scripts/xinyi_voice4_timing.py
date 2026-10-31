"""Explicit optional r17 timing overlay for pinned voice_3 CPU60 sources.

Only the software-observed first block of the confirmed VAD-start run is timed;
it is neither the listening start nor a physical acoustic timestamp.
"""


def adapt(name, data):
    s = data.decode().replace('\r', '')

    def once(old, new):
        nonlocal s
        assert s.count(old) == 1, (name, 'timing overlay anchor')
        s = s.replace(old, new, 1)

    if name == 'xqvoice_capture.h':
        old = '    unsigned frames,max_backlog_frames,paced,streamed;'
        once(old, old + '\n#if XINYI_BATTLE_R17\n    uint64_t utterance_start_us;\n#endif')
    elif name == 'xqvoice_capture.c':
        helper = '''#if XINYI_BATTLE_R17
/* First block of the original consecutive VAD-start run, observed in software.
 * Publish only after the original three-block activation condition succeeds. */
static void capture_utterance_start(xqvoice_stream_metrics *metrics,const xqvoice_capture_state *state,
                                   int was_active,uint64_t *candidate,uint64_t stamp)
{
    if(was_active)return;
    if(state->start_run==1)*candidate=stamp;
    else if(!state->start_run)*candidate=0;
    if(state->active && metrics)metrics->utterance_start_us=*candidate;
}
#endif
'''
        once('static int capture_features(', helper + 'static int capture_features(')
        old = '    uint64_t capture_started=xqvp_now(),feature_started;'
        once(old, old + '\n#if XINYI_BATTLE_R17\n    uint64_t utterance_candidate=0;\n#endif')
        old = '            rc=xqvoice_capture_feed(&state,decoded);used=0;'
        once(old, old + '\n#if XINYI_BATTLE_R17\n            capture_utterance_start(metrics,&state,was_active,&utterance_candidate,stream_wall_us());\n#endif')
    elif name == 'xqvoice_stream.inc':
        old = '    uint64_t deadline=0,capture_started=xqvp_now();struct timespec idle={0,500000};'
        once(old, old + '\n#if XINYI_BATTLE_R17\n    uint64_t utterance_candidate=0;\n#endif')
        old = '            rc=xqvoice_capture_feed(&s->state,decoded);used=0;'
        once(old, old + '\n#if XINYI_BATTLE_R17\n            capture_utterance_start(s->metrics,&s->state,was_active,&utterance_candidate,stream_wall_us());\n#endif')
    elif name == 'xqvoice_worker.inc':
        once(' feature_tail_us=%llu\\n",',
             ' feature_tail_us=%llu"\n#if XINYI_BATTLE_R17\n'
             '            " utterance_start_us=%llu utterance_to_result_us=%llu"\n'
             '#endif\n            "\\n",')
        old = '            (unsigned long long)(tail_valid?metrics.features_done_us-metrics.endpoint_us:0));'
        once(old, '''            (unsigned long long)(tail_valid?metrics.features_done_us-metrics.endpoint_us:0)
#if XINYI_BATTLE_R17
            ,(unsigned long long)(tail_valid && metrics.utterance_start_us>=began && metrics.utterance_start_us<=metrics.last_voice_us?metrics.utterance_start_us:0),
            (unsigned long long)(tail_valid && metrics.utterance_start_us>=began && metrics.utterance_start_us<=metrics.last_voice_us?finished-metrics.utterance_start_us:0)
#endif
            );''')
    else:
        return data
    return s.encode()
