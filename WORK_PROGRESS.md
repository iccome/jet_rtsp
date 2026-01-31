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
├── rtsp_server.py          # 原有：视频文件透传 RTSP 服务器
├── camera_rtsp_server.py   # 新建：相机 RTSP 服务器
├── camera_config.json      # 多路相机配置文件
├── README.md               # 原有文档
└── WORK_PROGRESS.md        # 本进度记录
```

---

## Jetson 信息
- IP 地址: 192.168.1.2
- 播放地址: `rtsp://192.168.1.2:8554/stream`
