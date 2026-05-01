TEMP_HEATWAVE      = 35.0 ;  WIND_STRONG        = 50.0
TEMP_OPTIMAL_LOW   = 20.0 ;  WIND_MODERATE      = 30.0
TEMP_COLD          = 10.0 ;  HUMIDITY_DISEASE   = 85.0
RAINFALL_CROP_NEED = 5.0  ;  HUMIDITY_DRY       = 30.0
RAINFALL_LOW       = 2.0  ;  AQI_UNHEALTHY      = 150
RAINFALL_HEAVY     = 25.0 ;  AQI_MODERATE       = 100

VALID_DAYS = ["Monday", "Tuesday", "Wednesday",
              "Thursday", "Friday", "Saturday", "Sunday"]

from abc import ABC, abstractmethod

class EnvironmentalReading(ABC):
    def __init__(self, day):
        if day not in VALID_DAYS:
            raise ValueError(f"Invalid day: '{day}'")
        self._day = day

    def get_day(self):
        return self._day

    @abstractmethod
    def get_summary(self) -> str:
        pass

    @abstractmethod
    def status_report(self):
        pass

    @abstractmethod
    def get_overall_status(self) -> str:
        pass

    def __str__(self):
        return self.get_summary()


class WeatherReading(EnvironmentalReading):
    def __init__(self, day, temperature, humidity,
                 rainfall, wind_speed, aqi,
                 validate=True):

        super().__init__(day)

        if validate:
            self.__temp     = self.__val_range("Temperature", temperature, -50, 60)
            self.__humidity = self.__val_range("Humidity",    humidity,      0, 100)
            self.__rainfall = self.__val_nonneg("Rainfall",   rainfall)
            self.__wind     = self.__val_nonneg("Wind speed", wind_speed)
            self.__aqi      = self.__val_range("AQI",         aqi,           0, 500)
        else:
            self.__temp     = temperature
            self.__humidity = humidity
            self.__rainfall = rainfall
            self.__wind     = wind_speed
            self.__aqi      = aqi

        self.__heat_index    = self.__compute_heat_index()
        self.__evap          = self.__compute_evapotranspiration()
        self.__dew_point     = self.__compute_dew_point()
        self.__kelvin        = round(self.__temp + 273.15, 2)
        self.__water_deficit = max(0.0, RAINFALL_CROP_NEED - self.__rainfall)

    def __val_range(self, name, v, lo, hi):
        if not (lo <= v <= hi):
            raise ValueError(f"{name} {v} out of range [{lo} – {hi}]")
        return v

    def __val_nonneg(self, name, v):
        if v < 0:
            raise ValueError(f"{name} cannot be negative: {v}")
        return v

    def __compute_heat_index(self):
        return round(self.__temp + (0.33 * (self.__humidity / 100) * 6.105) - 4.0, 1)

    def __compute_evapotranspiration(self):
        return round((0.0023 * (self.__temp + 17.8) * (100 - self.__humidity) ** 0.5), 2)

    def __compute_dew_point(self):
        a, b  = 17.27, 237.7
        gamma = ((a * self.__temp) / (b + self.__temp)) + (self.__humidity / 100.0)
        return round((b * gamma) / (a - gamma), 2)

    def get_temp(self):          return self.__temp
    def get_humidity(self):      return self.__humidity
    def get_rain(self):          return self.__rainfall
    def get_wind(self):          return self.__wind
    def get_aqi(self):           return self.__aqi
    def get_heat_index(self):    return self.__heat_index
    def get_evap(self):          return self.__evap
    def get_dew_point(self):     return self.__dew_point
    def get_kelvin(self):        return self.__kelvin
    def get_water_deficit(self): return self.__water_deficit

    def temperature_status(self):
        if self.__temp >= TEMP_HEATWAVE:
            return "CRITICAL : Heat stress — irrigate immediately"
        elif self.__temp >= TEMP_OPTIMAL_LOW:
            return "OK       : Temperature within optimal crop range"
        elif self.__temp <= TEMP_COLD:
            return "WARNING  : Cold stress — cover seedlings tonight"
        else:
            return "NOTICE   : Below optimal — monitor crops"

    def rainfall_status(self):
        if self.__rainfall == 0:
            return "ALERT    : No rainfall — full irrigation required"
        elif self.__rainfall < RAINFALL_LOW:
            return f"LOW      : {self.__rainfall}mm — partial irrigation needed"
        elif self.__rainfall < RAINFALL_CROP_NEED:
            return f"NOTICE   : {self.__rainfall}mm — below daily crop requirement"
        elif self.__rainfall <= RAINFALL_HEAVY:
            return "OK       : Adequate rainfall for crops today"
        else:
            return "CRITICAL : Excess rainfall — flooding risk, check drainage"

    def humidity_status(self):
        if self.__humidity > HUMIDITY_DISEASE:
            return "WARNING  : High humidity — fungal disease risk"
        elif self.__humidity < HUMIDITY_DRY:
            return "WARNING  : Low humidity — moisture stress likely"
        else:
            return "OK       : Humidity within acceptable range"

    def wind_status(self):
        if self.__wind > WIND_STRONG:
            return "CRITICAL : Strong winds — crop damage risk"
        elif self.__wind > WIND_MODERATE:
            return "WARNING  : Moderate winds — lodging risk"
        else:
            return "OK       : Calm wind conditions"

    def air_quality_status(self):
        if self.__aqi >= AQI_UNHEALTHY:
            return "CRITICAL : Unhealthy air — limit worker exposure"
        elif self.__aqi >= AQI_MODERATE:
            return "MODERATE : Elevated AQI — sensitive workers take caution"
        else:
            return "OK       : Air quality acceptable"

    def get_overall_status(self) -> str:
        checks = [
            self.temperature_status(), self.rainfall_status(),
            self.humidity_status(),    self.wind_status(),
            self.air_quality_status()
        ]
        if any("CRITICAL" in c or "ALERT" in c for c in checks): return "CRITICAL"
        if any("WARNING"  in c for c in checks):                  return "WARNING"
        return "NORMAL"

    def get_summary(self) -> str:
        deficit = f"Deficit:{self.__water_deficit:.1f}mm" if self.__water_deficit > 0 else "Water:OK"
        return (f"  {self._day:<12} | "
                f"Temp:{self.__temp}°C | "
                f"Humid:{self.__humidity}% | "
                f"Rain:{self.__rainfall}mm | "
                f"Wind:{self.__wind}km/h | "
                f"AQI:{self.__aqi} | "
                f"{deficit} | "
                f"{self.get_overall_status()}")

    def status_report(self):
        print(f"\n  {'='*56}")
        print(f"  WEATHER REPORT — {self._day}")
        print(f"  {'='*56}")
        print(f"   Temperature      : {self.__temp}°C  ({self.__kelvin}K)")
        print(f"   Humidity         : {self.__humidity}%")
        print(f"   Rainfall         : {self.__rainfall} mm")
        print(f"   Wind             : {self.__wind} km/h")
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
                 rainfall, wind_speed, aqi,
                 validate=True):
        super().__init__(day, temperature, humidity, rainfall,
                         wind_speed, aqi, validate)
        self.__alerts = []
        self.__build_alerts()

    def __build_alerts(self):
        temp    = self.get_temp()
        rain    = self.get_rain()
        hum     = self.get_humidity()
        wind    = self.get_wind()
        aqi     = self.get_aqi()
        evap    = self.get_evap()
        deficit = self.get_water_deficit()
        hi      = self.get_heat_index()

        alerts = []

        if rain == 0 and temp >= TEMP_HEATWAVE:
            alerts.append("🚨 Zero rain + extreme heat — irrigate all fields immediately")
        elif rain == 0:
            alerts.append("💧 No rainfall today — run a full irrigation cycle")
        elif deficit > 0:
            alerts.append(f"💧 Rainfall {rain}mm short of crop need — supplement with {deficit:.1f}mm irrigation")

        if evap > 5.0:
            alerts.append(f"☀️  High water loss rate ({evap}mm/day) — irrigate early morning before 8am")
        elif evap > 3.0:
            alerts.append(f"☀️  Moderate water loss ({evap}mm/day) — check soil moisture at noon")

        if temp >= TEMP_HEATWAVE:
            alerts.append(f"🔥 Heat stress at {temp}°C (feels like {hi}°C) — avoid midday field work")
            alerts.append("   Increase watering frequency. Mulch around plants to retain moisture.")
        elif temp >= 30:
            alerts.append(f"🌡️  Warm day ({temp}°C) — monitor crop water needs through the day")

        if hum > HUMIDITY_DISEASE:
            alerts.append(f"🍄 High humidity ({hum}%) — disease conditions active")
            alerts.append("   Scout fields for fungal symptoms. Improve drainage between rows.")
            alerts.append("   Avoid overhead irrigation — it increases leaf wetness duration.")
        elif hum > 75 and temp > 25:
            alerts.append(f"⚠️  Warm + humid ({temp}°C / {hum}%) — monitor closely for early disease signs")

        if rain > RAINFALL_HEAVY:
            alerts.append(f"🌊 Heavy rainfall ({rain}mm) — inspect drainage channels now")
            alerts.append("   Hold off on fertilizer application — nutrients will leach out")
            alerts.append("   Check for waterlogged areas and clear standing water")

        if wind > WIND_STRONG:
            alerts.append(f"💨 Dangerous wind speed ({wind}km/h) — secure structures and young plants")
            alerts.append("   Inspect crops for broken stems and lodging after wind subsides")
        elif wind > WIND_MODERATE:
            alerts.append(f"💨 Strong wind ({wind}km/h) — monitor tall crops for lodging")

        if temp <= TEMP_COLD:
            alerts.append(f"🥶 Cold temperature ({temp}°C) — cover young plants with mulch tonight")
            alerts.append("   Delay any spraying — cold slows chemical absorption")

        if aqi >= AQI_UNHEALTHY:
            alerts.append(f"😷 AQI {aqi} — unhealthy air. Farm workers must wear masks today.")
            alerts.append("   Limit outdoor exposure. Avoid burning anything on the farm.")
        elif aqi >= AQI_MODERATE:
            alerts.append(f"😷 AQI {aqi} — moderate air quality. Sensitive workers take precautions.")

        dew = self.get_dew_point()
        if dew > 20:
            alerts.append(f"💦 Dew point at {dew}°C — heavy dew expected. Delay morning spraying.")

        if not alerts:
            alerts.append("✅ All conditions within safe range — normal operations today")
            alerts.append("   Good day for weeding, scouting, fertilizer or pesticide application")

        self.__alerts = alerts

    def get_alerts(self):
        return list(self.__alerts)

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
        print(f"  Overall condition: {self.get_overall_status()}")
        print(f"  {'='*56}")


