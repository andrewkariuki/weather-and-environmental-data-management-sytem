package jkuat.weather.models;

import javafx.beans.property.DoubleProperty;
import javafx.beans.property.SimpleDoubleProperty;
import javafx.beans.property.SimpleStringProperty;
import javafx.beans.property.StringProperty;
import jkuat.weather.enums.AlertLevel;

/**
 * SensorReading — one timestamped reading from a single physical sensor.
 *
 * Holds JavaFX property wrappers (tsProp, idProp, …) so that TableView
 * columns can bind directly — no manual cell factories needed.
 *
 * Created by ConcurrentSensorFeed threads and displayed in:
 *   • SensorController  → full sensor table
 *   • DashboardController → rolling live feed strip
 */
public class SensorReading {

    public final String     sensorId;
    public final String     parameter;
    public final String     unit;
    public final String     timestamp;
    public final double     value;
    public final AlertLevel alertLevel;

    public SensorReading(String id, String param, double val,
                         String unit, String ts, AlertLevel al) {
        this.sensorId   = id;
        this.parameter  = param;
        this.value      = val;
        this.unit       = unit;
        this.timestamp  = ts;
        this.alertLevel = al;
    }

    // ── JavaFX property wrappers for TableView column binding ────────────────
    public StringProperty tsProp()    { return new SimpleStringProperty(timestamp); }
    public StringProperty idProp()    { return new SimpleStringProperty(sensorId); }
    public StringProperty paramProp() { return new SimpleStringProperty(parameter); }
    public DoubleProperty valProp()   { return new SimpleDoubleProperty(value); }
    public StringProperty unitProp()  { return new SimpleStringProperty(unit); }
    public StringProperty alertProp() { return new SimpleStringProperty(alertLevel.label); }
}