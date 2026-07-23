class_name LocaleCatalog
extends RefCounted

const DEFAULT_LOCALE := "zh_CN"
const SUPPORTED_LOCALES := ["en", "zh_CN"]
const RESOURCE_PATTERN := "res://i18n/%s.json"
const KEY_PREFIX := "@"

static var _locale := ""
static var _strings: Dictionary = {}


static func locale() -> String:
	_ensure_loaded()
	return _locale


static func set_locale(requested: String) -> void:
	var normalized: String = (
		requested if requested in SUPPORTED_LOCALES else DEFAULT_LOCALE
	)
	if normalized == _locale and not _strings.is_empty():
		return
	var path: String = RESOURCE_PATTERN % normalized
	var payload: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not payload is Dictionary:
		push_error("Locale resource is not an object: %s" % path)
		_locale = DEFAULT_LOCALE
		_strings = {}
		return
	_locale = normalized
	_strings = payload


static func text(key: String, fallback := "") -> String:
	_ensure_loaded()
	if _strings.has(key):
		return str(_strings[key])
	return fallback if not fallback.is_empty() else key


static func resolve(value: String) -> String:
	if value.begins_with(KEY_PREFIX):
		return text(value.substr(KEY_PREFIX.length()))
	return value


static func format(key: String, values: Variant, fallback := "") -> String:
	return text(key, fallback) % values


static func _ensure_loaded() -> void:
	if not _locale.is_empty() and not _strings.is_empty():
		return
	var requested := OS.get_environment("MACRO_SIM_LOCALE")
	set_locale(requested if requested in SUPPORTED_LOCALES else DEFAULT_LOCALE)