class WeatherDataset:
    def __init__(self):
        self.__readings = []

    def add(self, reading):
        self.__readings.append(reading)

    def remove_day(self, day):
        self.__readings = [r for r in self.__readings if r.get_day() != day]

    def get_all(self):
        return list(self.__readings)

    def get_for_day(self, day):
        for r in self.__readings:
            if r.get_day().lower() == day.lower():
                return r
        return None

    def count(self):
        return len(self.__readings)

    def is_empty(self):
        return len(self.__readings) == 0

    def _recursive_sum(self, values, index=0):
        if index == len(values): return 0
        return values[index] + self._recursive_sum(values, index + 1)

    def _recursive_max(self, values, index=0, current=None):
        if index == len(values): return current
        v = values[index]
        current = v if current is None else max(current, v)
        return self._recursive_max(values, index + 1, current)

    def _recursive_min(self, values, index=0, current=None):
        if index == len(values): return current
        v = values[index]
        current = v if current is None else min(current, v)
        return self._recursive_min(values, index + 1, current)

    def avg_temp(self):
        if self.is_empty(): return 0.0
        vals = [r.get_temp() for r in self.__readings]
        return round(self._recursive_sum(vals) / len(vals), 1)

    def max_temp(self):
        if self.is_empty(): return 0.0
        return self._recursive_max([r.get_temp() for r in self.__readings])

    def min_temp(self):
        if self.is_empty(): return 0.0
        return self._recursive_min([r.get_temp() for r in self.__readings])

    def total_rainfall(self):
        if self.is_empty(): return 0.0
        return round(self._recursive_sum([r.get_rain() for r in self.__readings]), 1)

    def avg_humidity(self):
        if self.is_empty(): return 0.0
        vals = [r.get_humidity() for r in self.__readings]
        return round(self._recursive_sum(vals) / len(vals), 1)

    def peak_wind(self):
        if self.is_empty(): return 0.0
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
        return [r for r in self.__readings if r.get_rain() > RAINFALL_HEAVY]

    def days_above_temp(self, threshold):
        return [r for r in self.__readings if r.get_temp() >= threshold]

    def worst_day(self):
        if self.is_empty(): return None
        return max(self.__readings, key=lambda r: r.get_temp())


