#define NOMINMAX
#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"
#include "dito_whisper.h"
#include "whisper.h"

#include <string>
#include <vector>
#include <cstring>
#include <cmath>
#include <mutex>
#include <fstream>
#include <algorithm>
#include <sstream>

static std::mutex g_audio_mutex;
static std::vector<float> g_audio_buffer;
static float g_latest_rms = 0.0f;
static float g_latest_peak = 0.0f;
static float g_recorded_seconds = 0.0f;
static bool g_is_capturing = false;
static ma_device g_capture_device;
static ma_context g_audio_context;
static bool g_context_initialized = false;

static void audio_data_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount) {
    (void)pDevice;
    (void)pOutput;
    const float* pInputF32 = (const float*)pInput;
    if (!pInputF32 || frameCount == 0) return;

    std::lock_guard<std::mutex> lock(g_audio_mutex);
    float sum_sq = 0.0f;
    float peak = 0.0f;

    for (ma_uint32 i = 0; i < frameCount; ++i) {
        float s = pInputF32[i];
        g_audio_buffer.push_back(s);
        sum_sq += s * s;
        float abs_s = std::fabs(s);
        if (abs_s > peak) peak = abs_s;
    }

    g_latest_rms = std::sqrt(sum_sq / (float)frameCount);
    g_latest_peak = peak;
    g_recorded_seconds = (float)g_audio_buffer.size() / 16000.0f;
}

static bool ensure_context() {
    if (!g_context_initialized) {
        if (ma_context_init(NULL, 0, NULL, &g_audio_context) != MA_SUCCESS) {
            return false;
        }
        g_context_initialized = true;
    }
    return true;
}

