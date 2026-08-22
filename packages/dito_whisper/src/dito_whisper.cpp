#define NOMINMAX
#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"
#include "dito_whisper.h"
#include "whisper.h"
#include "ggml-backend.h"

#ifdef __linux__
#include <dlfcn.h>
#include <limits.h>
#endif

#include <string>
#include <vector>
#include <cstring>
#include <cmath>
#include <mutex>
#include <fstream>
#include <algorithm>
#include <sstream>
#include <cstdint>
#include <cstdio>
#include <atomic>
#include <thread>
#include <chrono>

static std::mutex g_audio_mutex;
static std::vector<float> g_audio_buffer;
static std::atomic<float> g_latest_rms{0.0f};
static std::atomic<float> g_latest_peak{0.0f};
static std::atomic<uint64_t> g_frames_captured{0};
static bool g_is_capturing = false;

// Ring pre-alocado entre a thread de audio e a consumidora: 8 s de folga a 16 kHz.
static const size_t kRingSamples = 16000 * 8;
static const size_t kReserveChunkSamples = 16000 * 60;
static std::vector<float> g_ring;
static std::atomic<uint64_t> g_ring_write{0};
static std::atomic<uint64_t> g_ring_read{0};
static std::thread g_consumer;
static std::atomic<bool> g_consumer_running{false};
static ma_device g_capture_device;
static ma_context g_audio_context;
static bool g_context_initialized = false;

// Incremental WAV writer: file is kept valid (correct header sizes) after every flush, not just at stop.
static const uint32_t kWavSampleRate = 16000;
static const uint16_t kWavChannels = 1;
static const uint16_t kWavBitsPerSample = 16;
static const uint64_t kWavFlushIntervalSamples = kWavSampleRate; // patch header + flush about once a second
static std::ofstream g_wav_file;
static bool g_wav_active = false;
static uint64_t g_wav_samples_written = 0;
static uint64_t g_wav_samples_since_flush = 0;

// Writes the 44-byte PCM WAV header with the sizes for data_size bytes of payload; caller must be positioned at 0.
static void write_wav_header(std::ofstream& out, uint32_t data_size) {
    uint32_t byte_rate = kWavSampleRate * kWavChannels * (kWavBitsPerSample / 8);
    uint16_t block_align = kWavChannels * (kWavBitsPerSample / 8);
    uint32_t file_size = 36 + data_size;
    uint32_t subchunk1_size = 16;
    uint16_t audio_format = 1; // PCM

    out.write("RIFF", 4);
    out.write((const char*)&file_size, 4);
    out.write("WAVE", 4);
    out.write("fmt ", 4);
    out.write((const char*)&subchunk1_size, 4);
    out.write((const char*)&audio_format, 2);
    out.write((const char*)&kWavChannels, 2);
    out.write((const char*)&kWavSampleRate, 4);
    out.write((const char*)&byte_rate, 4);
    out.write((const char*)&block_align, 2);
    out.write((const char*)&kWavBitsPerSample, 2);
    out.write("data", 4);
    out.write((const char*)&data_size, 4);
}

// Rewrites just the RIFF/data size fields in place so the file on disk is a valid WAV right now.
static void patch_wav_header_and_flush() {
    if (!g_wav_active) return;
    uint32_t data_size = (uint32_t)(g_wav_samples_written * (kWavBitsPerSample / 8));
    std::streampos write_pos = g_wav_file.tellp();
    g_wav_file.seekp(0);
    write_wav_header(g_wav_file, data_size);
    g_wav_file.seekp(write_pos);
    g_wav_file.flush();
    if (!g_wav_file.good()) {
        fprintf(stderr, "[dito_whisper] falha ao gravar/atualizar WAV incremental em disco\n");
        g_wav_active = false;
    }
}

