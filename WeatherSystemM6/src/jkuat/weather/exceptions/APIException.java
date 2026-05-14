package jkuat.weather.exceptions;

public class APIException extends WeatherSystemException {
    public APIException(String m)              { super(m); }
    public APIException(String m, Throwable c) { super(m, c); }
}
