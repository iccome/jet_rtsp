# Jetson Nano RTSP Server

基于 GStreamer RTSP Server 的视频流服务器，支持 H.265 透传模式。

## 目录结构

```
rtsp_server/
├── rtsp_server.py           # RTSP 服务器主程序
├── install_deps.sh          # 依赖安装脚本
├── start_server.sh          # 启动脚本示例
├── setup_jetson_network.sh  # Jetson 网络配置脚本
├── setup_pc_network.sh      # PC 网络配置脚本
├── setup_vlan.sh            # VLAN 配置脚本
└── README.md                # 本文档
```

## 快速开始

### 1. 安装依赖（在 Jetson 上）

```bash
./install_deps.sh
```

### 2. 启动 RTSP 服务器

```bash
python3 rtsp_server.py /path/to/video.mp4
```

### 3. 客户端播放

```bash
# VLC
vlc rtsp://<jetson-ip>:8554/stream

# FFplay
ffplay rtsp://<jetson-ip>:8554/stream

# FFprobe（测试连接）
ffprobe rtsp://<jetson-ip>:8554/stream
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `video` | (必填) | 视频文件路径 |
| `--port, -p` | 8554 | RTSP 端口号 |
| `--mount, -m` | /stream | RTSP 挂载点 |
| `--codec, -c` | h265 | 编码格式 (h264/h265) |
| `--bitrate, -b` | 4000 | 比特率 (kbps) |
| `--no-loop` | False | 不循环播放 |

**示例：**

```bash
# 基本用法
python3 rtsp_server.py video.mp4

# 指定端口
python3 rtsp_server.py video.mp4 --port 8555

# 不循环播放
python3 rtsp_server.py video.mp4 --no-loop
```

## 网络配置

### 网络拓扑

```
┌─────────────────┐         网线          ┌─────────────────┐
│      PC         │◄──────────────────────►│   Jetson Nano   │
│ 192.168.1.100   │                        │  192.168.1.2    │
│ (enx000ec683b516)                        │     (eth0)      │
└─────────────────┘                        └─────────────────┘
```

### 配置步骤

#### 方式一：使用配置脚本（推荐）

**Jetson 端：**
```bash
# 编辑变量（如需修改）
vim setup_jetson_network.sh

# 运行配置
sudo ./setup_jetson_network.sh
```

**PC 端：**
```bash
# 编辑变量（如需修改）
vim setup_pc_network.sh

# 运行配置
sudo ./setup_pc_network.sh
```

#### 方式二：手动配置

**Jetson 端：**
```bash
sudo ip link set eth0 up
sudo ip addr add 192.168.1.2/24 dev eth0
```

**PC 端：**
```bash
sudo ip link set enx000ec683b516 up
sudo ip addr add 192.168.1.100/24 dev enx000ec683b516
```

### 配置变量说明

| 变量 | Jetson 默认值 | PC 默认值 | 说明 |
|------|---------------|-----------|------|
| INTERFACE | eth0 | enx000ec683b516 | 网络接口名称 |
| IP_ADDRESS | 192.168.1.2 | 192.168.1.100 | IP 地址 |
| NETMASK | 24 | 24 | 子网掩码 |

## 问题排查

### 1. 网络连通性检查

#### 检查网卡是否存在

```bash
# 列出所有网卡
ip link show

# 或
ls /sys/class/net/
```

#### 检查网线连接状态

```bash
# 返回 1 = 已连接，0 = 未连接
cat /sys/class/net/eth0/carrier        # Jetson
cat /sys/class/net/enx000ec683b516/carrier  # PC
```

#### 检查 IP 配置

```bash
ip addr show eth0           # Jetson
ip addr show enx000ec683b516    # PC
```

#### 检查路由表

```bash
ip route show
```

#### 检查 ARP 表

```bash
arp -a
```

#### Ping 测试

```bash
# PC ping Jetson
ping 192.168.1.2

# Jetson ping PC
ping 192.168.1.100
```

### 2. RTSP 服务器问题

#### 检查服务器是否启动

```bash
# 查看监听端口
netstat -tlnp | grep 8554

# 或
ss -tlnp | grep 8554
```

#### 测试 GStreamer Pipeline

```bash
# 测试透传模式
gst-launch-1.0 filesrc location=video.mp4 ! qtdemux ! h265parse ! fakesink

