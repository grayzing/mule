#!/usr/bin/env python3
import subprocess
import socket
import sys
import time

def run_cmd(cmd, check=True):
    """Helper to run a shell command and return stdout cleanly."""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed: {' '.join(cmd)}")
        print(f"Details: {e.stderr.strip()}")
        if check:
            sys.exit(1)
        return ""

def setup_virtual_interface():
    print("Checking for existing virtual interface 'uAP0'...")
    interfaces = run_cmd(["ip", "link", "show"])
    
    if "uAP0" in interfaces:
        print("[INFO] Interface 'uAP0' already exists.")
    else:
        print("[INFO] 'uAP0' not found. Creating virtual AP interface on wlan0...")
        # Add the virtual AP interface to the physical wlan0 radio chip
        run_cmd(["sudo", "iw", "dev", "wlan0", "interface", "add", "uAP0", "type", "__ap"])
        # Bring the interface link UP administratively
        run_cmd(["sudo", "ip", "link", "set", "uAP0", "up"])
        time.sleep(1)

def configure_networkmanager_ap():
    # Dynamically grab the device hostname
    hostname = socket.gethostname()
    ssid = hostname
    password = f"{hostname}123"
    
    print(f"[INFO] Targeting SSID: '{ssid}' with Password: '{password}'")
    
    # Check if an old profile named 'Field-AP' exists and clear it to prevent conflicts
    existing_connections = run_cmd(["nmcli", "-t", "-f", "NAME", "connection", "show"])
    if "Field-AP" in existing_connections.splitlines():
        print("[INFO] Cleaning up old 'Field-AP' NetworkManager profile...")
        run_cmd(["nmcli", "connection", "delete", "Field-AP"])
        
    print("[INFO] Creating and starting the NetworkManager Access Point...")
    # Add the connection profile locked specifically to the virtual uAP0 interface
    run_cmd([
        "nmcli", "device", "wifi", "hotspot",
        "ifname", "uAP0",
        "con-name", "Field-AP",
        "ssid", ssid,
        "password", password
    ])
    
    # Set route metric properties so client connections don't overwrite local paths
    print("[INFO] Adjusting routing priorities to prevent field lockouts...")
    run_cmd(["nmcli", "connection", "modify", "Field-AP", "ipv4.route-metric", "50"])
    
    # Ensure it autoconnects if the interface cycles
    run_cmd(["nmcli", "connection", "modify", "Field-AP", "connection.autoconnect", "yes"])
    
    print(f"\n[SUCCESS] Hotspot is up! You can now SSH into your Pi using:")
    print(f"  SSID: {ssid}")
    print(f"  Password: {password}")

if __name__ == "__main__":
    # Ensure network tools are available and user has sudo privileges
    setup_virtual_interface()
    configure_networkmanager_ap()
