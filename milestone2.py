
TEMP_HEATWAVE      = 35.0 ;  WIND_STRONG        = 50.0  
TEMP_OPTIMAL_LOW   = 20.0 ;  WIND_MODERATE      = 30.0 
TEMP_COLD          = 10.0 ;  HUMIDITY_DISEASE   = 85.0  
RAINFALL_CROP_NEED = 5.0  ;  HUMIDITY_DRY       = 30.0  
RAINFALL_LOW       = 2.0  ;  AQI_UNHEALTHY      = 150 
RAINFALL_HEAVY     = 25.0 ;  AQI_MODERATE       = 100   

VALID_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
              "Friday", "Saturday", "Sunday"]

class WeatherReading:
    def __init__(self, day, temperature, humidity,
                 rainfall, wind_speed, wind_direction, aqi,
                 validate=True):

        if validate:
            self.__day        = day
            self.__temp       = self._validate_temp(temperature)
            self.__humidity   = self._validate_humidity(humidity)
            self.__rainfall   = self._validate_rain(rainfall)
            self.__wind_speed = self._validate_wind(wind_speed)
            self.__wind_dir   = wind_direction
            self.__aqi        = self._validate_aqi(aqi)
        else:
            self.__day        = day
            self.__temp       = temperature
            self.__humidity   = humidity
            self.__rainfall   = rainfall
            self.__wind_speed = wind_speed
            self.__wind_dir   = wind_direction
            self.__aqi        = aqi

        self.__heat_index    = self._compute_heat_index()
        self.__evap          = self._compute_evapotranspiration()
        self.__dew_point     = self._compute_dew_point()
        self.__kelvin        = round(self.__temp + 273.15, 2)
        self.__water_deficit = max(0.0, RAINFALL_CROP_NEED - self.__rainfall)
  
    def _validate_temp(self, temp):
        if not (-50 <= temp <= 60):
            raise ValueError(f"Temperature out of range: {temp}")
        return temp

    def _validate_humidity(self, hum):
        if not (0 <= hum <= 100):
            raise ValueError(f"Humidity out of range: {hum}")
        return hum

    def _validate_rain(self, rain):
        if rain < 0:
            raise ValueError(f"Rainfall cannot be negative: {rain}")
        return rain

    def _validate_wind(self, wind):
        if wind < 0:
            raise ValueError(f"Wind speed cannot be negative: {wind}")
        return wind

    def _validate_aqi(self, aqi):
        if not (0 <= aqi <= 500):
            raise ValueError(f"AQI out of range: {aqi}")
        return aqi
  
    def _compute_heat_index(self):
        return round(self.__temp + (0.33 * (self.__humidity / 100) * 6.105) - 4.0, 1)

    def _compute_evapotranspiration(self):
        return round((0.0023 * (self.__temp + 17.8) * (100 - self.__humidity) ** 0.5), 2)

    def _compute_dew_point(self):
        a, b  = 17.27, 237.7
        gamma = ((a * self.__temp) / (b + self.__temp)) + (self.__humidity / 100.0)
        return round((b * gamma) / (a - gamma), 2)

    def get_day(self):           return self.__day
    def get_temp(self):          return self.__temp
    def get_humidity(self):      return self.__humidity
    def get_rain(self):          return self.__rainfall
    def get_wind(self):          return self.__wind_speed
    def get_wind_dir(self):      return self.__wind_dir
    def get_aqi(self):           return self.__aqi
    def get_heat_index(self):    return self.__heat_index
    def get_evap(self):          return self.__evap
    def get_dew_point(self):     return self.__dew_point
    def get_kelvin(self):        return self.__kelvin
    def get_water_deficit(self): return self.__water_deficit

    def temperature_status(self):
        if self.__temp >= TEMP_HEATWAVE:
            return " CRITICAL : Heat stress risk — irrigate immediately"
        elif self.__temp >= TEMP_OPTIMAL_LOW:
            return " OK       : Temperature within optimal crop range"
        elif self.__temp <= TEMP_COLD:
            return " WARNING  : Cold stress — cover seedlings tonight"
        else:
            return " NOTICE   : Below optimal — monitor crops"

    def rainfall_status(self):
        if self.__rainfall == 0:
            return " ALERT    : No rainfall — full irrigation required"
        elif self.__rainfall < RAINFALL_LOW:
            return f" LOW      : {self.__rainfall}mm — partial irrigation needed"
        elif self.__rainfall < RAINFALL_CROP_NEED:
            return f" NOTICE   : {self.__rainfall}mm — below daily crop requirement"
        elif self.__rainfall <= RAINFALL_HEAVY:
            return " OK       : Adequate rainfall for crops today"
        else:
            return " CRITICAL : Excess rainfall — flooding risk, check drainage"

    def humidity_status(self):
        if self.__humidity > HUMIDITY_DISEASE:
            return " WARNING  : High humidity — fungal/blight disease risk"
        elif self.__humidity < HUMIDITY_DRY:
            return " WARNING  : Low humidity — crop moisture stress likely"
        else:
            return " OK       : Humidity within acceptable range"

    def wind_status(self):
        if self.__wind_speed > WIND_STRONG:
            return " CRITICAL : Strong winds — structural crop damage risk"
        elif self.__wind_speed > WIND_MODERATE:
            return " WARNING  : Moderate winds — lodging risk for maize/sorghum"
        else:
            return " OK       : Calm wind conditions"

    def air_quality_status(self):
        if self.__aqi >= AQI_UNHEALTHY:
            return " CRITICAL : Unhealthy air — limit farm worker exposure"
        elif self.__aqi >= AQI_MODERATE:
            return " MODERATE : Elevated AQI — sensitive groups take caution"
        else:
            return " OK       : Air quality acceptable for farm operations"

    def get_overall_status(self):
        all_checks = [
            self.temperature_status(), self.rainfall_status(),
            self.humidity_status(),    self.wind_status(),
            self.air_quality_status(),
        ]
        if any("CRITICAL" in c for c in all_checks): return " CRITICAL"
        if any("WARNING"  in c or "ALERT" in c for c in all_checks): return " WARNING"
        return " NORMAL"

    def run_alerts(self):
        print(f"\n  {'='*54}")
        print(f"  ALERT REPORT — {self.__day}")
        print(f"  {'='*54}")
        print(f"  {self.temperature_status()}")
        print(f"  {self.rainfall_status()}")
        print(f"  {self.humidity_status()}")
        print(f"  {self.wind_status()}")
        print(f"  {self.air_quality_status()}")
        print(f"\n  📋 OVERALL  : {self.get_overall_status()}")
        if self.__water_deficit > 0:
            print(f"  💧 DEFICIT  : {self.__water_deficit:.1f}mm irrigation gap today")
        print(f"  {'='*54}")

    def full_report(self):
        print(f"\n  {'='*54}")
        print(f"  FULL WEATHER REPORT — {self.__day}")
        print(f"  {'='*54}")
        print(f"   Temperature      : {self.__temp}°C  ({self.__kelvin}K)")
        print(f"   Humidity         : {self.__humidity}%")
        print(f"   Rainfall         : {self.__rainfall} mm")
        print(f"   Wind             : {self.__wind_speed} km/h ({self.__wind_dir})")
        print(f"  🌫️  Air Quality(AQI) : {self.__aqi}")
        print(f"  {'─'*44}")
        print(f"   Heat Index       : {self.__heat_index}°C (feels like)")
        print(f"   Evapotransp.     : {self.__evap} mm/day")
        print(f"   Dew Point        : {self.__dew_point}°C")
        print(f"   Water Deficit    : {self.__water_deficit:.1f} mm")
        self.run_alerts()

    def __str__(self):
        deficit = f"Deficit:{self.__water_deficit:.1f}mm" \
                  if self.__water_deficit > 0 else "Water:OK"
        return (f"  {self.__day:<12} | "
                f"Temp:{self.__temp}°C | "
                f"Humid:{self.__humidity}% | "
                f"Rain:{self.__rainfall}mm | "
                f"Wind:{self.__wind_speed}km/h {self.__wind_dir:<2} | "
                f"AQI:{self.__aqi} | "
                f"{deficit} | "
                f"{self.get_overall_status()}")

