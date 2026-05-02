from abc import ABC, abstractmethod
import os
import csv
import json
import datetime

class WeatherConfig:
   
    SYSTEM_NAME    = "JKUAT Weather & Environmental Data System"
    VERSION        = "4.0"
    MILESTONE      = "Milestone 4"
    STATION_ID     = "KE-NBI-001"
    LOCATION       = "JKUAT Main Farm, Juja"

    TEMP_HEATWAVE      = 35.0 ;  WIND_STRONG        = 50.0
    TEMP_OPTIMAL_LOW   = 20.0 ;  WIND_MODERATE      = 30.0
    TEMP_COLD          = 10.0 ;  HUMIDITY_DISEASE   = 85.0
    RAINFALL_CROP_NEED = 5.0  ;  HUMIDITY_DRY       = 30.0
    RAINFALL_LOW       = 2.0  ;  AQI_UNHEALTHY      = 150
    RAINFALL_HEAVY     = 25.0 ;  AQI_MODERATE       = 100
   
    VALID_DAYS = ["Monday", "Tuesday", "Wednesday",
                  "Thursday", "Friday", "Saturday", "Sunday"]
    VALID_DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    DATA_DIR      = "weather_data"
    CSV_FILENAME  = os.path.join(DATA_DIR, "weather_readings.csv")
    JSON_FILENAME = os.path.join(DATA_DIR, "weather_readings.json")
    LOG_FILENAME  = os.path.join(DATA_DIR, "system.log")

    CSV_HEADERS = ["day", "temperature", "humidity",
                   "rainfall", "wind_speed", "wind_direction", "aqi"]

CFG = WeatherConfig

class WeatherSystemError(Exception):
    pass

class ValidationError(WeatherSystemError): # raised when sensor input fails range or type validation
    pass

class FileHandlingError(WeatherSystemError): # raised for any file I/O issues 
    pass

class DataNotFoundError(WeatherSystemError): # raised when trying to access data that doesn't exist
    pass

class EmptyDatasetError(WeatherSystemError): # raised when trying to save an empty dataset
    pass

