cmake_minimum_required(VERSION 3.14)

set(PROJECT_NAME "desktop_multi_window")
project(${PROJECT_NAME} LANGUAGES C CXX)

set(PLUGIN_NAME "desktop_multi_window_plugin")

list(APPEND PLUGIN_SOURCES
  "desktop_multi_window_plugin.cc"
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

set(desktop_multi_window_bundled_libraries
  ""
  PARENT_SCOPE
)
