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
import sys
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

class WeatherConfig:
    SYSTEM_NAME    = "JKUAT Weather & Environmental Data System"
    STATION_ID     = "KE-NBI-001"
    LOCATION       = "JKUAT Main Farm, Juja"
    LATITUDE       = -1.0896     
    LONGITUDE      = 37.0105

    TEMP_HEATWAVE      = 35.0;   WIND_STRONG        = 50.0
    TEMP_OPTIMAL_LOW   = 20.0;   WIND_MODERATE      = 30.0
    TEMP_COLD          = 10.0;   HUMIDITY_DISEASE   = 85.0
    RAINFALL_CROP_NEED = 5.0;    HUMIDITY_DRY       = 30.0
    RAINFALL_LOW       = 2.0;    AQI_UNHEALTHY      = 150
    RAINFALL_HEAVY     = 25.0;   AQI_MODERATE       = 100

    VALID_DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    VALID_DIRS = ["N","NE","E","SE","S","SW","W","NW"]

    DATA_DIR      = "weather_data"
    CSV_FILENAME  = os.path.join(DATA_DIR, "weather_readings.csv")
    POWERBI_CSV   = os.path.join(DATA_DIR, "powerbi_weather_export.csv")
    SENSOR_CSV    = os.path.join(DATA_DIR, "sensor_readings.csv")
    JSON_FILENAME = os.path.join(DATA_DIR, "weather_readings.json")
    LOG_FILENAME  = os.path.join(DATA_DIR, "system.log")
    CSV_HEADERS   = ["day","temperature","humidity",
                     "rainfall","wind_speed","wind_direction","aqi"]

CFG = WeatherConfig
#Exception
class WeatherSystemError(Exception):   pass
class ValidationError(WeatherSystemError):   pass
class FileHandlingError(WeatherSystemError):  pass
class DataNotFoundError(WeatherSystemError):  pass
class EmptyDatasetError(WeatherSystemError):  pass
class APIError(WeatherSystemError):           pass
#Enumaration
class AlertLevel(Enum):
    NORMAL   = 1
    NOTICE   = 2
    WARNING  = 3
    CRITICAL = 4

    def label(self) -> str: return self.name
    def symbol(self) -> str:
        return {AlertLevel.NORMAL:"[OK]", AlertLevel.NOTICE:"[NOTICE]",
                AlertLevel.WARNING:"[WARN]", AlertLevel.CRITICAL:"[CRIT]"}[self]
    def __ge__(self, other):
        if self.__class__ is other.__class__: return self.value >= other.value
        return NotImplemented
    def __gt__(self, other):
        if self.__class__ is other.__class__: return self.value > other.value
        return NotImplemented

class SystemStatus(Enum):
    IDLE       = auto()
    COLLECTING = auto()
    PROCESSING = auto()
    READY      = auto()
    ERROR      = auto()
    def display(self) -> str:
        return {
            SystemStatus.IDLE:       "IDLE       - awaiting data",
            SystemStatus.COLLECTING: "COLLECTING - sensors active",
            SystemStatus.PROCESSING: "PROCESSING - computing readings",
            SystemStatus.READY:      "READY      - data available",
            SystemStatus.ERROR:      "ERROR      - check system log",
        }[self]

class WindDirection(Enum):
    N="N"; NE="NE"; E="E"; SE="SE"; S="S"; SW="SW"; W="W"; NW="NW"
    @classmethod
    def from_string(cls, s: str):
        try: return cls(s.upper().strip())
        except ValueError: raise ValidationError(f"Invalid wind direction: '{s}'")

class Season(Enum): #Seasons used for realistic data collection
    LONG_RAINS  = "Long Rains (Mar-May)"
    DRY_1       = "Dry Season (Jun-Aug)"
    SHORT_RAINS = "Short Rains (Sep-Nov)"
    DRY_2       = "Dry Season (Dec-Feb)"
#Generic thread safe buffer
T = TypeVar("T")

class SensorBuffer(Generic[T]):
    def __init__(self, capacity: int = 2000):
        self._buffer: List[T] = []
        self._capacity        = capacity
        self._lock            = threading.Lock()

    def push(self, item: T) -> bool:
        with self._lock:
            if len(self._buffer) >= self._capacity: return False
            self._buffer.append(item); return True

    def pop(self) -> T:
        with self._lock:
            if not self._buffer: raise IndexError("SensorBuffer is empty")
            return self._buffer.pop(0)

    def drain(self) -> List[T]:
        with self._lock:
            items = list(self._buffer); self._buffer.clear(); return items

    def size(self) -> int:
        with self._lock: return len(self._buffer)

    def is_empty(self) -> bool:
        with self._lock: return len(self._buffer) == 0

    def peek_all(self) -> List[T]:
        with self._lock: return list(self._buffer)

