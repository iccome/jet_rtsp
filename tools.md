# Jetson 常用工具命令

## 网络带宽监控

### 1. nload (推荐，简洁直观)
```bash
sudo apt install nload -y
nload
# 或指定网卡
nload eth0
```

### 2. iftop (查看每连接流量)
```bash
sudo apt install iftop -y
sudo iftop -i eth0
```

### 3. vnstat (流量统计)
```bash
sudo apt install vnstat -y
vnstat -l -i eth0  # 实时监控
```

### 4. 系统自带 (无需安装)
```bash
# 实时查看流量
watch -n 1 'cat /proc/net/dev'

# 简单脚本 (计算实时速率)
while true; do
  R1=$(cat /sys/class/net/eth0/statistics/tx_bytes)
  sleep 1
  R2=$(cat /sys/class/net/eth0/statistics/tx_bytes)
  echo "TX: $(( (R2 - R1) / 1024 )) KB/s  ($(( (R2 - R1) * 8 / 1000000 )) Mbps)"
done
```

### 5. 查看网卡最大速率
```bash
ethtool eth0 | grep Speed
# 或
cat /sys/class/net/eth0/speed
```

### 带宽参考
| 网卡类型 | 最大带宽 |
|----------|----------|
| USB 虚拟网卡 (l4tbr0) | ~200 Mbps |
| 100M 以太网 | 100 Mbps |
| 千兆以太网 | ~950 Mbps |

---

## 网络带宽测试 (iperf3)

### 安装
```bash
sudo apt install iperf3 -y
```

### 测试方法
```bash
# 1. 服务端 (Jetson 或电脑)
iperf3 -s

# 2. 客户端 (另一端)
iperf3 -c <服务端IP>
```

### 示例
```bash
# 测试 USB 虚拟网卡带宽
iperf3 -c 192.168.55.1
# 结果: ~205 Mbps

# 测试千兆以太网带宽
iperf3 -c 192.168.1.2
# 结果: ~950 Mbps
```

### Jetson Nano 网卡对比
| 接口 | IP 示例 | 实测带宽 | 适用场景 |
|------|---------|----------|----------|
| l4tbr0 (USB) | 192.168.55.1 | ~205 Mbps | 调试、单路流 |
| eth0 (千兆) | 192.168.1.2 | ~950 Mbps | 多路高码率流 |

### 带宽规划
```
总带宽需求 = 视频比特率总和 × 1.2 (协议开销)

例: 13路 × 12Mbps = 156Mbps
    加开销: 156 × 1.2 = 187Mbps

USB 网卡 (205Mbps): 勉强 ⚠️
千兆网卡 (950Mbps): 充裕 ✅
```

---

## CPU/GPU 监控

### tegrastats (Jetson 专用)
```bash
tegrastats
```

输出说明:
- `RAM`: 内存使用
- `CPU [x%@freq]`: 各核心使用率和频率
- `GR3D_FREQ`: GPU 3D 引擎使用率
- `EMC_FREQ`: 内存带宽使用率
- 温度: PLL, CPU, GPU, AO, thermal

### jtop (推荐，图形化)
```bash
sudo pip3 install jetson-stats
sudo jtop
```

---

## 性能模式

### 查看/设置电源模式
```bash
sudo nvpmodel -q           # 查看当前模式
sudo nvpmodel -m 0         # 设置为 MAXN (最大性能)
```

### 锁定最大频率
```bash
sudo jetson_clocks         # 锁定 CPU/GPU/EMC 频率
sudo jetson_clocks --fan   # 同时开启风扇全速
sudo jetson_clocks --show  # 显示当前频率
```

---

## 风扇控制 (4pin PWM)

### 手动控制
```bash
# 设置转速 (0-255)
sudo sh -c 'echo 255 > /sys/devices/pwm-fan/target_pwm'  # 全速
sudo sh -c 'echo 128 > /sys/devices/pwm-fan/target_pwm'  # 50%
sudo sh -c 'echo 0 > /sys/devices/pwm-fan/target_pwm'    # 关闭

# 查看当前转速
cat /sys/devices/pwm-fan/target_pwm
```

### 转速对照
| 值 | 转速 |
|---|---|
| 255 | 100% |
| 200 | ~78% |
| 128 | 50% |
| 0 | 关闭 |

---

## 摄像头

### 列出摄像头
```bash
v4l2-ctl --list-devices
ls /dev/video*
```

### 查看摄像头支持的格式
```bash
v4l2-ctl -d /dev/video0 --list-formats-ext
```

### 重载 USB 摄像头驱动
```bash
sudo modprobe -r uvcvideo && sudo modprobe uvcvideo
```

---

## GStreamer 调试

### 查看 pipeline 运行状态
```bash
GST_DEBUG=3 python3 multi_res_server.py
```

### 测试编码器
```bash
gst-launch-1.0 videotestsrc ! nvvidconv ! nvv4l2h265enc ! fakesink
```

### 查看元素属性
```bash
gst-inspect-1.0 nvv4l2h265enc
```
