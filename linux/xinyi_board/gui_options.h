#ifndef XINYI_GUI_OPTIONS_H
#define XINYI_GUI_OPTIONS_H
#ifndef XINYI_GUI_ROW_SCALAR_R23
#define XINYI_GUI_ROW_SCALAR_R23 0
#endif
#if XINYI_GUI_ROW_SCALAR_R23 != 0 && XINYI_GUI_ROW_SCALAR_R23 != 1
#error XINYI_GUI_ROW_SCALAR_R23_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_ROW_NAV_R22
#define XINYI_GUI_ROW_NAV_R22 0
#endif
#if XINYI_GUI_ROW_NAV_R22 != 0 && XINYI_GUI_ROW_NAV_R22 != 1
#error XINYI_GUI_ROW_NAV_R22_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_PALETTE_R21
#define XINYI_GUI_PALETTE_R21 0
#endif
#if XINYI_GUI_PALETTE_R21 != 0 && XINYI_GUI_PALETTE_R21 != 1
#error XINYI_GUI_PALETTE_R21_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_LOAD8_R21
#define XINYI_GUI_LOAD8_R21 0
#endif
#if XINYI_GUI_LOAD8_R21 != 0 && XINYI_GUI_LOAD8_R21 != 1
#error XINYI_GUI_LOAD8_R21_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_COMMANDS_R21
#define XINYI_GUI_COMMANDS_R21 0
#endif
#if XINYI_GUI_COMMANDS_R21 != 0 && XINYI_GUI_COMMANDS_R21 != 1
#error XINYI_GUI_COMMANDS_R21_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_LINEAR_R21
#define XINYI_GUI_LINEAR_R21 0
#endif
#if XINYI_GUI_LINEAR_R21 != 0 && XINYI_GUI_LINEAR_R21 != 1
#error XINYI_GUI_LINEAR_R21_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_SPANS_R21
#define XINYI_GUI_SPANS_R21 0
#endif
#if XINYI_GUI_SPANS_R21 != 0 && XINYI_GUI_SPANS_R21 != 1
#error XINYI_GUI_SPANS_R21_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_CACHE_R21
#define XINYI_GUI_CACHE_R21 0
#endif
#if XINYI_GUI_CACHE_R21 != 0 && XINYI_GUI_CACHE_R21 != 1
#error XINYI_GUI_CACHE_R21_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_FAST_NAV_R21
#define XINYI_GUI_FAST_NAV_R21 0
#endif
#if XINYI_GUI_FAST_NAV_R21 != 0 && XINYI_GUI_FAST_NAV_R21 != 1
#error XINYI_GUI_FAST_NAV_R21_must_be_zero_or_one
#endif
#ifndef XINYI_PREVIEW_RETRY_R19
#define XINYI_PREVIEW_RETRY_R19 0
#endif
#if XINYI_PREVIEW_RETRY_R19 != 0 && XINYI_PREVIEW_RETRY_R19 != 1
#error XINYI_PREVIEW_RETRY_R19_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_METRIC_DELTAS
#define XINYI_GUI_METRIC_DELTAS 0
#endif
#if XINYI_GUI_METRIC_DELTAS != 0 && XINYI_GUI_METRIC_DELTAS != 1
#error XINYI_GUI_METRIC_DELTAS_must_be_zero_or_one
#endif
#ifndef XINYI_BATTLE_R17
#define XINYI_BATTLE_R17 0
#endif
#if XINYI_BATTLE_R17 != 0 && XINYI_BATTLE_R17 != 1
#error XINYI_BATTLE_R17_must_be_zero_or_one
#endif
#ifndef XINYI_ASR_VOICE4
#define XINYI_ASR_VOICE4 0
#endif
#if XINYI_ASR_VOICE4 != 0 && XINYI_ASR_VOICE4 != 1
#error XINYI_ASR_VOICE4_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_PAIR_DELTAS
#define XINYI_GUI_PAIR_DELTAS 0
#endif
#if XINYI_GUI_PAIR_DELTAS != 0 && XINYI_GUI_PAIR_DELTAS != 1
#error XINYI_GUI_PAIR_DELTAS_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_PAGE_DELTAS
#define XINYI_GUI_PAGE_DELTAS 0
#endif
#if XINYI_GUI_PAGE_DELTAS != 0 && XINYI_GUI_PAGE_DELTAS != 1
#error XINYI_GUI_PAGE_DELTAS_must_be_zero_or_one
#endif
#ifndef XINYI_GUI_RAM_RENDER
#define XINYI_GUI_RAM_RENDER 0
#endif
#if XINYI_GUI_RAM_RENDER != 0 && XINYI_GUI_RAM_RENDER != 1
#error XINYI_GUI_RAM_RENDER_must_be_zero_or_one
#endif
#ifndef XINYI_HOME_R15
#define XINYI_HOME_R15 0
#endif
#if XINYI_HOME_R15 != 0 && XINYI_HOME_R15 != 1
#error XINYI_HOME_R15_must_be_zero_or_one
#endif
#ifndef XINYI_UI_NAV_DIAG
#define XINYI_UI_NAV_DIAG 0
#endif
#if XINYI_UI_NAV_DIAG != 0 && XINYI_UI_NAV_DIAG != 1
#error XINYI_UI_NAV_DIAG_must_be_zero_or_one
#endif
#ifndef XINYI_HOME_R13
#define XINYI_HOME_R13 0
#endif
#if XINYI_HOME_R13 != 0 && XINYI_HOME_R13 != 1
#error XINYI_HOME_R13_must_be_zero_or_one
#endif
/* Explicit offline candidate; preserve the published single-page baseline. */
#ifndef XINYI_GUI_DOUBLE_BUFFER
#define XINYI_GUI_DOUBLE_BUFFER 0
#endif
#if XINYI_GUI_DOUBLE_BUFFER != 0 && XINYI_GUI_DOUBLE_BUFFER != 1
#error XINYI_GUI_DOUBLE_BUFFER_must_be_zero_or_one
#endif
#ifndef XINYI_UI_FEEDBACK
#define XINYI_UI_FEEDBACK 0
#endif
#if XINYI_UI_FEEDBACK != 0 && XINYI_UI_FEEDBACK != 1
#error XINYI_UI_FEEDBACK_must_be_zero_or_one
#endif
#ifndef XINYI_COACH_MOVE_AUDIO
#define XINYI_COACH_MOVE_AUDIO 0
#endif
#if XINYI_COACH_MOVE_AUDIO != 0 && XINYI_COACH_MOVE_AUDIO != 1
#error XINYI_COACH_MOVE_AUDIO_must_be_zero_or_one
#endif
#endif