class WeatherStation:

    def __init__(self, station_id, location):
        self.station_id = station_id
        self.location   = location
        self.readings   = []         

    def add_reading(self, reading):
        self.readings.append(reading)

    def get_reading_for_day(self, day):
        """Returns the WeatherReading object for a specific day, or None"""
        for r in self.readings:
            if r.get_day().lower() == day.lower():
                return r
        return None

    def has_readings(self):
        return len(self.readings) > 0

def collect_one_day_input(day_label):
    print(f"\n  --- Entering data for {day_label} ---")

    while True:
        try:
            temp = float(input(f"  Temperature °C [-50 to 60]  : "))
            if -50 <= temp <= 60: break
        except ValueError: pass
        print("  ❌ Invalid — enter a number e.g. 32.5")

    while True:
        try:
            hum = float(input(f"  Humidity %    [0 to 100]    : "))
            if 0 <= hum <= 100: break
        except ValueError: pass
        print("  ❌ Invalid — enter a number e.g. 78.0")

    while True:
        try:
            rain = float(input(f"  Rainfall mm   [0 or more]   : "))
            if rain >= 0: break
        except ValueError: pass
        print("  ❌ Invalid — cannot be negative")

    while True:
        try:
            wind = float(input(f"  Wind speed km/h [0 or more] : "))
            if wind >= 0: break
        except ValueError: pass
        print("  ❌ Invalid — cannot be negative")

    valid_dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    while True:
        wind_dir = input(f"  Wind direction {valid_dirs}: ").upper().strip()
        if wind_dir in valid_dirs: break
        print(f"  ❌ Invalid — choose from {valid_dirs}")

    while True:
        try:
            aqi = int(input(f"  AQI           [0 to 500]    : "))
            if 0 <= aqi <= 500: break
        except ValueError: pass
        print("  ❌ Invalid — whole number between 0 and 500")

    return WeatherReading(day_label, temp, hum, rain, wind, wind_dir, aqi,
                          validate=True)

