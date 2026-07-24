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

}  // namespace

NB_MODULE(_native, module) {
    module.doc() = "Native foundation for macro-simulator";
    module.attr("ABI_VERSION") = macro_sim::abi_version();
    module.def("engine_version", []() {
        return std::string(macro_sim::engine_version());
    });
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
