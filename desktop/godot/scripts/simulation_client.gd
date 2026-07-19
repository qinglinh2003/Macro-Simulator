class_name SimulationClient
extends Node

signal connected
signal disconnected
signal response_received(response: Dictionary)
signal request_failed(message: String)

var _peer := StreamPeerTCP.new()
var _receive_buffer := ""
var _host := "127.0.0.1"
var _port := 47821
var _was_connected := false
var _retry_at_ms := 0
var _request_sequence := 0
var busy := false


func _ready() -> void:
	var configured_port := OS.get_environment("MACRO_SIM_PORT")
	if configured_port.is_valid_int():
		_port = configured_port.to_int()
	set_process(true)
	connect_local()


func connect_local() -> void:
	if _peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		return
	_peer = StreamPeerTCP.new()
	var error := _peer.connect_to_host(_host, _port)
	if error != OK:
		_retry_at_ms = Time.get_ticks_msec() + 1200


func send_command(command: Dictionary) -> void:
	if _peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		request_failed.emit("Simulation worker is not connected yet.")
		return
	if busy:
		return
	_request_sequence += 1
	var payload := command.duplicate(true)
	payload["request_id"] = "godot:%d" % _request_sequence
	var error := _peer.put_data((JSON.stringify(payload) + "\n").to_utf8_buffer())
	if error != OK:
		request_failed.emit("Could not send command (%d)." % error)
		return
	busy = true


func _process(_delta: float) -> void:
	_peer.poll()
	var status := _peer.get_status()
	var now := Time.get_ticks_msec()
	if status == StreamPeerTCP.STATUS_CONNECTED:
		if not _was_connected:
			_was_connected = true
			connected.emit()
		_read_available()
	elif status in [StreamPeerTCP.STATUS_NONE, StreamPeerTCP.STATUS_ERROR]:
		if _was_connected:
			_was_connected = false
			busy = false
			disconnected.emit()
		if now >= _retry_at_ms:
			_retry_at_ms = now + 1200
			connect_local()


func _read_available() -> void:
	var available := _peer.get_available_bytes()
	if available <= 0:
		return
	var result := _peer.get_data(available)
	if result[0] != OK:
		request_failed.emit("Could not read simulation response.")
		return
	_receive_buffer += (result[1] as PackedByteArray).get_string_from_utf8()
	var newline := _receive_buffer.find("\n")
	while newline >= 0:
		var line := _receive_buffer.substr(0, newline)
		_receive_buffer = _receive_buffer.substr(newline + 1)
		if not line.is_empty():
			_parse_response(line)
		newline = _receive_buffer.find("\n")


func _parse_response(line: String) -> void:
	busy = false
	var parser := JSON.new()
	if parser.parse(line) != OK or not parser.data is Dictionary:
		request_failed.emit("Worker returned malformed JSON.")
		return
	var response: Dictionary = parser.data
	if not response.get("ok", false):
		var error: Dictionary = response.get("error", {})
		request_failed.emit(str(error.get("message", "Unknown worker error")))
		return
	response_received.emit(response)