#Logger
class WeatherLogger:
    def __init__(self, filepath: str = CFG.LOG_FILENAME):
        self._filepath     = filepath
        self._recent: list = []
        self._ensure_dir()

    def _ensure_dir(self):
        try: os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        except OSError as e: print(f"  WARNING: Logger could not create directory - {e}")

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
                print("\n  INFO: No log file found yet."); return
            print(f"\n  {'='*60}")
            print(f"  SYSTEM LOG - {self._filepath}")
            print(f"  {'='*60}")
            with open(self._filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if not lines: print("  (Log is empty)")
            for line in lines[-50:]: print(f"  {line.rstrip()}")
            print(f"  {'='*60}")
        except OSError as e: raise FileHandlingError(f"Cannot read log: {e}") from e

#Abstract base
class EnvironmentalReading(ABC):
    def __init__(self, day: str):
        if day not in CFG.VALID_DAYS:
            raise ValueError(f"Invalid day: '{day}'")
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
            self.__temp=temperature; self.__humidity=humidity
            self.__rainfall=rainfall; self.__wind=wind_speed; self.__aqi=aqi

        self.__wind_dir      = wind_direction
        self.__heat_index    = self.__compute_heat_index()
        self.__evap          = self.__compute_evapotranspiration()
        self.__dew_point     = self.__compute_dew_point()
        self.__kelvin        = round(self.__temp + 273.15, 2)
        self.__water_deficit = max(0.0, CFG.RAINFALL_CROP_NEED - self.__rainfall)

    def __val_range(self, name, v, lo, hi):
        if not (lo <= v <= hi):
            raise ValidationError(f"{name} {v} out of range [{lo}-{hi}]")
        return v
    def __val_nonneg(self, name, v):
        if v < 0: raise ValidationError(f"{name} cannot be negative: {v}")
        return v
    def __compute_heat_index(self):
        return round(self.__temp + (0.33*(self.__humidity/100)*6.105) - 4.0, 1)
    def __compute_evapotranspiration(self):
        return round(0.0023*(self.__temp+17.8)*(100-self.__humidity)**0.5, 2)
    def __compute_dew_point(self):
        a, b  = 17.27, 237.7
        gamma = (a*self.__temp)/(b+self.__temp)+(self.__humidity/100.0)
        return round((b*gamma)/(a-gamma), 2)

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
        if self.__temp >= CFG.TEMP_HEATWAVE:     return "CRITICAL : Heat stress - irrigate immediately"
        elif self.__temp >= CFG.TEMP_OPTIMAL_LOW: return "OK       : Temperature within optimal range"
        elif self.__temp <= CFG.TEMP_COLD:        return "WARNING  : Cold stress - cover seedlings"
        else:                                     return "NOTICE   : Below optimal - monitor crops"

    def rainfall_status(self):
        if self.__rainfall == 0:                       return "ALERT    : No rainfall - full irrigation required"
        elif self.__rainfall < CFG.RAINFALL_LOW:       return f"LOW      : {self.__rainfall}mm - partial irrigation"
        elif self.__rainfall < CFG.RAINFALL_CROP_NEED: return f"NOTICE   : {self.__rainfall}mm - below crop requirement"
        elif self.__rainfall <= CFG.RAINFALL_HEAVY:    return "OK       : Adequate rainfall"
        else:                                          return "CRITICAL : Excess rainfall - flooding risk"

    def humidity_status(self):
        if self.__humidity > CFG.HUMIDITY_DISEASE: return "WARNING  : High humidity - fungal disease risk"
        elif self.__humidity < CFG.HUMIDITY_DRY:   return "WARNING  : Low humidity - moisture stress"
        else:                                      return "OK       : Humidity within acceptable range"

    def wind_status(self):
        if self.__wind > CFG.WIND_STRONG:     return "CRITICAL : Strong winds - crop damage risk"
        elif self.__wind > CFG.WIND_MODERATE: return "WARNING  : Moderate winds - lodging risk"
        else:                                 return "OK       : Calm wind conditions"

    def air_quality_status(self):
        if self.__aqi >= CFG.AQI_UNHEALTHY:  return "CRITICAL : Unhealthy air - limit worker exposure"
        elif self.__aqi >= CFG.AQI_MODERATE: return "MODERATE : Elevated AQI - sensitive workers cautious"
        else:                                return "OK       : Air quality acceptable"

    def get_overall_status(self) -> str:
        checks = [self.temperature_status(), self.rainfall_status(),
                  self.humidity_status(),    self.wind_status(),
                  self.air_quality_status()]
        if any("CRITICAL" in c or "ALERT" in c for c in checks): return "CRITICAL"
        if any("WARNING"  in c for c in checks):                  return "WARNING"
        return "NORMAL"

    def get_alert_level(self) -> AlertLevel:
        s = self.get_overall_status()
        if s == "CRITICAL": return AlertLevel.CRITICAL
        if s == "WARNING":  return AlertLevel.WARNING
        return AlertLevel.NORMAL

    def get_summary(self) -> str:
        deficit = f"Deficit:{self.__water_deficit:.1f}mm" \
                  if self.__water_deficit > 0 else "Water:OK"
        return (f"  {self._day:<12} | Temp:{self.__temp}C | "
                f"Humid:{self.__humidity}% | Rain:{self.__rainfall}mm | "
                f"Wind:{self.__wind}km/h {self.__wind_dir:<2} | AQI:{self.__aqi} | "
                f"{deficit} | {self.get_overall_status()}")

    def status_report(self):
        print(f"\n  {'='*56}")
        print(f"  WEATHER REPORT - {self._day}")
        print(f"  {'='*56}")
        print(f"   Temperature      : {self.__temp}C  ({self.__kelvin}K)")
        print(f"   Humidity         : {self.__humidity}%")
        print(f"   Rainfall         : {self.__rainfall} mm")
        print(f"   Wind             : {self.__wind} km/h ({self.__wind_dir})")
        print(f"   Air Quality(AQI) : {self.__aqi}")
        print(f"  {'─'*46}")
        print(f"   Heat Index       : {self.__heat_index}C  (feels like)")
        print(f"   Evapotransp.     : {self.__evap} mm/day")
        print(f"   Dew Point        : {self.__dew_point}C")
        print(f"   Water Deficit    : {self.__water_deficit:.1f} mm")
        print(f"  {'─'*46}")
        print(f"   {self.temperature_status()}")
        print(f"   {self.rainfall_status()}")
        print(f"   {self.humidity_status()}")
        print(f"   {self.wind_status()}")
        print(f"   {self.air_quality_status()}")
        print(f"\n   OVERALL : {self.get_overall_status()}")
        if self.__water_deficit > 0:
            print(f"   IRRIGATION GAP  : {self.__water_deficit:.1f}mm needed today")
        print(f"  {'='*56}")

class FarmerAlert(WeatherReading): #Subclass for raising alerts
    def print_farmer_alerts(self):
        level = self.get_alert_level()
        print(f"\n  {level.symbol()} FARMER ALERT - {self.get_day()} | {level.label()}")
        print(f"  {'─'*50}")
        if self.get_temp() >= CFG.TEMP_HEATWAVE:
            print("  It is dangerously hot. Water your crops now.")
        if self.get_rain() == 0:
            print("  No rain fell today. Switch on irrigation.")
        if self.get_humidity() > CFG.HUMIDITY_DISEASE:
            print("  High humidity - check for blight and fungal disease.")
        if self.get_wind() > CFG.WIND_STRONG:
            print("  Very strong winds. Stake tall crops urgently.")
        if self.get_aqi() >= CFG.AQI_UNHEALTHY:
            print("  Poor air quality. Limit time outdoors for farm workers.")
        if self.get_water_deficit() > 0:
            print(f"  Irrigation gap: {self.get_water_deficit():.1f}mm short of daily crop need.")
        print(f"  {'─'*50}")
# Datasate
class WeatherDataset:
    def __init__(self):
        self._readings: list = []

    def add(self, r):          self._readings.append(r)
    def get_all(self) -> list: return list(self._readings)
    def count(self) -> int:    return len(self._readings)
    def is_empty(self) -> bool:return len(self._readings) == 0
    def clear(self):           self._readings.clear()

    def get_for_day(self, day):
        for r in self._readings:
            if r.get_day() == day: return r
        raise DataNotFoundError(f"No reading for {day}")

    def total_rainfall(self):
        return round(sum(r.get_rain() for r in self._readings), 1)

    # Recursive stats 
    def _rec_sum(self, lst, i=0):
        if i >= len(lst): return 0
        return lst[i] + self._rec_sum(lst, i+1)

    def avg_temp(self):
        vals = [r.get_temp() for r in self._readings]
        return round(self._rec_sum(vals)/len(vals), 1) if vals else 0

    def avg_humidity(self):
        vals = [r.get_humidity() for r in self._readings]
        return round(self._rec_sum(vals)/len(vals), 1) if vals else 0

    def max_temp(self):  return max((r.get_temp()  for r in self._readings), default=0)
    def min_temp(self):  return min((r.get_temp()  for r in self._readings), default=0)
    def peak_wind(self): return max((r.get_wind()  for r in self._readings), default=0)
    def peak_aqi(self):  return max((r.get_aqi()   for r in self._readings), default=0)

    def dry_days(self):     return [r for r in self._readings if r.get_rain() == 0]
    def flood_days(self):   return [r for r in self._readings if r.get_rain() > CFG.RAINFALL_HEAVY]
    def critical_days(self):return [r for r in self._readings if r.get_overall_status()=="CRITICAL"]
    def worst_day(self):
        if not self._readings: return None
        return max(self._readings, key=lambda r: r.get_temp())

    def sorted_by_temp(self):
        return sorted(self._readings, key=lambda r: r.get_temp(), reverse=True)
    def sorted_by_rain(self):
        return sorted(self._readings, key=lambda r: r.get_rain(), reverse=True)
    def days_above_temp(self, t):
        return [r for r in self._readings if r.get_temp() >= t]

#Thread safe datasate
class ThreadSafeDataset:
    def __init__(self):
        self._readings: list = []
        self._lock = threading.RLock()

    def add(self, reading) -> None:
        with self._lock: self._readings.append(reading)

    def get_all(self) -> list:
        with self._lock: return list(self._readings)

    def count(self) -> int:
        with self._lock: return len(self._readings)

    def is_empty(self) -> bool:
        with self._lock: return len(self._readings) == 0

    def clear(self) -> None:
        with self._lock: self._readings.clear()

    def get_by_sensor(self, sensor_id: str) -> list:
        with self._lock:
            return [r for r in self._readings
                    if getattr(r, "sensor_id", None) == sensor_id]
#Sensor reading
class SensorReading:
    def __init__(self, sensor_id, parameter, value, unit, ts, alert_level):
        self.sensor_id   = sensor_id
        self.parameter   = parameter
        self.value       = value
        self.unit        = unit
        self.timestamp   = ts
        self.alert_level = alert_level

    def __str__(self):
        return (f"  [{self.timestamp}] {self.sensor_id:<14} "
                f"{self.parameter:<14} {self.value:>7.2f} {self.unit:<6} "
                f"{self.alert_level.symbol()} {self.alert_level.label()}")
#Sensor thread
class SensorThread(threading.Thread):
    _RANGES = {
        "TEMP":        (18.0,  42.0,  "C"),
        "HUMIDITY":    (30.0, 100.0,  "%"),
        "RAINFALL":    (0.0,   50.0,  "mm"),
        "WIND":        (0.0,   80.0,  "km/h"),
        "AQI":         (20.0, 200.0,  "AQI"),
        "SOIL_MOIST":  (10.0,  80.0,  "%"),
        "UV_INDEX":    (0.0,   12.0,  "UV"),
    }

    def __init__(self, sensor_id, parameter, buffer, readings_per_sensor, results, lock):
        super().__init__(name=sensor_id, daemon=True)
        self._sensor_id  = sensor_id
        self._parameter  = parameter
        self._buffer     = buffer
        self._n          = readings_per_sensor
        self._results    = results
        self._lock       = lock
        self._stop_event = threading.Event()

    def _classify(self, param: str, value: float) -> AlertLevel:
        classifiers = {
            "TEMP":       lambda v: (AlertLevel.CRITICAL if v >= CFG.TEMP_HEATWAVE
                                     else AlertLevel.WARNING if v <= CFG.TEMP_COLD
                                     else AlertLevel.NOTICE  if v < CFG.TEMP_OPTIMAL_LOW
                                     else AlertLevel.NORMAL),
            "HUMIDITY":   lambda v: (AlertLevel.CRITICAL if v > CFG.HUMIDITY_DISEASE
                                     else AlertLevel.WARNING  if v < CFG.HUMIDITY_DRY
                                     else AlertLevel.NORMAL),
            "RAINFALL":   lambda v: (AlertLevel.CRITICAL if v > CFG.RAINFALL_HEAVY
                                     else AlertLevel.WARNING  if v == 0
                                     else AlertLevel.NORMAL),
            "WIND":       lambda v: (AlertLevel.CRITICAL if v > CFG.WIND_STRONG
                                     else AlertLevel.WARNING  if v > CFG.WIND_MODERATE
                                     else AlertLevel.NORMAL),
            "AQI":        lambda v: (AlertLevel.CRITICAL if v >= CFG.AQI_UNHEALTHY
                                     else AlertLevel.WARNING  if v >= CFG.AQI_MODERATE
                                     else AlertLevel.NORMAL),
            "SOIL_MOIST": lambda v: (AlertLevel.CRITICAL if v < 20
                                     else AlertLevel.WARNING  if v < 35
                                     else AlertLevel.NORMAL),
            "UV_INDEX":   lambda v: (AlertLevel.CRITICAL if v >= 8
                                     else AlertLevel.WARNING  if v >= 6
                                     else AlertLevel.NORMAL),
        }
        return classifiers.get(param, lambda v: AlertLevel.NORMAL)(value)

    def run(self):
        lo, hi, unit = self._RANGES[self._parameter]
        for i in range(self._n):
            if self._stop_event.is_set(): break
            value   = round(random.uniform(lo, hi), 2)
            ts      = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            level   = self._classify(self._parameter, value)
            reading = SensorReading(self._sensor_id, self._parameter, value, unit, ts, level)
            self._buffer.push(reading)
            with self._lock: self._results.append(reading)
            time.sleep(random.uniform(0.001, 0.005))

    def stop(self): self._stop_event.set()
#concurrent sensor field 
class ConcurrentSensorFeed:
    SENSORS = [
        ("SENSOR-TEMP",      "TEMP"),
        ("SENSOR-HUMID",     "HUMIDITY"),
        ("SENSOR-RAIN",      "RAINFALL"),
        ("SENSOR-WIND",      "WIND"),
        ("SENSOR-AQI",       "AQI"),
        ("SENSOR-SOIL",      "SOIL_MOIST"),
        ("SENSOR-UV",        "UV_INDEX"),
    ]

    def __init__(self, readings_per_sensor: int = 200, num_sensors: int = 7):
        self._n           = readings_per_sensor
        self._num_sensors = min(num_sensors, len(self.SENSORS))
        self._buffer      = SensorBuffer[SensorReading](capacity=10000)
        self._lock        = threading.Lock()
        self._status      = SystemStatus.IDLE
        self._all_results: list = []

    @property
    def status(self): return self._status

    def run(self, logger=None) -> list:
        self._status      = SystemStatus.COLLECTING
        self._all_results = []
        active_sensors    = self.SENSORS[:self._num_sensors]
        total = len(active_sensors) * self._n

        print(f"\n  {'='*62}")
        print(f"  CONCURRENT SENSOR SIMULATION                      ")
        print(f"  {'='*62}")
        print(f"  Sensors         : {len(active_sensors)}")
        print(f"  Readings/sensor : {self._n}")
        print(f"  Total target    : {total} rows")
        print(f"  {'─'*62}")

        threads = [
            SensorThread(sid, param, self._buffer,
                         self._n, self._all_results, self._lock)
            for sid, param in active_sensors
        ]

        start = time.time()
        for t in threads:
            t.start()
            print(f"  Thread started : {t.name}")

        print(f"\n  All {len(threads)} threads running concurrently...")

        for t in threads:
            t.join(timeout=30.0)
            if t.is_alive(): t.stop()

        elapsed = round(time.time() - start, 3)
        self._status = SystemStatus.PROCESSING

        sorted_results = sorted(self._all_results, key=lambda r: r.timestamp)
        self._status   = SystemStatus.READY

        if logger:
            logger.event(f"Concurrent simulation: {len(sorted_results)} readings in {elapsed}s")

        print(f"\n  All threads completed in {elapsed}s")
        print(f"  Total readings collected : {len(sorted_results)}")
        return sorted_results

    def get_status(self) -> str: return self._status.display()

#Sensor CSV exporter....saves  concurrent sensor readings
class SensorExporter:
    HEADERS = ["timestamp","sensor_id","parameter","value","unit","alert_level"]

    @classmethod
    def export(cls, readings: list, filepath: str = CFG.SENSOR_CSV,
               logger: "WeatherLogger" = None) -> str:
        if not readings:
            raise EmptyDatasetError("No sensor readings to export.")
        os.makedirs(CFG.DATA_DIR, exist_ok=True)

        def _try_write(path: str) -> bool:
            try:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=cls.HEADERS)
                    writer.writeheader()
                    for r in readings:
                        writer.writerow({
                            "timestamp"  : r.timestamp,
                            "sensor_id"  : r.sensor_id,
                            "parameter"  : r.parameter,
                            "value"      : r.value,
                            "unit"       : r.unit,
                            "alert_level": r.alert_level.label(),
                        })
                return True
            except PermissionError:
                return False

        if not _try_write(filepath):
            ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(CFG.DATA_DIR, f"sensor_readings_{ts}.csv")
            print(f"\n  WARNING: Default sensor file locked. Saving to: {filepath}")
            _try_write(filepath)

        size_kb = round(os.path.getsize(filepath) / 1024, 1)
        msg = f"Sensor CSV saved -> {filepath}  ({len(readings)} readings | {size_kb} KB)"
        print(f"\n  {msg}")
        if logger: logger.event(msg)
        return filepath
    
