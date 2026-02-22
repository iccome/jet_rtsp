#!/bin/bash
# Jetson Nano 性能优化脚本
# 运行: sudo ./setup_performance.sh

set -e

echo "=========================================="
echo "Jetson Nano 性能优化"
echo "=========================================="

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

# 1. 设置最大性能模式
echo ""
echo "[1/4] 设置电源模式为 MAXN..."
nvpmodel -m 0
echo "     电源模式: $(nvpmodel -q 2>&1 | grep 'NV Power Mode' || echo 'MAXN')"

# 2. 锁定最大频率
echo ""
echo "[2/4] 锁定 CPU/GPU/EMC 频率..."
jetson_clocks
echo "     频率已锁定"

# 3. 风扇全速
echo ""
echo "[3/4] 设置风扇全速..."
if [ -f /sys/devices/pwm-fan/target_pwm ]; then
    echo 255 > /sys/devices/pwm-fan/target_pwm
    echo "     风扇转速: 100%"
else
    echo "     未检测到 PWM 风扇"
fi

# 4. 增大 UDP 缓冲区
echo ""
echo "[4/4] 优化网络缓冲区..."
sysctl -w net.core.rmem_max=26214400
sysctl -w net.core.rmem_default=26214400
sysctl -w net.core.wmem_max=26214400
sysctl -w net.core.wmem_default=26214400
echo "     UDP 缓冲区已增大到 25MB"

# 显示当前状态
echo ""
echo "=========================================="
echo "优化完成! 当前状态:"
echo "=========================================="
echo ""
echo "电源模式:"
nvpmodel -q 2>&1 | head -3

echo ""
echo "温度:"
cat /sys/devices/virtual/thermal/thermal_zone*/temp 2>/dev/null | while read temp; do
    echo "  $((temp/1000))°C"
done

echo ""
echo "网络缓冲区:"
echo "  rmem_max: $(sysctl net.core.rmem_max | awk '{print $3/1024/1024}') MB"
echo "  wmem_max: $(sysctl net.core.wmem_max | awk '{print $3/1024/1024}') MB"

echo ""
echo "=========================================="
echo "可以启动 RTSP 服务器了:"
echo "  python3 multi_res_server.py --config multi_res_config.json"
echo "=========================================="
