include(GNUInstallDirs)
include(CTest)
include(CMakePackageConfigHelpers)
find_package(Threads REQUIRED)
find_package(ZLIB REQUIRED)

option(MACRO_SIM_BUILD_BENCHMARKS "Build native benchmark executables" ON)
option(MACRO_SIM_BUILD_PYTHON "Build the nanobind Python extension" ON)
option(MACRO_SIM_BUILD_TESTS "Build native unit and ABI tests" ON)
option(MACRO_SIM_COVERAGE "Enable source coverage instrumentation" OFF)
option(MACRO_SIM_IPO "Enable interprocedural optimization" OFF)
option(MACRO_SIM_WARNINGS_AS_ERRORS "Treat project warnings as errors" ON)
set(MACRO_SIM_SANITIZERS "" CACHE STRING "Comma-separated sanitizer list")

if(MACRO_SIM_IPO)
    include(CheckIPOSupported)
    check_ipo_supported(RESULT macro_sim_ipo_supported
                        OUTPUT macro_sim_ipo_error
                        LANGUAGES C CXX)
    if(NOT macro_sim_ipo_supported)
        message(FATAL_ERROR
                "Interprocedural optimization is unavailable: ${macro_sim_ipo_error}")
    endif()
    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON)
endif()

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
        src/core/housing.cpp
        src/core/invariants.cpp
        src/core/population.cpp
        src/core/securities.cpp
        src/core/social_labor.cpp
        src/core/transaction.cpp
        src/control/m10.cpp
        src/control/m10_checkpoint.cpp
        src/control/m11_artifact.cpp
        src/control/m11_policy.cpp
        src/reporting/m10.cpp
        src/reporting/probes.cpp
        src/simulation/m4.cpp
        src/simulation/m4_checkpoint.cpp
        src/simulation/m5.cpp
        src/simulation/m5_checkpoint.cpp
        src/simulation/m6.cpp
        src/simulation/m6_checkpoint.cpp
        src/simulation/m7.cpp
        src/simulation/m7_checkpoint.cpp
        src/simulation/m8.cpp
        src/simulation/m8_checkpoint.cpp
        src/simulation/m9.cpp
        src/simulation/m9_checkpoint.cpp
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
target_link_libraries(macro_sim_core PUBLIC Threads::Threads ZLIB::ZLIB)
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

    add_executable(macro_sim_m7_c_smoke tests/m7_c_smoke.c)
    target_link_libraries(macro_sim_m7_c_smoke PRIVATE macro_sim_c)
    macro_sim_project_options(macro_sim_m7_c_smoke)
    add_test(NAME macro_sim.m7_c_abi COMMAND macro_sim_m7_c_smoke)

    add_executable(macro_sim_m8_c_smoke tests/m8_c_smoke.c)
    target_link_libraries(macro_sim_m8_c_smoke PRIVATE macro_sim_c)
    macro_sim_project_options(macro_sim_m8_c_smoke)
    add_test(NAME macro_sim.m8_c_abi COMMAND macro_sim_m8_c_smoke)

    add_executable(macro_sim_m9_c_smoke tests/m9_c_smoke.c)
    target_link_libraries(macro_sim_m9_c_smoke PRIVATE macro_sim_c)
    macro_sim_project_options(macro_sim_m9_c_smoke)
    add_test(NAME macro_sim.m9_c_abi COMMAND macro_sim_m9_c_smoke)

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

    add_executable(
        macro_sim_m7_extension_seam_tests
        tests/m7_extension_seam_tests.cpp
    )
    target_link_libraries(
        macro_sim_m7_extension_seam_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m7_extension_seam_tests)
    macro_sim_enable_runtime_assertions(
        macro_sim_m7_extension_seam_tests
    )
    add_test(
        NAME macro_sim.m7_extension_seam
        COMMAND macro_sim_m7_extension_seam_tests
    )

    add_executable(
        macro_sim_m7_social_labor_store_tests
        tests/m7_social_labor_store_tests.cpp
    )
    target_link_libraries(
        macro_sim_m7_social_labor_store_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m7_social_labor_store_tests)
    macro_sim_enable_runtime_assertions(
        macro_sim_m7_social_labor_store_tests
    )
    add_test(
        NAME macro_sim.m7_social_labor_store
        COMMAND macro_sim_m7_social_labor_store_tests
    )

    add_executable(
        macro_sim_m7_checkpoint_tests
        tests/m7_checkpoint_tests.cpp
    )
    target_link_libraries(
        macro_sim_m7_checkpoint_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m7_checkpoint_tests)
    macro_sim_enable_runtime_assertions(
        macro_sim_m7_checkpoint_tests
    )
    add_test(
        NAME macro_sim.m7_checkpoint
        COMMAND macro_sim_m7_checkpoint_tests
    )

    add_executable(
        macro_sim_m8_energy_tests
        tests/m8_energy_tests.cpp
    )
    target_link_libraries(
        macro_sim_m8_energy_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m8_energy_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m8_energy_tests)
    add_test(
        NAME macro_sim.m8_energy
        COMMAND macro_sim_m8_energy_tests
    )

    add_executable(
        macro_sim_m8_property_registry_tests
        tests/m8_property_registry_tests.cpp
    )
    target_link_libraries(
        macro_sim_m8_property_registry_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m8_property_registry_tests)
    macro_sim_enable_runtime_assertions(
        macro_sim_m8_property_registry_tests
    )
    add_test(
        NAME macro_sim.m8_property_registry
        COMMAND macro_sim_m8_property_registry_tests
    )

    add_executable(
        macro_sim_m8_credit_port_tests
        tests/m8_credit_port_tests.cpp
    )
    target_link_libraries(
        macro_sim_m8_credit_port_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m8_credit_port_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m8_credit_port_tests)
    add_test(
        NAME macro_sim.m8_credit_port
        COMMAND macro_sim_m8_credit_port_tests
    )

    add_executable(
        macro_sim_m8_housing_genesis_tests
        tests/m8_housing_genesis_tests.cpp
    )
    target_link_libraries(
        macro_sim_m8_housing_genesis_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m8_housing_genesis_tests)
    macro_sim_enable_runtime_assertions(
        macro_sim_m8_housing_genesis_tests
    )
    add_test(
        NAME macro_sim.m8_housing_genesis
        COMMAND macro_sim_m8_housing_genesis_tests
    )

    add_executable(
        macro_sim_m8_housing_market_tests
        tests/m8_housing_market_tests.cpp
    )
    target_link_libraries(
        macro_sim_m8_housing_market_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m8_housing_market_tests)
    macro_sim_enable_runtime_assertions(
        macro_sim_m8_housing_market_tests
    )
    add_test(
        NAME macro_sim.m8_housing_market
        COMMAND macro_sim_m8_housing_market_tests
    )

    add_executable(
        macro_sim_m8_checkpoint_tests
        tests/m8_checkpoint_tests.cpp
    )
    target_link_libraries(
        macro_sim_m8_checkpoint_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m8_checkpoint_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m8_checkpoint_tests)
    add_test(
        NAME macro_sim.m8_checkpoint
        COMMAND macro_sim_m8_checkpoint_tests
    )

    add_executable(
        macro_sim_m9_world_tests
        tests/m9_world_tests.cpp
    )
    target_link_libraries(
        macro_sim_m9_world_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m9_world_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m9_world_tests)
    add_test(
        NAME macro_sim.m9_world
        COMMAND macro_sim_m9_world_tests
    )

    add_executable(
        macro_sim_m10_policy_tests
        tests/m10_policy_tests.cpp
    )
    target_link_libraries(
        macro_sim_m10_policy_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m10_policy_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m10_policy_tests)
    add_test(
        NAME macro_sim.m10_policy
        COMMAND macro_sim_m10_policy_tests
    )

    add_executable(
        macro_sim_m10_reporting_tests
        tests/m10_reporting_tests.cpp
    )
    target_link_libraries(
        macro_sim_m10_reporting_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m10_reporting_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m10_reporting_tests)
    add_test(
        NAME macro_sim.m10_reporting
        COMMAND macro_sim_m10_reporting_tests
    )

    add_executable(
        macro_sim_m10_control_tests
        tests/m10_control_tests.cpp
    )
    target_link_libraries(
        macro_sim_m10_control_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m10_control_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m10_control_tests)
    add_test(
        NAME macro_sim.m10_control
        COMMAND macro_sim_m10_control_tests
    )

    add_executable(
        macro_sim_m11_artifact_tests
        tests/m11_artifact_tests.cpp
    )
    target_link_libraries(
        macro_sim_m11_artifact_tests
        PRIVATE macro_sim_core
    )
    target_compile_definitions(
        macro_sim_m11_artifact_tests
        PRIVATE MACRO_SIM_SOURCE_DIR="${PROJECT_SOURCE_DIR}"
    )
    macro_sim_project_options(macro_sim_m11_artifact_tests)
    macro_sim_enable_runtime_assertions(macro_sim_m11_artifact_tests)
    add_test(
        NAME macro_sim.m11_artifact
        COMMAND macro_sim_m11_artifact_tests
    )

    add_executable(
        macro_sim_m11_policy_contract_tests
        tests/m11_policy_contract_tests.cpp
    )
    target_link_libraries(
        macro_sim_m11_policy_contract_tests
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m11_policy_contract_tests)
    macro_sim_enable_runtime_assertions(
        macro_sim_m11_policy_contract_tests
    )
    add_test(
        NAME macro_sim.m11_policy_contract
        COMMAND macro_sim_m11_policy_contract_tests
    )

    if(TARGET _native)
        add_test(
            NAME macro_sim.m11_artifact_golden
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m11/artifact_golden.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --source-dir
                "${PROJECT_SOURCE_DIR}"
                --artifact
                "${PROJECT_SOURCE_DIR}/macro_sim/rl/artifacts/fiscal_stabilization_v1.msrl"
        )
        set_tests_properties(
            macro_sim.m11_artifact_golden
            PROPERTIES LABELS "python-binding;m11"
        )
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
        add_test(
            NAME macro_sim.m7_fresh_process_checkpoint
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m7/fresh_process_checkpoint.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m7_fresh_process_checkpoint
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m7_semantic_panel
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m7/semantic_panel.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m7_semantic_panel
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m8_fresh_process_checkpoint
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m8/fresh_process_checkpoint.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m8_fresh_process_checkpoint
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m8_semantic_panel
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m8/semantic_panel.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m8_semantic_panel
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m9_binding_smoke
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m9/binding_smoke.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m9_binding_smoke
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m9_fresh_process_checkpoint
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m9/fresh_process_checkpoint.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m9_fresh_process_checkpoint
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m9_semantic_panel
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m9/semantic_panel.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m9_semantic_panel
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m10_binding_smoke
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m10/binding_smoke.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
        )
        set_tests_properties(
            macro_sim.m10_binding_smoke
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m10_native_facade
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m10/native_facade_smoke.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --source-dir
                "${PROJECT_SOURCE_DIR}"
        )
        set_tests_properties(
            macro_sim.m10_native_facade
            PROPERTIES LABELS "python-binding"
        )
        add_test(
            NAME macro_sim.m10_native_history_stream
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m10/native_history_stream_smoke.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --source-dir
                "${PROJECT_SOURCE_DIR}"
        )
        set_tests_properties(
            macro_sim.m10_native_history_stream
            PROPERTIES LABELS "python-binding;history"
        )
        add_test(
            NAME macro_sim.m10_controller_history_stream
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m10/controller_history_stream_smoke.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --source-dir
                "${PROJECT_SOURCE_DIR}"
        )
        set_tests_properties(
            macro_sim.m10_controller_history_stream
            PROPERTIES LABELS "controller;python-binding;history"
        )
        add_test(
            NAME macro_sim.m10_native_controller
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m10/native_controller_smoke.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --source-dir
                "${PROJECT_SOURCE_DIR}"
        )
        set_tests_properties(
            macro_sim.m10_native_controller
            PROPERTIES LABELS "python-binding;controller;rl"
        )
        add_test(
            NAME macro_sim.m10_native_desktop
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m10/native_desktop_smoke.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --source-dir
                "${PROJECT_SOURCE_DIR}"
        )
        set_tests_properties(
            macro_sim.m10_native_desktop
            PROPERTIES LABELS "python-binding;desktop"
        )
        add_test(
            NAME macro_sim.m10_policy_stress
            COMMAND
                "${Python_EXECUTABLE}"
                "${PROJECT_SOURCE_DIR}/tools/m10/reproduce_policy_stress.py"
                --native-dir
                "$<TARGET_FILE_DIR:_native>"
                --source-dir
                "${PROJECT_SOURCE_DIR}"
                --ticks
                550
        )
        set_tests_properties(
            macro_sim.m10_policy_stress
            PROPERTIES LABELS "python-binding;controller;longevity"
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

    add_executable(
        macro_sim_m7_benchmarks
        benchmarks/m7_population_labor_benchmark.cpp
    )
    target_link_libraries(
        macro_sim_m7_benchmarks
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m7_benchmarks)
    macro_sim_enable_runtime_assertions(macro_sim_m7_benchmarks)

    add_executable(
        macro_sim_m8_benchmarks
        benchmarks/m8_energy_housing_benchmark.cpp
    )
    target_link_libraries(
        macro_sim_m8_benchmarks
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m8_benchmarks)
    macro_sim_enable_runtime_assertions(macro_sim_m8_benchmarks)

    add_executable(
        macro_sim_m9_benchmarks
        benchmarks/m9_world_benchmark.cpp
    )
    target_link_libraries(
        macro_sim_m9_benchmarks
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m9_benchmarks)
    macro_sim_enable_runtime_assertions(macro_sim_m9_benchmarks)

    add_executable(
        macro_sim_m9_scale_probe
        benchmarks/m9_scale_probe.cpp
    )
    target_link_libraries(
        macro_sim_m9_scale_probe
        PRIVATE macro_sim_core
    )
    macro_sim_project_options(macro_sim_m9_scale_probe)
    macro_sim_enable_runtime_assertions(macro_sim_m9_scale_probe)
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