class WeatherStation:

    def __init__(self, station_id, location):
        self.station_id = station_id
        self.location   = location
        self.dataset    = WeatherDataset()

    def add_reading(self, reading):
        self.dataset.add(reading)

    def has_readings(self):
        return not self.dataset.is_empty()

    def get_reading_for_day(self, day):
        return self.dataset.get_for_day(day)

    def view_day(self, day, full=True):
        reading = self.dataset.get_for_day(day)
        if not reading:
            print(f"\n  ❌ No data for {day}")
            return
        if full:
            reading.status_report()
        else:
            print(reading.get_summary())


class StationNetwork:

    def __init__(self, name):
        self.__name     = name
        self.__stations = {}

    def add_station(self, station):
        self.__stations[station.station_id] = station

    def get_station(self, sid):
        return self.__stations.get(sid)

    def all_stations(self):
        return list(self.__stations.values())

    def network_summary(self):
        print(f"\n  {'='*56}")
        print(f"  STATION NETWORK — {self.__name}")
        print(f"  Stations : {len(self.__stations)}")
        print(f"  {'='*56}")
        for st in self.__stations.values():
            days = st.dataset.count()
            info = f"{days} day(s) recorded" if days else "No data yet"
            print(f"  📡 {st.station_id:<14} | {st.location:<28} | {info}")
        print(f"  {'='*56}")

    def hottest_across_network(self):
        all_r = []
        for st in self.__stations.values():
            all_r.extend(st.dataset.get_all())
        return max(all_r, key=lambda r: r.get_temp()) if all_r else None

    def total_critical_days(self):
        return sum(len(st.dataset.critical_days()) for st in self.__stations.values())

