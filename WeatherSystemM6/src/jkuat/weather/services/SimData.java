
package jkuat.weather.services;

/**
 * SimData — static 7-day JKUAT Main Farm dataset used by the Simulation panel.
 *
 * These values represent one week of real-world-like readings for Juja:
 * high temps (Thursday 38.2°C triggers CRITICAL), zero rain days,
 * and a flood day (Saturday 32.1mm).
 *
 * Kept as a separate class so SimulationController can reference it
 * without importing any service logic.
 */
public class SimData {

    /** Columns: day, temp, humidity, rainfall, windSpeed, windDir, aqi */
    public static final Object[][] WEEKLY = {
        {"Monday",    32.5, 78.0,  4.2, 18.5, "NE", 55},
        {"Tuesday",   34.1, 72.0,  0.0, 22.0, "N",  60},
        {"Wednesday", 29.8, 85.0, 18.5, 10.0, "SE", 48},
        {"Thursday",  38.2, 60.0,  0.0, 30.5, "NW", 72},   // CRITICAL — heat
        {"Friday",    31.0, 75.0,  7.3, 14.0, "NE", 50},
        {"Saturday",  27.5, 90.0, 32.1,  8.0, "E",  42},   // CRITICAL — flood + humidity
        {"Sunday",    30.2, 68.0,  2.0, 19.0, "N",  58},
    };
}