def run_weekly_simulation(station):
    print(f"\n  {'='*70}")
    print(f"  7-DAY SIMULATION — Station: {station.station_id}")
    print(f"  Location: {station.location}")
    print(f"  {'='*70}")

    weekly_data = [
        ["Monday",    32.5, 78.0,  4.2, 18.5, "NE", 55],
        ["Tuesday",   34.1, 72.0,  0.0, 22.0, "N",  60],
        ["Wednesday", 29.8, 85.0, 18.5, 10.0, "SE", 48],
        ["Thursday",  38.2, 60.0,  0.0, 30.5, "NW", 72],
        ["Friday",    31.0, 75.0,  7.3, 14.0, "NE", 50],
        ["Saturday",  27.5, 90.0, 32.1,  8.0, "E",  42],
        ["Sunday",    30.2, 68.0,  2.0, 19.0, "N",  58],]
   
    # simulation readings before adding new ones
    station.readings.clear()
    for row in weekly_data:
        reading = WeatherReading(
            row[0], row[1], row[2], row[3], row[4], row[5], row[6],
            validate=False
        )
        station.add_reading(reading)
        print(reading)

    print(f"\n  {len(weekly_data)} daily readings recorded into station.")

def enter_live_data(station):
    print(f"\n  {'='*54}")
    print(f"  LIVE DATA ENTRY — Station: {station.station_id}")
    print(f"  {'='*54}")
    print("  How would you like to enter data?\n")
    print("  ┌──────────────────────────────────────┐")
    print("  │  A. Enter a single day reading       │")
    print("  │  B. Enter readings for the full week │")
    print("  │  C. Back to main menu                │")
    print("  └──────────────────────────────────────┘")

    choice = input("\n  Select option (A/B/C): ").upper().strip()
    match choice:
        
        case "A":
            print(f"\n  Select a day:")
            for i, day in enumerate(VALID_DAYS, 1):
                print(f"  {i}. {day}")

            while True:
                try:
                    day_choice = int(input("\n  Enter day number (1–7): "))
                    if 1 <= day_choice <= 7: break
                except ValueError: pass
                print("  ❌ Invalid — enter a number between 1 and 7")

            selected_day = VALID_DAYS[day_choice - 1]

            existing = station.get_reading_for_day(selected_day)
            if existing:
                print(f"\n    A reading for {selected_day} already exists.")
                overwrite = input("  Overwrite it? (Y/N): ").upper().strip()
                if overwrite == "Y":
                    station.readings.remove(existing)
                else:
                    print("    Keeping existing reading. Returning to menu.")
                    return

            reading = collect_one_day_input(selected_day)
            station.add_reading(reading)
            print(f"\n   {selected_day} reading recorded successfully.")
         
            reading.full_report()
 
        case "B":
            print(f"\n  You will now enter readings for all 7 days.")
            print(f"  Follow the prompts for each day.\n")

            station.readings.clear()

            for day in VALID_DAYS:
                reading = collect_one_day_input(day)
                station.add_reading(reading)
                print(f"   {day} saved.\n")

            print(f"\n   All 7 days recorded successfully.")

            print_weekly_summary(station)

        case "C":
            print("  ↩  Returning to main menu.")

        case _:
            print("  ❌ Invalid — please enter A, B, or C")