// Realtime thread: slow work here drops blocks. The Dito in Python already knew it
// (src/dito/audio/capture.py:58) and the port forgot: this callback ONLY copies and measures.
// Disco, conversao e crescimento de buffer vivem na thread consumidora. Ver docs/armadilhas.md.
static void audio_data_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount) {
    (void)pDevice;
    (void)pOutput;
    const float* pInputF32 = (const float*)pInput;
    if (!pInputF32 || frameCount == 0 || g_ring.empty()) return;

    const size_t cap = g_ring.size();
    const uint64_t write = g_ring_write.load(std::memory_order_relaxed);
    float sum_sq = 0.0f;
    float peak = 0.0f;

    for (ma_uint32 i = 0; i < frameCount; ++i) {
        const float s = pInputF32[i];
        g_ring[(size_t)((write + i) % cap)] = s;
        sum_sq += s * s;
        const float abs_s = std::fabs(s);
        if (abs_s > peak) peak = abs_s;
    }
    g_ring_write.store(write + frameCount, std::memory_order_release);

    g_latest_rms.store(std::sqrt(sum_sq / (float)frameCount), std::memory_order_relaxed);
    g_latest_peak.store(peak, std::memory_order_relaxed);
    g_frames_captured.fetch_add(frameCount, std::memory_order_relaxed);
}

/// Consumidora: tudo que nao pode acontecer na thread de audio acontece aqui.
static void drain_ring() {
    const size_t cap = g_ring.size();
    if (cap == 0) return;
    uint64_t read = g_ring_read.load(std::memory_order_relaxed);
    const uint64_t write = g_ring_write.load(std::memory_order_acquire);
    if (write <= read) return;

    uint64_t available = write - read;
    // Ring pequeno demais para o atraso: perdeu o mais antigo, e isso precisa aparecer no log.
    if (available > cap) {
        fprintf(stderr, "[dito_whisper] consumidora atrasada: %llu amostras perdidas\n",
                (unsigned long long)(available - cap));
        read = write - cap;
        available = cap;
    }

    static std::vector<float> chunk;
    chunk.clear();
    chunk.reserve((size_t)available);
    for (uint64_t i = 0; i < available; ++i) {
        chunk.push_back(g_ring[(size_t)((read + i) % cap)]);
    }
    g_ring_read.store(read + available, std::memory_order_release);

    {
        std::lock_guard<std::mutex> lock(g_audio_mutex);
        g_audio_buffer.insert(g_audio_buffer.end(), chunk.begin(), chunk.end());
        if (g_audio_buffer.size() + kReserveChunkSamples > g_audio_buffer.capacity()) {
            g_audio_buffer.reserve(g_audio_buffer.capacity() + kReserveChunkSamples);
        }
    }

    if (!g_wav_active) return;
    static std::vector<int16_t> pcm16;
    pcm16.resize(chunk.size());
    for (size_t i = 0; i < chunk.size(); ++i) {
        const float sample = std::max(-1.0f, std::min(1.0f, chunk[i]));
        pcm16[i] = (int16_t)(sample * 32767.0f);
    }
    g_wav_file.write((const char*)pcm16.data(), (std::streamsize)(pcm16.size() * sizeof(int16_t)));
    if (!g_wav_file.good()) {
        fprintf(stderr, "[dito_whisper] falha ao escrever amostras de audio no WAV incremental\n");
        g_wav_active = false;
        return;
    }
    g_wav_samples_written += pcm16.size();
    g_wav_samples_since_flush += pcm16.size();
    if (g_wav_samples_since_flush >= kWavFlushIntervalSamples) {
        patch_wav_header_and_flush();
        g_wav_samples_since_flush = 0;
    }
}

