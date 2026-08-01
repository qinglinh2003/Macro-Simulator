/*
 * Native aggregates consumed by the indicator panorama.
 *
 * These are derived from committed engine state.  They are deliberately
 * refreshed at a lower cadence than causal tick metrics because several
 * require full population, loan-book, or security-book scans.
 */
MACRO_SIM_DASHBOARD_METRIC(inventory_to_sales,
                          "metric.economy.inventory_to_sales",
                          "ratio",
                          "firm inventory / trailing firm sales")
MACRO_SIM_DASHBOARD_METRIC(production_realization_rate,
                          "metric.economy.production_realization_rate",
                          "share",
                          "realized real output / gross real output")
MACRO_SIM_DASHBOARD_METRIC(underemployed_share,
                          "metric.economy.underemployed_share",
                          "share",
                          "underemployed heads / participating labor force")
MACRO_SIM_DASHBOARD_METRIC(wage_inflation,
                          "metric.economy.wage_inflation",
                          "per_tick",
                          "mean wage / previous published mean wage - 1")
MACRO_SIM_DASHBOARD_METRIC(avg_markup,
                          "metric.economy.avg_markup",
                          "ratio",
                          "mean markup of active firms")
MACRO_SIM_DASHBOARD_METRIC(gov_debt,
                          "metric.economy.gov_debt",
                          "currency",
                          "government bond face less treasury cash")
MACRO_SIM_DASHBOARD_METRIC(bank_deposit_total,
                          "metric.economy.bank_deposit_total",
                          "currency",
                          "positive open deposit-account balances")
MACRO_SIM_DASHBOARD_METRIC(household_debt_total,
                          "metric.economy.household_debt_total",
                          "currency",
                          "active loan principal owed by households")
MACRO_SIM_DASHBOARD_METRIC(household_debt_total_observed,
                          "metric.economy.household_debt_total_observed",
                          "currency",
                          "active loan principal owed by households")
MACRO_SIM_DASHBOARD_METRIC(firm_debt_total,
                          "metric.economy.firm_debt_total",
                          "currency",
                          "active loan principal owed by firms")
MACRO_SIM_DASHBOARD_METRIC(household_debt_gini,
                          "metric.economy.household_debt_gini",
                          "index",
                          "Gini of household active loan principal")
MACRO_SIM_DASHBOARD_METRIC(household_debt_top10_share,
                          "metric.economy.household_debt_top10_share",
                          "share",
                          "top household debt decile / household debt")
MACRO_SIM_DASHBOARD_METRIC(firm_debt_gini,
                          "metric.economy.firm_debt_gini",
                          "index",
                          "Gini of active-firm loan principal")
MACRO_SIM_DASHBOARD_METRIC(firm_debt_top10_share,
                          "metric.economy.firm_debt_top10_share",
                          "share",
                          "top active-firm debt decile / firm debt")
MACRO_SIM_DASHBOARD_METRIC(equity_market_cap,
                          "metric.economy.equity_market_cap",
                          "currency",
                          "firm plus bank equity market capitalization")
MACRO_SIM_DASHBOARD_METRIC(tobin_q_mean,
                          "metric.economy.tobin_q_mean",
                          "index",
                          "mean active-firm smoothed Tobin Q")
MACRO_SIM_DASHBOARD_METRIC(tobin_q_dispersion,
                          "metric.economy.tobin_q_dispersion",
                          "index",
                          "standard deviation of active-firm smoothed Tobin Q")
MACRO_SIM_DASHBOARD_METRIC(equity_wealth_share,
                          "metric.economy.equity_wealth_share",
                          "share",
                          "household equity value / household gross financial assets")
MACRO_SIM_DASHBOARD_METRIC(equity_ownership_gini,
                          "metric.economy.equity_ownership_gini",
                          "index",
                          "Gini of household equity market value")
MACRO_SIM_DASHBOARD_METRIC(hh_wealth_gini_incl_equity,
                          "metric.economy.hh_wealth_gini_incl_equity",
                          "index",
                          "Gini of household net wealth including securities")
