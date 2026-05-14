package jkuat.weather.exceptions;

public class WeatherSystemException extends RuntimeException {
    public WeatherSystemException(String m)              { super(m); }
    public WeatherSystemException(String m, Throwable c) { super(m, c); }
}
