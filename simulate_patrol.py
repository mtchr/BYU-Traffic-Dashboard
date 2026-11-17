"""
This script simulates a single vehicle (PD12) performing a patrol run in "Lot 16N" to test the dashboard's 
Active -> Partial -> Completed workflow. It sends GPS pings to the Django server at each step, allowing you to
verify that the dashboard updates correctly in real-time.

import requests
import time
from tracker.lot_polygons import CAMPUS_LOTS

# URL of your local Django server
WEBHOOK_URL = "http://127.0.0.1:8000/update_location/"
VEHICLE_ID = "PD12"

def get_lot_center(lot_name):
#    Calculates the exact middle of the polygon from your own data.
    if lot_name not in CAMPUS_LOTS:
        print(f"Error: {lot_name} not found in CAMPUS_LOTS.")
        return None
        
    coords = CAMPUS_LOTS[lot_name]
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    return center_lat, center_lon

def send_ping(lat, lon):
#   Fires the payload to your Django webhook.
    payload = {
        "vehicle_id": VEHICLE_ID,
        "lat": lat,
        "lon": lon
    }
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        print(f"[{time.strftime('%H:%M:%S')}] Sent ping at {lat:.5f}, {lon:.5f} - Server: {response.json()['status']}")
    except Exception as e:
        print(f"Failed to connect to server: {e}")

def run_test():
    # Pick a lot that you know has a 30-second default threshold (e.g., Lot 1)
    target_lot = "Lot 16N"
    center = get_lot_center(target_lot)
    
    if not center:
        return
        
    lat, lon = center
    
    # A fake coordinate "on the road" (somewhere in Utah Lake or far away)
    road_lat, road_lon = 40.2000, -111.7000 

    print("\n--- INITIATING DASHBOARD UI TEST ---")
    
    # ---------------------------------------------------------
    # TEST 1: ENTER THE LOT (Should turn Active / Yellow)
    # ---------------------------------------------------------
    print(f"\n1. Driving {VEHICLE_ID} into {target_lot}...")
    send_ping(lat, lon)
    print("-> Check Dashboard: Bubble should instantly appear as YELLOW (Active).")
    
    # ---------------------------------------------------------
    # TEST 2: THE PARTIAL RUN (Should turn Orange/Partial)
    # ---------------------------------------------------------
    print("\n2. Waiting 16 seconds to pass the verification noise filter...")
    time.sleep(16)
    send_ping(lat, lon) # Keep the stopwatch running
    
    print("\n3. Leaving the lot early!")
    send_ping(road_lat, road_lon)
    print("-> Check Dashboard: Bubble should turn ORANGE (Partial) with an '(Inc)' tag.")
    
    # ---------------------------------------------------------
    # TEST 3: THE COMPLETED RUN (Should turn Green/Completed)
    # ---------------------------------------------------------
    print("\n4. Driving back into the lot...")
    send_ping(lat, lon)
    print("-> Check Dashboard: Bubble should turn YELLOW (Active) again.")
    
    print("\n5. Waiting 32 seconds to complete the full patrol...")
    # Send a few pings to simulate driving around the lot
    time.sleep(10)
    send_ping(lat + 0.0001, lon) 
    time.sleep(10)
    send_ping(lat, lon - 0.0001)
    time.sleep(12)
    
    print("\n6. Leaving the lot after a successful patrol!")
    send_ping(road_lat, road_lon)
    print("-> Check Dashboard: Bubble should lock to GREEN (Completed).")
    print("\nTest Complete!")

if __name__ == "__main__":
    run_test()
"""

import requests
import time
import random
import threading
from tracker.lot_polygons import CAMPUS_LOTS

WEBHOOK_URL = "http://127.0.0.1:8000/update_location/"

# Provide the script with a list of guaranteed safe lots to pick from
AVAILABLE_LOTS = ["Lot 20", "Lot 39", "Lot 40", "Lot 40G", "Lot 45", "Lot 19", "Lot 10_11", "Lot 61", "Lot B67"]
ROAD_COORD = (40.2000, -111.7000)

def get_lot_center(lot_name):
    """Calculates the exact middle of the polygon."""
    if lot_name not in CAMPUS_LOTS:
        return None
        
    coords = CAMPUS_LOTS[lot_name]
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    
    return sum(lats) / len(lats), sum(lons) / len(lons)

def send_ping(vehicle_id, lat, lon):
    """Fires the payload to your Django webhook."""
    payload = {
        "vehicle_id": vehicle_id,
        "lat": lat,
        "lon": lon
    }
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=2)
        status = response.json().get('status', 'unknown')
        print(f"[{time.strftime('%H:%M:%S')}] {vehicle_id} pinged at {lat:.5f}, {lon:.5f} -> {status}")
    except Exception as e:
        print(f"FAILED TO PING {vehicle_id}: {e}")

def simulate_vehicle(vehicle_id, cycles=5):
    """The independent 'brain' for each vehicle."""
    print(f"--- {vehicle_id} unit initialized and on patrol. ---")
    
    for cycle in range(cycles):
        # 1. Drive on the road between lots
        for _ in range(3):
            send_ping(vehicle_id, ROAD_COORD[0], ROAD_COORD[1])
            time.sleep(5)

        # 2. Pick a random destination
        target_lot = random.choice(AVAILABLE_LOTS)
        center = get_lot_center(target_lot)
        if not center: 
            continue

        # 3. Decide behavior: 70% chance to complete it, 30% chance to leave early (Partial)
        run_type = random.choices(["COMPLETED", "PARTIAL"], weights=[0.7, 0.3])[0]
        stay_time = random.randint(35, 50) if run_type == "COMPLETED" else random.randint(16, 25)

        print(f"\n>>> {vehicle_id} entering {target_lot} for a {run_type} run ({stay_time} seconds) <<<")

        # 4. Stay in the lot and send pings every 5 seconds
        elapsed = 0
        while elapsed < stay_time:
            # Add tiny GPS jitter to simulate driving around the lot
            jitter_lat = center[0] + random.uniform(-0.0002, 0.0002)
            jitter_lon = center[1] + random.uniform(-0.0002, 0.0002)
            
            send_ping(vehicle_id, jitter_lat, jitter_lon)
            time.sleep(5)
            elapsed += 5

        print(f"<<< {vehicle_id} leaving {target_lot} >>>\n")

    print(f"--- {vehicle_id} has ended its shift. ---")

def run_multi_test():
    print("==================================================")
    print(" STARTING FLEET SIMULATION (Press Ctrl+C to stop) ")
    print("==================================================")
    
    # Define your active fleet
    vehicles = ["SE6", "SE4", "SE5"]
    threads = []

    for vid in vehicles:
        # Create a thread for each vehicle. Set to run 10 cycles (approx 10-15 mins)
        t = threading.Thread(target=simulate_vehicle, args=(vid, 10))
        t.daemon = True # Ensures threads die if you kill the main script
        threads.append(t)
        t.start()
        
        # Stagger the start times slightly so they don't ping at the exact same millisecond
        time.sleep(2)

    # Keep the main script alive while the threads do the work
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nSimulation aborted by user.")

if __name__ == "__main__":
    run_multi_test()