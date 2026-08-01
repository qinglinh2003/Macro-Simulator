extends RefCounted

var _game
var _failure := ""


func run(game) -> bool:
	_game = game
	_report("boot")
	if not await _wait_until(func() -> bool:
		return _game._client != null \
			and _game._client._was_connected \
			and not _game._client.busy):
		return false
	_report("connected")
	if OS.get_environment("MACRO_SIM_E2E_HOLD_AFTER_CONNECT") == "1":
		while true:
			await _game.get_tree().process_frame

	_game._on_start_menu_launch({"spec": _new_game_spec()})
	if not await _wait_idle():
		return false
	_report("new_game")
	if not _require(not _game._snapshot.is_empty(), "snapshot is empty"):
		return false
	if not _require(not _game._schemas.is_empty(), "schemas are empty"):
		return false
	if not _require(
		int(_game._snapshot.get("tick", -1)) == 0,
		"new session did not start at day zero",
	):
		return false
	if not _require(
		str(_game._snapshot.get("control_mode", "")) == "free_policy",
		"desktop session did not enter free-policy mode",
	):
		return false
	if not _require(
		not bool(_game._snapshot.get("awaiting_human", true)),
		"free-policy mode unexpectedly opened a human decision boundary",
	):
		return false
	var world: Dictionary = _game._snapshot.get("world", {})
	var latest: Dictionary = world.get("latest", {})
	if not _require(
		(latest.get("economies", []) as Array).size() == 2,
		"new session does not contain two economies",
	):
		return false
	var metric_values: Dictionary = _game._snapshot.get("metric_values", {})
	if not _require(
		metric_values.has("metric.source.m8.housing.house_price"),
		"housing metric is absent",
	):
		return false
	for stable_id: String in [
		"metric.source.m4.tax_profit",
		"metric.source.m4.tax_income",
		"metric.source.m4.tax_consumption",
		"metric.economy.energy_coverage_mean",
		"metric.economy.pyramid_male_0_14",
		"metric.economy.firm_size_pareto_slope",
		"metric.economy.na.household_consumption_real",
	]:
		if not _require(
			metric_values.has(stable_id),
			"native dashboard metric is absent: %s" % stable_id,
		):
			return false
	var panel_details: Dictionary = _game._snapshot.get("panel_details", {})
	if not _require(
		(((panel_details.get("population", {}) as Dictionary).get(
			"pyramid", [])) as Array).size() == 7,
		"population pyramid projection is incomplete",
	):
		return false
	if not _require(
		(((panel_details.get("labor", {}) as Dictionary).get(
			"participation_by_age", [])) as Array).size() == 6,
		"age participation projection is incomplete",
	):
		return false
	for tab_name in ["households", "firms", "stocks"]:
		_game._tab = tab_name
		_game._render()
		if not await _wait_idle():
			return false
		if not await _capture_tab(tab_name):
			return false
	if not _require(
		not (
			_game._snapshot.get("households", {}).get("items", []) as Array
		).is_empty(),
		"household projection is empty",
	):
		return false
	var household_items: Array = (
		_game._snapshot.get("households", {}).get("items", []) as Array)
	var selected_household_id := int(_game._household_selected)
	var selected_household: Dictionary = {}
	for household: Dictionary in household_items:
		if int(household.get("household_id", 0)) == selected_household_id:
			selected_household = household
			break
	var first_members: Array = (
		selected_household.get("members", []) as Array)
	var first_member_count := int(selected_household.get("member_count", 0))
	if not _require(
		first_member_count > 1 and first_members.size() == first_member_count,
		"household projection did not join every member record",
	):
		return false
	if not _require(
		selected_household_id > 0
			and _game._m11_adapter.entity_scope(
				"household_persons") == selected_household_id
			and _game._m11_adapter.entity_scope(
				"household_jobs") == selected_household_id,
		"household member queries were not scoped to the selected household",
	):
		return false
	for relation_key: String in [
		"mother_id", "father_id", "partner_id", "guardian_id",
	]:
		var relation: Variant = (
			first_members[0] as Dictionary).get(relation_key)
		if not _require(
			relation == null or int(relation) < 4294967295,
			"household projection leaked an invalid relation identifier",
		):
			return false
	var next_household: Dictionary = {}
	for household: Dictionary in household_items:
		if int(household.get("household_id", 0)) != selected_household_id \
				and int(household.get("member_count", 0)) > 1:
			next_household = household
			break
	if not _require(
		not next_household.is_empty(),
		"household projection does not contain a second multi-member family",
	):
		return false
	_game._household_selected = int(next_household.get("household_id", 0))
	_game._tab = "households"
	_game._render()
	if not await _wait_idle():
		return false
	household_items = (
		_game._snapshot.get("households", {}).get("items", []) as Array)
	var switched_household: Dictionary = {}
	for household: Dictionary in household_items:
		if int(household.get(
				"household_id", 0)) == _game._household_selected:
			switched_household = household
			break
	if not _require(
		(switched_household.get("members", []) as Array).size()
			== int(switched_household.get("member_count", 0))
			and _game._m11_adapter.entity_scope(
				"household_persons") == _game._household_selected
			and _game._m11_adapter.entity_scope(
				"household_jobs") == _game._household_selected,
		"switching families did not refresh every household member",
	):
		return false
	if not _require(
		not (
			_game._snapshot.get("firms", {}).get("items", []) as Array
		).is_empty(),
		"firm projection is empty",
	):
		return false
	var selected_firm_id := int(_game._firm_selected)
	if not _require(
		selected_firm_id > 0
			and _game._m11_adapter.entity_scope("firm_jobs") == selected_firm_id
			and _game._m11_adapter.entity_scope(
				"firm_persons") == selected_firm_id,
		"firm employment queries were not scoped to the selected firm",
	):
		return false
	if not _require(
		not (
			_game._snapshot.get(
				"stock_market", {}).get("listings", []) as Array
		).is_empty(),
		"stock-market projection is empty",
	):
		return false
	var market: Dictionary = _game._snapshot.get("stock_market", {})
	var listings: Array = market.get("listings", [])
	var has_company := false
	var has_bank := false
	for listing: Dictionary in listings:
		if str(listing.get("instrument_type", "")) == "company":
			has_company = true
			if not _require(
				str(listing.get("sector_id", "unknown")) != "unknown",
				"listed company was not joined to its sector",
			):
				return false
		elif str(listing.get("instrument_type", "")) == "bank":
			has_bank = true
	if not _require(
		has_company and has_bank,
		"stock-market issuer filters are incomplete",
	):
		return false
	var market_summary: Dictionary = market.get("summary", {})
	if not _require(
		is_equal_approx(
			float(market_summary.get("market_cap", 0.0)),
			float(market_summary.get("corporate_market_cap", 0.0))
				+ float(market_summary.get("bank_market_cap", 0.0)),
		),
		"stock-market capitalization split does not reconcile",
	):
		return false
	_game._tab = "focus"
	_game._render()

	_game._send({
		"command": "stage_policy",
		"actions": [{
			"lever": "gov_consumption_share",
			"value": 0.35,
		}],
	})
	if not await _wait_idle():
		return false
	_report("policy_staged")
	if not _require(
		(_game._snapshot.get("free_policy", {}).get("actions", []) as Array).size() == 1,
		"free-policy action was not staged",
	):
		return false
	if not _require(
		int(_game._snapshot.get("tick", -1)) == 0,
		"staging a policy changed the current day",
	):
		return false

	_game._send({"command": "advance", "ticks": 1})
	if not await _wait_idle():
		return false
	_report("policy_effective")
	var saved_tick := int(_game._snapshot.get("tick", -1))
	if not _require(saved_tick == 1, "simulation did not advance exactly one day"):
		return false
	if not _require(
		is_equal_approx(
			float(_game._snapshot.get(
				"policy_values", {}).get("gov_consumption_share", -1.0)),
			0.35,
		),
		"staged policy was not effective on the next day",
	):
		return false
	if not _require(
		(_game._snapshot.get("free_policy", {}).get("actions", []) as Array).is_empty(),
		"effective free-policy queue was not cleared",
	):
		return false
	_game._send({"command": "advance", "ticks": 1})
	if not await _wait_idle():
		return false
	saved_tick = int(_game._snapshot.get("tick", -1))
	if not _require(
		saved_tick == 2,
		"simulation did not retain the post-policy day boundary",
	):
		return false

	# Exercise the frontend edit path, including nullable controls, coupled
	# regimes, and both generated enabled_if dependencies.
	var nullable_lever: Dictionary = _game._lever_info.get(
		"tax_luxury_rate", {})
	if not _require(
		not nullable_lever.is_empty()
			and bool(nullable_lever.get("nullable", false))
			and str(nullable_lever.get("value_kind", "")) == "number",
		"nullable numeric policy was not normalized into an editable control",
	):
		return false
	_game._set_policy_edit(nullable_lever, 0.1)
	if not await _wait_idle():
		return false
	if not _require(
		_pending_policy_names().has("tax_luxury_rate"),
		"nullable numeric policy was not staged through the frontend",
	):
		return false
	_game._send({"command": "advance", "ticks": 1})
	if not await _wait_idle():
		return false
	if not _require(
		is_equal_approx(float(_game._snapshot.get(
			"policy_values", {}).get("tax_luxury_rate", -1.0)), 0.1),
		"nullable numeric policy did not become effective",
	):
		return false

	_game._set_policy_edit(
		_game._lever_info.get("monetary_regime", {}), "manual")
	if not await _wait_idle():
		return false
	var monetary_names := _pending_policy_names()
	if not _require(
		monetary_names.has("monetary_regime")
			and monetary_names.has("manual_policy_rate"),
		"manual monetary regime was not staged with its rate",
	):
		return false
	_game._send({"command": "advance", "ticks": 1})
	if not await _wait_idle():
		return false
	var policy_values: Dictionary = _game._snapshot.get("policy_values", {})
	if not _require(
		str(policy_values.get("monetary_regime", "")) == "manual"
			and policy_values.get("manual_policy_rate") != null,
		"manual monetary regime did not apply atomically",
	):
		return false

	_game._set_policy_edit(
		_game._lever_info.get("fx_regime", {}), "peg")
	if not await _wait_idle():
		return false
	var peg_names := _pending_policy_names()
	if not _require(
		peg_names.has("fx_regime") and peg_names.has("peg_anchor"),
		"currency peg was not staged with a valid anchor",
	):
		return false
	_game._send({"command": "advance", "ticks": 1})
	if not await _wait_idle():
		return false
	policy_values = _game._snapshot.get("policy_values", {})
	if not _require(
		str(policy_values.get("fx_regime", "")) == "peg"
			and int(policy_values.get("peg_anchor", -1)) == 1,
		"currency peg did not apply atomically",
	):
		return false

	for dependency: Array in [
		["omo", "omo_index_deposits"],
		["soe_efirm", "soe_price_at_cost"],
	]:
		var prerequisite := str(dependency[0])
		var dependent := str(dependency[1])
		if not _require(
			_game._lever_info.has(prerequisite)
				and _game._lever_info.has(dependent),
			"dependency test policies are absent: %s / %s" % [
				prerequisite, dependent],
		):
			return false
		_game._set_policy_edit(
			_game._lever_info.get(prerequisite, {}), false)
		if not await _wait_idle():
			return false
		_game._send({"command": "advance", "ticks": 1})
		if not await _wait_idle():
			return false
		var dependent_target := not bool(
			_game._snapshot.get("policy_values", {}).get(dependent, false))
		_game._set_policy_edit(
			_game._lever_info.get(dependent, {}), dependent_target)
		if not await _wait_idle():
			return false
		var dependency_names := _pending_policy_names()
		if not _require(
			dependency_names.has(prerequisite)
				and dependency_names.has(dependent),
			"%s was not staged with prerequisite %s; enabled_if=%s, values=%s, pending=%s, cart=%s" % [
				dependent, prerequisite,
				_game._lever_info.get(dependent, {}).get("enabled_if", []),
				_game._snapshot.get("policy_values", {}),
				dependency_names, _game._cart],
		):
			return false
		_game._send({"command": "advance", "ticks": 1})
		if not await _wait_idle():
			return false
		policy_values = _game._snapshot.get("policy_values", {})
		if not _require(
			bool(policy_values.get(prerequisite, false))
				and bool(policy_values.get(dependent, not dependent_target))
					== dependent_target,
			"%s and prerequisite %s did not apply atomically" % [
				dependent, prerequisite],
		):
			return false
	saved_tick = int(_game._snapshot.get("tick", -1))

	_game._tab = "stocks"
	_game._render()
	if not await _wait_idle():
		return false
	if not _require(
		(_game._snapshot.get(
			"stock_market", {}).get("history", []) as Array).size() >= 2,
		"stock-market index did not retain cross-day history",
	):
		return false
	_game._tab = "focus"
	_game._render()

	_game._send({
		"command": "schedule_shock",
		"seat": "energy",
		"shock": {
			"shock_id": 99001,
			"kind": "energy_capacity",
			"economy_id": 0,
			"announcement": saved_tick,
			"start": saved_tick + 1,
			"duration": 2,
			"magnitude": 0.2,
			"shape": "step",
		},
	})
	if not await _wait_idle():
		return false
	_report("crisis")
	if not _require(
		not (_game._snapshot.get("shock_bulletins", []) as Array).is_empty(),
		"shock bulletin is absent",
	):
		return false

	_game._send({"command": "save_slot", "slot_id": "godot_e2e"})
	if not await _wait_idle():
		return false
	_report("saved")
	_game._send({"command": "close_session"})
	if not await _wait_idle():
		return false
	if not _require(
		_game._client._session_id.is_empty(),
		"session did not close before reload",
	):
		return false
	_game._send({"command": "load_slot", "slot_id": "godot_e2e"})
	if not await _wait_idle():
		return false
	_report("loaded")
	if not _require(
		int(_game._snapshot.get("tick", -1)) == saved_tick,
		"loaded session resumed at the wrong day",
	):
		return false
	if not _require(
		not _game._client._session_id.is_empty(),
		"loaded session has no identifier",
	):
		return false

	_game._send({"command": "advance", "ticks": 30})
	if not await _wait_idle():
		return false
	_game._tab = "firms"
	_game._render()
	if not await _wait_idle():
		return false
	var active_firm: Dictionary = {}
	for firm: Dictionary in (
		_game._snapshot.get("firms", {}).get("items", []) as Array
	):
		if int((firm.get("labor", {}) as Dictionary).get(
			"contract_count", 0)) > 0:
			active_firm = firm
			break
	if not _require(
		not active_firm.is_empty(),
		"mature session did not expose a firm with labor contracts",
	):
		return false
	_game._firm_selected = str(active_firm.get("firm_id", ""))
	_game._render()
	if not await _wait_idle():
		return false
	var selected_firm: Dictionary = {}
	for firm: Dictionary in (
		_game._snapshot.get("firms", {}).get("items", []) as Array
	):
		if str(firm.get("firm_id", "")) == _game._firm_selected:
			selected_firm = firm
			break
	var contracts: Array = (
		(selected_firm.get("labor", {}) as Dictionary).get(
			"employees", []) as Array)
	if not _require(
		not contracts.is_empty(),
		"selected firm did not receive its exact labor-contract rows",
	):
		return false
	for contract: Dictionary in contracts:
		if not _require(
			int(contract.get("job_id", 0)) > 0
				and float(contract.get("contract_hours", 0.0)) > 0.0
				and contract.get("locked_wage") != null,
			"labor contract is missing its identifier, hours, or wage",
		):
			return false
	if not await _capture_tab("firms_contracts"):
		return false

	_game._send({"command": "shutdown"})
	if not await _wait_idle():
		return false
	_report("shutdown")
	_write_completion("m11_e2e:shutdown\n")
	return true


