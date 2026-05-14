package jkuat.weather.models;

import jkuat.weather.enums.AlertLevel;
import jkuat.weather.exceptions.ValidationException;
import jkuat.weather.utils.Cfg;

public class WeatherModels {

// ============================================================
//  ABSTRACT BASE — EnvironmentalReading
// ============================================================
/**
 * EnvironmentalReading — abstract base for all sensor/weather data objects.
 *
 * Enforces:
 *   • day validation against Cfg.VALID_DAYS
 *   • getSummary(), getOverallStatus(), getAlertLevel() contract
 *
 * Subclasses: WeatherReading → FarmerAlert
 */
public static abstract class EnvironmentalReading {

    protected final String day;

    protected EnvironmentalReading(String day) {
        if (!Cfg.VALID_DAYS.contains(day))
            throw new ValidationException("Invalid day: " + day);
        this.day = day;
    }

    public String     getDay()          { return day; }
    public abstract String getSummary();
    public abstract String getOverallStatus();
    public abstract AlertLevel getAlertLevel();
}


// ============================================================
//  CONCRETE — WeatherReading
// ============================================================
/**
 * WeatherReading — validated weather observation with derived agro-metrics.
 *
 * Derived metrics (computed in constructor, stored as final fields):
 *   heatIndex    — apparent temperature felt by crops/workers
 *   evap         — reference evapotranspiration (Hargreaves approx.)
 *   dewPoint     — Magnus formula dew point
 *   waterDeficit — mm gap between actual rain and crop daily need
 *   kelvin       — temperature in Kelvin (used in thermodynamic displays)
 */
public static class WeatherReading extends EnvironmentalReading {

    private final double temp, humidity, rainfall, windSpeed;
    private final String windDir;
    private final int    aqi;

    // Derived — computed once at construction time
    private final double heatIndex, evap, dewPoint, waterDeficit, kelvin;

    public WeatherReading(String day, double temp, double humidity,
                          double rainfall, double windSpeed,
                          String windDir, int aqi) {
        super(day);
        this.temp      = checkRange("Temperature", temp,     -50,  60);
        this.humidity  = checkRange("Humidity",    humidity,   0, 100);
        this.rainfall  = checkNonNeg("Rainfall",   rainfall);
        this.windSpeed = checkNonNeg("Wind Speed",  windSpeed);
        this.windDir   = windDir;
        this.aqi       = (int) checkRange("AQI", aqi, 0, 500);

        // Derived metrics
        this.heatIndex   = rd(temp + (0.33 * (humidity / 100) * 6.105) - 4.0);
        this.evap        = rd(0.0023 * (temp + 17.8) * Math.pow(100 - humidity, 0.5));
        double a = 17.27, b = 237.7, g = (a * temp) / (b + temp) + (humidity / 100.0);
        this.dewPoint    = rd((b * g) / (a - g));
        this.waterDeficit = Math.max(0, Cfg.RAINFALL_CROP_NEED - rainfall);
        this.kelvin      = rd(temp + 273.15);
    }

    // ── Validation helpers ───────────────────────────────────────────────────
    private double checkRange(String name, double v, double lo, double hi) {
        if (v < lo || v > hi)
            throw new ValidationException(name + " " + v + " out of range [" + lo + "–" + hi + "]");
        return v;
    }
    private double checkNonNeg(String name, double v) {
        if (v < 0) throw new ValidationException(name + " cannot be negative: " + v);
        return v;
    }
    private double rd(double v) { return Math.round(v * 100.0) / 100.0; }

    // ── Field accessors ──────────────────────────────────────────────────────
    public double getTemp()         { return temp; }
    public double getHumidity()     { return humidity; }
    public double getRainfall()     { return rainfall; }
    public double getWindSpeed()    { return windSpeed; }
    public String getWindDir()      { return windDir; }
    public int    getAqi()          { return aqi; }
    public double getHeatIndex()    { return heatIndex; }
    public double getEvap()         { return evap; }
    public double getDewPoint()     { return dewPoint; }
    public double getWaterDeficit() { return waterDeficit; }
    public double getKelvin()       { return kelvin; }

