# 工作进度记录

## 已完成

### 1. 创建 camera_rtsp_server.py
- 新建相机 RTSP 服务器，支持外部相机输入
- 支持分辨率缩放（使用 Jetson 硬件加速 nvvidconv）
- 原有 rtsp_server.py（视频文件透传）保持不变

### 2. 支持的相机源类型
| 类型 | 参数 | 说明 |
|------|------|------|
| `usb` | `--device /dev/video0` | USB 摄像头 (V4L2) |
| `csi` | - | Jetson CSI 相机 (nvarguscamerasrc) |
| `rtsp` | `--url rtsp://...` | IP 摄像头/RTSP 源 |
| `test` | - | 测试模式 (videotestsrc) |

### 3. 分辨率缩放
- 使用 `nvvidconv` 硬件加速缩放
- 使用 `nvv4l2h265enc` / `nvv4l2h264enc` 硬件编码

### 4. 摄像头格式查询功能
- `--list-formats` / `-l`: 列出摄像头支持的格式和分辨率
- `--list-cameras`: 列出系统中所有可用的摄像头设备

### 5. H.265 RTSP 源解码支持
- `--input-codec` 参数，支持 H.264 和 H.265 输入

### 6. USB 摄像头自动分辨率匹配
- 自动查询摄像头支持的分辨率
- 智能选择最接近输出分辨率的输入分辨率

### 7. 多路相机支持
- 支持同时运行多个相机流
- 每路可单独配置端口号
- 支持 `enable` 字段控制是否启用
- `--config` 参数加载 JSON 配置文件
- `--generate-config` 参数生成示例配置

### 8. USB 摄像头输入格式支持
- 新增 `input_format` 配置项，支持：
  - `mjpeg` - Motion JPEG (高分辨率高帧率)
  - `yuyv` - YUYV 4:2:2 原始格式
  - `nv12` - NV12 格式
- 使用 `nvv4l2decoder mjpeg=1` 硬件解码 MJPEG（输出到 NVMM 内存）

---

## 当前问题

### GStreamer 缓冲区错误 - 已修复
```
GStreamer-CRITICAL: gst_buffer_resize_range: assertion 'bufmax >= bufoffs + offset + size' failed
```

**根本原因：**
`nvjpegdec` 与 `nvvidconv` 之间的缓冲区同步问题

**解决方案：**
将 `nvjpegdec` 替换为 `nvv4l2decoder mjpeg=1` 并添加 `queue` 元素：
```
v4l2src ! image/jpeg ! nvv4l2decoder mjpeg=1 ! queue max-size-buffers=3 leaky=downstream ! nvvidconv ! nvv4l2h265enc
```

优点：
1. `nvv4l2decoder` 输出直接到 NVMM 内存，避免内存拷贝
2. `queue` 元素缓冲帧数据，防止缓冲区问题
3. `leaky=downstream` 在队列满时丢弃旧帧，避免阻塞

### 设备占用错误
```
libv4l2: error setting pixformat: Device or resource busy
```

**解决方法：**
```bash
# 重载 USB 摄像头驱动
sudo modprobe -r uvcvideo && sudo modprobe uvcvideo
```

### USB 摄像头设备号变化

USB 摄像头的 `/dev/videoX` 设备号在重新插拔或重启后可能会变化，导致配置文件中的设备路径失效。

**临时解决：** 启动前先确认设备
```bash
./camera_rtsp_server.py --list-cameras
```

**永久解决：** 使用 udev 规则固定设备名称
```bash
# 1. 查看摄像头的 Vendor/Product ID
udevadm info -a /dev/video0 | grep -E "idVendor|idProduct|serial"

# 2. 创建 udev 规则
sudo tee /etc/udev/rules.d/99-usb-camera.rules << 'EOF'
SUBSYSTEM=="video4linux", ATTRS{idVendor}=="xxxx", ATTRS{idProduct}=="yyyy", SYMLINK+="camera1"
EOF

# 3. 重新加载规则
sudo udevadm control --reload-rules

# 4. 重新插拔摄像头后，可使用固定的 /dev/camera1
```

