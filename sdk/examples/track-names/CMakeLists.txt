# bmashup-sdk example (c): track names from plugin-owned game memory. Part of the SDK's build, or on its own (BUILD.md).
# Another track / text at build time, e.g.
#   -DBMSDK_NAMES_DEFINES="TRACK_ID=\"US_C7_V1\";TRACK_NAME=\"Pier Run\";TRACK_LOCATION=\"PIER\""
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_plugin)
    project(bm_sdk_track_names LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
set(BMSDK_NAMES_DEFINES "" CACHE STRING "compile definitions of the track-names example (TRACK_*)")
bmsdk_add_plugin(bm_sdk_track_names
    SOURCES ${CMAKE_CURRENT_LIST_DIR}/bm_sdk_track_names.c
    DEFINES ${BMSDK_NAMES_DEFINES}
    MOD_DIR bmashup-sdk-track-names
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/mod.toml)
