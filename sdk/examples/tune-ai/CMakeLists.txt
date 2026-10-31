# bmashup-sdk example (p): data-only AI tuning ([bmashup.tune] version = 2, bmashup.tune 3). Nothing is compiled: the build
# copies each mod.toml into <build>/out/<mod folder>/. Part of the SDK's build, or on its own.
cmake_minimum_required(VERSION 3.20)
if(NOT COMMAND bmsdk_add_data_mod)
    project(bm_sdk_tune_ai LANGUAGES C)
    include(${CMAKE_CURRENT_LIST_DIR}/../../cmake/bmsdk.cmake)
endif()
bmsdk_add_data_mod(bmsdk_tune_ai_topspeed
    MOD_DIR gp-aitune-topspeed
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/topspeed/mod.toml)
bmsdk_add_data_mod(bmsdk_tune_ai_aggression
    MOD_DIR gp-aitune-aggression
    MOD_TOML ${CMAKE_CURRENT_LIST_DIR}/aggression/mod.toml)