#API for collecting real weather data
class OpenMeteoAPI:

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    @staticmethod    # to map Open-Meteo wind degrees to a compass
    def _degrees_to_compass(deg: float) -> str:
        dirs = ["N","NE","E","SE","S","SW","W","NW"]
        idx  = int((deg + 22.5) / 45) % 8
        return dirs[idx]

    @staticmethod    # Estimate AQI from environmental 
    def _estimate_aqi(wind_speed: float, rainfall: float, month: int) -> int:
       
        base = 45
        if rainfall == 0 and wind_speed > 20:
            base += int(wind_speed * 1.2)
        elif rainfall == 0:
            base += 15
        if rainfall > 10:
            base -= 15
        if month in (6, 7, 8, 12, 1, 2):
            base += 10
        return max(20, min(180, base))

    @classmethod
    def fetch(cls, target_rows: int = 1000, logger: "WeatherLogger" = None) -> list:
        params = (
            f"latitude={CFG.LATITUDE}&longitude={CFG.LONGITUDE}"
            f"&daily=temperature_2m_max,temperature_2m_min,"
            f"precipitation_sum,windspeed_10m_max,"
            f"winddirection_10m_dominant,"
            f"relative_humidity_2m_max,uv_index_max"
            f"&past_days=92&forecast_days=1"
            f"&timezone=Africa%2FNairobi"
        )
        url = f"{cls.BASE_URL}?{params}"

        print(f"\n  Connecting to Open-Meteo API (free tier)...")
        print(f"  Fetching last 92 days of real Juja weather data...")

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "JKUAT-Weather-System/5.2"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = ""
            try: body = e.read().decode("utf-8")[:200]
            except Exception: pass
            raise APIError(
                f"HTTP {e.code} from Open-Meteo: {e.reason}. {body}"
            ) from e
        except urllib.error.URLError as e:
            raise APIError(
                f"Cannot reach Open-Meteo API: {e}\n"
                f"  Check your internet connection and try again."
            ) from e
        except Exception as e:
            raise APIError(f"Unexpected network error: {e}") from e

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise APIError(f"Invalid JSON from API: {e}") from e

        if "daily" not in data:
            raise APIError(f"Unexpected API response - 'daily' key missing. "
                           f"Response: {raw[:200]}")

        daily    = data["daily"]
        dates    = daily.get("time", [])
        t_max    = daily.get("temperature_2m_max",         [])
        t_min    = daily.get("temperature_2m_min",         [])
        precip   = daily.get("precipitation_sum",          [])
        wind_spd = daily.get("windspeed_10m_max",          [])
        wind_dir = daily.get("winddirection_10m_dominant", [])
        humidity = daily.get("relative_humidity_2m_max",   [])
        uv       = daily.get("uv_index_max",               [])

        season_map = {
            1:"Dry (Dec-Feb)",  2:"Dry (Dec-Feb)",  3:"Long Rains",
            4:"Long Rains",     5:"Long Rains",     6:"Dry (Jun-Aug)",
            7:"Dry (Jun-Aug)",  8:"Dry (Jun-Aug)",  9:"Short Rains",
            10:"Short Rains",   11:"Short Rains",   12:"Dry (Dec-Feb)"
        }

        real_rows = []
        for i, date_str in enumerate(dates):
            try:
                date   = datetime.date.fromisoformat(date_str)
                month  = date.month
                tmax   = t_max[i]   if i < len(t_max)    and t_max[i]   is not None else 25.0
                tmin   = t_min[i]   if i < len(t_min)    and t_min[i]   is not None else 18.0
                temp   = round((tmax + tmin) / 2, 1)
                rain   = round(float(precip[i]   if i < len(precip)   and precip[i]  is not None else 0.0), 1)
                hum    = round(float(humidity[i] if i < len(humidity) and humidity[i] is not None else 65.0), 1)
                hum    = max(0.0, min(100.0, hum))
                wspd   = round(float(wind_spd[i] if i < len(wind_spd) and wind_spd[i] is not None else 10.0), 1)
                wdeg   = float(wind_dir[i] if i < len(wind_dir) and wind_dir[i] is not None else 0.0)
                wdir   = cls._degrees_to_compass(wdeg)
                uv_val = float(uv[i] if i < len(uv) and uv[i] is not None else 5.0)
                aqi    = cls._estimate_aqi(wspd, rain, month)
                temp   = max(-50.0, min(60.0, temp))

                real_rows.append({
                    "date": date_str, "day_name": date.strftime("%A"),
                    "month": date.strftime("%B"), "month_num": month,
                    "year": date.year, "season": season_map[month], "hour": 12,
                    "temperature": temp, "humidity": hum, "rainfall": rain,
                    "wind_speed": wspd, "wind_direction": wdir, "aqi": aqi,
                    "uv_index": round(uv_val, 1),
                    "latitude": CFG.LATITUDE, "longitude": CFG.LONGITUDE,
                    "station_id": CFG.STATION_ID, "location": CFG.LOCATION,
                    "source": "Open-Meteo API (real data)",
                })
            except (IndexError, TypeError, ValueError):
                continue

        if not real_rows:
            raise APIError("API returned data but no valid rows could be parsed.")

        real_count = len(real_rows)
        print(f"\n  Received {real_count} real daily readings from Open-Meteo.")

        # Pad to target_rows with realistic generated data if needed
        rows = list(real_rows)
        if real_count < target_rows:
            pad_needed = target_rows - real_count
            print(f"  Padding with {pad_needed} generated rows to reach {target_rows} total...")
            pad_rows = RealisticDataGenerator.generate(pad_needed)
            # Mark padded rows clearly
            for r in pad_rows:
                r["source"] = "Generated (padded to 1000)"
            rows.extend(pad_rows)

        msg = (f"Open-Meteo: {real_count} real rows + "
               f"{len(rows)-real_count} generated = {len(rows)} total rows for Juja")
        print(f"\n  {msg}")
        if logger: logger.event(msg)
        return rows

    @classmethod
    def to_weather_readings(cls, rows: list) -> list: #Convert API row dicts to FarmerAlert objects
        readings  = []
        valid_days = CFG.VALID_DAYS
        for row in rows:
            try: #To ensure values are in range
                day  = row["day_name"] if row["day_name"] in valid_days else "Monday"
                temp = max(-50.0, min(60.0, float(row["temperature"])))
                hum  = max(0.0,   min(100.0, float(row["humidity"])))
                rain = max(0.0,   float(row["rainfall"]))
                wind = max(0.0,   float(row["wind_speed"]))
                aqi  = max(0,     min(500, int(row["aqi"])))

                r = FarmerAlert(
                    day            = day,
                    temperature    = temp,
                    humidity       = hum,
                    rainfall       = rain,
                    wind_speed     = wind,
                    wind_direction = row["wind_direction"],
                    aqi            = aqi,
                    validate       = True,
                )
                readings.append(r)
            except (ValidationError, ValueError):
                continue
        return readings
    
