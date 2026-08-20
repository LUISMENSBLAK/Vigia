"""FWI 1987 según Wang, Anderson y Suddaby (NRCan/CFS, 2015).

La entrada diaria corresponde al mediodía solar/local estándar: temperatura (°C),
humedad relativa (%), viento (km/h) y precipitación acumulada de 24 h (mm).
Los códigos FFMC, DMC y DC requieren el estado válido del día anterior.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from .models import FWIResult, FWIState, FWIWeather

_DMC_DAY_LENGTH = (6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0)
_DC_DAY_LENGTH = (-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6)


def _validate(weather: FWIWeather, previous: FWIState) -> None:
    if not 0.0 <= weather.relative_humidity_pct <= 100.0:
        raise ValueError("relative_humidity_pct debe estar entre 0 y 100")
    if weather.wind_speed_kmh < 0.0 or weather.precipitation_24h_mm < 0.0:
        raise ValueError("viento y precipitación no pueden ser negativos")
    if not 1 <= weather.observed_at.month <= 12:
        raise ValueError("mes no válido")
    if not 0.0 <= previous.ffmc <= 101.0 or previous.dmc < 0.0 or previous.dc < 0.0:
        raise ValueError("estado FWI anterior no válido")


def _ffmc(weather: FWIWeather, previous_ffmc: float) -> float:
    humidity = weather.relative_humidity_pct
    temperature = weather.temperature_c
    wind = weather.wind_speed_kmh
    moisture = 147.2 * (101.0 - previous_ffmc) / (59.5 + previous_ffmc)
    if weather.precipitation_24h_mm > 0.5:
        effective_rain = weather.precipitation_24h_mm - 0.5
        moisture += (
            42.5
            * effective_rain
            * math.exp(-100.0 / (251.0 - moisture))
            * (1.0 - math.exp(-6.93 / effective_rain))
        )
        if moisture > 150.0:
            moisture += 0.0015 * (moisture - 150.0) ** 2 * math.sqrt(effective_rain)
        moisture = min(moisture, 250.0)

    drying_equilibrium = (
        0.942 * humidity**0.679
        + 11.0 * math.exp((humidity - 100.0) / 10.0)
        + 0.18 * (21.1 - temperature) * (1.0 - math.exp(-0.115 * humidity))
    )
    if moisture < drying_equilibrium:
        wetting_equilibrium = (
            0.618 * humidity**0.753
            + 10.0 * math.exp((humidity - 100.0) / 10.0)
            + 0.18 * (21.1 - temperature) * (1.0 - math.exp(-0.115 * humidity))
        )
        if moisture <= wetting_equilibrium:
            coefficient = 0.424 * (1.0 - ((100.0 - humidity) / 100.0) ** 1.7) + 0.0694 * math.sqrt(
                wind
            ) * (1.0 - ((100.0 - humidity) / 100.0) ** 8)
            rate = coefficient * 0.581 * math.exp(0.0365 * temperature)
            moisture = wetting_equilibrium - (wetting_equilibrium - moisture) / 10.0**rate
    elif moisture > drying_equilibrium:
        coefficient = 0.424 * (1.0 - (humidity / 100.0) ** 1.7) + 0.0694 * math.sqrt(wind) * (
            1.0 - (humidity / 100.0) ** 8
        )
        rate = coefficient * 0.581 * math.exp(0.0365 * temperature)
        moisture = drying_equilibrium + (moisture - drying_equilibrium) / 10.0**rate

    return min(101.0, max(0.0, 59.5 * (250.0 - moisture) / (147.2 + moisture)))


def _dmc(weather: FWIWeather, previous_dmc: float) -> float:
    temperature = max(weather.temperature_c, -1.1)
    drying = (
        1.894
        * (temperature + 1.1)
        * (100.0 - weather.relative_humidity_pct)
        * _DMC_DAY_LENGTH[weather.observed_at.month - 1]
        * 0.0001
    )
    pre_rain = previous_dmc
    if weather.precipitation_24h_mm > 1.5:
        effective_rain = 0.92 * weather.precipitation_24h_mm - 1.27
        initial_moisture = 20.0 + 280.0 / math.exp(0.023 * previous_dmc)
        if previous_dmc <= 33.0:
            coefficient = 100.0 / (0.5 + 0.3 * previous_dmc)
        elif previous_dmc <= 65.0:
            coefficient = 14.0 - 1.3 * math.log(previous_dmc)
        else:
            coefficient = 6.2 * math.log(previous_dmc) - 17.2
        rain_moisture = initial_moisture + 1000.0 * effective_rain / (
            48.77 + coefficient * effective_rain
        )
        pre_rain = 43.43 * (5.6348 - math.log(rain_moisture - 20.0))
    return max(1.0, max(0.0, pre_rain) + drying)


def _dc(weather: FWIWeather, previous_dc: float) -> float:
    temperature = max(weather.temperature_c, -2.8)
    potential_evaporation = max(
        0.0,
        (0.36 * (temperature + 2.8) + _DC_DAY_LENGTH[weather.observed_at.month - 1]) / 2.0,
    )
    pre_rain = previous_dc
    if weather.precipitation_24h_mm > 2.8:
        effective_rain = 0.83 * weather.precipitation_24h_mm - 1.27
        initial_moisture = 800.0 * math.exp(-previous_dc / 400.0)
        pre_rain = max(
            0.0,
            previous_dc - 400.0 * math.log(1.0 + 3.937 * effective_rain / initial_moisture),
        )
    return pre_rain + potential_evaporation


def _isi(ffmc: float, wind_speed_kmh: float) -> float:
    moisture = 147.2 * (101.0 - ffmc) / (59.5 + ffmc)
    fuel_factor = 19.115 * math.exp(-0.1386 * moisture) * (1.0 + moisture**5.31 / 49_300_000.0)
    return float(fuel_factor * math.exp(0.05039 * wind_speed_kmh))


def _bui(dmc: float, dc: float) -> float:
    if dmc <= 0.4 * dc:
        value = 0.8 * dc * dmc / (dmc + 0.4 * dc)
    else:
        value = dmc - (1.0 - 0.8 * dc / (dmc + 0.4 * dc)) * (0.92 + (0.0114 * dmc) ** 1.7)
    return max(0.0, value)


def _fwi(isi: float, bui: float) -> float:
    if bui <= 80.0:
        drought_factor = 0.626 * bui**0.809 + 2.0
    else:
        drought_factor = 1000.0 / (25.0 + 108.64 * math.exp(-0.023 * bui))
    initial = 0.1 * isi * drought_factor
    return initial if initial <= 1.0 else math.exp(2.72 * (0.434 * math.log(initial)) ** 0.647)


def calculate_fwi_day(weather: FWIWeather, previous: FWIState) -> FWIResult:
    """Calcula un día; nunca crea implícitamente el estado del día anterior."""
    _validate(weather, previous)
    ffmc = _ffmc(weather, previous.ffmc)
    dmc = _dmc(weather, previous.dmc)
    dc = _dc(weather, previous.dc)
    isi = _isi(ffmc, weather.wind_speed_kmh)
    bui = _bui(dmc, dc)
    return FWIResult(
        observed_at=weather.observed_at,
        ffmc=ffmc,
        dmc=dmc,
        dc=dc,
        isi=isi,
        bui=bui,
        fwi=_fwi(isi, bui),
    )


def calculate_fwi_sequence(
    weather_days: Iterable[FWIWeather], *, initial_state: FWIState
) -> tuple[FWIResult, ...]:
    """Calcula una serie ordenada y rechaza días no crecientes."""
    output: list[FWIResult] = []
    state = initial_state
    previous_time = None
    for weather in weather_days:
        if previous_time is not None and weather.observed_at <= previous_time:
            raise ValueError("La serie FWI debe estar estrictamente ordenada")
        result = calculate_fwi_day(weather, state)
        output.append(result)
        state = result.state
        previous_time = weather.observed_at
    return tuple(output)
