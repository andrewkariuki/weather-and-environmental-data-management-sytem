package jkuat.weather.models;

import javafx.beans.property.DoubleProperty;
import javafx.beans.property.SimpleDoubleProperty;
import javafx.beans.property.SimpleStringProperty;
import javafx.beans.property.StringProperty;
import jkuat.weather.enums.AlertLevel;

/// Represents a single sensor reading with all alert level.
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
// JavaFX properties for UI binding
    public StringProperty tsProp()    { return new SimpleStringProperty(timestamp); }
    public StringProperty idProp()    { return new SimpleStringProperty(sensorId); }
    public StringProperty paramProp() { return new SimpleStringProperty(parameter); }
    public DoubleProperty valProp()   { return new SimpleDoubleProperty(value); }
    public StringProperty unitProp()  { return new SimpleStringProperty(unit); }
    public StringProperty alertProp() { return new SimpleStringProperty(alertLevel.label); }
}