#datasate generator to use when API is unavialble
class RealisticDataGenerator:
    _MONTHS = {
        1:  {"temp":(18,30), "rain_prob":0.15, "rain_amt":(0,8),  "hum":(45,70), "wind":(5,25), "aqi":(40,90),  "season":"Dry (Jan-Feb)"},
        2:  {"temp":(19,31), "rain_prob":0.18, "rain_amt":(0,10), "hum":(45,72), "wind":(5,28), "aqi":(40,95),  "season":"Dry (Jan-Feb)"},
        3:  {"temp":(18,30), "rain_prob":0.55, "rain_amt":(2,40), "hum":(60,90), "wind":(3,18), "aqi":(30,70),  "season":"Long Rains"},
        4:  {"temp":(17,28), "rain_prob":0.70, "rain_amt":(5,55), "hum":(65,95), "wind":(2,15), "aqi":(25,65),  "season":"Long Rains"},
        5:  {"temp":(17,27), "rain_prob":0.65, "rain_amt":(3,45), "hum":(65,92), "wind":(3,18), "aqi":(28,68),  "season":"Long Rains"},
        6:  {"temp":(15,25), "rain_prob":0.20, "rain_amt":(0,12), "hum":(50,75), "wind":(8,35), "aqi":(35,85),  "season":"Dry (Jun-Aug)"},
        7:  {"temp":(14,24), "rain_prob":0.15, "rain_amt":(0,8),  "hum":(48,72), "wind":(10,40),"aqi":(38,90),  "season":"Dry (Jun-Aug)"},
        8:  {"temp":(15,25), "rain_prob":0.18, "rain_amt":(0,10), "hum":(48,73), "wind":(8,38), "aqi":(36,88),  "season":"Dry (Jun-Aug)"},
        9:  {"temp":(17,28), "rain_prob":0.40, "rain_amt":(1,28), "hum":(55,82), "wind":(5,25), "aqi":(30,75),  "season":"Short Rains"},
        10: {"temp":(17,28), "rain_prob":0.60, "rain_amt":(3,45), "hum":(60,90), "wind":(3,20), "aqi":(28,68),  "season":"Short Rains"},
        11: {"temp":(17,27), "rain_prob":0.55, "rain_amt":(2,40), "hum":(60,88), "wind":(3,20), "aqi":(28,65),  "season":"Short Rains"},
        12: {"temp":(18,29), "rain_prob":0.20, "rain_amt":(0,15), "hum":(48,72), "wind":(5,28), "aqi":(38,88),  "season":"Dry (Dec-Feb)"},
    }
    WIND_DIRS = ["N","NE","E","SE","S","SW","W","NW"]

    @classmethod
    def generate(cls, n: int = 1000) -> list:
        rows  = []
        rng   = random.Random(42)
        start = datetime.date(2024, 1, 1)
        print(f"\n  Generating {n} realistic weather readings (offline fallback)...")
        for i in range(n):
            date     = start + datetime.timedelta(days=i)
            month    = date.month
            p        = cls._MONTHS[month]
            day_name = date.strftime("%A")
            t_lo, t_hi = p["temp"]
            temp     = round(rng.uniform(t_lo, t_hi) + rng.gauss(0, 0.8), 1)
            temp     = max(t_lo - 2, min(t_hi + 3, temp))
            rainfall = round(rng.uniform(*p["rain_amt"]), 1) if rng.random() < p["rain_prob"] else 0.0
            humidity = round(rng.uniform(*p["hum"]), 1)
            if rainfall > 10:
                humidity = min(98, humidity + rng.uniform(5, 15))
                humidity = round(humidity, 1)
            wind_speed = round(rng.uniform(*p["wind"]), 1)
            wind_dir   = rng.choice(cls.WIND_DIRS)
            aqi        = int(rng.uniform(*p["aqi"]))
            if rainfall == 0 and wind_speed > 25:
                aqi = min(200, aqi + rng.randint(10, 40))
            rows.append({
                "date": date.isoformat(), "day_name": day_name,
                "month": date.strftime("%B"), "month_num": month,
                "year": date.year, "season": p["season"], "hour": 12,
                "temperature": temp, "humidity": humidity, "rainfall": rainfall,
                "wind_speed": wind_speed, "wind_direction": wind_dir, "aqi": aqi,
                "latitude": CFG.LATITUDE, "longitude": CFG.LONGITUDE,
                "station_id": CFG.STATION_ID, "location": CFG.LOCATION,
                "source": "Generated (offline fallback)",
            })
        print(f"  {len(rows)} rows generated.")
        return rows

    @classmethod
    def to_weather_readings(cls, rows: list) -> list:
        readings = []
        for row in rows:
            try:
                day = row["day_name"] if row["day_name"] in CFG.VALID_DAYS else "Monday"
                r   = FarmerAlert(
                    day=day, temperature=row["temperature"],
                    humidity=row["humidity"], rainfall=row["rainfall"],
                    wind_speed=row["wind_speed"], wind_direction=row["wind_direction"],
                    aqi=row["aqi"], validate=True,
                )
                readings.append(r)
            except (ValidationError, ValueError):
                pass
        return readings