# 测试完整 pipeline
gst-launch-1.0 filesrc location=video.mp4 ! qtdemux ! h265parse ! rtph265pay pt=96 config-interval=1 ! fakesink
```

#### 使用 ffprobe 测试 RTSP 流

```bash
ffprobe rtsp://192.168.1.2:8554/stream
```

### 3. 常见错误及解决方案

#### 错误：`Destination Host Unreachable`

**原因：** 网络不通

**排查步骤：**
1. 检查网线是否插好：`cat /sys/class/net/eth0/carrier`
2. 检查 IP 配置是否正确：`ip addr show eth0`
3. 检查两端是否在同一网段

#### 错误：`gst_buffer_resize_range: assertion failed`

**原因：** GStreamer buffer 处理问题

**解决方案：** 使用透传模式（不重新编码）

```python
# 透传 pipeline（已在 rtsp_server.py 中使用）
filesrc ! qtdemux ! h265parse ! rtph265pay
```

#### 错误：`No such element or plugin 'nvv4l2decoder'`

**原因：** 缺少 Jetson GStreamer 插件

**解决方案：**
```bash
sudo apt-get install nvidia-l4t-gstreamer
```

#### 错误：`Connection refused`

**原因：** RTSP 服务器未启动或端口错误

**排查步骤：**
1. 确认服务器正在运行
2. 检查端口号是否正确
3. 检查防火墙：`sudo ufw status`

### 4. 性能问题排查

#### 查看 CPU 使用率

```bash
top -d 1
```

#### 查看网络带宽使用

```bash
# 安装 iftop
sudo apt-get install iftop

# 监控网卡流量
sudo iftop -i eth0
```

#### 查看视频比特率

```bash
ffprobe -v error -show_entries format=bit_rate -of default=nw=1 video.mp4
```

## 并发能力评估

### 透传模式资源消耗

| 资源 | 消耗 | 说明 |
|------|------|------|
| CPU | 极低 | 仅文件读取 + RTP 封装 |
| GPU | 无 | 不需要编解码 |
| 内存 | 每路约 10-50MB | 缓冲区 |
| 网络 | 视频比特率 | 透传无额外开销 |

### 理论并发路数

```
并发路数 = 可用带宽 / 视频比特率
```

| 网络接口 | 可用带宽 | 10Mbps 视频 | 20Mbps 视频 |
|----------|----------|-------------|-------------|
| eth0 (千兆) | ~800 Mbps | ~80 路 | ~40 路 |
| USB (rndis) | ~200 Mbps | ~20 路 | ~10 路 |
| WiFi | ~50 Mbps | ~5 路 | ~2 路 |

> 注：实际部署建议预留 20-30% 带宽余量

## 网络接口说明

Jetson Nano 常见网络接口：

| 接口 | 类型 | 说明 |
|------|------|------|
| eth0 | 以太网 | 物理千兆网口 |
| wlan0 | WiFi | 无线网卡 |
| l4tbr0 | 网桥 | USB 网络网桥 |
| rndis0 | USB | USB RNDIS 虚拟网卡 |
| usb0 | USB | USB ECM 虚拟网卡 |
| docker0 | 虚拟 | Docker 网桥 |

### 识别 USB 虚拟网卡 vs 物理网卡

USB 虚拟网卡（Jetson USB Device Mode）的 MAC 地址通常以 `8e:21:12` 开头，例如：
- `8e:21:12:4b:94:75` - Jetson USB 虚拟网卡

物理网卡的 MAC 地址由硬件厂商分配，例如：
- `48:b0:2d:xx:xx:xx` - Jetson 物理网口
- `00:0e:c6:xx:xx:xx` - USB 转以太网适配器

## VLAN 配置

### 概述

VLAN（Virtual LAN）允许在单个物理网口上创建多个虚拟网络接口，每个接口属于不同的虚拟局域网。

```
                                    ┌─── eth0.100 (VLAN 100: 192.168.100.2)
┌──────────┐      ┌──────────┐      │
│  Jetson  │──────│  交换机   │──────┼─── eth0.200 (VLAN 200: 192.168.200.2)
│  (eth0)  │ Trunk│  (Trunk) │      │
└──────────┘      └──────────┘      └─── eth0.300 (VLAN 300: 192.168.300.2)
```

### 前置条件

1. 交换机端口需配置为 **Trunk 模式**
2. 交换机需允许对应 VLAN ID 通过
3. Jetson 需加载 `8021q` 内核模块

### 方式一：使用配置脚本（推荐）

#### 1. 编辑配置变量

```bash
vim setup_vlan.sh
```

修改脚本头部的配置变量：

```bash
# 物理网卡
PARENT_INTERFACE="eth0"

