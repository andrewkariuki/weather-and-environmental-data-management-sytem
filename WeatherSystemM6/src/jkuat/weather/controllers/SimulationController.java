package jkuat.weather.controllers;

import java.io.File;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.TextStyle;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

import javafx.application.Platform;
import javafx.collections.ObservableList;
import javafx.concurrent.Task;
import javafx.scene.Node;
import javafx.scene.chart.BarChart;
import javafx.scene.chart.LineChart;
import javafx.scene.chart.PieChart;
import javafx.scene.chart.XYChart;
import javafx.scene.control.Alert;
import javafx.scene.control.Label;
import javafx.scene.control.TextArea;
import javafx.scene.layout.HBox;
import javafx.scene.layout.VBox;
import jkuat.weather.enums.AlertLevel;
import jkuat.weather.exceptions.FileHandlingException;
import jkuat.weather.models.SensorReading;
import jkuat.weather.models.WeatherModels.FarmerAlert;
import jkuat.weather.models.WeatherModels.WeatherReading;
import jkuat.weather.services.ConcurrentSensorFeed;
import jkuat.weather.services.DataServices.OpenMeteoAPI;
import jkuat.weather.services.DataServices.RealisticDataGenerator;
import jkuat.weather.services.FileServices.PowerBIExporter;
import jkuat.weather.services.FileServices.SensorExporter;
import jkuat.weather.services.FileServices.WeatherFileHandler;
import jkuat.weather.services.SimData;
import jkuat.weather.services.WeatherDataset;
import jkuat.weather.utils.Cfg;
import jkuat.weather.utils.WeatherLogger;

//controller for updating dataset
public class SimulationController {

    private final WeatherDataset             dataset;
    private final ObservableList<WeatherReading> readingRows;
    private final WeatherLogger              logger;
    private final Runnable                   onComplete;  // called after run → refreshes dashboard

    public SimulationController(WeatherDataset ds,
                                ObservableList<WeatherReading> rows,
                                WeatherLogger log,
                                Runnable onComplete) {
        this.dataset     = ds;
        this.readingRows = rows;
        this.logger      = log;
        this.onComplete  = onComplete;
    }

    //loads 7-day simulation data
    public Task<Void> buildTask(Node simPanel) {
        return new Task<>() {
            @Override
            protected Void call() throws Exception {
                dataset.clear();
                Platform.runLater(readingRows::clear);

                for (Object[] row : SimData.WEEKLY) {
                    FarmerAlert r = new FarmerAlert(
                        (String) row[0], (double) row[1], (double) row[2],
                        (double) row[3], (double) row[4], (String) row[5], (int) row[6]);
                    dataset.add(r);
                    Platform.runLater(() -> readingRows.add(r));
                    Thread.sleep(100);
                }
                return null;
            }

            @Override
            protected void succeeded() {
                updateSimChart(simPanel);
                updateSimSummary(simPanel);
                logger.event("7-day simulation completed — " + dataset.count() + " readings");
                if (onComplete != null) onComplete.run();
            }
        };
    }

    private void updateSimChart(Node panel) {
        if (panel == null) return;
        @SuppressWarnings("unchecked")
        BarChart<String,Number> chart = (BarChart<String,Number>) panel.lookup("#sim_chart");
        if (chart == null) return;
        Platform.runLater(() -> {
            chart.getData().clear();
            XYChart.Series<String,Number> ts = new XYChart.Series<>(); ts.setName("Temp (°C)");
            XYChart.Series<String,Number> rs = new XYChart.Series<>(); rs.setName("Rain (mm)");
            for (WeatherReading r : dataset.getAll()) {
                String d = r.getDay().substring(0, 3);
                ts.getData().add(new XYChart.Data<>(d, r.getTemp()));
                rs.getData().add(new XYChart.Data<>(d, r.getRainfall()));
            }
            chart.getData().addAll(ts, rs);
        });
    }

    private void updateSimSummary(Node panel) {
        Label sl = (Label) panel.lookup("#sim_sum");
        if (sl == null) return;
        Platform.runLater(() -> sl.setText(String.format(
            "Avg Temp: %.1f°C  |  Max: %.1f°C  |  Total Rain: %.1fmm  |  Critical Days: %d  |  Dry Days: %d",
            dataset.avgTemp().orElse(0), dataset.maxTemp(), dataset.totalRainfall(),
            dataset.criticalDays().size(), dataset.dryDays().size())));
    }
    
