package jkuat.weather.services;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import jkuat.weather.exceptions.EmptyDatasetException;
import jkuat.weather.exceptions.FileHandlingException;
import jkuat.weather.models.SensorReading;
import jkuat.weather.models.WeatherModels.FarmerAlert;
import jkuat.weather.models.WeatherModels.WeatherReading;
import jkuat.weather.utils.Cfg;
import jkuat.weather.utils.WeatherLogger;

public class FileServices {

// ============================================================
//  WeatherFileHandler — CSV save / load (M4 file handling)
// ============================================================
/**
 * WeatherFileHandler — persists WeatherReading objects to/from CSV.
 *
 * saveCsv() is called by the File Handling panel "Save" button.
 * loadCsv() is called by the "Load" button — rebuilds FarmerAlert objects
 * from each row, so farmer advice is available immediately after load.
 *
 * Throws typed exceptions (EmptyDatasetException, FileHandlingException)
 * that the UI layer catches and displays in status labels — no raw IOException
 * ever reaches the UI.
 */
public static class WeatherFileHandler {

    private final WeatherLogger logger;

    public WeatherFileHandler(WeatherLogger logger) {
        this.logger = logger;
        new File(Cfg.DATA_DIR).mkdirs();
    }

    public void saveCsv(WeatherDataset ds) throws EmptyDatasetException, FileHandlingException {
        if (ds.isEmpty()) throw new EmptyDatasetException("No data to save.");
        try (var w = new FileWriter(Cfg.CSV_FILE)) {
            w.write("day,temperature,humidity,rainfall,wind_speed,wind_direction,aqi\n");
            for (WeatherReading r : ds.getAll()) {
                w.write(r.getDay() + "," + r.getTemp() + "," + r.getHumidity() + ","
                      + r.getRainfall() + "," + r.getWindSpeed() + ","
                      + r.getWindDir() + "," + r.getAqi() + "\n");
            }
            logger.event("CSV saved: " + Cfg.CSV_FILE + " (" + ds.count() + " records)");
        } catch (IOException e) {
            throw new FileHandlingException("Save failed: " + e.getMessage(), e);
        }
    }

    public List<WeatherReading> loadCsv() throws FileHandlingException {
        File f = new File(Cfg.CSV_FILE);
        if (!f.exists()) throw new FileHandlingException("File not found: " + Cfg.CSV_FILE);

        List<WeatherReading> list = new ArrayList<>();
        try (var br = new BufferedReader(new FileReader(f))) {
            String line;
            br.readLine(); // skip header
            while ((line = br.readLine()) != null) {
                String[] p = line.split(",");
                if (p.length < 7) continue;
                try {
                    list.add(new FarmerAlert(
                        p[0].trim(),
                        Double.parseDouble(p[1]),
                        Double.parseDouble(p[2]),
                        Double.parseDouble(p[3]),
                        Double.parseDouble(p[4]),
                        p[5].trim(),
                        Integer.parseInt(p[6].trim())));
                } catch (Exception ignored) {}
            }
        } catch (IOException e) {
            throw new FileHandlingException("Load failed: " + e.getMessage(), e);
        }

        if (list.isEmpty()) throw new FileHandlingException("No valid records in file.");
        logger.event("CSV loaded: " + Cfg.CSV_FILE + " (" + list.size() + " records)");
        return list;
    }
}


//generates data ready for csv export
public static class PowerBIExporter {

    public static final String[] HEADERS = {
        "date","day_name","month","month_num","year","season","hour",
        "temperature","humidity","rainfall","wind_speed","wind_direction",
        "aqi","heat_index","evapotranspiration","dew_point","water_deficit",
        "alert_level","overall_status","latitude","longitude",
        "station_id","location","source"
    };

    public static Map<String,Object> enrich(Map<String,Object> row) {
        double t  = ((Number) row.get("temperature")).doubleValue();
        double h  = ((Number) row.get("humidity")).doubleValue();
        double r  = ((Number) row.get("rainfall")).doubleValue();
        double hi = Math.round((t + (0.33*(h/100)*6.105) - 4.0) * 100) / 100.0;
        double et = Math.round(0.0023 * (t+17.8) * Math.pow(100-h, 0.5) * 100) / 100.0;
        double a  = 17.27, b = 237.7, g = (a*t)/(b+t) + (h/100.0);
        double dp = Math.round((b*g)/(a-g) * 100) / 100.0;
        double wd = Math.max(0, Math.round((Cfg.RAINFALL_CROP_NEED - r)*10)/10.0);
        int    aqi = ((Number) row.get("aqi")).intValue();

        String alert, status;
        if (t >= Cfg.TEMP_HEATWAVE || r > Cfg.RAINFALL_HEAVY || aqi >= Cfg.AQI_UNHEALTHY) {
            alert = status = "CRITICAL";
        } else if (t < Cfg.TEMP_OPTIMAL_LOW || h > Cfg.HUMIDITY_DISEASE || aqi >= Cfg.AQI_MODERATE) {
            alert = status = "WARNING";
        } else {
            alert = status = "NORMAL";
        }

        Map<String,Object> out = new LinkedHashMap<>(row);
        out.put("heat_index",        hi);
        out.put("evapotranspiration",et);
        out.put("dew_point",         dp);
        out.put("water_deficit",     wd);
        out.put("alert_level",       alert);
        out.put("overall_status",    status);
        return out;
    }

    public static String export(List<Map<String,Object>> rows, WeatherLogger logger)
            throws FileHandlingException {
        new File(Cfg.DATA_DIR).mkdirs();
        try (var w = new FileWriter(Cfg.POWERBI_CSV)) {
            w.write(String.join(",", HEADERS) + "\n");
            for (var row : rows) {
                var e = enrich(row);
                List<String> vals = new ArrayList<>();
                for (String h : HEADERS) vals.add(String.valueOf(e.getOrDefault(h, "")));
                w.write(String.join(",", vals) + "\n");
            }
        } catch (IOException ex) {
            if (logger != null) logger.error("PowerBI export failed: " + ex.getMessage());
            throw new FileHandlingException("Could not save CSV: " + ex.getMessage());
        }
        double kb = Math.round(new File(Cfg.POWERBI_CSV).length() / 102.4) / 10.0;
        if (logger != null)
            logger.event("PowerBI CSV: " + Cfg.POWERBI_CSV + " (" + rows.size() + " rows | " + kb + " KB)");
        return Cfg.POWERBI_CSV;
    }
}


//sensor exporter
public static class SensorExporter {

    public static String export(List<SensorReading> readings, WeatherLogger logger)
            throws FileHandlingException {
        if (readings.isEmpty()) throw new EmptyDatasetException("No sensor readings to export.");
        new File(Cfg.DATA_DIR).mkdirs();
        try (var w = new FileWriter(Cfg.SENSOR_CSV)) {
            w.write("timestamp,sensor_id,parameter,value,unit,alert_level\n");
            for (var r : readings)
                w.write(r.timestamp + "," + r.sensorId + "," + r.parameter + ","
                      + r.value + "," + r.unit + "," + r.alertLevel.label + "\n");
        } catch (IOException ex) {
            throw new FileHandlingException("Sensor export failed: " + ex.getMessage());
        }
        double kb = Math.round(new File(Cfg.SENSOR_CSV).length() / 102.4) / 10.0;
        if (logger != null)
            logger.event("Sensor CSV: " + Cfg.SENSOR_CSV + " (" + readings.size() + " readings | " + kb + " KB)");
        return Cfg.SENSOR_CSV;
    }
}}
