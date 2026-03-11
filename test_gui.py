import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
import subprocess
import re
import time
import os
import threading
import queue

from sheets_db import SheetsDB

# ========================================================
# CONSTANTS & FOLDER IDS
# ========================================================
GOOGLE_DRIVE_FOLDER_ID = "0AM3yJfNKTJr6Uk9PVA" 
PLATFORM_DRIVE_FOLDER_ID = "14QY2BS1efMujYIlnm1NR1VmXNf7zrJc3" 

LOCAL_BACKUPS_DIR = "/home/pruthvir/Documents/acu_fleet_manager/jetson_image_toolkit/backups"
FLASH_SCRIPT_PATH = "/home/pruthvir/Documents/acu_fleet_manager/jetson_image_toolkit/flash_from_zip.sh"

HOST_SEARCH_PATHS = [
    LOCAL_BACKUPS_DIR,
    "/home/pruthvir/jetson_image_toolkit/backups",
    "/home/pruthvir/Downloads",
    "/home/pruthvir/Downloads/images"
]

# ========================================================
# GUI THEME CONSTANTS (BULLWORK BRAND EDITION)
# ========================================================
BG_COLOR = "#0D1117"          # Pitch Black / Dark Carbon
PANEL_BG = "#161B22"          # Dark Gray Panel Background
FG_COLOR = "#E6EDF3"          # Crisp White Text
MUTED_FG = "#8B949E"          # Dimmed Gray Text
BRAND_PURPLE = "#8A2BE2"      # Bullwork High-Contrast Purple
SUCCESS_GREEN = "#238636"     # Dark-mode safe Green
DANGER_RED = "#DA3633"        # Dark-mode safe Red

FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_MAIN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")

# ========================================================
# CUSTOM VECTOR ROCKET PROGRESS BAR (CRASH-FREE)
# ========================================================
class RocketProgressBar(tk.Canvas):
    def __init__(self, parent, width=350, height=60, bg_color=BG_COLOR, **kwargs):
        super().__init__(parent, width=width, height=height, bg=bg_color, highlightthickness=0, **kwargs)
        self.width = width
        self.height = height
        self.start_x = 40
        self.end_x = width - 40
        self.cy = height // 2
        
        # 1. Trajectory Track
        self.create_line(self.start_x, self.cy, self.end_x, self.cy, fill="#30363D", dash=(4, 4), width=2)
        
        # 2. Draw Earth (Blue Ocean with Green Landmasses)
        self.create_oval(self.start_x-14, self.cy-14, self.start_x+14, self.cy+14, fill="#0D47A1", outline="")
        self.create_polygon(self.start_x-8, self.cy-4, self.start_x, self.cy-12, self.start_x+6, self.cy-6, fill="#2E7D32", outline="")
        self.create_polygon(self.start_x-2, self.cy+4, self.start_x+8, self.cy+12, self.start_x+12, self.cy+2, fill="#2E7D32", outline="")
        
        # 3. Draw Moon (Silver with Craters)
        self.create_oval(self.end_x-14, self.cy-14, self.end_x+14, self.cy+14, fill="#9E9E9E", outline="")
        self.create_oval(self.end_x-6, self.cy-8, self.end_x+2, self.cy, fill="#757575", outline="")
        self.create_oval(self.end_x+4, self.cy+4, self.end_x+10, self.cy+10, fill="#757575", outline="")
        
        self.rocket_ids = []
        self.progress_line_id = None
        self.set_progress(0)

    def set_progress(self, pct):
        if pct < 0: pct = 0
        if pct > 100: pct = 100
        
        # Clear old rocket
        for rid in self.rocket_ids:
            self.delete(rid)
        self.rocket_ids.clear()
        if self.progress_line_id:
            self.delete(self.progress_line_id)
            
        current_x = self.start_x + (self.end_x - self.start_x) * (pct / 100.0)
        
        # Draw Purple Laser Trail
        if current_x > self.start_x:
            self.progress_line_id = self.create_line(self.start_x, self.cy, current_x, self.cy, fill=BRAND_PURPLE, width=3)
            
        # Draw Rocket Engine Flames
        f1 = self.create_polygon(current_x-16, self.cy-4, current_x-26, self.cy, current_x-16, self.cy+4, fill="#FF9800", outline="")
        f2 = self.create_polygon(current_x-16, self.cy-2, current_x-20, self.cy, current_x-16, self.cy+2, fill="#FFEB3B", outline="")
        
        # Draw Rocket Body
        r_body = self.create_polygon(
            current_x-16, self.cy-5,
            current_x+4, self.cy-5,
            current_x+16, self.cy,
            current_x+4, self.cy+5,
            current_x-16, self.cy+5,
            fill="#F8F9FA", outline="#D1D5DB", width=1
        )
        
        # Draw Rocket Window & Fins
        r_win = self.create_oval(current_x+2, self.cy-2, current_x+8, self.cy+2, fill="#0D47A1", outline="")
        r_fin1 = self.create_polygon(current_x-16, self.cy-5, current_x-10, self.cy-5, current_x-16, self.cy-12, fill=BRAND_PURPLE, outline="")
        r_fin2 = self.create_polygon(current_x-16, self.cy+5, current_x-10, self.cy+5, current_x-16, self.cy+12, fill=BRAND_PURPLE, outline="")
        
        # Save IDs so they can be deleted and redrawn on next frame
        self.rocket_ids.extend([f1, f2, r_body, r_win, r_fin1, r_fin2])


