package jkuat.weather.exceptions;

public class FileHandlingException extends WeatherSystemException {
    public FileHandlingException(String m)              { super(m); }
    public FileHandlingException(String m, Throwable c) { super(m, c); }
}
