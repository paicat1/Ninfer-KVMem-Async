# The measured device route profiles ship inside the binary: device_profiles.json (ninfer-calibrate
# --print output of each part, merged) becomes a string in the generated source.
set(NINFER_DEVICE_PROFILES_FILE ${CMAKE_CURRENT_SOURCE_DIR}/engine/device_profiles.json)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${NINFER_DEVICE_PROFILES_FILE})
file(READ ${NINFER_DEVICE_PROFILES_FILE} NINFER_DEVICE_PROFILES_JSON)
# MSVC caps a single string literal at 16380 chars; the embedded JSON (30,566) exceeds it, which
# would raise C2026 (and truncate the data). Adjacent raw-string literals concatenate at
# translation phase 6, so split the JSON into chunks each < 16000 and join them with the
# )ninfer_json" R"ninfer_json( delimiter. The bytes are unchanged; the delimiter token never
# appears inside the JSON, so there is no collision. The .cpp.in template is untouched.
string(LENGTH "${NINFER_DEVICE_PROFILES_JSON}" _json_len)
set(_chunk_size 16000)
set(_json_parts "")
math(EXPR _offset 0)
while(_offset LESS _json_len)
  if(NOT _offset EQUAL 0)
    string(APPEND _json_parts ")ninfer_json\" R\"ninfer_json(")
  endif()
  string(SUBSTRING "${NINFER_DEVICE_PROFILES_JSON}" ${_offset} ${_chunk_size} _chunk)
  string(APPEND _json_parts "${_chunk}")
  math(EXPR _offset "${_offset} + ${_chunk_size}")
endwhile()
set(NINFER_DEVICE_PROFILES_JSON "${_json_parts}")
configure_file(engine/device_profiles_builtin.cpp.in
               ${CMAKE_CURRENT_BINARY_DIR}/engine/device_profiles_builtin.cpp @ONLY)

add_library(ninfer_runtime_support STATIC
  engine/admission_policy.cpp
  engine/context_cache/context_cost.cpp
  engine/context_cache/context_cost_defaults.cpp
  engine/device_profile.cpp
  ${CMAKE_CURRENT_BINARY_DIR}/engine/device_profiles_builtin.cpp
  engine/kv_capacity.cpp
  engine/public_types.cpp
  prefix_cache/block_hash.cpp
  prefix_cache/prefix_index.cpp
  prefix_cache/tap_planner.cpp
)
ninfer_internal_includes(ninfer_runtime_support)
target_link_libraries(ninfer_runtime_support PUBLIC ninfer_core ninfer_ops PRIVATE ninfer::json)

# Public Engine and common contracts; model execution remains in the model layer.
add_library(ninfer_engine STATIC
  engine/model_instance.cpp
  contract/sampling.cpp
  engine/engine.cpp
)
ninfer_internal_includes(ninfer_engine)
target_include_directories(ninfer_engine PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(ninfer_engine PRIVATE
  ninfer_calibration
  ninfer_model_runtime
  ninfer_artifact
  ninfer_core
  ninfer_runtime_support
  ninfer_ops
  ninfer_text
  ninfer_media_decode)
add_library(ninfer::engine ALIAS ninfer_engine)