class WeatherLogger:
    def __init__(self, filepath: str = CFG.LOG_FILENAME):
        self._filepath     = filepath
        self._recent: list = []  
        self._ensure_dir()

    def _ensure_dir(self): # create log directory if it doesn't exist, but don't crash if it fails
        try:
            os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        except OSError as e:
            print(f"  ⚠️  Logger: could not create directory — {e}")

    def _timestamp(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write(self, level: str, message: str):
        entry = f"[{self._timestamp()}] [{level:<7}] {message}"
        self._recent.append(entry)
        try:
            with open(self._filepath, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except OSError:
            pass   

    def info(self,    msg: str): self._write("INFO",    msg)
    def warning(self, msg: str): self._write("WARNING", msg)
    def error(self,   msg: str): self._write("ERROR",   msg)
    def event(self,   msg: str): self._write("EVENT",   msg)

    def get_recent(self, n: int = 20) -> list: #return the most recent n log entries
        return self._recent[-n:]

    def view_log_file(self): # print the contents of the log file 
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

class WeatherFileHandler: # handles all CSV and JSON file operations, with error handling and logging
    def __init__(self, logger: WeatherLogger):
        self._logger = logger
        self._ensure_dir()

    def _ensure_dir(self):
        try:
            os.makedirs(CFG.DATA_DIR, exist_ok=True)
        except OSError as e:
            self._logger.error(f"Cannot create data directory: {e}")

    def save_csv(self, dataset, filepath: str = CFG.CSV_FILENAME): # Save all readings to a CSV file. 
        if dataset.is_empty():
            raise EmptyDatasetError("No data to save — run simulation or enter readings first.")

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CFG.CSV_HEADERS)
                writer.writeheader()
                for r in dataset.get_all():
                    writer.writerow({
                        "day"           : r.get_day(),
                        "temperature"   : r.get_temp(),
                        "humidity"      : r.get_humidity(),
                        "rainfall"      : r.get_rain(),
                        "wind_speed"    : r.get_wind(),
                        "wind_direction": r.get_wind_dir(),
                        "aqi"           : r.get_aqi(),
                    })
            self._logger.event(f"CSV saved → {filepath}  ({dataset.count()} records)")
            print(f"\n  ✅ Data saved to: {filepath}  ({dataset.count()} record(s))")

        except OSError as e:
            self._logger.error(f"CSV save failed: {e}")
            raise FileHandlingError(f"Could not save CSV: {e}") from e

    def load_csv(self, filepath: str = CFG.CSV_FILENAME) -> list: #load readings from a CSV file 
        if not os.path.exists(filepath):
            raise FileHandlingError(f"File not found: {filepath}")

        records = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):  # row 1 = header
                    try:
                        record = FarmerAlert(
                            day           = row["day"],
                            temperature   = float(row["temperature"]),
                            humidity      = float(row["humidity"]),
                            rainfall      = float(row["rainfall"]),
                            wind_speed    = float(row["wind_speed"]),
                            wind_direction= row["wind_direction"],
                            aqi           = int(row["aqi"]),
                            validate      = True,
                        )
                        records.append(record)
                    except (ValueError, KeyError, WeatherSystemError) as row_err:
                        self._logger.warning(f"Skipped row {row_num}: {row_err}")
                        print(f"  ⚠️  Row {row_num} skipped — {row_err}")

        except OSError as e:
            self._logger.error(f"CSV load failed: {e}")
            raise FileHandlingError(f"Could not read CSV: {e}") from e

        if not records:
            raise FileHandlingError("File loaded but contained no valid records.")

        self._logger.event(f"CSV loaded ← {filepath}  ({len(records)} records)")
        return records

    def save_json(self, dataset, station_id: str, # JSON 
                  filepath: str = CFG.JSON_FILENAME):
        if dataset.is_empty():
            raise EmptyDatasetError("No data to save.")

        payload = {
            "system"    : CFG.SYSTEM_NAME,
            "version"   : CFG.VERSION,
            "station_id": station_id,
            "saved_at"  : datetime.datetime.now().isoformat(),
            "readings"  : [
                {
                    "day"           : r.get_day(),
                    "temperature"   : r.get_temp(),
                    "humidity"      : r.get_humidity(),
                    "rainfall"      : r.get_rain(),
                    "wind_speed"    : r.get_wind(),
                    "wind_direction": r.get_wind_dir(),
                    "aqi"           : r.get_aqi(),
                    "heat_index"    : r.get_heat_index(),
                    "evap"          : r.get_evap(),
                    "dew_point"     : r.get_dew_point(),
                    "overall_status": r.get_overall_status(),
                }
                for r in dataset.get_all()
            ],
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            self._logger.event(f"JSON saved → {filepath}  ({dataset.count()} records)")
            print(f"\n  ✅ JSON saved to: {filepath}  ({dataset.count()} record(s))")
        except OSError as e:
            self._logger.error(f"JSON save failed: {e}")
            raise FileHandlingError(f"Could not save JSON: {e}") from e


VALID_DAYS = CFG.VALID_DAYS   
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

    def get_summary(self) -> str:
        deficit = f"Deficit:{self.__water_deficit:.1f}mm" \
                  if self.__water_deficit > 0 else "Water:OK"
        return (f"  {self._day:<12} | Temp:{self.__temp}°C | "
                f"Humid:{self.__humidity}% | Rain:{self.__rainfall}mm | "
                f"Wind:{self.__wind}km/h {self.__wind_dir:<2} | "
                f"AQI:{self.__aqi} | {deficit} | {self.get_overall_status()}")

    def status_report(self):
        print(f"\n  {'='*56}")
        print(f"  WEATHER REPORT — {self._day}")
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
        print(f"\n   OVERALL          : {self.get_overall_status()}")
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
            alerts.append("   Delay spraying — cold slows chemical absorption")

        if aqi >= CFG.AQI_UNHEALTHY:
            alerts.append(f"😷 AQI {aqi} — workers must wear masks today")
        elif aqi >= CFG.AQI_MODERATE:
            alerts.append(f"😷 AQI {aqi} — moderate air quality, sensitive workers take care")

        if dew > 20:
            alerts.append(f"💦 Dew point {dew}°C — heavy dew expected, delay morning spraying")

        if not alerts:
            alerts.append("✅ All conditions within safe range — normal operations today")
            alerts.append("   Good day for weeding, scouting, or fertilizer application")

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
        print(f"  Overall condition : {self.get_overall_status()}")
        print(f"  {'='*56}")

class WeatherDataset:
    def __init__(self):
        self.__readings: list = []

    def add(self, reading: EnvironmentalReading):
        self.__readings.append(reading)

    def remove_day(self, day: str):
        self.__readings = [r for r in self.__readings if r.get_day() != day]

    def get_for_day(self, day: str):
        for r in self.__readings:
            if r.get_day() == day: return r
        return None

    def get_all(self) -> list: return list(self.__readings)

    def count(self) -> int:    return len(self.__readings)

    def is_empty(self) -> bool: return len(self.__readings) == 0

    def clear(self):            self.__readings = []

    def _recursive_sum(self, lst): #recursively sum a list of numbers
        if not lst:     return 0
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

    def add_reading(self, reading: EnvironmentalReading):
        self.dataset.add(reading)

    def has_readings(self) -> bool:
        return not self.dataset.is_empty()

    def get_reading_for_day(self, day: str):
        return self.dataset.get_for_day(day)

WEEKLY_SIMULATION = [
    ["Monday",    32.5, 78.0,  4.2, 18.5, "NE", 55],
    ["Tuesday",   34.1, 72.0,  0.0, 22.0, "N",  60],
    ["Wednesday", 29.8, 85.0, 18.5, 10.0, "SE", 48],
    ["Thursday",  38.2, 60.0,  0.0, 30.5, "NW", 72],
    ["Friday",    31.0, 75.0,  7.3, 14.0, "NE", 50],
    ["Saturday",  27.5, 90.0, 32.1,  8.0, "E",  42],
    ["Sunday",    30.2, 68.0,  2.0, 19.0, "N",  58],
]
# input validation functions for live data entry, with error handling and user prompts
def _get_float(prompt, lo, hi): 
    while True:
        try:
            v = float(input(f"  {prompt}"))
            if lo <= v <= hi: return v
        except ValueError:
            pass
        print(f"  ❌ Enter a number between {lo} and {hi}")


def _get_int(prompt, lo, hi):
    while True:
        try:
            v = int(input(f"  {prompt}"))
            if lo <= v <= hi: return v
        except ValueError:
            pass
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

#menu functions
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
    print("  → View Summary → Full week to see all alerts per day.")


def enter_live_data(station: WeatherStation, logger: WeatherLogger):
    print(f"\n  {'='*54}")
    print(f"  LIVE DATA ENTRY — Station: {station.station_id}")
    print(f"  {'='*54}")
    print("  ┌──────────────────────────────────────────┐")
    print("  │  A. Enter a single day                   │")
    print("  │  B. Enter readings for the full week     │")
    print("  │  C. Back                                 │")
    print("  └──────────────────────────────────────────┘")
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
                logger.error(f"Validation error during live entry: {ve}")
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
                    logger.error(f"Skipped {day} — validation error: {ve}")
                    print(f"  ⚠️  {day} skipped — {ve}\n")
            print("  ✅ Full week recorded.")
            print_weekly_summary(station)

        case "C":
            print("  ↩  Back.")
        case _:
            print("  ❌ Invalid — enter A, B, or C")


def view_summary_menu(station: WeatherStation):
    if not station.has_readings():
        print("\n  ⚠️  No data yet — run simulation or enter live data first.")
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
    print(f"\n  🌡️  TEMPERATURE  (recursive stats)")
    print(f"     Average  : {ds.avg_temp()}°C")
    print(f"     Peak     : {ds.max_temp()}°C")
    print(f"     Lowest   : {ds.min_temp()}°C")
    print(f"\n  💧 HUMIDITY")
    print(f"     Average  : {ds.avg_humidity()}%")
    print(f"\n  🌧️  RAINFALL")
    print(f"     Total    : {total_rain} mm")
    print(f"     Daily avg: {avg_rain} mm/day")
    print(f"     Dry days : {len(ds.dry_days())}")
    print(f"     Flood days: {len(ds.flood_days())}")
    print(f"\n  💨 WIND")
    print(f"     Peak     : {ds.peak_wind()} km/h")
    print(f"\n  🌫️  AIR QUALITY")
    print(f"     Peak AQI : {ds.peak_aqi()}")
    print(f"\n  {'─'*56}")
    print(f"  DAILY BREAKDOWN")
    print(f"  {'─'*56}")
    for r in ds.get_all():
        print(r.get_summary())
    critical = ds.critical_days()
    print(f"\n  ⚠️  CRITICAL DAYS : {len(critical)}")
    for r in critical:
        print(f"     → {r.get_day()}")
    worst = ds.worst_day()
    if worst:
        print(f"\n  🌡️  WORST DAY     : {worst.get_day()} — {worst.get_temp()}°C")
    print(f"\n  {'─'*56}")
    print(f"  FARMER ALERTS — ALL DAYS")
    print(f"  {'─'*56}")
    for r in ds.get_all():
        if isinstance(r, FarmerAlert):
            r.print_farmer_alerts()
    print(f"\n  {'='*56}")
    print(f"  WEEKLY CONCLUSION")
    print(f"  {'='*56}")
    if avg_rain < 3:
        print("  ⚠️  Dry week — drought conditions")
        print("  ➡️  Activate irrigation for the coming week")
        print("  ➡️  Apply mulch to conserve soil moisture")
    elif total_rain > CFG.RAINFALL_HEAVY * 3:
        print("  ⚠️  Very wet week — waterlogging risk")
        print("  ➡️  Inspect drainage channels urgently")
        print("  ➡️  Delay fertilizer — nutrients will leach out")
    else:
        print("  ✅ Conditions generally favourable this week")
        print("  ➡️  Continue normal farm operations")
    if ds.max_temp() >= CFG.TEMP_HEATWAVE:
        print(f"  🔥 Heat stress peak: {ds.max_temp()}°C — review irrigation schedule")
    if ds.peak_aqi() >= CFG.AQI_MODERATE:
        print(f"  😷 Air quality concern — peak AQI {ds.peak_aqi()} this week")
    print(f"  {'='*56}")


def dataset_analysis_menu(station: WeatherStation):
    if not station.has_readings():
        print("\n  ⚠️  No data yet — run simulation or enter live data first.")
        return
    ds = station.dataset
    while True:
        print(f"\n  {'─'*44}")
        print("  DATASET ANALYSIS")
        print(f"  {'─'*44}")
        print("  A. Recursive statistics")
        print("  B. Sort by temperature (hottest → coolest)")
        print("  C. Sort by rainfall    (wettest → driest)")
        print("  D. Show critical days only")
        print("  E. Days above a temperature threshold")
        print("  F. Back")
        choice = input("\n  Select (A–F): ").upper().strip()
        match choice:
            case "A":
                print(f"\n  Temp  — avg:{ds.avg_temp()}°C  max:{ds.max_temp()}°C  min:{ds.min_temp()}°C")
                print(f"  Rain  — total:{ds.total_rainfall()}mm  avg:{round(ds.total_rainfall()/ds.count(),1)}mm/day")
                print(f"  Humid — avg:{ds.avg_humidity()}%")
                print(f"  Wind  — peak:{ds.peak_wind()} km/h")
                print(f"  AQI   — peak:{ds.peak_aqi()}")
            case "B":
                print("\n  Hottest → Coolest:")
                for r in ds.sorted_by_temp():
                    print(r.get_summary())
            case "C":
                print("\n  Wettest → Driest:")
                for r in ds.sorted_by_rain():
                    print(r.get_summary())
            case "D":
                crit = ds.critical_days()
                if crit:
                    print(f"\n  {len(crit)} critical day(s):")
                    for r in crit: print(r.get_summary())
                else:
                    print("\n  ✅ No critical days this week.")
            case "E":
                t   = _get_float("Threshold °C: ", -50, 60)
                res = ds.days_above_temp(t)
                if res:
                    print(f"\n  Days at or above {t}°C:")
                    for r in res: print(r.get_summary())
                else:
                    print(f"\n  No days reached {t}°C.")
            case "F":
                break
            case _:
                print("  ❌ Invalid — enter A, B, C, D, E or F")


def file_persistence_menu(station: WeatherStation,
                           file_handler: WeatherFileHandler,
                           logger: WeatherLogger):
    while True:
        print(f"\n  {'─'*50}")
        print("  FILE PERSISTENCE                          ")
        print(f"  {'─'*50}")
        print("  A. Save current data to CSV")
        print("  B. Save current data to JSON")
        print("  C. Load data from CSV (replaces current data)")
        print("  D. Back")
        choice = input("\n  Select (A–D): ").upper().strip()

        match choice:

            case "A":
                try:
                    file_handler.save_csv(station.dataset)
                except EmptyDatasetError as e:
                    print(f"\n  ⚠️  {e}")
                    logger.warning(str(e))
                except FileHandlingError as e:
                    print(f"\n  ❌ Save failed: {e}")

            case "B":
                try:
                    file_handler.save_json(station.dataset, station.station_id)
                except EmptyDatasetError as e:
                    print(f"\n  ⚠️  {e}")
                    logger.warning(str(e))
                except FileHandlingError as e:
                    print(f"\n  ❌ Save failed: {e}")

            case "C":
                print(f"\n  Loading from: {CFG.CSV_FILENAME}")
                confirm = input("  This will replace all current data. Continue? (Y/N): ").upper().strip()
                if confirm != "Y":
                    print("  ↩  Load cancelled.")
                    break
                try:
                    records = file_handler.load_csv()
                    station.dataset = WeatherDataset()
                    for r in records:
                        station.add_reading(r)
                    print(f"\n  ✅ Loaded {len(records)} record(s) successfully.")
                    print_weekly_summary(station)
                except FileHandlingError as e:
                    print(f"\n  ❌ Load failed: {e}")
                except WeatherSystemError as e:
                    print(f"\n  ❌ System error: {e}")

            case "D":
                break

            case _:
                print("  ❌ Invalid — enter A, B, C or D")

#system log viewer function
def view_system_log(logger: WeatherLogger):
    try:
        logger.view_log_file()
    except FileHandlingError as e:
        print(f"\n  ❌ Could not read log: {e}")

#entry point
def main():
    logger       = WeatherLogger()            #initialize logger first to capture all events 
    file_handler = WeatherFileHandler(logger)

    logger.event("System started — Milestone 4")

    print("=" * 60)
    print(f"  {CFG.SYSTEM_NAME}")
    print(f"  Version  : {CFG.VERSION}  |  {CFG.MILESTONE}")
    print(f"  Focus    : Modular Architecture & System Robustness")
    print(f"  Station  : {CFG.STATION_ID}")
    print(f"  Location : {CFG.LOCATION}")
    print("=" * 60)

    station = WeatherStation(CFG.STATION_ID, CFG.LOCATION)

    while True:
        print("\n  ┌──────────────────────────────────────────────────┐")
        print("  │                   MAIN MENU                      │")
        print("  ├──────────────────────────────────────────────────┤")
        print("  │  1. Run 7-Day Simulation                         │")
        print("  │  2. Enter Live Data                              │")
        print("  │  3. View Summary & Alerts                        │")
        print("  │  4. Dataset Analysis                             │")
        print("  │  5. File Persistence (Save / Load)               │")
        print("  │  6. View System Log                              │")
        print("  │  7. Exit                                         │")
        print("  └──────────────────────────────────────────────────┘")

        choice = input("\n  Select (1–7): ").strip()

        match choice:
            case "1": run_weekly_simulation(station, logger)
            case "2": enter_live_data(station, logger)
            case "3": view_summary_menu(station)
            case "4": dataset_analysis_menu(station)
            case "5": file_persistence_menu(station, file_handler, logger)
            case "6": view_system_log(logger)
            case "7":
                logger.event("System shutdown")
                print("\n  Shutting down JKUAT Weather System...")
                print("  ─────────────────────────────────────────────────")
                print("  END OF MILESTONE 4")
                print("  Modular Architecture & System Robustness")
                print("  What was added:")
                print("   ✔ WeatherConfig   — centralised constants & paths")
                print("   ✔ WeatherLogger   — persistent timestamped log file")
                print("   ✔ WeatherFileHandler — CSV + JSON save/load")
                print("   ✔ Custom exception hierarchy (5 exception types)")
                print("   ✔ All file I/O wrapped in try/except/finally")
                print("  Next → Milestone 5: Concurrency & Advanced Computation")
                print("=" * 60)
                break
            case _:
                print("  ❌ Invalid — enter 1 through 7")


if __name__ == "__main__":
    main()