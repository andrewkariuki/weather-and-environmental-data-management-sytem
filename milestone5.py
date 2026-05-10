from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import TypeVar, Generic, List
from functools import reduce
import threading
import time
import random
import os
import csv
import json
import datetime

class WeatherConfig:
    SYSTEM_NAME    = "JKUAT Weather & Environmental Data System"
    STATION_ID     = "KE-NBI-001"
    LOCATION       = "JKUAT Main Farm, Juja"

    TEMP_HEATWAVE      = 35.0
    TEMP_OPTIMAL_LOW   = 20.0
    TEMP_COLD          = 10.0
    RAINFALL_CROP_NEED = 5.0
    RAINFALL_LOW       = 2.0
    RAINFALL_HEAVY     = 25.0
    WIND_STRONG        = 50.0
    WIND_MODERATE      = 30.0
    HUMIDITY_DISEASE   = 85.0
    HUMIDITY_DRY       = 30.0
    AQI_UNHEALTHY      = 150
    AQI_MODERATE       = 100

    VALID_DAYS = ["Monday", "Tuesday", "Wednesday",
                  "Thursday", "Friday", "Saturday", "Sunday"]
    VALID_DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    DATA_DIR      = "weather_data"
    CSV_FILENAME  = os.path.join(DATA_DIR, "weather_readings.csv")
    JSON_FILENAME = os.path.join(DATA_DIR, "weather_readings.json")
    LOG_FILENAME  = os.path.join(DATA_DIR, "system.log")
    CSV_HEADERS   = ["day", "temperature", "humidity",
                     "rainfall", "wind_speed", "wind_direction", "aqi"]

CFG = WeatherConfig

class WeatherSystemError(Exception):   pass
class ValidationError(WeatherSystemError):  pass
class FileHandlingError(WeatherSystemError): pass
class DataNotFoundError(WeatherSystemError): pass
class EmptyDatasetError(WeatherSystemError): pass

class AlertLevel(Enum):
  
    NORMAL   = 1
    NOTICE   = 2
    WARNING  = 3
    CRITICAL = 4

    def label(self) -> str:
        return self.name

    def symbol(self) -> str:
        return {
            AlertLevel.NORMAL:   "✅",
            AlertLevel.NOTICE:   "ℹ️ ",
            AlertLevel.WARNING:  "⚠️ ",
            AlertLevel.CRITICAL: "🚨",
        }[self]

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented


class SystemStatus(Enum):
    
    IDLE       = auto()
    COLLECTING = auto()
    PROCESSING = auto()
    READY      = auto()
    ERROR      = auto()

    def display(self) -> str:
        return {
            SystemStatus.IDLE:       "🔵 IDLE       — awaiting data",
            SystemStatus.COLLECTING: "🟡 COLLECTING — sensors active",
            SystemStatus.PROCESSING: "🟠 PROCESSING — computing readings",
            SystemStatus.READY:      "🟢 READY      — data available",
            SystemStatus.ERROR:      "🔴 ERROR      — check system log",
        }[self]


class WindDirection(Enum):
    """
    Typed wind direction constants.
    M5 requirement: Enumerations for structured states.
    """
    N  = "N"
    NE = "NE"
    E  = "E"
    SE = "SE"
    S  = "S"
    SW = "SW"
    W  = "W"
    NW = "NW"

    @classmethod
    def from_string(cls, s: str):
        try:
            return cls(s.upper().strip())
        except ValueError:
            raise ValidationError(f"Invalid wind direction: '{s}'")

T = TypeVar("T")

class SensorBuffer(Generic[T]):
    """
    Generic thread-safe buffer for any sensor reading type.
    Works with floats, ints, strings, or any object.
    M5 requirement: Generics for reusability.

    Usage:
        temp_buf  = SensorBuffer[float]()
        alert_buf = SensorBuffer[str]()
    """

    def __init__(self, capacity: int = 100):
        self._buffer: List[T] = []
        self._capacity        = capacity
        self._lock            = threading.Lock()

    def push(self, item: T) -> bool:
        """Add an item. Returns False if buffer is full."""
        with self._lock:
            if len(self._buffer) >= self._capacity:
                return False
            self._buffer.append(item)
            return True

    def pop(self) -> T:
        with self._lock:
            if not self._buffer:
                raise IndexError("SensorBuffer is empty")
            return self._buffer.pop(0)

    def drain(self) -> List[T]:
        with self._lock:
            items = list(self._buffer)
            self._buffer.clear()
            return items

    def size(self) -> int:
        with self._lock:
            return len(self._buffer)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._buffer) == 0

    def peek_all(self) -> List[T]:
        """Return a snapshot without removing items."""
        with self._lock:
            return list(self._buffer)


class ThreadSafeDataset:

    def __init__(self):
        self._readings: list = []
        self._lock = threading.RLock()   # reentrant lock

    def add(self, reading) -> None:
        with self._lock:
            self._readings.append(reading)

    def get_all(self) -> list:
        with self._lock:
            return list(self._readings)

    def count(self) -> int:
        with self._lock:
            return len(self._readings)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._readings) == 0

    def clear(self) -> None:
        with self._lock:
            self._readings.clear()

    def get_by_sensor(self, sensor_id: str) -> list:
        with self._lock:
            return [r for r in self._readings
                    if getattr(r, "sensor_id", None) == sensor_id]
        
class SensorReading:
    """
    A single raw reading from one sensor at one moment.
    Lightweight data object produced by ConcurrentSensorFeed.
    """
    def __init__(self, sensor_id: str, parameter: str,
                 value: float, unit: str, timestamp: str,
                 alert_level: AlertLevel):
        self.sensor_id   = sensor_id
        self.parameter   = parameter
        self.value       = value
        self.unit        = unit
        self.timestamp   = timestamp
        self.alert_level = alert_level

    def __str__(self):
        return (f"  [{self.timestamp}] {self.sensor_id:<12} "
                f"{self.parameter:<14} {self.value:>7.2f} {self.unit:<6} "
                f"{self.alert_level.symbol()} {self.alert_level.label()}")


