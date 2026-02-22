#!/bin/bash
# PC 端取消路由配置
# 运行位置: Linux PC
# 用法: sudo ./pc_unset_route.sh

set -e

JETSON_IP="192.168.55.1"
TARGET_NET="192.168.1.0/24"

echo "=========================================="
echo "PC 端取消路由"
echo "=========================================="

if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

echo ""
echo "删除路由: $TARGET_NET via $JETSON_IP"
ip route del $TARGET_NET via $JETSON_IP 2>/dev/null || echo "路由不存在"

echo ""
echo "=========================================="
echo "路由已删除"
echo "=========================================="
