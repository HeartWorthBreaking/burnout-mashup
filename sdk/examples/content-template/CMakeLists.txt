# bmashup-sdk example (e): data-only content template. Nothing is compiled: the build copies mod.toml into
# <build>/out/example-content-template/ (add the track files yourself: README.md). Part of the SDK's build, or on its own.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_data_mod)
    project(bm_sdk_content_template LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_data_mod(bmsdk_content_template
    MOD_DIR example-content-template
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
