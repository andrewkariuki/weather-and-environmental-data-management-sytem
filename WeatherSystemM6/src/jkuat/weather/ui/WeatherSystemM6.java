package jkuat.weather.ui;

import java.io.File;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.TextStyle;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;

import javafx.animation.FadeTransition;
import javafx.animation.KeyFrame;
import javafx.animation.Timeline;
import javafx.application.Application;
import javafx.application.Platform;
import javafx.beans.property.SimpleStringProperty;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.concurrent.Task;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.geometry.Side;
import javafx.scene.Node;
import javafx.scene.Scene;
import javafx.scene.chart.BarChart;
import javafx.scene.chart.CategoryAxis;
import javafx.scene.chart.Chart;
import javafx.scene.chart.LineChart;
import javafx.scene.chart.NumberAxis;
import javafx.scene.chart.PieChart;
import javafx.scene.control.Alert;
import javafx.scene.control.Button;
import javafx.scene.control.ComboBox;
import javafx.scene.control.Label;
import javafx.scene.control.ProgressBar;
import javafx.scene.control.RadioButton;
import javafx.scene.control.ScrollPane;
import javafx.scene.control.Spinner;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.control.TextArea;
import javafx.scene.control.TextField;
import javafx.scene.control.ToggleButton;
import javafx.scene.control.ToggleGroup;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.ColumnConstraints;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;
import javafx.scene.paint.Color;
import javafx.scene.shape.Circle;
import javafx.stage.Stage;
import javafx.util.Duration;

import jkuat.weather.controllers.SimulationController;
import jkuat.weather.enums.AlertLevel;
import jkuat.weather.exceptions.ValidationException;
import jkuat.weather.models.SensorReading;
import jkuat.weather.models.WeatherModels.FarmerAlert;
import jkuat.weather.models.WeatherModels.WeatherReading;
import jkuat.weather.services.ConcurrentSensorFeed;
import jkuat.weather.services.FileServices.WeatherFileHandler;
import jkuat.weather.services.WeatherDataset;
import jkuat.weather.utils.Cfg;
import jkuat.weather.utils.WeatherLogger;

//main application class
public class WeatherSystemM6 extends Application {

   //state model
    private final WeatherLogger              logger      = new WeatherLogger();
    private final WeatherFileHandler         fileHandler = new WeatherFileHandler(logger);
    private final WeatherDataset             dataset     = new WeatherDataset();
    private final ObservableList<WeatherReading> readingRows = FXCollections.observableArrayList();
    private final ObservableList<SensorReading>  sensorRows  = FXCollections.observableArrayList();
    private final ObservableList<SensorReading>  liveFeedRows= FXCollections.observableArrayList();
    private final List<SensorReading>            lastSensorBatch = new ArrayList<>();

    //controllers
    private SimulationController simCtrl;
    private SimulationController.SensorController     sensorCtrl;
    private SimulationController.AnalysisController   analysisCtrl;
    private SimulationController.SummaryController    summaryCtrl;
    private SimulationController.FileController       fileCtrl;
    private SimulationController.PowerBIController    pbiCtrl;
    private SimulationController.DashboardController  dashCtrl;
    private boolean liveTickerStarted = false;

//ui components
    private StackPane contentArea;
    private Label     statusBar;
    private final Map<String, Node> panels = new LinkedHashMap<>();

  //color definitions
    static final String BG     = "#060D1F";
    static final String PANEL  = "#0A1628";
    static final String CARD   = "#0D1E36";
    static final String CARD2  = "#112240";
    static final String BORDER = "#1C3354";
    static final String ACCENT = "#00C8FF";
    static final String GREEN  = "#00E5A0";
    static final String YELLOW = "#FFD060";
    static final String RED    = "#FF4060";
    static final String PURPLE = "#B06EFF";
    static final String ORANGE = "#FF8C42";
    static final String TEXT   = "#E8F4FD";
    static final String MUTED  = "#4A7FA5";
    static final String DIM    = "#2A4A6A";

  //abstract method to launch the application
    @Override
    public void start(Stage stage) {
        initControllers();
        logger.event("M6 JavaFX started — clean architecture build");

        BorderPane root = new BorderPane();
        root.setStyle("-fx-background-color:" + BG + ";");
        root.setTop(buildTopBar());
        root.setLeft(buildSidebar());
        root.setCenter(buildCenter());
        root.setBottom(buildStatusBar());
//build panels 
        panels.put("dashboard",  buildDashboard());
        panels.put("simulation", buildSimulation());
        panels.put("livedata",   buildLiveData());
        panels.put("summary",    buildSummary());
        panels.put("analysis",   buildAnalysis());
        panels.put("files",      buildFiles());
        panels.put("log",        buildLog());
        panels.put("sensors",    buildSensors());
        panels.put("powerbi",    buildPowerBI());

        switchPanel("dashboard");

        Scene scene = new Scene(root, 1380, 820);
        stage.setTitle("JKUAT Weather & Environmental Data System — M6");
        stage.setScene(scene);
        stage.setMinWidth(1100);
        stage.setMinHeight(680);
        stage.show();

        loadSavedDataset();
    }

    private void loadSavedDataset() {
        File csv = new File(Cfg.CSV_FILE);
        if (!csv.exists()) {
            status("Clean startup — no saved data found.");
            return;
        }
        try {
            String msg = fileCtrl.load();
            status(msg);
            dashCtrl.refreshDashboard(panels.get("dashboard"));
            summaryCtrl.refreshSummary(panels.get("summary"));
            analysisCtrl.runAnalysis(panels.get("analysis"));
        } catch (Exception ex) {
            status("Could not load saved data: " + ex.getMessage());
        }
    }

    private void saveDataset(String origin) {
        if (dataset.isEmpty()) return;
        try {
            String msg = fileCtrl.save();
            status("Auto-saved after " + origin + ": " + dataset.count() + " rows.");
        } catch (Exception ex) {
            status("Auto-save failed: " + ex.getMessage());
        }
    }