---

## 摄像头信息

### /dev/video0
- YUYV: 最高 1280x960 @ 7.5fps, 640x480 @ 30fps
- **MJPEG: 最高 1280x720 @ 30fps** ✓

### /dev/video1
- YUYV: 1920x1080 @ 5fps, 640x480 @ 30fps
- **MJPEG: 1920x1080 @ 30fps** ✓
- NV12: 1920x1080 @ 5fps

---

## 当前配置文件 (camera_config.json)

```json
{
  "port": 8554,
  "streams": [
    {
      "name": "USB 摄像头 1",
      "enable": false,
      "port": 8554,
      "device": "/dev/video0",
      "input_format": "mjpeg",
      "input_width": 1280,
      "input_height": 720,
      "output_width": 1920,
      "output_height": 1080,
      "codec": "h265",
      "bitrate": 9000,
      "framerate": 30
    },
    {
      "name": "USB 摄像头 2",
      "enable": true,
      "port": 8555,
      "device": "/dev/video1",
      "input_format": "mjpeg",
      "input_width": 1920,
      "input_height": 1080,
      "output_width": 1920,
      "output_height": 1080,
      "codec": "h265",
      "bitrate": 9000,
      "framerate": 30
    }
  ]
}
```

---

## 多分辨率 RTSP 服务器 (2026-01-27)

### 需求
- 一路摄像头输出多个不同分辨率的 RTSP 流
- 编码固定为 H.265
- 每个分辨率发布到不同端口（8554, 8555, 8556 等）

### 实现架构
```
                      +-> queue -> nvvidconv (1080p) -> nvv4l2h265enc -> UDP:15000 -> RTSP:8554
                      |
v4l2src -> decode -> tee -> queue -> nvvidconv (720p)  -> nvv4l2h265enc -> UDP:15001 -> RTSP:8555
                      |
                      +-> queue -> nvvidconv (480p)  -> nvv4l2h265enc -> UDP:15002 -> RTSP:8556
```

关键点：
- **单一摄像头源** - 摄像头只打开一次，解码一次
- **tee 分流** - 将解码后的视频分发到多个编码分支
- **UDP 内部传输** - 编码后通过 localhost UDP 传给 RTSP 服务器
- **独立端口** - 每个分辨率使用独立 RTSP 端口

### 新建文件
- `multi_res_server.py` - 多分辨率 RTSP 服务器主程序
- `multi_res_config.json` - 配置文件

### 使用方法
```bash
python3 multi_res_server.py --config multi_res_config.json
```

### Jetson Nano 硬件限制

| 路数 | 状态 | 说明 |
|------|------|------|
| 2 路 | ✅ 稳定 | 全 1080p 无问题 |
| 4 路 | ⚠️ 边界 | 偶尔花屏，基本可用 |
| 6+ 路 | ❌ 超载 | 黑屏/花屏 |
| 13 路 | ❌ 丢帧 | MAXN 模式 + jetson_clocks 仍有丢帧 |

**13路测试结果 (2026-01-31):**
- 模式: MAXN (nvpmodel -m 0) + jetson_clocks
- 现象: 丢帧
- 原因: nvv4l2h265enc 硬件编码器达到极限

### 性能优化建议

1. **启用全部 CPU 核心**
   ```bash
   sudo nvpmodel -m 0      # 最大性能模式 (10W, 4核)
   sudo jetson_clocks      # 最大化时钟频率
   sudo nvpmodel -q        # 查看当前状态
   ```

2. **多路混合分辨率** - 降低部分流的分辨率以支持更多路数
   ```
   2 路 1080p + 4 路 720p + 2 路 480p = 8 路
   ```

3. **降低比特率** - 减少编码器负载