# --- FLASHING PROGRESS DIALOG ---
class FlashProgressDialog(tk.Toplevel):
    def __init__(self, parent, version):
        super().__init__(parent)
        self.title("Flashing Jetson")
        self.update_idletasks()
        w, h = 450, 220
        x = int((self.winfo_screenwidth() / 2) - (w / 2))
        y = int((self.winfo_screenheight() / 2) - (h / 2))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.grab_set()
        self.config(bg=BG_COLOR)

        tk.Label(self, text=f"DEPLOYING TARGET IMAGE", font=FONT_TITLE, bg=BG_COLOR, fg=BRAND_PURPLE).pack(pady=10)
        
        self.lbl_action = tk.Label(self, text="Preparing Environment...", font=FONT_BOLD, bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_action.pack(pady=5)

        self.rocket_bar = RocketProgressBar(self, width=380, height=60)
        self.rocket_bar.pack(pady=5)
        self.fake_pct = 0.0 

        self.lbl_pct = tk.Label(self, text="0%", font=FONT_BOLD, bg=BG_COLOR, fg=BRAND_PURPLE)
        self.lbl_pct.pack()

        self.lbl_detail = tk.Label(self, text="Initializing...", font=("Courier", 8), bg=BG_COLOR, fg=MUTED_FG)
        self.lbl_detail.pack(pady=5)

    def update_status(self, action_text, detail_text="", inc_amt=0.0, force_pct=None):
        if action_text:
            self.lbl_action.config(text=action_text)
            
        if force_pct is not None:
            self.fake_pct = force_pct
        elif inc_amt > 0:
            self.fake_pct = min(98.0, self.fake_pct + inc_amt)
            
        self.rocket_bar.set_progress(int(self.fake_pct))
        self.lbl_pct.config(text=f"{int(self.fake_pct)}%")

        if detail_text:
            if len(detail_text) > 60: detail_text = "..." + detail_text[-57:]
            self.lbl_detail.config(text=detail_text)


# --- LIVE BVT PROGRESS DIALOG ---
class BVTProgressDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Executing BVT Suite")
        self.update_idletasks()
        w, h = 400, 200
        x = int((self.winfo_screenwidth() / 2) - (w / 2))
        y = int((self.winfo_screenheight() / 2) - (h / 2))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.grab_set()
        self.config(bg=BG_COLOR)

        tk.Label(self, text="BUILD VERIFICATION TEST", font=FONT_TITLE, bg=BG_COLOR, fg=BRAND_PURPLE).pack(pady=10)
        self.lbl_status = tk.Label(self, text="Initializing SSH Connection...", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_status.pack(pady=5)
        
        self.rocket_bar = RocketProgressBar(self, width=350, height=60)
        self.rocket_bar.pack(pady=10)

    def update_progress(self, current, total):
        pct = int((current / total) * 100) if total > 0 else 0
        self.rocket_bar.set_progress(pct)
        self.lbl_status.config(text=f"Testing... Step {current} of {total} ({pct}%)")
        self.update()


# --- BVT RESULTS DIALOG ---
class BVTResultDialog(tk.Toplevel):
    def __init__(self, parent, stats):
        super().__init__(parent)
        self.title("BVT Execution Results")
        self.update_idletasks()
        w, h = 420, 250
        x = int((self.winfo_screenwidth() / 2) - (w / 2))
        y = int((self.winfo_screenheight() / 2) - (h / 2))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.result = "ABORT" 
        self.grab_set()
        self.config(bg=BG_COLOR)

        parts = stats.split(",")
        rate = parts[1] if len(parts) > 1 else "Unknown"
        fails = parts[2] if len(parts) > 2 and parts[2].strip() else "None"

        tk.Label(self, text="BVT TESTING COMPLETE", font=FONT_TITLE, bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
        color = SUCCESS_GREEN if rate == "100%" else "#E3A008"
        tk.Label(self, text=f"SUCCESS RATE: {rate}", font=("Segoe UI", 12, "bold"), bg=BG_COLOR, fg=color).pack(pady=5)

        if fails != "None":
            tk.Label(self, text=f"Failures Detected:\n{fails}", font=FONT_MAIN, bg=BG_COLOR, fg=DANGER_RED, wraplength=380, justify="center").pack(pady=5)
        else:
            tk.Label(self, text="🌟 ALL SYSTEMS PASSED! 🌟", font=FONT_BOLD, bg=BG_COLOR, fg=SUCCESS_GREEN).pack(pady=5)

        btn_frame = tk.Frame(self, bg=BG_COLOR)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="SAVE & COMPLETE", bg=BRAND_PURPLE, fg=FG_COLOR, font=FONT_BOLD, width=16, relief="flat", command=self.complete).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="RETEST BVT", bg=PANEL_BG, fg=FG_COLOR, font=FONT_BOLD, width=16, relief="flat", command=self.retest).pack(side=tk.LEFT, padx=10)

    def complete(self): self.result = "COMPLETE"; self.destroy()
    def retest(self): self.result = "RETEST"; self.destroy()


# --- BOOT PING CHECK DIALOG ---
class DeviceWaitDialog(tk.Toplevel):
    def __init__(self, parent, jetson_ip):
        super().__init__(parent)
        self.title("Waiting for Jetson OS")
        self.update_idletasks()
        w, h = 350, 230
        x = int((self.winfo_screenwidth() / 2) - (w / 2))
        y = int((self.winfo_screenheight() / 2) - (h / 2))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.result = False
        self.time_left = 180 
        self.max_time = 180
        self.is_cancelled = False
        self.jetson_ip = jetson_ip
        self.grab_set()
        self.config(bg=BG_COLOR)
        
        tk.Label(self, text="WAITING FOR TARGET OS", font=FONT_TITLE, bg=BG_COLOR, fg=BRAND_PURPLE).pack(pady=10)
        self.lbl_time = tk.Label(self, text=f"Pinging {self.jetson_ip}...\nTimeout in: {self.time_left}s", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_time.pack()
        
        self.rocket_bar = RocketProgressBar(self, width=300, height=60)
        self.rocket_bar.pack(pady=10)
        
        tk.Button(self, text="CANCEL WAIT", command=self.cancel_wait, bg=PANEL_BG, fg=DANGER_RED, font=FONT_BOLD, relief="flat", width=15).pack(pady=5)
        self.after(2000, self.check_boot)

    def cancel_wait(self):
        self.is_cancelled = True; self.result = False; self.destroy()

    def check_boot(self):
        if self.is_cancelled: return
        
        response = subprocess.run(['ping', '-c', '1', '-W', '1', self.jetson_ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if response.returncode == 0:
            self.rocket_bar.set_progress(100)
            self.lbl_time.config(text="Target Online!\nWaiting 5 seconds for SSH to start...", fg=SUCCESS_GREEN)
            self.update()
            time.sleep(5) 
            self.result = True
            self.destroy()
            return
            
        self.time_left -= 1
        pct = int(((self.max_time - self.time_left) / self.max_time) * 100)
        self.rocket_bar.set_progress(pct)
        self.lbl_time.config(text=f"Pinging {self.jetson_ip}...\nTimeout in: {self.time_left}s")
        
        if self.time_left <= 0:
            self.result = False; self.destroy()
        else:
            self.after(1000, self.check_boot)


# --- HARDWARE REGISTRATION WINDOW ---
class RegistrationWindow(tk.Toplevel):
    def __init__(self, parent, uid, callback, platform_options, existing_data=None):
        super().__init__(parent)
        self.title("Hardware Configuration Setup")
        self.geometry("500x600")
        self.callback = callback
        self.uid = uid
        self.existing_data = existing_data or {} 
        self.grab_set() 
        self.config(bg=BG_COLOR)

        mode_text = "UPGRADE TARGET BUILD" if existing_data else "REGISTER NEW TARGET"
        tk.Label(self, text=mode_text, font=FONT_TITLE, bg=BG_COLOR, fg=BRAND_PURPLE).pack(pady=15)
        tk.Label(self, text="Leave any field blank to auto-fill with 'NIL'.", font=("Segoe UI", 9, "italic"), bg=BG_COLOR, fg=MUTED_FG).pack(pady=5)

        self.setup_var = tk.StringVar(value="Vehicle")
        frame_type = tk.Frame(self, bg=BG_COLOR)
        frame_type.pack(pady=5)
        
        style = ttk.Style()
        style.configure("TRadiobutton", background=BG_COLOR, foreground=FG_COLOR, font=FONT_MAIN)
        ttk.Radiobutton(frame_type, text="On-Vehicle Setup", variable=self.setup_var, value="Vehicle", command=self.toggle_fields, style="TRadiobutton").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(frame_type, text="Bench Setup", variable=self.setup_var, value="Bench", command=self.toggle_fields, style="TRadiobutton").pack(side=tk.LEFT, padx=10)

        self.fields = {}
        form_frame = tk.Frame(self, bg=PANEL_BG, padx=15, pady=15, bd=0)
        form_frame.pack(pady=10, padx=20, fill="both")

        config_options = ["coir_no_replan_T1_nav2", "coir_no_replan_T3_nav2", "construction_T1_nav2", "construction_T3_nav2", "NIL"]

        form_layout = [
            ("Platform Version:", "plat_ver_raw", platform_options), 
            ("Configuration:", "config", config_options),
            ("Vehicle Number:", "veh_num", ["", "VEH-", "NIL"]),
            ("ACU Box Number:", "acu_id", ["", "ACU-", "NIL"]),
            ("Router Number:", "router", ["", "NIL"]),
            ("M2M SIM Number:", "m2m_sim", ["", "NIL"])
        ]

        for i, (label_text, key, options) in enumerate(form_layout):
            tk.Label(form_frame, text=label_text, font=FONT_BOLD, bg=PANEL_BG, fg=FG_COLOR).grid(row=i, column=0, sticky="w", pady=10)
            combo = ttk.Combobox(form_frame, values=options, width=30, font=FONT_MAIN)
            combo.grid(row=i, column=1, pady=10, padx=10)
            
            if key == "plat_ver_raw" and existing_data and existing_data.get('plat_ver') != "NIL":
                match = next((opt for opt in options if existing_data['plat_ver'] in opt), options[0] if options else "")
                combo.set(match)
            elif existing_data and key in existing_data and existing_data[key] != "NIL":
                combo.set(existing_data[key])
            elif options: 
                combo.set(options[0])
                
            self.fields[key] = combo
            
        tk.Button(self, text="CONTINUE TO DEPLOYMENT >", bg=BRAND_PURPLE, fg=FG_COLOR, font=FONT_TITLE, relief="flat", height=2, width=28, command=self.submit).pack(pady=20)

    def toggle_fields(self):
        locked_keys = ["veh_num", "acu_id", "m2m_sim", "router"]
        if self.setup_var.get() == "Bench":
            for key in locked_keys:
                self.fields[key].set("NIL")
                self.fields[key].config(state="disabled")
        else:
            for key in locked_keys:
                self.fields[key].config(state="normal")
                if self.fields[key].get() == "NIL":
                    if key in self.existing_data and self.existing_data[key] != "NIL":
                        self.fields[key].set(self.existing_data[key])
                    else:
                        self.fields[key].set("")

    def submit(self):
        data = {"uid": self.uid, "setup_type": self.setup_var.get(), "bvt_test": "Pending"}
        keys = ["plat_ver_raw", "config", "veh_num", "acu_id", "router", "m2m_sim"]
        for key in keys:
            val = self.fields[key].get().strip()
            data[key] = val if val != "" else "NIL"
            
        raw_plat = data['plat_ver_raw']
        data['plat_ver'] = raw_plat.replace(" (Local)", "").replace(" (Drive)", "")
        
        self.destroy() 
        self.callback(data)


# --- MAIN APP ---
class ACUFleetManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ACU Target Manager - Bullwork Edition")
        self.root.update_idletasks()
        
        window_height = 700
        x = int((self.root.winfo_screenwidth() / 2) - (600 / 2))
        y = int((self.root.winfo_screenheight() / 2) - (window_height / 2))
        self.root.geometry(f"600x{window_height}+{x}+{y}")
        self.root.config(bg=BG_COLOR)
        
        self.db = SheetsDB()
        self.current_uid = None
        self.current_record = None
        self.sudo_pwd = None 
        
        self.local_files = {}
        self.drive_files = {}

        # HEADER
        header = tk.Frame(root, bg="#010409", pady=15)
        header.pack(fill="x")
        tk.Label(header, text="TARGET ENVIRONMENT SETUP", font=FONT_TITLE, bg="#010409", fg=BRAND_PURPLE).pack()
        
        self.status_label = tk.Label(root, text="Status: Checking Target Connection...", font=FONT_BOLD, bg=BG_COLOR, fg=MUTED_FG)
        self.status_label.pack(pady=10)
        
        self.read_btn = tk.Button(root, text="SCAN JETSON MODULE", command=self.scan_uid, width=30, height=2, bg=PANEL_BG, fg=FG_COLOR, font=FONT_BOLD, relief="flat")
        self.read_btn.pack(pady=5)

        # INFO PANEL
        self.info_frame = tk.Frame(root, bg=PANEL_BG, bd=0)
        tk.Label(self.info_frame, text="TARGET COMPONENTS", font=FONT_BOLD, bg=PANEL_BG, fg=BRAND_PURPLE).pack(anchor="w", padx=15, pady=10)
        
        self.lbl_sn = tk.Label(self.info_frame, text=">  Module SN: Waiting for scan...", font=FONT_MAIN, bg=PANEL_BG, fg=FG_COLOR)
        self.lbl_sn.pack(anchor="w", padx=20, pady=2)
        self.lbl_veh = tk.Label(self.info_frame, text=">  Vehicle Number: --", font=FONT_MAIN, bg=PANEL_BG, fg=FG_COLOR)
        self.lbl_veh.pack(anchor="w", padx=20, pady=2)
        self.lbl_acu = tk.Label(self.info_frame, text=">  ACU Box Number: --", font=FONT_MAIN, bg=PANEL_BG, fg=FG_COLOR)
        self.lbl_acu.pack(anchor="w", padx=20, pady=2)
        self.lbl_plat = tk.Label(self.info_frame, text=">  OS Image Version: --", font=FONT_MAIN, bg=PANEL_BG, fg=FG_COLOR)
        self.lbl_plat.pack(anchor="w", padx=20, pady=2)
        self.lbl_config = tk.Label(self.info_frame, text=">  Configuration: --", font=FONT_MAIN, bg=PANEL_BG, fg=FG_COLOR)
        self.lbl_config.pack(anchor="w", padx=20, pady=2)
        self.lbl_updated = tk.Label(self.info_frame, text=">  Status: --", font=FONT_MAIN, bg=PANEL_BG, fg=FG_COLOR)
        self.lbl_updated.pack(anchor="w", padx=20, pady=10)

        self.db_status_label = tk.Label(root, text="", font=FONT_BOLD, bg=BG_COLOR, fg=MUTED_FG)
        self.db_status_label.pack(pady=10)
        
        # ACTION BUTTONS
        self.action_frame = tk.Frame(root, bg=BG_COLOR)
        self.action_frame.pack(pady=5)

        self.btn_repair = tk.Button(self.action_frame, text="REPAIR IMAGE", command=self.repair_flash, width=20, height=2, bg=PANEL_BG, fg=FG_COLOR, font=FONT_BOLD, relief="flat")
        self.btn_upgrade = tk.Button(self.action_frame, text="UPGRADE IMAGE", command=self.upgrade_build, width=20, height=2, bg=BRAND_PURPLE, fg=FG_COLOR, font=FONT_BOLD, relief="flat")
        self.btn_new_flash = tk.Button(self.action_frame, text="INITIALIZE FLASH", command=self.setup_new_flash, width=20, height=2, bg=BRAND_PURPLE, fg=FG_COLOR, font=FONT_BOLD, relief="flat")
        self.btn_replace = tk.Button(self.action_frame, text="RMA / REPLACE", command=self.replace_hardware, width=20, height=2, bg=PANEL_BG, fg=DANGER_RED, font=FONT_BOLD, relief="flat")

        self.update_usb_status()
        self.root.after(500, self.refresh_platforms)

    # ========================================================
    # SMART PLATFORM LOGIC
    # ========================================================
    def refresh_platforms(self):
        self.db_status_label.config(text="Scanning Host & Cloud for Target Images...", fg=BRAND_PURPLE)
        self.root.update()
        
        self.local_files.clear()
        self.drive_files.clear()

        os.makedirs(LOCAL_BACKUPS_DIR, exist_ok=True)
        for directory in HOST_SEARCH_PATHS:
            if os.path.exists(directory):
                for f in os.listdir(directory):
                    if f.endswith('.zip') and "acu_platform" in f:
                        full_path = os.path.join(directory, f)
                        if os.path.getsize(full_path) > 1000000:
                            self.local_files[f] = full_path
                        else:
                            if directory == LOCAL_BACKUPS_DIR: os.remove(full_path)

        remote_files = self.db.get_drive_files(PLATFORM_DRIVE_FOLDER_ID)
        for d_file in remote_files:
            if d_file['name'].endswith('.zip') and d_file['name'] not in self.local_files:
                self.drive_files[d_file['name']] = d_file['id']

        self.db_status_label.config(text="Environment Sync Complete.", fg=MUTED_FG)

    def get_dropdown_options(self):
        options = []
        for loc_f in self.local_files.keys():
            options.append(f"{loc_f} (Local)")
        for drv_f in self.drive_files.keys():
            options.append(f"{drv_f} (Drive)")
        return sorted(options, reverse=True) if options else ["No OS Images Found"]

    def download_platform(self, file_id, filename):
        dest_path = os.path.join(LOCAL_BACKUPS_DIR, filename)
        dlg = tk.Toplevel(self.root)
        dlg.title(f"Downloading {filename}")
        w, h = 400, 200
        x = int((self.root.winfo_screenwidth() / 2) - (w / 2))
        y = int((self.root.winfo_screenheight() / 2) - (h / 2))
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.grab_set()
        dlg.config(bg=BG_COLOR)
        
        tk.Label(dlg, text=f"DOWNLOADING COMPONENT", font=FONT_TITLE, bg=BG_COLOR, fg=BRAND_PURPLE).pack(pady=10)
        tk.Label(dlg, text=f"{filename}", font=FONT_MAIN, bg=BG_COLOR, fg=MUTED_FG).pack(pady=5)
        
        rocket_bar = RocketProgressBar(dlg, width=350, height=60)
        rocket_bar.pack(pady=10)
        
        lbl_pct = tk.Label(dlg, text="0%", font=FONT_BOLD, bg=BG_COLOR, fg=BRAND_PURPLE)
        lbl_pct.pack()
        
        def update_prog(pct):
            rocket_bar.set_progress(pct)
            lbl_pct.config(text=f"{pct}%")
            dlg.update()
            
        success = self.db.download_file(file_id, dest_path, update_prog)
        dlg.destroy()
        
        if success:
            self.local_files[filename] = dest_path
            return dest_path
        else:
            if os.path.exists(dest_path): os.remove(dest_path) 
            return None

    # ========================================================
    # HARDWARE MANAGER LOGIC
    # ========================================================
    def update_usb_status(self):
        try:
            lsusb = subprocess.run(['lsusb'], capture_output=True, text=True).stdout
            if "0955:7523" in lsusb: self.status_label.config(text="TARGET READY: Recovery Mode Detected", fg=SUCCESS_GREEN)
            elif "0955:" in lsusb: self.status_label.config(text="TARGET WARNING: Booted Normally (RCM Required)", fg="#E3A008")
            else: self.status_label.config(text="TARGET ERROR: No Connection", fg=DANGER_RED)
        except Exception: self.status_label.config(text="Error reading USB tree", fg=DANGER_RED)

    def get_sudo_password(self):
        if not self.sudo_pwd: self.sudo_pwd = simpledialog.askstring("Auth Required", "Enter System Administrator Password:", show='*', parent=self.root)
        return self.sudo_pwd

    def run_sudo_cmd(self, cmd_list, cwd=None):
        pwd = self.get_sudo_password()
        if not pwd: return None
        result = subprocess.run(['sudo', '-S'] + cmd_list, input=pwd + "\n", cwd=cwd, capture_output=True, text=True)
        if "incorrect password" in result.stderr.lower() or "sudo: auth" in result.stderr.lower():
            self.sudo_pwd = None 
            messagebox.showerror("Auth Error", "Incorrect Administrator Password!")
            return None
        return result

    def scan_uid(self):
        self.update_usb_status()
        self.db_status_label.config(text="Handshaking with Boot ROM...", fg=FG_COLOR)
        self.root.update()
        try:
            bootloader_path = "/home/pruthvir/Documents/acu_fleet_manager/jetson_image_toolkit/Linux_for_Tegra/bootloader/"
            result = self.run_sudo_cmd(['./tegrarcm_v2', '--new_session', '--chip', '0x23', '--uid'], cwd=bootloader_path)
            if result is None:
                self.db_status_label.config(text="Target Scan Aborted.", fg=DANGER_RED); return
            match = re.search(r'0x[0-9a-fA-F]+', result.stdout)
            if match:
                self.current_uid = match.group(0)
                self.check_database()
            else:
                messagebox.showerror("Read Error", "Could not read UID. Verify device is in RCM state.")
                self.db_status_label.config(text="UID Extraction Failed.", fg=DANGER_RED)
        except Exception as e: messagebox.showerror("Execution Error", f"Core fault:\n{e}")

    def check_database(self):
        self.db_status_label.config(text="Authenticating with Cloud Database...", fg=BRAND_PURPLE)
        self.root.update()
        self.current_record = self.db.find_jetson(self.current_uid)

        self.info_frame.pack(pady=10, fill="x", padx=30)
        self.lbl_sn.config(text=f">  Module SN: {self.current_uid}")
        for btn in [self.btn_repair, self.btn_upgrade, self.btn_new_flash, self.btn_replace]: btn.grid_forget()

        if self.current_record:
            acu = self.current_record.get('acu_id', 'NIL')
            veh = self.current_record.get('veh_num', 'NIL')
            
            self.lbl_veh.config(text=f">  Vehicle Number: {veh}")
            self.lbl_acu.config(text=f">  ACU Box Number: {acu}")
            self.lbl_plat.config(text=f">  OS Image Version: {self.current_record.get('plat_ver', 'NIL')}")
            self.lbl_config.config(text=f">  Configuration: {self.current_record.get('config', 'NIL')}")
            self.lbl_updated.config(text=f">  Status: {self.current_record.get('last_updated', 'Unknown')}")
            
            display_id = acu if acu != "NIL" else (veh if veh != "NIL" else "Unknown Target")
            self.db_status_label.config(text=f"AUTHENTICATED: {display_id}", fg=SUCCESS_GREEN)
            self.btn_repair.grid(row=0, column=0, pady=5, padx=5)
            self.btn_upgrade.grid(row=0, column=1, pady=5, padx=5)
        else:
            self.lbl_veh.config(text=">  Vehicle Number: Unregistered")
            self.lbl_acu.config(text=">  ACU Box Number: Unregistered")
            self.lbl_plat.config(text=">  OS Image Version: --")
            self.lbl_config.config(text=">  Configuration: --")
            self.lbl_updated.config(text=">  Status: Uninitialized")
            self.db_status_label.config(text="UNREGISTERED MODULE DETECTED", fg=DANGER_RED)
            self.btn_new_flash.grid(row=0, column=0, pady=5, padx=5)
            self.btn_replace.grid(row=0, column=1, pady=5, padx=5)

    def setup_new_flash(self): 
        RegistrationWindow(self.root, self.current_uid, self.process_new_flash, self.get_dropdown_options())
        
    def upgrade_build(self): 
        RegistrationWindow(self.root, self.current_uid, self.process_upgrade, self.get_dropdown_options(), existing_data=self.current_record)

    def process_new_flash(self, form_data):
        if self.db.add_new_acu(form_data):
            target_id = form_data['acu_id'] if form_data['acu_id'] != "NIL" else form_data['veh_num']
            self.trigger_flash_workflow(target_id, form_data['plat_ver_raw'], form_data['config'], "INITIALIZE BUILD")
        else: messagebox.showerror("Cloud Error", "Failed to sync with Google Sheets.")

    # --- BUG FIX: PULLS EXACT OS VERSION FROM DATABASE FOR HARDWARE REPLACEMENTS ---
    def replace_hardware(self):
        old_acu = simpledialog.askstring("Hardware RMA", "Enter the old ACU or Vehicle Number this module is replacing:")
        if old_acu:
            try:
                # 1. Look up the old vehicle/ACU in the database
                old_record = self.db.sheet.find(old_acu)
                if old_record:
                    # 2. Extract exactly what software it was running
                    row_data = self.db.sheet.row_values(old_record.row)
                    row_data += [""] * (10 - len(row_data))
                    plat_ver = row_data[2] # e.g. "acu_platform_v2.5.zip"
                    cfg = row_data[7]      # e.g. "coir_no_replan_T3_nav2"
                    
                    # 3. Swap the hardware UIDs in the cloud database
                    if self.db.replace_hardware(old_acu, self.current_uid):
                        # 4. Clone the exact software environment onto the new Jetson!
                        raw_str = f"{plat_ver} (Local)" if plat_ver in self.local_files else f"{plat_ver} (Drive)"
                        self.trigger_flash_workflow(old_acu, raw_str, cfg, "RMA REPLACEMENT")
                    else:
                        messagebox.showerror("Cloud Error", "Failed to update cloud database.")
                else: 
                    messagebox.showerror("Not Found", f"Could not find target '{old_acu}' in cloud registry.")
            except Exception as e:
                messagebox.showerror("Cloud Error", f"Failed to fetch historical target data: {e}")

    def repair_flash(self):
        acu = self.current_record.get('acu_id', 'Unknown')
        veh = self.current_record.get('veh_num', 'Unknown')
        plat = self.current_record.get('plat_ver', 'Unknown')
        cfg = self.current_record.get('config', 'NIL')
        
        target = acu if acu != "NIL" else veh
        if messagebox.askyesno("Confirm Verification", f"Executing Repair protocol for {target} with image {plat}.\nProceed?"):
            raw_str = f"{plat} (Local)" if plat in self.local_files else f"{plat} (Drive)"
            self.trigger_flash_workflow(target, raw_str, cfg, "SYSTEM REPAIR")

    def process_upgrade(self, form_data):
        if self.db.update_build(self.current_uid, form_data):
            target_id = form_data['acu_id'] if form_data['acu_id'] != "NIL" else form_data['veh_num']
            self.trigger_flash_workflow(target_id, form_data['plat_ver_raw'], form_data['config'], "UPGRADE BUILD")
        else: messagebox.showerror("Cloud Error", "Failed to sync with Google Sheets.")

    def trigger_flash_workflow(self, target_id, raw_version_str, cfg, flash_type):
        self.db_status_label.config(text=f"Allocating Environment for {target_id}...", fg=BRAND_PURPLE)
        self.root.update()
        
        # --- 1. DETERMINE FILE PATH ---
        clean_version = raw_version_str.replace(" (Local)", "").replace(" (Drive)", "")
        zip_path = None

        if " (Drive)" in raw_version_str:
            self.db_status_label.config(text=f"Pulling {clean_version} from Cloud Storage...", fg="#E3A008")
            self.root.update()
            file_id = self.drive_files.get(clean_version)
            if not file_id:
                messagebox.showerror("Error", f"Could not locate unique hash for {clean_version}.")
                self.db_status_label.config(text="Execution Aborted.", fg=DANGER_RED); return
                
            zip_path = self.download_platform(file_id, clean_version)
            if not zip_path:
                self.db_status_label.config(text="Download Fault. Execution Aborted.", fg=DANGER_RED); return
        else:
            zip_path = self.local_files.get(clean_version)
            if not zip_path or not os.path.exists(zip_path):
                 messagebox.showerror("Error", f"Local volume missing for {clean_version}.")
                 self.db_status_label.config(text="Execution Aborted.", fg=DANGER_RED); return

        # --- 2. ACTUAL FLASHING BASH SCRIPT ---
        self.db_status_label.config(text=f"Flashing Image {clean_version} to Target...", fg=BRAND_PURPLE)
        self.root.update()

        flash_dlg = FlashProgressDialog(self.root, clean_version)

        flash_process = subprocess.Popen(
            ['sudo', FLASH_SCRIPT_PATH, zip_path], 
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        
        log_queue = queue.Queue()
        flash_success = [False]
        flash_done_var = tk.BooleanVar(value=False)

        def read_terminal_output():
            try:
                for line in iter(flash_process.stdout.readline, ''):
                    line_str = line.strip()
                    if line_str:
                        print(line_str)
                        log_queue.put(line_str)
                    
                    if "[FINISH] Restore completed" in line_str or "power-cycle" in line_str:
                        flash_success[0] = True
                        break
            except Exception: pass
            finally:
                try: flash_process.terminate() 
                except: pass
                self.root.after(0, lambda: flash_done_var.set(True))

        reader_thread = threading.Thread(target=read_terminal_output, daemon=True)
        reader_thread.start()

        def process_flash_logs():
            while not log_queue.empty():
                try:
                    line_str = log_queue.get_nowait()
                    if "[EXTRACT]" in line_str: flash_dlg.update_status("Extracting Target Archive...", line_str, inc_amt=2.0)
                    elif "[SYMLINK]" in line_str: flash_dlg.update_status("Linking Storage Volumes...", line_str, force_pct=5)
                    elif "checkpoint" in line_str.lower():
                        flash_dlg.update_status("Deploying OS Core to NVMe...", line_str, inc_amt=0.5)
                    elif "Restoring" in line_str and "image" in line_str:
                        part = re.search(r'image (nvme[^\s]+)', line_str).group(1) if re.search(r'image (nvme[^\s]+)', line_str) else "partition"
                        flash_dlg.update_status(f"Writing {part} to NVMe...", line_str, inc_amt=3.0)
                    elif "copied" in line_str: flash_dlg.update_status(None, line_str)
                    elif "Successful restore" in line_str: flash_dlg.update_status("Finalizing Bootloader...", "Validation check...", force_pct=99)
                    else: flash_dlg.update_status(None, line_str)
                except queue.Empty: break
            if not flash_done_var.get(): self.root.after(50, process_flash_logs)

        process_flash_logs()
        self.root.wait_variable(flash_done_var)

        flash_process.wait()
        flash_dlg.destroy()

        if flash_success[0]:
            messagebox.showinfo("Hardware Action Required", "OS Image deployed successfully.\n\nACTION: Remove Jetson from Recovery Mode (unplug jumper) and reset power to begin normal boot.")
        else:
             messagebox.showerror("Flash Failure", "Flashing engine threw a fatal error. Review terminal outputs.")
             self.db_status_label.config(text="Execution Aborted.", fg=DANGER_RED)
             return
        
        # --- 3. WAIT FOR BOOT (PING VERIFICATION) ---
        self.db_status_label.config(text="Awaiting Target OS Initialization...", fg="#E3A008")
        self.root.update()
        
        jetson_ip = "192.168.55.1"
        if os.path.exists(".env"):
            with open(".env", "r") as f:
                for line in f:
                    if line.startswith("JETSON_IP="):
                        jetson_ip = line.split("=")[1].strip().strip('"').strip("'")
                        break
        
        while True:
            wait_dlg = DeviceWaitDialog(self.root, jetson_ip)
            self.root.wait_window(wait_dlg)
            if wait_dlg.result: break
            else:
                ans = messagebox.askretrycancel("Timeout Fault", f"Target unresponsive at {jetson_ip}!\nEnsure power is restored and device is booting normally.\nSelect 'Retry' to poll again.")
                if not ans: self.db_status_label.config(text="Execution Aborted. No Target.", fg=DANGER_RED); return
                
        # --- 4. INSTALL DEBIAN CONFIGURATION ---
        self.db_status_label.config(text="Injecting Debian Parameters...", fg=BRAND_PURPLE)
        self.root.update()
        
        cfg_proc = subprocess.run(['./configuration_manager.sh', str(cfg)], capture_output=True, text=True)
        if "CONFIG_SUCCESS" not in cfg_proc.stdout:
            messagebox.showwarning("Configuration Alert", f"Parameter injection threw a warning or was skipped.\nLogs:\n{cfg_proc.stdout[-200:]}")

        # --- 5. RUN BVT RETEST LOOP ---
        while True:
            self.db_status_label.config(text="Executing Build Verification Suite...", fg=BRAND_PURPLE)
            self.root.update()
            
            prog_dlg = BVTProgressDialog(self.root)
            process = subprocess.Popen(['./run_bvt.sh'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            
            bvt_filename = "Failed_To_Generate"
            bvt_stats = ""
            
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if line.startswith("GUI_PROGRESS:"):
                    parts = line.split(":")
                    if len(parts) == 3: prog_dlg.update_progress(int(parts[1]), int(parts[2]))
                elif line.startswith("PYTHON_BVT_STATS:"): bvt_stats = line.split(":", 1)[1]
                elif line.startswith("PYTHON_BVT_RETURN:"): bvt_filename = line.split(":", 1)[1]
                self.root.update()

            process.stdout.close()
            process.wait()
            prog_dlg.destroy()

            if bvt_filename == "Failed_To_Generate":
                messagebox.showerror("BVT Fault", "Verification suite aborted fatally. Check SSH/Auth integrity.")
                return

            res_dlg = BVTResultDialog(self.root, bvt_stats)
            self.root.wait_window(res_dlg)
            
            if res_dlg.result == "RETEST": continue 
            elif res_dlg.result == "COMPLETE": break 
            else: self.db_status_label.config(text="Execution halted by operator.", fg=DANGER_RED); return 

        # --- 6. UPLOAD FILE TO GOOGLE DRIVE ---
        self.db_status_label.config(text="Syncing Telemetry to Cloud...", fg=BRAND_PURPLE)
        self.root.update()
        
        if self.db.upload_bvt_report(bvt_filename, GOOGLE_DRIVE_FOLDER_ID):
            os.remove(bvt_filename)
            if self.db.update_bvt_filename(self.current_uid, bvt_filename):
                messagebox.showinfo("Operation Complete", f"SYSTEM READY!\n\nTarget: {target_id}\nTelemetry Log: {bvt_filename}\nCloud Sync: Verified")
                self.check_database() 
                self.db_status_label.config(text="Operation Complete. Target registered.", fg=SUCCESS_GREEN)
            else:
                messagebox.showwarning("Cloud Sync Error", f"Operation succeeded, but failed to log '{bvt_filename}' to registry.")
        else:
            messagebox.showwarning("Cloud Sync Error", f"Failed to push {bvt_filename} to Drive.\nLog preserved locally.")

if __name__ == "__main__":
    root = tk.Tk()
    app = ACUFleetManagerApp(root)
    root.mainloop()