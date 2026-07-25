include(GNUInstallDirs)
include(CTest)
include(CMakePackageConfigHelpers)

option(MACRO_SIM_BUILD_BENCHMARKS "Build native benchmark executables" ON)
option(MACRO_SIM_BUILD_PYTHON "Build the nanobind Python extension" ON)
option(MACRO_SIM_BUILD_TESTS "Build native unit and ABI tests" ON)
option(MACRO_SIM_COVERAGE "Enable source coverage instrumentation" OFF)
option(MACRO_SIM_WARNINGS_AS_ERRORS "Treat project warnings as errors" ON)
set(MACRO_SIM_SANITIZERS "" CACHE STRING "Comma-separated sanitizer list")

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)

function(macro_sim_project_options target)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4)
        if(MACRO_SIM_WARNINGS_AS_ERRORS)
            target_compile_options(${target} PRIVATE /WX)
        endif()
    else()
        target_compile_options(
            ${target}
            PRIVATE
                -Wall
                -Wextra
                -Wconversion
                -Wpedantic
                -Wshadow
        )
        if(MACRO_SIM_WARNINGS_AS_ERRORS)
            target_compile_options(${target} PRIVATE -Werror)
        endif()
    endif()

    if(MACRO_SIM_SANITIZERS)
        if(MSVC)
            message(FATAL_ERROR "The requested sanitizers are not configured for MSVC")
        endif()
        string(REPLACE "," ";" sanitizer_items "${MACRO_SIM_SANITIZERS}")
        list(JOIN sanitizer_items "," sanitizer_flags)
        target_compile_options(${target} PRIVATE "-fsanitize=${sanitizer_flags}" -fno-omit-frame-pointer)
        target_link_options(${target} PRIVATE "-fsanitize=${sanitizer_flags}" -fno-omit-frame-pointer)
    endif()

    if(MACRO_SIM_COVERAGE)
        if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
            target_compile_options(${target} PRIVATE -fprofile-instr-generate -fcoverage-mapping)
            target_link_options(${target} PRIVATE -fprofile-instr-generate -fcoverage-mapping)
        elseif(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
            target_compile_options(${target} PRIVATE --coverage)
            target_link_options(${target} PRIVATE --coverage)
        else()
            message(FATAL_ERROR "Coverage is unsupported for ${CMAKE_CXX_COMPILER_ID}")
        endif()
    endif()
endfunction()

function(macro_sim_enable_runtime_assertions target)
    if(MSVC)
        target_compile_options(${target} PRIVATE /UNDEBUG)
    else()
        target_compile_options(${target} PRIVATE -UNDEBUG)
    endif()
endfunction()

add_library(
    macro_sim_core
    STATIC
        src/algorithms/behavior.cpp
        src/algorithms/market.cpp
        src/algorithms/shock_overlay.cpp
        src/algorithms/valuation.cpp
        src/algorithms/vital_rates.cpp
        src/core/accounting.cpp
        src/core/checkpoint.cpp
        src/core/digest.cpp
        src/core/financial.cpp
        src/core/genesis.cpp
        src/core/invariants.cpp
        src/core/population.cpp
        src/core/securities.cpp
        src/core/transaction.cpp
        src/simulation/m4.cpp
        src/simulation/m4_checkpoint.cpp
        src/simulation/m5.cpp
        src/simulation/m5_checkpoint.cpp
        src/simulation/m6.cpp
        src/simulation/m6_checkpoint.cpp
        src/simulation/m7.cpp
        src/engine_session.cpp
        src/rng.cpp
        src/version.cpp
)
add_library(macro_sim::core ALIAS macro_sim_core)
set_target_properties(macro_sim_core PROPERTIES EXPORT_NAME core)
target_include_directories(
    macro_sim_core
    PUBLIC
        "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
        "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
)
target_include_directories(
    macro_sim_core
    SYSTEM
    PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/vendor/flatbuffers/include"
        "${CMAKE_CURRENT_SOURCE_DIR}/vendor/nlohmann-json/single_include"
        "${CMAKE_CURRENT_SOURCE_DIR}/vendor/picosha2"
)
macro_sim_project_options(macro_sim_core)

add_library(macro_sim_c SHARED src/c_api.cpp)
add_library(macro_sim::c ALIAS macro_sim_c)
set_target_properties(macro_sim_c PROPERTIES EXPORT_NAME c)
target_link_libraries(macro_sim_c PRIVATE macro_sim_core)
target_include_directories(
    macro_sim_c
    PUBLIC
        "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
        "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
)
target_compile_definitions(macro_sim_c PRIVATE MACRO_SIM_C_BUILDING_LIBRARY=1)
set_target_properties(
    macro_sim_c
    PROPERTIES
        OUTPUT_NAME macro_sim_c
        SOVERSION 1
        VERSION 1.0.0
)
macro_sim_project_options(macro_sim_c)

if(MACRO_SIM_BUILD_PYTHON)
    if(DEFINED ENV{VIRTUAL_ENV})
        set(Python_FIND_VIRTUALENV ONLY)
        set(Python_ROOT_DIR "$ENV{VIRTUAL_ENV}")
    endif()
    find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
    execute_process(
        COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
        RESULT_VARIABLE nanobind_result
        OUTPUT_VARIABLE nanobind_dir
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if(NOT nanobind_result EQUAL 0)
        message(FATAL_ERROR "Unable to locate nanobind through ${Python_EXECUTABLE}")
    endif()
    list(APPEND CMAKE_PREFIX_PATH "${nanobind_dir}")
    find_package(nanobind CONFIG REQUIRED)
    nanobind_add_module(_native STABLE_ABI src/python_bindings.cpp)
    target_link_libraries(_native PRIVATE macro_sim_core)
    macro_sim_project_options(_native)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        # GCC diagnoses shadowing inside nanobind's headers while compiling the
        # binding translation unit. First-party libraries and tests retain the
        # stricter -Wshadow/-Werror gate.
        target_compile_options(_native PRIVATE -Wno-shadow)
    endif()
    install(TARGETS _native LIBRARY DESTINATION macro_sim)
endif()

if(MACRO_SIM_BUILD_TESTS)
    add_executable(macro_sim_native_tests tests/native_tests.cpp)
    target_link_libraries(macro_sim_native_tests PRIVATE macro_sim_core macro_sim_c)
    macro_sim_project_options(macro_sim_native_tests)
    add_test(NAME macro_sim.native COMMAND macro_sim_native_tests)

    add_executable(macro_sim_c_smoke tests/c_smoke.c)
    target_link_libraries(macro_sim_c_smoke PRIVATE macro_sim_c)
    macro_sim_project_options(macro_sim_c_smoke)
    add_test(NAME macro_sim.c_abi COMMAND macro_sim_c_smoke)

    add_executable(macro_sim_m2_c_smoke tests/m2_c_smoke.c)
    target_link_libraries(macro_sim_m2_c_smoke PRIVATE macro_sim_c)
    macro_sim_project_options(macro_sim_m2_c_smoke)
    add_test(NAME macro_sim.m2_c_abi COMMAND macro_sim_m2_c_smoke)

    add_executable(macro_sim_m4_c_smoke tests/m4_c_smoke.c)
    target_link_libraries(macro_sim_m4_c_smoke PRIVATE macro_sim_c)
    macro_sim_project_options(macro_sim_m4_c_smoke)
    add_test(NAME macro_sim.m4_c_abi COMMAND macro_sim_m4_c_smoke)

    add_executable(macro_sim_m5_c_smoke tests/m5_c_smoke.c)
    target_link_libraries(macro_sim_m5_c_smoke PRIVATE macro_sim_c)
    macro_sim_project_options(macro_sim_m5_c_smoke)
    add_test(NAME macro_sim.m5_c_abi COMMAND macro_sim_m5_c_smoke)

    add_executable(macro_sim_m6_c_smoke tests/m6_c_smoke.c)
    target_link_libraries(macro_sim_m6_c_smoke PRIVATE macro_sim_c)
    macro_sim_project_options(macro_sim_m6_c_smoke)
    add_test(NAME macro_sim.m6_c_abi COMMAND macro_sim_m6_c_smoke)

    add_executable(macro_sim_rng_tests tests/rng_tests.cpp)
    target_link_libraries(macro_sim_rng_tests PRIVATE macro_sim_core)
    macro_sim_project_options(macro_sim_rng_tests)
    add_test(NAME macro_sim.rng COMMAND macro_sim_rng_tests)

    add_executable(macro_sim_m2_store_tests tests/m2_store_tests.cpp)
    target_link_libraries(macro_sim_m2_store_tests PRIVATE macro_sim_core)
    macro_sim_project_options(macro_sim_m2_store_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m2_store_tests)
    add_test(NAME macro_sim.m2_store COMMAND macro_sim_m2_store_tests)

    add_executable(
        macro_sim_m2_accounting_tests
        tests/m2_accounting_tests.cpp
    )
    target_link_libraries(
        macro_sim_m2_accounting_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m2_accounting_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m2_accounting_tests)
    add_test(
        NAME macro_sim.m2_accounting
        COMMAND macro_sim_m2_accounting_tests
    )

    add_executable(
        macro_sim_m2_transaction_tests
        tests/m2_transaction_tests.cpp
    )
    target_link_libraries(
        macro_sim_m2_transaction_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m2_transaction_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m2_transaction_tests)
    add_test(
        NAME macro_sim.m2_transaction
        COMMAND macro_sim_m2_transaction_tests
    )

    add_executable(
        macro_sim_m2_checkpoint_tests
        tests/m2_checkpoint_tests.cpp
    )
    target_link_libraries(
        macro_sim_m2_checkpoint_tests
        PRIVATE macro_sim_core
    )
    target_include_directories(
        macro_sim_m2_checkpoint_tests
        SYSTEM
        PRIVATE
            "${CMAKE_CURRENT_SOURCE_DIR}/vendor/nlohmann-json/single_include"
    )
    macro_sim_project_options(macro_sim_m2_checkpoint_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m2_checkpoint_tests)
    target_compile_definitions(
        macro_sim_m2_checkpoint_tests
        PRIVATE MACRO_SIM_SOURCE_DIR="${PROJECT_SOURCE_DIR}"
    )
    add_test(
        NAME macro_sim.m2_checkpoint
        COMMAND macro_sim_m2_checkpoint_tests
    )

    add_executable(
        macro_sim_m3_equation_tests
        tests/m3_equation_tests.cpp
    )
    target_link_libraries(
        macro_sim_m3_equation_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m3_equation_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m3_equation_tests)
    add_test(
        NAME macro_sim.m3_equations
        COMMAND macro_sim_m3_equation_tests
    )

    add_executable(
        macro_sim_m3_market_tests
        tests/m3_market_tests.cpp
    )
    target_link_libraries(
        macro_sim_m3_market_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m3_market_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m3_market_tests)
    add_test(
        NAME macro_sim.m3_markets
        COMMAND macro_sim_m3_market_tests
    )

    add_executable(
        macro_sim_m4_tick_tests
        tests/m4_tick_tests.cpp
    )
    target_link_libraries(
        macro_sim_m4_tick_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m4_tick_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m4_tick_tests)
    add_test(
        NAME macro_sim.m4_tick
        COMMAND macro_sim_m4_tick_tests
    )

    add_executable(
        macro_sim_m5_monetary_tests
        tests/m5_monetary_tests.cpp
    )
    target_link_libraries(
        macro_sim_m5_monetary_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m5_monetary_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m5_monetary_tests)
    add_test(
        NAME macro_sim.m5_monetary
        COMMAND macro_sim_m5_monetary_tests
    )

    add_executable(
        macro_sim_m6_security_book_tests
        tests/m6_security_book_tests.cpp
    )
    target_link_libraries(
        macro_sim_m6_security_book_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m6_security_book_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m6_security_book_tests)
    add_test(
        NAME macro_sim.m6_security_book
        COMMAND macro_sim_m6_security_book_tests
    )

    add_executable(
        macro_sim_m6_extension_seam_tests
        tests/m6_extension_seam_tests.cpp
    )
    target_link_libraries(
        macro_sim_m6_extension_seam_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m6_extension_seam_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m6_extension_seam_tests)
    add_test(
        NAME macro_sim.m6_extension_seam
        COMMAND macro_sim_m6_extension_seam_tests
    )

    add_executable(
        macro_sim_m6_simulation_tests
        tests/m6_simulation_tests.cpp
    )
    target_link_libraries(
        macro_sim_m6_simulation_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m6_simulation_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m6_simulation_tests)
    add_test(
        NAME macro_sim.m6_simulation
        COMMAND macro_sim_m6_simulation_tests
    )

    add_executable(
        macro_sim_m7_population_store_tests
        tests/m7_population_store_tests.cpp
    )
    target_link_libraries(
        macro_sim_m7_population_store_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m7_population_store_tests)
    macro_sim_enable_runtime_assertions(
        macro_sim_m7_population_store_tests
    )
    add_test(
        NAME macro_sim.m7_population_store
        COMMAND macro_sim_m7_population_store_tests
    )

    add_executable(
        macro_sim_m7_simulation_tests
        tests/m7_simulation_tests.cpp
    )
    target_link_libraries(
        macro_sim_m7_simulation_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m7_simulation_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m7_simulation_tests)
    add_test(
        NAME macro_sim.m7_simulation
        COMMAND macro_sim_m7_simulation_tests
    )

    if(TARGET _native)
        add_test(
            NAME macro_sim.m2_python_oracle
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m2/differential_oracle.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --seeds
                "100"
                --operations-per-seed
                "100"
        )
        set_tests_properties(
            macro_sim.m2_python_oracle
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m3_python_oracle
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m3/differential_oracle.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --random-cases
                "200"
        )
        set_tests_properties(
            macro_sim.m3_python_oracle
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m4_python_oracle
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m4/differential_oracle.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m4_python_oracle
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m4_fresh_process_checkpoint
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m4/fresh_process_checkpoint.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m4_fresh_process_checkpoint
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m4_stochastic_panel
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m4/stochastic_panel.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --envelopes
                "${PROJECT_SOURCE_DIR}/schemas/m4/stochastic_envelopes.json"
        )
        set_tests_properties(
            macro_sim.m4_stochastic_panel
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m5_fresh_process_checkpoint
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m5/fresh_process_checkpoint.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m5_fresh_process_checkpoint
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m5_semantic_panel
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m5/semantic_panel.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m5_semantic_panel
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m6_fresh_process_checkpoint
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m6/fresh_process_checkpoint.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m6_fresh_process_checkpoint
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m6_semantic_panel
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m6/semantic_panel.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m6_semantic_panel
            PROPERTIES LABELS "python-binding"
        )
    endif()
endif()

if(MACRO_SIM_BUILD_BENCHMARKS)
    add_executable(macro_sim_benchmarks benchmarks/foundation_benchmark.cpp)
    target_link_libraries(macro_sim_benchmarks PRIVATE macro_sim_core)
    macro_sim_project_options(macro_sim_benchmarks)

    add_executable(
        macro_sim_m2_benchmarks
        benchmarks/m2_accounting_benchmark.cpp
    )
    target_link_libraries(macro_sim_m2_benchmarks PRIVATE macro_sim_core)
    macro_sim_project_options(macro_sim_m2_benchmarks)
    macro_sim_enable_runtime_assertions(macro_sim_m2_benchmarks)

    add_executable(
        macro_sim_m3_benchmarks
        benchmarks/m3_market_benchmark.cpp
    )
    target_link_libraries(
        macro_sim_m3_benchmarks
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m3_benchmarks)
    macro_sim_enable_runtime_assertions(macro_sim_m3_benchmarks)

    add_executable(
        macro_sim_m4_benchmarks
        benchmarks/m4_tick_benchmark.cpp
    )
    target_link_libraries(
        macro_sim_m4_benchmarks
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m4_benchmarks)
    macro_sim_enable_runtime_assertions(macro_sim_m4_benchmarks)

    add_executable(
        macro_sim_m5_benchmarks
        benchmarks/m5_monetary_benchmark.cpp
    )
    target_link_libraries(
        macro_sim_m5_benchmarks
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m5_benchmarks)
    macro_sim_enable_runtime_assertions(macro_sim_m5_benchmarks)

    add_executable(
        macro_sim_m6_benchmarks
        benchmarks/m6_securities_benchmark.cpp
    )
    target_link_libraries(
        macro_sim_m6_benchmarks
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m6_benchmarks)
    macro_sim_enable_runtime_assertions(macro_sim_m6_benchmarks)
endif()

install(
    TARGETS macro_sim_core macro_sim_c
    EXPORT macro_simTargets
    ARCHIVE DESTINATION "${CMAKE_INSTALL_LIBDIR}"
    LIBRARY DESTINATION "${CMAKE_INSTALL_LIBDIR}"
    RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}"
)
install(DIRECTORY include/ DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}")
install(
    EXPORT macro_simTargets
    FILE macro_simTargets.cmake
    NAMESPACE macro_sim::
    DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/macro_sim"
)
configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/macro_simConfig.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/macro_simConfig.cmake"
    INSTALL_DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/macro_sim"
)
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/macro_simConfigVersion.cmake"
    VERSION "${PROJECT_VERSION}"
    COMPATIBILITY SameMajorVersion
)
install(
    FILES
        "${CMAKE_CURRENT_BINARY_DIR}/macro_simConfig.cmake"
        "${CMAKE_CURRENT_BINARY_DIR}/macro_simConfigVersion.cmake"
    DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/macro_sim"
)
