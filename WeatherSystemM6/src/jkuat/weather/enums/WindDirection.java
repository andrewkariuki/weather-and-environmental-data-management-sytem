package jkuat.weather.enums;

import jkuat.weather.exceptions.ValidationException;

//represents the 8 cardinal 
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