#power BI csv expoter
class PowerBIExporter:
    POWERBI_HEADERS = [
        "date","day_name","month","month_num","year","season","hour",
        "temperature","humidity","rainfall","wind_speed","wind_direction",
        "aqi","heat_index","evapotranspiration","dew_point","water_deficit",
        "alert_level","overall_status",
        "latitude","longitude","station_id","location","source"
    ]

    @classmethod
    def _compute_derived(cls, row: dict) -> dict:
        t  = row["temperature"]
        h  = row["humidity"]
        r  = row["rainfall"]
        hi = round(t + (0.33*(h/100)*6.105) - 4.0, 1)
        et = round(0.0023*(t+17.8)*(100-h)**0.5, 2)
        a, b = 17.27, 237.7
        g    = (a*t)/(b+t)+(h/100.0)
        dp   = round((b*g)/(a-g), 2)
        wd   = round(max(0.0, CFG.RAINFALL_CROP_NEED - r), 1)
        checks = []
        if t >= CFG.TEMP_HEATWAVE or r > CFG.RAINFALL_HEAVY: checks.append("CRITICAL")
        elif t < CFG.TEMP_OPTIMAL_LOW or h > CFG.HUMIDITY_DISEASE: checks.append("WARNING")
        if row["aqi"] >= CFG.AQI_UNHEALTHY: checks.append("CRITICAL")
        elif row["aqi"] >= CFG.AQI_MODERATE: checks.append("WARNING")
        if "CRITICAL" in checks: alert = status = "CRITICAL"
        elif "WARNING" in checks: alert = status = "WARNING"
        else:                     alert = status = "NORMAL"
        source = row.get("source", "System")
        return {**row, "heat_index":hi, "evapotranspiration":et,
                "dew_point":dp, "water_deficit":wd,
                "alert_level":alert, "overall_status":status, "source":source}

    @classmethod
    def export(cls, rows: list, filepath: str = CFG.POWERBI_CSV,
               logger: "WeatherLogger" = None) -> str:
        os.makedirs(CFG.DATA_DIR, exist_ok=True)
        enriched = [cls._compute_derived(row) for row in rows]

        def _try_write(path: str) -> bool:
            try:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=cls.POWERBI_HEADERS,
                                            extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(enriched)
                return True
            except PermissionError:
                return False

        if not _try_write(filepath):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            fallback  = os.path.join(CFG.DATA_DIR, f"powerbi_weather_export_{timestamp}.csv")
            print(f"\n  WARNING: '{filepath}' is open in another program.")
            print(f"  Saving to: {fallback}")
            if logger: logger.warning(f"Default file locked - using fallback: {fallback}")
            try:
                _try_write(fallback)
                filepath = fallback
            except OSError as e:
                if logger: logger.error(f"PowerBI export failed: {e}")
                raise FileHandlingError(f"Could not save Power BI CSV: {e}") from e

        size_kb = round(os.path.getsize(filepath) / 1024, 1)
        source_label = enriched[0].get("source", "System") if enriched else "System"
        msg = (f"Power BI CSV saved -> {filepath}  "
               f"({len(rows)} rows | {size_kb} KB | {source_label})")
        print(f"\n  {msg}")
        if logger: logger.event(msg)
        return filepath