    //sensor controller
    public static class SensorController {

    private final ObservableList<SensorReading> sensorRows;
    private final List<SensorReading>           lastBatch;
    private final WeatherLogger                 logger;

    public SensorController(ObservableList<SensorReading> rows,
                            List<SensorReading> lastBatch,
                            WeatherLogger logger) {
        this.sensorRows = rows;
        this.lastBatch  = lastBatch;
        this.logger     = logger;
    }

    //builds a task that runs concurrent sensor
    public Task<List<SensorReading>> buildTask(int numSensors, int n,
                                               Label statusLbl, Node sensorPanel) {
        ConcurrentSensorFeed feed = new ConcurrentSensorFeed(n, numSensors);

        return new Task<>() {
            @Override
            protected List<SensorReading> call() throws Exception {
                Platform.runLater(() ->
                    statusLbl.setText("Status: COLLECTING — " + numSensors + " threads active"));
                return feed.run(logger);
            }

            @Override
            protected void succeeded() {
                List<SensorReading> readings = getValue();
                lastBatch.clear();
                lastBatch.addAll(readings);

                Platform.runLater(() -> {
                    sensorRows.setAll(readings);
                    statusLbl.setText("Status: " + feed.getStatus().label
                                    + " — " + readings.size() + " readings");
                    updateAlertBar(sensorPanel, readings);
                });
            }
        };
    }

    private void updateAlertBar(Node panel, List<SensorReading> readings) {
        HBox bar = (HBox) panel.lookup("#sns_bar");
        if (bar == null) return;
        bar.getChildren().clear();
        for (AlertLevel al : AlertLevel.values()) {
            long cnt = readings.stream().filter(r -> r.alertLevel == al).count();
            Label lb = new Label(al.label + ": " + cnt);
            lb.setStyle("-fx-text-fill:" + al.color + "; -fx-font-size:12; -fx-font-weight:bold;" +
                        "-fx-padding:4 14; -fx-background-color:#112240;" +
                        "-fx-background-radius:4; -fx-border-color:" + al.color +
                        "; -fx-border-radius:4; -fx-border-width:1;");
            bar.getChildren().add(lb);
        }
    }

    public void exportCsv() {
        if (lastBatch.isEmpty()) {
            showInfo("No data", "Run sensor simulation first.");
            return;
        }
        try {
            String path = SensorExporter.export(lastBatch, logger);
            showInfo("Exported", "Sensor CSV saved:\n" + path);
        } catch (Exception e) {
            showInfo("Error", e.getMessage());
        }
    }

    private void showInfo(String title, String msg) {
        Platform.runLater(() -> {
            Alert a = new Alert(Alert.AlertType.INFORMATION);
            a.setTitle(title); a.setHeaderText(null); a.setContentText(msg);
            a.showAndWait();
        });
    }
    }

//analysis controller 
    public static class AnalysisController {

    private final WeatherDataset dataset;

    public AnalysisController(WeatherDataset ds) { this.dataset = ds; }
//populate line chat
    public void runAnalysis(Node analysisPanel) {
        if (dataset.isEmpty()) return;

        updateLineChart(analysisPanel);
        updateStatsTable(analysisPanel);
        updateSortedLabel(analysisPanel);
    }

    @SuppressWarnings("unchecked")
    private void updateLineChart(Node panel) {
        LineChart<String,Number> lc = (LineChart<String,Number>) panel.lookup("#an_line");
        if (lc == null) return;
        lc.getData().clear();
        XYChart.Series<String,Number> ts = new XYChart.Series<>(); ts.setName("Temp (°C)");
        XYChart.Series<String,Number> rs = new XYChart.Series<>(); rs.setName("Rain (mm)");
        XYChart.Series<String,Number> hs = new XYChart.Series<>(); hs.setName("Humidity (%)");
        for (WeatherReading r : dataset.getAll()) {
            String d = r.getDay().substring(0, 3);
            ts.getData().add(new XYChart.Data<>(d, r.getTemp()));
            rs.getData().add(new XYChart.Data<>(d, r.getRainfall()));
            hs.getData().add(new XYChart.Data<>(d, r.getHumidity()));
        }
        lc.getData().addAll(ts, rs, hs);
    }

