#ifndef DITO_WHISPER_H
#define DITO_WHISPER_H

#ifdef _WIN32
#define DITO_EXPORT __declspec(dllexport)
#else
#define DITO_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef void* dito_whisper_handle;

// Whisper model & transcription
DITO_EXPORT dito_whisper_handle dito_whisper_init(const char* model_path, int use_gpu);
DITO_EXPORT int dito_whisper_transcribe(
    dito_whisper_handle handle,
    const float* pcm_data,
    int n_samples,
    const char* lang,
    char* out_text,
    int max_len
);
DITO_EXPORT void dito_whisper_free(dito_whisper_handle handle);
DITO_EXPORT const char* dito_whisper_version(void);

// Audio capture
DITO_EXPORT int dito_audio_list_devices(char* out_json, int max_len);
DITO_EXPORT int dito_audio_start_capture(const char* device_name);
DITO_EXPORT int dito_audio_get_level(float* out_rms, float* out_peak, float* out_seconds);
DITO_EXPORT int dito_audio_stop_capture(float** out_pcm_data, int* out_n_samples);
DITO_EXPORT void dito_audio_free_samples(float* pcm_data);
DITO_EXPORT int dito_audio_save_wav(const char* file_path, const float* pcm_data, int n_samples);

#ifdef __cplusplus
}
#endif

#endif // DITO_WHISPER_H
