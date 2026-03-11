import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
import os
import io

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

class SheetsDB:
    def __init__(self, json_key="service_account.json"):
        self.connected = False
        self.drive_service = None
        try:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets", 
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_file(json_key, scopes=scopes)
            self.client = gspread.authorize(creds)
            
            # Connect to Main Document
            self.doc = self.client.open("ACU_Fleet_Database")
            self.sheet = self.doc.sheet1
            
            # Automatically Connect to or Create the History Ledger Tab
            try:
                self.history_sheet = self.doc.worksheet("History_Log")
            except Exception:
                # If it doesn't exist, create it and setup headers!
                self.history_sheet = self.doc.add_worksheet(title="History_Log", rows="1000", cols="8")
                headers = ["Vehicle Number", "ACU Box Number", "Jetson UID", "Platform Version", "Config", "In Time", "Out Time", "Notes"]
                self.history_sheet.append_row(headers)

            self.drive_service = build('drive', 'v3', credentials=creds)
            self.connected = True
        except Exception as e:
            print(f"Google APIs Connection Error: {e}")

    # ==========================================
    # HISTORY LEDGER HELPER METHODS
    # ==========================================
    def _close_history_record(self, uid, out_time, reason):
        """Finds the 'ACTIVE' record for a specific UID and closes it with an Out Time."""
        if not self.connected: return
        try:
            cells = self.history_sheet.findall(uid)
            # Search from the bottom up to find the most recent entry
            for cell in reversed(cells):
                row_vals = self.history_sheet.row_values(cell.row)
                row_vals += [""] * (8 - len(row_vals)) # Pad to avoid index errors
                
                if row_vals[6] == "ACTIVE": # Column G is 'Out Time'
                    self.history_sheet.update_cell(cell.row, 7, out_time)
                    self.history_sheet.update_cell(cell.row, 8, reason)
                    break
        except Exception as e:
            print(f"History Close Error: {e}")

    def _append_history_record(self, veh, acu, uid, plat, config, in_time, notes):
        """Appends a fresh active record to the ledger."""
        if not self.connected: return
        try:
            self.history_sheet.append_row([veh, acu, uid, plat, config, in_time, "ACTIVE", notes])
        except Exception as e:
            print(f"History Append Error: {e}")

    # ==========================================
    # CORE DATABASE METHODS
    # ==========================================
    def find_jetson(self, uid):
        if not self.connected: return None
        try:
            cell = self.sheet.find(uid)
            if cell is None: return None
                
            row = self.sheet.row_values(cell.row)
            row += [""] * (10 - len(row)) 
            
            return {
                "row": cell.row, 
                "uid": row[1], 
                "plat_ver": row[2],
                "veh_num": row[3],
                "acu_id": row[4],
                "router": row[5],
                "m2m_sim": row[6],
                "config": row[7],
                "last_updated": row[8]
            }
        except Exception as e:
            print(f"Search Error: {e}")
            return None

    def add_new_acu(self, data):
        if not self.connected: return False
        try:
            all_records = self.sheet.get_all_values()
            next_sl_no = str(len(all_records)) 
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            row_data = [
                next_sl_no,
                data.get('uid', 'NIL'),
                data.get('plat_ver', 'NIL'),
                data.get('veh_num', 'NIL'),
                data.get('acu_id', 'NIL'),
                data.get('router', 'NIL'),
                data.get('m2m_sim', 'NIL'),
                data.get('config', 'NIL'),
                current_time,
                data.get('bvt_test', 'Pending')
            ]
            self.sheet.append_row(row_data)

            # --- ADD TO HISTORY LEDGER ---
            self._append_history_record(
                data.get('veh_num', 'NIL'), data.get('acu_id', 'NIL'), data.get('uid', 'NIL'), 
                data.get('plat_ver', 'NIL'), data.get('config', 'NIL'), current_time, "INITIAL SETUP"
            )
            return True
        except Exception as e:
            return False

    def update_build(self, uid, data):
        if not self.connected: return False
        try:
            cell = self.sheet.find(uid)
            if cell is None: return False
            r = cell.row
            
            # Fetch old data before overwriting
            old_row = self.sheet.row_values(r)
            old_row += [""] * (10 - len(old_row))
            old_veh = old_row[3]
            old_acu = old_row[4]

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self.sheet.update_cell(r, 3, data.get('plat_ver', 'NIL'))
            self.sheet.update_cell(r, 4, data.get('veh_num', 'NIL'))
            self.sheet.update_cell(r, 5, data.get('acu_id', 'NIL'))
            self.sheet.update_cell(r, 6, data.get('router', 'NIL'))
            self.sheet.update_cell(r, 7, data.get('m2m_sim', 'NIL'))
            self.sheet.update_cell(r, 8, data.get('config', 'NIL'))
            self.sheet.update_cell(r, 9, f"Upgraded: {current_time}")
            self.sheet.update_cell(r, 10, "Pending")

            # --- UPDATE HISTORY LEDGER ---
            new_veh = data.get('veh_num', old_veh)
            new_acu = data.get('acu_id', old_acu)
            new_plat = data.get('plat_ver', 'NIL')
            new_cfg = data.get('config', 'NIL')

            # Close the old software state
            self._close_history_record(uid, current_time, "OS/CONFIG UPGRADE")
            # Open the new software state
            self._append_history_record(new_veh, new_acu, uid, new_plat, new_cfg, current_time, "UPGRADED BUILD")

            return True
        except Exception as e:
            return False

    def replace_hardware(self, old_target, new_uid):
        if not self.connected: return False
        try:
            cell = self.sheet.find(old_target)
            if cell is None: return False
            r = cell.row

            # Extract old hardware info
            old_row = self.sheet.row_values(r)
            old_row += [""] * (10 - len(old_row))
            old_uid = old_row[1]
            plat_ver = old_row[2]
            veh_num = old_row[3]
            acu_id = old_row[4]
            config = old_row[7]

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Overwrite main sheet with new hardware UID
            self.sheet.update_cell(r, 2, new_uid)
            self.sheet.update_cell(r, 9, f"Replaced: {current_time}")
            self.sheet.update_cell(r, 10, "Pending")

            # --- UPDATE HISTORY LEDGER ---
            # 1. Close out the damaged/replaced hardware
            self._close_history_record(old_uid, current_time, "HARDWARE DAMAGED / REPLACED")
            # 2. Add the new hardware taking its place
            self._append_history_record(veh_num, acu_id, new_uid, plat_ver, config, current_time, "NEW HARDWARE SWAPPED IN")

            return True
        except Exception as e:
            print(f"Replace Error: {e}")
            return False
            
    def update_bvt_filename(self, uid, filename):
        if not self.connected: return False
        try:
            cell = self.sheet.find(uid)
            if cell is None: return False
            self.sheet.update_cell(cell.row, 10, filename)
            return True
        except Exception as e:
            return False

    def upload_bvt_report(self, file_path, folder_id):
        if not self.connected or not self.drive_service: return False
        try:
            file_metadata = {'name': os.path.basename(file_path), 'parents': [folder_id]}
            media = MediaFileUpload(file_path, mimetype='text/csv')
            file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
            return True
        except Exception as e:
            print(f"Drive Upload Error: {e}")
            return False

    # ==========================================
    # DRIVE UPDATE METHODS
    # ==========================================
    def get_drive_files(self, folder_id):
        if not self.connected or not self.drive_service: return []
        try:
            query = f"'{folder_id}' in parents and trashed=false"
            results = self.drive_service.files().list(
                q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            return results.get('files', [])
        except Exception as e:
            return []

    def download_file(self, file_id, dest_path, progress_callback=None):
        if not self.connected or not self.drive_service: return False
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            fh = io.FileIO(dest_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request, chunksize=1024*1024*10)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status and progress_callback:
                    progress_callback(int(status.progress() * 100))
            return True
        except Exception as e:
            return False