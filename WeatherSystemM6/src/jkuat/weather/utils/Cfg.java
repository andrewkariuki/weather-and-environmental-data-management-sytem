package jkuat.weather.utils;

import java.io.File;
import java.util.List;

/**
 * Cfg — central configuration constants for the entire system.
 *
 * Why a separate class?
 *   Any panel, service, or model that needs a threshold (e.g. TEMP_HEATWAVE)
 *   imports from ONE place. Change the value here and it propagates everywhere —
 *   no hunting through 1 400 lines of code.
 */
public class Cfg {

    // ── Station metadata ────────────────────────────────────────────────────
    public static final String SYSTEM_NAME = "JKUAT WEATHER SYSTEM";
    public static final String STATION_ID  = "KE-NBI-001";
    public static final String LOCATION    = "JKUAT Main Farm, Juja";
    public static final double LATITUDE    = -1.0896;
    public static final double LONGITUDE   = 37.0105;

    // ── Agronomic thresholds ────────────────────────────────────────────────
    public static final double TEMP_HEATWAVE      = 35.0;
    public static final double TEMP_OPTIMAL_LOW   = 20.0;
    public static final double TEMP_COLD          = 10.0;
    public static final double RAINFALL_CROP_NEED =  5.0;
    public static final double RAINFALL_LOW       =  2.0;
    public static final double RAINFALL_HEAVY     = 25.0;
    public static final double WIND_STRONG        = 50.0;
    public static final double WIND_MODERATE      = 30.0;
    public static final double HUMIDITY_DISEASE   = 85.0;
    public static final double HUMIDITY_DRY       = 30.0;
    public static final int    AQI_UNHEALTHY      = 150;
    public static final int    AQI_MODERATE       = 100;

    // ── Validation lists ────────────────────────────────────────────────────
    public static final List<String> VALID_DAYS = List.of(
        "Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday");
    public static final List<String> VALID_DIRS = List.of(
        "N","NE","E","SE","S","SW","W","NW");

    // ── File paths ──────────────────────────────────────────────────────────
    public static final String DATA_DIR    = "weather_data";
    public static final String CSV_FILE    = DATA_DIR + File.separator + "weather_readings.csv";
    public static final String POWERBI_CSV = DATA_DIR + File.separator + "powerbi_weather_export.csv";
    public static final String SENSOR_CSV  = DATA_DIR + File.separator + "sensor_readings.csv";
    public static final String LOG_FILE    = DATA_DIR + File.separator + "system.log";
}