    @SuppressWarnings("unchecked")
    private void updateStatsTable(Node panel) {
        javafx.scene.control.TableView<String[]> st =
            (javafx.scene.control.TableView<String[]>) panel.lookup("#an_table");
        if (st == null) return;

        double         totalR = dataset.totalRainfall();
        WeatherReading hot    = dataset.sortedByTemp().get(0);
        WeatherReading wet    = dataset.sortedByRain().get(0);

        st.setItems(javafx.collections.FXCollections.observableArrayList(
            new String[]{"Avg Temp          [map + reduce]",   String.format("%.1f°C", dataset.avgTemp().orElse(0))},
            new String[]{"Max Temp          [stream max]",     String.format("%.1f°C", dataset.maxTemp())},
            new String[]{"Min Temp          [stream min]",     String.format("%.1f°C", dataset.minTemp())},
            new String[]{"Total Rainfall    [reduce sum]",     String.format("%.1fmm", totalR)},
            new String[]{"Avg Rainfall/Day  [reduce/count]",   String.format("%.1fmm", totalR / dataset.count())},
            new String[]{"Avg Humidity      [map + reduce]",   String.format("%.0f%%", dataset.avgHumidity().orElse(0))},
            new String[]{"Peak Wind         [stream max]",     String.format("%.1fkm/h", dataset.peakWind())},
            new String[]{"Peak AQI          [stream max]",     String.valueOf(dataset.peakAqi())},
            new String[]{"Hottest Day       [sorted + lambda]",hot.getDay() + " (" + hot.getTemp() + "°C)"},
            new String[]{"Wettest Day       [sorted + lambda]",wet.getDay() + " (" + wet.getRainfall() + "mm)"},
            new String[]{"Critical Days     [filter + lambda]",String.valueOf(dataset.criticalDays().size())},
            new String[]{"Dry Days          [filter + lambda]",String.valueOf(dataset.dryDays().size())},
            new String[]{"Flood Days        [filter + lambda]",String.valueOf(dataset.floodDays().size())},
            new String[]{"Heat Days >=35°C  [filter + lambda]",String.valueOf(dataset.heatDays().size())},
            new String[]{"Disease Risk Days [filter + lambda]",String.valueOf(dataset.diseaseDays().size())}
        ));
    }

    private void updateSortedLabel(Node panel) {
        Label sl = (Label) panel.lookup("#an_sorted");
        if (sl == null) return;
        sl.setText("Hottest → Coldest: " + dataset.sortedByTemp().stream()
            .map(r -> r.getDay() + " (" + r.getTemp() + "°C)")
            .collect(Collectors.joining(" > ")));
    }
    }

//summary controller
    public static class SummaryController {

    private final WeatherDataset dataset;

    public SummaryController(WeatherDataset ds) { this.dataset = ds; }

    public void refreshSummary(Node summaryPanel) {
        if (dataset.isEmpty()) return;
        updateStats(summaryPanel);
        updateCriticalLabel(summaryPanel);
        updateAlertsArea(summaryPanel);
        updatePieChart(summaryPanel);
    }

    private void updateStats(Node panel) {
        javafx.scene.layout.GridPane stats =
            (javafx.scene.layout.GridPane) panel.lookup("#sum_stats");
        if (stats == null) return;
        stats.getChildren().clear();
        Object[][] rows = {
            {"Avg Temp",      String.format("%.1f°C",  dataset.avgTemp().orElse(0))},
            {"Max Temp",      String.format("%.1f°C",  dataset.maxTemp())},
            {"Min Temp",      String.format("%.1f°C",  dataset.minTemp())},
            {"Total Rain",    String.format("%.1fmm",  dataset.totalRainfall())},
            {"Avg Rain/Day",  String.format("%.1fmm",  dataset.totalRainfall() / dataset.count())},
            {"Avg Humidity",  String.format("%.0f%%",  dataset.avgHumidity().orElse(0))},
            {"Peak Wind",     String.format("%.1fkm/h",dataset.peakWind())},
            {"Peak AQI",      String.valueOf(dataset.peakAqi())},
            {"Dry Days",      String.valueOf(dataset.dryDays().size())},
            {"Flood Days",    String.valueOf(dataset.floodDays().size())},
            {"Critical Days", String.valueOf(dataset.criticalDays().size())},
        };
        int col = 0, row = 0;
        for (Object[] r : rows) {
            HBox pair = new HBox(8);
            Label key = new Label((String) r[0] + ":");
            key.setStyle("-fx-text-fill:#4A7FA5; -fx-font-size:11;");
            Label val = new Label((String) r[1]);
            val.setStyle("-fx-text-fill:#E8F4FD; -fx-font-size:11; -fx-font-weight:bold;");
            pair.getChildren().addAll(key, val);
            stats.add(pair, col, row);
            if (++row > 5) { row = 0; col++; }
        }
    }

