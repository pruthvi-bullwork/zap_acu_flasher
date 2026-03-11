#!/bin/bash

# Config name from GUI (e.g., coir_no_replan_T1_nav2)
CONFIG_NAME=$1

# Exit if no config selected
if [[ "$CONFIG_NAME" == "NIL" ]] || [[ -z "$CONFIG_NAME" ]]; then
    echo "Config set to NIL. Skipping debian injection."
    echo "CONFIG_SUCCESS"
    exit 0
fi

# Load Jetson credentials from .env
if [ -f .env ]; then 
    source .env 
else 
    echo "❌ ERROR: .env file not found."
    exit 1 
fi

# GitHub Repository Info
REPO="pruthvi-bullwork/vamana_pro_nav2_config"
TAG="acu_configuration_v1.0.0"
PKG_NAME="${CONFIG_NAME}.deb"
LOCAL_DIR="./configurations"

mkdir -p "$LOCAL_DIR"

echo "------------------------------------------------"
echo "📦 Configuration Manager: $PKG_NAME"
echo "------------------------------------------------"

# --- 1. LOCAL CACHE DOWNLOAD ---
# We still keep the local cache so your laptop doesn't spam GitHub on every flash
if [ ! -f "$LOCAL_DIR/$PKG_NAME" ]; then
    echo "⬇️  Downloading $PKG_NAME from GitHub..."
    gh release download "$TAG" --repo "$REPO" --pattern "$PKG_NAME" --dir "$LOCAL_DIR"
    
    if [ $? -ne 0 ]; then
        echo "❌ ERROR: Download failed. Run 'gh auth login' on your laptop."
        exit 1
    fi
else
    echo "✅ Using locally cached file: $LOCAL_DIR/$PKG_NAME"
fi

# --- 2. AGGRESSIVE CLEANUP ON JETSON ---
echo "🧹 Purging ALL previous configurations from Jetson..."

# We force dpkg to purge all 4 known packages (ignoring errors if they aren't there)
# Then we forcefully delete EVERYTHING inside the vamana_configs folder to guarantee a clean slate.
CLEANUP_CMD="echo '$JETSON_PASS' | sudo -S bash -c 'dpkg -P coir-no-replan-t1-nav2 coir-no-replan-t3-nav2 construction-t1-nav2 construction-t3-nav2 2>/dev/null; rm -rf /opt/vamana_configs/*'"

sshpass -p "$JETSON_PASS" ssh -o StrictHostKeyChecking=no "$JETSON_USER@$JETSON_IP" "$CLEANUP_CMD"
echo "✅ Cleanup complete."


# --- 3. TRANSFER AND INSTALL ---
echo "📤 Pushing new configuration to Jetson..."
sshpass -p "$JETSON_PASS" scp -o StrictHostKeyChecking=no "$LOCAL_DIR/$PKG_NAME" "$JETSON_USER@$JETSON_IP:/tmp/"

echo "⚙️  Installing new package via dpkg..."
sshpass -p "$JETSON_PASS" ssh -o StrictHostKeyChecking=no "$JETSON_USER@$JETSON_IP" "echo '$JETSON_PASS' | sudo -S dpkg -i --force-all /tmp/$PKG_NAME && rm /tmp/$PKG_NAME"

if [ $? -eq 0 ]; then
    echo "🚀 Configuration deployed successfully!"
    echo "CONFIG_SUCCESS"
else
    echo "❌ ERROR: dpkg installation failed on Jetson."
    exit 1
fi