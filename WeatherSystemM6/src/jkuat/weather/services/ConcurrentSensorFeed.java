package jkuat.weather.services;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Random;
import java.util.concurrent.locks.ReentrantLock;

import jkuat.weather.enums.AlertLevel;
import jkuat.weather.enums.SystemStatus;
import jkuat.weather.models.SensorReading;
import jkuat.weather.utils.WeatherLogger;

// ============================================================
//  SensorBuffer<T> — generic bounded buffer (M5 generics)
// ============================================================
/**
 * SensorBuffer&lt;T&gt; — bounded, thread-safe buffer for sensor data.
 *
 * Generic type T means the same buffer works for SensorReading today
 * and for any future sensor type without code duplication.
 *
 * Thread safety: ReentrantLock on push() and drain() prevents data races
 * when multiple sensor threads write simultaneously.
 */
class SensorBuffer<T> {

    private final List<T>      buf = new ArrayList<>();
    private final int          cap;
    private final ReentrantLock lock = new ReentrantLock();

    public SensorBuffer(int capacity) { this.cap = capacity; }

    /** Push one item. Returns false (drops item) if buffer is full. */
    public boolean push(T item) {
        lock.lock();
        try {
            if (buf.size() >= cap) return false;
            buf.add(item);
            return true;
        } finally { lock.unlock(); }
    }

    /** Drain all buffered items and return them, clearing the buffer. */
    public List<T> drain() {
        lock.lock();
        try {
            List<T> result = new ArrayList<>(buf);
            buf.clear();
            return result;
        } finally { lock.unlock(); }
    }

    public int size() {
        lock.lock();
        try { return buf.size(); }
        finally { lock.unlock(); }
    }
}


// ============================================================
//  ConcurrentSensorFeed — 7 sensor threads (M5 concurrency)
// ============================================================
/**
 * ConcurrentSensorFeed — simulates 7 hardware sensors running in parallel.
 *
 * Architecture:
 *   • One Thread per sensor (SENSOR-TEMP, SENSOR-HUMID, …)
 *   • All threads write into a shared SensorBuffer&lt;SensorReading&gt;
 *   • A ReentrantLock protects the combined output list
 *   • Main thread joins all worker threads (max 30 s timeout)
 *   • Returns readings sorted by timestamp for display
 *
 * Called from SensorController.runSensors() on a background Task,
 * never on the JavaFX Application Thread.
 */
public class ConcurrentSensorFeed {

    /** Sensor definitions: {id, parameter, min, max, unit} */
    public static final String[][] SENSORS = {
        {"SENSOR-TEMP",  "TEMP",       "18", "42",  "C"},
        {"SENSOR-HUMID", "HUMIDITY",   "30", "100", "%"},
        {"SENSOR-RAIN",  "RAINFALL",   "0",  "50",  "mm"},
        {"SENSOR-WIND",  "WIND",       "0",  "80",  "km/h"},
        {"SENSOR-AQI",   "AQI",        "20", "200", "AQI"},
        {"SENSOR-SOIL",  "SOIL_MOIST", "10", "80",  "%"},
        {"SENSOR-UV",    "UV_INDEX",   "0",  "12",  "UV"},
    };

    private volatile SystemStatus status     = SystemStatus.IDLE;
    private final int             n;           // readings per sensor
    private final int             numSensors;

    public ConcurrentSensorFeed(int readingsPerSensor, int numSensors) {
        this.n          = readingsPerSensor;
        this.numSensors = Math.min(numSensors, SENSORS.length);
    }

    public SystemStatus getStatus() { return status; }

    /**
     * Spawns numSensors threads, collects all readings, joins, returns sorted list.
     * Must be called off the JavaFX Application Thread (use inside Task.call()).
     */
    public List<SensorReading> run(WeatherLogger logger) throws InterruptedException {
        status = SystemStatus.COLLECTING;

        List<SensorReading>  all    = Collections.synchronizedList(new ArrayList<>());
        SensorBuffer<SensorReading> buffer = new SensorBuffer<>(10_000);
        ReentrantLock        lock   = new ReentrantLock();
        Random               rng    = new Random();
        List<Thread>         threads = new ArrayList<>();

        for (int i = 0; i < numSensors; i++) {
            String[] s     = SENSORS[i];
            String   id    = s[0], param = s[1], unit = s[4];
            double   lo    = Double.parseDouble(s[2]);
            double   hi    = Double.parseDouble(s[3]);

            Thread t = new Thread(() -> {
                for (int j = 0; j < n; j++) {
                    double     val = Math.round((lo + rng.nextDouble() * (hi - lo)) * 100.0) / 100.0;
                    String     ts  = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss.SSS"));
                    AlertLevel al  = AlertLevel.classify(param, val);
                    SensorReading sr = new SensorReading(id, param, val, unit, ts, al);

                    buffer.push(sr);
                    lock.lock();
                    try { all.add(sr); } finally { lock.unlock(); }

                    try { Thread.sleep(1 + rng.nextInt(4)); }
                    catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                }
            }, id);   // thread name = sensor id — visible in thread dumps

            t.setDaemon(true);
            threads.add(t);
        }

        for (Thread t : threads) t.start();
        for (Thread t : threads) t.join(30_000);   // 30 s safety timeout

        status = SystemStatus.READY;
        all.sort(Comparator.comparing(r -> r.timestamp));

        if (logger != null)
            logger.event("Sensor run: " + all.size() + " readings from " + numSensors + " threads");

        return all;
    }
}