class SensorThread(threading.Thread):
    
    _RANGES = {
        "TEMP":     (18.0,  42.0,  "°C"),
        "HUMIDITY": (30.0, 100.0,  "%"),
        "RAINFALL": (0.0,   50.0,  "mm"),
        "WIND":     (0.0,   80.0,  "km/h"),
        "AQI":      (20.0, 200.0,  "AQI"),
    }

    def __init__(self, sensor_id: str, parameter: str,
                 buffer: SensorBuffer, readings_per_sensor: int,
                 results: list, lock: threading.Lock):
        super().__init__(name=sensor_id, daemon=True)
        self._sensor_id  = sensor_id
        self._parameter  = parameter
        self._buffer     = buffer
        self._n          = readings_per_sensor
        self._results    = results  
        self._lock       = lock
        self._stop_event = threading.Event()

    def _classify(self, param: str, value: float) -> AlertLevel:
        """Map a raw value to an AlertLevel using lambdas (functional)."""
        classifiers = {
            "TEMP":     lambda v: (AlertLevel.CRITICAL if v >= CFG.TEMP_HEATWAVE
                                   else AlertLevel.WARNING if v <= CFG.TEMP_COLD
                                   else AlertLevel.NOTICE  if v < CFG.TEMP_OPTIMAL_LOW
                                   else AlertLevel.NORMAL),
            "HUMIDITY": lambda v: (AlertLevel.CRITICAL if v > CFG.HUMIDITY_DISEASE
                                   else AlertLevel.WARNING  if v < CFG.HUMIDITY_DRY
                                   else AlertLevel.NORMAL),
            "RAINFALL": lambda v: (AlertLevel.CRITICAL if v > CFG.RAINFALL_HEAVY
                                   else AlertLevel.WARNING  if v == 0
                                   else AlertLevel.NORMAL),
            "WIND":     lambda v: (AlertLevel.CRITICAL if v > CFG.WIND_STRONG
                                   else AlertLevel.WARNING  if v > CFG.WIND_MODERATE
                                   else AlertLevel.NORMAL),
            "AQI":      lambda v: (AlertLevel.CRITICAL if v >= CFG.AQI_UNHEALTHY
                                   else AlertLevel.WARNING  if v >= CFG.AQI_MODERATE
                                   else AlertLevel.NORMAL),
        }
        return classifiers.get(param, lambda v: AlertLevel.NORMAL)(value)

    def run(self):
        lo, hi, unit = self._RANGES[self._parameter]
        for i in range(self._n):
            if self._stop_event.is_set():
                break
            value     = round(random.uniform(lo, hi), 2)
            ts        = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            level     = self._classify(self._parameter, value)
            reading   = SensorReading(self._sensor_id, self._parameter,
                                      value, unit, ts, level)
            self._buffer.push(reading)
            with self._lock:
                self._results.append(reading)
            time.sleep(random.uniform(0.05, 0.15))   # simulate async timing

    def stop(self):
        self._stop_event.set()


class ConcurrentSensorFeed:

    SENSORS = [
        ("SENSOR-TEMP",  "TEMP"),
        ("SENSOR-HUMID", "HUMIDITY"),
        ("SENSOR-RAIN",  "RAINFALL"),
        ("SENSOR-WIND",  "WIND"),
        ("SENSOR-AQI",   "AQI"),
    ]

    def __init__(self, readings_per_sensor: int = 5):
        self._n      = readings_per_sensor
        self._buffer = SensorBuffer[SensorReading](capacity=500)
        self._lock   = threading.Lock()
        self._status = SystemStatus.IDLE
        self._all_results: list = []

    @property
    def status(self) -> SystemStatus:
        return self._status

    def run(self, logger=None) -> list:
        self._status      = SystemStatus.COLLECTING
        self._all_results = []

        print(f"\n  {'='*60}")
        print(f"  CONCURRENT SENSOR SIMULATION             [M5]")
        print(f"  {'='*60}")
        print(f"  Launching {len(self.SENSORS)} sensor threads "
              f"({self._n} readings each)...")
        print(f"  {'─'*60}")

        threads = [
            SensorThread(sid, param, self._buffer,
                         self._n, self._all_results, self._lock)
            for sid, param in self.SENSORS
        ]

        start = time.time()
        for t in threads:
            t.start()
            print(f"  🟡 Thread started : {t.name}")

        print(f"\n  ⏳ All threads running concurrently...")

        for t in threads:
            t.join(timeout=10.0)
            if t.is_alive():
                t.stop()

        elapsed = round(time.time() - start, 3)
        self._status = SystemStatus.PROCESSING

        sorted_results = sorted(self._all_results,
                                key=lambda r: r.timestamp)
        self._status = SystemStatus.READY

        if logger:
            logger.event(f"Concurrent simulation: "
                         f"{len(sorted_results)} readings in {elapsed}s")

        print(f"\n  ✅ All threads completed in {elapsed}s")
        print(f"  Total readings collected : {len(sorted_results)}")
        print(f"  Buffer remaining         : {self._buffer.size()} (drained below)")
        return sorted_results

    def get_status(self) -> str:
        return self._status.display()

