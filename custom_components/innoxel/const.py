DOMAIN = "innoxel"
DEFAULT_PORT = 5001
SCAN_INTERVAL = 1
SOAP_NS = "urn:innoxel-ch:service:noxnetRemote:1"

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
