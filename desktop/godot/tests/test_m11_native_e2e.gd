extends SceneTree

const MainScript := preload("res://scripts/main.gd")

var _game


func _init() -> void:
	_run.call_deferred()


func _run() -> void:
	print("m11_e2e:boot")
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "1")
	_game = MainScript.new()
	root.add_child(_game)
	await _wait_until(func() -> bool:
		return _game._client != null \
			and _game._client._was_connected \
			and not _game._client.busy)
	print("m11_e2e:connected")

	_game._on_start_menu_launch({"spec": _new_game_spec()})
	await _wait_idle()
	print("m11_e2e:new_game")
	assert(not _game._snapshot.is_empty())
	assert(not _game._schemas.is_empty())
	assert(int(_game._snapshot.get("tick", -1)) == 0)
	var world: Dictionary = _game._snapshot.get("world", {})
	var latest: Dictionary = world.get("latest", {})
	assert((latest.get("economies", []) as Array).size() == 2)
	var metric_values: Dictionary = _game._snapshot.get("metric_values", {})
	assert(metric_values.has("metric.source.m8.housing.house_price"))
	for tab_name in ["households", "firms", "stocks"]:
		_game._tab = tab_name
		_game._render()
		await _wait_idle()
	assert(not (
		_game._snapshot.get("households", {}).get("items", []) as Array
	).is_empty())
	assert(not (
		_game._snapshot.get("firms", {}).get("items", []) as Array
	).is_empty())
	assert(not (
		_game._snapshot.get("stock_market", {}).get("listings", []) as Array
	).is_empty())
	_game._tab = "focus"
	_game._render()

	_game._send({"command": "advance", "ticks": 1})
	await _wait_idle()
	print("m11_e2e:decision_boundary")
	assert(bool(_game._snapshot.get("awaiting_human", false)))
	assert(not _game._contexts().is_empty())

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
	await _wait_idle()
	print("m11_e2e:first_policy")

	var resolution_guard := 0
	while bool(_game._snapshot.get("awaiting_human", false)):
		var contexts: Array = _game._contexts()
		assert(not contexts.is_empty())
		var context: Dictionary = contexts[0]
		_game._send({
			"command": "resolve_context",
			"context_id": context.get("context_id"),
			"actions": [],
		})
		await _wait_idle()
		resolution_guard += 1
		assert(resolution_guard < 32)
	print("m11_e2e:policies_resolved")

	_game._send({"command": "advance", "ticks": 1})
	await _wait_idle()
	print("m11_e2e:played")
	var saved_tick := int(_game._snapshot.get("tick", -1))
	assert(saved_tick >= 1)

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
	await _wait_idle()
	print("m11_e2e:crisis")
	assert(not (_game._snapshot.get("shock_bulletins", []) as Array).is_empty())

	_game._send({"command": "save_slot", "slot_id": "godot_e2e"})
	await _wait_idle()
	print("m11_e2e:saved")
	_game._send({"command": "close_session"})
	await _wait_idle()
	assert(_game._client._session_id.is_empty())
	_game._send({"command": "load_slot", "slot_id": "godot_e2e"})
	await _wait_idle()
	print("m11_e2e:loaded")
	assert(int(_game._snapshot.get("tick", -1)) == saved_tick)
	assert(not _game._client._session_id.is_empty())

	_game._send({"command": "shutdown"})
	await _wait_idle()
	print("m11_e2e:shutdown")
	_game.queue_free()
	OS.set_environment("MACRO_SIM_SKIP_START_MENU", "")
	quit(0)


func _wait_idle() -> void:
	await process_frame
	await _wait_until(func() -> bool:
		return not _game._client.busy \
			and _game._outbox.is_empty() \
			and _game._active_command.is_empty())


func _wait_until(predicate: Callable, timeout_seconds := 30.0) -> void:
	var deadline := Time.get_ticks_msec() + int(timeout_seconds * 1000.0)
	while not predicate.call():
		if Time.get_ticks_msec() >= deadline:
			push_error("M11 E2E timed out while waiting for the client state.")
			quit(2)
			return
		await process_frame


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