    private void updateCriticalLabel(Node panel) {
        Label cl = (Label) panel.lookup("#sum_crit");
        if (cl == null) return;
        List<WeatherReading> crit = dataset.criticalDays();
        cl.setText(crit.isEmpty() ? "No critical days in dataset."
            : "CRITICAL: " + crit.stream().map(WeatherReading::getDay)
                                  .collect(Collectors.joining(", ")));
        cl.setStyle("-fx-text-fill:" + (crit.isEmpty() ? "#00E5A0" : "#FF4060")
                  + "; -fx-font-size:12; -fx-font-weight:bold;");
    }

    private void updateAlertsArea(Node panel) {
        TextArea ta = (TextArea) panel.lookup("#sum_alerts");
        if (ta == null) return;
        StringBuilder sb = new StringBuilder();
        for (WeatherReading r : dataset.getAll()) {
            sb.append("== ").append(r.getDay()).append(" == ").append(r.getOverallStatus()).append("\n");
            if (r instanceof FarmerAlert fa) sb.append(fa.farmerAdvice()).append("\n\n");
        }
        ta.setText(sb.toString());
    }

    private void updatePieChart(Node panel) {
        PieChart pie = (PieChart) panel.lookup("#sum_pie");
        if (pie == null) return;
        pie.getData().clear();
        long norm = dataset.getAll().stream().filter(r -> r.getOverallStatus().equals("NORMAL")).count();
        long warn = dataset.getAll().stream().filter(r -> r.getOverallStatus().equals("WARNING")).count();
        long crit = dataset.criticalDays().size();
        if (norm > 0) pie.getData().add(new PieChart.Data("Normal ("  + norm + ")", norm));
        if (warn > 0) pie.getData().add(new PieChart.Data("Warning (" + warn + ")", warn));
        if (crit > 0) pie.getData().add(new PieChart.Data("Critical (" + crit + ")", crit));
    }
    }

    //file controller for saving/loading dataset to CSV
    public static class FileController {

    private final WeatherDataset             dataset;
    private final ObservableList<WeatherReading> readingRows;
    private final WeatherFileHandler         handler;
    private final WeatherLogger              logger;
    private final Runnable                   onLoad;   // refreshes dashboard after load

    public FileController(WeatherDataset ds, ObservableList<WeatherReading> rows,
                          WeatherFileHandler handler, WeatherLogger log, Runnable onLoad) {
        this.dataset     = ds;
        this.readingRows = rows;
        this.handler     = handler;
        this.logger      = log;
        this.onLoad      = onLoad;
    }

    public String save() throws Exception {
        handler.saveCsv(dataset);
        return "Saved " + dataset.count() + " record(s) to " + Cfg.CSV_FILE;
    }

    public String load() throws Exception {
        List<WeatherReading> recs = handler.loadCsv();
        dataset.clear(); readingRows.clear();
        recs.forEach(r -> { dataset.add(r); readingRows.add(r); });
        if (onLoad != null) onLoad.run();
        return "Loaded " + recs.size() + " record(s) from " + Cfg.CSV_FILE;
    }
    }

//power bi export controller
    public static class PowerBIController {

    private final WeatherDataset             dataset;
    private final ObservableList<WeatherReading> readingRows;
    private final WeatherLogger              logger;
    private final Runnable                   onComplete;

    public PowerBIController(WeatherDataset ds, ObservableList<WeatherReading> rows,
                             WeatherLogger log, Runnable onComplete) {
        this.dataset     = ds;
        this.readingRows = rows;
        this.logger      = log;
        this.onComplete  = onComplete;
    }