MACRO_SIM_DASHBOARD_METRIC(mortgage_count,
                          "metric.economy.mortgage_count",
                          "loans",
                          "active mortgage contracts")
MACRO_SIM_DASHBOARD_METRIC(tenant_share,
                          "metric.economy.tenant_share",
                          "share",
                          "tenant households / occupied households")
MACRO_SIM_DASHBOARD_METRIC(rental_vacancies,
                          "metric.economy.rental_vacancies",
                          "dwellings",
                          "unoccupied household-owned dwellings")
MACRO_SIM_DASHBOARD_METRIC(landlord_count,
                          "metric.economy.landlord_count",
                          "households",
                          "households owning a dwelling occupied by another household")
MACRO_SIM_DASHBOARD_METRIC(builder_wip_units,
                          "metric.economy.builder_wip_units",
                          "dwellings",
                          "builder work in progress")
MACRO_SIM_DASHBOARD_METRIC(builder_inventory_units,
                          "metric.economy.builder_inventory_units",
                          "dwellings",
                          "builder finished dwelling inventory")
MACRO_SIM_DASHBOARD_METRIC(builder_employment,
                          "metric.economy.builder_employment",
                          "fte",
                          "active hours at construction firms")
MACRO_SIM_DASHBOARD_METRIC(energy_cost_share,
                          "metric.economy.energy_cost_share",
                          "share",
                          "household energy spending / household consumption")
MACRO_SIM_DASHBOARD_METRIC(energy_coverage_mean,
                          "metric.economy.energy_coverage_mean",
                          "days",
                          "energy stocks / current energy use")
MACRO_SIM_DASHBOARD_METRIC(net_population_growth_rate_annualized,
                          "metric.economy.net_population_growth_rate_annualized",
                          "per_year",
                          "365 * (births - deaths) / population")
MACRO_SIM_DASHBOARD_METRIC(birth_rate_per_1000_annualized,
                          "metric.economy.birth_rate_per_1000_annualized",
                          "persons_per_thousand_year",
                          "365000 * births / population")
MACRO_SIM_DASHBOARD_METRIC(death_rate_per_1000_annualized,
                          "metric.economy.death_rate_per_1000_annualized",
                          "persons_per_thousand_year",
                          "365000 * deaths / population")
MACRO_SIM_DASHBOARD_METRIC(firm_count_c,
                          "metric.economy.firm_count_c",
                          "firms",
                          "active consumption firms")
MACRO_SIM_DASHBOARD_METRIC(firm_count_k,
                          "metric.economy.firm_count_k",
                          "firms",
                          "active capital firms")
MACRO_SIM_DASHBOARD_METRIC(firm_count_e,
                          "metric.economy.firm_count_e",
                          "firms",
                          "active energy firms")
MACRO_SIM_DASHBOARD_METRIC(firm_count_construction,
                          "metric.economy.firm_count_construction",
                          "firms",
                          "active construction firms")
MACRO_SIM_DASHBOARD_METRIC(n_firms_producing,
                          "metric.economy.n_firms_producing",
                          "firms",
                          "active firms with current production or labor input")
MACRO_SIM_DASHBOARD_METRIC(n_firms_selling,
                          "metric.economy.n_firms_selling",
                          "firms",
                          "active firms with trailing sales")
MACRO_SIM_DASHBOARD_METRIC(n_firms_borrowing,
                          "metric.economy.n_firms_borrowing",
                          "firms",
                          "active firms with loan principal")
MACRO_SIM_DASHBOARD_METRIC(firm_size_gini_output,
                          "metric.economy.firm_size_gini_output",
                          "index",
                          "Gini of active-firm trailing nominal sales")
MACRO_SIM_DASHBOARD_METRIC(firm_size_top_share_output,
                          "metric.economy.firm_size_top_share_output",
                          "share",
                          "top active-firm output decile / firm output")
MACRO_SIM_DASHBOARD_METRIC(firm_size_pareto_slope,
                          "metric.economy.firm_size_pareto_slope",
                          "index",
                          "Pareto alpha fitted to the upper active-firm output decile")
