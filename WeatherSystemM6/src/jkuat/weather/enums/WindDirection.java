package jkuat.weather.enums;

import jkuat.weather.exceptions.ValidationException;

/**
 * WindDirection — compass rose directions validated on user input.
 * WindDirection.from(String) is called by the Live Entry panel.
 */
public enum WindDirection {
    N, NE, E, SE, S, SW, W, NW;

    public static WindDirection from(String s) {
        try {
            return valueOf(s.toUpperCase().trim());
        } catch (IllegalArgumentException e) {
            throw new ValidationException("Invalid wind direction: " + s);
        }
    }
}