# VLAN 配置（可添加多个）
# 格式: "VLAN_ID:IP_ADDRESS:NETMASK"
VLANS=(
    "100:192.168.100.2:24"
    "200:192.168.200.2:24"
    "300:192.168.300.2:24"
)

# 是否持久化配置（写入 netplan）
PERSISTENT=false
```

#### 2. 运行配置脚本

```bash
sudo ./setup_vlan.sh
```

#### 3. 验证配置

```bash
# 查看 VLAN 接口
ip -d link show eth0.100

# 查看所有接口 IP
ip addr show
```

### 方式二：手动配置

#### 1. 加载内核模块

```bash
# 加载 8021q 模块
sudo modprobe 8021q

# 确认模块已加载
lsmod | grep 8021q

# 开机自动加载
echo "8021q" | sudo tee -a /etc/modules
```

#### 2. 创建 VLAN 接口

```bash
# 创建 VLAN 100 接口
sudo ip link add link eth0 name eth0.100 type vlan id 100
sudo ip addr add 192.168.100.2/24 dev eth0.100
sudo ip link set eth0.100 up

# 创建 VLAN 200 接口
sudo ip link add link eth0 name eth0.200 type vlan id 200
sudo ip addr add 192.168.200.2/24 dev eth0.200
sudo ip link set eth0.200 up
```

#### 3. 删除 VLAN 接口

```bash
sudo ip link delete eth0.100
```

### 持久化配置

#### 方式一：Netplan（Ubuntu 18.04+，推荐）

创建配置文件：

```bash
sudo vim /etc/netplan/02-vlans.yaml
```

内容：

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: no
      addresses: [192.168.1.2/24]
  vlans:
    eth0.100:
      id: 100
      link: eth0
      addresses: [192.168.100.2/24]
    eth0.200:
      id: 200
      link: eth0
      addresses: [192.168.200.2/24]
```

应用配置：

```bash
sudo netplan apply
```

#### 方式二：/etc/network/interfaces（传统方式）

```bash
sudo vim /etc/network/interfaces
```

内容：

```
auto eth0
iface eth0 inet static
    address 192.168.1.2
    netmask 255.255.255.0

auto eth0.100
iface eth0.100 inet static
    address 192.168.100.2
    netmask 255.255.255.0
    vlan-raw-device eth0

auto eth0.200
iface eth0.200 inet static
    address 192.168.200.2
    netmask 255.255.255.0
    vlan-raw-device eth0
```

重启网络：

```bash
sudo systemctl restart networking
```

### 交换机配置示例

#### Cisco 交换机

```
interface GigabitEthernet0/1
  switchport mode trunk
  switchport trunk allowed vlan 100,200,300
```

#### 华为交换机

```
interface GigabitEthernet0/0/1
  port link-type trunk
  port trunk allow-pass vlan 100 200 300
```

#### H3C 交换机

```
interface GigabitEthernet1/0/1
  port link-type trunk
  port trunk permit vlan 100 200 300
```

### VLAN 问题排查

#### 检查 8021q 模块

```bash
lsmod | grep 8021q
```

如果没有输出，需要加载模块：

```bash
sudo modprobe 8021q
```

#### 检查 VLAN 接口状态

```bash
# 查看接口详情（包含 VLAN ID）
ip -d link show eth0.100

# 查看 VLAN 信息
cat /proc/net/vlan/eth0.100
```

#### 抓包分析 VLAN 标签

```bash
# 安装 tcpdump
sudo apt-get install tcpdump

# 抓取 VLAN 包（显示 VLAN 标签）
sudo tcpdump -i eth0 -e -n vlan
```

#### 检查交换机端口配置

确认交换机端口：
1. 配置为 Trunk 模式
2. 允许对应 VLAN ID 通过
3. Native VLAN 设置正确

### VLAN 配置变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| PARENT_INTERFACE | eth0 | 物理网卡接口名 |
| VLANS | 100:192.168.100.2:24 | VLAN 配置数组 |
| PERSISTENT | false | 是否写入 netplan 持久化 |

### VLAN 配置格式

```
"VLAN_ID:IP_ADDRESS:NETMASK"
```

示例：
- `"100:192.168.100.2:24"` → VLAN 100，IP 192.168.100.2/24
- `"200:10.0.200.1:16"` → VLAN 200，IP 10.0.200.1/16