    //Export current session data 
    public Task<String> buildSessionTask() {
        return new Task<>() {
            @Override
            protected String call() throws Exception {
                List<Map<String,Object>> rows = new ArrayList<>();
                for (WeatherReading r : dataset.getAll()) {
                    java.util.Map<String,Object> row = new java.util.LinkedHashMap<>();
                    row.put("date", LocalDate.now().toString());
                    row.put("day_name",   r.getDay());
                    row.put("month",      "Session");
                    row.put("month_num",  1);
                    row.put("year",       2024);
                    row.put("season",     "Session");
                    row.put("hour",       12);
                    row.put("temperature",r.getTemp());
                    row.put("humidity",   r.getHumidity());
                    row.put("rainfall",   r.getRainfall());
                    row.put("wind_speed", r.getWindSpeed());
                    row.put("wind_direction", r.getWindDir());
                    row.put("aqi",        r.getAqi());
                    row.put("latitude",   Cfg.LATITUDE);
                    row.put("longitude",  Cfg.LONGITUDE);
                    row.put("station_id", Cfg.STATION_ID);
                    row.put("location",   Cfg.LOCATION);
                    row.put("source",     "Session Data");
                    rows.add(row);
                }
                return PowerBIExporter.export(rows, logger);
            }
            @Override protected void succeeded() { if (onComplete != null) onComplete.run(); }
        };
    }

//export from API or generated data
    public Task<String> buildExportTask(boolean useApi) {
        return new Task<>() {
            @Override
            protected String call() throws Exception {
                List<Map<String,Object>> rows = useApi
                    ? OpenMeteoAPI.fetch(1000, logger)
                    : RealisticDataGenerator.generate(1000);
                dataset.clear();
                Platform.runLater(readingRows::clear);
                List<WeatherReading> rds = RealisticDataGenerator.toReadings(rows);
                rds.forEach(r -> {
                    dataset.add(r);
                    Platform.runLater(() -> readingRows.add(r));
                });
                return PowerBIExporter.export(rows, logger);
            }
            @Override protected void succeeded() { if (onComplete != null) onComplete.run(); }
        };
    }
    }

//dashboard controller
    public static class DashboardController {

    private final WeatherDataset             dataset;
    private final ObservableList<SensorReading> liveFeedRows;
    private final WeatherLogger              logger;

    // Color constants 
    private static final String RED    = "#FF4060";
    private static final String YELLOW = "#FFD060";
    private static final String GREEN  = "#00E5A0";
    private static final String ACCENT = "#00C8FF";
    private static final String MUTED  = "#4A7FA5";
    private static final String TEXT   = "#E8F4FD";
    private static final String BORDER = "#1C3354";
    private static final String CARD2  = "#112240";
    private static final String CARD   = "#0D1E36";

    public DashboardController(WeatherDataset ds,
                               ObservableList<SensorReading> liveFeed,
                               WeatherLogger log) {
        this.dataset      = ds;
        this.liveFeedRows = liveFeed;
        this.logger       = log;
    }

   //push new sensor reading
    public void pushLiveSensorReading(SensorReading sr) {
        Platform.runLater(() -> {
            liveFeedRows.add(0, sr);
            if (liveFeedRows.size() > 8) liveFeedRows.remove(liveFeedRows.size() - 1);
        });
    }
//refresh dashboard with latest dataset
    public void refreshDashboard(Node dashPanel) {
        if (dataset.isEmpty() || dashPanel == null) return;
        Platform.runLater(() -> {
            updateHero(dashPanel);
            updateKpiStrip(dashPanel);
            updateAlertBanner(dashPanel);
            updateAlertsBox(dashPanel);
            updateForecastRow(dashPanel);
            updateChart(dashPanel);
        });
    }

//rebuild live sensor feed
    public void updateLiveFeed(Node dashPanel) {
        if (dashPanel == null) return;
        VBox feedList = (VBox) dashPanel.lookup("#dash_feedlist");
        if (feedList == null) return;
        feedList.getChildren().clear();
        for (SensorReading sr : liveFeedRows) {
            feedList.getChildren().add(buildFeedRow(sr, feedList.getChildren().isEmpty()));
        }
    }
//dashboard update methods 
    private void updateHero(Node panel) {
        Label tempBig = (Label) panel.lookup("#dash_tempbig");
        if (tempBig != null)
            tempBig.setText(String.format("%.1f°C", dataset.avgTemp().orElse(0)));

        Label cond = (Label) panel.lookup("#dash_condition");
        if (cond != null) {
            WeatherReading latest = dataset.sortedByTemp().get(0);
            String status = latest.getOverallStatus();
            cond.setText(status.equals("CRITICAL") ? "Heat stress conditions"
                        : status.equals("WARNING")  ? "Caution advised"
                        : "Partly Cloudy · Feels like " +
                          String.format("%.0f°C", latest.getHeatIndex()));
        }
    }

