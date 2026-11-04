"""
Gray Greenridge
GeNeLa
ggree024@ucr.edu

This script queries the SDI12 <-> USB adapter made by Dr. Liu and then saves it so a .csv file
"""
import serial.tools.list_ports
import serial
import time
import yaml
import sys
import os
import threading
import pandas as pd
import subprocess
import socket
import requests
from datetime import datetime
from pathlib import Path
from rich import print

# Load configuration
with open("conf.yaml", "r") as file:
    config = yaml.safe_load(file)

possible_sensor_addresses = [chr(i) for i in list(range(48, 58)) + list(range(97, 123)) + list(range(65, 91))]
sensor_addresses: dict[str,list] = {}
soil_kpi_csv_path = config["sensors"]["buffer_csv_path"]
sensor_query_periodicity_s: int = config["sensors"]["sensor_periodicity_s"]

ap_ssid = config["networking"]["ap_ssid"]
ap_pw = config["networking"]["ap_pw"]
ap_scan_interval: float = config["networking"]["ap_scan_interval"]
buffer_csv_path: str = config["sensors"]["buffer_csv_path"]
data_reservoir_ip: str = config["networking"]["data_reservoir_ip"]

data_csv_lock = threading.Lock() # lock for reading and writing from the data csv
hostname = socket.gethostname() # hostname

def ensure_uap0_exists():
    """Checks the kernel for uAP0, and recreates it cleanly if it was destroyed."""
    try:
        # Check if uAP0 exists in the system interfaces
        res = subprocess.run(["ip", "link", "show", "uAP0"], capture_output=True, text=True)
        if res.returncode != 0:
            print("[yellow]uAP0 interface was destroyed by the hardware driver! Re-creating it...[/yellow]")
            # Re-initialize the virtual chip space
            subprocess.run(["sudo", "iw", "dev", "wlan0", "interface", "add", "uAP0", "type", "__ap"], check=True)
            # Re-spoof the isolated MAC address
            subprocess.run(["sudo", "ip", "link", "set", "dev", "uAP0", "address", "02:00:00:00:00:55"], check=True)
            # Bring it up link-wise
            subprocess.run(["sudo", "ip", "link", "set", "uAP0", "up"], check=True)
            time.sleep(1)
    except Exception as e:
        print(f"[red]Failed to repair uAP0 kernel interface: {e}[/red]")


def get_sdi12_to_usb_ports() -> list[serial.Serial] | None:
    list_of_ports: list[serial.Serial] = []
    print("Finding port for SDI12 <-> USB")
    ports = serial.tools.list_ports.comports()
    
    for port in ports:
        # FTDI chip (VID 0x0403) = SDI-12 adapter
        if port.vid == 0x0403:
            print(f"[green]Found candidate port: {port.device} ({port.description})[/green]")
            list_of_ports.append(serial.Serial(
                            port=port.device,
                            baudrate=9600,
                            bytesize=8,
                            parity="N"))
            sensor_addresses[str(port.device)] = []

    if len(list_of_ports) == 0:
        return None
    return list_of_ports



def detect_sensor_addresses(list_of_serials: list[serial.Serial]):
    for ser in list_of_serials:
        if not ser.port:
            print(f"[red]Serial has no port! WTF?[/red]")
            continue
        ser.timeout = 0.2
        print(f"Detecting sensor addresses on serial {ser.port}")
        for address in possible_sensor_addresses:
            if address == 'z': # Just skip, z is for the adapter
                continue
            
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            time.sleep(0.05) 
            
            m_command = f"{address}!".encode('utf-8')
            ser.write(m_command)
            ser.flush()

            sdi_12_line = ser.readline()
            raw_decoded = sdi_12_line.decode('utf-8', errors='ignore').strip()

            if raw_decoded and address in raw_decoded:
                print(f"[green]Sensor with address {address} on serial {ser.port} found! (Response: '{raw_decoded}')[/green]")
                sensor_addresses[ser.port].append(address)

