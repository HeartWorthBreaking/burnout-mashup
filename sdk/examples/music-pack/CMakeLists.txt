# bmashup-sdk example (q): data-only music packs ([bmashup.music] version 1). Nothing is compiled: the build copies each
# mod.toml into <build>/out/<mod folder>/; generate the tone files with make_tones.py (README.md). Part of the SDK's build.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_data_mod)
    project(bm_sdk_music_pack LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_data_mod(bmsdk_music_tones
    MOD_DIR bmashup-test-tones
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/tones/mod.toml)
bmsdk_add_data_mod(bmsdk_music_tones_remix
    MOD_DIR bmashup-test-tones-remix
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/remix/mod.toml)