    private void updateKpiStrip(Node panel) {
        setText(panel, "dash_kpi_temp", String.format("%.1f", dataset.avgTemp().orElse(0)) + "°C");
        setText(panel, "dash_kpi_rain", String.format("%.1f", dataset.totalRainfall()) + "mm");
        setText(panel, "dash_kpi_wind", String.format("%.1f", dataset.peakWind()) + "km/h");
        setText(panel, "dash_kpi_aqi",  String.valueOf(dataset.peakAqi()));
    }

    private void updateAlertBanner(Node panel) {
        HBox banner   = (HBox)  panel.lookup("#dash_banner");
        Label bannerMsg = (Label) panel.lookup("#dash_bannermsg");
        if (banner == null || bannerMsg == null) return;

        List<WeatherReading> crits = dataset.criticalDays();
        if (!crits.isEmpty()) {
            banner.setVisible(true); banner.setManaged(true);
            List<String> msgs = new ArrayList<>();
            for (WeatherReading r : crits) {
                if (r.getTemp()     >= Cfg.TEMP_HEATWAVE)   msgs.add("Zero rain + extreme heat — irrigate all fields immediately");
                if (r.getRainfall() >  Cfg.RAINFALL_HEAVY)  msgs.add("Heavy rainfall — flooding risk");
            }
            bannerMsg.setText(msgs.isEmpty() ? "Critical conditions detected" : msgs.get(0));
        } else {
            banner.setVisible(false); banner.setManaged(false);
        }
    }

    private void updateAlertsBox(Node panel) {
        VBox alertsBox = (VBox) panel.lookup("#dash_alertsbox");
        if (alertsBox == null) return;
        alertsBox.getChildren().clear();
        if (!dataset.heatDays().isEmpty())  alertsBox.getChildren().add(alertChip("CRITICAL","Heat stress", RED));
        if (!dataset.dryDays().isEmpty())   alertsBox.getChildren().add(alertChip("NOTICE","No rainfall",   YELLOW));
        if (!dataset.floodDays().isEmpty()) alertsBox.getChildren().add(alertChip("CRITICAL","Flood risk",  RED));
        if (alertsBox.getChildren().isEmpty()) {
            Label ok = new Label("All clear — normal conditions");
            ok.setStyle("-fx-text-fill:" + GREEN + "; -fx-font-size:11;");
            alertsBox.getChildren().add(ok);
        }
        Label cnt = (Label) panel.lookup("#dash_alertcount");
        if (cnt != null) {
            int n = dataset.criticalDays().size();
            cnt.setText(n > 0 ? n + " alert" + (n != 1 ? "s" : "") + " today" : "");
        }
    }

    @SuppressWarnings("unchecked")
    private void updateForecastRow(Node panel) {
        HBox forecastRow = (HBox) panel.lookup("#dash_forecastrow");
        if (forecastRow == null) return;
        forecastRow.getChildren().clear();
        List<WeatherReading> readings = dataset.getAll();
        boolean first = true;
        for (int i = 0; i < readings.size() && i < 7; i++) {
            forecastRow.getChildren().add(buildForecastCard(readings.get(i), first));
            first = false;
        }
    }

