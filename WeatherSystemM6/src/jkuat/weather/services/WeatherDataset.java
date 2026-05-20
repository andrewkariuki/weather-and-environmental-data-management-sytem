package jkuat.weather.services;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.OptionalDouble;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.stream.Collectors;
import jkuat.weather.models.WeatherModels.WeatherReading;
import jkuat.weather.utils.Cfg;


public class WeatherDataset {

    private final List<WeatherReading> data = new ArrayList<>();

    public void add(WeatherReading r) { data.add(r); }
    public List<WeatherReading> getAll()  { return new ArrayList<>(data); }
    public int     count()   { return data.size(); }
    public boolean isEmpty() { return data.isEmpty(); }
    public void    clear()   { data.clear(); }

    // map and reduce
    public OptionalDouble avgTemp()     { return data.stream().mapToDouble(WeatherReading::getTemp).average(); }
    public OptionalDouble avgHumidity() { return data.stream().mapToDouble(WeatherReading::getHumidity).average(); }
    public double totalRainfall()       { return data.stream().mapToDouble(WeatherReading::getRainfall).sum(); }
    public double maxTemp()             { return data.stream().mapToDouble(WeatherReading::getTemp).max().orElse(0); }
    public double minTemp()             { return data.stream().mapToDouble(WeatherReading::getTemp).min().orElse(0); }
    public double peakWind()            { return data.stream().mapToDouble(WeatherReading::getWindSpeed).max().orElse(0); }
    public int    peakAqi()             { return data.stream().mapToInt(WeatherReading::getAqi).max().orElse(0); }

    // filter and lambda
    public List<WeatherReading> criticalDays() {
        return data.stream().filter(r -> r.getOverallStatus().equals("CRITICAL")).collect(Collectors.toList());
    }
    public List<WeatherReading> dryDays() {
        return data.stream().filter(r -> r.getRainfall() == 0).collect(Collectors.toList());
    }
    public List<WeatherReading> floodDays() {
        return data.stream().filter(r -> r.getRainfall() > Cfg.RAINFALL_HEAVY).collect(Collectors.toList());
    }
    public List<WeatherReading> heatDays() {
        return data.stream().filter(r -> r.getTemp() >= Cfg.TEMP_HEATWAVE).collect(Collectors.toList());
    }
    public List<WeatherReading> diseaseDays() {
        return data.stream().filter(r -> r.getHumidity() > Cfg.HUMIDITY_DISEASE).collect(Collectors.toList());
    }

    // sort
    public List<WeatherReading> sortedByTemp() {
        return data.stream()
                   .sorted(Comparator.comparingDouble(WeatherReading::getTemp).reversed())
                   .collect(Collectors.toList());
    }
    public List<WeatherReading> sortedByRain() {
        return data.stream()
                   .sorted(Comparator.comparingDouble(WeatherReading::getRainfall).reversed())
                   .collect(Collectors.toList());
    }
}


class ThreadSafeDataset {

    private final List<Object>             data = new ArrayList<>();
    private final ReentrantReadWriteLock   lock = new ReentrantReadWriteLock();

    public void add(Object r) {
        lock.writeLock().lock();
        try { data.add(r); }
        finally { lock.writeLock().unlock(); }
    }

    public List<Object> getAll() {
        lock.readLock().lock();
        try { return new ArrayList<>(data); }
        finally { lock.readLock().unlock(); }
    }

    public int count() {
        lock.readLock().lock();
        try { return data.size(); }
        finally { lock.readLock().unlock(); }
    }

    public void clear() {
        lock.writeLock().lock();
        try { data.clear(); }
        finally { lock.writeLock().unlock(); }
    }
}