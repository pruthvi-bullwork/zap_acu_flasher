import subprocess
import re

def get_usb_status():
    lsusb = subprocess.run(['lsusb'], capture_output=True, text=True).stdout
    # RCM IDs for Orin Nano/NX are usually 0955:7020 or 0955:7ed0
    if "0955:7020" in lsusb or "0955:7ed0" in lsusb:
        return "RCM"
    # Normal booted ID you mentioned
    elif "0955:7372" in lsusb or "0955:" in lsusb:
        return "BOOTED"
    return "NONE"

def get_uid():
    # Use tegrarcm to pull the hardware ID
    res = subprocess.run(['sudo', './tegrarcm', '--uid'], capture_output=True, text=True)
    match = re.search(r'0x[0-9a-fA-F]+', res.stdout)
    return match.group(0) if match else None