class FunctionalAnalytics:
   
    _get_temp  = lambda self, r: r.get_temp()
    _get_rain  = lambda self, r: r.get_rain()
    _get_hum   = lambda self, r: r.get_humidity()
    _get_wind  = lambda self, r: r.get_wind()
    _get_aqi   = lambda self, r: r.get_aqi()
    _is_crit   = lambda self, r: r.get_overall_status() == "CRITICAL"
    _is_dry    = lambda self, r: r.get_rain() == 0
    _is_flood  = lambda self, r: r.get_rain() > CFG.RAINFALL_HEAVY

    def analyse_dataset(self, readings: list) -> dict:

        if not readings:
            return {}

        temps  = list(map(self._get_temp,  readings))
        rains  = list(map(self._get_rain,  readings))
        humids = list(map(self._get_hum,   readings))
        winds  = list(map(self._get_wind,  readings))
        aqis   = list(map(self._get_aqi,   readings))

        total_rain  = reduce(lambda a, b: a + b, rains)
        total_temp  = reduce(lambda a, b: a + b, temps)
        total_humid = reduce(lambda a, b: a + b, humids)

        critical_days = list(filter(self._is_crit,  readings))
        dry_days      = list(filter(self._is_dry,   readings))
        flood_days    = list(filter(self._is_flood, readings))
        heat_days     = list(filter(
            lambda r: r.get_temp() >= CFG.TEMP_HEATWAVE, readings))
        disease_days  = list(filter(
            lambda r: r.get_humidity() > CFG.HUMIDITY_DISEASE, readings))

        n = len(readings)
        return {
            "count"         : n,
            "avg_temp"      : round(total_temp  / n, 1),
            "avg_rain"      : round(total_rain  / n, 1),
            "avg_humidity"  : round(total_humid / n, 1),
            "total_rain"    : round(total_rain, 1),
            "max_temp"      : max(temps),
            "min_temp"      : min(temps),
            "peak_wind"     : max(winds),
            "peak_aqi"      : max(aqis),
            "critical_days" : critical_days,
            "dry_days"      : dry_days,
            "flood_days"    : flood_days,
            "heat_days"     : heat_days,
            "disease_days"  : disease_days,
            "hottest_day"   : sorted(readings,
                                     key=lambda r: r.get_temp(),
                                     reverse=True)[0],
            "wettest_day"   : sorted(readings,
                                     key=lambda r: r.get_rain(),
                                     reverse=True)[0],
        }

    def analyse_sensor_feed(self, sensor_readings: list) -> dict:
        if not sensor_readings:
            return {}

        values = list(map(lambda r: r.value, sensor_readings))

     
        total = reduce(lambda a, b: a + b, values)

        critical = list(filter(
            lambda r: r.alert_level == AlertLevel.CRITICAL, sensor_readings))
        warnings = list(filter(
            lambda r: r.alert_level == AlertLevel.WARNING, sensor_readings))
        normals  = list(filter(
            lambda r: r.alert_level == AlertLevel.NORMAL, sensor_readings))

        sensors = list({r.sensor_id for r in sensor_readings})
        per_sensor = {
            sid: list(filter(lambda r: r.sensor_id == sid, sensor_readings))
            for sid in sensors
        }

        worst_per_sensor = {}
        for sid, group in per_sensor.items():
            worst_per_sensor[sid] = reduce(
                lambda a, b: a if a.alert_level.value >= b.alert_level.value else b,
                group
            )

        return {
            "total_readings" : len(sensor_readings),
            "avg_value"      : round(total / len(values), 2),
            "critical_count" : len(critical),
            "warning_count"  : len(warnings),
            "normal_count"   : len(normals),
            "sensors"        : sensors,
            "per_sensor"     : per_sensor,
            "worst_per_sensor": worst_per_sensor,
        }

    def print_dataset_analysis(self, readings: list):
        result = self.analyse_dataset(readings)
        if not result:
            print("\n  ⚠️  No data to analyse.")
            return

        print(f"\n  {'='*58}")
        print(f"  FUNCTIONAL ANALYTICS REPORT              [M5]")
        print(f"  {'='*58}")
        print(f"  Days analysed    : {result['count']}")
        print(f"\n  📊 COMPUTED VIA map() + reduce()")
        print(f"     Avg Temp      : {result['avg_temp']}°C")
        print(f"     Avg Rainfall  : {result['avg_rain']} mm/day")
        print(f"     Avg Humidity  : {result['avg_humidity']}%")
        print(f"     Total Rain    : {result['total_rain']} mm")
        print(f"     Max Temp      : {result['max_temp']}°C")
        print(f"     Min Temp      : {result['min_temp']}°C")
        print(f"     Peak Wind     : {result['peak_wind']} km/h")
        print(f"     Peak AQI      : {result['peak_aqi']}")

        print(f"\n  🔍 COMPUTED VIA filter() + lambda")
        print(f"     Critical days : {len(result['critical_days'])}", end="")
        if result['critical_days']:
            print(" →", ", ".join(r.get_day() for r in result['critical_days']))
        else:
            print()
        print(f"     Dry days      : {len(result['dry_days'])}", end="")
        if result['dry_days']:
            print(" →", ", ".join(r.get_day() for r in result['dry_days']))
        else:
            print()
        print(f"     Flood days    : {len(result['flood_days'])}", end="")
        if result['flood_days']:
            print(" →", ", ".join(r.get_day() for r in result['flood_days']))
        else:
            print()
        print(f"     Heat days     : {len(result['heat_days'])}", end="")
        if result['heat_days']:
            print(" →", ", ".join(r.get_day() for r in result['heat_days']))
        else:
            print()
        print(f"     Disease risk  : {len(result['disease_days'])}", end="")
        if result['disease_days']:
            print(" →", ", ".join(r.get_day() for r in result['disease_days']))
        else:
            print()

        print(f"\n  📈 COMPUTED VIA sorted() + lambda key")
        print(f"     Hottest day   : {result['hottest_day'].get_day()} "
              f"({result['hottest_day'].get_temp()}°C)")
        print(f"     Wettest day   : {result['wettest_day'].get_day()} "
              f"({result['wettest_day'].get_rain()}mm)")
        print(f"  {'='*58}")

    def print_sensor_analysis(self, sensor_readings: list):
        """Print a formatted sensor feed analytics report."""
        result = self.analyse_sensor_feed(sensor_readings)
        if not result:
            print("\n  ⚠️  No sensor data to analyse.")
            return

        print(f"\n  {'='*58}")
        print(f"  SENSOR FEED ANALYTICS                    [M5]")
        print(f"  {'='*58}")
        print(f"  Total readings   : {result['total_readings']}")
        print(f"  Average value    : {result['avg_value']}")
        print(f"\n  📊 ALERT DISTRIBUTION  (filter + lambda)")
        print(f"     {AlertLevel.CRITICAL.symbol()} CRITICAL : {result['critical_count']}")
        print(f"     {AlertLevel.WARNING.symbol()}  WARNING  : {result['warning_count']}")
        print(f"     {AlertLevel.NORMAL.symbol()} NORMAL   : {result['normal_count']}")

        print(f"\n  🔎 WORST READING PER SENSOR  (reduce)")
        for sid, worst in result['worst_per_sensor'].items():
            print(f"     {sid:<14} → {worst.parameter:<10} "
                  f"{worst.value:>7.2f} {worst.unit:<5} "
                  f"{worst.alert_level.symbol()} {worst.alert_level.label()}")
        print(f"  {'='*58}")


class EnvironmentalReading(ABC):
    def __init__(self, day: str):
        if day not in CFG.VALID_DAYS:
            raise ValidationError(f"Invalid day: '{day}'")
        self._day = day

    def get_day(self) -> str: return self._day

    @abstractmethod
    def get_summary(self) -> str: pass

    @abstractmethod
    def status_report(self): pass

    @abstractmethod
    def get_overall_status(self) -> str: pass

    def __str__(self) -> str: return self.get_summary()