    // ── Agronomic status strings ─────────────────────────────────────────────
    public String tempStatus() {
        if (temp >= Cfg.TEMP_HEATWAVE)    return "CRITICAL: Heat stress — irrigate immediately";
        if (temp >= Cfg.TEMP_OPTIMAL_LOW) return "OK: Temperature within optimal range";
        if (temp <= Cfg.TEMP_COLD)        return "WARNING: Cold stress — cover seedlings";
        return "NOTICE: Below optimal — monitor crops";
    }
    public String rainStatus() {
        if (rainfall == 0)                    return "ALERT: No rainfall — full irrigation required";
        if (rainfall < Cfg.RAINFALL_LOW)      return "LOW: " + rainfall + "mm — partial irrigation";
        if (rainfall < Cfg.RAINFALL_CROP_NEED)return "NOTICE: " + rainfall + "mm — below crop requirement";
        if (rainfall <= Cfg.RAINFALL_HEAVY)   return "OK: Adequate rainfall";
        return "CRITICAL: Excess rainfall — flooding risk";
    }
    public String humidityStatus() {
        if (humidity > Cfg.HUMIDITY_DISEASE) return "WARNING: High humidity — fungal disease risk";
        if (humidity < Cfg.HUMIDITY_DRY)     return "WARNING: Low humidity — moisture stress";
        return "OK: Humidity within acceptable range";
    }
    public String windStatus() {
        if (windSpeed > Cfg.WIND_STRONG)   return "CRITICAL: Strong winds — crop damage risk";
        if (windSpeed > Cfg.WIND_MODERATE) return "WARNING: Moderate winds — lodging risk";
        return "OK: Calm wind conditions";
    }
    public String aqiStatus() {
        if (aqi >= Cfg.AQI_UNHEALTHY) return "CRITICAL: Unhealthy air — limit worker exposure";
        if (aqi >= Cfg.AQI_MODERATE)  return "MODERATE: Elevated AQI — sensitive workers cautious";
        return "OK: Air quality acceptable";
    }

    @Override
    public String getOverallStatus() {
        String all = tempStatus() + rainStatus() + humidityStatus() + windStatus() + aqiStatus();
        if (all.contains("CRITICAL") || all.contains("ALERT")) return "CRITICAL";
        if (all.contains("WARNING"))  return "WARNING";
        return "NORMAL";
    }

    @Override
    public AlertLevel getAlertLevel() {
        return switch (getOverallStatus()) {
            case "CRITICAL" -> AlertLevel.CRITICAL;
            case "WARNING"  -> AlertLevel.WARNING;
            default         -> AlertLevel.NORMAL;
        };
    }

    @Override
    public String getSummary() {
        return String.format("%s | %.1f°C | %.0f%% | %.1fmm | %.1fkm/h %s | AQI:%d | %s",
            day, temp, humidity, rainfall, windSpeed, windDir, aqi, getOverallStatus());
    }
}


// ============================================================
//  SUBCLASS — FarmerAlert  (M3 inheritance demo)
// ============================================================
/**
 * FarmerAlert extends WeatherReading to add plain-English farmer advice.
 *
 * This is the M3 inheritance requirement:
 *   FarmerAlert IS-A WeatherReading (inherits all validation + metrics)
 *   but adds farmerAdvice() — actionable text for farmers, not engineers.
 *
 * All readings created in the system are FarmerAlert instances so that
 * the Summary panel can always call fa.farmerAdvice().
 */
public static class FarmerAlert extends WeatherReading {

    public FarmerAlert(String day, double t, double h, double r,
                       double w, String d, int aqi) {
        super(day, t, h, r, w, d, aqi);
    }

    /**
     * Returns bullet-point advice in plain Swahili/English suitable for
     * display in the Farmer Alerts text area.
     */
    public String farmerAdvice() {
        StringBuilder sb = new StringBuilder();
        if (getTemp()      >= Cfg.TEMP_HEATWAVE)   sb.append("* Dangerously hot. Water crops now.\n");
        if (getRainfall()  == 0)                    sb.append("* No rain today. Switch on irrigation.\n");
        if (getHumidity()  >  Cfg.HUMIDITY_DISEASE) sb.append("* High humidity — check for blight and fungal disease.\n");
        if (getWindSpeed() >  Cfg.WIND_STRONG)      sb.append("* Very strong winds. Stake tall crops urgently.\n");
        if (getAqi()       >= Cfg.AQI_UNHEALTHY)    sb.append("* Poor air quality. Limit outdoor time for farm workers.\n");
        if (getWaterDeficit() > 0)
            sb.append(String.format("* Irrigation gap: %.1fmm short of daily crop need.\n", getWaterDeficit()));
        if (sb.isEmpty()) sb.append("* Conditions are within acceptable range. No action needed.");
        return sb.toString().trim();
    }
}}
