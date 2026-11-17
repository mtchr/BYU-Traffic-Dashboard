import requests
import time
import random

URL = 'http://127.0.0.1:8000/update_location/'

def send_gps(units):
    lat, lon = 40.25, -111.65  # starting point at center of campus
    fleet = ["PD12", "PD3", "PD11"]
    
    try:
        while True:
            for unit in fleet:
                lat += random.uniform(-0.0001, 0.0001)
                lon += random.uniform(-0.0001, 0.0001)
                # The Pi ONLY sends identity and location
                data = {
                    "vehicle_id": unit,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6)
                }
                
                try:
                    requests.post(URL, json=data, timeout=5)
                    print(f"Sent: {unit} at {lat}, {lon}")
                except requests.exceptions.ConnectionError:
                    print("Error: Could not connect to Django.")

            time.sleep(5)
    except KeyboardInterrupt:
        print("\nSimulation stopped.")

if __name__ == "__main__":
    send_gps("")