    //initialize controllers with shared state and UI update callbacks
    private void initControllers() {
        simCtrl      = new SimulationController(dataset, readingRows, logger,
                            () -> dashCtrl.refreshDashboard(panels.get("dashboard")));
        sensorCtrl   = new SimulationController.SensorController(sensorRows, lastSensorBatch, logger);
        analysisCtrl = new SimulationController.AnalysisController(dataset);
        summaryCtrl  = new SimulationController.SummaryController(dataset);
        fileCtrl     = new SimulationController.FileController(dataset, readingRows, fileHandler, logger,
                            () -> dashCtrl.refreshDashboard(panels.get("dashboard")));
        pbiCtrl      = new SimulationController.PowerBIController(dataset, readingRows, logger,
                            () -> dashCtrl.refreshDashboard(panels.get("dashboard")));
        dashCtrl     = new SimulationController.DashboardController(dataset, liveFeedRows, logger);
    }

  //top bar
    private Node buildTopBar() {
        HBox bar = new HBox(14);
        bar.setPadding(new Insets(0, 24, 0, 20));
        bar.setAlignment(Pos.CENTER_LEFT);
        bar.setMinHeight(46);
        bar.setStyle("-fx-background-color:" + PANEL +
                     "; -fx-border-color:" + BORDER + "; -fx-border-width:0 0 1 0;");

        Circle pulse = new Circle(4, Color.web(ACCENT));
        FadeTransition ft = new FadeTransition(Duration.millis(800), pulse);
        ft.setFromValue(1); ft.setToValue(0.15); ft.setAutoReverse(true);
        ft.setCycleCount(-1); ft.play();

        Label title = lbl(Cfg.SYSTEM_NAME, 13, ACCENT, true);
        title.setStyle(title.getStyle() + "-fx-font-family:'Courier New'; -fx-letter-spacing:2;");
        Label ver     = lbl("v6.0", 11, MUTED, false);
        Label station = lbl(Cfg.STATION_ID + " | " + Cfg.LOCATION, 11, MUTED, false);
        Region sp     = new Region(); HBox.setHgrow(sp, Priority.ALWAYS);

        Label clock = lbl("", 13, GREEN, true);
        clock.setStyle(clock.getStyle() + "-fx-font-family:'Courier New';");
        Timeline clockTL = new Timeline(new KeyFrame(Duration.seconds(1),
            e -> clock.setText(LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss")))));
        clockTL.setCycleCount(-1); clockTL.play();

        HBox liveBadge = new HBox(5); liveBadge.setAlignment(Pos.CENTER);
        liveBadge.setPadding(new Insets(3, 10, 3, 10));
        liveBadge.setStyle("-fx-background-color:#001A0D; -fx-border-color:" + GREEN +
                           "; -fx-border-radius:20; -fx-background-radius:20; -fx-border-width:1;");
        Circle dot2 = new Circle(3, Color.web(GREEN));
        FadeTransition ft2 = new FadeTransition(Duration.millis(1200), dot2);
        ft2.setFromValue(1); ft2.setToValue(0.3); ft2.setAutoReverse(true);
        ft2.setCycleCount(-1); ft2.play();
        liveBadge.getChildren().addAll(dot2, lbl("LIVE", 10, GREEN, true));

        bar.getChildren().addAll(pulse, title, ver, new Label("  "), station, sp, clock, new Label("  "), liveBadge);
        return bar;
    }

//side bar & navigation
    private Node buildSidebar() {
        VBox sb = new VBox(2);
        sb.setPrefWidth(200);
        sb.setPadding(new Insets(16, 6, 16, 6));
        sb.setStyle("-fx-background-color:" + PANEL +
                    "; -fx-border-color:" + BORDER + "; -fx-border-width:0 1 0 0;");

        Label nav = new Label("NAVIGATION");
        nav.setStyle("-fx-text-fill:" + DIM + "; -fx-font-size:8; -fx-font-weight:bold;" +
                     "-fx-font-family:'Courier New'; -fx-letter-spacing:4; -fx-padding:0 8 12 10;");
        sb.getChildren().add(nav);

        String[][] items = {
            {"dashboard",  "DASHBOARD"},
            {"simulation", "SIMULATION"},
            {"livedata",   "LIVE ENTRY"},
            {"summary",    "ALERTS"},
            {"analysis",   "ANALYTICS"},
            {"files",      "FILE HANDLING"},
            {"log",        "SYSTEM LOG"},
            {"sensors",    "SENSORS"},
            {"powerbi",    "POWER BI"},
        };
        for (String[] item : items) sb.getChildren().add(navBtn(item[0], item[1]));
        return sb;
    }

    private Button navBtn(String panelId, String label) {
        Button b = new Button(label);
        b.setMaxWidth(Double.MAX_VALUE);
        b.setAlignment(Pos.CENTER_LEFT);
        b.setStyle(navStyleOff());
        b.setOnAction(e -> switchPanel(panelId));
        b.setOnMouseEntered(e -> b.setStyle(navStyleOn()));
        b.setOnMouseExited(e  -> b.setStyle(navStyleOff()));
        return b;
    }

    private String navStyleOff() {
        return "-fx-background-color:transparent; -fx-text-fill:" + MUTED +
               "; -fx-font-size:11; -fx-font-weight:bold; -fx-font-family:'Courier New';" +
               "-fx-letter-spacing:1; -fx-padding:9 12; -fx-cursor:hand; -fx-background-radius:6;";
    }
    private String navStyleOn() {
        return "-fx-background-color:" + CARD2 + "; -fx-text-fill:" + ACCENT +
               "; -fx-font-size:11; -fx-font-weight:bold; -fx-font-family:'Courier New';" +
               "-fx-letter-spacing:1; -fx-padding:9 12; -fx-cursor:hand; -fx-background-radius:0 6 6 0;" +
               "-fx-border-color:" + ACCENT + "; -fx-border-width:0 0 0 2; -fx-border-radius:0;";
    }

  //center content area
    private StackPane buildCenter() {
        contentArea = new StackPane();
        contentArea.setStyle("-fx-background-color:" + BG + ";");
        return contentArea;
    }

    private void switchPanel(String id) {
        Node p = panels.get(id);
        if (p == null) return;
        contentArea.getChildren().setAll(p);
        FadeTransition ft = new FadeTransition(Duration.millis(120), p);
        ft.setFromValue(0); ft.setToValue(1); ft.play();
    }

    private Node buildStatusBar() {
        HBox bar = new HBox();
        bar.setPadding(new Insets(4, 16, 4, 16));
        bar.setStyle("-fx-background-color:" + PANEL +
                     "; -fx-border-color:" + BORDER + "; -fx-border-width:1 0 0 0;");
        statusBar = lbl("Ready", 10, MUTED, false);
        statusBar.setStyle(statusBar.getStyle() + "-fx-font-family:'Courier New';");
        bar.getChildren().add(statusBar);
        return bar;
    }

    private void status(String msg) {
        Platform.runLater(() -> statusBar.setText(msg));
        logger.info(msg);
    }

  //live sensor feed
    private void startLiveSensorTicker() {
        Random rng = new Random();
        String[][] SENSORS = ConcurrentSensorFeed.SENSORS;
        Timeline ticker = new Timeline(new KeyFrame(Duration.millis(900), e -> {
            String[] s  = SENSORS[rng.nextInt(SENSORS.length)];
            double   lo = Double.parseDouble(s[2]), hi = Double.parseDouble(s[3]);
            double   val = Math.round((lo + rng.nextDouble() * (hi - lo)) * 100) / 100.0;
            String   ts  = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss"));
            AlertLevel al = AlertLevel.classify(s[1], val);
            SensorReading sr = new SensorReading(s[0], s[1], val, s[4], ts, al);
            dashCtrl.pushLiveSensorReading(sr);
            dashCtrl.updateLiveFeed(panels.get("dashboard"));
        }));
        ticker.setCycleCount(-1);
        ticker.play();
    }

//simulation panel
    private Node buildSimulation() {
        VBox v = vbx(14, 24);
        v.getChildren().addAll(
            lbl("7-DAY SIMULATION", 20, TEXT, true),
            lbl("Pre-loaded JKUAT Main Farm dataset — M1 computational data", 12, MUTED, false),
            new HBox(12,
                accentBtn("RUN SIMULATION", ACCENT, this::runSimulation),
                accentBtn("LOAD REAL DATA", GREEN,   this::loadRealData),
                accentBtn("CLEAR DATA",     RED,    () -> {
                    dataset.clear(); readingRows.clear();
                    status("Dataset cleared.");
                })));

        TableView<WeatherReading> tbl = new TableView<>(readingRows);
        styleTbl(tbl); VBox.setVgrow(tbl, Priority.ALWAYS); tbl.setMinHeight(260);
        tbl.getColumns().addAll(
            col("Day",       100, d -> new SimpleStringProperty(d.getValue().getDay())),
            col("Temp (°C)",  90, d -> new SimpleStringProperty(String.format("%.1f", d.getValue().getTemp()))),
            col("Humidity%",  90, d -> new SimpleStringProperty(String.format("%.0f", d.getValue().getHumidity()))),
            col("Rain (mm)",  90, d -> new SimpleStringProperty(String.format("%.1f", d.getValue().getRainfall()))),
            col("Wind km/h",  90, d -> new SimpleStringProperty(String.format("%.1f", d.getValue().getWindSpeed()))),
            col("Dir",        55, d -> new SimpleStringProperty(d.getValue().getWindDir())),
            col("AQI",        55, d -> new SimpleStringProperty(String.valueOf(d.getValue().getAqi()))),
            col("Status",    100, d -> new SimpleStringProperty(d.getValue().getOverallStatus()))
        );

        BarChart<String,Number> chart = new BarChart<>(xAx("Day"), yAx("Value"));
        chart.setTitle("Temperature vs Rainfall by Day");
        chart.setPrefHeight(240); chart.setId("sim_chart"); styleChart(chart);

        Label sumLbl = lbl("", 12, MUTED, false); sumLbl.setId("sim_sum"); sumLbl.setWrapText(true);
        v.getChildren().addAll(tbl, sumLbl, chart);
        ScrollPane sc = scr(); sc.setContent(v); return sc;
    }

    private void loadRealData() {
        Task<Void> task = simCtrl.buildOpenMeteoTask(panels.get("simulation"));
        task.setOnSucceeded(e -> {
            status("Open-Meteo data loaded — " + dataset.count() + " days.");
            saveDataset("Open-Meteo load");
        });
        task.setOnFailed(e -> status("Open-Meteo failed: " + task.getException().getMessage()));
        new Thread(task, "OpenMeteoThread").start();
        status("Fetching real data from Open-Meteo...");
    }

  //simulate data loading with background task and UI updates
    private void runSimulation() {
        Task<Void> task = simCtrl.buildTask(panels.get("simulation"));
        task.setOnSucceeded(e -> {
            status("Simulation complete — " + dataset.count() + " days loaded.");
            if (!liveTickerStarted) {
                startLiveSensorTicker();
                liveTickerStarted = true;
            }
        });
        new Thread(task, "SimThread").start();
        status("Running simulation...");
    }

   //dashboard panel
    private Node buildDashboard() {
        VBox root = new VBox(0);
        root.setStyle("-fx-background-color:" + BG + ";");

        // Row 1
        HBox heroRow = new HBox(0); heroRow.setPrefHeight(145);

        VBox heroLeft = new VBox(4); heroLeft.setPadding(new Insets(20, 30, 16, 24));
        heroLeft.setStyle("-fx-background-color:" + CARD + "; -fx-border-color:" + BORDER + "; -fx-border-width:0 1 1 0;");
        HBox.setHgrow(heroLeft, Priority.ALWAYS);

        Label cloudIcon = new Label("⛅"); cloudIcon.setStyle("-fx-font-size:38; -fx-opacity:0.7;");
        Label tempBig   = new Label("—°C"); tempBig.setId("dash_tempbig");
        tempBig.setStyle("-fx-text-fill:" + TEXT + "; -fx-font-size:42; -fx-font-weight:bold;");
        Label condition = new Label("No data yet"); condition.setId("dash_condition");
        condition.setStyle("-fx-text-fill:" + MUTED + "; -fx-font-size:13;");
        HBox iconRow = new HBox(16, cloudIcon, new VBox(0, tempBig, condition));
        iconRow.setAlignment(Pos.CENTER_LEFT);

        Label locLbl = lbl("Juja, Kiambu County", 11, ACCENT, false);
        Label daySep = lbl("•", 11, DIM, false);
        Label dayLbl = lbl(LocalDate.now().getDayOfWeek().getDisplayName(TextStyle.FULL, Locale.ENGLISH), 11, MUTED, false);
        HBox locationRow = new HBox(8, locLbl, daySep, dayLbl); locationRow.setAlignment(Pos.CENTER_LEFT);
        heroLeft.getChildren().addAll(iconRow, locationRow);

        VBox heroRight = new VBox(6); heroRight.setPrefWidth(260);
        heroRight.setPadding(new Insets(16, 20, 16, 20));
        heroRight.setStyle("-fx-background-color:" + CARD2 + "; -fx-border-color:" + BORDER + "; -fx-border-width:0 0 1 0;");
        VBox alertsBox = new VBox(6); alertsBox.setId("dash_alertsbox");
        alertsBox.getChildren().add(lbl("Run simulation to see alerts", 11, MUTED, false));
        Label alertCount = lbl("", 10, YELLOW, false); alertCount.setId("dash_alertcount");
        heroRight.getChildren().addAll(lbl("ALERTS", 9, MUTED, true), alertsBox, alertCount);
        heroRow.getChildren().addAll(heroLeft, heroRight);

        // Row 2 
        HBox kpiStrip = new HBox(0); kpiStrip.setPrefHeight(72);
        kpiStrip.getChildren().addAll(
            kpiCell("AVG TEMP",   "—", "°C",    RED,    "dash_kpi_temp"),
            kpiCell("TOTAL RAIN", "—", "mm",    ACCENT, "dash_kpi_rain"),
            kpiCell("PEAK WIND",  "—", "km/h",  ORANGE, "dash_kpi_wind"),
            kpiCell("PEAK AQI",   "—", "",      PURPLE, "dash_kpi_aqi")
        );

        // Row 3  Alert banner
        HBox alertBanner = new HBox(10); alertBanner.setAlignment(Pos.CENTER_LEFT);
        alertBanner.setPadding(new Insets(10, 20, 10, 20));
        alertBanner.setStyle("-fx-background-color:#1A0510; -fx-border-color:" + RED + "; -fx-border-width:0 0 0 3;");
        alertBanner.setId("dash_banner"); alertBanner.setVisible(false); alertBanner.setManaged(false);
        Label bannerMsg = new Label(); bannerMsg.setId("dash_bannermsg");
        bannerMsg.setStyle("-fx-text-fill:" + TEXT + "; -fx-font-size:11; -fx-font-family:'Courier New';");
        Label bannerDot = lbl("●", 10, RED, false);
        Label bannerLbl = lbl("CRITICAL", 10, RED, true);
        alertBanner.getChildren().addAll(bannerDot, bannerLbl, bannerMsg);

        // Row 4  Forecast row
        HBox forecastRow = new HBox(0); forecastRow.setPrefHeight(110); forecastRow.setId("dash_forecastrow");
        forecastRow.setStyle("-fx-background-color:" + CARD + "; -fx-border-color:" + BORDER + "; -fx-border-width:0 0 1 0;");
        forecastRow.getChildren().add(lbl("Run simulation to see 7-day forecast", 12, MUTED, false));

        // Row 5 Chart & sensor feed
        HBox bottomRow = new HBox(0); VBox.setVgrow(bottomRow, Priority.ALWAYS);

        VBox chartArea = new VBox(0); HBox.setHgrow(chartArea, Priority.ALWAYS);
        chartArea.setStyle("-fx-background-color:" + CARD + "; -fx-border-color:" + BORDER + "; -fx-border-width:0 1 0 0;");

        BarChart<String,Number> barChart = new BarChart<>(xAx("Day"), yAx("Value"));
        barChart.setTitle(null); barChart.setLegendVisible(false);
        barChart.setStyle("-fx-background-color:transparent; -fx-plot-background-color:" + CARD + "; -fx-padding:0;");
        barChart.setId("dash_chart"); VBox.setVgrow(barChart, Priority.ALWAYS);
        chartArea.getChildren().add(barChart);

        VBox sensorPanel = new VBox(0); sensorPanel.setPrefWidth(330);
        sensorPanel.setStyle("-fx-background-color:" + CARD2 + ";");
        HBox sfHeader = new HBox(8, lbl("⚡", 12, YELLOW, false), lbl("Sensor feed", 11, TEXT, true), lbl("(live)", 10, GREEN, false));
        sfHeader.setAlignment(Pos.CENTER_LEFT); sfHeader.setPadding(new Insets(10, 16, 10, 16));
        sfHeader.setStyle("-fx-border-color:" + BORDER + "; -fx-border-width:0 0 1 0;");
        VBox feedList = new VBox(0); feedList.setId("dash_feedlist");
        sensorPanel.getChildren().addAll(sfHeader, feedList);
        bottomRow.getChildren().addAll(chartArea, sensorPanel);

        root.getChildren().addAll(heroRow, kpiStrip, alertBanner, forecastRow, bottomRow);
        ScrollPane sc = new ScrollPane(root); sc.setFitToWidth(true);
        sc.setStyle("-fx-background-color:transparent; -fx-background:transparent;");
        return sc;
    }

    private HBox kpiCell(String label, String val, String unit, String col, String id) {
        HBox cell = new HBox(); HBox.setHgrow(cell, Priority.ALWAYS);
        cell.setAlignment(Pos.CENTER_LEFT); cell.setPadding(new Insets(12, 20, 12, 20));
        cell.setStyle("-fx-background-color:" + CARD2 + "; -fx-border-color:" + BORDER + "; -fx-border-width:0 1 1 0;");
        VBox txt  = new VBox(1);
        Label lLbl = lbl(label, 9, MUTED, true); lLbl.setStyle(lLbl.getStyle() + "-fx-font-family:'Courier New'; -fx-letter-spacing:1;");
        Label vLbl = lbl(val + unit, 24, col, true); vLbl.setId(id);
        txt.getChildren().addAll(lLbl, vLbl);
        cell.getChildren().add(txt);
        return cell;
    }

 //live data entry panel
    private Node buildLiveData() {
        ScrollPane sc = scr(); VBox v = vbx(20, 24); v.setMaxWidth(720);
        v.getChildren().addAll(
            lbl("ENTER LIVE DATA", 20, TEXT, true),
            lbl("Add a single weather reading — validated per M2 control logic", 12, MUTED, false));

        ComboBox<String> dayBox = new ComboBox<>(FXCollections.observableArrayList(Cfg.VALID_DAYS));
        dayBox.setPromptText("Select day"); dayBox.setStyle(fldStyle());
        TextField tempF = fld("Temperature (°C)  -50 to 60");
        TextField humF  = fld("Humidity (%)     0 to 100");
        TextField rainF = fld("Rainfall (mm)    >= 0");
        TextField windF = fld("Wind Speed (km/h) >= 0");
        ComboBox<String> dirBox = new ComboBox<>(FXCollections.observableArrayList(Cfg.VALID_DIRS));
        dirBox.setPromptText("Wind direction"); dirBox.setStyle(fldStyle());
        TextField aqiF = fld("AQI  0 to 500");

        Label errLbl = lbl("", 12, RED,   false);
        Label okLbl  = lbl("", 12, GREEN, false);

        Button addBtn = accentBtn("ADD READING", ACCENT, () -> {
            errLbl.setText(""); okLbl.setText("");
            try {
                if (dayBox.getValue() == null) throw new ValidationException("Please select a day.");
                FarmerAlert r = new FarmerAlert(
                    dayBox.getValue(),
                    pf(tempF, "Temperature"), pf(humF, "Humidity"),
                    pf(rainF, "Rainfall"),    pf(windF, "Wind Speed"),
                    dirBox.getValue() == null ? "N" : dirBox.getValue(),
                    (int) pf(aqiF, "AQI"));
                dataset.add(r); readingRows.add(r);
                    saveDataset("manual entry");
        grid.addRow(3, flbl("Rainfall"),       rainF);
        grid.addRow(4, flbl("Wind Speed"),     windF);
        grid.addRow(5, flbl("Wind Direction"), dirBox);
        grid.addRow(6, flbl("AQI"),            aqiF);
        ColumnConstraints cc1 = new ColumnConstraints(150);
        ColumnConstraints cc2 = new ColumnConstraints(); cc2.setHgrow(Priority.ALWAYS);
        grid.getColumnConstraints().addAll(cc1, cc2);
        v.getChildren().addAll(grid, errLbl, okLbl, addBtn);
        sc.setContent(v); return sc;
    }

    private void showReadingDialog(WeatherReading r) {
        Alert a = new Alert(Alert.AlertType.INFORMATION);
        a.setTitle("Reading Report — " + r.getDay());
        a.setHeaderText("Status: " + r.getOverallStatus());
        a.setContentText(String.format(
            "Temperature  : %.1f°C  (Heat Index: %.1f°C | Kelvin: %.2fK)\n" +
            "Humidity     : %.1f%%\nRainfall     : %.1fmm  (Deficit: %.1fmm)\n" +
            "Wind         : %.1fkm/h %s\nAQI          : %d\n" +
            "Dew Point    : %.1f°C\nEvapotransp. : %.2fmm/day\n\n" +
            r.tempStatus() + "\n" + r.rainStatus() + "\n" + r.humidityStatus() + "\n" +
            r.windStatus() + "\n" + r.aqiStatus() +
            (r instanceof FarmerAlert fa ? "\n\nFARMER ADVICE:\n" + fa.farmerAdvice() : ""),
            r.getTemp(), r.getHeatIndex(), r.getKelvin(), r.getHumidity(),
            r.getRainfall(), r.getWaterDeficit(), r.getWindSpeed(), r.getWindDir(),
            r.getAqi(), r.getDewPoint(), r.getEvap()));
        a.showAndWait();
    }

//summary & alerts panel
    private Node buildSummary() {
        VBox v = vbx(16, 24);
        v.getChildren().addAll(
            lbl("SUMMARY & ALERTS", 20, TEXT, true),
            lbl("Full dataset summary with FarmerAlert advice — M3 inheritance", 12, MUTED, false),
            accentBtn("GENERATE SUMMARY", ACCENT, () -> {
                if (dataset.isEmpty()) { showInfo("No data", "Run simulation first."); return; }
                summaryCtrl.refreshSummary(panels.get("summary"));
                status("Summary refreshed — " + dataset.count() + " readings.");
            }));

        GridPane stats = new GridPane(); stats.setHgap(32); stats.setVgap(8); stats.setId("sum_stats");
        Label critLbl = lbl("", 12, MUTED, false); critLbl.setId("sum_crit"); critLbl.setWrapText(true);
        TextArea alertArea = new TextArea("Run summary to see farmer alerts.");
        alertArea.setEditable(false); alertArea.setPrefHeight(220); alertArea.setWrapText(true);
        alertArea.setStyle("-fx-background-color:" + CARD2 + "; -fx-text-fill:" + YELLOW +
                           "; -fx-font-family:'Courier New'; -fx-font-size:12;");
        alertArea.setId("sum_alerts");
        PieChart pie = new PieChart(); pie.setTitle("Status Distribution");
        pie.setPrefHeight(230); pie.setId("sum_pie"); styleChart(pie);
        v.getChildren().addAll(stats, critLbl,
            lbl("FARMER ALERTS (FarmerAlert — M3 inheritance)", 13, TEXT, true),
            alertArea, pie);
        ScrollPane sc = scr(); sc.setContent(v); return sc;
    }

   //analysis panel
    private Node buildAnalysis() {
        VBox v = vbx(16, 24);
        v.getChildren().addAll(
            lbl("DATASET ANALYSIS", 20, TEXT, true),
            lbl("Functional analytics — map/reduce/filter/sorted with lambdas (M5)", 12, MUTED, false),
            accentBtn("RUN ANALYSIS", ACCENT, () -> {
                if (dataset.isEmpty()) { showInfo("No data", "Run simulation first."); return; }
                analysisCtrl.runAnalysis(panels.get("analysis"));
                status("Analysis complete — " + dataset.count() + " readings.");
            }));

        LineChart<String,Number> line = new LineChart<>(xAx("Day"), yAx("Value"));
        line.setTitle("Weekly Trends"); line.setPrefHeight(270); line.setId("an_line"); styleChart(line);

        TableView<String[]> stbl = new TableView<>(); stbl.setPrefHeight(300); stbl.setId("an_table"); styleTbl(stbl);
        stbl.getColumns().addAll(
            col("Metric (M5 Operation)", 300, d -> new SimpleStringProperty(d.getValue()[0])),
            col("Value",                 200, d -> new SimpleStringProperty(d.getValue()[1]))
        );
        stbl.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY);

        Label sortedLbl = lbl("", 12, MUTED, false); sortedLbl.setId("an_sorted"); sortedLbl.setWrapText(true);
        v.getChildren().addAll(line, stbl, sortedLbl);
        ScrollPane sc = scr(); sc.setContent(v); return sc;
    }

   //file handling panel
    private Node buildFiles() {
        VBox v = vbx(20, 24);
        v.getChildren().addAll(
            lbl("FILE HANDLING", 20, TEXT, true),
            lbl("CSV save/load — M4 WeatherFileHandler | " + Cfg.CSV_FILE, 12, MUTED, false));

        Label fb = lbl("", 13, GREEN, false); fb.setWrapText(true);

        // Buttons 
        Button saveBtn = accentBtn("SAVE TO CSV", GREEN, () -> {
            try {
                String msg = fileCtrl.save();
                fb.setText(msg); fb.setStyle("-fx-text-fill:" + GREEN + "; -fx-font-size:13;");
                status("CSV saved.");
            } catch (Exception e) {
                fb.setText("ERROR: " + e.getMessage()); fb.setStyle("-fx-text-fill:" + RED + "; -fx-font-size:13;");
            }
        });
        Button loadBtn = accentBtn("LOAD FROM CSV", ACCENT, () -> {
            try {
                String msg = fileCtrl.load();
                fb.setText(msg); fb.setStyle("-fx-text-fill:" + GREEN + "; -fx-font-size:13;");
                status("CSV loaded.");
            } catch (Exception e) {
                fb.setText("ERROR: " + e.getMessage()); fb.setStyle("-fx-text-fill:" + RED + "; -fx-font-size:13;");
            }
        });

        VBox fileInfo = card("FILE INFORMATION", "");
        Button refBtn = accentBtn("REFRESH", MUTED, () -> {
            File f = new File(Cfg.CSV_FILE); fileInfo.getChildren().clear();
            fileInfo.getChildren().add(lbl("FILE INFORMATION", 13, TEXT, true));
            fileInfo.getChildren().add(lbl(f.exists()
                ? "Path: " + f.getAbsolutePath() + "\nSize: " + f.length() + " bytes"
                : "No CSV saved yet.", 12, MUTED, false));
        });
        v.getChildren().addAll(new HBox(12, saveBtn, loadBtn, refBtn), fb, fileInfo);
        ScrollPane sc = scr(); sc.setContent(v); return sc;
    }

    //system log panel
    private Node buildLog() {
        VBox v = vbx(12, 24);
        v.getChildren().addAll(
            lbl("SYSTEM LOG", 20, TEXT, true),
            lbl("WeatherLogger (M4) — auto-refreshes every 5s | " + Cfg.LOG_FILE, 12, MUTED, false));
        TextArea ta = new TextArea(); ta.setEditable(false); ta.setWrapText(false);
        VBox.setVgrow(ta, Priority.ALWAYS); ta.setPrefHeight(520);
        ta.setStyle("-fx-background-color:#030810; -fx-text-fill:" + GREEN +
                    "; -fx-font-family:'Courier New'; -fx-font-size:11;");
        Button ref = accentBtn("REFRESH", ACCENT, () -> { ta.setText(logger.readAll()); ta.setScrollTop(Double.MAX_VALUE); });
        Button clr = accentBtn("CLEAR VIEW", MUTED, () -> ta.clear());
        Timeline autoRefresh = new Timeline(new KeyFrame(Duration.seconds(5), e -> {
            String txt = String.join("\n", logger.recent(100));
            if (!txt.equals(ta.getText())) { ta.setText(txt); ta.setScrollTop(Double.MAX_VALUE); }
        }));
        autoRefresh.setCycleCount(-1); autoRefresh.play();
        v.getChildren().addAll(new HBox(12, ref, clr), ta);
        ScrollPane sc = scr(); sc.setContent(v); return sc;
    }

    //concurrent sensor feed panel
    private Node buildSensors() {
        VBox v = vbx(16, 24);
        v.getChildren().addAll(
            lbl("CONCURRENT SENSOR SIMULATION", 20, TEXT, true),
            lbl("7 sensor threads in parallel — M5 multithreading + SensorBuffer<T> generics", 12, MUTED, false));

        VBox sCard = card("AVAILABLE SENSORS", "");
        for (String[] s : ConcurrentSensorFeed.SENSORS) {
            HBox row = new HBox(12); row.setAlignment(Pos.CENTER_LEFT);
            Label idLbl = lbl(s[0], 11, ACCENT, true); idLbl.setMinWidth(130);
            Label prLbl = lbl(s[1], 11, TEXT,   false); prLbl.setMinWidth(100);
            Label rnLbl = lbl("[" + s[2] + " – " + s[3] + " " + s[4] + "]", 11, MUTED, false);
            row.getChildren().addAll(idLbl, lbl("→", 11, DIM, false), prLbl, rnLbl);
            sCard.getChildren().add(row);
        }

        Spinner<Integer> sensorSpin = new Spinner<>(1, 7,   7);   sensorSpin.setEditable(true); sensorSpin.setStyle(fldStyle());
        Spinner<Integer> readSpin   = new Spinner<>(1, 200, 200); readSpin.setEditable(true);   readSpin.setStyle(fldStyle());
        Label statusLbl = lbl("Status: IDLE", 12, MUTED, false);

        Button runBtn = accentBtn("START SENSORS", ACCENT, () -> {
            Node sPanel = panels.get("sensors");
            Task<List<SensorReading>> t = sensorCtrl.buildTask(
                sensorSpin.getValue(), readSpin.getValue(), statusLbl, sPanel);
            t.setOnSucceeded(e -> status("Sensor run complete — " + sensorRows.size() + " readings."));
            new Thread(t, "SensorThread").start();
        });

        HBox ctrl = new HBox(14, flbl("Sensors:"), sensorSpin, flbl("Readings/sensor:"), readSpin, runBtn, statusLbl);
        ctrl.setAlignment(Pos.CENTER_LEFT);

        TableView<SensorReading> tbl = new TableView<>(sensorRows);
        styleTbl(tbl); tbl.setMinHeight(300); VBox.setVgrow(tbl, Priority.ALWAYS);
        tbl.getColumns().addAll(
            col("Timestamp", 120, d -> new SimpleStringProperty(d.getValue().timestamp)),
            col("Sensor",    140, d -> new SimpleStringProperty(d.getValue().sensorId)),
            col("Parameter", 110, d -> new SimpleStringProperty(d.getValue().parameter)),
            col("Value",      80, d -> new SimpleStringProperty(String.format("%.2f", d.getValue().value))),
            col("Unit",       60, d -> new SimpleStringProperty(d.getValue().unit)),
            col("Alert",     100, d -> new SimpleStringProperty(d.getValue().alertLevel.label))
        );

        HBox alertBar = new HBox(12); alertBar.setId("sns_bar");
        Button expBtn = accentBtn("EXPORT SENSOR CSV", GREEN, () -> sensorCtrl.exportCsv());
        v.getChildren().addAll(sCard, ctrl, tbl, alertBar, expBtn);
        ScrollPane sc = scr(); sc.setContent(v); return sc;
    }

   //power BI export panel
    private Node buildPowerBI() {
        ScrollPane sc = scr(); VBox v = vbx(20, 24);
        v.getChildren().addAll(
            lbl("POWER BI EXPORT", 20, TEXT, true),
            lbl("Generate 1000-row enriched CSV — open directly in Power BI Desktop", 12, MUTED, false));

        VBox optCard = card("SELECT EXPORT SOURCE", "");
        ToggleGroup tg = new ToggleGroup();
        RadioButton rbA = radio("A  —  Export current session data", tg);
        RadioButton rbB = radio("B  —  Fetch REAL data from Open-Meteo API  (internet required)", tg);
        RadioButton rbC = radio("C  —  Generate 1000 realistic rows  (offline fallback)", tg);
        rbC.setSelected(true);
        optCard.getChildren().addAll(rbA, rbB, rbC);

        Label fb = lbl("", 12, GREEN, false); fb.setWrapText(true);
        ProgressBar pb = new ProgressBar(0); pb.setPrefWidth(500); pb.setVisible(false);

        Button expBtn = accentBtn("EXPORT TO POWER BI CSV", YELLOW, () -> {
            pb.setVisible(true); pb.setProgress(-1); fb.setText("Working...");
            if (rbA.isSelected() && dataset.isEmpty()) {
                pb.setVisible(false);
                fb.setText("ERROR: No data loaded. Run simulation first.");
                fb.setStyle("-fx-text-fill:" + RED + "; -fx-font-size:12;"); return;
            }

            Task<String> task = rbA.isSelected()
                ? pbiCtrl.buildSessionTask()
                : pbiCtrl.buildExportTask(rbB.isSelected());

            task.setOnSucceeded(e -> Platform.runLater(() -> {
                pb.setVisible(false); pb.setProgress(1);
                fb.setStyle("-fx-text-fill:" + GREEN + "; -fx-font-size:12;");
                fb.setText("Exported to:\n" + task.getValue() +
                    "\n\nTo open in Power BI: Home → Get Data → Text/CSV → select the file");
                status("Power BI export complete.");
            }));
            task.setOnFailed(e -> Platform.runLater(() -> {
                pb.setVisible(false);
                fb.setStyle("-fx-text-fill:" + RED + "; -fx-font-size:12;");
                fb.setText("ERROR: " + task.getException().getMessage() +
                    (rbB.isSelected() ? "\n\nNo internet? Try option C instead." : ""));
            }));
            new Thread(task, "PBIThread").start();
        });

        VBox tip = card("POWER BI QUICK-START", "");
        String[] tips = {
            "1.  Download Power BI Desktop (free):  powerbi.microsoft.com/desktop",
            "2.  Home → Get Data → Text/CSV → select powerbi_weather_export.csv → Load",
            "3.  Suggested visuals:",
            "     Line Chart  :  date (X) vs temperature + rainfall + humidity",
            "     Bar Chart   :  month (X) vs avg temperature / avg rainfall",
            "     Map         :  latitude / longitude, bubble size = AQI",
            "     Slicer      :  season, alert_level, month",
            "     Card        :  Avg Temperature  |  Total Rainfall  |  Critical Day count",
            "     Pie Chart   :  alert_level distribution (NORMAL / WARNING / CRITICAL)",
            "4.  Enriched columns: heat_index, dew_point, evapotranspiration,",
            "     water_deficit, alert_level, overall_status, lat/lon, season, source",
        };
        for (String t : tips) tip.getChildren().add(lbl(t, 11, MUTED, false));
        v.getChildren().addAll(optCard, expBtn, pb, fb, tip);
        sc.setContent(v); return sc;
    }
    
//utility methods
    Label lbl(String t, int sz, String col, boolean bold) {
        Label l = new Label(t);
        l.setStyle("-fx-text-fill:" + col + "; -fx-font-size:" + sz +
                   (bold ? "; -fx-font-weight:bold; -fx-font-family:'Segoe UI';"
                         : "; -fx-font-family:'Segoe UI';"));
        return l;
    }
    private Label flbl(String t) {
        Label l = lbl(t, 11, MUTED, false);
        l.setStyle(l.getStyle() + "-fx-font-family:'Courier New';"); return l;
    }
    Button accentBtn(String text, String bgColor, Runnable action) {
        Button b = new Button(text);
        b.setStyle("-fx-background-color:" + bgColor + "; -fx-text-fill:" + TEXT +
                   "; -fx-font-size:11; -fx-font-weight:bold; -fx-font-family:'Courier New';" +
                   "-fx-letter-spacing:1; -fx-padding:8 18; -fx-background-radius:5; -fx-cursor:hand;");
        b.setOnMouseEntered(e -> b.setOpacity(0.82));
        b.setOnMouseExited(e  -> b.setOpacity(1.0));
        b.setOnAction(e -> action.run());
        return b;
    }
    private RadioButton radio(String text, ToggleGroup tg) {
        RadioButton rb = new RadioButton(text); rb.setToggleGroup(tg);
        rb.setStyle("-fx-text-fill:" + TEXT + "; -fx-font-size:12;"); return rb;
    }
    VBox card(String title, String subtitle) {
        VBox c = new VBox(8); c.setPadding(new Insets(14));
        c.setStyle("-fx-background-color:" + CARD2 + "; -fx-border-color:" + BORDER +
                   "; -fx-border-width:1; -fx-background-radius:8; -fx-border-radius:8;");
        if (title    != null && !title.isEmpty())    c.getChildren().add(lbl(title,    12, TEXT, true));
        if (subtitle != null && !subtitle.isEmpty()) c.getChildren().add(lbl(subtitle, 10, MUTED, false));
        return c;
    }
    VBox vbx(int sp, int pad) { VBox v = new VBox(sp); v.setPadding(new Insets(pad)); return v; }
    ScrollPane scr() {
        ScrollPane s = new ScrollPane(); s.setFitToWidth(true);
        s.setStyle("-fx-background-color:transparent; -fx-background:transparent;"); return s;
    }
    TextField fld(String prompt) {
        TextField tf = new TextField(); tf.setPromptText(prompt); tf.setStyle(fldStyle()); return tf;
    }
    String fldStyle() {
        return "-fx-background-color:" + CARD2 + "; -fx-text-fill:" + TEXT +
               "; -fx-border-color:" + BORDER + "; -fx-border-radius:4; -fx-background-radius:4;" +
               "-fx-prompt-text-fill:" + MUTED + "; -fx-pref-width:320; -fx-font-family:'Segoe UI';";
    }
    CategoryAxis xAx(String label) {
        CategoryAxis a = new CategoryAxis(); a.setLabel(label); a.setTickLabelFill(Color.web(MUTED)); return a;
    }
    NumberAxis yAx(String label) {
        NumberAxis a = new NumberAxis(); a.setLabel(label); a.setTickLabelFill(Color.web(MUTED)); return a;
    }
    void styleChart(Chart c) {
        c.setStyle("-fx-background-color:" + CARD2 + "; -fx-plot-background-color:" + CARD + ";");
        c.setLegendSide(Side.BOTTOM);
    }
    <T> void styleTbl(TableView<T> t) {
        t.setStyle("-fx-background-color:" + CARD2 + "; -fx-text-fill:" + TEXT +
                   "; -fx-table-cell-border-color:" + BORDER + ";");
        t.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY);
    }
    <T> TableColumn<T,String> col(String title, int w,
            javafx.util.Callback<TableColumn.CellDataFeatures<T,String>,
            javafx.beans.value.ObservableValue<String>> factory) {
        TableColumn<T,String> c = new TableColumn<>(title);
        c.setCellValueFactory(factory); c.setPrefWidth(w); return c;
    }
    double pf(TextField f, String name) {
        try { return Double.parseDouble(f.getText().trim()); }
        catch (NumberFormatException e) { throw new ValidationException(name + " must be a number."); }
    }
    void showInfo(String title, String msg) {
        Platform.runLater(() -> {
            Alert a = new Alert(Alert.AlertType.INFORMATION);
            a.setTitle(title); a.setHeaderText(null); a.setContentText(msg); a.showAndWait();
        });
    }

    public static void main(String[] args) { launch(args); }
}