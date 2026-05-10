from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import TypeVar, Generic, List
from functools import reduce
import threading
import time
import random
import os
import csv
import json
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

class WeatherConfig:
    SYSTEM_NAME    = "JKUAT Weather & Environmental Data System"
    STATION_ID     = "KE-NBI-001"
    LOCATION       = "JKUAT Main Farm, Juja"
    TEMP_HEATWAVE      = 35.0
    TEMP_OPTIMAL_LOW   = 20.0
    TEMP_COLD          = 10.0
    RAINFALL_CROP_NEED = 5.0
    RAINFALL_LOW       = 2.0
    RAINFALL_HEAVY     = 25.0
    WIND_STRONG        = 50.0
    WIND_MODERATE      = 30.0
    HUMIDITY_DISEASE   = 85.0
    HUMIDITY_DRY       = 30.0
    AQI_UNHEALTHY      = 150
    AQI_MODERATE       = 100
    VALID_DAYS  = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    VALID_DIRS  = ["N","NE","E","SE","S","SW","W","NW"]
    DATA_DIR    = "weather_data"
    CSV_FILENAME  = os.path.join(DATA_DIR, "weather_readings.csv")
    JSON_FILENAME = os.path.join(DATA_DIR, "weather_readings.json")
    LOG_FILENAME  = os.path.join(DATA_DIR, "system.log")
    CSV_HEADERS   = ["day","temperature","humidity","rainfall","wind_speed","wind_direction","aqi"]

CFG = WeatherConfig

class WeatherSystemError(Exception): pass
class ValidationError(WeatherSystemError): pass
class FileHandlingError(WeatherSystemError): pass
class DataNotFoundError(WeatherSystemError): pass
class EmptyDatasetError(WeatherSystemError): pass

class AlertLevel(Enum):
    NORMAL   = 1
    NOTICE   = 2
    WARNING  = 3
    CRITICAL = 4
    def label(self): return self.name
    def symbol(self):
        return {AlertLevel.NORMAL:"✅",AlertLevel.NOTICE:"ℹ️",
                AlertLevel.WARNING:"⚠️",AlertLevel.CRITICAL:"🚨"}[self]
    def color(self):
        return {AlertLevel.NORMAL:"#2ecc71",AlertLevel.NOTICE:"#3498db",
                AlertLevel.WARNING:"#f39c12",AlertLevel.CRITICAL:"#e74c3c"}[self]
    def __ge__(self,other):
        if self.__class__ is other.__class__: return self.value>=other.value
        return NotImplemented
    def __gt__(self,other):
        if self.__class__ is other.__class__: return self.value>other.value
        return NotImplemented

class SystemStatus(Enum):
    IDLE=auto(); COLLECTING=auto(); PROCESSING=auto(); READY=auto(); ERROR=auto()

class WindDirection(Enum):
    N="N"; NE="NE"; E="E"; SE="SE"; S="S"; SW="SW"; W="W"; NW="NW"
    @classmethod
    def from_string(cls,s):
        try: return cls(s.upper().strip())
        except ValueError: raise ValidationError(f"Invalid wind direction: '{s}'")

T = TypeVar("T")
class SensorBuffer(Generic[T]):
    def __init__(self,capacity=100):
        self._buffer:List[T]=[]; self._capacity=capacity; self._lock=threading.Lock()
    def push(self,item):
        with self._lock:
            if len(self._buffer)>=self._capacity: return False
            self._buffer.append(item); return True
    def drain(self):
        with self._lock: items=list(self._buffer); self._buffer.clear(); return items
    def size(self):
        with self._lock: return len(self._buffer)

class ThreadSafeDataset:
    def __init__(self):
        self._readings=[]; self._lock=threading.RLock()
    def add(self,r):
        with self._lock: self._readings.append(r)
    def get_all(self):
        with self._lock: return list(self._readings)
    def count(self):
        with self._lock: return len(self._readings)
    def is_empty(self):
        with self._lock: return len(self._readings)==0
    def clear(self):
        with self._lock: self._readings.clear()

class SensorReading:
    def __init__(self,sensor_id,parameter,value,unit,timestamp,alert_level):
        self.sensor_id=sensor_id; self.parameter=parameter; self.value=value
        self.unit=unit; self.timestamp=timestamp; self.alert_level=alert_level

class SensorThread(threading.Thread):
    _RANGES={"TEMP":(18.0,42.0,"°C"),"HUMIDITY":(30.0,100.0,"%"),
             "RAINFALL":(0.0,50.0,"mm"),"WIND":(0.0,80.0,"km/h"),"AQI":(20.0,200.0,"AQI")}
    def __init__(self,sensor_id,parameter,buffer,n,results,lock,callback=None):
        super().__init__(name=sensor_id,daemon=True)
        self._sid=sensor_id; self._param=parameter; self._buf=buffer
        self._n=n; self._results=results; self._lock=lock
        self._callback=callback; self._stop=threading.Event()
    def _classify(self,p,v):
        c={"TEMP":lambda v:(AlertLevel.CRITICAL if v>=CFG.TEMP_HEATWAVE else
                             AlertLevel.WARNING if v<=CFG.TEMP_COLD else AlertLevel.NORMAL),
           "HUMIDITY":lambda v:(AlertLevel.CRITICAL if v>CFG.HUMIDITY_DISEASE else
                                AlertLevel.WARNING if v<CFG.HUMIDITY_DRY else AlertLevel.NORMAL),
           "RAINFALL":lambda v:(AlertLevel.CRITICAL if v>CFG.RAINFALL_HEAVY else
                                AlertLevel.WARNING if v==0 else AlertLevel.NORMAL),
           "WIND":lambda v:(AlertLevel.CRITICAL if v>CFG.WIND_STRONG else
                            AlertLevel.WARNING if v>CFG.WIND_MODERATE else AlertLevel.NORMAL),
           "AQI":lambda v:(AlertLevel.CRITICAL if v>=CFG.AQI_UNHEALTHY else
                           AlertLevel.WARNING if v>=CFG.AQI_MODERATE else AlertLevel.NORMAL)}
        return c.get(p,lambda v:AlertLevel.NORMAL)(v)
    def run(self):
        lo,hi,unit=self._RANGES[self._param]
        for _ in range(self._n):
            if self._stop.is_set(): break
            v=round(random.uniform(lo,hi),2)
            ts=datetime.datetime.now().strftime("%H:%M:%S")
            lvl=self._classify(self._param,v)
            r=SensorReading(self._sid,self._param,v,unit,ts,lvl)
            self._buf.push(r)
            with self._lock: self._results.append(r)
            if self._callback: self._callback(r)
            time.sleep(random.uniform(0.08,0.2))

