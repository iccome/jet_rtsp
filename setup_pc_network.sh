#!/bin/bash
# PC 网络配置脚本

#############################################
# 配置变量 - 根据需要修改
#############################################
INTERFACE="enx000ec683b516"
IP_ADDRESS="192.168.1.100"
NETMASK="24"
# Jetson 的 IP（用于测试连通性）
JETSON_IP="192.168.1.1"

#############################################
# 脚本逻辑 - 一般不需要修改
#############################################

echo "=== PC 网络配置 ==="
echo "接口: $INTERFACE"
echo "IP: $IP_ADDRESS/$NETMASK"

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

# 检查网卡是否存在
if [ ! -d "/sys/class/net/$INTERFACE" ]; then
    echo "错误: 网卡 $INTERFACE 不存在"
    echo "可用的网卡:"
    ls /sys/class/net/
    exit 1
fi

# 启用网卡
echo "[1/4] 启用网卡 $INTERFACE..."
ip link set $INTERFACE up

# 清除旧的 IP 配置
echo "[2/4] 清除旧的 IP 配置..."
ip addr flush dev $INTERFACE

# 添加新的 IP
echo "[3/4] 配置 IP 地址..."
ip addr add $IP_ADDRESS/$NETMASK dev $INTERFACE

# 验证配置
echo "[4/4] 验证配置..."
echo ""
echo "--- IP 配置 ---"
ip addr show $INTERFACE
echo ""
echo "--- 路由表 ---"
ip route show | grep $INTERFACE
echo ""

# 检查链路状态
CARRIER=$(cat /sys/class/net/$INTERFACE/carrier 2>/dev/null)
if [ "$CARRIER" == "1" ]; then
    echo "--- 链路状态: 已连接 ---"
    echo ""
    echo "=== 测试与 Jetson ($JETSON_IP) 的连通性 ==="
    ping -c 3 $JETSON_IP
else
    echo "--- 链路状态: 未连接 (请检查网线) ---"
fi

echo ""
echo "=== 配置完成 ==="
