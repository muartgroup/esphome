import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import (
    climate,
    uart,
    sensor,
    time,
)
from esphome.const import (
    CONF_CUSTOM_FAN_MODES,
    CONF_ID,
    CONF_SUPPORTED_FAN_MODES,
    CONF_SUPPORTED_MODES,
    CONF_TIME_ID,
)
from esphome.core import coroutine

CODEOWNERS = ["@Sammy1Am", "@KazWolfe"]

AUTO_LOAD = [
    "climate",
    "select",
    "sensor",
    "binary_sensor",
    "button",
    "text_sensor",
    "time",
]
DEPENDENCIES = [
    "uart",
]

CONF_UART_HEATPUMP = "uart_heatpump"
CONF_UART_THERMOSTAT = "uart_thermostat"

CONF_TEMPERATURE_SOURCES = (
    "temperature_sources"  # This is for specifying additional sources
)

CONF_DISABLE_ACTIVE_MODE = "disable_active_mode"
CONF_ENHANCED_MHK_SUPPORT = (
    "enhanced_mhk"  # EXPERIMENTAL. Will be set to default eventually.
)

DEFAULT_POLLING_INTERVAL = "5s"

mitsubishi_itp_ns = cg.esphome_ns.namespace("mitsubishi_itp")
MitsubishiUART = mitsubishi_itp_ns.class_(
    "MitsubishiUART", cg.PollingComponent, climate.Climate
)
CONF_MITSUBISHI_ITP_ID = "mitsubishi_itp_id"

DEFAULT_CLIMATE_MODES = ["OFF", "HEAT", "DRY", "COOL", "FAN_ONLY", "HEAT_COOL"]
DEFAULT_FAN_MODES = ["AUTO", "QUIET", "LOW", "MEDIUM", "HIGH"]
CUSTOM_FAN_MODES = {"VERYHIGH": mitsubishi_itp_ns.FAN_MODE_VERYHIGH}

validate_custom_fan_modes = cv.enum(CUSTOM_FAN_MODES, upper=True)

CONFIG_SCHEMA = climate.CLIMATE_SCHEMA.extend(
    {
        cv.GenerateID(CONF_ID): cv.declare_id(MitsubishiUART),
        cv.Required(CONF_UART_HEATPUMP): cv.use_id(uart.UARTComponent),
        cv.Optional(CONF_UART_THERMOSTAT): cv.use_id(uart.UARTComponent),
        cv.Optional(CONF_TIME_ID): cv.use_id(time.RealTimeClock),
        cv.Optional(
            CONF_SUPPORTED_MODES, default=DEFAULT_CLIMATE_MODES
        ): cv.ensure_list(climate.validate_climate_mode),
        cv.Optional(
            CONF_SUPPORTED_FAN_MODES, default=DEFAULT_FAN_MODES
        ): cv.ensure_list(climate.validate_climate_fan_mode),
        cv.Optional(CONF_CUSTOM_FAN_MODES, default=["VERYHIGH"]): cv.ensure_list(
            validate_custom_fan_modes
        ),
        cv.Optional(CONF_TEMPERATURE_SOURCES, default=[]): cv.ensure_list(
            cv.use_id(sensor.Sensor)
        ),
        cv.Optional(CONF_DISABLE_ACTIVE_MODE, default=False): cv.boolean,
        cv.Optional(CONF_ENHANCED_MHK_SUPPORT, default=False): cv.boolean,
    }
).extend(cv.polling_component_schema(DEFAULT_POLLING_INTERVAL))


def final_validate(config):
    schema = uart.final_validate_device_schema(
        "mitsubishi_itp",
        uart_bus=CONF_UART_HEATPUMP,
        require_tx=True,
        require_rx=True,
        data_bits=8,
        parity="EVEN",
        stop_bits=1,
    )
    if CONF_UART_THERMOSTAT in config:
        schema = schema.extend(
            uart.final_validate_device_schema(
                "mitsubishi_itp",
                uart_bus=CONF_UART_THERMOSTAT,
                require_tx=True,
                require_rx=True,
                data_bits=8,
                parity="EVEN",
                stop_bits=1,
            )
        )
    schema(config)


FINAL_VALIDATE_SCHEMA = final_validate


@coroutine
async def to_code(config):
    hp_uart_component = await cg.get_variable(config[CONF_UART_HEATPUMP])
    muart_component = cg.new_Pvariable(config[CONF_ID], hp_uart_component)

    await cg.register_component(muart_component, config)
    await climate.register_climate(muart_component, config)

    # If thermostat defined
    if CONF_UART_THERMOSTAT in config:
        # Register thermostat with MUART
        ts_uart_component = await cg.get_variable(config[CONF_UART_THERMOSTAT])
        cg.add(getattr(muart_component, "set_thermostat_uart")(ts_uart_component))

    # If RTC defined
    if CONF_TIME_ID in config:
        rtc_component = await cg.get_variable(config[CONF_TIME_ID])
        cg.add(getattr(muart_component, "set_time_source")(rtc_component))
    elif CONF_UART_THERMOSTAT in config and config.get(CONF_ENHANCED_MHK_SUPPORT):
        raise cv.RequiredFieldInvalid(
            f"{CONF_TIME_ID} is required if {CONF_ENHANCED_MHK_SUPPORT} is set."
        )

    # Traits
    traits = muart_component.config_traits()

    if CONF_SUPPORTED_MODES in config:
        cg.add(traits.set_supported_modes(config[CONF_SUPPORTED_MODES]))

    if CONF_SUPPORTED_FAN_MODES in config:
        cg.add(traits.set_supported_fan_modes(config[CONF_SUPPORTED_FAN_MODES]))

    if CONF_CUSTOM_FAN_MODES in config:
        cg.add(traits.set_supported_custom_fan_modes(config[CONF_CUSTOM_FAN_MODES]))

    # Add additional configured temperature sensors to the select menu
    for ts_id in config[CONF_TEMPERATURE_SOURCES]:
        ts = await cg.get_variable(ts_id)
        cg.add(
            getattr(muart_component, "register_temperature_source")(ts.get_name().str())
        )
        cg.add(
            getattr(ts, "add_on_state_callback")(
                # TODO: Is there anyway to do this without a raw expression?
                cg.RawExpression(
                    f"[](float v){{{getattr(muart_component, 'temperature_source_report')}({ts.get_name()}, v);}}"
                )
            )
        )

    # Debug Settings
    if dam_conf := config.get(CONF_DISABLE_ACTIVE_MODE):
        cg.add(getattr(muart_component, "set_active_mode")(not dam_conf))

    if enhanced_mhk_protocol := config.get(CONF_ENHANCED_MHK_SUPPORT):
        cg.add(
            getattr(muart_component, "set_enhanced_mhk_support")(enhanced_mhk_protocol)
        )
