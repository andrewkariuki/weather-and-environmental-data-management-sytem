package jkuat.weather.services;

import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.format.TextStyle;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;

import jkuat.weather.exceptions.APIException;
import jkuat.weather.models.WeatherModels.FarmerAlert;
import jkuat.weather.models.WeatherModels.WeatherReading;
import jkuat.weather.utils.Cfg;
import jkuat.weather.utils.WeatherLogger;

public class DataServices {

// ============================================================
//  RealisticDataGenerator — Juja climate model (offline)
// ============================================================
/**
 * RealisticDataGenerator — produces climate-realistic synthetic rows
 * when the Open-Meteo API is unavailable.
 *
 * Uses a month × parameter lookup table (MONTHS) that models Juja's
 * four seasons: Long Rains (Mar–May), Short Rains (Sep–Nov),
 * two Dry seasons (Jun–Aug, Dec–Feb).
 *
 * Called by PowerBIExporter (option C) and as a padding fallback
 * when the API returns fewer rows than requested.
 */
public static class RealisticDataGenerator {

    /** Month profiles: {tMin,tMax, rainProb%,rainMin,rainMax,
     *                   humMin,humMax, windMin,windMax, aqiMin,aqiMax} */
    private static final int[][] MONTHS = {
        {18,30, 15,0,8,   45,70, 5,25,  40,90},   // Jan
        {19,31, 18,0,10,  45,72, 5,28,  40,95},   // Feb
        {18,30, 55,2,40,  60,90, 3,18,  30,70},   // Mar
        {17,28, 70,5,55,  65,95, 2,15,  25,65},   // Apr
        {17,27, 65,3,45,  65,92, 3,18,  28,68},   // May
        {15,25, 20,0,12,  50,75, 8,35,  35,85},   // Jun
        {14,24, 15,0,8,   48,72,10,40,  38,90},   // Jul
        {15,25, 18,0,10,  48,73, 8,38,  36,88},   // Aug
        {17,28, 40,1,28,  55,82, 5,25,  30,75},   // Sep
        {17,28, 60,3,45,  60,90, 3,20,  28,68},   // Oct
        {17,27, 55,2,40,  60,88, 3,20,  28,65},   // Nov
        {18,29, 20,0,15,  48,72, 5,28,  38,88},   // Dec
    };
    private static final String[] SEASONS = {
        "Dry (Dec-Feb)","Dry (Dec-Feb)","Long Rains","Long Rains","Long Rains",
        "Dry (Jun-Aug)","Dry (Jun-Aug)","Dry (Jun-Aug)",
        "Short Rains","Short Rains","Short Rains","Dry (Dec-Feb)"
    };
    private static final String[] DIRS = {"N","NE","E","SE","S","SW","W","NW"};

    /** Generate {@code n} daily rows starting 2024-01-01. */
    public static List<Map<String,Object>> generate(int n) {
        List<Map<String,Object>> rows = new ArrayList<>();
        Random    rng   = new Random(42);
        LocalDate start = LocalDate.of(2024, 1, 1);

        for (int i = 0; i < n; i++) {
            LocalDate date  = start.plusDays(i);
            int       m     = date.getMonthValue() - 1;
            int[]     p     = MONTHS[m];

            double temp = clamp(
                Math.round((p[0] + rng.nextDouble()*(p[1]-p[0]) + rng.nextGaussian()*0.8)*10)/10.0,
                p[0]-2, p[1]+3);
            double rain = rng.nextInt(100) < p[2]
                ? Math.round((p[3] + rng.nextDouble()*(p[4]-p[3]))*10)/10.0
                : 0.0;
            double hum  = Math.round((p[5] + rng.nextDouble()*(p[6]-p[5]))*10)/10.0;
            if (rain > 10) hum = Math.min(98, hum + 5 + rng.nextDouble()*10);
            double wind = Math.round((p[7] + rng.nextDouble()*(p[8]-p[7]))*10)/10.0;
            String dir  = DIRS[rng.nextInt(8)];
            int    aqi  = p[9] + (int)(rng.nextDouble()*(p[10]-p[9]));
            if (rain == 0 && wind > 25) aqi = Math.min(200, aqi + 10 + rng.nextInt(30));

            String dayName = date.getDayOfWeek().getDisplayName(TextStyle.FULL, Locale.ENGLISH);
            Map<String,Object> row = new LinkedHashMap<>();
            row.put("date",        date.toString());
            row.put("day_name",    dayName);
            row.put("month",       date.getMonth().getDisplayName(TextStyle.FULL, Locale.ENGLISH));
            row.put("month_num",   date.getMonthValue());
            row.put("year",        date.getYear());
            row.put("season",      SEASONS[m]);
            row.put("hour",        12);
            row.put("temperature", temp);
            row.put("humidity",    Math.round(hum*10)/10.0);
            row.put("rainfall",    rain);
            row.put("wind_speed",  wind);
            row.put("wind_direction", dir);
            row.put("aqi",         aqi);
            row.put("latitude",    Cfg.LATITUDE);
            row.put("longitude",   Cfg.LONGITUDE);
            row.put("station_id",  Cfg.STATION_ID);
            row.put("location",    Cfg.LOCATION);
            row.put("source",      "Generated (offline fallback)");
            rows.add(row);
        }
        return rows;
    }