func failure() -> String:
	return _failure


func _pending_policy_names() -> Dictionary:
	var names: Dictionary = {}
	for action: Dictionary in _game._snapshot.get(
		"free_policy", {}).get("actions", []):
		names[str(action.get("lever", ""))] = action.get("value")
	return names


func _capture_tab(tab_name: String) -> bool:
	var capture_dir := OS.get_environment("MACRO_SIM_E2E_CAPTURE_DIR")
	if capture_dir.is_empty():
		return true
	var error := DirAccess.make_dir_recursive_absolute(capture_dir)
	if error != OK:
		return _require(false, "could not create E2E capture directory")
	await _game.get_tree().create_timer(0.45).timeout
	await _game.get_tree().process_frame
	await _game.get_tree().process_frame
	var texture: Texture2D = _game.get_viewport().get_texture()
	if texture == null:
		return _require(false, "E2E capture has no viewport texture")
	var image: Image = texture.get_image()
	if image == null:
		return _require(false, "E2E capture has no viewport image")
	error = image.save_png(capture_dir.path_join("%s.png" % tab_name))
	return _require(error == OK, "could not save E2E capture: %s" % tab_name)


func _report(phase: String) -> void:
	var message := "m11_e2e:%s" % phase
	print(message)
	var progress_path := OS.get_environment("MACRO_SIM_E2E_PROGRESS_FILE")
	if progress_path.is_empty():
		return
	var progress := FileAccess.open(progress_path, FileAccess.WRITE)
	if progress == null:
		push_error("Unable to write the M11 E2E progress marker.")
		return
	progress.store_string(message + "\n")
	progress.flush()