WEEKLY_SIMULATION = [
    ["Monday",      32.5,  78.0,   4.2, 18.5,  55],
    ["Tuesday",     34.1,  72.0,   0.0, 22.0,  60],
    ["Wednesday",   29.8,  85.0,  18.5, 10.0,  48],
    ["Thursday",    38.2,  60.0,   0.0, 30.5,  72],
    ["Friday",      31.0,  75.0,   7.3, 14.0,  50],
    ["Saturday",    27.5,  90.0,  32.1,  8.0,  42],
    ["Sunday",      30.2,  68.0,   2.0, 19.0,  58],
]
def get_float(prompt, lo, hi):
    while True:
        try:
            v = float(input(f"  {prompt}"))
            if lo <= v <= hi: return v
        except ValueError: pass
        print(f"  ❌ Enter a number between {lo} and {hi}")

def get_int(prompt, lo, hi):
    while True:
        try:
            v = int(input(f"  {prompt}"))
            if lo <= v <= hi: return v
        except ValueError: pass
        print(f"  ❌ Enter a whole number between {lo} and {hi}")

def collect_one_day(day):
    print(f"\n  --- Weather data for {day} ---")
    temp     = get_float("Temperature °C  [-50 to 60]  : ", -50,   60)
    humidity = get_float("Humidity %      [0 to 100]   : ",   0,  100)
    rainfall = get_float("Rainfall mm     [0 or more]  : ",   0, 9999)
    wind     = get_float("Wind speed km/h [0 or more]  : ",   0, 9999)
    aqi      = get_int(  "AQI             [0 to 500]   : ",   0,  500)
    return FarmerAlert(day, temp, humidity, rainfall, wind, aqi, validate=True)

