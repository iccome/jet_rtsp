#!/bin/bash
# 取消路由转发配置
# 运行位置: Jetson
# 用法: sudo ./unset_route.sh

set -e

echo "=========================================="
echo "取消路由转发配置"
echo "=========================================="

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

# 1. 删除 NAT 规则
echo ""
echo "[1/3] 删除 NAT 规则..."
if iptables -t nat -C POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null; then
    iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
    echo "     NAT 规则已删除"
else
    echo "     NAT 规则不存在，跳过"
fi

# 2. 删除 FORWARD 规则
echo ""
echo "[2/3] 删除 FORWARD 规则..."
if iptables -C FORWARD -i l4tbr0 -o eth0 -j ACCEPT 2>/dev/null; then
    iptables -D FORWARD -i l4tbr0 -o eth0 -j ACCEPT
    echo "     FORWARD 规则 (出) 已删除"
else
    echo "     FORWARD 规则 (出) 不存在，跳过"
fi

if iptables -C FORWARD -i eth0 -o l4tbr0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -D FORWARD -i eth0 -o l4tbr0 -m state --state RELATED,ESTABLISHED -j ACCEPT
    echo "     FORWARD 规则 (入) 已删除"
else
    echo "     FORWARD 规则 (入) 不存在，跳过"
fi

# 3. 禁用 IP 转发
echo ""
echo "[3/3] 禁用 IP 转发..."
sysctl -w net.ipv4.ip_forward=0
echo "     IP 转发已禁用"

echo ""
echo "=========================================="
echo "Jetson 端配置已取消!"
echo "=========================================="
echo ""
echo "如需取消电脑上的路由，运行:"
echo ""
echo "  Linux/Mac:"
echo "    sudo ip route del 192.168.1.0/24 via 192.168.55.1"
echo ""
echo "  Windows (管理员):"
echo "    route delete 192.168.1.0"
echo ""
echo "=========================================="