func _write_completion(content: String) -> void:
	var completion_path := OS.get_environment(
		"MACRO_SIM_E2E_COMPLETION_FILE")
	if completion_path.is_empty():
		return
	var completion := FileAccess.open(completion_path, FileAccess.WRITE)
	if completion == null:
		push_error("Unable to write the M11 E2E completion marker.")
		return
	completion.store_string(content)
	completion.flush()


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	_failure = message
	push_error("M11 E2E failed: %s" % message)
	_write_completion("m11_e2e:failed:%s\n" % message)
	return false


func _wait_idle() -> bool:
	await _game.get_tree().process_frame
	return await _wait_until(func() -> bool:
		return not _game._client.busy \
			and _game._outbox.is_empty() \
			and _game._active_command.is_empty())


func _wait_until(predicate: Callable, timeout_seconds := 30.0) -> bool:
	var deadline := Time.get_ticks_msec() + int(timeout_seconds * 1000.0)
	while not predicate.call():
		if Time.get_ticks_msec() >= deadline:
			return _require(
				false,
				"timed out while waiting for the client state",
			)
		await _game.get_tree().process_frame
	return true


func _new_game_spec() -> Dictionary:
	return {
		"schema_version": 1,
		"seed": 41,
		"start_date": "2024-01-01",
		"scenario": "sandbox",
		"duration": 365,
		"world": {
			"trade": true,
			"capital": true,
			"migration": true,
			"fx_lambda": 0.05,
			"fx_friction": 0.03,
			"fx_trade_cap": 0.15,
			"capital_mobility": 1.0,
			"capital_adjust": 0.2,
			"migration_rate": 0.02,
			"migration_max_share": 0.25,
			"remittance_share": 0.2,
			"wage_smoothing": 0.02,
			"peg_reserves0": 5000.0,
		},
		"countries": [
			{
				"name": "Aurelia",
				"code": "AUR",
				"profile": "advanced",
				"overrides": {
					"demographics_population": 80,
					"n_firms_c": 8,
					"n_firms_k": 3,
					"n_firms_e": 2,
					"n_builders": 2,
					"n_banks": 2,
					"bank_enabled": true,
					"interbank": true,
					"bonds": true,
					"energy_enabled": true,
					"government": true,
				},
			},
			{
				"name": "Borvia",
				"code": "BOR",
				"profile": "developing",
				"overrides": {
					"demographics_population": 90,
					"n_firms_c": 9,
					"n_firms_k": 3,
					"n_firms_e": 2,
					"n_builders": 2,
					"n_banks": 2,
					"bank_enabled": true,
					"interbank": true,
					"bonds": true,
					"energy_enabled": true,
					"government": true,
				},
			},
		],
		"player_country": 0,
		"run_mode": "interactive",
		"seats": {
			"treasury": "null",
			"cb": "null",
			"labor_social": "null",
			"regulator": "null",
			"external": "null",
			"energy": "null",
		},
		"initial_policy_overrides": {},
	}
