# ACU Fleet Manager & Jetson Image Toolkit

An integrated suite for managing and deploying software to Jetson-based autonomous vehicle units. The core component — the **Jetson Image Toolkit** — provides a high-performance, automated pipeline for flashing and restoring Jetson Orin Nano modules using an optimized caching and symlink strategy.

---

## 🏗️ Core Logic: Smart Flashing

The toolkit avoids redundant data movement through a three-stage strategy:

**1. Cache Extraction**
Backup ZIPs are extracted once into a persistent `extracted_caches/` directory. Subsequent flashes of the same version skip extraction entirely.

**2. Zero-Copy Linking**
Instead of copying tens of gigabytes of image data, the script creates a symbolic link (`ln -s`) pointing to the L4T tools folder. Version switching is instant — no data duplication.

**3. Aggressive Cleanup**
Temporary folders and "ghost" directories are automatically wiped after each flash to prevent host SSD saturation.

**4. Verification**
A built-in "Proof of Link" check validates that images are correctly mapped before the flash sequence begins.

---

## 📂 Project Structure

```
acu_fleet_manager/
├── jetson_image_toolkit/
│   ├── faster_flash.sh           # Main entry point for flashing
│   ├── jetson_bsp_common.sh      # Shared functions: sudo handling, env checks
│   ├── backup_and_zip.sh         # Creates versioned backup archives
│   ├── backups/                  # Versioned image archives (e.g. acu_platform_v2.5_final.zip)
│   │   └── extracted_caches/     # Auto-extracted image caches (generated at runtime)
│   └── images/                   # Raw partition images for direct flashing
├── configurations/               # Fleet-specific unit settings
├── hardware.py                   # Hardware verification utilities
└── sheets_db.py                  # Google Sheets logging integration
```

---

## 🚀 Usage

### 1. Host Machine Setup

Install required dependencies on the Ubuntu host:

```bash
sudo apt update && sudo apt install -y unzip python3-pip
```

### 2. Flash a Unit

Connect the Jetson in **RCM**, then run:

```bash
cd ~/Documents/acu_fleet_manager/jetson_image_toolkit
./faster_flash.sh ./backups/<name.zip>
```

The script will:
- Extract the ZIP to `extracted_caches/` (first run only)
- Symlink the L4T tools directory
- Verify the link integrity
- Begin the flash sequence

### 3. Create a Backup

To snapshot the current Jetson state into a versioned archive:

```bash
cd ~/Documents/acu_fleet_manager/jetson_image_toolkit
./backup_and_zip.sh acu_platform_v2.5_final
```