    @SuppressWarnings("unchecked")
    private void updateChart(Node panel) {
        BarChart<String,Number> chart = (BarChart<String,Number>) panel.lookup("#dash_chart");
        if (chart == null) return;
        chart.getData().clear();
        XYChart.Series<String,Number> ser = new XYChart.Series<>();
        for (WeatherReading r : dataset.getAll())
            ser.getData().add(new XYChart.Data<>(r.getDay().substring(0, 3), r.getTemp()));
        chart.getData().add(ser);
        Platform.runLater(() -> {
            for (XYChart.Data<String,Number> d : ser.getData()) {
                if (d.getNode() == null) continue;
                double v   = d.getYValue().doubleValue();
                String col = v >= Cfg.TEMP_HEATWAVE ? RED : v >= Cfg.TEMP_OPTIMAL_LOW ? YELLOW : ACCENT;
                d.getNode().setStyle("-fx-bar-fill:" + col + "; -fx-background-radius:3 3 0 0;");
            }
        });
    }
//widet methods for building forecast cards and feed rows
    private VBox buildForecastCard(WeatherReading r, boolean isToday) {
        VBox card = new VBox(4);
        card.setAlignment(javafx.geometry.Pos.CENTER);
        card.setPadding(new javafx.geometry.Insets(10, 0, 10, 0));
        javafx.scene.layout.HBox.setHgrow(card, javafx.scene.layout.Priority.ALWAYS);
        card.setStyle("-fx-background-color:" + (isToday ? CARD2 : CARD) +
                     "; -fx-border-color:" + (isToday ? ACCENT : BORDER) +
                     "; -fx-border-width:0 1 0 0;");

        String icon = r.getTemp() >= Cfg.TEMP_HEATWAVE  ? "🔥"
                    : r.getRainfall() > Cfg.RAINFALL_HEAVY ? "⛈"
                    : r.getRainfall() > 0                   ? "🌧"
                    : r.getHumidity() > 75                  ? "⛅" : "☀";

        Label dayLbl  = new Label(r.getDay().substring(0, 3));
        dayLbl.setStyle("-fx-text-fill:" + (isToday ? ACCENT : MUTED) + "; -fx-font-size:10; -fx-font-weight:bold;");
        Label iconLbl = new Label(icon); iconLbl.setStyle("-fx-font-size:20;");
        Label tmpLbl  = new Label(String.format("%.1f°", r.getTemp()));
        tmpLbl.setStyle("-fx-text-fill:" + TEXT + "; -fx-font-size:13; -fx-font-weight:bold;");
        Label rnLbl   = new Label(r.getRainfall() == 0 ? "0mm" : String.format("%.1fmm", r.getRainfall()));
        rnLbl.setStyle("-fx-text-fill:" + MUTED + "; -fx-font-size:10;");
        card.getChildren().addAll(dayLbl, iconLbl, tmpLbl, rnLbl);
        return card;
    }

    private HBox buildFeedRow(SensorReading sr, boolean isNewest) {
        HBox row = new HBox(0); row.setAlignment(javafx.geometry.Pos.CENTER_LEFT);
        row.setPadding(new javafx.geometry.Insets(6, 16, 6, 16));
        row.setStyle("-fx-border-color:" + BORDER + "; -fx-border-width:0 0 1 0;"
                   + (isNewest ? "-fx-background-color:#0A2030;" : ""));

        Label ts = new Label(sr.timestamp);
        ts.setStyle("-fx-text-fill:" + MUTED + "; -fx-font-size:10; -fx-font-family:'Courier New'; -fx-min-width:72;");
        Label sid = new Label(sr.sensorId.replace("SENSOR-",""));
        sid.setStyle("-fx-text-fill:" + GREEN + "; -fx-font-size:10; -fx-font-weight:bold;" +
                     "-fx-font-family:'Courier New'; -fx-min-width:70;");
        String valCol = sr.alertLevel == AlertLevel.CRITICAL ? RED
                      : sr.alertLevel == AlertLevel.WARNING  ? YELLOW : TEXT;
        Label val = new Label(String.format("%.1f%s", sr.value, sr.unit));
        val.setStyle("-fx-text-fill:" + valCol + "; -fx-font-size:11; -fx-font-weight:bold; -fx-min-width:80;");

        javafx.scene.layout.Region sp = new javafx.scene.layout.Region();
        javafx.scene.layout.HBox.setHgrow(sp, javafx.scene.layout.Priority.ALWAYS);
        String ico = sr.alertLevel == AlertLevel.CRITICAL ? "🔴"
                   : sr.alertLevel == AlertLevel.WARNING  ? "🟡" : "🟢";
        Label alIco = new Label(ico); alIco.setStyle("-fx-font-size:9;");
        row.getChildren().addAll(ts, sid, val, sp, alIco);
        return row;
    }

    private HBox alertChip(String level, String msg, String col) {
        HBox chip = new HBox(6); chip.setAlignment(javafx.geometry.Pos.CENTER_LEFT);
        Label lvl = new Label(level);
        lvl.setStyle("-fx-text-fill:" + col + "; -fx-font-size:9; -fx-font-weight:bold;" +
                     "-fx-font-family:'Courier New'; -fx-background-color:" +
                     (col.equals(RED) ? "#300010" : "#201500") +
                     "; -fx-padding:1 5; -fx-background-radius:2;");
        Label m = new Label(msg); m.setStyle("-fx-text-fill:" + TEXT + "; -fx-font-size:10;");
        chip.getChildren().addAll(lvl, m);
        return chip;
    }

    private void setText(Node panel, String id, String text) {
        Label l = (Label) panel.lookup("#" + id);
        if (l != null) l.setText(text);
    }
}
}