static void consumer_main() {
    while (g_consumer_running.load(std::memory_order_acquire)) {
        drain_ring();
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    drain_ring();
}

static bool ensure_context() {
    if (!g_context_initialized) {
        // ALSA cru abre o "default" do card 0 (placa-mae, sem nada plugado) e grava ruido de fundo;
        // o servidor de som e quem sabe qual e o microfone do dono. Regra herdada do Dito em Python
        // (docs/armadilhas.md 1.7): tentar o servidor primeiro, cair para ALSA so avisando.
        ma_backend preferidos[] = {ma_backend_pulseaudio, ma_backend_jack};
        if (ma_context_init(preferidos, 2, NULL, &g_audio_context) != MA_SUCCESS) {
            fprintf(stderr, "[dito_whisper] ATENCAO: sem servidor de som (PulseAudio/PipeWire);"
                            " caindo para ALSA, que pode abrir a entrada da placa-mae\n");
            if (ma_context_init(NULL, 0, NULL, &g_audio_context) != MA_SUCCESS) {
                return false;
            }
            g_context_initialized = true;
            return true;
        }
        g_context_initialized = true;
    }
    return true;
}

extern "C" {

static std::string g_backend_dir;

DITO_EXPORT void dito_whisper_set_backend_dir(const char* dir) {
    g_backend_dir = dir ? dir : "";
}

// Optional backend modules (libggml-cuda.so) may live in a Dart-provided directory (a
// downloaded GPU pack) or next to this very .so — ggml's default search (exe dir + cwd)
// finds neither, so both are tried explicitly.
static void load_optional_backends() {
    if (!g_backend_dir.empty()) {
        ggml_backend_load_all_from_path(g_backend_dir.c_str());
    }
#ifdef __linux__
    Dl_info info;
    if (dladdr((void*)&load_optional_backends, &info) && info.dli_fname) {
        std::string self_path(info.dli_fname);
        size_t slash = self_path.find_last_of('/');
        if (slash != std::string::npos) {
            ggml_backend_load_all_from_path(self_path.substr(0, slash).c_str());
            return;
        }
    }
#endif
    if (g_backend_dir.empty()) ggml_backend_load_all();
}

DITO_EXPORT const char* dito_whisper_backend_name(void) {
    static std::string name;
    ggml_backend_dev_t best = nullptr;
    for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
        ggml_backend_dev_t dev = ggml_backend_dev_get(i);
        enum ggml_backend_dev_type type = ggml_backend_dev_type(dev);
        if (type == GGML_BACKEND_DEVICE_TYPE_GPU || type == GGML_BACKEND_DEVICE_TYPE_IGPU) {
            best = dev;
            break;
        }
        if (!best && type == GGML_BACKEND_DEVICE_TYPE_CPU) best = dev;
    }
    name = best ? ggml_backend_dev_name(best) : "desconhecido";
    return name.c_str();
}

DITO_EXPORT dito_whisper_handle dito_whisper_init(const char* model_path, int use_gpu) {
    if (!model_path) return nullptr;
    // Discovers optional dlopen()-only backend modules (e.g. libggml-cuda.so); no-op if none exist.
    static std::once_flag backends_loaded;
    std::call_once(backends_loaded, load_optional_backends);
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

DITO_EXPORT int dito_audio_start_capture(const char* device_name, const char* wav_path) {
    std::lock_guard<std::mutex> lock(g_audio_mutex);
    if (g_is_capturing) {
        return 0; // Already capturing
    }

    if (!ensure_context()) return -1;

    g_audio_buffer.clear();
    g_audio_buffer.reserve(kReserveChunkSamples);
    if (g_ring.size() != kRingSamples) g_ring.assign(kRingSamples, 0.0f);
    g_ring_write.store(0);
    g_ring_read.store(0);
    g_latest_rms.store(0.0f);
    g_latest_peak.store(0.0f);
    g_frames_captured.store(0);

    g_wav_active = false;
    g_wav_samples_written = 0;
    g_wav_samples_since_flush = 0;
    if (g_wav_file.is_open()) g_wav_file.close();
    if (wav_path && strlen(wav_path) > 0) {
        g_wav_file.open(wav_path, std::ios::binary | std::ios::trunc | std::ios::out);
        if (!g_wav_file.is_open()) {
            fprintf(stderr, "[dito_whisper] falha ao abrir WAV para gravacao incremental: %s\n", wav_path);
            return -5;
        }
        write_wav_header(g_wav_file, 0);
        g_wav_file.flush();
        if (!g_wav_file.good()) {
            fprintf(stderr, "[dito_whisper] falha ao escrever header WAV inicial: %s\n", wav_path);
            g_wav_file.close();
            return -5;
        }
        g_wav_active = true;
    }

    ma_device_config deviceConfig = ma_device_config_init(ma_device_type_capture);
    deviceConfig.capture.format = ma_format_f32;
    deviceConfig.capture.channels = 1;
    deviceConfig.sampleRate = 16000;
    deviceConfig.dataCallback = audio_data_callback;
    deviceConfig.pUserData = NULL;
    // 50 ms por periodo, como o Dito em Python fixava (BLOCKSIZE = 800): o default do miniaudio e
    // 10 ms x 3, sem folga para o callback. Ver CHANGELOG 2026-08-21.
    deviceConfig.periodSizeInMilliseconds = 50;
    deviceConfig.periods = 4;
    deviceConfig.performanceProfile = ma_performance_profile_conservative;

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
        if (g_wav_active) { g_wav_file.close(); g_wav_active = false; }
        return -2;
    }

    if (ma_device_start(&g_capture_device) != MA_SUCCESS) {
        ma_device_uninit(&g_capture_device);
        if (g_wav_active) { g_wav_file.close(); g_wav_active = false; }
        return -3;
    }

    // O Dito em Python provou nesta maquina que ALSA cru recusa 16 kHz (docs/armadilhas.md 1.12):
    // sem este log nao havia como saber qual caminho o audio tomou numa gravacao ruim.
    fprintf(stderr,
            "[dito_whisper] captura aberta: backend=%s device=%s taxa pedida=16000 "
            "taxa real=%u formato=%d periodo=%u frames\n",
            ma_get_backend_name(g_audio_context.backend),
            g_capture_device.capture.name,
            g_capture_device.capture.internalSampleRate,
            (int)g_capture_device.capture.internalFormat,
            g_capture_device.capture.internalPeriodSizeInFrames);
    if (g_audio_context.backend == ma_backend_alsa) {
        fprintf(stderr, "[dito_whisper] ATENCAO: abriu por ALSA cru, nao pelo servidor de som\n");
    }

    g_consumer_running.store(true, std::memory_order_release);
    g_consumer = std::thread(consumer_main);

    g_is_capturing = true;
    return 0;
}

DITO_EXPORT int dito_audio_get_level(float* out_rms, float* out_peak, float* out_seconds) {
    if (out_rms) *out_rms = g_latest_rms.load(std::memory_order_relaxed);
    if (out_peak) *out_peak = g_latest_peak.load(std::memory_order_relaxed);
    if (out_seconds) {
        *out_seconds = (float)g_frames_captured.load(std::memory_order_relaxed) / 16000.0f;
    }
    return g_is_capturing ? 1 : 0;
}

DITO_EXPORT int dito_audio_stop_capture(float** out_pcm_data, int* out_n_samples) {
    // Parar o device ANTES da consumidora, e a consumidora ANTES de tomar o lock: ela drena o que
    // sobrou no ring e usa esse mesmo mutex.
    if (g_is_capturing) {
        ma_device_stop(&g_capture_device);
        ma_device_uninit(&g_capture_device);
        g_is_capturing = false;
    }
    if (g_consumer_running.exchange(false, std::memory_order_acq_rel)) {
        if (g_consumer.joinable()) g_consumer.join();
    }

    std::lock_guard<std::mutex> lock(g_audio_mutex);

    if (g_wav_active) {
        patch_wav_header_and_flush();
        g_wav_file.close();
        g_wav_active = false;
    }
    g_wav_samples_written = 0;
    g_wav_samples_since_flush = 0;

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