def run_weekly_simulation(station):
    print(f"\n  {'='*70}")
    print(f"  7-DAY SIMULATION — Station: {station.station_id}")
    print(f"  {'='*70}")

    station.dataset = WeatherDataset()
    for row in WEEKLY_SIMULATION:
        r = FarmerAlert(row[0], row[1], row[2], row[3],
                        row[4], row[5], validate=False)
        station.add_reading(r)
        print(r.get_summary())

    print(f"\n  ✅ {len(WEEKLY_SIMULATION)} days simulated.")
    print("  Go to View Summary → Full week to see all alerts per day.")


def enter_live_data(station):
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
            for i, d in enumerate(VALID_DAYS, 1): print(f"  {i}. {d}")
            while True:
                try:
                    idx = int(input("\n  Day number (1–7): "))
                    if 1 <= idx <= 7: break
                except ValueError: pass
                print("  ❌ Enter 1–7")

            selected = VALID_DAYS[idx - 1]
            existing = station.get_reading_for_day(selected)
            if existing:
                print(f"\n  A reading for {selected} already exists.")
                if input("  Overwrite? (Y/N): ").upper().strip() == "Y":
                    station.dataset.remove_day(selected)
                else:
                    print("  Keeping existing reading.")
                    return

            reading = collect_one_day(selected)
            station.add_reading(reading)
            print(f"\n  ✅ {selected} recorded.")
            reading.status_report()

        case "B":
            station.dataset = WeatherDataset()
            for day in VALID_DAYS:
                reading = collect_one_day(day)
                station.add_reading(reading)
                print(f"  ✅ {day} saved.\n")
            print("  ✅ Full week recorded.")
            print_weekly_summary(station)

        case "C":
            print("  ↩  Back.")

        case _:
            print("  ❌ Invalid")


def view_summary_menu(station):
    if not station.has_readings():
        print("\n  ⚠️  No data yet — run simulation or enter live data first.")
        return

    print(f"\n  {'─'*44}")
    print("  A. Single day — full report + alerts")
    print("  B. Single day — alerts only")
    print("  C. Full week summary + all alerts")
    print("  D. Back")
    choice = input("\n  Select (A/B/C/D): ").upper().strip()

    match choice:
        case "A": _pick_day(station, mode="full")
        case "B": _pick_day(station, mode="alerts")
        case "C": print_weekly_summary(station)
        case "D": print("  ↩  Back.")
        case _:   print("  ❌ Invalid")


def _pick_day(station, mode):
    available = [r.get_day() for r in station.dataset.get_all()]
    for i, d in enumerate(available, 1): print(f"  {i}. {d}")
    while True:
        try:
            idx = int(input(f"\n  Select (1–{len(available)}): "))
            if 1 <= idx <= len(available): break
        except ValueError: pass
        print("  ❌ Invalid")
    reading = station.dataset.get_for_day(available[idx - 1])
    if mode == "full":
        reading.status_report()
    elif mode == "alerts" and isinstance(reading, FarmerAlert):
        reading.print_farmer_alerts()
    else:
        reading.status_report()