    /** Convert raw map rows to FarmerAlert domain objects for the dataset. */
    public static List<WeatherReading> toReadings(List<Map<String,Object>> rows) {
        List<WeatherReading> result = new ArrayList<>();
        for (var row : rows) {
            try {
                String day = (String) row.get("day_name");
                if (!Cfg.VALID_DAYS.contains(day)) day = "Monday";
                result.add(new FarmerAlert(day,
                    ((Number) row.get("temperature")).doubleValue(),
                    ((Number) row.get("humidity")).doubleValue(),
                    ((Number) row.get("rainfall")).doubleValue(),
                    ((Number) row.get("wind_speed")).doubleValue(),
                    (String)  row.get("wind_direction"),
                    ((Number) row.get("aqi")).intValue()));
            } catch (Exception ignored) {}
        }
        return result;
    }

    private static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(hi, v));
    }
}


// ============================================================
//  OpenMeteoAPI — real weather fetch (online)
// ============================================================
/**
 * OpenMeteoAPI — fetches real daily weather for Juja from the free
 * Open-Meteo API (no API key required).
 *
 * Endpoint: api.open-meteo.com/v1/forecast
 * Parameters: past 92 days + 1 forecast day, daily resolution.
 *
 * If the API returns fewer rows than targetRows, the gap is padded
 * with RealisticDataGenerator rows so the PowerBI export is always full.
 *
 * JSON is parsed manually (no external library dependency) using
 * simple string search — keeps the build simple for a student project.
 *
 * Called from PowerBIController on a background Task.
 */
public static class OpenMeteoAPI {

    private static final String BASE =
        "https://api.open-meteo.com/v1/forecast";

    private static String compassFromDeg(double deg) {
        String[] d = {"N","NE","E","SE","S","SW","W","NW"};
        return d[(int)((deg + 22.5) / 45) % 8];
    }

    private static int estimateAqi(double wind, double rain, int month) {
        int base = 45;
        if (rain == 0 && wind > 20) base += (int)(wind * 1.2);
        else if (rain == 0)         base += 15;
        if (rain > 10)              base -= 15;
        if (month == 6 || month == 7 || month == 8 ||
            month == 12 || month == 1 || month == 2) base += 10;
        return Math.max(20, Math.min(180, base));
    }