MACRO_SIM_DASHBOARD_METRIC(working_age_population,
                          "metric.economy.working_age_population",
                          "persons",
                          "living persons between working and retirement ages")
MACRO_SIM_DASHBOARD_METRIC(child_population,
                          "metric.economy.child_population",
                          "persons",
                          "living persons younger than 18")
MACRO_SIM_DASHBOARD_METRIC(child_share,
                          "metric.economy.child_share",
                          "share",
                          "children / population")
MACRO_SIM_DASHBOARD_METRIC(adult_share,
                          "metric.economy.adult_share",
                          "share",
                          "working-age adults / population")
MACRO_SIM_DASHBOARD_METRIC(elder_population,
                          "metric.economy.elder_population",
                          "persons",
                          "living persons at or above retirement age")
MACRO_SIM_DASHBOARD_METRIC(elder_share,
                          "metric.economy.elder_share",
                          "share",
                          "retirement-age persons / population")
MACRO_SIM_DASHBOARD_METRIC(child_median_consumption,
                          "metric.economy.child_median_consumption",
                          "real_currency",
                          "person-weighted median equivalized consumption of children")
MACRO_SIM_DASHBOARD_METRIC(adult_median_consumption,
                          "metric.economy.adult_median_consumption",
                          "real_currency",
                          "person-weighted median equivalized consumption of working-age adults")
MACRO_SIM_DASHBOARD_METRIC(elder_median_consumption,
                          "metric.economy.elder_median_consumption",
                          "real_currency",
                          "person-weighted median equivalized consumption of retirement-age persons")
MACRO_SIM_DASHBOARD_METRIC(labor_sector_consumption_fte,
                          "metric.economy.labor_sector_consumption_fte",
                          "fte",
                          "active hours at consumption firms")
MACRO_SIM_DASHBOARD_METRIC(labor_sector_capital_fte,
                          "metric.economy.labor_sector_capital_fte",
                          "fte",
                          "active hours at capital firms")
MACRO_SIM_DASHBOARD_METRIC(labor_sector_energy_fte,
                          "metric.economy.labor_sector_energy_fte",
                          "fte",
                          "active hours at energy firms")
MACRO_SIM_DASHBOARD_METRIC(labor_sector_construction_fte,
                          "metric.economy.labor_sector_construction_fte",
                          "fte",
                          "active hours at construction firms")
MACRO_SIM_DASHBOARD_METRIC(sector_consumption_sales,
                          "metric.economy.sector_consumption_sales",
                          "goods_units_per_tick",
                          "trailing sales of consumption firms")
MACRO_SIM_DASHBOARD_METRIC(sector_capital_sales,
                          "metric.economy.sector_capital_sales",
                          "goods_units_per_tick",
                          "trailing sales of capital firms")
MACRO_SIM_DASHBOARD_METRIC(sector_energy_sales,
                          "metric.economy.sector_energy_sales",
                          "goods_units_per_tick",
                          "trailing sales of energy firms")
MACRO_SIM_DASHBOARD_METRIC(sector_construction_sales,
                          "metric.economy.sector_construction_sales",
                          "goods_units_per_tick",
                          "trailing sales of construction firms")
MACRO_SIM_DASHBOARD_METRIC(age_15_24_participation,
                          "metric.economy.age_15_24_participation",
                          "share",
                          "participating persons age 15-24 / persons age 15-24")
MACRO_SIM_DASHBOARD_METRIC(age_25_34_participation,
                          "metric.economy.age_25_34_participation",
                          "share",
                          "participating persons age 25-34 / persons age 25-34")
MACRO_SIM_DASHBOARD_METRIC(age_35_44_participation,
                          "metric.economy.age_35_44_participation",
                          "share",
                          "participating persons age 35-44 / persons age 35-44")
MACRO_SIM_DASHBOARD_METRIC(age_45_54_participation,
                          "metric.economy.age_45_54_participation",
                          "share",
                          "participating persons age 45-54 / persons age 45-54")
MACRO_SIM_DASHBOARD_METRIC(age_55_64_participation,
                          "metric.economy.age_55_64_participation",
                          "share",
                          "participating persons age 55-64 / persons age 55-64")