def query_sensor(ser: serial.Serial, addr: str) -> str:
    clean_addr = str(addr).strip() 
    ser.reset_input_buffer()

    m_command = f"{clean_addr}M!".encode('utf-8')
    ser.write(m_command)
    ser.flush()
    
    time.sleep(0.2) 
    
    m_response = ser.readline().decode('utf-8', errors='ignore').strip()
    
    time.sleep(1.2) 
    
    if ser.in_waiting > 0:
        ser.readline()
        
    d_command = f"{clean_addr}D0!".encode('utf-8')
    ser.write(d_command)
    ser.flush()
    
    time.sleep(0.3)
    
    sdi_12_line = ser.readline()
    raw_decoded = sdi_12_line.decode('utf-8', errors='ignore').strip()

    return raw_decoded


def is_already_connected():
        """Return True if currently active on the target AP, False otherwise."""
        try:
            # -t gives terse output, -f common fields. 
            # 'active' column will show 'yes' if active.
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,ACTIVE", "device", "wifi", "list"],
                capture_output=True,
                text=True,
                check=True
            )
            
            for line in result.stdout.splitlines():
                if not line:
                    continue
                if ":" in line:
                    ssid, active = line.rsplit(":", 1)
                    if ssid == ap_ssid and active.lower() == "yes":
                        return True
        except subprocess.CalledProcessError:
            pass
        
        return False

