import logging
import random
import socket

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    LightEntityFeature,
    PLATFORM_SCHEMA,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_EFFECTS = 'effects'
CONF_RANDOM_EFFECTS = 'random_effects'
CONF_USE_RANDOM_EFFECT = 'use_random_effect'
CONF_INCLUDE_ALL_EFFECT_TO_RANDOM = 'include_all_effect_to_random'
CONF_EFFECTS_MAP = 'effects_map'
CONF_EFFECTS_MAP_NAME = 'name'
CONF_EFFECTS_MAP_ID = 'id'
CONF_EFFECTS_MAP_RANDOM = 'random'

EFFECTS = [
    "Конфетти",
    "Огонь",
    "Радуга вертикальная",
    "Радуга горизонтальная",
    "Смена цвета",
    "Безумие",
    "Облака",
    "Лава",
    "Плазма",
    "Радуга",
    "Павлин",
    "Зебра",
    "Лес",
    "Океан",
    "Цвет",
    "Снег",
    "Матрица",
    "Светлячки",
]

EFFECT_MAP_ITEM = vol.Schema({
    vol.Required(CONF_EFFECTS_MAP_NAME): cv.string,
    vol.Required(CONF_EFFECTS_MAP_ID): cv.positive_int,
    vol.Optional(CONF_EFFECTS_MAP_RANDOM, default=False): cv.boolean
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_USE_RANDOM_EFFECT): cv.boolean,
    vol.Optional(CONF_INCLUDE_ALL_EFFECT_TO_RANDOM): cv.boolean,
    vol.Optional(CONF_EFFECTS): cv.ensure_list,
    vol.Optional(CONF_EFFECTS_MAP): vol.All(cv.ensure_list, [EFFECT_MAP_ITEM])
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    add_entities([GyverLamp(config)], True)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    entity = GyverLamp(entry.options, entry.entry_id)
    async_add_entities([entity], True)

    hass.data[DOMAIN][entry.entry_id] = entity


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data[DOMAIN].pop(entry.entry_id)
    return True


class GyverLamp(LightEntity):
    _effects_by_name = dict()
    _effects_by_id = dict()
    _use_random_effect = None
    _random_effect_ids = None

    def __init__(self, config: dict, unique_id=None):
        self._attr_effect_list = config.get(CONF_EFFECTS, EFFECTS)
        self._attr_name = config.get(CONF_NAME, "Gyver Lamp Ex")
        self._attr_should_poll = True
        self._attr_supported_color_modes = {ColorMode.HS}
        self._attr_color_mode = ColorMode.HS
        self._attr_supported_features = LightEntityFeature.EFFECT
        self._attr_unique_id = unique_id

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            manufacturer="@AlexGyver",
            model="GyverLamp",
        )

        self._unavailable_counter = 0

        self.host = config[CONF_HOST]

        self.update_config(config)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5)

    @property
    def address(self) -> tuple:
        return self.host, 8888

    def debug(self, message):
        _LOGGER.debug(f"{self.host} | {message}")

    def update_config(self, config: dict):
        self.host = config[CONF_HOST]
        self._use_random_effect = config.get(CONF_USE_RANDOM_EFFECT, False)

        self._attr_effect_list = config.get(CONF_EFFECTS, EFFECTS)
        effects_map = config.get(CONF_EFFECTS_MAP, {})

        self._effects_by_id = {i: self._attr_effect_list[i] for i in range(0, len(self._attr_effect_list))}

        random_ids = set()
        if config.get(CONF_INCLUDE_ALL_EFFECT_TO_RANDOM, False):
            random_ids.update(list(self._effects_by_id.keys()))

        for effect_info in effects_map:
            effect_id = effect_info.get(CONF_EFFECTS_MAP_ID, 0)
            self._effects_by_id[effect_id] = effect_info.get(CONF_EFFECTS_MAP_NAME, "none")
            if effect_info.get(CONF_EFFECTS_MAP_RANDOM, False):
                random_ids.add(effect_id)

        self._effects_by_name = {}
        for item in self._effects_by_id.items():
            self._effects_by_name[item[1]] = item[0]

        for item in config.get(CONF_RANDOM_EFFECTS, []):
            if item in self._effects_by_name:
                random_ids.add(self._effects_by_name[item])

        self._random_effect_ids = []
        if self._use_random_effect and len(random_ids) > 0:
            self._random_effect_ids.extend(list(random_ids))

        self.debug("map " + str(self._effects_by_name))
        self.debug("_random_effect_ids " + str(self._random_effect_ids))

        self._attr_effect_list = list(self._effects_by_id.values())

        if self.hass:
            self._async_write_ha_state()

    def turn_on(
        self,
        brightness: int = None,
        effect: str = None,
        hs_color: tuple = None,
        **kwargs,
    ):
        payload = []
        if brightness:
            payload.append("BRI%d" % brightness)

        if effect:
            try:
                if effect in self._effects_by_name:
                    payload.append('EFF%d' % self._effects_by_name[effect])
                else:
                    payload.append(effect)
            except ValueError:
                payload.append(effect)
        elif self._use_random_effect and len(self._random_effect_ids) > 0:
            payload.append('EFF%d' % random.choice(self._random_effect_ids))

        if hs_color:
            scale = round(hs_color[0] / 360.0 * 100.0)
            payload.append("SCA%d" % scale)
            speed = hs_color[1] / 100.0 * 255.0
            payload.append("SPD%d" % speed)

        if not self._attr_is_on:
            payload.append("P_ON")

        self.debug(f"SEND {payload}")

        for data in payload:
            self.sock.sendto(data.encode(), self.address)
            resp = self.sock.recv(1024)
            self.debug(f"RESP {resp}")

    def turn_off(self, **kwargs):
        self.sock.sendto(b"P_OFF", self.address)
        resp = self.sock.recv(1024)
        self.debug(f"RESP {resp}")

    def update(self):
        try:
            self.sock.sendto(b"GET", self.address)
            data = self.sock.recv(1024).decode().split(" ")
            self.debug(f"UPDATE {data}")
            # bri eff spd sca pow
            i = int(data[1])
            self._attr_effect = self._effects_by_id.get(i, None)
            self._attr_brightness = int(data[2])
            self._attr_hs_color = (
                float(data[4]) / 100.0 * 360.0,
                float(data[3]) / 255.0 * 100.0,
            )
            self._attr_is_on = data[5] == "1"
            self._attr_available = True
            self._unavailable_counter = 0

        except Exception as e:
            self.debug(f"Can't update: {e}")

            if self._unavailable_counter >= 3:
                self._attr_available = False
                self.debug("Lamp unavailable")
            else:
                self._unavailable_counter = self._unavailable_counter + 1