def print_weekly_summary(station):
    if not station.has_readings():
        print("\n  ⚠️  No data yet.")
        return

    ds = station.dataset
    total_rain = ds.total_rainfall()
    avg_rain   = round(total_rain / ds.count(), 1)

    print(f"\n  {'='*56}")
    print(f"  WEEKLY SUMMARY — {station.station_id} | {station.location}")
    print(f"  Days recorded : {ds.count()}")
    print(f"  {'='*56}")

    print(f"\n  🌡️  TEMPERATURE (recursive stats)")
    print(f"     Average  : {ds.avg_temp()}°C")
    print(f"     Peak     : {ds.max_temp()}°C")
    print(f"     Lowest   : {ds.min_temp()}°C")

    print(f"\n  💧 HUMIDITY")
    print(f"     Average  : {ds.avg_humidity()}%")

    print(f"\n  🌧️  RAINFALL")
    print(f"     Total    : {total_rain} mm")
    print(f"     Daily avg: {avg_rain} mm/day")
    print(f"     Dry days : {len(ds.dry_days())}")
    print(f"     Flood risk days: {len(ds.flood_days())}")

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
        print(f"     {r.get_day()}")

    worst = ds.worst_day()
    if worst:
        print(f"\n  🌡️  WORST DAY : {worst.get_day()} — {worst.get_temp()}°C")

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
    elif total_rain > RAINFALL_HEAVY * 3:
        print("  ⚠️  Very wet week — waterlogging risk")
        print("  ➡️  Inspect drainage channels urgently")
        print("  ➡️  Delay fertilizer — nutrients will leach out")
    else:
        print("  ✅ Conditions generally favourable this week")
        print("  ➡️  Continue normal farm operations")

    if ds.max_temp() >= TEMP_HEATWAVE:
        print(f"  🔥 Heat stress peak: {ds.max_temp()}°C — review irrigation schedule")
    if ds.peak_aqi() >= AQI_MODERATE:
        print(f"  😷 Air quality concern — peak AQI {ds.peak_aqi()} this week")
    print(f"  {'='*56}")


def dataset_analysis_menu(station):
    if not station.has_readings():
        print("\n  ⚠️  No data yet.")
        return

    ds = station.dataset
    while True:
        print(f"\n  {'─'*44}")
        print("  DATASET ANALYSIS  (M3)")
        print(f"  {'─'*44}")
        print("  A. Recursive statistics")
        print("  B. Sort by temperature")
        print("  C. Sort by rainfall")
        print("  D. Critical days")
        print("  E. Days above a temperature")
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
                for r in ds.sorted_by_temp(): print(r.get_summary())

            case "C":
                print("\n  Wettest → Driest:")
                for r in ds.sorted_by_rain(): print(r.get_summary())

            case "D":
                crit = ds.critical_days()
                if crit:
                    print(f"\n  {len(crit)} critical day(s):")
                    for r in crit: print(r.get_summary())
                else:
                    print("\n  ✅ No critical days this week.")

            case "E":
                t = get_float("Threshold °C: ", -50, 60)
                res = ds.days_above_temp(t)
                if res:
                    for r in res: print(r.get_summary())
                else:
                    print(f"  No days exceeded {t}°C.")

            case "F":
                break

            case _:
                print("  ❌ Invalid")


def select_station(network):
    stations = network.all_stations()
    print(f"\n  Select a station:")
    for i, st in enumerate(stations, 1):
        print(f"  {i}. {st.station_id} — {st.location}")
    while True:
        try:
            idx = int(input(f"\n  Station number (1–{len(stations)}): "))
            if 1 <= idx <= len(stations):
                return stations[idx - 1]
        except ValueError:
            pass
        print(f"  ❌ Enter a number between 1 and {len(stations)}")