class WeatherReading(EnvironmentalReading):
    def __init__(self, day, temperature, humidity,
                 rainfall, wind_speed, wind_direction, aqi,
                 validate=True):
        super().__init__(day)
        if validate:
            self.__temp     = self.__val_range("Temperature", temperature, -50, 60)
            self.__humidity = self.__val_range("Humidity",    humidity,      0, 100)
            self.__rainfall = self.__val_nonneg("Rainfall",   rainfall)
            self.__wind     = self.__val_nonneg("Wind speed", wind_speed)
            self.__aqi      = self.__val_range("AQI",         aqi,           0, 500)
        else:
            self.__temp = temperature; self.__humidity = humidity
            self.__rainfall = rainfall; self.__wind = wind_speed
            self.__aqi = aqi
        self.__wind_dir      = wind_direction
        self.__heat_index    = self.__compute_heat_index()
        self.__evap          = self.__compute_evapotranspiration()
        self.__dew_point     = self.__compute_dew_point()
        self.__kelvin        = round(self.__temp + 273.15, 2)
        self.__water_deficit = max(0.0, CFG.RAINFALL_CROP_NEED - self.__rainfall)

    def __val_range(self, name, v, lo, hi):
        if not (lo <= v <= hi):
            raise ValidationError(f"{name} {v} out of range [{lo}–{hi}]")
        return v

    def __val_nonneg(self, name, v):
        if v < 0:
            raise ValidationError(f"{name} cannot be negative: {v}")
        return v

    def __compute_heat_index(self):
        return round(self.__temp + (0.33 * (self.__humidity / 100) * 6.105) - 4.0, 1)

    def __compute_evapotranspiration(self):
        return round(0.0023 * (self.__temp + 17.8) * (100 - self.__humidity) ** 0.5, 2)

    def __compute_dew_point(self):
        a, b  = 17.27, 237.7
        gamma = (a * self.__temp) / (b + self.__temp) + (self.__humidity / 100.0)
        return round((b * gamma) / (a - gamma), 2)

    def get_temp(self):          return self.__temp
    def get_humidity(self):      return self.__humidity
    def get_rain(self):          return self.__rainfall
    def get_wind(self):          return self.__wind
    def get_wind_dir(self):      return self.__wind_dir
    def get_aqi(self):           return self.__aqi
    def get_heat_index(self):    return self.__heat_index
    def get_evap(self):          return self.__evap
    def get_dew_point(self):     return self.__dew_point
    def get_kelvin(self):        return self.__kelvin
    def get_water_deficit(self): return self.__water_deficit

    def temperature_status(self):
        t = self.__temp
        if   t >= CFG.TEMP_HEATWAVE:    return "CRITICAL : Heat stress — irrigate immediately"
        elif t >= CFG.TEMP_OPTIMAL_LOW: return "OK       : Temperature within optimal crop range"
        elif t <= CFG.TEMP_COLD:        return "WARNING  : Cold stress — cover seedlings tonight"
        else:                           return "NOTICE   : Below optimal — monitor crops"

    def rainfall_status(self):
        r = self.__rainfall
        if   r == 0:                       return "ALERT    : No rainfall — full irrigation required"
        elif r < CFG.RAINFALL_LOW:         return f"LOW      : {r}mm — partial irrigation needed"
        elif r < CFG.RAINFALL_CROP_NEED:   return f"NOTICE   : {r}mm — below daily crop requirement"
        elif r <= CFG.RAINFALL_HEAVY:      return "OK       : Adequate rainfall for crops today"
        else:                              return "CRITICAL : Excess rainfall — flooding risk"

    def humidity_status(self):
        h = self.__humidity
        if   h > CFG.HUMIDITY_DISEASE: return "WARNING  : High humidity — fungal disease risk"
        elif h < CFG.HUMIDITY_DRY:     return "WARNING  : Low humidity — moisture stress likely"
        else:                          return "OK       : Humidity within acceptable range"

    def wind_status(self):
        w = self.__wind
        if   w > CFG.WIND_STRONG:   return "CRITICAL : Strong winds — crop damage risk"
        elif w > CFG.WIND_MODERATE: return "WARNING  : Moderate winds — lodging risk"
        else:                       return "OK       : Calm wind conditions"

    def air_quality_status(self):
        a = self.__aqi
        if   a >= CFG.AQI_UNHEALTHY: return "CRITICAL : Unhealthy air — limit worker exposure"
        elif a >= CFG.AQI_MODERATE:  return "MODERATE : Elevated AQI — sensitive workers take caution"
        else:                        return "OK       : Air quality acceptable"

    def get_overall_status(self) -> str:
        checks = [self.temperature_status(), self.rainfall_status(),
                  self.humidity_status(),    self.wind_status(),
                  self.air_quality_status()]
        if any("CRITICAL" in c or "ALERT" in c for c in checks): return "CRITICAL"
        if any("WARNING"  in c for c in checks):                  return "WARNING"
        return "NORMAL"

    def get_alert_level(self) -> AlertLevel:
        status = self.get_overall_status()
        return {"CRITICAL": AlertLevel.CRITICAL,
                "WARNING":  AlertLevel.WARNING,
                "NORMAL":   AlertLevel.NORMAL}.get(status, AlertLevel.NORMAL)

    def get_summary(self) -> str:
        deficit = f"Deficit:{self.__water_deficit:.1f}mm" \
                  if self.__water_deficit > 0 else "Water:OK"
        return (f"  {self._day:<12} | Temp:{self.__temp}°C | "
                f"Humid:{self.__humidity}% | Rain:{self.__rainfall}mm | "
                f"Wind:{self.__wind}km/h {self.__wind_dir:<2} | "
                f"AQI:{self.__aqi} | {deficit} | "
                f"{self.get_alert_level().symbol()} {self.get_overall_status()}")

    def status_report(self):
        level = self.get_alert_level()
        print(f"\n  {'='*56}")
        print(f"  WEATHER REPORT — {self._day}  {level.symbol()} {level.label()}")
        print(f"  {'='*56}")
        print(f"   Temperature      : {self.__temp}°C  ({self.__kelvin}K)")
        print(f"   Humidity         : {self.__humidity}%")
        print(f"   Rainfall         : {self.__rainfall} mm")
        print(f"   Wind             : {self.__wind} km/h ({self.__wind_dir})")
        print(f"   Air Quality(AQI) : {self.__aqi}")
        print(f"  {'─'*46}")
        print(f"   Heat Index       : {self.__heat_index}°C  (feels like)")
        print(f"   Evapotransp.     : {self.__evap} mm/day")
        print(f"   Dew Point        : {self.__dew_point}°C")
        print(f"   Water Deficit    : {self.__water_deficit:.1f} mm")
        print(f"  {'─'*46}")
        print(f"   {self.temperature_status()}")
        print(f"   {self.rainfall_status()}")
        print(f"   {self.humidity_status()}")
        print(f"   {self.wind_status()}")
        print(f"   {self.air_quality_status()}")
        print(f"\n   OVERALL          : {level.symbol()} {self.get_overall_status()}")
        if self.__water_deficit > 0:
            print(f"   IRRIGATION GAP   : {self.__water_deficit:.1f}mm needed today")
        print(f"  {'='*56}")