extern "C" {

DITO_EXPORT dito_whisper_handle dito_whisper_init(const char* model_path, int use_gpu) {
    if (!model_path) return nullptr;
    whisper_context_params cparams = whisper_context_default_params();
    cparams.use_gpu = (use_gpu != 0);
    whisper_context* ctx = whisper_init_from_file_with_params(model_path, cparams);
    return (dito_whisper_handle)ctx;
}

DITO_EXPORT int dito_whisper_transcribe(
    dito_whisper_handle handle,
    const float* pcm_data,
    int n_samples,
    const char* lang,
    char* out_text,
    int max_len
) {
    if (!handle || !pcm_data || n_samples <= 0 || !out_text || max_len <= 0) return -1;
    whisper_context* ctx = (whisper_context*)handle;

    whisper_full_params wparams = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    wparams.print_progress   = false;
    wparams.print_special    = false;
    wparams.print_realtime   = false;
    wparams.print_timestamps = false;
    wparams.translate        = false;
    wparams.single_segment   = false;
    wparams.no_context       = true;
    wparams.language         = (lang && strlen(lang) > 0) ? lang : "pt";
    wparams.n_threads        = 4;

    int ret = whisper_full(ctx, wparams, pcm_data, n_samples);
    if (ret != 0) return -1;

    std::string full_text = "";
    const int n_segments = whisper_full_n_segments(ctx);
    for (int i = 0; i < n_segments; ++i) {
        const char* seg_text = whisper_full_get_segment_text(ctx, i);
        if (seg_text) {
            full_text += seg_text;
        }
    }

    size_t start = full_text.find_first_not_of(" \t\r\n");
    if (start != std::string::npos) {
        full_text = full_text.substr(start);
    } else {
        full_text.clear();
    }

    size_t copy_len = std::min((size_t)(max_len - 1), full_text.length());
    if (copy_len > 0) {
        memcpy(out_text, full_text.c_str(), copy_len);
    }
    out_text[copy_len] = '\0';
    return (int)n_segments;
}

DITO_EXPORT void dito_whisper_free(dito_whisper_handle handle) {
    if (handle) {
        whisper_free((whisper_context*)handle);
    }
}

DITO_EXPORT const char* dito_whisper_version(void) {
    return whisper_version();
}

// ---------------------------------------------------------------------------
// Native Audio Capture Functions
// ---------------------------------------------------------------------------

DITO_EXPORT int dito_audio_list_devices(char* out_json, int max_len) {
    if (!out_json || max_len <= 0) return -1;
    if (!ensure_context()) return -1;

    ma_device_info* pCaptureInfos;
    ma_uint32 captureCount;
    if (ma_context_get_devices(&g_audio_context, NULL, NULL, &pCaptureInfos, &captureCount) != MA_SUCCESS) {
        return -1;
    }

    std::ostringstream ss;
    ss << "[";
    for (ma_uint32 i = 0; i < captureCount; ++i) {
        if (i > 0) ss << ",";
        std::string name = pCaptureInfos[i].name;
        // Escape quotes
        std::string escaped;
        for (char c : name) {
            if (c == '"' || c == '\\') escaped += '\\';
            escaped += c;
        }
        ss << "{\"id\":\"" << i << "\",\"name\":\"" << escaped << "\",\"is_default\":" << (pCaptureInfos[i].isDefault ? "true" : "false") << "}";
    }
    ss << "]";

    std::string json_str = ss.str();
    size_t copy_len = std::min((size_t)(max_len - 1), json_str.length());
    if (copy_len > 0) {
        memcpy(out_json, json_str.c_str(), copy_len);
    }
    out_json[copy_len] = '\0';
    return (int)captureCount;
}

DITO_EXPORT int dito_audio_start_capture(const char* device_name) {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    if (g_is_capturing) {
        return 0; // Already capturing
    }

    if (!ensure_context()) return -1;

    g_audio_buffer.clear();
    g_latest_rms = 0.0f;
    g_latest_peak = 0.0f;
    g_recorded_seconds = 0.0f;

    ma_device_config deviceConfig = ma_device_config_init(ma_device_type_capture);
    deviceConfig.capture.format = ma_format_f32;
    deviceConfig.capture.channels = 1;
    deviceConfig.sampleRate = 16000;
    deviceConfig.dataCallback = audio_data_callback;
    deviceConfig.pUserData = NULL;

    ma_device_id customDeviceId;
    bool useCustomDevice = false;

    if (device_name && strlen(device_name) > 0 && strcmp(device_name, "auto") != 0 && strcmp(device_name, "default") != 0) {
        ma_device_info* pCaptureInfos;
        ma_uint32 captureCount;
        if (ma_context_get_devices(&g_audio_context, NULL, NULL, &pCaptureInfos, &captureCount) == MA_SUCCESS) {
            for (ma_uint32 i = 0; i < captureCount; ++i) {
                if (strstr(pCaptureInfos[i].name, device_name) != NULL) {
                    customDeviceId = pCaptureInfos[i].id;
                    useCustomDevice = true;
                    break;
                }
            }
        }
    }

    if (useCustomDevice) {
        deviceConfig.capture.pDeviceID = &customDeviceId;
    }

    if (ma_device_init(&g_audio_context, &deviceConfig, &g_capture_device) != MA_SUCCESS) {
        return -2;
    }

    if (ma_device_start(&g_capture_device) != MA_SUCCESS) {
        ma_device_uninit(&g_capture_device);
        return -3;
    }

    g_is_capturing = true;
    return 0;
}

DITO_EXPORT int dito_audio_get_level(float* out_rms, float* out_peak, float* out_seconds) {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    if (out_rms) *out_rms = g_latest_rms;
    if (out_peak) *out_peak = g_latest_peak;
    if (out_seconds) *out_seconds = g_recorded_seconds;
    return g_is_capturing ? 1 : 0;
}

DITO_EXPORT int dito_audio_stop_capture(float** out_pcm_data, int* out_n_samples) {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    if (g_is_capturing) {
        ma_device_stop(&g_capture_device);
        ma_device_uninit(&g_capture_device);
        g_is_capturing = false;
    }

    int n_samples = (int)g_audio_buffer.size();
    if (out_n_samples) *out_n_samples = n_samples;

    if (n_samples > 0 && out_pcm_data) {
        float* pcm = (float*)malloc(n_samples * sizeof(float));
        if (pcm) {
            memcpy(pcm, g_audio_buffer.data(), n_samples * sizeof(float));
            *out_pcm_data = pcm;
        } else {
            *out_pcm_data = nullptr;
            return -1;
        }
    } else if (out_pcm_data) {
        *out_pcm_data = nullptr;
    }

    g_audio_buffer.clear();
    return 0;
}

DITO_EXPORT void dito_audio_free_samples(float* pcm_data) {
    if (pcm_data) {
        free(pcm_data);
    }
}

DITO_EXPORT int dito_audio_save_wav(const char* file_path, const float* pcm_data, int n_samples) {
    if (!file_path || !pcm_data || n_samples <= 0) return -1;

    std::ofstream out(file_path, std::ios::binary);
    if (!out.is_open()) return -2;

    uint32_t sample_rate = 16000;
    uint16_t num_channels = 1;
    uint16_t bits_per_sample = 16;
    uint32_t byte_rate = sample_rate * num_channels * (bits_per_sample / 8);
    uint16_t block_align = num_channels * (bits_per_sample / 8);
    uint32_t data_size = n_samples * sizeof(int16_t);
    uint32_t file_size = 36 + data_size;

    // RIFF Header
    out.write("RIFF", 4);
    out.write((const char*)&file_size, 4);
    out.write("WAVE", 4);

    // FMT chunk
    out.write("fmt ", 4);
    uint32_t subchunk1_size = 16;
    uint16_t audio_format = 1; // PCM
    out.write((const char*)&subchunk1_size, 4);
    out.write((const char*)&audio_format, 2);
    out.write((const char*)&num_channels, 2);
    out.write((const char*)&sample_rate, 4);
    out.write((const char*)&byte_rate, 4);
    out.write((const char*)&block_align, 2);
    out.write((const char*)&bits_per_sample, 2);

    // DATA chunk
    out.write("data", 4);
    out.write((const char*)&data_size, 4);

    // Convert float samples [-1.0, 1.0] to 16-bit PCM
    std::vector<int16_t> pcm16(n_samples);
    for (int i = 0; i < n_samples; ++i) {
        float sample = std::max(-1.0f, std::min(1.0f, pcm_data[i]));
        pcm16[i] = (int16_t)(sample * 32767.0f);
    }

    out.write((const char*)pcm16.data(), data_size);
    out.close();
    return 0;
}

}