def network_menu(network):
    while True:
        print(f"\n  {'─'*44}")
        print("  STATION NETWORK  (M3)")
        print(f"  {'─'*44}")
        print("  A. All stations overview")
        print("  B. Enter data for any station")
        print("  C. Hottest reading across network")
        print("  D. Total critical days across network")
        print("  E. Back")
        choice = input("\n  Select (A–E): ").upper().strip()
        match choice:
            case "A":
                network.network_summary()

            case "B":
                st = select_station(network)
                print(f"\n  {'─'*44}")
                print(f"  Entering data for: {st.station_id} — {st.location}")
                print(f"  {'─'*44}")
                print("  A. Run 7-day simulation for this station")
                print("  B. Enter a single day manually")
                sub = input("\n  Select (A/B): ").upper().strip()
                if sub == "A":
                    st.dataset = WeatherDataset()
                    for row in WEEKLY_SIMULATION:
                        r = FarmerAlert(row[0], row[1], row[2], row[3],
                                        row[4], row[5], validate=False)
                        st.add_reading(r)
                        print(r.get_summary())
                    print(f"\n  ✅ Simulation loaded into {st.station_id}")
                elif sub == "B":
                    print("\n  Select a day:")
                    for i, d in enumerate(VALID_DAYS, 1):
                        print(f"  {i}. {d}")
                    while True:
                        try:
                            idx = int(input("\n  Day number (1–7): "))
                            if 1 <= idx <= 7: break
                        except ValueError: pass
                        print("  ❌ Enter 1–7")
                    selected = VALID_DAYS[idx - 1]
                    existing = st.get_reading_for_day(selected)
                    if existing:
                        print(f"\n  A reading for {selected} already exists.")
                        if input("  Overwrite? (Y/N): ").upper().strip() == "Y":
                            st.dataset.remove_day(selected)
                        else:
                            print("  Keeping existing.")
                            continue
                    reading = collect_one_day(selected)
                    st.add_reading(reading)
                    print(f"\n  ✅ {selected} recorded into {st.station_id}")
                else:
                    print("  ❌ Invalid")

            case "C":
                h = network.hottest_across_network()
                if h:
                    print(f"\n  🔥 Hottest across network:")
                    print(f"  {h.get_summary()}")
                else:
                    print("\n  ⚠️  No data in network yet — enter data via option B first.")

            case "D":
                total = network.total_critical_days()
                print(f"\n  Total critical days across all stations: {total}")
                if total == 0:
                    print("  (No critical conditions recorded, or no data entered yet)")

            case "E":
                break

            case _:
                print("  ❌ Invalid")

def main():
    print("=" * 60)
    print(f"  Station  : KE-NBI-001")
    print(f"  Location : JKUAT Main Farm, Juja")
    print("=" * 60)

    station = WeatherStation("KE-NBI-001", "JKUAT Main Farm, Juja")
    network = StationNetwork("JKUAT Farm Grid")
    network.add_station(station)
    network.add_station(WeatherStation("KE-NBI-002", "JKUAT Greenhouse Block"))
    network.add_station(WeatherStation("KE-NBI-003", "JKUAT Livestock Zone"))

    while True:
        print("\n  ┌──────────────────────────────────────────────┐")
        print("  │                 MAIN MENU                    │")
        print("  ├──────────────────────────────────────────────┤")
        print("  │  1. Run 7-Day Simulation                     │")
        print("  │  2. Enter Live Data                          │")
        print("  │  3. View Summary & Alerts                    │")
        print("  │  4. Dataset Analysis                         │")
        print("  │  5. Station Network                          │")
        print("  │  6. Exit                                     │")
        print("  └──────────────────────────────────────────────┘")

        choice = input("\n  Select (1–6): ").strip()

        match choice:
            case "1": run_weekly_simulation(station)
            case "2": enter_live_data(station)
            case "3": view_summary_menu(station)
            case "4": dataset_analysis_menu(station)
            case "5": network_menu(network)
            case "6":
                print("\n  Shutting down JKUAT Weather System...")
                print("  ─────────────────────────────────────────────")
                print("=" * 60)
                break
            case _:
                print("  ❌ Invalid — enter 1 through 6")

if __name__ == "__main__":
    main()