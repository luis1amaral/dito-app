cmake_minimum_required(VERSION 3.14)

set(PROJECT_NAME "dito_win32")
project(${PROJECT_NAME} LANGUAGES C CXX)

set(PLUGIN_NAME "dito_win32_plugin")

list(APPEND PLUGIN_SOURCES
  "dito_win32_plugin.cc"
)

add_library(${PLUGIN_NAME} SHARED
  ${PLUGIN_SOURCES}
)

apply_standard_settings(${PLUGIN_NAME})

target_compile_features(${PLUGIN_NAME} PUBLIC cxx_std_17)

target_include_directories(${PLUGIN_NAME} PUBLIC
  "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

target_compile_definitions(${PLUGIN_NAME} PRIVATE
  FLUTTER_PLUGIN_IMPL
)

target_link_libraries(${PLUGIN_NAME} PRIVATE
  flutter
  PkgConfig::GTK
)

set(dito_win32_bundled_libraries
  ""
  PARENT_SCOPE
)
