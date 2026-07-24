#include <array>
#include <cstdint>
#include <string>
#include <stdexcept>
#include <vector>

#include <nanobind/nanobind.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/string_view.h>

#include "macro_sim/engine_session.hpp"
#include "macro_sim/generated/contracts.hpp"
#include "macro_sim/rng.hpp"
#include "macro_sim/version.hpp"
#include "python_m3_bindings.hpp"

namespace nb = nanobind;

namespace {

struct PythonScalar final {
    macro_sim::generated::InputKind kind;
    double number;
    std::string text;
};

PythonScalar scalar_from_python(nb::handle value) {
    using macro_sim::generated::InputKind;
    if (value.is_none()) {
        return {InputKind::null_value, 0.0, ""};
    }
    if (nb::isinstance<nb::bool_>(value)) {
        return {
            InputKind::boolean,
            nb::cast<bool>(value) ? 1.0 : 0.0,
            "",
        };
    }
    if (nb::isinstance<nb::int_>(value)) {
        return {
            InputKind::integer,
            static_cast<double>(nb::cast<std::int64_t>(value)),
            "",
        };
    }
    if (nb::isinstance<nb::float_>(value)) {
        return {InputKind::number, nb::cast<double>(value), ""};
    }
    if (nb::isinstance<nb::str>(value)) {
        return {InputKind::string, 0.0, nb::cast<std::string>(value)};
    }
    return {InputKind::id_set, 0.0, ""};
}

void require_status(const macro_sim::Status& status) {
    if (!status.ok()) {
        throw std::runtime_error(
            std::string(macro_sim::error_code_name(status.code()))
            + ": " + std::string(status.message())
        );
    }
}

nb::dict receipt_to_python(
    const macro_sim::core::TransactionReceipt& receipt
) {
    nb::list loans;
    for (const auto loan : receipt.created_loans) {
        loans.append(loan.value());
    }
    nb::dict output;
    output["before"] = receipt.before.hex();
    output["after"] = receipt.after.hex();
    output["applied_mutations"] = receipt.applied_mutations;
    output["created_loans"] = std::move(loans);
    return output;
}

nb::dict snapshot_to_python(const macro_sim::core::RootState& state) {
    nb::list accounts;
    for (const auto& account : state.postings.records()) {
        nb::dict item;
        item["id"] = account.id.value();
        item["kind"] = static_cast<std::uint8_t>(account.key.kind);
        item["owner_kind"] =
            static_cast<std::uint8_t>(account.key.owner.kind);
        item["owner_id"] = account.key.owner.value;
        item["settlement_node"] = account.key.settlement_node.value();
        item["balance"] = account.balance.value();
        item["open"] = account.open;
        accounts.append(std::move(item));
    }
    nb::list reserves;
    for (const auto& reserve : state.reserves.records()) {
        nb::dict item;
        item["node"] = reserve.node.value();
        item["bank"] = reserve.bank.value();
        item["balance"] = reserve.balance.value();
        reserves.append(std::move(item));
    }
    nb::list loans;
    for (const auto& loan : state.loans.records()) {
        nb::dict item;
        item["id"] = loan.id.value();
        item["lender"] = loan.lender.value();
        item["borrower_kind"] =
            static_cast<std::uint8_t>(loan.borrower.kind);
        item["borrower_id"] = loan.borrower.value;
        item["borrower_account"] = loan.borrower_account.value();
        item["principal"] = loan.principal.value();
        item["active"] = loan.active;
        loans.append(std::move(item));
    }
    nb::dict counters;
    for (const auto& [stream, value] : state.named_counters.records()) {
        counters[nb::int_(stream)] = nb::int_(value);
    }
    nb::dict output;
    output["digest"] = macro_sim::core::state_digest(state).hex();
    output["accounts"] = std::move(accounts);
    output["reserves"] = std::move(reserves);
    output["loans"] = std::move(loans);
    output["counters"] = std::move(counters);
    return output;
}

nb::dict m4_metrics_to_python(
    const macro_sim::simulation::M4Metrics& metrics
) {
    nb::dict output;
    output["tick"] = metrics.tick.value();
    output["real_output"] = metrics.real_output;
    output["nominal_output"] = metrics.nominal_output;
    output["price_index"] = metrics.price_index;
    output["unemployment_rate"] = metrics.unemployment_rate;
    output["total_money"] = metrics.total_money;
    output["conservation_drift"] = metrics.conservation_drift;
    output["aggregate_capital"] = metrics.aggregate_capital;
    output["household_consumption"] = metrics.household_consumption;
    output["wages_paid"] = metrics.wages_paid;
    output["firm_profit"] = metrics.firm_profit;
    output["tax_total"] = metrics.tax_total;
    output["government_spending"] = metrics.government_spending;
    output["government_deficit"] = metrics.government_deficit;
    output["public_capital"] = metrics.public_capital;
    return output;
}

nb::dict m4_result_to_python(
    const macro_sim::simulation::M4AdvanceResult& result
) {
    nb::dict output;
    output["first_tick"] = result.first_tick.value();
    output["next_tick"] = result.next_tick.value();
    output["advanced_ticks"] = result.advanced_ticks;
    output["scratch_capacity_signature"] =
        result.scratch_capacity_signature;
    output["transfer_count"] = result.transfer_count;
    output["trade_count"] = result.trade_count;
    output["metrics"] = m4_metrics_to_python(result.metrics);
    return output;
}

nb::dict m4_snapshot_to_python(
    const macro_sim::EngineSession& session
) {
    if (session.root() == nullptr || session.simulation_runtime() == nullptr) {
        throw std::runtime_error(
            "invalid_handle: session has no active simulation"
        );
    }
    nb::list households;
    session.root()->households.for_each_alive(
        [&households](
            macro_sim::HouseholdId id,
            const macro_sim::core::HouseholdComponent& household
        ) {
            nb::dict item;
            item["id"] = id.value();
            item["account"] = household.primary_account.value();
            item["income_expected"] = household.income_expected;
            item["income_realized"] = household.income_realized;
            item["consumption_budget"] = household.consumption_budget;
            item["spent"] = household.spent;
            item["labor_sold"] = household.labor_sold;
            households.append(std::move(item));
        }
    );
    nb::list firms;
    session.root()->firms.for_each_alive(
        [&firms](
            macro_sim::FirmId id,
            const macro_sim::core::FirmComponent& firm
        ) {
            nb::dict item;
            item["id"] = id.value();
            item["sector"] = static_cast<std::uint8_t>(firm.sector);
            item["account"] = firm.primary_account.value();
            item["inventory"] = firm.goods_inventory.value();
            item["capital"] = firm.physical_capital.value();
            item["price"] = firm.posted_price.value();
            item["wage"] = firm.posted_wage.value();
            item["expected_demand"] = firm.demand_expected;
            item["previous_sales"] = firm.sales_previous;
            firms.append(std::move(item));
        }
    );
    nb::list balances;
    for (const auto& account : session.root()->postings.records()) {
        balances.append(account.balance.value());
    }
    nb::dict output;
    const auto digest = session.digest();
    require_status(digest.status());
    output["digest"] = digest.get_if()->hex();
    output["tick"] = session.tick().value();
    output["households"] = std::move(households);
    output["firms"] = std::move(firms);
    output["balances"] = std::move(balances);
    output["technology_index"] =
        session.simulation_runtime()->technology_index;
    output["public_capital"] =
        session.simulation_runtime()->public_capital;
    nb::list rng_counter;
    for (const auto value : session.simulation_runtime()->rng_counter) {
        rng_counter.append(value);
    }
    output["rng_counter"] = std::move(rng_counter);
    nb::list phase_trace;
    for (const auto& phase :
         session.simulation_runtime()->last_phase_trace) {
        nb::dict item;
        item["phase"] = static_cast<std::uint8_t>(phase.phase);
        item["money_total"] = phase.money_total;
        item["goods_total"] = phase.goods_total;
        item["capital_total"] = phase.capital_total;
        item["transfer_count"] = phase.transfer_count;
        item["trade_count"] = phase.trade_count;
        phase_trace.append(std::move(item));
    }
    output["phase_trace"] = std::move(phase_trace);
    output["metrics"] = m4_metrics_to_python(
        session.simulation_runtime()->last_metrics
    );
    return output;
}

}  // namespace

