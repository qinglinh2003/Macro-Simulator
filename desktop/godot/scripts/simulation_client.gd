class_name SimulationClient
extends Node

signal connected
signal disconnected
signal response_received(response: Dictionary)
signal request_failed(message: String)

const PROTOCOL_VERSION := 5
const MAXIMUM_RESPONSE_BYTES := 4 * 1024 * 1024
const RETRY_DELAY_MS := 600
const CONNECTION_ID_PATH := "user://m11_connection_id"

var _peer := StreamPeerTCP.new()
var _receive_buffer := PackedByteArray()
var _host := "127.0.0.1"
var _port := 0
var _token := ""
var _connection_id := ""
var _session_id := ""
var _was_connected := false
var _retry_at_ms := 0
var _request_sequence := 0
var _pending_request_id := ""
var _pending_frame := PackedByteArray()
var _base_snapshot_id := ""
var _configured := false
var busy := false


func _ready() -> void:
	_connection_id = _load_or_create_connection_id()
	_configured = _consume_bootstrap()
	set_process(true)
	if _configured:
		connect_local()


func connect_local() -> void:
	if not _configured or _peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		return
	_peer = StreamPeerTCP.new()
	var error := _peer.connect_to_host(_host, _port)
	if error != OK:
		_retry_at_ms = Time.get_ticks_msec() + RETRY_DELAY_MS


func send_command(command: Dictionary) -> void:
	if not _configured:
		request_failed.emit("The native simulation bootstrap is unavailable.")
		return
	if _peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		request_failed.emit("The native simulation worker is not connected.")
		return
	if busy:
		return
	_request_sequence += 1
	var payload := command.duplicate(true)
	var command_name := str(payload.get("command", ""))
	if command_name == "get_schema":
		command_name = "policy_schema"
		payload["command"] = command_name
		payload["role"] = "player"
	elif command_name == "resolve_context":
		command_name = "submit_human_policy"
		payload["command"] = command_name
	if command_name in [
		"submit_policy", "submit_human_policy", "timeout_context",
		"cancel_policy", "assign_seat", "restore_seat", "schedule_shock",
	] and not payload.has("operation_id"):
		payload["operation_id"] = "godot-operation:%d" % _request_sequence
	if not _base_snapshot_id.is_empty() and command_name in [
		"snapshot", "advance", "submit_policy", "submit_human_policy",
		"timeout_context", "cancel_policy", "schedule_shock",
	]:
		payload["base_snapshot_id"] = _base_snapshot_id
	_pending_request_id = "godot:%d" % _request_sequence
	payload["protocol_version"] = PROTOCOL_VERSION
	payload["request_id"] = _pending_request_id
	payload["connection_id"] = _connection_id
	payload["sequence"] = _request_sequence
	payload["token"] = _token
	if not _session_id.is_empty() and command_name not in [
		"hello", "new_session", "new_game", "load_slot",
	]:
		payload["session_id"] = _session_id
	_pending_frame = (JSON.stringify(payload) + "\n").to_utf8_buffer()
	var error := _peer.put_data(_pending_frame)
	if error != OK:
		_pending_frame.clear()
		_pending_request_id = ""
		request_failed.emit("Could not send the simulation command (%d)." % error)
		return
	busy = true


func request_full_snapshot(role := "treasury", economy_id := 0) -> void:
	send_command({
		"command": "snapshot",
		"role": role,
		"economy_id": economy_id,
	})


func _process(_delta: float) -> void:
	if not _configured:
		return
	_peer.poll()
	var status := _peer.get_status()
	var now := Time.get_ticks_msec()
	if status == StreamPeerTCP.STATUS_CONNECTED:
		if not _was_connected:
			_was_connected = true
			connected.emit()
			if busy and not _pending_frame.is_empty():
				var retry_error := _peer.put_data(_pending_frame)
				if retry_error != OK:
					request_failed.emit(
						"Could not retry the interrupted simulation command.")
		_read_available()
	elif status in [StreamPeerTCP.STATUS_NONE, StreamPeerTCP.STATUS_ERROR]:
		if _was_connected:
			_was_connected = false
			_receive_buffer.clear()
			disconnected.emit()
		if now >= _retry_at_ms:
			_retry_at_ms = now + RETRY_DELAY_MS
			connect_local()


func _read_available() -> void:
	var available := _peer.get_available_bytes()
	while available > 0:
		var result := _peer.get_data(available)
		if result[0] != OK:
			request_failed.emit("Could not read the simulation response.")
			return
		_receive_buffer.append_array(result[1] as PackedByteArray)
		if _receive_buffer.size() > MAXIMUM_RESPONSE_BYTES + 1:
			_fail_connection("The simulation response exceeded the protocol limit.")
			return
		_parse_available_frames()
		available = _peer.get_available_bytes()


