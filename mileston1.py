
SYSTEM_NAME = "JKUAT Weather & Environmental Data System"
LOCATION    = "JKUAT Main Farm, Juja"

print("=" * 60)
print(f"{SYSTEM_NAME}")
print(f"Location: {LOCATION}")
print("=" * 60)

temperature    = 32.5   
humidity       = 78.0  
rainfall       = 4.2   
wind_speed     = 18.5   
wind_direction = "NE"
day_of_reading = "Monday"

TEMP_HEAT      = 35
TEMP_COLD      = 10
RAINFALL_HEAVY = 25
WIND_STRONG    = 50

def compute_heat_index(temp, hum):
    return temp + (0.33 * (hum / 100) * 6.105) - 4.0

def compute_evapotranspiration(temp, hum):
    return round((0.0023 * (temp + 17.8) * (100 - hum) ** 0.5), 2)

def compute_water_deficit(rain):
    crop_need = 5.0
    return crop_need - rain


heat_index = compute_heat_index(temperature, humidity)
evapo      = compute_evapotranspiration(temperature, humidity)
deficit    = compute_water_deficit(rainfall)

def temperature_status(temp):
    if temp >= TEMP_HEAT:
        return " Heat stress risk — irrigate immediately"
    elif temp >= 20:
        return " Temperature within optimal range"
    else:
        return " Low temperature — possible cold stress"

def rainfall_status(rain):
    if rain == 0:
        return " No rainfall — irrigation required"
    elif rain < 5:
        return " Low rainfall — supplement irrigation"
    elif rain <= RAINFALL_HEAVY:
        return " Adequate rainfall"
    else:
        return " Excess rainfall — flooding risk"

def humidity_status(hum):
    if hum > 85:
        return " High humidity — disease risk"
    elif hum < 30:
        return " Dry air — moisture stress"
    else:
        return " Humidity normal"

def wind_status(wind):
    if wind > WIND_STRONG:
        return " Strong winds — crop damage risk"
    elif wind > 30:
        return " Moderate winds — monitor crops"
    else:
        return " Calm wind conditions"
    
print("\n--- CURRENT WEATHER CONDITIONS ---")
print(f"Day           : {day_of_reading}")
print(f"Temperature   : {temperature} °C")
print(f"Humidity      : {humidity} %")
print(f"Rainfall      : {rainfall} mm")
print(f"Wind          : {wind_speed} km/h ({wind_direction})")

print("\n--- COMPUTED VALUES ---")
print(f"Heat Index            : {heat_index:.1f} °C")
print(f"Evapotranspiration    : {evapo} mm/day")
print(f"Water Deficit         : {deficit:.1f} mm")

print("\n--- SYSTEM ADVISORY ---")
print(temperature_status(temperature))
print(rainfall_status(rainfall))
print(humidity_status(humidity))
print(wind_status(wind_speed))

weekly_data = [
    ["Monday",    32.5, 78.0,  4.2],
    ["Tuesday",   34.1, 72.0,  0.0],
    ["Wednesday", 29.8, 85.0, 18.5],
    ["Thursday",  38.2, 60.0,  0.0],
    ["Friday",    31.0, 75.0,  7.3],
    ["Saturday",  27.5, 90.0, 32.1],
    ["Sunday",    30.2, 68.0,  2.0],
]

print("\n" + "=" * 60)
print("7-DAY WEATHER SIMULATION")
print("=" * 60)

total_rain = 0
total_temp = 0

for day, temp, hum, rain in weekly_data:
    total_rain += rain
    total_temp += temp

    if rain == 0 and temp > 33:
        status = " Drought Risk"
    elif rain > 25:
        status = " Flood Risk"
    elif temp > 35:
        status = " Heat Stress"
    elif hum > 85:
        status = " Disease Risk"
    else:
        status = " Normal"

    print(f"{day:<10} | {temp:>5}°C | {hum:>5}% | {rain:>5}mm | {status}")

avg_temp = total_temp / len(weekly_data)
avg_rain = total_rain / len(weekly_data)

print("\n--- WEEKLY SUMMARY ---")
print(f"Total Rainfall      : {total_rain:.1f} mm")
print(f"Average Temperature : {avg_temp:.1f} °C")
print(f"Average Rainfall    : {avg_rain:.1f} mm/day")

print("\n--- FINAL ADVISORY ---")
if avg_rain < 3:
    print("⚠️ Dry week — Draught detected")
    print("➡️  Recommend activating irrigation system for next week.")
elif avg_rain > 20:
    print("⚠️ Wet week — High rainfall detected")
    print("➡️  Inspect drainage and delay fertilizer application.")
else:
    print("✅ Conditions generally favorable")
    print("➡️  Continue normal farm operations.")