class FunctionalAnalytics:
    _get_temp =lambda self,r:r.get_temp()
    _get_rain =lambda self,r:r.get_rain()
    _get_hum  =lambda self,r:r.get_humidity()
    _get_wind =lambda self,r:r.get_wind()
    _get_aqi  =lambda self,r:r.get_aqi()
    _is_crit  =lambda self,r:r.get_overall_status()=="CRITICAL"
    _is_dry   =lambda self,r:r.get_rain()==0
    _is_flood =lambda self,r:r.get_rain()>CFG.RAINFALL_HEAVY
    def analyse_dataset(self,readings):
        if not readings: return {}
        temps =list(map(self._get_temp,readings))
        rains =list(map(self._get_rain,readings))
        humids=list(map(self._get_hum, readings))
        winds =list(map(self._get_wind,readings))
        aqis  =list(map(self._get_aqi, readings))
        total_rain =reduce(lambda a,b:a+b,rains)
        total_temp =reduce(lambda a,b:a+b,temps)
        total_humid=reduce(lambda a,b:a+b,humids)
        n=len(readings)
        return {"count":n,"avg_temp":round(total_temp/n,1),"avg_rain":round(total_rain/n,1),
                "avg_humidity":round(total_humid/n,1),"total_rain":round(total_rain,1),
                "max_temp":max(temps),"min_temp":min(temps),"peak_wind":max(winds),"peak_aqi":max(aqis),
                "critical_days":list(filter(self._is_crit,readings)),
                "dry_days":list(filter(self._is_dry,readings)),
                "flood_days":list(filter(self._is_flood,readings)),
                "heat_days":list(filter(lambda r:r.get_temp()>=CFG.TEMP_HEATWAVE,readings)),
                "hottest_day":sorted(readings,key=lambda r:r.get_temp(),reverse=True)[0],
                "wettest_day":sorted(readings,key=lambda r:r.get_rain(),reverse=True)[0]}

class EnvironmentalReading(ABC):
    def __init__(self,day):
        if day not in CFG.VALID_DAYS: raise ValidationError(f"Invalid day: '{day}'")
        self._day=day
    def get_day(self): return self._day
    @abstractmethod
    def get_summary(self): pass
    @abstractmethod
    def status_report(self): pass
    @abstractmethod
    def get_overall_status(self): pass
    def __str__(self): return self.get_summary()

class WeatherReading(EnvironmentalReading):
    def __init__(self,day,temperature,humidity,rainfall,wind_speed,wind_direction,aqi,validate=True):
        super().__init__(day)
        if validate:
            self.__temp    =self.__vr("Temperature",temperature,-50,60)
            self.__humidity=self.__vr("Humidity",humidity,0,100)
            self.__rainfall=self.__vn("Rainfall",rainfall)
            self.__wind    =self.__vn("Wind speed",wind_speed)
            self.__aqi     =self.__vr("AQI",aqi,0,500)
        else:
            self.__temp=temperature; self.__humidity=humidity
            self.__rainfall=rainfall; self.__wind=wind_speed; self.__aqi=aqi
        self.__wind_dir     =wind_direction
        self.__heat_index   =round(self.__temp+(0.33*(self.__humidity/100)*6.105)-4.0,1)
        self.__evap         =round(0.0023*(self.__temp+17.8)*(100-self.__humidity)**0.5,2)
        a,b=17.27,237.7
        g=(a*self.__temp)/(b+self.__temp)+(self.__humidity/100.0)
        self.__dew_point    =round((b*g)/(a-g),2)
        self.__kelvin       =round(self.__temp+273.15,2)
        self.__water_deficit=max(0.0,CFG.RAINFALL_CROP_NEED-self.__rainfall)
    def __vr(self,name,v,lo,hi):
        if not(lo<=v<=hi): raise ValidationError(f"{name} {v} out of range [{lo}–{hi}]")
        return v
    def __vn(self,name,v):
        if v<0: raise ValidationError(f"{name} cannot be negative: {v}")
        return v
    def get_temp(self):           return self.__temp
    def get_humidity(self):       return self.__humidity
    def get_rain(self):           return self.__rainfall
    def get_wind(self):           return self.__wind
    def get_wind_dir(self):       return self.__wind_dir
    def get_aqi(self):            return self.__aqi
    def get_heat_index(self):     return self.__heat_index
    def get_evap(self):           return self.__evap
    def get_dew_point(self):      return self.__dew_point
    def get_kelvin(self):         return self.__kelvin
    def get_water_deficit(self):  return self.__water_deficit
    def get_overall_status(self):
        checks=[self._temp_s(),self._rain_s(),self._hum_s(),self._wind_s(),self._aqi_s()]
        if any("CRITICAL" in c or "ALERT" in c for c in checks): return "CRITICAL"
        if any("WARNING"  in c for c in checks):                  return "WARNING"
        return "NORMAL"
    def get_alert_level(self):
        return {"CRITICAL":AlertLevel.CRITICAL,"WARNING":AlertLevel.WARNING,
                "NORMAL":AlertLevel.NORMAL}.get(self.get_overall_status(),AlertLevel.NORMAL)
    def _temp_s(self):
        t=self.__temp
        if t>=CFG.TEMP_HEATWAVE:    return "CRITICAL"
        elif t>=CFG.TEMP_OPTIMAL_LOW: return "OK"
        elif t<=CFG.TEMP_COLD:      return "WARNING"
        return "NOTICE"
    def _rain_s(self):
        r=self.__rainfall
        if r==0:                      return "ALERT"
        elif r<CFG.RAINFALL_LOW:      return "LOW"
        elif r<CFG.RAINFALL_CROP_NEED:return "NOTICE"
        elif r<=CFG.RAINFALL_HEAVY:   return "OK"
        return "CRITICAL"
    def _hum_s(self):
        h=self.__humidity
        if h>CFG.HUMIDITY_DISEASE:  return "WARNING"
        elif h<CFG.HUMIDITY_DRY:    return "WARNING"
        return "OK"
    def _wind_s(self):
        w=self.__wind
        if w>CFG.WIND_STRONG:    return "CRITICAL"
        elif w>CFG.WIND_MODERATE:return "WARNING"
        return "OK"
    def _aqi_s(self):
        a=self.__aqi
        if a>=CFG.AQI_UNHEALTHY:  return "CRITICAL"
        elif a>=CFG.AQI_MODERATE: return "MODERATE"
        return "OK"
    def get_summary(self):
        deficit=f"Deficit:{self.__water_deficit:.1f}mm" if self.__water_deficit>0 else "Water:OK"
        return (f"{self._day:<12}| T:{self.__temp}°C | H:{self.__humidity}% | "
                f"R:{self.__rainfall}mm | W:{self.__wind}km/h | AQI:{self.__aqi} | "
                f"{deficit} | {self.get_overall_status()}")
    def status_report(self):
        print(self.get_summary())

