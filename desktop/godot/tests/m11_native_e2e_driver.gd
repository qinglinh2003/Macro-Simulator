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
	for tab_name in ["households", "firms", "stocks"]:
		_game._tab = tab_name
		_game._render()
		if not await _wait_idle():
			return false
	if not _require(
		not (
			_game._snapshot.get("households", {}).get("items", []) as Array
		).is_empty(),
		"household projection is empty",
	):
		return false
	if not _require(
		not (
			_game._snapshot.get("firms", {}).get("items", []) as Array
		).is_empty(),
		"firm projection is empty",
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
	_game._tab = "focus"
	_game._render()

	_game._send({"command": "advance", "ticks": 1})
	if not await _wait_idle():
		return false
	_report("decision_boundary")
	if not _require(
		bool(_game._snapshot.get("awaiting_human", false)),
		"human decision boundary did not open",
	):
		return false
	if not _require(not _game._contexts().is_empty(), "no decision context opened"):
		return false

	var first_context: Dictionary = _game._contexts()[0]
	var actions: Array = []
	for raw_action: Variant in first_context.get("permitted_actions", []):
		if raw_action is Dictionary and bool(
			(raw_action as Dictionary).get("allowed", false)):
			var action := raw_action as Dictionary
			actions.append({
				"lever": action.get("lever"),
				"value": action.get("current_value"),
			})
			break
	_game._send({
		"command": "resolve_context",
		"context_id": first_context.get("context_id"),
		"actions": actions,
	})
	if not await _wait_idle():
		return false
	_report("first_policy")

	var resolution_guard := 0
	while bool(_game._snapshot.get("awaiting_human", false)):
		var contexts: Array = _game._contexts()
		if not _require(not contexts.is_empty(), "decision context disappeared"):
			return false
		var context: Dictionary = contexts[0]
		_game._send({
			"command": "resolve_context",
			"context_id": context.get("context_id"),
			"actions": [],
		})
		if not await _wait_idle():
			return false
		resolution_guard += 1
		if not _require(
			resolution_guard < 32,
			"decision resolution exceeded its safety bound",
		):
			return false
	_report("policies_resolved")

	_game._send({"command": "advance", "ticks": 1})
	if not await _wait_idle():
		return false
	_report("played")
	var saved_tick := int(_game._snapshot.get("tick", -1))
	if not _require(saved_tick >= 1, "simulation did not advance"):
		return false

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

	_game._send({"command": "shutdown"})
	if not await _wait_idle():
		return false
	_report("shutdown")
	_write_completion("m11_e2e:shutdown\n")
	return true


func failure() -> String:
	return _failure


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
				},
			},
		],
		"player_country": 0,
		"run_mode": "interactive",
		"seats": {
			"treasury": "human",
			"cb": "human",
			"regulator": "human",
			"external": "human",
			"energy": "human",
		},
		"initial_policy_overrides": {},
	}
