package jkuat.weather.enums;

import jkuat.weather.utils.Cfg;

//classifies sensor readings to alert levels
public enum AlertLevel {
    NORMAL  (1, "NORMAL",   "#4CAF50"),
    NOTICE  (2, "NOTICE",   "#2196F3"),
    WARNING (3, "WARNING",  "#FF9800"),
    CRITICAL(4, "CRITICAL", "#F44336");

    public final int    val;
    public final String label;
    public final String color;

    AlertLevel(int v, String l, String c) { val = v; label = l; color = c; }

    //classifies a sensor reading to an alert level based on thresholds defined in Cfg
    public static AlertLevel classify(String param, double v) {
        return switch (param) {
            case "TEMP"       -> v >= Cfg.TEMP_HEATWAVE   ? CRITICAL
                               : v <= Cfg.TEMP_COLD        ? WARNING
                               : v <  Cfg.TEMP_OPTIMAL_LOW ? NOTICE : NORMAL;
            case "HUMIDITY"   -> v >  Cfg.HUMIDITY_DISEASE ? CRITICAL
                               : v <  Cfg.HUMIDITY_DRY     ? WARNING : NORMAL;
            case "RAINFALL"   -> v >  Cfg.RAINFALL_HEAVY   ? CRITICAL
                               : v == 0                    ? WARNING : NORMAL;
            case "WIND"       -> v >  Cfg.WIND_STRONG      ? CRITICAL
                               : v >  Cfg.WIND_MODERATE    ? WARNING : NORMAL;
            case "AQI"        -> v >= Cfg.AQI_UNHEALTHY    ? CRITICAL
                               : v >= Cfg.AQI_MODERATE     ? WARNING : NORMAL;
            case "SOIL_MOIST" -> v < 20 ? CRITICAL : v < 35 ? WARNING : NORMAL;
            case "UV_INDEX"   -> v >= 8 ? CRITICAL : v >= 6 ? WARNING : NORMAL;
            default           -> NORMAL;
        };
    }
}