def find_ap():
    """Return the signal strength of the target AP, or None."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL", "device", "wifi", "list"],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error scanning for networks: {e.stderr.strip()}")
        return None

    for line in result.stdout.splitlines():
        if not line:
            continue

        if ":" in line:
            ssid, signal = line.rsplit(":", 1)
            if ssid == ap_ssid:
                try:
                    return int(signal)
                except ValueError:
                    continue

    return None

def thread_sensor_accumulation():
    if not list_of_serials:
        return
    if not Path(soil_kpi_csv_path).exists():
        print("[green]Creating csv file[/green]")
        headers = ["timestamp","address", "serial", "raw_decoded"]
        df = pd.DataFrame(columns=headers)
        df.to_csv(soil_kpi_csv_path, index=False)
    print("[green]Starting measurement accumulation loop...[/green]")
    
    while True:
        for ser in list_of_serials:
            if not ser.port:
                print(f"[red]Serial has no port? WTF?[/red]")
                return
            for address in sensor_addresses[ser.port]:
                raw_decoded = query_sensor(ser, address)
                print(f"Sensor reading for sensor with address {address}: {raw_decoded}")

                try:
                    # Append parsed payload to CSV (safe against the networking
                    # component claiming/rotating the buffer file mid-loop)
                    timestamp = datetime.now().isoformat()
                    with data_csv_lock:
                        soil_data_row = pd.DataFrame({
                            "timestamp": timestamp,
                            "address": address,
                            "serial": ser.port,
                            "raw_decoded": str(raw_decoded)
                        },index=[0])
                        soil_data_row.to_csv(soil_kpi_csv_path, mode='a', index=False, header=False)
                        print(f"[blue]Successfully saved measurement for address {address} to CSV.[/blue]")

                except (IndexError, ValueError) as e:
                    print(f"[red]Error parsing payload from sensor {address} ('{raw_decoded}'): {e}[/red]")
                    print(f"[red]Removing sensor {address} from the query list for this session[/red]")
                    if len(sensor_addresses[ser.port]) > 1:
                        sensor_addresses[ser.port].remove(address)
                    else:
                        print(f"[red]All sensor addresses nonfunctioning for serial {ser.port}![/red]")

            time.sleep(sensor_query_periodicity_s)

def connect():
    """Brings up the pre-configured network profile cleanly."""
    print(f"Connecting to {ap_ssid}...")
    
    # Using the pre-built connection profile avoids the key-mgmt CLI bug entirely
    result = subprocess.run(
        ["nmcli", "connection", "up", ap_ssid],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("Connected successfully!")
        return True

    print("Connection failed:")
    print(result.stderr.strip())
    return False

def disconnect():
    print(f"Disconnecting from {ap_ssid}...")
    # 1. Break the client uplink
    subprocess.run(["nmcli", "connection", "down", ap_ssid], capture_output=True)
    time.sleep(1)
    
    # 2. Repair the hardware interface that the kernel just deleted
    ensure_uap0_exists()
    
    # 3. Bring your Field-AP back online safely
    print("[green]Re-activating Field-AP fallback hotspot...[/green]")
    subprocess.run(["nmcli", "connection", "up", "Field-AP"], capture_output=True)


def is_ssh_active() -> bool:
    """Return True if there is an active, established SSH session to this Pi."""
    try:
        # Check active tcp sockets looking for established SSH connections
        result = subprocess.run(
            "ss -t -a | grep -i ssh | grep -i established", 
            shell=True, capture_output=True, text=True
        )
        return len(result.stdout.strip()) > 0
    except Exception:
        # Fallback: if the ss command fails, assume safe to prevent field lockout
        return False

def thread_drone_uplink():
    print(f"[green]Monitoring network state for AP: {ap_ssid}[/green]")
    check_file_path = Path(buffer_csv_path)  # Synced cleanly with your config variable

    while True:
        # CRITICAL SAFETY CHECK:
        # If you are working on the Pi via SSH in the field, freeze client network changes
        if is_ssh_active():
            print("[yellow]SSH Session active. Ensuring Field-AP interface health...[/yellow]")
            ensure_uap0_exists()
            time.sleep(ap_scan_interval)
            continue

        # Check if we have data ready to be uploaded
        if check_file_path.is_file():
            # Uses the optimized find_ap() with '--rescan no' to protect virtual AP stability
            signal = find_ap()
            
            if signal is not None:
                print(f"[green]Target AP found (Signal: {signal}%). Connecting...[/green]")
                
                if connect():
                    time.sleep(2) # Given routing tables a brief moment to stabilize
                    
                    try:
                        url = f'http://{data_reservoir_ip}/soil_kpi_handler'

                        with data_csv_lock:
                            # Double-check file existence under lock constraint
                            if check_file_path.is_file():
                                df = pd.read_csv(soil_kpi_csv_path)
                                row_count = len(df.index)

                                with open(soil_kpi_csv_path, 'rb') as file_to_send:
                                    files = {'file': file_to_send, 'hostname': hostname}
                                    response = requests.post(url, files=files, timeout=15)

                                if response.status_code == 200:
                                    print("[green]File sent successfully![/green]")
                                    if int(response.json().get("row_count", 0)) == row_count:
                                        print("[green]Row counts match. Clearing the buffer![/green]")
                                        os.remove(buffer_csv_path)
                                    else:
                                        print("[red]Row count mismatch! Retaining buffer.[/red]")
                                else:
                                    print(f"[red]Server returned status code: {response.status_code}[/red]")
                                
                    except requests.exceptions.RequestException as e:
                        print(f"[red]Network error during POST request: {e}[/red]")
                    
                    finally:
                        # CRITICAL: Always disconnect to return interface control to uAP0
                        disconnect()
            else:
                # AP not found or signal too weak to safely try a handshake
                pass

        time.sleep(ap_scan_interval)



if __name__ == "__main__":
    list_of_serials = get_sdi12_to_usb_ports()
    time.sleep(2.5) # delay for arduino bootloader and the 1 second delay of the adapter.

    if not list_of_serials:
        print("[red]No candidate ports found. Is your SDI-12 to USB adapter(s) connected and receiving power? Terminating...[/red]")
        sys.exit()

    print("[green]Detecting sensor addresses. This will take a minute.[/green]")
    detect_sensor_addresses(list_of_serials)

    for ser in list_of_serials:
        time.sleep(1.5)  # Give the adapter hardware time to settle down
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        

    sensor_accumulation_thread = threading.Thread(
        target=thread_sensor_accumulation, 
        name="Sensor Accumulation Thread",
    )
    network_drone_uplink_thread = threading.Thread(
        target=thread_drone_uplink,
        name="Drone Uplink Network Thread"
    )

    sensor_accumulation_thread.start()
    network_drone_uplink_thread.start()
