cmake_minimum_required(VERSION 3.14)

set(PROJECT_NAME "dito_whisper")
project(${PROJECT_NAME} LANGUAGES C CXX)

set(PLUGIN_NAME "dito_whisper_plugin")

set(SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../src")
set(GGML_SRC "${SRC_DIR}/ggml/src")
set(GGML_CPU "${GGML_SRC}/ggml-cpu")

list(APPEND PLUGIN_SOURCES
  "include/dito_whisper/dito_whisper_plugin_c_api.h"
  "dito_whisper_plugin_c_api.cpp"
  "${SRC_DIR}/dito_whisper.h"
  "${SRC_DIR}/dito_whisper.cpp"
  "${SRC_DIR}/whisper.cpp"
  "${GGML_SRC}/ggml.c"
  "${GGML_SRC}/ggml-alloc.c"
  "${GGML_SRC}/ggml-backend.cpp"
  "${GGML_SRC}/ggml-backend-reg.cpp"
  "${GGML_SRC}/ggml-backend-meta.cpp"
  "${GGML_SRC}/ggml-backend-dl.cpp"
  "${GGML_SRC}/ggml-quants.c"
  "${GGML_SRC}/ggml-threading.cpp"
  "${GGML_SRC}/ggml-opt.cpp"
  "${GGML_CPU}/ggml-cpu.c"
  "${GGML_CPU}/ggml-cpu.cpp"
  "${GGML_CPU}/quants.c"
  "${GGML_CPU}/unary-ops.cpp"
  "${GGML_CPU}/binary-ops.cpp"
  "${GGML_CPU}/ops.cpp"
  "${GGML_CPU}/repack.cpp"
  "${GGML_CPU}/traits.cpp"
  "${GGML_CPU}/vec.cpp"
  "${GGML_CPU}/arch/x86/quants.c"
  "${GGML_CPU}/arch/x86/repack.cpp"
  "${GGML_CPU}/arch/x86/cpu-feats.cpp"
  "${GGML_CPU}/amx/amx.cpp"
  "${GGML_CPU}/amx/mmq.cpp"
  "${GGML_CPU}/llamafile/sgemm.cpp"
)

set_source_files_properties(
  "${GGML_SRC}/ggml.c"
  "${GGML_SRC}/ggml-alloc.c"
  "${GGML_SRC}/ggml-quants.c"
  "${GGML_CPU}/ggml-cpu.c"
  "${GGML_CPU}/quants.c"
  "${GGML_CPU}/arch/x86/quants.c"
  PROPERTIES LANGUAGE C
)

add_library(${PLUGIN_NAME} SHARED
  ${PLUGIN_SOURCES}
)

apply_standard_settings(${PLUGIN_NAME})

target_compile_features(${PLUGIN_NAME} PUBLIC cxx_std_17)

target_include_directories(${PLUGIN_NAME} PUBLIC
  "${CMAKE_CURRENT_SOURCE_DIR}/include"
  "${SRC_DIR}/include"
  "${SRC_DIR}"
  "${SRC_DIR}/ggml/include"
  "${GGML_SRC}"
  "${GGML_CPU}"
)

target_compile_definitions(${PLUGIN_NAME} PRIVATE
  FLUTTER_PLUGIN_IMPL
  _DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR
  _CRT_SECURE_NO_WARNINGS
  WHISPER_VERSION="1.9.2"
  GGML_VERSION="1.9.2"
  GGML_COMMIT="dito"
  GGML_AVX2
  GGML_FMA
  GGML_F16C
  GGML_USE_LLAMAFILE
  GGML_USE_CPU
)

if (MSVC)
  target_compile_options(${PLUGIN_NAME} PRIVATE /WX- /wd4244 /wd4267 /wd4505 /wd4018 /wd4101 /wd4201 /wd4047 /wd4133 /wd4013 /wd4028 /wd4090 /arch:AVX2 $<$<COMPILE_LANGUAGE:CXX>:/EHsc>)
  target_compile_options(${PLUGIN_NAME} PRIVATE "$<$<CONFIG:Release>:/O2>")
endif()

target_link_libraries(${PLUGIN_NAME} PRIVATE flutter flutter_wrapper_plugin)

set(dito_whisper_bundled_libraries
  ""
  PARENT_SCOPE
)