#File hanling
class WeatherFileHandler:
    def __init__(self, logger: WeatherLogger):
        self._logger = logger
        os.makedirs(CFG.DATA_DIR, exist_ok=True)

    def save_csv(self, dataset: WeatherDataset, filepath=CFG.CSV_FILENAME):
        if dataset.is_empty():
            raise EmptyDatasetError("No data to save.")
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CFG.CSV_HEADERS)
                writer.writeheader()
                for r in dataset.get_all():
                    writer.writerow({
                        "day":r.get_day(),"temperature":r.get_temp(),
                        "humidity":r.get_humidity(),"rainfall":r.get_rain(),
                        "wind_speed":r.get_wind(),"wind_direction":r.get_wind_dir(),
                        "aqi":r.get_aqi()
                    })
            self._logger.event(f"CSV saved -> {filepath}  ({dataset.count()} records)")
            print(f"\n  Data saved to: {filepath}  ({dataset.count()} record(s))")
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
                            day=row["day"], temperature=float(row["temperature"]),
                            humidity=float(row["humidity"]), rainfall=float(row["rainfall"]),
                            wind_speed=float(row["wind_speed"]),
                            wind_direction=row["wind_direction"],
                            aqi=int(row["aqi"]), validate=True))
                    except (ValueError, KeyError, WeatherSystemError) as e:
                        self._logger.warning(f"Skipped row {row_num}: {e}")
        except OSError as e:
            raise FileHandlingError(f"Could not read CSV: {e}") from e
        if not records:
            raise FileHandlingError("No valid records in file.")
        self._logger.event(f"CSV loaded <- {filepath}  ({len(records)} records)")
        return records

    def save_json(self, dataset, station_id: str,
                  filepath: str = CFG.JSON_FILENAME):
        if dataset.is_empty():
            raise EmptyDatasetError("No data to save.")
        payload = {
            "system"      : CFG.SYSTEM_NAME,
            "station_id"  : station_id,
            "saved_at"    : datetime.datetime.now().isoformat(),
            "record_count": dataset.count(),
            "readings": [
                {
                    "day"               : r.get_day(),
                    "temperature"       : r.get_temp(),
                    "humidity"          : r.get_humidity(),
                    "rainfall"          : r.get_rain(),
                    "wind_speed"        : r.get_wind(),
                    "wind_direction"    : r.get_wind_dir(),
                    "aqi"               : r.get_aqi(),
                    "heat_index"        : r.get_heat_index(),
                    "evapotranspiration": r.get_evap(),
                    "dew_point"         : r.get_dew_point(),
                    "water_deficit"     : r.get_water_deficit(),
                    "overall_status"    : r.get_overall_status(),
                }
                for r in dataset.get_all()
            ]
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            self._logger.event(f"JSON saved -> {filepath}  ({dataset.count()} records)")
            print(f"\n  Data saved to: {filepath}  ({dataset.count()} record(s))")
        except OSError as e:
            self._logger.error(f"JSON save failed: {e}")
            raise FileHandlingError(f"Could not save JSON: {e}") from e

#Fanctional analytics
class FunctionalAnalytics:
    _get_temp = lambda self, r: r.get_temp()
    _get_rain = lambda self, r: r.get_rain()
    _get_hum  = lambda self, r: r.get_humidity()
    _get_wind = lambda self, r: r.get_wind()
    _get_aqi  = lambda self, r: r.get_aqi()
    _is_crit  = lambda self, r: r.get_overall_status() == "CRITICAL"
    _is_dry   = lambda self, r: r.get_rain() == 0
    _is_flood = lambda self, r: r.get_rain() > CFG.RAINFALL_HEAVY

    def analyse_dataset(self, readings: list) -> dict:
        if not readings: return {}
        temps  = list(map(self._get_temp,  readings))
        rains  = list(map(self._get_rain,  readings))
        humids = list(map(self._get_hum,   readings))
        winds  = list(map(self._get_wind,  readings))
        aqis   = list(map(self._get_aqi,   readings))
        n      = len(readings)
        total_rain  = reduce(lambda a, b: a+b, rains)
        total_temp  = reduce(lambda a, b: a+b, temps)
        total_humid = reduce(lambda a, b: a+b, humids)
        return {
            "count"        : n,
            "avg_temp"     : round(total_temp/n, 1),
            "avg_rain"     : round(total_rain/n, 1),
            "avg_humidity" : round(total_humid/n, 1),
            "total_rain"   : round(total_rain, 1),
            "max_temp"     : max(temps), "min_temp": min(temps),
            "peak_wind"    : max(winds), "peak_aqi": max(aqis),
            "critical_days": list(filter(self._is_crit,  readings)),
            "dry_days"     : list(filter(self._is_dry,   readings)),
            "flood_days"   : list(filter(self._is_flood, readings)),
            "heat_days"    : list(filter(lambda r: r.get_temp()>=CFG.TEMP_HEATWAVE, readings)),
            "disease_days" : list(filter(lambda r: r.get_humidity()>CFG.HUMIDITY_DISEASE, readings)),
            "hottest_day"  : sorted(readings, key=lambda r: r.get_temp(), reverse=True)[0],
            "wettest_day"  : sorted(readings, key=lambda r: r.get_rain(), reverse=True)[0],
        }

    def print_dataset_analysis(self, readings: list):
        result = self.analyse_dataset(readings)
        if not result: print("\n  WARNING: No data to analyse."); return
        print(f"\n  {'='*58}")
        print(f"  FUNCTIONAL ANALYTICS - {result['count']} readings   ")
        print(f"  {'='*58}")
        print(f"\n  map() + reduce()")
        print(f"     Avg Temp      : {result['avg_temp']}C")
        print(f"     Avg Rainfall  : {result['avg_rain']} mm/day")
        print(f"     Avg Humidity  : {result['avg_humidity']}%")
        print(f"     Total Rain    : {result['total_rain']} mm")
        print(f"     Max Temp      : {result['max_temp']}C")
        print(f"     Min Temp      : {result['min_temp']}C")
        print(f"     Peak Wind     : {result['peak_wind']} km/h")
        print(f"     Peak AQI      : {result['peak_aqi']}")
        print(f"\n  filter() + lambda")
        print(f"     Critical      : {len(result['critical_days'])}")
        print(f"     Dry days      : {len(result['dry_days'])}")
        print(f"     Flood days    : {len(result['flood_days'])}")
        print(f"     Heat days     : {len(result['heat_days'])}")
        print(f"     Disease risk  : {len(result['disease_days'])}")
        print(f"\n  sorted() + lambda key")
        print(f"     Hottest       : {result['hottest_day'].get_day()} ({result['hottest_day'].get_temp()}C)")
        print(f"     Wettest       : {result['wettest_day'].get_day()} ({result['wettest_day'].get_rain()}mm)")
        print(f"  {'='*58}")

    def analyse_sensor_feed(self, sensor_readings: list) -> dict:
        if not sensor_readings: return {}
        values   = list(map(lambda r: r.value, sensor_readings))
        total    = reduce(lambda a, b: a+b, values)
        critical = list(filter(lambda r: r.alert_level==AlertLevel.CRITICAL, sensor_readings))
        warnings = list(filter(lambda r: r.alert_level==AlertLevel.WARNING,  sensor_readings))
        normals  = list(filter(lambda r: r.alert_level==AlertLevel.NORMAL,   sensor_readings))
        sensors  = list({r.sensor_id for r in sensor_readings})
        per_sensor = {sid: list(filter(lambda r: r.sensor_id==sid, sensor_readings))
                      for sid in sensors}
        worst_per_sensor = {
            sid: reduce(lambda a,b: a if a.alert_level.value>=b.alert_level.value else b, group)
            for sid, group in per_sensor.items()
        }
        return {
            "total_readings"   : len(sensor_readings),
            "avg_value"        : round(total/len(values), 2),
            "critical_count"   : len(critical),
            "warning_count"    : len(warnings),
            "normal_count"     : len(normals),
            "sensors"          : sensors,
            "per_sensor"       : per_sensor,
            "worst_per_sensor" : worst_per_sensor,
        }

    def print_sensor_analysis(self, sensor_readings: list):
        result = self.analyse_sensor_feed(sensor_readings)
        if not result: print("\n  WARNING: No sensor data."); return
        print(f"\n  {'─'*58}")
        print(f"  SENSOR FEED ANALYTICS                             ")
        print(f"  {'─'*58}")
        print(f"  Total readings   : {result['total_readings']}")
        print(f"  Avg value        : {result['avg_value']}")
        print(f"  Critical         : {result['critical_count']}")
        print(f"  Warnings         : {result['warning_count']}")
        print(f"  Normal           : {result['normal_count']}")
        print(f"\n  Worst reading per sensor:")
        for sid, r in result["worst_per_sensor"].items():
            print(f"    {sid:<16} -> {r.value:>7.2f} {r.unit:<6} "
                  f"{r.alert_level.symbol()} {r.alert_level.label()}")
        print(f"  {'─'*58}")

#Weather station class
class WeatherStation:
    def __init__(self, station_id: str, location: str):
        self.station_id = station_id
        self.location   = location
        self.dataset    = WeatherDataset()

    def add_reading(self, r): self.dataset.add(r)
    def has_readings(self) -> bool: return not self.dataset.is_empty()

    def get_reading_for_day(self, day):
        try:    return self.dataset.get_for_day(day)
        except DataNotFoundError: return None

#Menu helper
def _get_int(prompt: str, lo: int, hi: int) -> int:
    while True:
        try:
            v = int(input(f"  {prompt}"))
            if lo <= v <= hi: return v
        except ValueError: pass
        print(f"  ERROR: Enter a number between {lo} and {hi}")

def _get_float(prompt: str, lo: float, hi: float) -> float:
    while True:
        try:
            v = float(input(f"  {prompt}"))
            if lo <= v <= hi: return v
        except ValueError: pass
        print(f"  ERROR: Enter a number between {lo} and {hi}")

def collect_one_day_input(day: str) -> FarmerAlert:
    print(f"\n  --- {day} ---")
    temp = _get_float("Temperature (C, -50 to 60): ", -50, 60)
    hum  = _get_float("Humidity    (%, 0-100): ",      0, 100)
    rain = _get_float("Rainfall    (mm, >= 0): ",       0, 500)
    wind = _get_float("Wind speed  (km/h, >= 0): ",     0, 200)
    print(f"  Wind directions: {', '.join(CFG.VALID_DIRS)}")
    while True:
        wdir = input("  Wind direction: ").upper().strip()
        if wdir in CFG.VALID_DIRS: break
        print("  ERROR: Invalid direction.")
    aqi = _get_int("AQI (0-500): ", 0, 500)
    return FarmerAlert(day, temp, hum, rain, wind, wdir, aqi)

#Simulation
WEEKLY_SIMULATION = [
    ["Monday",    32.5, 78.0,  4.2, 18.5, "NE", 55],
    ["Tuesday",   34.1, 72.0,  0.0, 22.0, "N",  60],
    ["Wednesday", 29.8, 85.0, 18.5, 10.0, "SE", 48],
    ["Thursday",  38.2, 60.0,  0.0, 30.5, "NW", 72],
    ["Friday",    31.0, 75.0,  7.3, 14.0, "NE", 50],
    ["Saturday",  27.5, 90.0, 32.1,  8.0, "E",  42],
    ["Sunday",    30.2, 68.0,  2.0, 19.0, "N",  58],
]

def run_weekly_simulation(station: WeatherStation, logger: WeatherLogger):
    station.dataset.clear()
    print(f"\n  {'='*56}")
    print(f"  7-DAY SIMULATION - {station.station_id}                   ")
    print(f"  {'='*56}")
    for row in WEEKLY_SIMULATION:
        r = FarmerAlert(*row)
        station.add_reading(r)
        print(r.get_summary())
    logger.event(f"7-day simulation run - {station.dataset.count()} readings")
    print(f"\n  {station.dataset.count()} days loaded.")

#Weakly summary
def print_weekly_summary(station: WeatherStation):
    if not station.has_readings():
        print("\n  WARNING: No data yet."); return
    ds         = station.dataset
    total_rain = ds.total_rainfall()
    avg_rain   = round(total_rain / ds.count(), 1)
    print(f"\n  {'='*56}")
    print(f"  WEEKLY SUMMARY - {station.station_id} | {station.location}")
    print(f"  Days recorded : {ds.count()}")
    print(f"  {'='*56}")
    print(f"\n  TEMPERATURE  avg:{ds.avg_temp()}C  max:{ds.max_temp()}C  min:{ds.min_temp()}C")
    print(f"  HUMIDITY     avg:{ds.avg_humidity()}%")
    print(f"  RAINFALL     total:{total_rain}mm  avg:{avg_rain}mm/day  "
          f"dry:{len(ds.dry_days())}  flood:{len(ds.flood_days())}")
    print(f"  WIND         peak:{ds.peak_wind()} km/h")
    print(f"  AQI          peak:{ds.peak_aqi()}")
    print(f"\n  {'─'*56}  DAILY BREAKDOWN")
    for r in ds.get_all(): print(r.get_summary())
    crit = ds.critical_days()
    print(f"\n  CRITICAL DAYS : {len(crit)}")
    for r in crit: print(f"     -> {r.get_day()}")
    worst = ds.worst_day()
    if worst: print(f"\n  WORST DAY : {worst.get_day()} - {worst.get_temp()}C")
    for r in ds.get_all():
        if isinstance(r, FarmerAlert): r.print_farmer_alerts()
    print(f"\n  {'='*56}  WEEKLY CONCLUSION")
    if avg_rain < 3:
        print("  WARNING: Dry week - drought conditions\n  -> Activate irrigation")
    elif total_rain > CFG.RAINFALL_HEAVY * 3:
        print("  WARNING: Very wet week\n  -> Inspect drainage, delay fertilizer")
    else:
        print("  OK: Conditions generally favourable\n  -> Continue normal farm operations")
    print(f"  {'='*56}")

#menu functions
def enter_live_data(station: WeatherStation, logger: WeatherLogger):
    print(f"\n  {'─'*46}")
    print("  ENTER LIVE DATA")
    print(f"  {'─'*46}")
    print("  A. Single day  B. All 7 days  C. Back")
    choice = input("\n  Select (A/B/C): ").upper().strip()
    match choice:
        case "A":
            print(f"\n  Select day:")
            for i, d in enumerate(CFG.VALID_DAYS, 1):
                print(f"  {i}. {d}")
            idx = _get_int(f"Day (1-7): ", 1, 7)
            day = CFG.VALID_DAYS[idx - 1]
            existing = station.get_reading_for_day(day)
            if existing:
                ow = input(f"  Reading for {day} exists. Overwrite? (Y/N): ").upper().strip()
                if ow == "Y": station.dataset._readings.remove(existing)
                else: return
            r = collect_one_day_input(day)
            station.add_reading(r)
            r.status_report()
            logger.event(f"Live reading added: {r.get_summary()}")
        case "B":
            station.dataset.clear()
            for day in CFG.VALID_DAYS:
                r = collect_one_day_input(day)
                station.add_reading(r)
                print(f"  {day} saved.")
            print_weekly_summary(station)
        case "C": print("  Back.")
        case _:   print("  ERROR: Invalid")

def view_summary_menu(station: WeatherStation):
    if not station.has_readings():
        print("\n  WARNING: No data yet."); return
    print(f"\n  {'─'*44}")
    print("  VIEW SUMMARY & ALERTS")
    print(f"  {'─'*44}")
    print("  A. Full report (single day)  B. Farmer alerts (single day)")
    print("  C. Full weekly summary       D. Back")
    choice = input("\n  Select (A-D): ").upper().strip()
    match choice:
        case "A": _pick_day(station, "full")
        case "B": _pick_day(station, "alerts")
        case "C": print_weekly_summary(station)
        case "D": print("  Back.")
        case _:   print("  ERROR: Invalid")

def _pick_day(station: WeatherStation, mode: str):
    available = [r.get_day() for r in station.dataset.get_all()]
    for i, d in enumerate(available, 1): print(f"  {i}. {d}")
    idx     = _get_int(f"Select (1-{len(available)}): ", 1, len(available))
    reading = station.dataset.get_for_day(available[idx-1])
    if mode == "full": reading.status_report()
    elif mode == "alerts" and isinstance(reading, FarmerAlert):
        reading.print_farmer_alerts()
    else: reading.status_report()

def dataset_analysis_menu(station: WeatherStation):
    if not station.has_readings():
        print("\n  WARNING: No data yet."); return
    ds = station.dataset
    while True:
        print(f"\n  {'─'*44}  DATASET ANALYSIS")
        print("  A. Recursive stats  B. Sort by temperature  C. Sort by rainfall")
        print("  D. Critical days    E. Days above threshold  F. Back")
        choice = input("\n  Select (A-F): ").upper().strip()
        match choice:
            case "A":
                print(f"\n  Temp  avg:{ds.avg_temp()}C  max:{ds.max_temp()}C  min:{ds.min_temp()}C")
                print(f"  Rain  total:{ds.total_rainfall()}mm  avg:{round(ds.total_rainfall()/ds.count(),1)}mm/day")
                print(f"  Humid avg:{ds.avg_humidity()}%  Wind peak:{ds.peak_wind()} km/h  AQI peak:{ds.peak_aqi()}")
            case "B":
                for r in ds.sorted_by_temp(): print(r.get_summary())
            case "C":
                for r in ds.sorted_by_rain(): print(r.get_summary())
            case "D":
                crit = ds.critical_days()
                if crit:
                    for r in crit: print(r.get_summary())
                else: print("\n  No critical days.")
            case "E":
                t = _get_float("Threshold C: ", -50, 60)
                res = ds.days_above_temp(t)
                if res:
                    for r in res: print(r.get_summary())
                else: print(f"\n  No days reached {t}C.")
            case "F": break
            case _:   print("  ERROR: Invalid")

def file_persistence_menu(station: WeatherStation,
                           file_handler: WeatherFileHandler,
                           logger: WeatherLogger):
    while True:
        print(f"\n  {'─'*50}")
        print(f"  FILE HANDLING                           ")
        print(f" \n {'─'*50}")
        print(" \n A. Save current data to CSV")
        print(" \n B. Save current data to JSON")
        print(" \nC. Load data from CSV (replaces current data)")
        print(" \n D. Back")
        choice = input("\n  Select (A-D): ").upper().strip()
        match choice:
            case "A":
                try:
                    file_handler.save_csv(station.dataset)
                except EmptyDatasetError as e:
                    print(f"\n  WARNING: {e}"); logger.warning(str(e))
                except FileHandlingError as e:
                    print(f"\n  ERROR: Save failed - {e}"); logger.error(str(e))
            case "B":
                try:
                    file_handler.save_json(station.dataset, station.station_id)
                except EmptyDatasetError as e:
                    print(f"\n  WARNING: {e}"); logger.warning(str(e))
                except FileHandlingError as e:
                    print(f"\n  ERROR: Save failed - {e}"); logger.error(str(e))
            case "C":
                confirm = input("  This will replace all current data. Continue? (Y/N): ").upper().strip()
                if confirm != "Y":
                    print("  Load cancelled."); continue
                try:
                    records = file_handler.load_csv()
                    station.dataset.clear()
                    for r in records: station.add_reading(r)
                    print(f"\n  Loaded {len(records)} record(s) successfully.")
                    print_weekly_summary(station)
                except (FileHandlingError, WeatherSystemError) as e:
                    print(f"\n  ERROR: {e}"); logger.error(str(e))
            case "D": break
            case _:   print("  ERROR: Invalid - enter A, B, C or D")

def concurrent_sensor_menu(analytics: FunctionalAnalytics, logger: WeatherLogger):
    print(f"\n  {'─'*54}")
    print(f"  CONCURRENT SENSOR SIMULATION                  ")
    print(f"  {'─'*54}")
    print(f"  Available sensors: {len(ConcurrentSensorFeed.SENSORS)}")
    for sid, param in ConcurrentSensorFeed.SENSORS:
        print(f"    {sid:<18} -> {param}")
    print()
    num_sensors = _get_int(f"How many sensors to activate? (1-{len(ConcurrentSensorFeed.SENSORS)}): ",
                           1, len(ConcurrentSensorFeed.SENSORS))
    n           = _get_int("Readings per sensor (1-200): ", 1, 200)

    feed     = ConcurrentSensorFeed(readings_per_sensor=n, num_sensors=num_sensors)
    readings = feed.run(logger)

    print(f"\n  {'─'*60}")
    print(f"  SAMPLE - first 20 readings (sorted by timestamp)")
    print(f"  {'─'*60}")
    print(f"  {'Timestamp':<14} {'Sensor':<18} {'Parameter':<14} {'Value':>7} {'Unit':<6} Level")
    print(f"  {'─'*60}")
    for r in readings[:20]: print(r)
    if len(readings) > 20:
        print(f"  ... {len(readings)-20} more rows")

    print(f"\n  {'─'*60}")
    print(f"  ALERT SUMMARY")
    print(f"  {'─'*60}")
    for level in [AlertLevel.CRITICAL, AlertLevel.WARNING, AlertLevel.NORMAL]:
        cnt = sum(1 for r in readings if r.alert_level == level)
        bar = "#" * min(cnt // 5, 40)
        print(f"  {level.symbol()} {level.label():<10} {bar} ({cnt})")

    analytics.print_sensor_analysis(readings)
    print(f"\n  System status: {feed.get_status()}")

    # Export sensor data to CSV
    save = input("\n  Save sensor readings to CSV? (Y/N): ").upper().strip()
    if save == "Y":
        try:
            filepath = SensorExporter.export(readings, logger=logger)
            print(f"  Sensor data saved. Import into Power BI for sensor-level charts.")
        except (EmptyDatasetError, FileHandlingError) as e:
            print(f"\n  ERROR: {e}")

def functional_analytics_menu(station: WeatherStation, analytics: FunctionalAnalytics):
    if not station.has_readings():
        print("\n  WARNING: No data yet - run simulation or enter live data first.")
        return
    analytics.print_dataset_analysis(station.dataset.get_all())

#Exports current datasate or uses APIs
def powerbi_export_menu(station: WeatherStation, logger: WeatherLogger):
    print(f"\n  {'='*58}")
    print(f"  POWER BI EXPORT                                [")
    print(f"  {'='*58}")

    has_data = station.has_readings()
    if has_data:
        print(f"  Current dataset : {station.dataset.count()} reading(s) loaded")
    else:
        print(f"  No data currently loaded.")

    print(f"\n  WHAT WOULD YOU LIKE TO EXPORT?")
    print(f"  A. Export current session data to Power BI CSV")
    if not has_data:
        print(f"     (NO DATA LOADED - load data first or choose B/C)")
    print(f"  B. Fetch REAL historical Juja data via Open-Meteo API")
    print(f"     (INTERNET REQUIRED- ~1000 actual daily readings)")
    print(f"  C. Generate 1000 simulated rows (offline fallback)")
    print(f"  D. Cancel")
 

    choice = input("\n  Select (A/B/C/D): ").upper().strip()

    try:
        if choice == "A":
            if not has_data:
                print("\n  WARNING: No data to export.")
                print("  Load data first (option 1, 2, or 10), then come back.")
                return
            rows = []
            for r in station.dataset.get_all():
                rows.append({
                    "date"          : datetime.date.today().isoformat(),
                    "day_name"      : r.get_day(),
                    "month"         : datetime.date.today().strftime("%B"),
                    "month_num"     : datetime.date.today().month,
                    "year"          : datetime.date.today().year,
                    "season"        : "User Data",
                    "hour"          : 12,
                    "temperature"   : r.get_temp(),
                    "humidity"      : r.get_humidity(),
                    "rainfall"      : r.get_rain(),
                    "wind_speed"    : r.get_wind(),
                    "wind_direction": r.get_wind_dir(),
                    "aqi"           : r.get_aqi(),
                    "latitude"      : CFG.LATITUDE,
                    "longitude"     : CFG.LONGITUDE,
                    "station_id"    : CFG.STATION_ID,
                    "location"      : CFG.LOCATION,
                    "source"        : "Live/Session Data",
                })
            filepath = PowerBIExporter.export(rows, logger=logger)
            print(f"\n  Exported {len(rows)} reading(s) from current session.")
            PowerBIExporter.print_powerbi_guide()
            logger.event(f"Power BI export (session data): {filepath}")

        elif choice == "B":
            print("\n  Fetching real weather data from Open-Meteo API...")
            print("  This requires an internet connection.")
            rows = OpenMeteoAPI.fetch(target_rows=1000, logger=logger)
            station.dataset.clear()
            readings = OpenMeteoAPI.to_weather_readings(rows)
            for r in readings:
                station.add_reading(r)
            print(f"  Loaded {station.dataset.count()} real readings into the system.")
            filepath = PowerBIExporter.export(rows, logger=logger)
            PowerBIExporter.print_powerbi_guide()
            logger.event(f"Power BI export (Open-Meteo API real data): {filepath}")

        elif choice == "C":
            rows = RealisticDataGenerator.generate(1000)
            station.dataset.clear()
            for reading in RealisticDataGenerator.to_weather_readings(rows):
                station.add_reading(reading)
            print(f"\n  Loaded {station.dataset.count()} simulated readings into the system.")
            filepath = PowerBIExporter.export(rows, logger=logger)
            PowerBIExporter.print_powerbi_guide()
            logger.event(f"Power BI export (generated fallback): {filepath}")

        elif choice == "D":
            print("  Cancelled.")
        else:
            print("  ERROR: Invalid - enter A, B, C or D")

    except APIError as e:
        print(f"\n  API ERROR: {e}")
        print(f"\n  No internet? Use option C to generate offline fallback data instead.")
        logger.error(f"API error: {e}")
    except FileHandlingError as e:
        print(f"\n  ERROR: Export failed - {e}")
        print(f"  Close any open CSV files in Excel/Power BI and try again.")
        logger.error(f"Power BI export failed: {e}")

def view_system_log(logger: WeatherLogger):
    try:    logger.view_log_file()
    except FileHandlingError as e: print(f"\n  ERROR: Could not read log: {e}")

#Main Entery Point
def main():
    logger       = WeatherLogger()
    file_handler = WeatherFileHandler(logger)
    analytics    = FunctionalAnalytics()

    logger.event("SYSTEM STARTED")

    print("=" * 64)
    print(f"  {CFG.SYSTEM_NAME}")
    print(f"  Station  : {CFG.STATION_ID}")
    print(f"  Location : {CFG.LOCATION}")
    print(f"  Version  : 5.2 - Real API + sensor export + Power BI")
    print("=" * 64)

    station = WeatherStation(CFG.STATION_ID, CFG.LOCATION)

    while True:
        print("\n  ┌─────────────────────────────────────────────────────────┐")
        print("  │                       MAIN MENU                         │")
        print("  ├─────────────────────────────────────────────────────────┤")
        print("  │  1. Run 7-Day Simulation                                │")
        print("  │  2. Enter Live Data                                     │")
        print("  │  3. View Summary & Alerts                               │")
        print("  │  4. Dataset Analysis                                    │")
        print("  │  5. File Handling                                       │")
        print("  │  6. View System Log                                     │")
        print("  │  7. Concurrent Sensor Simulation                        │")
        print("  │  8. Functional Analytics                                │")
        print("  │  9. Power BI Export                                     │")
        print("  │  0. Exit                                                │")
        print("  └─────────────────────────────────────────────────────────┘")

        choice = input("\n  Select (0-9): ").strip()
        match choice:
            case "1": run_weekly_simulation(station, logger)
            case "2": enter_live_data(station, logger)
            case "3": view_summary_menu(station)
            case "4": dataset_analysis_menu(station)
            case "5": file_persistence_menu(station, file_handler, logger)
            case "6": view_system_log(logger)
            case "7": concurrent_sensor_menu(analytics, logger)
            case "8": functional_analytics_menu(station, analytics)
            case "9": powerbi_export_menu(station, logger)
            case "0":
                logger.event("System shutdown")
                print("\n  Shutting down JKUAT Weather System...")
                print("  ─────────────────────────────────────────────────────────")
                print("=" * 64)
                break
            case _: print("  ERROR: Invalid - enter 0 through 9")

if __name__ == "__main__":
    main()