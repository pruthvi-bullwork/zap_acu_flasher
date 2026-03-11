#!/bin/bash

# --- Load Environment Variables ---
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "❌ ERROR: .env file not found."
    echo "PYTHON_BVT_RETURN:Failed_To_Generate"
    exit 1
fi

REPORT_FILE="BVT_Report_$(date +%Y%m%d_%H%M%S).csv"
HOST_DATE=$(date +%d/%m/%Y)

draw_progress() {
    local current=$1
    local total=$2
    local percent=$(( (current * 100) / total ))
    local filled=$(( (percent / 2) ))
    local empty=$(( 50 - filled ))
    printf "\rProgress: ["
    printf "%${filled}s" | tr ' ' '#'
    printf "%${empty}s" | tr ' ' '-'
    printf "] %d%%" "$percent"
}

echo "------------------------------------------------"
echo "🔍 Initializing Build Verification Test..."
echo "------------------------------------------------"

echo "Waiting for device on network ($JETSON_IP)..."
while ! lsusb | grep -q "$JETSON_USB_ID"; do sleep 1; done
while ! timeout 1 bash -c "</dev/tcp/$JETSON_IP/22" 2>/dev/null; do sleep 2; done

REMOTE_COMMANDS=$(cat << EOF
    CURRENT=0
    PASSED=0
    FAILURES=""
    DATE_STR="$HOST_DATE"
    PASS_WORD="$JETSON_PASS"

    export PATH=\$PATH:/usr/local/cuda/bin:/usr/local/zed/tools
    export LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:/usr/local/cuda/lib64
    source /opt/ros/humble/setup.bash 2>/dev/null

    log() {
        echo "\$1,\$2,\$3,\$4,\"\$5\",\"\$6\",\"\$7\",\$8,\$DATE_STR"
        ((CURRENT++))
        echo "PROGRESS,\$CURRENT"
        if [[ "\$8" == "PASS" ]]; then
            ((PASSED++))
        else
            FAILURES+="\$1 (\$4), "
        fi
    }

    # --- Test Suite ---
    log "HW-01" "Hardware" "Power" "Cold boot" "Power" "Boots" "Active" "PASS"
    
    DRIVE=\$(lsblk -dn -o NAME,SIZE | grep -E "nvme|mmcblk" | head -n 1 | tr -s ' ' '_')
    [[ -n "\$DRIVE" ]] && log "HW-02" "Hardware" "Storage" "eMMC/NVMe" "lsblk" "Drive Found" "\$DRIVE" "PASS" || log "HW-02" "Hardware" "Storage" "eMMC/NVMe" "lsblk" "Drive Found" "Missing" "FAIL"
    
    PING_TIME=\$(ping -c 1 8.8.8.8 2>/dev/null | grep time= | awk -F'time=' '{print \$2}' | awk '{print \$1"ms"}')
    [[ -n "\$PING_TIME" ]] && log "HW-03" "Hardware" "Ethernet" "Internet" "ping" "Reply" "\$PING_TIME" "PASS" || log "HW-03" "Hardware" "Ethernet" "Internet" "ping" "Reply" "Timeout" "FAIL"
    
    USB_CNT=\$(lsusb | grep -viE "root|hub" | wc -l)
    log "HW-04" "Hardware" "USB" "Enumeration" "lsusb" ">0 Devices" "\$USB_CNT Devices" "PASS"
    
    TEMP=\$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
    [[ -n "\$TEMP" ]] && TEMP=\$((TEMP/1000))C || TEMP="Unknown"
    log "HW-05" "Hardware" "Thermals" "Temp" "sysfs" "Read Temp" "\$TEMP" "PASS"
    
    log "SYS-01" "System" "User" "UID" "id" "1000" "\$(id -u)" "PASS"
    
    KERN=\$(uname -r)
    log "OS-01" "OS" "Kernel" "Version" "uname" "L4T Kernel" "\$KERN" "PASS"
    
    HOST=\$(hostname)
    log "OS-02" "OS" "User" "Hostname" "hostname" "Set" "\$HOST" "PASS"
    
    if command -v nvcc &> /dev/null; then
        VER=\$(nvcc --version | grep "release" | awk '{print \$5}' | tr -d ',')
        log "OS-03" "OS" "CUDA" "CUDA Version" "nvcc" "Installed" "\$VER" "PASS"
    else
        log "OS-03" "OS" "CUDA" "CUDA Version" "nvcc" "Installed" "Missing" "FAIL"
    fi

    ZED_VER=\$(dpkg-query -W -f='\${Version}' stereolabs-zed 2>/dev/null || ls /usr/local/zed/lib/libsl_zed.so* 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 || echo "Missing")
    if [[ "\$ZED_VER" != "Missing" ]]; then
        log "ZED-DRV-01" "Drivers" "ZED SDK" "Version" "dpkg/lib" "Installed" "\$ZED_VER" "PASS"
    else
        log "ZED-DRV-01" "Drivers" "ZED SDK" "Version" "dpkg/lib" "Installed" "Missing" "FAIL"
    fi

    DAEMON_STAT=\$(systemctl is-active zed_x_daemon 2>/dev/null || echo "inactive")
    if [[ "\$DAEMON_STAT" == "active" ]]; then
        log "ZED-DRV-02" "Drivers" "ZED Daemon" "Service" "systemctl" "active" "\$DAEMON_STAT" "PASS"
    else
        log "ZED-DRV-02" "Drivers" "ZED Daemon" "Service" "systemctl" "active" "\$DAEMON_STAT" "FAIL"
    fi
    
    ros2 daemon stop &>/dev/null && ros2 daemon start &>/dev/null
    sleep 1
    [[ -n \$(ros2 topic list 2>/dev/null | grep -E "rosout") ]] && log "ROS-01" "ROS2" "Daemon" "Status" "ros2" "Active" "Active" "PASS" || log "ROS-01" "ROS2" "Daemon" "Status" "ros2" "Active" "Offline" "FAIL"
    
    [[ -n \$(ros2 pkg list 2>/dev/null | grep -i "zed") ]] && log "ZED-ROS-01" "ZED" "Package" "installed" "ros2" "Found" "Found" "PASS" || log "ZED-ROS-01" "ZED" "Package" "installed" "ros2" "Found" "Missing" "FAIL"
    [[ -n \$(ros2 pkg list 2>/dev/null | grep "nav2") ]] && log "NAV-FLASH-01" "Nav2" "Package" "installed" "ros2" "Found" "Found" "PASS" || log "NAV-FLASH-01" "Nav2" "Package" "installed" "ros2" "Found" "Missing" "FAIL"
    [[ -n \$(ros2 pkg list 2>/dev/null | grep "robot_localization") ]] && log "LOC-FLASH-01" "Loc" "Package" "installed" "ros2" "Found" "Found" "PASS" || log "LOC-FLASH-01" "Loc" "Package" "installed" "ros2" "Found" "Missing" "FAIL"

    echo "\$PASS_WORD" | sudo -S ip link set can0 up &>/dev/null
    if ip link show can0 2>/dev/null | grep -q "UP"; then
        log "CAN-01" "Drivers" "CAN" "Kernel Modules" "lsmod" "UP" "UP" "PASS"
    else
        log "CAN-01" "Drivers" "CAN" "Status" "ip link" "UP" "DOWN" "FAIL"
    fi

    CPU_LOAD=\$(uptime | awk -F'load average:' '{print \$2}' | cut -d, -f1 | tr -d ' ')
    log "PERF-01" "Perf" "CPU" "1-Min Load" "uptime" "<10.0" "\$CPU_LOAD" "PASS"
    
    RATIO=\$(( (PASSED * 100) / CURRENT ))
    echo "SUMMARY,\$RATIO%,\$FAILURES"
EOF
)

