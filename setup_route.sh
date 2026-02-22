#!/bin/bash
# 配置路由转发 - 让电脑通过 Jetson 访问 Gen5
# 运行位置: Jetson
# 用法: sudo ./setup_route.sh

set -e

echo "=========================================="
echo "配置路由转发 (Jetson -> Gen5)"
echo "=========================================="

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

# 1. 启用 IP 转发
echo ""
echo "[1/2] 启用 IP 转发..."
sysctl -w net.ipv4.ip_forward=1
echo "     IP 转发已启用"

# 2. 配置 FORWARD 规则
echo ""
echo "[2/3] 配置 FORWARD 规则..."
if ! iptables -C FORWARD -i l4tbr0 -o eth0 -j ACCEPT 2>/dev/null; then
    iptables -I FORWARD 1 -i l4tbr0 -o eth0 -j ACCEPT
    echo "     FORWARD 规则 (出) 已添加"
else
    echo "     FORWARD 规则 (出) 已存在"
fi

if ! iptables -C FORWARD -i eth0 -o l4tbr0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -I FORWARD 2 -i eth0 -o l4tbr0 -m state --state RELATED,ESTABLISHED -j ACCEPT
    echo "     FORWARD 规则 (入) 已添加"
else
    echo "     FORWARD 规则 (入) 已存在"
fi

# 3. 配置 NAT (MASQUERADE)
echo ""
echo "[3/3] 配置 NAT..."
if ! iptables -t nat -C POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null; then
    iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
    echo "     NAT 规则已添加"
else
    echo "     NAT 规则已存在"
fi

echo ""
echo "=========================================="
echo "Jetson 端配置完成!"
echo "=========================================="
echo ""
echo "接下来在电脑上运行以下命令:"
echo ""
echo "  Linux/Mac:"
echo "    sudo ip route add 192.168.1.0/24 via 192.168.55.1"
echo ""
echo "  Windows (管理员):"
echo "    route add 192.168.1.0 mask 255.255.255.0 192.168.55.1"
echo ""
echo "测试连接:"
echo "    ping 192.168.1.1"
echo ""
echo "取消配置请运行: sudo ./unset_route.sh"
echo "=========================================="