class FarmerAlert(WeatherReading):
    def __init__(self, day, temperature, humidity,
                 rainfall, wind_speed, wind_direction, aqi,
                 validate=True):
        super().__init__(day, temperature, humidity, rainfall,
                         wind_speed, wind_direction, aqi, validate)
        self.__alerts = []
        self.__build_alerts()

    def __build_alerts(self):
        temp = self.get_temp(); rain = self.get_rain()
        hum  = self.get_humidity(); wind = self.get_wind()
        aqi  = self.get_aqi(); evap = self.get_evap()
        deficit = self.get_water_deficit()
        hi = self.get_heat_index(); dew = self.get_dew_point()
        alerts = []

        if rain == 0 and temp >= CFG.TEMP_HEATWAVE:
            alerts.append("🚨 Zero rain + extreme heat — irrigate all fields immediately")
        elif rain == 0:
            alerts.append("💧 No rainfall today — run a full irrigation cycle")
        elif deficit > 0:
            alerts.append(f"💧 Rainfall short — supplement with {deficit:.1f}mm irrigation")
        if evap > 5.0:
            alerts.append(f"☀️  High water loss ({evap}mm/day) — irrigate before 8am")
        elif evap > 3.0:
            alerts.append(f"☀️  Moderate water loss ({evap}mm/day) — check soil moisture at noon")
        if temp >= CFG.TEMP_HEATWAVE:
            alerts.append(f"🔥 Heat stress at {temp}°C (feels like {hi}°C) — avoid midday field work")
            alerts.append("   Mulch around plants to retain moisture")
        elif temp >= 30:
            alerts.append(f"🌡️  Warm day ({temp}°C) — monitor crop water needs through the day")
        if hum > CFG.HUMIDITY_DISEASE:
            alerts.append(f"🍄 High humidity ({hum}%) — fungal disease conditions active")
            alerts.append("   Scout fields for symptoms. Avoid overhead irrigation.")
        elif hum > 75 and temp > 25:
            alerts.append(f"⚠️  Warm + humid ({temp}°C / {hum}%) — monitor for early disease signs")
        if rain > CFG.RAINFALL_HEAVY:
            alerts.append(f"🌊 Heavy rainfall ({rain}mm) — inspect drainage channels now")
            alerts.append("   Hold off on fertilizer — nutrients will leach out")
        if wind > CFG.WIND_STRONG:
            alerts.append(f"💨 Dangerous wind ({wind}km/h) — secure structures and young plants")
        elif wind > CFG.WIND_MODERATE:
            alerts.append(f"💨 Strong wind ({wind}km/h) — monitor tall crops for lodging")
        if temp <= CFG.TEMP_COLD:
            alerts.append(f"🥶 Cold ({temp}°C) — cover young plants with mulch tonight")
        if aqi >= CFG.AQI_UNHEALTHY:
            alerts.append(f"😷 AQI {aqi} — workers must wear masks today")
        elif aqi >= CFG.AQI_MODERATE:
            alerts.append(f"😷 AQI {aqi} — moderate air quality, sensitive workers take care")
        if dew > 20:
            alerts.append(f"💦 Dew point {dew}°C — heavy dew expected, delay morning spraying")
        if not alerts:
            alerts.append("✅ All conditions within safe range — normal operations today")
        self.__alerts = alerts

    def get_alerts(self) -> list: return list(self.__alerts)

    def get_summary(self) -> str:
        return super().get_summary() + f" | {len(self.__alerts)} alert(s)"

    def get_overall_status(self) -> str:
        return super().get_overall_status()

    def status_report(self):
        super().status_report()
        self.print_farmer_alerts()

    def print_farmer_alerts(self):
        print(f"\n  {'='*56}")
        print(f"  FARMER ALERTS — {self._day}")
        print(f"  {'='*56}")
        for alert in self.__alerts:
            print(f"  {alert}")
        print(f"  {'─'*56}")
        print(f"  Overall condition : {self.get_alert_level().symbol()} "
              f"{self.get_overall_status()}")
        print(f"  {'='*56}")


class WeatherDataset:
    def __init__(self):
        self.__readings: list = []

    def add(self, reading):      self.__readings.append(reading)
    def remove_day(self, day):   self.__readings = [r for r in self.__readings if r.get_day() != day]
    def get_for_day(self, day):
        for r in self.__readings:
            if r.get_day() == day: return r
        return None
    def get_all(self) -> list:   return list(self.__readings)
    def count(self) -> int:      return len(self.__readings)
    def is_empty(self) -> bool:  return len(self.__readings) == 0
    def clear(self):             self.__readings = []

    def _recursive_sum(self, lst):
        if not lst: return 0
        return lst[0] + self._recursive_sum(lst[1:])

    def _recursive_max(self, lst):
        if len(lst) == 1: return lst[0]
        rest = self._recursive_max(lst[1:])
        return lst[0] if lst[0] > rest else rest

    def _recursive_min(self, lst):
        if len(lst) == 1: return lst[0]
        rest = self._recursive_min(lst[1:])
        return lst[0] if lst[0] < rest else rest

    def avg_temp(self):
        if self.is_empty(): return 0
        v = [r.get_temp() for r in self.__readings]
        return round(self._recursive_sum(v) / len(v), 1)

    def max_temp(self):
        if self.is_empty(): return 0
        return self._recursive_max([r.get_temp() for r in self.__readings])

    def min_temp(self):
        if self.is_empty(): return 0
        return self._recursive_min([r.get_temp() for r in self.__readings])

    def avg_humidity(self):
        if self.is_empty(): return 0
        v = [r.get_humidity() for r in self.__readings]
        return round(self._recursive_sum(v) / len(v), 1)

    def total_rainfall(self):
        if self.is_empty(): return 0
        return round(self._recursive_sum([r.get_rain() for r in self.__readings]), 1)

    def peak_wind(self):
        if self.is_empty(): return 0
        return self._recursive_max([r.get_wind() for r in self.__readings])

    def peak_aqi(self):
        if self.is_empty(): return 0
        return self._recursive_max([r.get_aqi() for r in self.__readings])

    def sorted_by_temp(self, descending=True):
        return sorted(self.__readings, key=lambda r: r.get_temp(), reverse=descending)

    def sorted_by_rain(self, descending=True):
        return sorted(self.__readings, key=lambda r: r.get_rain(), reverse=descending)

    def critical_days(self):
        return [r for r in self.__readings if r.get_overall_status() == "CRITICAL"]

    def dry_days(self):
        return [r for r in self.__readings if r.get_rain() == 0]

    def flood_days(self):
        return [r for r in self.__readings if r.get_rain() > CFG.RAINFALL_HEAVY]

    def days_above_temp(self, threshold: float):
        return [r for r in self.__readings if r.get_temp() >= threshold]

    def worst_day(self):
        if self.is_empty(): return None
        return max(self.__readings, key=lambda r: r.get_temp())