func _parse_available_frames() -> void:
	var newline := _receive_buffer.find(10)
	while newline >= 0:
		var line := _receive_buffer.slice(0, newline)
		_receive_buffer = _receive_buffer.slice(newline + 1)
		if not line.is_empty():
			_parse_response(line.get_string_from_utf8())
		newline = _receive_buffer.find(10)


func _parse_response(line: String) -> void:
	var parser := JSON.new()
	if parser.parse(line) != OK or not parser.data is Dictionary:
		_fail_request("The native worker returned malformed JSON.")
		return
	var response: Dictionary = parser.data
	if int(response.get("protocol_version", -1)) != PROTOCOL_VERSION:
		_fail_request("The native worker protocol version is incompatible.")
		return
	if str(response.get("request_id", "")) != _pending_request_id:
		_fail_request("The native worker response has the wrong request ID.")
		return
	if str(response.get("connection_id", "")) != _connection_id:
		_fail_request("The native worker response has the wrong connection ID.")
		return
	if int(response.get("sequence", -1)) != _request_sequence:
		_fail_request("The native worker response sequence is invalid.")
		return
	busy = false
	_pending_frame.clear()
	_pending_request_id = ""
	if not response.get("ok", false):
		var error: Dictionary = response.get("error", {})
		request_failed.emit(str(error.get(
			"message", "The native worker rejected the request.")))
		return
	_track_projection(response.get("result", {}))
	var response_session: Variant = response.get("session_id")
	if response_session == null:
		_session_id = ""
	elif response_session is String:
		if not _session_id.is_empty() and _session_id != str(response_session):
			request_failed.emit("The native worker changed the active session unexpectedly.")
			return
		_session_id = str(response_session)
	else:
		request_failed.emit("The native worker returned an invalid session ID.")
		return
	response_received.emit(response)


func _track_projection(result: Variant) -> void:
	if not result is Dictionary:
		return
	var data := result as Dictionary
	var projection: Variant = data.get("projection", data)
	if not projection is Dictionary:
		return
	var projected := projection as Dictionary
	var mode := str(projected.get("mode", ""))
	if mode in ["full", "full_resync"]:
		var snapshot: Dictionary = projected.get("snapshot", {})
		_base_snapshot_id = str(snapshot.get("snapshot_id", ""))
	elif mode == "delta":
		var delta: Dictionary = projected.get("delta", {})
		_base_snapshot_id = str(delta.get("result_snapshot_id", ""))


func _fail_request(message: String) -> void:
	busy = false
	_pending_frame.clear()
	_pending_request_id = ""
	request_failed.emit(message)


func _fail_connection(message: String) -> void:
	_peer.disconnect_from_host()
	_receive_buffer.clear()
	_fail_request(message)


func _consume_bootstrap() -> bool:
	var path := OS.get_environment("MACRO_SIM_CLIENT_BOOTSTRAP")
	if path.is_empty() or not path.is_absolute_path():
		request_failed.emit("The native simulation bootstrap path is missing.")
		return false
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		request_failed.emit("The native simulation bootstrap could not be opened.")
		return false
	var content := file.get_as_text()
	file.close()
	DirAccess.remove_absolute(path)
	var parser := JSON.new()
	if parser.parse(content) != OK or not parser.data is Dictionary:
		request_failed.emit("The native simulation bootstrap is malformed.")
		return false
	var bootstrap: Dictionary = parser.data
	var port := int(bootstrap.get("port", 0))
	var token := str(bootstrap.get("token", ""))
	var version := int(bootstrap.get("protocol_version", -1))
	var host := str(bootstrap.get("host", ""))
	if version != PROTOCOL_VERSION or host != "127.0.0.1" \
			or port < 1 or port > 65535 or not _valid_token(token):
		request_failed.emit("The native simulation bootstrap is invalid.")
		return false
	_host = host
	_port = port
	_token = token
	return true


func _load_or_create_connection_id() -> String:
	if FileAccess.file_exists(CONNECTION_ID_PATH):
		var existing_file := FileAccess.open(CONNECTION_ID_PATH, FileAccess.READ)
		if existing_file != null:
			var existing := existing_file.get_as_text().strip_edges()
			existing_file.close()
			if _valid_connection_id(existing):
				return existing
	var generated := "godot-" + Crypto.new().generate_random_bytes(16).hex_encode()
	var output := FileAccess.open(CONNECTION_ID_PATH, FileAccess.WRITE)
	if output != null:
		output.store_string(generated)
		output.close()
	return generated


func _valid_connection_id(value: String) -> bool:
	if value.length() < 8 or value.length() > 128:
		return false
	for index in value.length():
		var code := value.unicode_at(index)
		if not ((code >= 48 and code <= 57) \
				or (code >= 65 and code <= 90) \
				or (code >= 97 and code <= 122) \
				or code in [45, 95]):
			return false
	return true


func _valid_token(value: String) -> bool:
	if value.length() != 64:
		return false
	for index in value.length():
		var code := value.unicode_at(index)
		if not ((code >= 48 and code <= 57) or (code >= 97 and code <= 102)):
			return false
	return true