### 当前测试配置 (8路混合分辨率)
```json
{
  "camera": {
    "device": "/dev/video0",
    "input_format": "mjpeg",
    "input_width": 1920,
    "input_height": 1080,
    "framerate": 30
  },
  "streams": [
    { "name": "camera0", "port": 8554, "width": 1920, "height": 1080, "bitrate": 6000 },
    { "name": "camera1", "port": 8555, "width": 1920, "height": 1080, "bitrate": 6000 },
    { "name": "camera2", "port": 8556, "width": 1280, "height": 720,  "bitrate": 4000 },
    { "name": "camera3", "port": 8557, "width": 1280, "height": 720,  "bitrate": 4000 },
    { "name": "camera4", "port": 8558, "width": 1280, "height": 720,  "bitrate": 4000 },
    { "name": "camera5", "port": 8559, "width": 1280, "height": 720,  "bitrate": 4000 },
    { "name": "camera6", "port": 8560, "width": 640,  "height": 480,  "bitrate": 2000 },
    { "name": "camera7", "port": 8561, "width": 640,  "height": 480,  "bitrate": 2000 }
  ]
}
```

### 待测试
- [ ] 启用 4 核后测试 8 路
- [ ] 确认稳定的最大路数

---

## 下次继续的工作

1. **测试修复后的 MJPEG pipeline**
   ```bash
   # 先重载驱动
   sudo modprobe -r uvcvideo && sudo modprobe uvcvideo

   # 运行测试
   python3 camera_rtsp_server.py --config camera_config.json
   ```

2. **当前 pipeline (已更新)**
   ```
   v4l2src ! image/jpeg ! nvv4l2decoder mjpeg=1 ! queue max-size-buffers=3 leaky=downstream ! nvvidconv ! nvv4l2h265enc
   ```

3. **如果仍有问题的备选方案**
   ```
   # 备选方案: 软件解码 + queue
   v4l2src ! image/jpeg ! jpegdec ! queue ! videoconvert ! nvvidconv ! nvv4l2h265enc
   ```

---

## 文件结构

```
rtsp_server/
├── rtsp_server.py          # 视频文件透传 RTSP 服务器
├── camera_rtsp_server.py   # 相机 RTSP 服务器（多摄像头）
├── camera_config.json      # 多路相机配置文件
├── multi_res_server.py     # 多分辨率 RTSP 服务器（单摄像头多输出）
├── multi_res_config.json   # 多分辨率配置文件
├── README.md               # 文档
└── WORK_PROGRESS.md        # 本进度记录
```

---

## Jetson Nano 风扇控制 (4pin PWM)

### 手动控制
```bash
# 设置风扇转速 (0-255)
sudo sh -c 'echo 255 > /sys/devices/pwm-fan/target_pwm'  # 全速
sudo sh -c 'echo 128 > /sys/devices/pwm-fan/target_pwm'  # 50%
sudo sh -c 'echo 0 > /sys/devices/pwm-fan/target_pwm'    # 关闭

# 查看当前转速
cat /sys/devices/pwm-fan/target_pwm
```

### 转速对照表
| 值 | 转速 |
|---|---|
| 255 | 100% (全速) |
| 200 | ~78% |
| 128 | 50% |
| 80 | ~31% |
| 0 | 关闭 |

### 配合 jetson_clocks 使用
```bash
sudo jetson_clocks --fan  # 锁定 CPU/GPU 频率 + 风扇全速
```

### 开机自动全速
```bash
# 创建 systemd 服务
sudo tee /etc/systemd/system/fan-max.service << 'EOF'
[Unit]
Description=Set fan to max speed
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo 255 > /sys/devices/pwm-fan/target_pwm'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# 启用服务
sudo systemctl enable fan-max.service
sudo systemctl start fan-max.service
```

### 查看温度
```bash
# CPU/GPU 温度
cat /sys/devices/virtual/thermal/thermal_zone*/temp

# 实时监控
tegrastats
```

---

## Jetson 信息
- IP 地址: 192.168.1.2
- 播放地址: `rtsp://192.168.1.2:8554/stream`
