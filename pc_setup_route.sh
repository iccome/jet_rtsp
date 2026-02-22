#!/bin/bash
# PC 端配置路由 - 通过 Jetson 访问 Gen5
# 运行位置: Linux PC
# 用法: sudo ./pc_setup_route.sh

set -e

JETSON_IP="192.168.55.1"
TARGET_NET="192.168.1.0/24"

echo "=========================================="
echo "PC 端配置路由"
echo "=========================================="

if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

echo ""
echo "添加路由: $TARGET_NET via $JETSON_IP"
ip route add $TARGET_NET via $JETSON_IP 2>/dev/null || echo "路由已存在"

echo ""
echo "当前路由表:"
ip route | grep "$TARGET_NET" || echo "未找到路由"

echo ""
echo "=========================================="
echo "配置完成! 测试连接:"
echo "  ping 192.168.1.1"
echo ""
echo "取消配置: sudo ./pc_unset_route.sh"
echo "=========================================="
