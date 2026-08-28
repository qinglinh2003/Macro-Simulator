extends SceneTree

const LocaleCatalogScript := preload("res://scripts/localization.gd")
const MainScript := preload("res://scripts/main.gd")


func _init() -> void:
	var game := MainScript.new()
	var lever := {
		"evidence_scope": {
			"coverage": "single_policy_calibrated",
			"individual_classification": "effective",
			"package_findings": [{
				"package_disposition": "package_guardrail_failure",
				"package_id": "recession_response",
				"role": "harmful",
				"scenario_id": "CR_DEMAND_RECESSION",
			}],
			"population_per_country": 100000,
			"real_world_empirical_claim": false,
			"scale_disposition": "finite_size_confirmed",
			"tested_crisis_states": [
				"CR_DEMAND_RECESSION", "CR_SUPPLY_STAGFLATION",
			],
		},
	}
	LocaleCatalogScript.set_locale("en")
	var english: String = game._lever_evidence_text(lever)
	assert("Single-policy classification: effective" in english)
	assert("Recession response" in english)
	assert("not real-world causal estimates" in english)
	LocaleCatalogScript.set_locale("zh_CN")
	var chinese: String = game._lever_evidence_text(lever)
	assert(chinese != english)
	assert(chinese.length() > 80)
	assert("desktop.policy.evidence" not in chinese)
	game.free()
	quit(0)