class FarmerAlert(WeatherReading):
    def __init__(self,day,temperature,humidity,rainfall,wind_speed,wind_direction,aqi,validate=True):
        super().__init__(day,temperature,humidity,rainfall,wind_speed,wind_direction,aqi,validate)
        self.__alerts=[]; self.__build_alerts()
    def __build_alerts(self):
        temp=self.get_temp(); rain=self.get_rain(); hum=self.get_humidity()
        wind=self.get_wind(); aqi=self.get_aqi(); evap=self.get_evap()
        deficit=self.get_water_deficit(); hi=self.get_heat_index(); dew=self.get_dew_point()
        a=[]
        if rain==0 and temp>=CFG.TEMP_HEATWAVE: a.append("🚨 Zero rain + extreme heat — irrigate immediately")
        elif rain==0: a.append("💧 No rainfall — run full irrigation cycle")
        elif deficit>0: a.append(f"💧 Rainfall short — supplement {deficit:.1f}mm")
        if evap>5.0: a.append(f"☀️ High water loss ({evap}mm/day) — irrigate before 8am")
        elif evap>3.0: a.append(f"☀️ Moderate water loss ({evap}mm/day) — check at noon")
        if temp>=CFG.TEMP_HEATWAVE: a.append(f"🔥 Heat stress {temp}°C (feels {hi}°C)")
        elif temp>=30: a.append(f"🌡️ Warm day ({temp}°C) — monitor water needs")
        if hum>CFG.HUMIDITY_DISEASE: a.append(f"🍄 High humidity ({hum}%) — disease risk")
        elif hum>75 and temp>25: a.append(f"⚠️ Warm+humid — monitor disease signs")
        if rain>CFG.RAINFALL_HEAVY: a.append(f"🌊 Heavy rain ({rain}mm) — check drainage")
        if wind>CFG.WIND_STRONG: a.append(f"💨 Dangerous wind ({wind}km/h)")
        elif wind>CFG.WIND_MODERATE: a.append(f"💨 Strong wind ({wind}km/h) — lodging risk")
        if temp<=CFG.TEMP_COLD: a.append(f"🥶 Cold ({temp}°C) — cover seedlings")
        if aqi>=CFG.AQI_UNHEALTHY: a.append(f"😷 AQI {aqi} — workers must wear masks")
        elif aqi>=CFG.AQI_MODERATE: a.append(f"😷 AQI {aqi} — moderate air quality")
        if dew>20: a.append(f"💦 Dew point {dew}°C — delay morning spraying")
        if not a: a.append("✅ All conditions normal — safe operations today")
        self.__alerts=a
    def get_alerts(self): return list(self.__alerts)
    def get_summary(self): return super().get_summary()+f" | {len(self.__alerts)} alert(s)"
    def get_overall_status(self): return super().get_overall_status()
    def status_report(self): print(self.get_summary())

class WeatherDataset:
    def __init__(self): self.__r=[]
    def add(self,r): self.__r.append(r)
    def remove_day(self,day): self.__r=[r for r in self.__r if r.get_day()!=day]
    def get_for_day(self,day):
        for r in self.__r:
            if r.get_day()==day: return r
        return None
    def get_all(self): return list(self.__r)
    def count(self): return len(self.__r)
    def is_empty(self): return len(self.__r)==0
    def clear(self): self.__r=[]
    def _rs(self,lst):
        if not lst: return 0
        return lst[0]+self._rs(lst[1:])
    def _rmx(self,lst):
        if len(lst)==1: return lst[0]
        rest=self._rmx(lst[1:]); return lst[0] if lst[0]>rest else rest
    def _rmn(self,lst):
        if len(lst)==1: return lst[0]
        rest=self._rmn(lst[1:]); return lst[0] if lst[0]<rest else rest
    def avg_temp(self):
        if self.is_empty(): return 0
        v=[r.get_temp() for r in self.__r]; return round(self._rs(v)/len(v),1)
    def max_temp(self):
        if self.is_empty(): return 0
        return self._rmx([r.get_temp() for r in self.__r])
    def min_temp(self):
        if self.is_empty(): return 0
        return self._rmn([r.get_temp() for r in self.__r])
    def avg_humidity(self):
        if self.is_empty(): return 0
        v=[r.get_humidity() for r in self.__r]; return round(self._rs(v)/len(v),1)
    def total_rainfall(self):
        if self.is_empty(): return 0
        return round(self._rs([r.get_rain() for r in self.__r]),1)
    def peak_wind(self):
        if self.is_empty(): return 0
        return self._rmx([r.get_wind() for r in self.__r])
    def peak_aqi(self):
        if self.is_empty(): return 0
        return self._rmx([r.get_aqi() for r in self.__r])
    def sorted_by_temp(self,desc=True): return sorted(self.__r,key=lambda r:r.get_temp(),reverse=desc)
    def sorted_by_rain(self,desc=True): return sorted(self.__r,key=lambda r:r.get_rain(),reverse=desc)
    def critical_days(self): return [r for r in self.__r if r.get_overall_status()=="CRITICAL"]
    def dry_days(self):      return [r for r in self.__r if r.get_rain()==0]
    def flood_days(self):    return [r for r in self.__r if r.get_rain()>CFG.RAINFALL_HEAVY]
    def days_above_temp(self,t): return [r for r in self.__r if r.get_temp()>=t]
    def worst_day(self):
        if self.is_empty(): return None
        return max(self.__r,key=lambda r:r.get_temp())

class WeatherStation:
    def __init__(self,station_id,location):
        self.station_id=station_id; self.location=location; self.dataset=WeatherDataset()
    def add_reading(self,r): self.dataset.add(r)
    def has_readings(self): return not self.dataset.is_empty()
    def get_reading_for_day(self,day): return self.dataset.get_for_day(day)

class WeatherLogger:
    def __init__(self,filepath=CFG.LOG_FILENAME):
        self._filepath=filepath; self._recent=[]
        try: os.makedirs(os.path.dirname(self._filepath),exist_ok=True)
        except OSError: pass
    def _write(self,level,message):
        ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry=f"[{ts}] [{level:<7}] {message}"
        self._recent.append(entry)
        try:
            with open(self._filepath,"a",encoding="utf-8") as f: f.write(entry+"\n")
        except OSError: pass
    def info(self,m):    self._write("INFO",m)
    def warning(self,m): self._write("WARNING",m)
    def error(self,m):   self._write("ERROR",m)
    def event(self,m):   self._write("EVENT",m)
    def get_recent(self,n=50): return self._recent[-n:]

