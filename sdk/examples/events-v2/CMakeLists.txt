# bmashup-sdk example (i): data-only World Tour events with names / help ([bmashup.extra_events] version 2, platform
# >=0.1.1). Nothing is compiled: the build copies mod.toml into <build>/out/example-events-v2/ (add the track files
# yourself: README.md). Part of the SDK's build, or on its own.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_data_mod)
    project(bm_sdk_events_v2 LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_data_mod(bmsdk_events_v2
    MOD_DIR example-events-v2
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