MACRO_SIM_DASHBOARD_METRIC(age_65_plus_participation,
                          "metric.economy.age_65_plus_participation",
                          "share",
                          "participating persons age 65+ / persons age 65+")
MACRO_SIM_DASHBOARD_METRIC(age_15_24_employment,
                          "metric.economy.age_15_24_employment",
                          "share",
                          "employed persons age 15-24 / persons age 15-24")
MACRO_SIM_DASHBOARD_METRIC(age_25_34_employment,
                          "metric.economy.age_25_34_employment",
                          "share",
                          "employed persons age 25-34 / persons age 25-34")
MACRO_SIM_DASHBOARD_METRIC(age_35_44_employment,
                          "metric.economy.age_35_44_employment",
                          "share",
                          "employed persons age 35-44 / persons age 35-44")
MACRO_SIM_DASHBOARD_METRIC(age_45_54_employment,
                          "metric.economy.age_45_54_employment",
                          "share",
                          "employed persons age 45-54 / persons age 45-54")
MACRO_SIM_DASHBOARD_METRIC(age_55_64_employment,
                          "metric.economy.age_55_64_employment",
                          "share",
                          "employed persons age 55-64 / persons age 55-64")
MACRO_SIM_DASHBOARD_METRIC(age_65_plus_employment,
                          "metric.economy.age_65_plus_employment",
                          "share",
                          "employed persons age 65+ / persons age 65+")
MACRO_SIM_DASHBOARD_METRIC(pyramid_male_0_14,
                          "metric.economy.pyramid_male_0_14",
                          "persons",
                          "living male persons age 0-14")
MACRO_SIM_DASHBOARD_METRIC(pyramid_female_0_14,
                          "metric.economy.pyramid_female_0_14",
                          "persons",
                          "living female persons age 0-14")
MACRO_SIM_DASHBOARD_METRIC(pyramid_male_15_24,
                          "metric.economy.pyramid_male_15_24",
                          "persons",
                          "living male persons age 15-24")
MACRO_SIM_DASHBOARD_METRIC(pyramid_female_15_24,
                          "metric.economy.pyramid_female_15_24",
                          "persons",
                          "living female persons age 15-24")
MACRO_SIM_DASHBOARD_METRIC(pyramid_male_25_34,
                          "metric.economy.pyramid_male_25_34",
                          "persons",
                          "living male persons age 25-34")
MACRO_SIM_DASHBOARD_METRIC(pyramid_female_25_34,
                          "metric.economy.pyramid_female_25_34",
                          "persons",
                          "living female persons age 25-34")
MACRO_SIM_DASHBOARD_METRIC(pyramid_male_35_44,
                          "metric.economy.pyramid_male_35_44",
                          "persons",
                          "living male persons age 35-44")
MACRO_SIM_DASHBOARD_METRIC(pyramid_female_35_44,
                          "metric.economy.pyramid_female_35_44",
                          "persons",
                          "living female persons age 35-44")
MACRO_SIM_DASHBOARD_METRIC(pyramid_male_45_54,
                          "metric.economy.pyramid_male_45_54",
                          "persons",
                          "living male persons age 45-54")
MACRO_SIM_DASHBOARD_METRIC(pyramid_female_45_54,
                          "metric.economy.pyramid_female_45_54",
                          "persons",
                          "living female persons age 45-54")
MACRO_SIM_DASHBOARD_METRIC(pyramid_male_55_64,
                          "metric.economy.pyramid_male_55_64",
                          "persons",
                          "living male persons age 55-64")
MACRO_SIM_DASHBOARD_METRIC(pyramid_female_55_64,
                          "metric.economy.pyramid_female_55_64",
                          "persons",
                          "living female persons age 55-64")
MACRO_SIM_DASHBOARD_METRIC(pyramid_male_65_plus,
                          "metric.economy.pyramid_male_65_plus",
                          "persons",
                          "living male persons age 65+")
MACRO_SIM_DASHBOARD_METRIC(pyramid_female_65_plus,
                          "metric.economy.pyramid_female_65_plus",
                          "persons",
                          "living female persons age 65+")