class WeatherFileHandler:
    def __init__(self,logger):
        self._logger=logger
        try: os.makedirs(CFG.DATA_DIR,exist_ok=True)
        except OSError: pass
    def save_csv(self,dataset,filepath=CFG.CSV_FILENAME):
        if dataset.is_empty(): raise EmptyDatasetError("No data to save.")
        try:
            with open(filepath,"w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=CFG.CSV_HEADERS); w.writeheader()
                for r in dataset.get_all():
                    w.writerow({"day":r.get_day(),"temperature":r.get_temp(),
                                "humidity":r.get_humidity(),"rainfall":r.get_rain(),
                                "wind_speed":r.get_wind(),"wind_direction":r.get_wind_dir(),
                                "aqi":r.get_aqi()})
            self._logger.event(f"CSV saved → {filepath}")
        except OSError as e: raise FileHandlingError(str(e)) from e
    def load_csv(self,filepath=CFG.CSV_FILENAME):
        if not os.path.exists(filepath): raise FileHandlingError(f"File not found: {filepath}")
        records=[]
        try:
            with open(filepath,"r",encoding="utf-8") as f:
                for row_num,row in enumerate(csv.DictReader(f),start=2):
                    try:
                        records.append(FarmerAlert(
                            row["day"],float(row["temperature"]),float(row["humidity"]),
                            float(row["rainfall"]),float(row["wind_speed"]),
                            row["wind_direction"],int(row["aqi"]),validate=True))
                    except (ValueError,KeyError,WeatherSystemError): pass
        except OSError as e: raise FileHandlingError(str(e)) from e
        if not records: raise FileHandlingError("No valid records in file.")
        self._logger.event(f"CSV loaded ← {filepath} ({len(records)} records)")
        return records
    def save_json(self,dataset,station_id,filepath=CFG.JSON_FILENAME):
        if dataset.is_empty(): raise EmptyDatasetError("No data to save.")
        payload={"system":CFG.SYSTEM_NAME,"version":CFG.VERSION,"station_id":station_id,
                 "saved_at":datetime.datetime.now().isoformat(),
                 "readings":[{"day":r.get_day(),"temperature":r.get_temp(),
                               "humidity":r.get_humidity(),"rainfall":r.get_rain(),
                               "wind_speed":r.get_wind(),"wind_direction":r.get_wind_dir(),
                               "aqi":r.get_aqi(),"heat_index":r.get_heat_index(),
                               "overall_status":r.get_overall_status(),
                               "alert_level":r.get_alert_level().label()}
                              for r in dataset.get_all()]}
        try:
            with open(filepath,"w",encoding="utf-8") as f: json.dump(payload,f,indent=2)
            self._logger.event(f"JSON saved → {filepath}")
        except OSError as e: raise FileHandlingError(str(e)) from e

WEEKLY_SIMULATION=[
    ["Monday",   32.5,78.0, 4.2,18.5,"NE",55],
    ["Tuesday",  34.1,72.0, 0.0,22.0,"N", 60],
    ["Wednesday",29.8,85.0,18.5,10.0,"SE",48],
    ["Thursday", 38.2,60.0, 0.0,30.5,"NW",72],
    ["Friday",   31.0,75.0, 7.3,14.0,"NE",50],
    ["Saturday", 27.5,90.0,32.1, 8.0,"E", 42],
    ["Sunday",   30.2,68.0, 2.0,19.0,"N", 58],
]
#colour palette
BG        = "#0d1117"  
BG2       = "#161b22" 
BG3       = "#21262d"  
ACCENT    = "#58a6ff"  
ACCENT2   = "#1f6feb"   
GREEN     = "#3fb950"
YELLOW    = "#d29922"
RED       = "#f85149"
TEXT      = "#e6edf3"
TEXT2     = "#8b949e"
BORDER    = "#30363d"
FONT_HEAD = ("Courier New", 13, "bold")
FONT_BODY = ("Courier New", 10)
FONT_CARD = ("Courier New", 22, "bold")
FONT_LBL  = ("Courier New", 9)
FONT_BTN  = ("Courier New", 10, "bold")
FONT_MONO = ("Courier New", 9)

def status_color(status):
    return {"CRITICAL":RED,"WARNING":YELLOW,"NORMAL":GREEN}.get(status,TEXT2)

def alert_color(level: AlertLevel):
    return level.color()

#
def styled_button(parent, text, command, color=ACCENT, fg=BG, **kw):
    btn = tk.Button(parent, text=text, command=command,
                    bg=color, fg=fg, font=FONT_BTN,
                    relief="flat", cursor="hand2",
                    padx=12, pady=5, activebackground=ACCENT2,
                    activeforeground=TEXT, **kw)
    return btn

def styled_label(parent, text, font=FONT_BODY, fg=TEXT, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg,
                    bg=BG2, **kw)

def section_title(parent, text):
    lbl = tk.Label(parent, text=text, font=FONT_HEAD,
                   fg=ACCENT, bg=BG2, pady=6)
    lbl.pack(fill="x", padx=10)
    sep = tk.Frame(parent, bg=BORDER, height=1)
    sep.pack(fill="x", padx=10)

def card(parent, title, value, unit="", color=ACCENT, width=140, height=90):
    f = tk.Frame(parent, bg=BG3, bd=0, relief="flat",
                 width=width, height=height)
    f.pack_propagate(False)
    tk.Label(f, text=title, font=FONT_LBL, fg=TEXT2, bg=BG3).pack(pady=(8,0))
    tk.Label(f, text=str(value), font=FONT_CARD, fg=color, bg=BG3).pack()
    tk.Label(f, text=unit, font=FONT_LBL, fg=TEXT2, bg=BG3).pack()
    return f
#DashboardFrame
class DashboardFrame(tk.Frame): # Live summary dashboard. Shows stat cards and per-day status table.Requirement
    def __init__(self, parent, station: WeatherStation, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._station = station
        self._cards   = {}
        self._build()

    def _build(self):
        section_title(self, "📊  DASHBOARD — Station KE-NBI-001 | JKUAT Main Farm, Juja")

        #  Stat cards row ─
        card_row = tk.Frame(self, bg=BG2)
        card_row.pack(fill="x", padx=10, pady=10)

        defs = [("AVG TEMP","—","°C",ACCENT),("PEAK TEMP","—","°C",RED),
                ("TOTAL RAIN","—","mm",GREEN),("AVG HUMID","—","%",ACCENT),
                ("PEAK WIND","—","km/h",YELLOW),("PEAK AQI","—","",TEXT2)]
        for title,val,unit,color in defs:
            c = card(card_row,title,val,unit,color)
            c.pack(side="left",padx=5)
            self._cards[title] = c.winfo_children()[1]  

        #Status table 
        tbl_frame = tk.Frame(self, bg=BG2)
        tbl_frame.pack(fill="both", expand=True, padx=10, pady=5)

        cols = ("Day","Temp °C","Humid %","Rain mm","Wind km/h","AQI","Status","Alerts")
        self._tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=10)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=BG3, foreground=TEXT,
                        fieldbackground=BG3, font=FONT_MONO, rowheight=22)
        style.configure("Treeview.Heading", background=BG, foreground=ACCENT,
                        font=("Courier New",9,"bold"))
        style.map("Treeview", background=[("selected", ACCENT2)])

        widths = [90,70,70,70,80,60,80,60]
        for col,w in zip(cols,widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center")

        sb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        #Conclusion label 
        self._conclusion = tk.Label(self, text="Run simulation or enter data to populate dashboard.",
                                    font=FONT_BODY, fg=TEXT2, bg=BG2, pady=6)
        self._conclusion.pack()

    def refresh(self): #Repopulate all cards and table from current dataset.
        ds = self._station.dataset
        if ds.is_empty(): return

        # Update cards
        updates = {"AVG TEMP":  (ds.avg_temp(),    ACCENT),
                   "PEAK TEMP": (ds.max_temp(),    RED),
                   "TOTAL RAIN":(ds.total_rainfall(),GREEN),
                   "AVG HUMID": (ds.avg_humidity(),ACCENT),
                   "PEAK WIND": (ds.peak_wind(),   YELLOW),
                   "PEAK AQI":  (ds.peak_aqi(),    TEXT2)}
        for key,(val,color) in updates.items():
            lbl = self._cards.get(key)
            if lbl:
                lbl.config(text=str(val), fg=color)

        # Repopulate table
        self._tree.delete(*self._tree.get_children())
        for r in ds.get_all():
            alerts = len(r.get_alerts()) if isinstance(r,FarmerAlert) else 0
            status = r.get_overall_status()
            tag    = status.lower()
            self._tree.insert("","end", values=(
                r.get_day(), r.get_temp(), r.get_humidity(),
                r.get_rain(), r.get_wind(), r.get_aqi(),
                status, alerts), tags=(tag,))

        self._tree.tag_configure("critical", foreground=RED)
        self._tree.tag_configure("warning",  foreground=YELLOW)
        self._tree.tag_configure("normal",   foreground=GREEN)

        # Conclusion
        avg_rain = round(ds.total_rainfall()/ds.count(),1)
        if avg_rain < 3:
            msg = "⚠️  DRY WEEK — drought conditions. Activate irrigation."
            col = RED
        elif ds.total_rainfall() > CFG.RAINFALL_HEAVY*3:
            msg = "⚠️  WET WEEK — flooding risk. Inspect drainage."
            col = YELLOW
        else:
            msg = "✅  CONDITIONS FAVOURABLE — continue normal operations."
            col = GREEN
        if ds.max_temp() >= CFG.TEMP_HEATWAVE:
            msg += f"  |  🔥 Heat peak: {ds.max_temp()}°C"
        self._conclusion.config(text=msg, fg=col)

class SimulationFrame(tk.Frame): 
    def __init__(self, parent, station, dashboard, logger, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._station   = station
        self._dashboard = dashboard
        self._logger    = logger
        self._build()

    def _build(self):
        section_title(self, "🌤️  7-DAY WEATHER SIMULATION")

        btn_row = tk.Frame(self, bg=BG2)
        btn_row.pack(pady=10)
        styled_button(btn_row,"▶  Run 7-Day Simulation", self._run_sim).pack(side="left",padx=5)
        styled_button(btn_row,"🗑  Clear Data",           self._clear,  color=BG3, fg=RED).pack(side="left",padx=5)

        # Output text area
        self._out = scrolledtext.ScrolledText(
            self, bg=BG3, fg=TEXT, font=FONT_MONO,
            insertbackground=ACCENT, relief="flat",
            wrap="none", height=22)
        self._out.pack(fill="both", expand=True, padx=10, pady=6)
        self._out.config(state="disabled")

        # tag colours
        self._out.tag_configure("head",    foreground=ACCENT,  font=("Courier New",10,"bold"))
        self._out.tag_configure("critical",foreground=RED)
        self._out.tag_configure("warning", foreground=YELLOW)
        self._out.tag_configure("normal",  foreground=GREEN)
        self._out.tag_configure("dim",     foreground=TEXT2)

    def _write(self, text, tag=""):
        self._out.config(state="normal")
        self._out.insert("end", text, tag)
        self._out.see("end")
        self._out.config(state="disabled")

    def _run_sim(self):
        self._out.config(state="normal"); self._out.delete("1.0","end"); self._out.config(state="disabled")
        self._station.dataset = WeatherDataset()
        self._write("="*66+"\n","head")
        self._write(f"  7-DAY SIMULATION — {self._station.station_id}\n","head")
        self._write(f"  Location : {self._station.location}\n","head")
        self._write("="*66+"\n","head")
        self._write(f"  {'Day':<12}{'Temp':>7}{'Humid':>7}{'Rain':>7}{'Wind':>7}{'AQI':>6}  Status\n","dim")
        self._write("  "+"-"*60+"\n","dim")

        for row in WEEKLY_SIMULATION:
            r = FarmerAlert(row[0],row[1],row[2],row[3],row[4],row[5],row[6],validate=False)
            self._station.add_reading(r)
            status = r.get_overall_status()
            tag    = status.lower()
            self._write(
                f"  {row[0]:<12}{row[1]:>7}°C{row[2]:>6}%{row[3]:>7}mm"
                f"{row[4]:>7}k/h{row[5]:>5}  {status}\n", tag)

        ds = self._station.dataset
        self._write("\n"+"─"*66+"\n","dim")
        self._write("  WEEKLY SUMMARY (recursive stats)\n","head")
        self._write(f"  Avg Temp     : {ds.avg_temp()}°C\n")
        self._write(f"  Peak Temp    : {ds.max_temp()}°C\n")
        self._write(f"  Min Temp     : {ds.min_temp()}°C\n")
        self._write(f"  Total Rain   : {ds.total_rainfall()} mm\n")
        self._write(f"  Avg Humidity : {ds.avg_humidity()}%\n")
        self._write(f"  Peak Wind    : {ds.peak_wind()} km/h\n")
        self._write(f"  Peak AQI     : {ds.peak_aqi()}\n")
        crit = ds.critical_days()
        self._write(f"  Critical days: {len(crit)} → "
                    +", ".join(r.get_day() for r in crit)+"\n","critical")
        self._write("\n  FARMER ALERTS PER DAY\n","head")
        self._write("─"*66+"\n","dim")
        for r in ds.get_all():
            if isinstance(r,FarmerAlert):
                tag = r.get_overall_status().lower()
                self._write(f"  {r.get_day()}:\n",tag)
                for a in r.get_alerts():
                    self._write(f"    {a}\n")

        self._logger.event("7-day simulation run via GUI")
        self._dashboard.refresh()
        messagebox.showinfo("Simulation Complete",
                            f"7-day simulation done.\n{ds.count()} readings loaded.")

    def _clear(self):
        if messagebox.askyesno("Clear Data","Clear all current weather data?"):
            self._station.dataset = WeatherDataset()
            self._out.config(state="normal"); self._out.delete("1.0","end"); self._out.config(state="disabled")
            self._dashboard.refresh()
            self._logger.event("Dataset cleared via GUI")

class LiveEntryFrame(tk.Frame):
    def __init__(self, parent, station, dashboard, logger, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._station   = station
        self._dashboard = dashboard
        self._logger    = logger
        self._vars      = {}
        self._build()

    def _build(self):
        section_title(self, "✏️  LIVE DATA ENTRY")

        form = tk.Frame(self, bg=BG2)
        form.pack(pady=10, padx=20)

        fields = [
            ("Day",           "day",    "combobox", CFG.VALID_DAYS),
            ("Temperature °C",  "temp",   "entry",    None),
            ("Humidity %",      "humid",  "entry",    None),
            ("Rainfall mm",     "rain",   "entry",    None),
            ("Wind Speed km/h", "wind",   "entry",    None),
            ("Wind Direction",  "wdir",   "combobox", CFG.VALID_DIRS),
            ("AQI (0–500)",     "aqi",    "entry",    None),
        ]

        for row_idx,(label,key,kind,opts) in enumerate(fields):
            tk.Label(form, text=label+":", font=FONT_BODY, fg=TEXT2,
                     bg=BG2, width=18, anchor="e").grid(row=row_idx,column=0,padx=5,pady=3)
            var = tk.StringVar()
            self._vars[key] = var
            if kind=="combobox":
                w = ttk.Combobox(form, textvariable=var, values=opts,
                                 font=FONT_BODY, width=18, state="readonly")
                if opts: w.current(0)
            else:
                w = tk.Entry(form, textvariable=var, font=FONT_BODY,
                             bg=BG3, fg=TEXT, insertbackground=ACCENT,
                             relief="flat", width=20)
            w.grid(row=row_idx,column=1,padx=5,pady=3,sticky="w")

        btn_row = tk.Frame(self, bg=BG2)
        btn_row.pack(pady=8)
        styled_button(btn_row,"💾  Save Reading",  self._save).pack(side="left",padx=5)
        styled_button(btn_row,"🔄  Clear Form",    self._clear_form, color=BG3, fg=TEXT).pack(side="left",padx=5)

        # Alert output box
        self._out = scrolledtext.ScrolledText(
            self, bg=BG3, fg=TEXT, font=FONT_MONO,
            relief="flat", height=16, wrap="word")
        self._out.pack(fill="both",expand=True,padx=10,pady=6)
        self._out.config(state="disabled")
        self._out.tag_configure("ok",       foreground=GREEN)
        self._out.tag_configure("err",      foreground=RED)
        self._out.tag_configure("alert",    foreground=YELLOW)
        self._out.tag_configure("head",     foreground=ACCENT, font=("Courier New",10,"bold"))

    def _save(self):
        try:
            day  = self._vars["day"].get()
            temp = float(self._vars["temp"].get())
            hum  = float(self._vars["humid"].get())
            rain = float(self._vars["rain"].get())
            wind = float(self._vars["wind"].get())
            wdir = self._vars["wdir"].get()
            aqi  = int(self._vars["aqi"].get())
        except ValueError:
            messagebox.showerror("Input Error","Please fill all fields with valid numbers.")
            return

        existing = self._station.get_reading_for_day(day)
        if existing:
            if not messagebox.askyesno("Overwrite",f"Reading for {day} exists. Overwrite?"):
                return
            self._station.dataset.remove_day(day)

        try:
            r = FarmerAlert(day,temp,hum,rain,wind,wdir,aqi,validate=True)
        except ValidationError as ve:
            messagebox.showerror("Validation Error",str(ve))
            return

        self._station.add_reading(r)
        self._logger.event(f"Live entry saved: {day}")
        self._dashboard.refresh()

        # Show alerts in output box
        self._out.config(state="normal"); self._out.delete("1.0","end")
        self._out.insert("end",f"✅  {day} saved successfully.\n\n","ok")
        self._out.insert("end",f"FARMER ALERTS — {day}\n","head")
        self._out.insert("end","─"*50+"\n","head")
        for a in r.get_alerts():
            tag = "err" if "🚨" in a or "🔥" in a or "🌊" in a else "alert"
            self._out.insert("end",f"  {a}\n",tag)
        self._out.insert("end",f"\nOverall: {r.get_overall_status()}\n",
                         r.get_overall_status().lower())
        self._out.config(state="disabled")

    def _clear_form(self):
        for key,var in self._vars.items():
            if key=="day": var.set(CFG.VALID_DAYS[0])
            elif key=="wdir": var.set(CFG.VALID_DIRS[0])
            else: var.set("")
        self._out.config(state="normal"); self._out.delete("1.0","end"); self._out.config(state="disabled")


class AnalyticsFrame(tk.Frame): #Bar chart visualisation + functional analytics report.Output visual chats
    def __init__(self, parent, station, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._station   = station
        self._analytics = FunctionalAnalytics()
        self._build()

    def _build(self):
        section_title(self, "📈  ANALYTICS & VISUALISATION")

        btn_row = tk.Frame(self, bg=BG2)
        btn_row.pack(pady=8)
        styled_button(btn_row,"📊  Temperature Bar Chart", lambda:self._draw_chart("temp")).pack(side="left",padx=4)
        styled_button(btn_row,"🌧️  Rainfall Bar Chart",    lambda:self._draw_chart("rain")).pack(side="left",padx=4)
        styled_button(btn_row,"🔍  Functional Analytics",  self._show_analytics).pack(side="left",padx=4)

        # Canvas for bar chart
        self._canvas = tk.Canvas(self, bg=BG3, height=220, relief="flat")
        self._canvas.pack(fill="x", padx=10, pady=6)

        # Text report
        self._out = scrolledtext.ScrolledText(
            self, bg=BG3, fg=TEXT, font=FONT_MONO,
            relief="flat", height=12, wrap="word")
        self._out.pack(fill="both",expand=True,padx=10,pady=4)
        self._out.config(state="disabled")
        self._out.tag_configure("head",     foreground=ACCENT,  font=("Courier New",10,"bold"))
        self._out.tag_configure("critical", foreground=RED)
        self._out.tag_configure("ok",       foreground=GREEN)
        self._out.tag_configure("dim",      foreground=TEXT2)

    def _draw_chart(self, kind):
        if not self._station.has_readings():
            messagebox.showwarning("No Data","Run simulation or enter data first.")
            return
        ds      = self._station.dataset
        rows    = ds.get_all()
        self._canvas.delete("all")
        c       = self._canvas
        W       = c.winfo_width() or 700
        H       = 210
        margin  = 45
        n       = len(rows)
        bar_w   = max(20, (W - 2*margin) // (n or 1) - 8)

        if kind == "temp":
            values = [r.get_temp() for r in rows]
            title  = "Daily Temperature (°C)"
            lo,hi  = 0, max(values)+5
            colors = [RED if v>=CFG.TEMP_HEATWAVE else YELLOW if v>=30 else GREEN for v in values]
        else:
            values = [r.get_rain() for r in rows]
            title  = "Daily Rainfall (mm)"
            lo,hi  = 0, max(max(values)+5, 10)
            colors = [RED if v>CFG.RAINFALL_HEAVY else YELLOW if v==0 else ACCENT for v in values]

        # Title
        c.create_text(W//2, 12, text=title, fill=ACCENT,
                      font=("Courier New",10,"bold"))

        chart_h = H - 40
        for i,(r,val,col) in enumerate(zip(rows,values,colors)):
            x1 = margin + i*(bar_w+8)
            x2 = x1+bar_w
            frac   = (val-lo)/(hi-lo) if hi>lo else 0
            bar_px = int(frac * chart_h)
            y2     = H-30
            y1     = y2-bar_px
            c.create_rectangle(x1,y1,x2,y2,fill=col,outline="")
            c.create_text((x1+x2)//2, y1-6, text=str(val),
                          fill=TEXT, font=("Courier New",7))
            c.create_text((x1+x2)//2, H-14, text=r.get_day()[:3],
                          fill=TEXT2, font=("Courier New",7))

        # Y axis
        for tick in range(0,5):
            y    = H-30 - int(tick/4 * chart_h)
            val  = round(lo + tick/4*(hi-lo), 1)
            c.create_line(margin-3, y, margin, y, fill=BORDER)
            c.create_text(margin-4, y, text=str(val),
                          fill=TEXT2, font=("Courier New",7), anchor="e")

    def _show_analytics(self):
        if not self._station.has_readings():
            messagebox.showwarning("No Data","Run simulation or enter data first.")
            return
        result = self._analytics.analyse_dataset(self._station.dataset.get_all())
        self._out.config(state="normal"); self._out.delete("1.0","end")

        def w(text,tag=""): self._out.insert("end",text,tag)

        w("FUNCTIONAL ANALYTICS  [map · filter · reduce · lambda]\n","head")
        w("─"*58+"\n","dim")
        w(f"  Days analysed   : {result['count']}\n")
        w(f"\n  📊  via map() + reduce()\n","head")
        w(f"     Avg Temp      : {result['avg_temp']}°C\n")
        w(f"     Avg Rainfall  : {result['avg_rain']} mm/day\n")
        w(f"     Avg Humidity  : {result['avg_humidity']}%\n")
        w(f"     Total Rain    : {result['total_rain']} mm\n")
        w(f"     Max Temp      : {result['max_temp']}°C\n")
        w(f"     Min Temp      : {result['min_temp']}°C\n")
        w(f"     Peak Wind     : {result['peak_wind']} km/h\n")
        w(f"     Peak AQI      : {result['peak_aqi']}\n")
        w(f"\n  🔍  via filter() + lambda\n","head")
        crit=result['critical_days']
        w(f"     Critical days : {len(crit)}", "critical")
        w((" → "+", ".join(r.get_day() for r in crit)+"\n") if crit else "\n","critical")
        dry=result['dry_days']
        w(f"     Dry days      : {len(dry)}")
        w((" → "+", ".join(r.get_day() for r in dry)+"\n") if dry else "\n")
        flood=result['flood_days']
        w(f"     Flood days    : {len(flood)}")
        w((" → "+", ".join(r.get_day() for r in flood)+"\n") if flood else "\n")
        heat=result['heat_days']
        w(f"     Heat days     : {len(heat)}")
        w((" → "+", ".join(r.get_day() for r in heat)+"\n") if heat else "\n")
        w(f"\n  📈  via sorted() + lambda key\n","head")
        w(f"     Hottest day   : {result['hottest_day'].get_day()} ({result['hottest_day'].get_temp()}°C)\n","critical")
        w(f"     Wettest day   : {result['wettest_day'].get_day()} ({result['wettest_day'].get_rain()}mm)\n","ok")
        self._out.config(state="disabled")


class SensorFrame(tk.Frame): #Concurrent sensor simulation panel with live log.
    def __init__(self, parent, logger, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._logger    = logger
        self._results   = []
        self._lock      = threading.Lock()
        self._running   = False
        self._build()

    def _build(self):
        section_title(self, "⚡  CONCURRENT SENSOR SIMULATION  [M5 INTEGRATION]")

        ctrl = tk.Frame(self, bg=BG2)
        ctrl.pack(pady=8)
        tk.Label(ctrl, text="Readings per sensor:", font=FONT_BODY, fg=TEXT2, bg=BG2).pack(side="left",padx=4)
        self._n_var = tk.IntVar(value=5)
        tk.Spinbox(ctrl, from_=1, to=10, textvariable=self._n_var, width=4,
                   bg=BG3, fg=TEXT, font=FONT_BODY,
                   buttonbackground=BG3).pack(side="left",padx=4)
        self._run_btn = styled_button(ctrl,"▶  Launch Threads", self._launch)
        self._run_btn.pack(side="left",padx=8)
        self._status_lbl = tk.Label(ctrl, text="🔵 IDLE", font=FONT_BODY, fg=TEXT2, bg=BG2)
        self._status_lbl.pack(side="left",padx=8)

        # Alert bar chart canvas
        self._canvas = tk.Canvas(self, bg=BG3, height=80, relief="flat")
        self._canvas.pack(fill="x",padx=10,pady=4)

        # Live log
        self._log = scrolledtext.ScrolledText(
            self, bg=BG3, fg=TEXT, font=FONT_MONO,
            relief="flat", height=16, wrap="none")
        self._log.pack(fill="both",expand=True,padx=10,pady=4)
        self._log.config(state="disabled")
        self._log.tag_configure("critical", foreground=RED)
        self._log.tag_configure("warning",  foreground=YELLOW)
        self._log.tag_configure("normal",   foreground=GREEN)
        self._log.tag_configure("head",     foreground=ACCENT, font=("Courier New",10,"bold"))
        self._log.tag_configure("dim",      foreground=TEXT2)

    def _log_write(self, text, tag=""):
        self._log.config(state="normal")
        self._log.insert("end", text, tag)
        self._log.see("end")
        self._log.config(state="disabled")

    def _launch(self):
        if self._running:
            messagebox.showinfo("Running","Sensor threads are still active.")
            return
        self._running = True
        self._results = []
        self._run_btn.config(state="disabled")
        self._status_lbl.config(text="🟡 COLLECTING", fg=YELLOW)
        self._log.config(state="normal"); self._log.delete("1.0","end"); self._log.config(state="disabled")
        self._canvas.delete("all")

        n = self._n_var.get()
        SENSORS=[("SENSOR-TEMP","TEMP"),("SENSOR-HUMID","HUMIDITY"),
                 ("SENSOR-RAIN","RAINFALL"),("SENSOR-WIND","WIND"),("SENSOR-AQI","AQI")]
        buf = SensorBuffer(capacity=500)

        self._log_write("="*60+"\n","head")
        self._log_write(f"  Launching {len(SENSORS)} threads  ({n} readings each)\n","head")
        self._log_write("="*60+"\n","head")
        self._log_write(f"  {'Timestamp':<12} {'Sensor':<14} {'Parameter':<12} {'Value':>8} {'Unit':<6} Level\n","dim")
        self._log_write("  "+"-"*58+"\n","dim")

        threads=[]
        for sid,param in SENSORS:
            t=SensorThread(sid,param,buf,n,self._results,self._lock,
                           callback=lambda r: self.after(0,self._on_reading,r))
            threads.append(t)
            self._log_write(f"  🟡 Thread started: {sid}\n")

        def run_all():
            for t in threads: t.start()
            for t in threads: t.join(timeout=15)
            self.after(0, self._on_done)

        threading.Thread(target=run_all, daemon=True).start()
        self._logger.event(f"Concurrent sensor sim launched: {n} readings/sensor")

    def _on_reading(self, r: SensorReading):
        tag = r.alert_level.label().lower()
        self._log_write(
            f"  [{r.timestamp}] {r.sensor_id:<14} {r.parameter:<12} "
            f"{r.value:>8.2f} {r.unit:<6} {r.alert_level.symbol()} {r.alert_level.label()}\n", tag)

    def _on_done(self):
        self._running = False
        self._run_btn.config(state="normal")
        self._status_lbl.config(text="🟢 READY", fg=GREEN)
        n_crit = sum(1 for r in self._results if r.alert_level==AlertLevel.CRITICAL)
        n_warn = sum(1 for r in self._results if r.alert_level==AlertLevel.WARNING)
        n_ok   = sum(1 for r in self._results if r.alert_level==AlertLevel.NORMAL)
        total  = len(self._results)
        self._log_write(f"\n  ✅  All threads complete. {total} readings collected.\n","head")
        self._log_write(f"  🚨 CRITICAL:{n_crit}  ⚠️ WARNING:{n_warn}  ✅ NORMAL:{n_ok}\n","dim")
        self._draw_summary(n_crit,n_warn,n_ok)
        self._logger.event(f"Sensor sim done: {total} readings collected")

    def _draw_summary(self,crit,warn,ok):
        c=self._canvas; c.delete("all")
        W=c.winfo_width() or 700; H=75
        total=max(crit+warn+ok,1)
        bars=[(crit,"CRITICAL",RED),(warn,"WARNING",YELLOW),(ok,"NORMAL",GREEN)]
        x=20
        for count,label,color in bars:
            w=int((count/total)*(W-40))
            if w>0:
                c.create_rectangle(x,15,x+w,45,fill=color,outline="")
                if w>40:
                    c.create_text(x+w//2,30,text=f"{label} ({count})",
                                  fill=BG,font=("Courier New",8,"bold"))
            x+=w
        c.create_text(W//2,62,text="Alert Level Distribution (filter+lambda  [M5])",
                      fill=TEXT2,font=("Courier New",8))


class FileFrame(tk.Frame):
    def __init__(self, parent, station, logger, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._station = station
        self._logger  = logger
        self._handler = WeatherFileHandler(logger)
        self._build()

    def _build(self):
        section_title(self, "💾  FILE PERSISTENCE  [M4 INTEGRATION]")

        grid = tk.Frame(self, bg=BG2)
        grid.pack(pady=16, padx=20)

        actions = [
            ("💾  Save CSV",    self._save_csv,  ACCENT),
            ("📄  Save JSON",   self._save_json, ACCENT),
            ("📂  Load CSV",    self._load_csv,  GREEN),
            ("📋  View Log",    self._view_log,  TEXT2),
        ]
        for col,(text,cmd,color) in enumerate(actions):
            styled_button(grid,text,cmd,color=color,fg=BG if color!=TEXT2 else TEXT).grid(
                row=0,column=col,padx=8)

        self._out = scrolledtext.ScrolledText(
            self, bg=BG3, fg=TEXT, font=FONT_MONO,
            relief="flat", height=26, wrap="none")
        self._out.pack(fill="both",expand=True,padx=10,pady=8)
        self._out.config(state="disabled")
        self._out.tag_configure("ok",  foreground=GREEN)
        self._out.tag_configure("err", foreground=RED)
        self._out.tag_configure("dim", foreground=TEXT2)
        self._out.tag_configure("head",foreground=ACCENT,font=("Courier New",10,"bold"))

    def _write(self,text,tag=""):
        self._out.config(state="normal"); self._out.insert("end",text,tag); self._out.config(state="disabled")

    def _save_csv(self):
        try:
            path=filedialog.asksaveasfilename(defaultextension=".csv",
                filetypes=[("CSV","*.csv")], initialfile="weather_readings.csv")
            if not path: return
            self._handler.save_csv(self._station.dataset,filepath=path)
            self._write(f"✅  CSV saved → {path}\n","ok")
        except (EmptyDatasetError,FileHandlingError) as e:
            self._write(f"❌  {e}\n","err")

    def _save_json(self):
        try:
            path=filedialog.asksaveasfilename(defaultextension=".json",
                filetypes=[("JSON","*.json")], initialfile="weather_readings.json")
            if not path: return
            self._handler.save_json(self._station.dataset,self._station.station_id,filepath=path)
            self._write(f"✅  JSON saved → {path}\n","ok")
        except (EmptyDatasetError,FileHandlingError) as e:
            self._write(f"❌  {e}\n","err")

    def _load_csv(self):
        try:
            path=filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
            if not path: return
            if not messagebox.askyesno("Load CSV","This will replace current data. Continue?"): return
            records=self._handler.load_csv(filepath=path)
            self._station.dataset=WeatherDataset()
            for r in records: self._station.add_reading(r)
            self._write(f"✅  Loaded {len(records)} records from {path}\n","ok")
            self._write("\n  LOADED DATA:\n","head")
            for r in records:
                self._write(f"  {r.get_summary()}\n","dim")
        except (FileHandlingError,WeatherSystemError) as e:
            self._write(f"❌  {e}\n","err")

    def _view_log(self):
        self._out.config(state="normal"); self._out.delete("1.0","end")
        self._write("SYSTEM LOG\n","head")
        self._write("─"*60+"\n","dim")
        entries=self._logger.get_recent(100)
        if not entries: self._write("  (No log entries yet)\n","dim")
        for e in entries:
            tag="err" if "ERROR" in e else "ok" if "EVENT" in e else "dim"
            self._write(f"  {e}\n",tag)
        self._out.config(state="disabled")

class WeatherApp:
    def __init__(self):
        self.root    = tk.Tk()
        self.root.title(f"{CFG.SYSTEM_NAME}  v{CFG.VERSION}  |  {CFG.MILESTONE}")
        self.root.geometry("1050x700")
        self.root.configure(bg=BG)
        self.root.resizable(True,True)

        self._station = WeatherStation(CFG.STATION_ID, CFG.LOCATION)
        self._logger  = WeatherLogger()
        self._logger.event("GUI application started — Milestone 6")

        self._build_header()
        self._build_notebook()
        self._build_statusbar()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=ACCENT2, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text=f"  🌦  {CFG.SYSTEM_NAME}",
                 font=("Courier New",13,"bold"), fg=TEXT,
                 bg=ACCENT2).pack(side="left",padx=10)
        tk.Label(hdr, text=f"v{CFG.VERSION}  |  {CFG.STATION_ID}  |  {CFG.LOCATION}  ",
                 font=FONT_LBL, fg="#a8d8ff", bg=ACCENT2).pack(side="right",padx=10)

    def _build_notebook(self):
        style = ttk.Style()
        style.configure("TNotebook",       background=BG,  borderwidth=0)
        style.configure("TNotebook.Tab",   background=BG2, foreground=TEXT2,
                        font=FONT_BTN, padding=[12,5])
        style.map("TNotebook.Tab",
                  background=[("selected",ACCENT2)],
                  foreground=[("selected",TEXT)])

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        # Build frames
        self._dashboard = DashboardFrame(nb, self._station)
        self._sim       = SimulationFrame(nb, self._station, self._dashboard, self._logger)
        self._entry     = LiveEntryFrame(nb, self._station, self._dashboard, self._logger)
        self._analytics = AnalyticsFrame(nb, self._station)
        self._sensors   = SensorFrame(nb, self._logger)
        self._files     = FileFrame(nb, self._station, self._logger)

        tabs = [
            (self._dashboard, "📊 Dashboard"),
            (self._sim,       "🌤️ Simulation"),
            (self._entry,     "✏️ Live Entry"),
            (self._analytics, "📈 Analytics"),
            (self._sensors,   "⚡ Sensors"),
            (self._files,     "💾 Files"),
        ]
        for frame,title in tabs:
            nb.add(frame, text=title)

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=BG3, height=22)
        bar.pack(fill="x",side="bottom")
        bar.pack_propagate(False)
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(bar, textvariable=self._status_var,
                 font=FONT_LBL, fg=TEXT2, bg=BG3, anchor="w",
                 padx=10).pack(side="left")
        tk.Label(bar, text=f"{CFG.MILESTONE}  |  Python + Tkinter  |  ICS 2276",
                 font=FONT_LBL, fg=TEXT2, bg=BG3, anchor="e",
                 padx=10).pack(side="right")

    def _on_close(self):
        self._logger.event("GUI application closed")
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = WeatherApp()
    app.run()