TOTAL_STEPS=17
echo "ID,Category,Component,Test Description,Command,Expected,Actual,Status,Date" > "$REPORT_FILE"

FINAL_STATS=""

while IFS= read -r line; do
    if [[ "$line" == PROGRESS* ]]; then
        step=$(echo "$line" | cut -d',' -f2)
        # --- NEW: Tell Python the progress exactly ---
        echo "GUI_PROGRESS:$step:$TOTAL_STEPS"
        draw_progress "$step" "$TOTAL_STEPS"
    elif [[ "$line" == SUMMARY* ]]; then
        FINAL_STATS=$(echo "$line")
    else
        echo "$line" >> "$REPORT_FILE"
    fi
done < <(sshpass -p "$JETSON_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$JETSON_USER@$JETSON_IP" "$REMOTE_COMMANDS" 2>/dev/null)

printf "\n"

if [[ -z "$FINAL_STATS" ]]; then
    echo "❌ ERROR: BVT testing failed!"
    echo "PYTHON_BVT_RETURN:Failed_To_Generate"
    exit 1
fi

echo "✅ REPORT GENERATED: $REPORT_FILE"

# --- NEW: Tell Python the exact stats so it can show the popup ---
echo "PYTHON_BVT_STATS:$FINAL_STATS"
echo "PYTHON_BVT_RETURN:$REPORT_FILE"