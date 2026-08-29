DOMAIN = "innoxel"
DEFAULT_PORT = 5001
SOAP_NS = "urn:innoxel-ch:service:noxnetRemote:1"

# Poll intervals in seconds. Two independent coordinators poll the master:
# - fast (SCAN_INTERVAL): output, dim and Motor G2 blind module state, i.e.
#   switches, lights, covers and output binary sensors - every second, so
#   that button presses elsewhere in the house show up promptly
# - slow (SLOW_SCAN_INTERVAL): weather station, time switches, room climate
#   and the master's hardware diagnostics; the fast poll never waits for
#   these
SCAN_INTERVAL = 1
SLOW_SCAN_INTERVAL = 10
# Diagnostics entities (voltages, CPU temperatures, uptime, serial errors,
# bus supply states) become unavailable when the last successful
# device-status read is older than this, i.e. after three failed slow polls
# in a row. A failing diagnostics read never affects the other entities.
DEVICE_STATUS_STALE_AFTER = 6 * SLOW_SCAN_INTERVAL

CONF_ENABLE_COOLING = "enable_cooling"

# Writable thermostat temperature fields (SOAP setState element names)
RC_FIELD_SET_HEATING = "setTemperatureHeating"
RC_FIELD_SET_COOLING = "setTemperatureCooling"
RC_FIELD_NIGHT_HEATING = "nightSetbackTemperatureHeating"
RC_FIELD_NIGHT_COOLING = "nightSetbackTemperatureCooling"
RC_FIELD_ABSENCE_HEATING = "absenceSetbackTemperatureHeating"
RC_FIELD_ABSENCE_COOLING = "absenceSetbackTemperatureCooling"

RC_WRITABLE_FIELDS = {
    RC_FIELD_SET_HEATING,
    RC_FIELD_SET_COOLING,
    RC_FIELD_NIGHT_HEATING,
    RC_FIELD_NIGHT_COOLING,
    RC_FIELD_ABSENCE_HEATING,
    RC_FIELD_ABSENCE_COOLING,
}