    public static List<Map<String,Object>> fetch(int targetRows, WeatherLogger logger)
            throws APIException {
        String params =
            "latitude="  + Cfg.LATITUDE +
            "&longitude=" + Cfg.LONGITUDE +
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum," +
            "windspeed_10m_max,winddirection_10m_dominant," +
            "relative_humidity_2m_max,uv_index_max" +
            "&past_days=92&forecast_days=1&timezone=Africa%2FNairobi";

        try {
            URI uri  = URI.create(BASE + "?" + params);
            URL url  = uri.toURL();
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestProperty("User-Agent", "JKUAT-Weather-M6/6.0");
            conn.setConnectTimeout(15_000);
            conn.setReadTimeout(15_000);

            int code = conn.getResponseCode();
            if (code != 200) throw new APIException("HTTP " + code + " from Open-Meteo");

            String raw;
            try (var is = conn.getInputStream()) {
                raw = new String(is.readAllBytes(), StandardCharsets.UTF_8);
            }

            List<String> dates  = extractArr (raw, "\"time\"");
            List<Double> tmax   = extractDbls(raw, "\"temperature_2m_max\"");
            List<Double> tmin   = extractDbls(raw, "\"temperature_2m_min\"");
            List<Double> precip = extractDbls(raw, "\"precipitation_sum\"");
            List<Double> wSpd   = extractDbls(raw, "\"windspeed_10m_max\"");
            List<Double> wDir   = extractDbls(raw, "\"winddirection_10m_dominant\"");
            List<Double> hum    = extractDbls(raw, "\"relative_humidity_2m_max\"");

            String[] SEAS = {"","Dry (Dec-Feb)","Dry (Dec-Feb)","Long Rains","Long Rains",
                "Long Rains","Dry (Jun-Aug)","Dry (Jun-Aug)","Dry (Jun-Aug)",
                "Short Rains","Short Rains","Short Rains","Dry (Dec-Feb)"};

            List<Map<String,Object>> rows = new ArrayList<>();
            for (int i = 0; i < dates.size(); i++) {
                try {
                    LocalDate date  = LocalDate.parse(dates.get(i).replace("\"","").trim());
                    int       month = date.getMonthValue();
                    double    tmx   = safe(tmax,   i, 25.0);
                    double    tmn   = safe(tmin,   i, 18.0);
                    double    temp  = Math.max(-50, Math.min(60, Math.round((tmx+tmn)/2*10)/10.0));
                    double    rain  = Math.round(safe(precip, i, 0.0)*10)/10.0;
                    double    h     = Math.min(100, Math.max(0, safe(hum,   i, 65.0)));
                    double    ws    = safe(wSpd, i, 10.0);
                    String    wd    = i < wDir.size() && wDir.get(i) != null
                                     ? compassFromDeg(wDir.get(i)) : "N";
                    int       aqi   = estimateAqi(ws, rain, month);

                    String dayName = date.getDayOfWeek().getDisplayName(TextStyle.FULL, Locale.ENGLISH);
                    Map<String,Object> row = new LinkedHashMap<>();
                    row.put("date",           date.toString());
                    row.put("day_name",       dayName);
                    row.put("month",          date.getMonth().getDisplayName(TextStyle.FULL, Locale.ENGLISH));
                    row.put("month_num",      month);
                    row.put("year",           date.getYear());
                    row.put("season",         SEAS[month]);
                    row.put("hour",           12);
                    row.put("temperature",    temp);
                    row.put("humidity",       Math.round(h*10)/10.0);
                    row.put("rainfall",       rain);
                    row.put("wind_speed",     ws);
                    row.put("wind_direction", wd);
                    row.put("aqi",            aqi);
                    row.put("latitude",       Cfg.LATITUDE);
                    row.put("longitude",      Cfg.LONGITUDE);
                    row.put("station_id",     Cfg.STATION_ID);
                    row.put("location",       Cfg.LOCATION);
                    row.put("source",         "Open-Meteo API (real data)");
                    rows.add(row);
                } catch (Exception ignored) {}
            }

            if (rows.isEmpty()) throw new APIException("API returned no parseable rows");

            int real = rows.size();
            if (real < targetRows) {
                List<Map<String,Object>> pad = RealisticDataGenerator.generate(targetRows - real);
                pad.forEach(r -> r.put("source", "Generated (padded to " + targetRows + ")"));
                rows.addAll(pad);
            }

            if (logger != null)
                logger.event("Open-Meteo: " + real + " real + " + (rows.size()-real)
                           + " generated = " + rows.size() + " rows");
            return rows;

        } catch (APIException e) { throw e;
        } catch (Exception e)    { throw new APIException("Network error: " + e.getMessage(), e); }
    }

    // ── JSON helpers ─────────────────────────────────────────────────────────
    private static List<String> extractArr(String json, String key) {
        List<String> r = new ArrayList<>();
        int idx = json.indexOf(key); if (idx < 0) return r;
        int s   = json.indexOf('[', idx);
        int e   = json.indexOf(']', s);
        if (s < 0 || e < 0) return r;
        for (String t : json.substring(s+1, e).split(",")) r.add(t.trim());
        return r;
    }
    private static List<Double> extractDbls(String json, String key) {
        List<Double> r = new ArrayList<>();
        for (String s : extractArr(json, key)) {
            try { r.add("null".equals(s) ? null : Double.parseDouble(s)); }
            catch (NumberFormatException e) { r.add(null); }
        }
        return r;
    }
    private static double safe(List<Double> list, int i, double def) {
        return (i < list.size() && list.get(i) != null) ? list.get(i) : def;
    }
}}