def view_summary(station):
    if not station.has_readings():
        print("\n    No data yet — run simulation or enter live data first.")
        return

    print(f"\n  {'='*54}")
    print(f"  SUMMARY — Station: {station.station_id}")
    print(f"  {'='*54}")
    print("  What would you like to view?\n")
    print("  ┌──────────────────────────────────────┐")
    print("  │  A. Summary for a single day         │")
    print("  │  B. Summary for the full week        │")
    print("  │  C. Back to main menu                │")
    print("  └──────────────────────────────────────┘")

    choice = input("\n  Select option (A/B/C): ").upper().strip()
    match choice:

        case "A":

            available = [r.get_day() for r in station.readings]
            print(f"\n  Days with recorded data:")
            for i, day in enumerate(available, 1):
                print(f"  {i}. {day}")

            while True:
                try:
                    day_choice = int(input(f"\n  Select day number (1–{len(available)}): "))
                    if 1 <= day_choice <= len(available): break
                except ValueError: pass
                print(f"  ❌ Invalid — enter a number between 1 and {len(available)}")

            selected_day = available[day_choice - 1]
            reading = station.get_reading_for_day(selected_day)
            reading.full_report()

        case "B":
            print_weekly_summary(station)

        case "C":
            print("  ↩  Returning to main menu.")

        case _:
            print("   Invalid — please enter A, B, or C")

