package jkuat.weather.enums;

/**
 * SystemStatus — represents the current state of the sensor feed pipeline.
 * Displayed in the top bar and sensor panel status label.
 */
public enum SystemStatus {
    IDLE       ("IDLE",        "#607D8B"),
    COLLECTING ("COLLECTING",  "#FFC107"),
    PROCESSING ("PROCESSING",  "#FF5722"),
    READY      ("READY",       "#4CAF50"),
    ERROR      ("ERROR",       "#F44336");

    public final String label;
    public final String color;

    SystemStatus(String l, String c) { label = l; color = c; }
}