NB_MODULE(_native, module) {
    module.doc() = "Native foundation for macro-simulator";
    module.attr("ABI_VERSION") = macro_sim::abi_version();
    module.def("engine_version", []() {
        return std::string(macro_sim::engine_version());
    });
    macro_sim::python_m3::bind(module);
    module.def(
        "validate_scalar",
        [](std::string_view contract_id, nb::object value) {
            const auto scalar = scalar_from_python(value);
            const auto code = macro_sim::generated::validate_scalar(
                contract_id,
                {
                    scalar.kind,
                    scalar.number,
                    scalar.text,
                }
            );
            return std::pair(
                code == macro_sim::generated::ValidationCode::ok,
                std::string(macro_sim::generated::validation_code_name(code))
            );
        },
        nb::arg("contract_id"),
        nb::arg("value").none()
    );
    module.def(
        "philox_block",
        [](macro_sim::PhiloxCounter counter, macro_sim::PhiloxKey key) {
            const auto block = macro_sim::philox4x32_10(counter, key);
            return nb::make_tuple(block[0], block[1], block[2], block[3]);
        },
        nb::arg("counter"),
        nb::arg("key")
    );
    nb::enum_<macro_sim::SessionState>(module, "SessionState")
        .value("READY", macro_sim::SessionState::ready)
        .value("CLOSED", macro_sim::SessionState::closed);
    nb::enum_<macro_sim::core::GenesisVertical>(module, "GenesisVertical")
        .value(
            "M4_V0_CASH_LOOP",
            macro_sim::core::GenesisVertical::m4_v0_cash_loop
        )
        .value(
            "M4_V1_CAPITAL_FISCAL",
            macro_sim::core::GenesisVertical::m4_v1_capital_fiscal
        );
    nb::enum_<macro_sim::simulation::M4Vertical>(module, "M4Vertical")
        .value(
            "CASH_LOOP",
            macro_sim::simulation::M4Vertical::cash_loop
        )
        .value(
            "CAPITAL_FISCAL",
            macro_sim::simulation::M4Vertical::capital_fiscal
        );
    nb::enum_<macro_sim::algorithms::MatchingProtocol>(
        module,
        "MatchingProtocol"
    )
        .value(
            "SAMPLED",
            macro_sim::algorithms::MatchingProtocol::sampled
        )
        .value(
            "PREFERENTIAL",
            macro_sim::algorithms::MatchingProtocol::preferential
        )
        .value(
            "PRICE_SORTED",
            macro_sim::algorithms::MatchingProtocol::price_sorted
        );
    nb::class_<macro_sim::simulation::M4SimulationSpec>(
        module,
        "M4SimulationSpec"
    )
        .def(nb::init<>())
        .def_rw(
            "vertical",
            &macro_sim::simulation::M4SimulationSpec::vertical
        )
        .def_prop_rw(
            "economy_id",
            [](const macro_sim::simulation::M4SimulationSpec& spec) {
                return spec.economy.value();
            },
            [](macro_sim::simulation::M4SimulationSpec& spec,
               std::uint64_t value) {
                spec.economy = macro_sim::EconomyId(value);
            }
        )
        .def_prop_rw(
            "currency_id",
            [](const macro_sim::simulation::M4SimulationSpec& spec) {
                return spec.currency.value();
            },
            [](macro_sim::simulation::M4SimulationSpec& spec,
               std::uint32_t value) {
                spec.currency = macro_sim::CurrencyId(value);
            }
        )
        .def_rw(
            "households",
            &macro_sim::simulation::M4SimulationSpec::households
        )
        .def_rw(
            "consumption_firms",
            &macro_sim::simulation::M4SimulationSpec::consumption_firms
        )
        .def_rw(
            "capital_firms",
            &macro_sim::simulation::M4SimulationSpec::capital_firms
        )
        .def_rw("seed", &macro_sim::simulation::M4SimulationSpec::seed)
        .def_rw(
            "requested_capabilities",
            &macro_sim::simulation::M4SimulationSpec::requested_capabilities
        )
        .def_rw(
            "stochastic",
            &macro_sim::simulation::M4SimulationSpec::stochastic
        )
        .def_rw(
            "market_protocol",
            &macro_sim::simulation::M4SimulationSpec::market_protocol
        );
    nb::enum_<macro_sim::core::OwnerKind>(module, "OwnerKind")
        .value("HOUSEHOLD", macro_sim::core::OwnerKind::household)
        .value("FIRM", macro_sim::core::OwnerKind::firm)
        .value("BANK", macro_sim::core::OwnerKind::bank)
        .value("TREASURY", macro_sim::core::OwnerKind::treasury)
        .value("CENTRAL_BANK", macro_sim::core::OwnerKind::central_bank)
        .value("DEALER", macro_sim::core::OwnerKind::dealer)
        .value(
            "ROUNDING_RESIDUAL",
            macro_sim::core::OwnerKind::rounding_residual
        )
        .value("INSTITUTION", macro_sim::core::OwnerKind::institution);
    nb::class_<macro_sim::core::GenesisSpec>(module, "GenesisSpec")
        .def(nb::init<>())
        .def_prop_rw(
            "vertical",
            [](const macro_sim::core::GenesisSpec& spec) {
                return spec.vertical;
            },
            [](macro_sim::core::GenesisSpec& spec,
               macro_sim::core::GenesisVertical value) {
                spec.vertical = value;
            }
        )
        .def_prop_rw(
            "economy_id",
            [](const macro_sim::core::GenesisSpec& spec) {
                return spec.economy.value();
            },
            [](macro_sim::core::GenesisSpec& spec, std::uint64_t value) {
                spec.economy = macro_sim::EconomyId(value);
            }
        )
        .def_prop_rw(
            "currency_id",
            [](const macro_sim::core::GenesisSpec& spec) {
                return spec.currency.value();
            },
            [](macro_sim::core::GenesisSpec& spec, std::uint32_t value) {
                spec.currency = macro_sim::CurrencyId(value);
            }
        )
        .def_rw("households", &macro_sim::core::GenesisSpec::households)
        .def_rw(
            "consumption_firms",
            &macro_sim::core::GenesisSpec::consumption_firms
        )
        .def_rw(
            "capital_firms",
            &macro_sim::core::GenesisSpec::capital_firms
        )
        .def_rw(
            "settlement_banks",
            &macro_sim::core::GenesisSpec::settlement_banks
        )
        .def_rw("government", &macro_sim::core::GenesisSpec::government)
        .def_prop_rw(
            "opening_money",
            [](const macro_sim::core::GenesisSpec& spec) {
                return spec.aggregate_opening_money.value();
            },
            [](macro_sim::core::GenesisSpec& spec, double value) {
                spec.aggregate_opening_money = macro_sim::Money(value);
            }
        )
        .def_prop_rw(
            "opening_capital",
            [](const macro_sim::core::GenesisSpec& spec) {
                return spec.aggregate_opening_capital.value();
            },
            [](macro_sim::core::GenesisSpec& spec, double value) {
                spec.aggregate_opening_capital = macro_sim::Capital(value);
            }
        )
        .def_rw("seed", &macro_sim::core::GenesisSpec::seed)
        .def(
            "add_counter_stream",
            [](macro_sim::core::GenesisSpec& spec, std::uint64_t stream) {
                spec.named_counter_streams.push_back(stream);
            },
            nb::arg("stream_id")
        );
    nb::class_<macro_sim::core::SettlementBatch>(module, "SettlementBatch")
        .def(nb::init<>())
        .def(
            "transfer",
            [](macro_sim::core::SettlementBatch& batch,
               std::uint64_t source,
               std::uint64_t destination,
               double amount) {
                batch.transfers.push_back(
                    {
                        macro_sim::AccountId(source),
                        macro_sim::AccountId(destination),
                        macro_sim::Money(amount),
                    }
                );
            },
            nb::arg("source_account"),
            nb::arg("destination_account"),
            nb::arg("amount")
        )
        .def(
            "move_reserves",
            [](macro_sim::core::SettlementBatch& batch,
               std::uint64_t source,
               std::uint64_t destination,
               double amount) {
                batch.reserve_transfers.push_back(
                    {
                        macro_sim::SettlementNodeId(source),
                        macro_sim::SettlementNodeId(destination),
                        macro_sim::Money(amount),
                    }
                );
            },
            nb::arg("source_node"),
            nb::arg("destination_node"),
            nb::arg("amount")
        )
        .def(
            "issue_reserves",
            [](macro_sim::core::SettlementBatch& batch,
               std::uint64_t destination,
               double amount) {
                batch.reserve_issues.push_back(
                    {
                        macro_sim::SettlementNodeId(destination),
                        macro_sim::Money(amount),
                    }
                );
            },
            nb::arg("destination_node"),
            nb::arg("amount")
        )
        .def(
            "originate_loan",
            [](macro_sim::core::SettlementBatch& batch,
               std::uint64_t lender,
               macro_sim::core::OwnerKind borrower_kind,
               std::uint64_t borrower,
               std::uint64_t borrower_account,
               double amount,
               double annual_rate,
               std::uint64_t originated_tick,
               std::uint64_t maturity_tick) {
                batch.originations.push_back(
                    {
                        macro_sim::BankId(lender),
                        {borrower_kind, borrower},
                        macro_sim::AccountId(borrower_account),
                        macro_sim::Money(amount),
                        {
                            macro_sim::Rate(annual_rate),
                            macro_sim::Tick(originated_tick),
                            macro_sim::Tick(maturity_tick),
                        },
                    }
                );
            },
            nb::arg("lender_bank"),
            nb::arg("borrower_kind"),
            nb::arg("borrower_id"),
            nb::arg("borrower_account"),
            nb::arg("amount"),
            nb::arg("annual_rate"),
            nb::arg("originated_tick"),
            nb::arg("maturity_tick")
        )
        .def(
            "repay_loan",
            [](macro_sim::core::SettlementBatch& batch,
               std::uint64_t loan,
               std::uint64_t payer_account,
               double amount) {
                batch.repayments.push_back(
                    {
                        macro_sim::LoanId(loan),
                        macro_sim::AccountId(payer_account),
                        macro_sim::Money(amount),
                    }
                );
            },
            nb::arg("loan_id"),
            nb::arg("payer_account"),
            nb::arg("amount")
        )
        .def(
            "mutate_ownership",
            [](macro_sim::core::SettlementBatch& batch,
               std::uint64_t lot,
               macro_sim::core::OwnerKind owner_kind,
               std::uint64_t owner,
               double share) {
                batch.ownership_mutations.push_back(
                    {
                        macro_sim::OwnershipLotId(lot),
                        {owner_kind, owner},
                        share,
                    }
                );
            },
            nb::arg("lot_id"),
            nb::arg("owner_kind"),
            nb::arg("owner_id"),
            nb::arg("share")
        )
        .def(
            "increment_counter",
            [](macro_sim::core::SettlementBatch& batch,
               std::uint64_t stream,
               std::uint64_t amount) {
                batch.counter_increments.push_back({stream, amount});
            },
            nb::arg("stream_id"),
            nb::arg("amount") = 1
        );
    nb::class_<macro_sim::EngineSession>(module, "EngineSession")
        .def(
            nb::init<std::uint64_t>(),
            nb::arg("session_id") = 1
        )
        .def_prop_ro("session_id", [](const macro_sim::EngineSession& session) {
            return session.id().value();
        })
        .def_prop_ro("tick", [](const macro_sim::EngineSession& session) {
            return session.tick().value();
        })
        .def_prop_ro("state", &macro_sim::EngineSession::state)
        .def_prop_ro("closed", &macro_sim::EngineSession::closed)
        .def_prop_ro(
            "initialized",
            &macro_sim::EngineSession::initialized
        )
        .def(
            "initialize_m2",
            [](macro_sim::EngineSession& session,
               const macro_sim::core::GenesisSpec& spec) {
                require_status(session.initialize(spec));
            },
            nb::arg("spec")
        )
        .def(
            "initialize_simulation",
            [](macro_sim::EngineSession& session,
               const macro_sim::simulation::M4SimulationSpec& spec) {
                require_status(session.initialize_simulation(spec));
            },
            nb::arg("spec")
        )
        .def(
            "advance_ticks",
            [](macro_sim::EngineSession& session,
               std::uint64_t count,
               bool capture_phase_trace) {
                macro_sim::simulation::M4AdvanceOptions options;
                options.capture_phase_trace = capture_phase_trace;
                const auto result = session.advance_ticks(count, options);
                require_status(result.status());
                return m4_result_to_python(*result.get_if());
            },
            nb::arg("count"),
            nb::arg("capture_phase_trace") = false
        )
        .def(
            "simulation_snapshot",
            [](const macro_sim::EngineSession& session) {
                return m4_snapshot_to_python(session);
            }
        )
        .def(
            "apply_batch",
            [](macro_sim::EngineSession& session,
               const macro_sim::core::SettlementBatch& batch) {
                const auto result = session.apply(batch);
                require_status(result.status());
                return receipt_to_python(*result.get_if());
            },
            nb::arg("batch")
        )
        .def("digest", [](const macro_sim::EngineSession& session) {
            const auto result = session.digest();
            require_status(result.status());
            return result.get_if()->hex();
        })
        .def("accounting_snapshot", [](const macro_sim::EngineSession& session) {
            if (session.root() == nullptr || session.closed()) {
                throw std::runtime_error(
                    "invalid_handle: session has no active canonical state"
                );
            }
            return snapshot_to_python(*session.root());
        })
        .def("checkpoint", [](const macro_sim::EngineSession& session) {
            const auto result = session.checkpoint();
            require_status(result.status());
            const auto& bytes = *result.get_if();
            return nb::bytes(bytes.data(), bytes.size());
        })
        .def(
            "restore_checkpoint",
            [](macro_sim::EngineSession& session, const nb::bytes& encoded) {
                require_status(
                    session.restore_checkpoint(
                        std::span<const std::uint8_t>(
                            static_cast<const std::uint8_t*>(
                                encoded.data()
                            ),
                            encoded.size()
                        )
                    )
                );
            },
            nb::arg("checkpoint")
        )
        .def("close", [](macro_sim::EngineSession& session) {
            const auto result = session.close();
            if (!result.ok()) {
                throw std::runtime_error(std::string(result.message()));
            }
        });
}
