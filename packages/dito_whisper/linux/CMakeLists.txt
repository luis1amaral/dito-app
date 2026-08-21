cmake_minimum_required(VERSION 3.14)

set(PROJECT_NAME "dito_whisper")
project(${PROJECT_NAME} LANGUAGES C CXX)

set(PLUGIN_NAME "dito_whisper_plugin")

set(SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../src")
set(GGML_SRC "${SRC_DIR}/ggml/src")
set(GGML_CPU "${GGML_SRC}/ggml-cpu")

list(APPEND PLUGIN_SOURCES
  "dito_whisper_plugin.cc"
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
  _GNU_SOURCE
  WHISPER_VERSION="1.9.2"
  GGML_VERSION="1.9.2"
  GGML_COMMIT="dito"
  GGML_AVX2
  GGML_FMA
  GGML_F16C
  GGML_USE_LLAMAFILE
  GGML_USE_CPU
)

target_compile_options(${PLUGIN_NAME} PRIVATE
  -mavx2 -mfma -mf16c -O3 -fPIC
  -Wno-unused-function -Wno-unused-variable -Wno-unused-but-set-variable
)

target_link_libraries(${PLUGIN_NAME} PRIVATE
  flutter
  PkgConfig::GTK
  pthread
  m
  dl
  asound
)

# Optional GPU backend: a standalone dlopen()-only module, never linked into the plugin
# itself, so a machine without CUDA still loads dito_whisper_plugin fine and just runs on CPU.
find_package(CUDAToolkit QUIET)
if (CUDAToolkit_FOUND)
  message(STATUS "dito_whisper: CUDA Toolkit ${CUDAToolkit_VERSION} found, building optional GPU backend")
  enable_language(CUDA)

  set(GGML_CUDA_SRC "${SRC_DIR}/ggml/src/ggml-cuda")
  file(GLOB GGML_CUDA_SOURCES "${GGML_CUDA_SRC}/*.cu")
  file(GLOB GGML_CUDA_TEMPLATE_SOURCES
    "${GGML_CUDA_SRC}/template-instances/fattn-vec-instance-f16-f16.cu"
    "${GGML_CUDA_SRC}/template-instances/fattn-vec-instance-q4_0-q4_0.cu"
    "${GGML_CUDA_SRC}/template-instances/fattn-vec-instance-q8_0-q8_0.cu"
    "${GGML_CUDA_SRC}/template-instances/fattn-vec-instance-bf16-bf16.cu"
    "${GGML_CUDA_SRC}/template-instances/fattn-tile*.cu"
    "${GGML_CUDA_SRC}/template-instances/fattn-mma*.cu"
    "${GGML_CUDA_SRC}/template-instances/mmq*.cu"
    "${GGML_CUDA_SRC}/template-instances/mmf*.cu"
  )

  add_library(ggml-cuda MODULE ${GGML_CUDA_SOURCES} ${GGML_CUDA_TEMPLATE_SOURCES})
  set_target_properties(ggml-cuda PROPERTIES
    PREFIX "lib"
    OUTPUT_NAME "ggml-cuda"
    CUDA_SEPARABLE_COMPILATION ON
    # Real SASS per arch, not "-virtual" PTX: PTX made the driver JIT every kernel on first use, stalling minutes.
    CUDA_ARCHITECTURES "61;75;86;89"
  )

  target_include_directories(ggml-cuda PRIVATE
    "${SRC_DIR}/ggml/include"
    "${GGML_SRC}"
  )
  target_compile_definitions(ggml-cuda PRIVATE
    GGML_BACKEND_DL
    GGML_BACKEND_BUILD
    GGML_CUDA_PEER_MAX_BATCH_SIZE=128
  )
  target_compile_options(ggml-cuda PRIVATE
    $<$<COMPILE_LANGUAGE:CUDA>:-use_fast_math -extended-lambda -Wno-deprecated-gpu-targets>
  )
  # Undefined ggml-base symbols (tensor/backend plumbing) resolve against the plugin that
  # dlopen()s this module — it already links every ggml-base source statically.
  target_link_libraries(ggml-cuda PRIVATE
    ${PLUGIN_NAME}
    CUDA::cudart
    CUDA::cublas
    CUDA::cuda_driver
  )
else()
  message(STATUS "dito_whisper: CUDA Toolkit not found, GPU backend skipped — CPU only")
endif()

if (TARGET ggml-cuda)
  set(dito_whisper_bundled_libraries
    "$<TARGET_FILE:ggml-cuda>"
    PARENT_SCOPE
  )
else()
  set(dito_whisper_bundled_libraries
    ""
    PARENT_SCOPE
  )
endif()
