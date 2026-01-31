#!/bin/bash
# Jetson Nano VLAN 配置脚本

#############################################
# 配置变量 - 根据需要修改
#############################################

# 物理网卡
PARENT_INTERFACE="eth0"

# VLAN 配置（可添加多个）
# 格式: "VLAN_ID:IP_ADDRESS:NETMASK"
VLANS=(
    "100:192.168.100.2:24"
    # "200:192.168.200.2:24"
    # "300:192.168.300.2:24"
)

# 是否持久化配置（写入 netplan）
PERSISTENT=false

#############################################
# 脚本逻辑 - 一般不需要修改
#############################################

echo "=== Jetson Nano VLAN 配置 ==="
echo "物理接口: $PARENT_INTERFACE"
echo ""

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
    echo "错误: 请使用 sudo 运行此脚本"
    exit 1
fi

# 检查物理接口是否存在
if [ ! -d "/sys/class/net/$PARENT_INTERFACE" ]; then
    echo "错误: 接口 $PARENT_INTERFACE 不存在"
    echo "可用接口:"
    ls /sys/class/net/
    exit 1
fi

# 加载 8021q 模块
echo "[1/4] 加载 VLAN 内核模块 (8021q)..."
if ! lsmod | grep -q 8021q; then
    modprobe 8021q
    if [ $? -ne 0 ]; then
        echo "错误: 无法加载 8021q 模块"
        exit 1
    fi
    echo "  8021q 模块已加载"
else
    echo "  8021q 模块已存在"
fi

# 确保开机自动加载
if ! grep -q "8021q" /etc/modules 2>/dev/null; then
    echo "8021q" >> /etc/modules
    echo "  已添加到 /etc/modules"
fi

# 确保物理接口已启用
echo "[2/4] 启用物理接口 $PARENT_INTERFACE..."
ip link set $PARENT_INTERFACE up

# 创建 VLAN 接口
echo "[3/4] 创建 VLAN 接口..."
for vlan_config in "${VLANS[@]}"; do
    # 解析配置
    IFS=':' read -r VLAN_ID IP_ADDR NETMASK <<< "$vlan_config"
    VLAN_INTERFACE="${PARENT_INTERFACE}.${VLAN_ID}"

    echo "  配置 VLAN $VLAN_ID:"
    echo "    接口: $VLAN_INTERFACE"
    echo "    IP: $IP_ADDR/$NETMASK"

    # 删除已存在的 VLAN 接口
    if ip link show $VLAN_INTERFACE &>/dev/null; then
        ip link delete $VLAN_INTERFACE
    fi

    # 创建 VLAN 接口
    ip link add link $PARENT_INTERFACE name $VLAN_INTERFACE type vlan id $VLAN_ID
    if [ $? -ne 0 ]; then
        echo "    错误: 无法创建 VLAN 接口"
        continue
    fi

    # 配置 IP
    ip addr add $IP_ADDR/$NETMASK dev $VLAN_INTERFACE

    # 启用接口
    ip link set $VLAN_INTERFACE up

    echo "    完成"
done

# 持久化配置
if [ "$PERSISTENT" = true ]; then
    echo "[4/4] 写入持久化配置..."

    NETPLAN_FILE="/etc/netplan/02-vlans.yaml"

    # 生成 netplan 配置
    cat > $NETPLAN_FILE << EOF
# VLAN 配置 - 由 setup_vlan.sh 生成
network:
  version: 2
  renderer: networkd
  vlans:
EOF

    for vlan_config in "${VLANS[@]}"; do
        IFS=':' read -r VLAN_ID IP_ADDR NETMASK <<< "$vlan_config"
        VLAN_INTERFACE="${PARENT_INTERFACE}.${VLAN_ID}"

        cat >> $NETPLAN_FILE << EOF
    $VLAN_INTERFACE:
      id: $VLAN_ID
      link: $PARENT_INTERFACE
      addresses: [$IP_ADDR/$NETMASK]
EOF
    done

    echo "  已写入 $NETPLAN_FILE"
    echo "  运行 'sudo netplan apply' 应用配置"
else
    echo "[4/4] 跳过持久化配置 (PERSISTENT=false)"
    echo "  注意: 当前配置重启后会丢失"
    echo "  如需持久化，设置 PERSISTENT=true 并重新运行"
fi

# 显示结果
echo ""
echo "=== VLAN 配置结果 ==="
echo ""
echo "--- VLAN 接口 ---"
for vlan_config in "${VLANS[@]}"; do
    IFS=':' read -r VLAN_ID IP_ADDR NETMASK <<< "$vlan_config"
    VLAN_INTERFACE="${PARENT_INTERFACE}.${VLAN_ID}"

    echo ""
    echo "[$VLAN_INTERFACE]"
    ip -d link show $VLAN_INTERFACE 2>/dev/null | grep -E "vlan|inet"
    ip addr show $VLAN_INTERFACE 2>/dev/null | grep "inet "
done

echo ""
echo "--- 路由表 ---"
ip route show | grep -E "$(echo "${VLANS[@]}" | tr ' ' '\n' | cut -d: -f1 | tr '\n' '|' | sed 's/|$//')"

echo ""
echo "=== 配置完成 ==="
echo ""
echo "提示: 确保交换机端口配置为 Trunk 模式，允许对应 VLAN 通过"
