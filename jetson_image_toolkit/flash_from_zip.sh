#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}"
LOG_TAG="FLASH"
source "${REPO_ROOT}/jetson_bsp_common.sh"

DEFAULT_BOARD="jetson-orin-nano-devkit-super-nvme"
DEFAULT_DEVICE="nvme0n1"
BOARD=""
BACKUP_DEVICE=""
IMAGES_DIR=""

usage() {
    cat <<HELP
Usage: $(basename "$0") [options] <backup-zip-or-version> [restore-options]
HELP
}

BOARD_CLI=""
DEVICE_CLI=""
ZIP_PATH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --board) BOARD_CLI="$2"; shift 2 ;;
        --board=*) BOARD_CLI="${1#*=}"; shift ;;
        --device) DEVICE_CLI="$2"; shift 2 ;;
        --device=*) DEVICE_CLI="${1#*=}"; shift ;;
        --) shift; break ;;
        -* ) log "Unknown option: $1"; usage; exit 1 ;;
        * ) ZIP_PATH="$1"; shift; break ;;
    esac
done

if [[ -z "${ZIP_PATH}" ]]; then usage; exit 1; fi

RESTORE_ARGS=("$@")
BOARD="${BOARD_CLI:-${DEFAULT_BOARD}}"
BACKUP_DEVICE="${DEVICE_CLI:-${DEFAULT_DEVICE}}"

ensure_host_dependencies
require_command unzip
ensure_l4t

IMAGES_DIR="${L4T_DIR}/tools/backup_restore/images"

if [[ ! -x "${L4T_BACKUP_SCRIPT}" ]]; then
    log "Backup script ${L4T_BACKUP_SCRIPT} is missing or not executable."
    exit 1
fi

# --- BULLETPROOF CACHING LOGIC ---
ZIP_NAME=$(basename "${ZIP_PATH}")
BASENAME="${ZIP_NAME%.zip}"

CACHE_BASE="${L4T_DIR}/tools/backup_restore/extracted_caches"
CACHE_DIR="${CACHE_BASE}/${BASENAME}"

# 1. Clean up ANY old garbage before we even check the cache
log "[CLEANUP] Aggressively sweeping for old hoarded folders..."
sudo rm -rf "${IMAGES_DIR}" 2>/dev/null || true
sudo rm -rf "${L4T_DIR}/tools/backup_restore/images_"* 2>/dev/null || true

# 2. Extract or use cache
if [[ -d "${CACHE_DIR}/images" ]] && [[ -n "$(ls -A "${CACHE_DIR}/images" 2>/dev/null)" ]]; then
    log "[CACHE] Found cached extraction for '${BASENAME}'. Skipping unzip! No storage will be used."
else
    if [[ ! -f "${ZIP_PATH}" ]]; then
        log "[ERROR] Cache not found AND zip archive '${ZIP_PATH}' not found."
        exit 1
    fi
    
    log "[EXTRACT] Extracting ${ZIP_PATH} to network-safe cache..."
    sudo mkdir -p "${CACHE_DIR}"
    temp_dir="$(mktemp -d "${REPO_ROOT}/backups/tmp.flash.XXXX")"
    
    unzip -q "${ZIP_PATH}" -d "${temp_dir}"
    
    if [[ ! -d "${temp_dir}/images" ]]; then
        log "[ERROR] Archive ${ZIP_PATH} does not contain an images/ directory."
        sudo rm -rf "${temp_dir}"
        exit 1
    fi
    
    sudo mv "${temp_dir}/images" "${CACHE_DIR}/images"
    sudo rm -rf "${temp_dir}"
    log "[EXTRACT] Extraction complete."
fi

# 3. CREATE THE SYMLINK
log "[SYMLINK] Linking ${BASENAME} into Linux_for_Tegra for flashing..."
cd "${L4T_DIR}/tools/backup_restore"
sudo ln -snf "extracted_caches/${BASENAME}/images" "images"

# 4. PRINT PROOF
log "[VERIFY] SYMLINK CREATED: If you see an arrow (->) below, zero space is being wasted!"
ls -la images
cd "${REPO_ROOT}"
# --- END CACHING LOGIC ---

log "[RESTORE] Restoring board ${BOARD} using images for ${BASENAME}"

SUDO_BIN="$(needsudo)"
if [[ ${#RESTORE_ARGS[@]} -gt 0 ]]; then
    log "Invoking ./tools/backup_restore/l4t_backup_restore.sh -r -e ${BACKUP_DEVICE} ${BOARD} ${RESTORE_ARGS[*]}"
else
    log "Invoking ./tools/backup_restore/l4t_backup_restore.sh -r -e ${BACKUP_DEVICE} ${BOARD}"
fi

if [[ -n "${SUDO_BIN}" ]]; then
    (
        cd "${L4T_DIR}"
        "${SUDO_BIN}" env LC_ALL=C LANG=C ./tools/backup_restore/l4t_backup_restore.sh -r -e "${BACKUP_DEVICE}" "${RESTORE_ARGS[@]}" "${BOARD}"
    )
else
    (
        cd "${L4T_DIR}"
        LC_ALL=C LANG=C ./tools/backup_restore/l4t_backup_restore.sh -r -e "${BACKUP_DEVICE}" "${RESTORE_ARGS[@]}" "${BOARD}"
    )
fi

log "[FINISH] Restore completed. You can reboot or power-cycle the target."