def print_weekly_summary(station):
    if not station.has_readings():
        print("\n    No data yet.")
        return

    temps    = [r.get_temp()     for r in station.readings]
    humidity = [r.get_humidity() for r in station.readings]
    rain     = [r.get_rain()     for r in station.readings]
    wind     = [r.get_wind()     for r in station.readings]
    aqi      = [r.get_aqi()      for r in station.readings]

    total_rain = sum(rain)
    avg_temp   = sum(temps) / len(temps)
    avg_rain   = total_rain / len(rain)

    critical_days = [r for r in station.readings if "CRITICAL" in r.get_overall_status()]
    drought_days  = [r for r in station.readings if r.get_rain() == 0]
    flood_days    = [r for r in station.readings if r.get_rain() > RAINFALL_HEAVY]

    print(f"\n  {'='*54}")
    print(f"  WEEKLY SUMMARY — Station: {station.station_id}")
    print(f"  Location : {station.location}")
    print(f"  Readings : {len(station.readings)} day(s)")
    print(f"  {'='*54}")
    print(f"\n  🌡️  TEMPERATURE")
    print(f"     Average  : {avg_temp:.1f}°C")
    print(f"     Maximum  : {max(temps)}°C")
    print(f"     Minimum  : {min(temps)}°C")
    print(f"\n  💧 HUMIDITY")
    print(f"     Average  : {sum(humidity)/len(humidity):.1f}%")
    print(f"     Maximum  : {max(humidity)}%")
    print(f"     Minimum  : {min(humidity)}%")
    print(f"\n  🌧️  RAINFALL")
    print(f"     Total        : {total_rain:.1f} mm")
    print(f"     Daily Avg    : {avg_rain:.1f} mm/day")
    print(f"     Peak Day     : {max(rain):.1f} mm")
    print(f"     Dry Days     : {len(drought_days)}")
    print(f"\n  💨 WIND")
    print(f"     Average  : {sum(wind)/len(wind):.1f} km/h")
    print(f"     Peak     : {max(wind)} km/h")
    print(f"\n  🌫️  AIR QUALITY (AQI)")
    print(f"     Average  : {sum(aqi)/len(aqi):.0f}")
    print(f"     Peak     : {max(aqi)}")
    print(f"\n  ⚠️  ALERT SUMMARY")
    print(f"     Critical Days : {len(critical_days)}")
    print(f"     Drought Days  : {len(drought_days)}")
    print(f"     Flood Days    : {len(flood_days)}")

    worst = max(station.readings, key=lambda r: r.get_temp())
    print(f"\n   WORST DAY : {worst.get_day()} ({worst.get_temp()}°C)")

    print(f"\n  --- FINAL ADVISORY ---")
    if avg_rain < 3:
        print("  ⚠️  Dry week — drought conditions detected")
        print("  ➡️  Recommend activating irrigation for next week.")
    elif total_rain > RAINFALL_HEAVY * 3:
        print("  ⚠️  Wet week — high cumulative rainfall")
        print("  ➡️  Inspect drainage and delay fertilizer application.")
    else:
        print("  ✅ Conditions generally favourable this week.")
        print("  ➡️  Continue normal farm operations.")

    if max(temps) >= TEMP_HEATWAVE:
        print(f"   Peak temp {max(temps)}°C — heat stress risk identified.")
    if max(aqi) >= AQI_MODERATE:
        print(f"   Peak AQI {max(aqi)} — monitor farm worker health.")

    print(f"  {'='*54}")

def main():
    print("=" * 60)
    print("  JKUAT Weather & Environmental Data System")
    print("  Version  : 2.0  |  Milestone 2")
    print("  Station  : KE-NBI-001")
    print("  Location : JKUAT Main Farm, Juja")
    print("=" * 60)

    station = WeatherStation("KE-NBI-001", "JKUAT Main Farm, Juja")

    while True:
        print("\n  ┌──────────────────────────────────────┐")
        print("  │            MAIN MENU                 │")
        print("  ├──────────────────────────────────────┤")
        print("  │  1. Run 7-Day Simulation             │")
        print("  │  2. Enter Live Data                  │")
        print("  │  3. View Summary                     │")
        print("  │  4. Exit System                      │")
        print("  └──────────────────────────────────────┘")

        choice = input("\n  Select option (1–4): ").strip()

        match choice:
            case "1":
                run_weekly_simulation(station)
            case "2":
                enter_live_data(station)      
            case "3":
                view_summary(station)        
            case "4":
                print("\n  Shutting down JKUAT Weather System...")
                print("  ─────────────────────────────────────────")
                print("  END OF MILESTONE 2")
                print("  Control Logic & Object Introduction ")
                print("  Next → Milestone 3: Data Structures & Full OOP")
                print("=" * 60)
                break
            case _:
                print("  ❌ Invalid — please enter 1, 2, 3 or 4")


if __name__ == "__main__":
    main()