class WeatherStation:
    def __init__(self, station_id: str, location: str):
        self.station_id = station_id
        self.location   = location
        self.dataset    = WeatherDataset()

    def add_reading(self, reading):      self.dataset.add(reading)
    def has_readings(self) -> bool:      return not self.dataset.is_empty()
    def get_reading_for_day(self, day):  return self.dataset.get_for_day(day)


class WeatherLogger:
    def __init__(self, filepath: str = CFG.LOG_FILENAME):
        self._filepath = filepath
        self._recent: list = []
        self._ensure_dir()

    def _ensure_dir(self):
        try:
            os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        except OSError: pass

    def _timestamp(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write(self, level: str, message: str):
        entry = f"[{self._timestamp()}] [{level:<7}] {message}"
        self._recent.append(entry)
        try:
            with open(self._filepath, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except OSError: pass

    def info(self,    msg): self._write("INFO",    msg)
    def warning(self, msg): self._write("WARNING", msg)
    def error(self,   msg): self._write("ERROR",   msg)
    def event(self,   msg): self._write("EVENT",   msg)

    def get_recent(self, n=20): return self._recent[-n:]

    def view_log_file(self):
        try:
            if not os.path.exists(self._filepath):
                print("\n  ℹ️  No log file found yet.")
                return
            print(f"\n  {'='*60}")
            print(f"  SYSTEM LOG — {self._filepath}")
            print(f"  {'='*60}")
            with open(self._filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if not lines:
                print("  (Log is empty)")
            for line in lines[-50:]:
                print(f"  {line.rstrip()}")
            print(f"  {'='*60}")
        except OSError as e:
            raise FileHandlingError(f"Cannot read log file: {e}") from e

class WeatherFileHandler:
    def __init__(self, logger: WeatherLogger):
        self._logger = logger
        self._ensure_dir()

    def _ensure_dir(self):
        try:
            os.makedirs(CFG.DATA_DIR, exist_ok=True)
        except OSError as e:
            self._logger.error(f"Cannot create data directory: {e}")

    def save_csv(self, dataset, filepath=CFG.CSV_FILENAME):
        if dataset.is_empty():
            raise EmptyDatasetError("No data to save.")
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CFG.CSV_HEADERS)
                writer.writeheader()
                for r in dataset.get_all():
                    writer.writerow({
                        "day": r.get_day(), "temperature": r.get_temp(),
                        "humidity": r.get_humidity(), "rainfall": r.get_rain(),
                        "wind_speed": r.get_wind(), "wind_direction": r.get_wind_dir(),
                        "aqi": r.get_aqi(),
                    })
            self._logger.event(f"CSV saved → {filepath}  ({dataset.count()} records)")
            print(f"\n  ✅ Data saved to: {filepath}  ({dataset.count()} record(s))")
        except OSError as e:
            self._logger.error(f"CSV save failed: {e}")
            raise FileHandlingError(f"Could not save CSV: {e}") from e

    def load_csv(self, filepath=CFG.CSV_FILENAME) -> list:
        if not os.path.exists(filepath):
            raise FileHandlingError(f"File not found: {filepath}")
        records = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):
                    try:
                        records.append(FarmerAlert(
                            row["day"], float(row["temperature"]),
                            float(row["humidity"]), float(row["rainfall"]),
                            float(row["wind_speed"]), row["wind_direction"],
                            int(row["aqi"]), validate=True))
                    except (ValueError, KeyError, WeatherSystemError) as e:
                        self._logger.warning(f"Skipped row {row_num}: {e}")
        except OSError as e:
            raise FileHandlingError(f"Could not read CSV: {e}") from e
        if not records:
            raise FileHandlingError("File contained no valid records.")
        self._logger.event(f"CSV loaded ← {filepath}  ({len(records)} records)")
        return records

    def save_json(self, dataset, station_id, filepath=CFG.JSON_FILENAME):
        if dataset.is_empty():
            raise EmptyDatasetError("No data to save.")
        payload = {
            "system": CFG.SYSTEM_NAME, "version": CFG.VERSION,
            "station_id": station_id,
            "saved_at": datetime.datetime.now().isoformat(),
            "readings": [
                {"day": r.get_day(), "temperature": r.get_temp(),
                 "humidity": r.get_humidity(), "rainfall": r.get_rain(),
                 "wind_speed": r.get_wind(), "wind_direction": r.get_wind_dir(),
                 "aqi": r.get_aqi(), "heat_index": r.get_heat_index(),
                 "evap": r.get_evap(), "dew_point": r.get_dew_point(),
                 "overall_status": r.get_overall_status(),
                 "alert_level": r.get_alert_level().label()}
                for r in dataset.get_all()
            ],
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            self._logger.event(f"JSON saved → {filepath}  ({dataset.count()} records)")
            print(f"\n  ✅ JSON saved to: {filepath}  ({dataset.count()} record(s))")
        except OSError as e:
            raise FileHandlingError(f"Could not save JSON: {e}") from e


WEEKLY_SIMULATION = [
    ["Monday",    32.5, 78.0,  4.2, 18.5, "NE", 55],
    ["Tuesday",   34.1, 72.0,  0.0, 22.0, "N",  60],
    ["Wednesday", 29.8, 85.0, 18.5, 10.0, "SE", 48],
    ["Thursday",  38.2, 60.0,  0.0, 30.5, "NW", 72],
    ["Friday",    31.0, 75.0,  7.3, 14.0, "NE", 50],
    ["Saturday",  27.5, 90.0, 32.1,  8.0, "E",  42],
    ["Sunday",    30.2, 68.0,  2.0, 19.0, "N",  58],
]

def _get_float(prompt, lo, hi):
    while True:
        try:
            v = float(input(f"  {prompt}"))
            if lo <= v <= hi: return v
        except ValueError: pass
        print(f"  ❌ Enter a number between {lo} and {hi}")


def _get_int(prompt, lo, hi):
    while True:
        try:
            v = int(input(f"  {prompt}"))
            if lo <= v <= hi: return v
        except ValueError: pass
        print(f"  ❌ Enter a whole number between {lo} and {hi}")


def collect_one_day(day: str) -> FarmerAlert:
    print(f"\n  --- Weather data for {day} ---")
    temp = _get_float("Temperature °C  [-50 to 60]  : ", -50,   60)
    hum  = _get_float("Humidity %      [0 to 100]   : ",   0,  100)
    rain = _get_float("Rainfall mm     [0 or more]  : ",   0, 9999)
    wind = _get_float("Wind speed km/h [0 or more]  : ",   0, 9999)
    while True:
        wdir = input(f"  Wind direction  {CFG.VALID_DIRS}: ").upper().strip()
        if wdir in CFG.VALID_DIRS: break
        print(f"  ❌ Choose from {CFG.VALID_DIRS}")
    aqi = _get_int("AQI             [0 to 500]   : ", 0, 500)
    return FarmerAlert(day, temp, hum, rain, wind, wdir, aqi, validate=True)

def run_weekly_simulation(station: WeatherStation, logger: WeatherLogger):
    print(f"\n  {'='*60}")
    print(f"  7-DAY SIMULATION — Station: {station.station_id}")
    print(f"  Location: {station.location}")
    print(f"  {'='*60}")
    station.dataset = WeatherDataset()
    for row in WEEKLY_SIMULATION:
        r = FarmerAlert(row[0], row[1], row[2], row[3],
                        row[4], row[5], row[6], validate=False)
        station.add_reading(r)
        print(r.get_summary())
    logger.event(f"7-day simulation run for station {station.station_id}")
    print(f"\n  ✅ {len(WEEKLY_SIMULATION)} days simulated.")


def enter_live_data(station: WeatherStation, logger: WeatherLogger):
    print(f"\n  {'='*54}")
    print(f"  LIVE DATA ENTRY — Station: {station.station_id}")
    print(f"  {'='*54}")
    print("  A. Enter a single day")
    print("  B. Enter readings for the full week")
    print("  C. Back")
    choice = input("\n  Select (A/B/C): ").upper().strip()
    match choice:
        case "A":
            print("\n  Select a day:")
            for i, d in enumerate(CFG.VALID_DAYS, 1):
                print(f"  {i}. {d}")
            idx      = _get_int("Day number (1–7): ", 1, 7)
            selected = CFG.VALID_DAYS[idx - 1]
            existing = station.get_reading_for_day(selected)
            if existing:
                print(f"\n  A reading for {selected} already exists.")
                if input("  Overwrite? (Y/N): ").upper().strip() == "Y":
                    station.dataset.remove_day(selected)
                else:
                    print("  Keeping existing reading.")
                    return
            try:
                reading = collect_one_day(selected)
                station.add_reading(reading)
                logger.event(f"Live data entered for {selected}")
                print(f"\n  ✅ {selected} recorded.")
                reading.status_report()
            except ValidationError as ve:
                logger.error(f"Validation error: {ve}")
                print(f"\n  ❌ Validation error: {ve}")
        case "B":
            station.dataset = WeatherDataset()
            for day in CFG.VALID_DAYS:
                try:
                    reading = collect_one_day(day)
                    station.add_reading(reading)
                    logger.event(f"Live data entered for {day}")
                    print(f"  ✅ {day} saved.\n")
                except ValidationError as ve:
                    logger.error(f"Skipped {day}: {ve}")
                    print(f"  ⚠️  {day} skipped — {ve}\n")
            print("  ✅ Full week recorded.")
            print_weekly_summary(station)
        case "C": print("  ↩  Back.")
        case _:   print("  ❌ Invalid — enter A, B, or C")


def view_summary_menu(station: WeatherStation):
    if not station.has_readings():
        print("\n  ⚠️  No data yet.")
        return
    print(f"\n  {'─'*44}")
    print("  A. Single day — full report + alerts")
    print("  B. Single day — alerts only")
    print("  C. Full week summary")
    print("  D. Back")
    choice = input("\n  Select (A/B/C/D): ").upper().strip()
    match choice:
        case "A": _pick_day(station, mode="full")
        case "B": _pick_day(station, mode="alerts")
        case "C": print_weekly_summary(station)
        case "D": print("  ↩  Back.")
        case _:   print("  ❌ Invalid")


def _pick_day(station: WeatherStation, mode: str):
    available = [r.get_day() for r in station.dataset.get_all()]
    for i, d in enumerate(available, 1):
        print(f"  {i}. {d}")
    idx     = _get_int(f"Select (1–{len(available)}): ", 1, len(available))
    reading = station.dataset.get_for_day(available[idx - 1])
    if mode == "full":
        reading.status_report()
    elif mode == "alerts" and isinstance(reading, FarmerAlert):
        reading.print_farmer_alerts()
    else:
        reading.status_report()


def print_weekly_summary(station: WeatherStation):
    if not station.has_readings():
        print("\n  ⚠️  No data yet.")
        return
    ds         = station.dataset
    total_rain = ds.total_rainfall()
    avg_rain   = round(total_rain / ds.count(), 1)
    print(f"\n  {'='*56}")
    print(f"  WEEKLY SUMMARY — {station.station_id} | {station.location}")
    print(f"  Days recorded : {ds.count()}")
    print(f"  {'='*56}")
    print(f"\n  🌡️  TEMPERATURE")
    print(f"     Average  : {ds.avg_temp()}°C  |  Peak: {ds.max_temp()}°C  |  Low: {ds.min_temp()}°C")
    print(f"\n  💧 HUMIDITY     Average: {ds.avg_humidity()}%")
    print(f"\n  🌧️  RAINFALL    Total: {total_rain}mm  |  Daily avg: {avg_rain}mm  |  "
          f"Dry days: {len(ds.dry_days())}  |  Flood days: {len(ds.flood_days())}")
    print(f"\n  💨 WIND         Peak: {ds.peak_wind()} km/h")
    print(f"\n  🌫️  AQI         Peak: {ds.peak_aqi()}")
    print(f"\n  {'─'*56}  DAILY BREAKDOWN")
    for r in ds.get_all():
        print(r.get_summary())
    critical = ds.critical_days()
    print(f"\n  ⚠️  CRITICAL DAYS : {len(critical)}")
    for r in critical: print(f"     → {r.get_day()}")
    worst = ds.worst_day()
    if worst:
        print(f"\n  🌡️  WORST DAY : {worst.get_day()} — {worst.get_temp()}°C")
    print(f"\n  {'─'*56}  FARMER ALERTS")
    for r in ds.get_all():
        if isinstance(r, FarmerAlert): r.print_farmer_alerts()
    print(f"\n  {'='*56}  WEEKLY CONCLUSION")
    if avg_rain < 3:
        print("  ⚠️  Dry week — drought conditions\n  ➡️  Activate irrigation")
    elif total_rain > CFG.RAINFALL_HEAVY * 3:
        print("  ⚠️  Very wet week\n  ➡️  Inspect drainage, delay fertilizer")
    else:
        print("  ✅ Conditions generally favourable\n  ➡️  Continue normal farm operations")
    print(f"  {'='*56}")


def dataset_analysis_menu(station: WeatherStation):
    if not station.has_readings():
        print("\n  ⚠️  No data yet.")
        return
    ds = station.dataset
    while True:
        print(f"\n  {'─'*44}  DATASET ANALYSIS")
        print("  A. Recursive statistics  B. Sort by temperature")
        print("  C. Sort by rainfall      D. Show critical days")
        print("  E. Days above threshold  F. Back")
        choice = input("\n  Select (A–F): ").upper().strip()
        match choice:
            case "A":
                print(f"\n  Temp  — avg:{ds.avg_temp()}°C  max:{ds.max_temp()}°C  min:{ds.min_temp()}°C")
                print(f"  Rain  — total:{ds.total_rainfall()}mm  avg:{round(ds.total_rainfall()/ds.count(),1)}mm/day")
                print(f"  Humid — avg:{ds.avg_humidity()}%   Wind — peak:{ds.peak_wind()} km/h   AQI — peak:{ds.peak_aqi()}")
            case "B":
                for r in ds.sorted_by_temp(): print(r.get_summary())
            case "C":
                for r in ds.sorted_by_rain(): print(r.get_summary())
            case "D":
                crit = ds.critical_days()
                if crit:
                    for r in crit: print(r.get_summary())
                else:
                    print("\n  ✅ No critical days.")
            case "E":
                t = _get_float("Threshold °C: ", -50, 60)
                res = ds.days_above_temp(t)
                if res:
                    for r in res: print(r.get_summary())
                else:
                    print(f"\n  No days reached {t}°C.")
            case "F": break
            case _:   print("  ❌ Invalid")


def file_persistence_menu(station: WeatherStation,
                           file_handler: WeatherFileHandler,
                           logger: WeatherLogger):
    while True:
        print(f"\n  {'─'*50}  FILE PERSISTENCE  [M4]")
        print("  A. Save CSV  B. Save JSON  C. Load CSV  D. Back")
        choice = input("\n  Select (A–D): ").upper().strip()
        match choice:
            case "A":
                try:    file_handler.save_csv(station.dataset)
                except (EmptyDatasetError, FileHandlingError) as e:
                    print(f"\n  ❌ {e}")
            case "B":
                try:    file_handler.save_json(station.dataset, station.station_id)
                except (EmptyDatasetError, FileHandlingError) as e:
                    print(f"\n  ❌ {e}")
            case "C":
                if input("  Replace current data? (Y/N): ").upper().strip() != "Y":
                    break
                try:
                    records = file_handler.load_csv()
                    station.dataset = WeatherDataset()
                    for r in records: station.add_reading(r)
                    print(f"\n  ✅ Loaded {len(records)} record(s).")
                    print_weekly_summary(station)
                except (FileHandlingError, WeatherSystemError) as e:
                    print(f"\n  ❌ {e}")
            case "D": break
            case _:   print("  ❌ Invalid")


def view_system_log(logger: WeatherLogger):
    try:
        logger.view_log_file()
    except FileHandlingError as e:
        print(f"\n  ❌ Could not read log: {e}")



def concurrent_sensor_menu(feed: ConcurrentSensorFeed,
                            analytics: FunctionalAnalytics,
                            logger: WeatherLogger):
   
    print(f"\n  {'─'*54}")
    print(f"  CONCURRENT SENSOR SIMULATION             [M5]")
    print(f"  {'─'*54}")
    print(f"  System status : {feed.get_status()}")
    print(f"\n  How many readings per sensor? (1–10)")
    n = _get_int("Readings (1–10): ", 1, 10)

    feed_instance = ConcurrentSensorFeed(readings_per_sensor=n)
    readings      = feed_instance.run(logger)

    print(f"\n  {'─'*60}")
    print(f"  ALL SENSOR READINGS  (sorted by timestamp)")
    print(f"  {'─'*60}")
    print(f"  {'Timestamp':<14} {'Sensor':<14} {'Parameter':<14} "
          f"{'Value':>8} {'Unit':<6} {'Level'}")
    print(f"  {'─'*60}")
    for r in readings:
        print(r)

    print(f"\n  {'─'*60}")
    print(f"  ALERT LEVEL SUMMARY  (using AlertLevel enum)")
    print(f"  {'─'*60}")
    for level in [AlertLevel.CRITICAL, AlertLevel.WARNING, AlertLevel.NORMAL]:
        count = sum(1 for r in readings if r.alert_level == level)
        bar   = "█" * count
        print(f"  {level.symbol()} {level.label():<10} {bar} ({count})")

    analytics.print_sensor_analysis(readings)

    print(f"\n  System status : {feed_instance.get_status()}")


def functional_analytics_menu(station: WeatherStation,
                               analytics: FunctionalAnalytics):

    if not station.has_readings():
        print("\n  ⚠️  No data yet — run simulation or enter live data first.")
        return
    analytics.print_dataset_analysis(station.dataset.get_all())

def main():
    logger       = WeatherLogger()
    file_handler = WeatherFileHandler(logger)
    feed         = ConcurrentSensorFeed()
    analytics    = FunctionalAnalytics()

    logger.event("System started — Milestone 5")

    print("=" * 62)
    print(f"  {CFG.SYSTEM_NAME}")
    print(f"  Station  : {CFG.STATION_ID}")
    print(f"  Location : {CFG.LOCATION}")
    print("=" * 62)

    station = WeatherStation(CFG.STATION_ID, CFG.LOCATION)

    while True:
        print("\n  ┌────────────────────────────────────────────────────┐")
        print("  │                    MAIN MENU                       │")
        print("  ├────────────────────────────────────────────────────┤")
        print("  │  1. Run 7-Day Simulation                           │")
        print("  │  2. Enter Live Data                                │")
        print("  │  3. View Summary & Alerts                          │")
        print("  │  4. Dataset Analysis                    [M3]       │")
        print("  │  5. File Persistence (Save / Load)      [M4]       │")
        print("  │  6. View System Log                     [M4]       │")
        print("  │  7. Concurrent Sensor Simulation        [M5]       │")
        print("  │  8. Functional Analytics                [M5]       │")
        print("  │  9. Exit                                           │")
        print("  └────────────────────────────────────────────────────┘")

        choice = input("\n  Select (1–9): ").strip()
        match choice:
            case "1": run_weekly_simulation(station, logger)
            case "2": enter_live_data(station, logger)
            case "3": view_summary_menu(station)
            case "4": dataset_analysis_menu(station)
            case "5": file_persistence_menu(station, file_handler, logger)
            case "6": view_system_log(logger)
            case "7": concurrent_sensor_menu(feed, analytics, logger)
            case "8": functional_analytics_menu(station, analytics)
            case "9":
                logger.event("System shutdown")
                print("\n  Shutting down JKUAT Weather System...")
                print("  ────────────────────────────────────────────────────")
                print("=" * 62)
                break
            case _:
                print("  ❌ Invalid — enter 1 through 9")

if __name__ == "__main__":
    main()