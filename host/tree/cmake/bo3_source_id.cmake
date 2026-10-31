# bo3_source_id.cmake - PLATFORM-P2: the build identity, made from the source inputs, without git.
#
#   cmake -DROOT=<game tree> -DXR=<xboxrecomp> -DOUT_DIR=<dir> [-DCONFIG_FILE=<file>] -P bo3_source_id.cmake
#
# Writes into OUT_DIR (each file only when its text changes, so nothing recompiles for it):
#   bo3_build_id.h          #define BO3_BUILD_COMMIT "bmp-<platform version>+<12 hex>"
#   bo3_toolkit_id.h        #define BO3_TOOLKIT_COMMIT "xr+<12 hex>"
#   bo3_build_manifest.txt  the exact text the game digest is taken over (every input file's SHA-256, by path)
#   bo3_toolkit_manifest.txt  the same for the toolkit
#
# The toolkit digest = SHA-256 of "xboxrecomp source manifest v1" + one line "<sha256>  toolkit/<path>" per file of the
# toolkit's CMakeLists.txt, cmake/, include/, src/, templates/, third_party/ (sorted by path, byte order).
# The game digest = SHA-256 of "bmp build manifest v1", "platform <version>", one line "<sha256>  bmp/<path>" per file of
# this tree's CMakeLists.txt, VERSION, cmake/, config/, graphics/, include/, src/game/, assets/glyphs/,
# tools/glyphs/build.py, tools/install/supported.json, tools/release/windows/ (sorted), "toolkit <toolkit digest>",
# then CONFIG_FILE's text (compiler, build type, generated-code options; src/game/CMakeLists.txt writes it).
# Left out: BUILD_COMMIT (a label only), .git, __pycache__ and build outputs (*.o, *.obj, *.exe, *.dll, *.a, *.lib, *.pyc).
# File contents are hashed as bytes (a checkout with other line ends is another input). The platform version is
# BO3_PLATFORM_VERSION of src/game/bm_platform_table.h. git is never asked: the same inputs give the same identity in a
# checkout, a copy or an archive, on any machine and in any build folder.
cmake_minimum_required(VERSION 3.20)
foreach(_v ROOT XR OUT_DIR)
    if(NOT DEFINED ${_v} OR "${${_v}}" STREQUAL "")
        message(FATAL_ERROR "bo3_source_id.cmake: -D${_v}= is required")
    endif()
endforeach()
get_filename_component(ROOT "${ROOT}" ABSOLUTE)
get_filename_component(XR "${XR}" ABSOLUTE)

# _bo3_lines(<base> <tag> <out> <entry>...): an entry ending in "/" is a folder (every file under it), else one file.
function(_bo3_lines base tag out)
    set(_all "")
    foreach(_e ${ARGN})
        if(_e MATCHES "/$")
            file(GLOB_RECURSE _f LIST_DIRECTORIES false RELATIVE "${base}" "${base}/${_e}*")
            list(APPEND _all ${_f})
        elseif(EXISTS "${base}/${_e}")
            list(APPEND _all "${_e}")
        endif()
    endforeach()
    list(REMOVE_DUPLICATES _all)
    set(_keep "")
    foreach(_f ${_all})
        if(_f MATCHES "(^|/)(\\.git|__pycache__)(/|$)" OR _f MATCHES "\\.(pyc|o|obj|exe|dll|a|lib)$" OR
           _f STREQUAL "BUILD_COMMIT")
            continue()
        endif()
        list(APPEND _keep "${_f}")
    endforeach()
    list(SORT _keep COMPARE STRING CASE SENSITIVE ORDER ASCENDING)
    set(_text "")
    foreach(_f ${_keep})
        file(SHA256 "${base}/${_f}" _h)
        string(APPEND _text "${_h}  ${tag}/${_f}\n")
    endforeach()
    set(${out} "${_text}" PARENT_SCOPE)
endfunction()

function(_bo3_write path text)
    set(_old "")
    if(EXISTS "${path}")
        file(READ "${path}" _old)
    endif()
    if(NOT _old STREQUAL text)
        # LF on every system (file(WRITE) writes CRLF on Windows): a manifest file is exactly the text that was hashed.
        set(AT "@")
        string(REPLACE "@" "@AT@" _t "${text}")
        file(CONFIGURE OUTPUT "${path}" CONTENT "${_t}" @ONLY NEWLINE_STYLE UNIX)
    endif()
endfunction()

file(STRINGS "${ROOT}/src/game/bm_platform_table.h" _pv REGEX "^#define BO3_PLATFORM_VERSION \"[0-9]+\\.[0-9]+\\.[0-9]+\"")
if(NOT _pv MATCHES "\"([0-9]+\\.[0-9]+\\.[0-9]+)\"")
    message(FATAL_ERROR "bo3_source_id.cmake: no BO3_PLATFORM_VERSION in ${ROOT}/src/game/bm_platform_table.h")
endif()
set(_platform "${CMAKE_MATCH_1}")

_bo3_lines("${XR}" toolkit _xr_lines CMakeLists.txt cmake/ include/ src/ templates/ third_party/)
set(_xr_text "xboxrecomp source manifest v1\n${_xr_lines}")
string(SHA256 _xr_digest "${_xr_text}")

_bo3_lines("${ROOT}" bmp _bmp_lines CMakeLists.txt VERSION cmake/ config/ graphics/ include/ src/game/ assets/glyphs/
           tools/glyphs/build.py tools/install/supported.json tools/release/windows/)
set(_cfg "")
if(DEFINED CONFIG_FILE AND EXISTS "${CONFIG_FILE}")
    file(READ "${CONFIG_FILE}" _cfg)
    string(REPLACE "\r" "" _cfg "${_cfg}")
endif()
set(_bmp_text "bmp build manifest v1\nplatform ${_platform}\n${_bmp_lines}toolkit ${_xr_digest}\n${_cfg}")
string(SHA256 _bmp_digest "${_bmp_text}")

string(SUBSTRING "${_bmp_digest}" 0 12 _b12)
string(SUBSTRING "${_xr_digest}" 0 12 _x12)
set(_id "bmp-${_platform}+${_b12}")
set(_xid "xr+${_x12}")
file(MAKE_DIRECTORY "${OUT_DIR}")
_bo3_write("${OUT_DIR}/bo3_build_manifest.txt" "${_bmp_text}")
_bo3_write("${OUT_DIR}/bo3_toolkit_manifest.txt" "${_xr_text}")
_bo3_write("${OUT_DIR}/bo3_build_id.h"
           "/* Made by cmake/bo3_source_id.cmake at build time: digest ${_bmp_digest} of bo3_build_manifest.txt. */\n#define BO3_BUILD_COMMIT \"${_id}\"\n")
_bo3_write("${OUT_DIR}/bo3_toolkit_id.h"
           "/* Made by cmake/bo3_source_id.cmake at build time: digest ${_xr_digest} of bo3_toolkit_manifest.txt. */\n#define BO3_TOOLKIT_COMMIT \"${_xid}\"\n")
message(STATUS "build identity ${_id}, toolkit ${_xid}")
