#!/usr/bin/env python3
"""
Jetson Nano Camera RTSP Server
支持外部相机（USB、CSI、RTSP源）的 RTSP 流媒体服务器
支持分辨率缩放和硬件加速编码
"""

import sys
import argparse
import subprocess
import re
import json
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib


def list_camera_formats(device: str = "/dev/video0") -> bool:
    """
    列出摄像头支持的格式和分辨率

    Args:
        device: 摄像头设备路径

    Returns:
        True 如果成功, False 如果失败
    """
    print(f"查询摄像头格式: {device}")
    print("=" * 60)

    # 方法1: 使用 v4l2-ctl
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--device", device, "--list-formats-ext"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            print("使用 v4l2-ctl 查询结果:")
            print("-" * 60)
            print(result.stdout)
            return True
    except FileNotFoundError:
        print("提示: v4l2-ctl 未安装，可通过 'sudo apt install v4l-utils' 安装")
    except subprocess.TimeoutExpired:
        print("警告: v4l2-ctl 查询超时")
    except Exception as e:
        print(f"v4l2-ctl 查询失败: {e}")

    # 方法2: 使用 GStreamer 查询
    print("\n尝试使用 GStreamer 查询...")
    print("-" * 60)

    try:
        Gst.init(None)

        # 创建 v4l2src 元素
        source = Gst.ElementFactory.make("v4l2src", "source")
        if not source:
            print("错误: 无法创建 v4l2src 元素")
            return False

        source.set_property("device", device)

        # 获取 src pad
        source.set_state(Gst.State.READY)
        pad = source.get_static_pad("src")

        if pad:
            caps = pad.query_caps(None)
            if caps:
                print(f"支持的格式 (共 {caps.get_size()} 种):\n")

                # 解析并整理格式信息
                formats = {}
                for i in range(caps.get_size()):
                    structure = caps.get_structure(i)
                    name = structure.get_name()

                    # 获取格式
                    fmt = structure.get_string("format")
                    if not fmt:
                        fmt = name

                    # 获取分辨率
                    width = structure.get_value("width")
                    height = structure.get_value("height")

                    # 获取帧率
                    framerate = structure.get_value("framerate")

                    if width and height:
                        key = fmt if fmt else name
                        if key not in formats:
                            formats[key] = []

                        fps_str = ""
                        if framerate:
                            if hasattr(framerate, 'num') and hasattr(framerate, 'denom'):
                                fps = framerate.num / framerate.denom if framerate.denom else 0
                                fps_str = f" @ {fps:.1f}fps"

                        res_str = f"{width}x{height}{fps_str}"
                        if res_str not in formats[key]:
                            formats[key].append(res_str)

                # 打印整理后的格式
                for fmt, resolutions in formats.items():
                    print(f"格式: {fmt}")
                    for res in sorted(set(resolutions), key=lambda x: int(x.split('x')[0]) if x.split('x')[0].isdigit() else 0, reverse=True):
                        print(f"  - {res}")
                    print()

        source.set_state(Gst.State.NULL)
        return True

    except Exception as e:
        print(f"GStreamer 查询失败: {e}")
        return False


def list_all_cameras() -> list:
    """
    列出系统中所有可用的摄像头设备

    Returns:
        设备列表 [(device_path, device_name), ...]
    """
    import os

    cameras = []

    # 查找 /dev/video* 设备
    for i in range(10):
        device = f"/dev/video{i}"
        if os.path.exists(device):
            name = f"Video device {i}"

            # 尝试获取设备名称
            try:
                result = subprocess.run(
                    ["v4l2-ctl", "--device", device, "--info"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Card type' in line:
                            name = line.split(':')[1].strip()
                            break
            except:
                pass

            cameras.append((device, name))

    return cameras


def get_camera_resolutions(device: str = "/dev/video0") -> list:
    """
    获取摄像头支持的所有分辨率

    Args:
        device: 摄像头设备路径

    Returns:
        分辨率列表 [(width, height, max_fps), ...] 按像素数降序排列
    """
    resolutions = []

    # 方法1: 使用 v4l2-ctl 查询
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--device", device, "--list-formats-ext"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            current_width = None
            current_height = None
            max_fps = 30

            for line in result.stdout.split('\n'):
                # 匹配分辨率行，如 "Size: Discrete 1920x1080"
                size_match = re.search(r'Size:\s*\w+\s+(\d+)x(\d+)', line)
                if size_match:
                    current_width = int(size_match.group(1))
                    current_height = int(size_match.group(2))
                    max_fps = 30  # 重置

                # 匹配帧率行，如 "Interval: Discrete 0.033s (30.000 fps)"
                fps_match = re.search(r'\((\d+(?:\.\d+)?)\s*fps\)', line)
                if fps_match and current_width and current_height:
                    fps = float(fps_match.group(1))
                    if fps > max_fps:
                        max_fps = fps

                # 当遇到下一个分辨率或空行时，保存当前分辨率
                if current_width and current_height:
                    res = (current_width, current_height, int(max_fps))
                    if res not in resolutions:
                        resolutions.append(res)

    except Exception:
        pass

    # 方法2: 使用 GStreamer 查询作为备选
    if not resolutions:
        try:
            Gst.init(None)
            source = Gst.ElementFactory.make("v4l2src", "source")
            if source:
                source.set_property("device", device)
                source.set_state(Gst.State.READY)
                pad = source.get_static_pad("src")

                if pad:
                    caps = pad.query_caps(None)
                    for i in range(caps.get_size()):
                        structure = caps.get_structure(i)
                        width = structure.get_value("width")
                        height = structure.get_value("height")

                        if width and height:
                            # 获取帧率
                            fps = 30
                            framerate = structure.get_value("framerate")
                            if framerate and hasattr(framerate, 'num') and hasattr(framerate, 'denom'):
                                if framerate.denom:
                                    fps = int(framerate.num / framerate.denom)

                            res = (width, height, fps)
                            if res not in resolutions:
                                resolutions.append(res)

                source.set_state(Gst.State.NULL)
        except Exception:
            pass

    # 按像素数降序排列（优先选择高分辨率）
    resolutions.sort(key=lambda x: x[0] * x[1], reverse=True)

    # 去重（保留每个分辨率的最高帧率）
    unique_resolutions = {}
    for w, h, fps in resolutions:
        key = (w, h)
        if key not in unique_resolutions or fps > unique_resolutions[key]:
            unique_resolutions[key] = fps

    return [(w, h, fps) for (w, h), fps in sorted(unique_resolutions.items(),
                                                   key=lambda x: x[0][0] * x[0][1],
                                                   reverse=True)]


def find_best_resolution(device: str, target_width: int, target_height: int,
                         target_fps: int = 30) -> tuple:
    """
    查找最接近目标分辨率的摄像头分辨率

    策略:
    1. 优先选择 >= 目标分辨率的最小分辨率（便于缩小）
    2. 如果没有更大的，选择最接近的较小分辨率（需要放大）
    3. 帧率需要 >= 目标帧率

    Args:
        device: 摄像头设备路径
        target_width: 目标宽度
        target_height: 目标高度
        target_fps: 目标帧率

    Returns:
        (width, height, fps) 或 None 如果查询失败
    """
    resolutions = get_camera_resolutions(device)

    if not resolutions:
        return None

    target_pixels = target_width * target_height

    # 筛选帧率满足要求的分辨率
    valid_resolutions = [(w, h, fps) for w, h, fps in resolutions if fps >= target_fps]

    # 如果没有满足帧率要求的，使用所有分辨率
    if not valid_resolutions:
        valid_resolutions = resolutions

    # 分为两组：大于等于目标 和 小于目标
    larger_or_equal = []
    smaller = []

    for w, h, fps in valid_resolutions:
        pixels = w * h
        if pixels >= target_pixels:
            larger_or_equal.append((w, h, fps, pixels))
        else:
            smaller.append((w, h, fps, pixels))

    # 优先选择大于等于目标的最小分辨率
    if larger_or_equal:
        larger_or_equal.sort(key=lambda x: x[3])  # 按像素数升序
        best = larger_or_equal[0]
        return (best[0], best[1], best[2])

    # 否则选择最大的较小分辨率
    if smaller:
        smaller.sort(key=lambda x: x[3], reverse=True)  # 按像素数降序
        best = smaller[0]
        return (best[0], best[1], best[2])

    # 都没有，返回第一个
    if valid_resolutions:
        return valid_resolutions[0]

    return None


class CameraSource:
    """相机源类型"""
    USB = "usb"
    CSI = "csi"
    RTSP = "rtsp"
    TEST = "test"  # 测试模式，使用 videotestsrc


class CameraRTSPServer:
    def __init__(self,
                 source_type: str = CameraSource.USB,
                 device: str = "/dev/video0",
                 rtsp_url: str = None,
                 port: int = 8554,
                 mount_point: str = "/stream",
                 codec: str = "h265",
                 input_format: str = "mjpeg",
                 input_codec: str = "h264",
                 bitrate: int = 4000000,
                 input_width: int = None,
                 input_height: int = None,
                 output_width: int = 1920,
                 output_height: int = 1080,
                 framerate: int = 30,
                 flip_method: int = 0):
        """
        初始化相机 RTSP 服务器

        Args:
            source_type: 相机源类型 (usb, csi, rtsp, test)
            device: USB 相机设备路径 (如 /dev/video0)
            rtsp_url: RTSP 源地址 (用于 rtsp 类型)
            port: RTSP 服务端口
            mount_point: RTSP 挂载点
            codec: 输出编码格式 (h264 或 h265)
            input_format: USB 摄像头输入格式 (mjpeg, yuyv, nv12)
            input_codec: RTSP 源输入编码格式 (h264 或 h265)
            bitrate: 编码比特率 (bps)
            input_width: 输入分辨率宽度 (None 表示自动检测)
            input_height: 输入分辨率高度 (None 表示自动检测)
            output_width: 输出分辨率宽度
            output_height: 输出分辨率高度
            framerate: 帧率
            flip_method: 图像翻转方式 (0-7, 仅 CSI 相机)
        """
        self.source_type = source_type
        self.device = device
        self.rtsp_url = rtsp_url
        self.port = port
        self.mount_point = mount_point
        self.codec = codec.lower()
        self.input_format = input_format.lower()
        self.input_codec = input_codec.lower()
        self.bitrate = bitrate
        self.input_width = input_width
        self.input_height = input_height
        self.output_width = output_width
        self.output_height = output_height
        self.framerate = framerate
        self.flip_method = flip_method

        Gst.init(None)

    def _auto_detect_resolution(self):
        """自动检测 USB 摄像头的最佳输入分辨率"""
        if self.source_type != CameraSource.USB:
            return

        if self.input_width and self.input_height:
            # 用户已指定输入分辨率
            self._auto_detected = False
            return

        # 自动查找最佳分辨率
        best = find_best_resolution(
            self.device,
            self.output_width,
            self.output_height,
            self.framerate
        )

        if best:
            self.input_width, self.input_height, detected_fps = best
            self._auto_detected = True
            # 如果检测到的最大帧率低于目标帧率，使用检测到的帧率
            if detected_fps < self.framerate:
                self.framerate = detected_fps
        else:
            self._auto_detected = False

    def _build_source_pipeline(self) -> str:
        """构建视频源 pipeline"""
        if self.source_type == CameraSource.USB:
            # USB 相机 (V4L2)
            # 自动检测分辨率（如果未指定）
            self._auto_detect_resolution()

            source = f'v4l2src device="{self.device}"'

            # 根据输入格式构建不同的 pipeline
            if self.input_format == 'mjpeg':
                # MJPEG 格式 - 使用 nvv4l2decoder 硬件解码 (Jetson)
                # 这是推荐的 Jetson MJPEG 解码方案，输出直接到 NVMM 内存
                if self.input_width and self.input_height:
                    source += (
                        f' ! image/jpeg,width={self.input_width},'
                        f'height={self.input_height},framerate={self.framerate}/1'
                    )
                else:
                    source += f' ! image/jpeg,framerate={self.framerate}/1'
                # 使用 nvv4l2decoder 解码 MJPEG，添加 queue 防止缓冲区问题
                source += ' ! nvv4l2decoder mjpeg=1 ! queue max-size-buffers=3 leaky=downstream'

            elif self.input_format == 'nv12':
                # NV12 格式
                if self.input_width and self.input_height:
                    source += (
                        f' ! video/x-raw,format=NV12,width={self.input_width},'
                        f'height={self.input_height},framerate={self.framerate}/1'
                    )
                else:
                    source += f' ! video/x-raw,format=NV12,framerate={self.framerate}/1'

            else:
                # YUYV 格式 (默认)
                if self.input_width and self.input_height:
                    source += (
                        f' ! video/x-raw,format=YUY2,width={self.input_width},'
                        f'height={self.input_height},framerate={self.framerate}/1'
                    )
                else:
                    source += f' ! video/x-raw,format=YUY2,framerate={self.framerate}/1'
                source += ' ! videoconvert'

            return source

        elif self.source_type == CameraSource.CSI:
            # CSI 相机 (Jetson 原生)
            width = self.input_width or 1920
            height = self.input_height or 1080
            source = (
                f'nvarguscamerasrc ! '
                f'video/x-raw(memory:NVMM),width={width},height={height},'
                f'format=NV12,framerate={self.framerate}/1 ! '
                f'nvvidconv flip-method={self.flip_method}'
            )
            return source

        elif self.source_type == CameraSource.RTSP:
            # RTSP 源
            if not self.rtsp_url:
                raise ValueError("RTSP 源需要提供 rtsp_url 参数")

            if self.input_codec == "h265":
                # H.265/HEVC 输入
                source = (
                    f'rtspsrc location="{self.rtsp_url}" latency=100 ! '
                    f'rtph265depay ! h265parse ! nvv4l2decoder'
                )
            else:
                # H.264/AVC 输入 (默认)
                source = (
                    f'rtspsrc location="{self.rtsp_url}" latency=100 ! '
                    f'rtph264depay ! h264parse ! nvv4l2decoder'
                )
            return source

        elif self.source_type == CameraSource.TEST:
            # 测试源
            width = self.input_width or 640
            height = self.input_height or 480
            source = (
                f'videotestsrc is-live=true pattern=ball ! '
                f'video/x-raw,width={width},height={height},'
                f'framerate={self.framerate}/1'
            )
            return source

        else:
            raise ValueError(f"不支持的相机源类型: {self.source_type}")

    def _build_scale_pipeline(self) -> str:
        """构建缩放 pipeline (使用 Jetson 硬件加速)"""
        # 判断是否需要缩放
        needs_scale = True

        if self.source_type == CameraSource.CSI:
            # CSI 相机已经在 NVMM 内存中
            scale = (
                f'nvvidconv ! '
                f'video/x-raw(memory:NVMM),width={self.output_width},'
                f'height={self.output_height},format=NV12'
            )
        elif self.source_type == CameraSource.RTSP:
            # RTSP 解码后已在 NVMM 内存中
            scale = (
                f'nvvidconv ! '
                f'video/x-raw(memory:NVMM),width={self.output_width},'
                f'height={self.output_height},format=NV12'
            )
        else:
            # USB 相机和测试源需要先上传到 NVMM
            scale = (
                f'nvvidconv ! '
                f'video/x-raw(memory:NVMM),width={self.output_width},'
                f'height={self.output_height},format=NV12'
            )

        return scale

    def _build_encoder_pipeline(self) -> str:
        """构建编码器 pipeline (使用 Jetson 硬件加速)"""
        if self.codec == "h265":
            encoder = (
                f'nvv4l2h265enc bitrate={self.bitrate} '
                f'preset-level=1 iframeinterval=30 ! '
                f'h265parse ! '
                f'rtph265pay name=pay0 pt=96 config-interval=1'
            )
        else:  # h264
            encoder = (
                f'nvv4l2h264enc bitrate={self.bitrate} '
                f'preset-level=1 iframeinterval=30 ! '
                f'h264parse ! '
                f'rtph264pay name=pay0 pt=96 config-interval=1'
            )

        return encoder

    def _build_pipeline(self) -> str:
        """构建完整的 GStreamer pipeline"""
        source = self._build_source_pipeline()
        scale = self._build_scale_pipeline()
        encoder = self._build_encoder_pipeline()

        pipeline = f"( {source} ! {scale} ! {encoder} )"
        return pipeline

    def start(self):
        """启动 RTSP 服务器"""
        server = GstRtspServer.RTSPServer()
        server.set_service(str(self.port))

        factory = GstRtspServer.RTSPMediaFactory()

        pipeline = self._build_pipeline()
        print(f"Pipeline: {pipeline}")

        factory.set_launch(pipeline)
        factory.set_shared(True)

        mounts = server.get_mount_points()
        mounts.add_factory(self.mount_point, factory)

        server.attach(None)

        # 获取所有网卡 IP
        ips = self._get_all_ips()

        print("=" * 60)
        print(f"Camera RTSP 服务器已启动")
        print("-" * 60)
        print(f"相机源类型: {self.source_type.upper()}")
        if self.source_type == CameraSource.USB:
            print(f"设备: {self.device}")
            if self.input_width and self.input_height:
                auto_tag = " (自动检测)" if getattr(self, '_auto_detected', False) else ""
                print(f"输入分辨率: {self.input_width}x{self.input_height}{auto_tag}")
        elif self.source_type == CameraSource.RTSP:
            print(f"RTSP 源: {self.rtsp_url}")
            print(f"输入编码: {self.input_codec.upper()}")
        elif self.source_type == CameraSource.CSI:
            width = self.input_width or 1920
            height = self.input_height or 1080
            print(f"输入分辨率: {width}x{height}")
        print(f"输出分辨率: {self.output_width}x{self.output_height}")
        print(f"输出编码: {self.codec.upper()}")
        print(f"比特率: {self.bitrate // 1000} kbps")
        print(f"帧率: {self.framerate} fps")
        print("=" * 60)
        print("RTSP 地址:")
        for iface, ip in ips:
            print(f"  [{iface}] rtsp://{ip}:{self.port}{self.mount_point}")
        print("=" * 60)
        print("按 Ctrl+C 停止服务器")

        loop = GLib.MainLoop()
        try:
            loop.run()
        except KeyboardInterrupt:
            print("\n服务器已停止")

    def _get_all_ips(self) -> list:
        """获取所有网卡的 IP 地址"""
        import socket
        import fcntl
        import struct

        ips = []
        try:
            for iface in socket.if_nameindex():
                iface_name = iface[1]
                if iface_name == 'lo':
                    continue
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    ip = socket.inet_ntoa(fcntl.ioctl(
                        s.fileno(),
                        0x8915,  # SIOCGIFADDR
                        struct.pack('256s', iface_name[:15].encode('utf-8'))
                    )[20:24])
                    ips.append((iface_name, ip))
                    s.close()
                except OSError:
                    pass
        except Exception:
            pass

        if not ips:
            ips.append(("unknown", "localhost"))
        return ips


class MultiCameraRTSPServer:
    """多路相机 RTSP 服务器"""

    def __init__(self, port: int = 8554):
        """
        初始化多路相机 RTSP 服务器

        Args:
            port: RTSP 服务端口
        """
        self.port = port
        self.streams = []  # 存储所有流配置
        Gst.init(None)

    def add_stream(self, config: dict):
        """
        添加一个视频流

        Args:
            config: 流配置字典，包含:
                - name: 流名称（用于显示）
                - mount: 挂载点 (如 /stream1)
                - port: 端口号（可选，默认使用全局端口）
                - source: 源类型 (usb/csi/rtsp/test)
                - device: USB 设备路径（可选）
                - url: RTSP 源地址（可选）
                - input_codec: 输入编码（可选，默认 h264）
                - codec: 输出编码（可选，默认 h265）
                - bitrate: 比特率 kbps（可选，默认 4000）
                - input_width/input_height: 输入分辨率（可选）
                - output_width/output_height: 输出分辨率（可选，默认 1920x1080）
                - framerate: 帧率（可选，默认 30）
                - flip: 翻转方式（可选，默认 0）
        """
        # 设置默认值
        stream_config = {
            'name': config.get('name', f'Stream {len(self.streams) + 1}'),
            'enable': config.get('enable', True),  # 是否启用，默认启用
            'mount': config.get('mount', f'/stream{len(self.streams) + 1}'),
            'port': config.get('port', self.port),  # 支持单独配置端口
            'source': config.get('source', 'test'),
            'device': config.get('device', '/dev/video0'),
            'url': config.get('url'),
            'input_format': config.get('input_format', 'mjpeg'),  # USB 摄像头输入格式: mjpeg, yuyv, nv12
            'input_codec': config.get('input_codec', 'h264'),
            'codec': config.get('codec', 'h265'),
            'bitrate': config.get('bitrate', 4000),
            'input_width': config.get('input_width'),
            'input_height': config.get('input_height'),
            'output_width': config.get('output_width', 1920),
            'output_height': config.get('output_height', 1080),
            'framerate': config.get('framerate', 30),
            'flip': config.get('flip', 0),
        }
        self.streams.append(stream_config)

    def _create_camera_server(self, config: dict) -> CameraRTSPServer:
        """根据配置创建 CameraRTSPServer 实例"""
        return CameraRTSPServer(
            source_type=config['source'],
            device=config['device'],
            rtsp_url=config['url'],
            port=self.port,
            mount_point=config['mount'],
            codec=config['codec'],
            input_format=config.get('input_format', 'mjpeg'),
            input_codec=config['input_codec'],
            bitrate=config['bitrate'] * 1000,
            input_width=config['input_width'],
            input_height=config['input_height'],
            output_width=config['output_width'],
            output_height=config['output_height'],
            framerate=config['framerate'],
            flip_method=config['flip']
        )

    def start(self):
        """启动多路 RTSP 服务器"""
        if not self.streams:
            print("错误: 没有配置任何视频流", file=sys.stderr)
            sys.exit(1)

        # 过滤出启用的流
        enabled_streams = [s for s in self.streams if s.get('enable', True)]
        disabled_count = len(self.streams) - len(enabled_streams)

        if not enabled_streams:
            print("错误: 没有启用任何视频流", file=sys.stderr)
            sys.exit(1)

        # 按端口分组
        streams_by_port = {}
        for config in enabled_streams:
            port = config['port']
            if port not in streams_by_port:
                streams_by_port[port] = []
            streams_by_port[port].append(config)

        print("=" * 60)
        print(f"多路 Camera RTSP 服务器")
        if disabled_count > 0:
            print(f"正在初始化 {len(enabled_streams)} 路视频流 ({disabled_count} 路已禁用)...")
        else:
            print(f"正在初始化 {len(enabled_streams)} 路视频流...")
        print("=" * 60)

        # 为每个端口创建一个 RTSP 服务器
        servers = {}
        for port, port_streams in streams_by_port.items():
            server = GstRtspServer.RTSPServer()
            server.set_service(str(port))
            servers[port] = server
            mounts = server.get_mount_points()

            # 为该端口的每个流创建 factory
            for config in port_streams:
                try:
                    cam_server = self._create_camera_server(config)
                    pipeline = cam_server._build_pipeline()

                    factory = GstRtspServer.RTSPMediaFactory()
                    factory.set_launch(pipeline)
                    factory.set_shared(True)

                    mounts.add_factory(config['mount'], factory)

                    # 记录自动检测的分辨率
                    config['_cam_server'] = cam_server

                except Exception as e:
                    print(f"初始化失败 [{config['name']}]: {e}", file=sys.stderr)

            server.attach(None)

        # 打印流信息
        for i, config in enumerate(enabled_streams):
            print(f"\n[{i+1}] {config['name']}")
            print(f"    类型: {config['source'].upper()}")
            if config['source'] == 'usb':
                print(f"    设备: {config['device']}")
                cam_server = config.get('_cam_server')
                if cam_server and cam_server.input_width and cam_server.input_height:
                    auto_tag = " (自动)" if getattr(cam_server, '_auto_detected', False) else ""
                    print(f"    输入: {cam_server.input_width}x{cam_server.input_height}{auto_tag}")
            elif config['source'] == 'rtsp':
                print(f"    源: {config['url']}")
                print(f"    输入编码: {config['input_codec'].upper()}")
            print(f"    输出: {config['output_width']}x{config['output_height']} {config['codec'].upper()}")
            print(f"    端口: {config['port']}")
            print(f"    挂载点: {config['mount']}")

        # 获取 IP 地址
        ips = self._get_all_ips()

        print("\n" + "=" * 60)
        print("RTSP 地址:")
        for iface, ip in ips:
            print(f"\n  [{iface}] {ip}")
            for config in enabled_streams:
                print(f"    - {config['name']}: rtsp://{ip}:{config['port']}{config['mount']}")
        print("\n" + "=" * 60)
        print("按 Ctrl+C 停止服务器")

        loop = GLib.MainLoop()
        try:
            loop.run()
        except KeyboardInterrupt:
            print("\n服务器已停止")

    def _get_all_ips(self) -> list:
        """获取所有网卡的 IP 地址"""
        import socket
        import fcntl
        import struct

        ips = []
        try:
            for iface in socket.if_nameindex():
                iface_name = iface[1]
                if iface_name == 'lo':
                    continue
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    ip = socket.inet_ntoa(fcntl.ioctl(
                        s.fileno(),
                        0x8915,
                        struct.pack('256s', iface_name[:15].encode('utf-8'))
                    )[20:24])
                    ips.append((iface_name, ip))
                    s.close()
                except OSError:
                    pass
        except Exception:
            pass

        if not ips:
            ips.append(("unknown", "localhost"))
        return ips

    @staticmethod
    def from_config_file(config_path: str) -> 'MultiCameraRTSPServer':
        """
        从配置文件创建多路服务器

        Args:
            config_path: JSON 配置文件路径

        Returns:
            MultiCameraRTSPServer 实例
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        port = config.get('port', 8554)
        server = MultiCameraRTSPServer(port=port)

        for stream in config.get('streams', []):
            server.add_stream(stream)

        return server

    @staticmethod
    def generate_sample_config(output_path: str = None) -> str:
        """
        生成示例配置文件

        Args:
            output_path: 输出路径，None 则返回字符串

        Returns:
            配置文件内容
        """
        sample_config = {
            "port": 8554,
            "streams": [
                {
                    "name": "USB 摄像头",
                    "mount": "/usb",
                    "source": "usb",
                    "device": "/dev/video0",
                    "output_width": 1920,
                    "output_height": 1080,
                    "codec": "h265",
                    "bitrate": 4000,
                    "framerate": 30
                },
                {
                    "name": "测试源",
                    "mount": "/test",
                    "source": "test",
                    "output_width": 1280,
                    "output_height": 720,
                    "codec": "h264",
                    "bitrate": 2000
                },
                {
                    "name": "IP 摄像头",
                    "mount": "/ipcam",
                    "source": "rtsp",
                    "url": "rtsp://192.168.1.100:554/stream",
                    "input_codec": "h264",
                    "output_width": 1920,
                    "output_height": 1080,
                    "codec": "h265"
                }
            ]
        }

        content = json.dumps(sample_config, indent=2, ensure_ascii=False)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"示例配置已保存到: {output_path}")

        return content


def main():
    parser = argparse.ArgumentParser(
        description="Jetson Nano Camera RTSP Server - 支持外部相机和分辨率缩放",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
相机源类型:
  usb   - USB 摄像头 (通过 V4L2)
  csi   - CSI 相机 (Jetson 原生接口)
  rtsp  - RTSP 视频源 (IP 摄像头)
  test  - 测试模式 (使用测试图案)

示例:
  # USB 摄像头，输出 1920x1080
  python3 camera_rtsp_server.py --source usb --device /dev/video0

  # USB 摄像头，从 640x480 放大到 1920x1080
  python3 camera_rtsp_server.py --source usb --device /dev/video0 \\
      --input-width 640 --input-height 480 \\
      --output-width 1920 --output-height 1080

  # CSI 相机
  python3 camera_rtsp_server.py --source csi

  # RTSP 源 (IP 摄像头, H.264 输入)
  python3 camera_rtsp_server.py --source rtsp --url rtsp://192.168.1.100:554/stream

  # RTSP 源 (IP 摄像头, H.265 输入)
  python3 camera_rtsp_server.py --source rtsp --url rtsp://192.168.1.100:554/stream \\
      --input-codec h265

  # 测试模式
  python3 camera_rtsp_server.py --source test

  # 自定义分辨率和编码
  python3 camera_rtsp_server.py --source usb --device /dev/video0 \\
      --output-width 1024 --output-height 1024 \\
      --codec h264 --bitrate 8000

播放:
  vlc rtsp://192.168.1.2:8554/stream
  ffplay rtsp://192.168.1.2:8554/stream

多路相机模式:
  # 生成示例配置文件
  python3 camera_rtsp_server.py --generate-config multi_camera.json

  # 使用配置文件启动多路服务器
  python3 camera_rtsp_server.py --config multi_camera.json
        """
    )

    # 查询功能
    parser.add_argument("--list-formats", "-l", action="store_true",
                        help="列出摄像头支持的格式和分辨率")
    parser.add_argument("--list-cameras", action="store_true",
                        help="列出系统中所有可用的摄像头设备")

    # 多路相机模式
    parser.add_argument("--config", type=str, default=None,
                        help="多路相机配置文件路径 (JSON)")
    parser.add_argument("--generate-config", type=str, metavar="FILE",
                        help="生成示例配置文件")

    parser.add_argument("--source", "-s", choices=["usb", "csi", "rtsp", "test"],
                        default="usb", help="相机源类型 (默认: usb)")
    parser.add_argument("--device", "-d", default="/dev/video0",
                        help="USB 相机设备路径 (默认: /dev/video0)")
    parser.add_argument("--url", "-u", default=None,
                        help="RTSP 源地址 (用于 rtsp 类型)")
    parser.add_argument("--input-codec", choices=["h264", "h265"], default="h264",
                        help="RTSP 源输入编码格式 (默认: h264)")

    parser.add_argument("--port", "-p", type=int, default=8554,
                        help="RTSP 端口号 (默认: 8554)")
    parser.add_argument("--mount", "-m", default="/stream",
                        help="RTSP 挂载点 (默认: /stream)")

    parser.add_argument("--codec", "-c", choices=["h264", "h265"], default="h265",
                        help="输出编码格式 (默认: h265)")
    parser.add_argument("--bitrate", "-b", type=int, default=4000,
                        help="编码比特率 kbps (默认: 4000)")

    parser.add_argument("--input-width", type=int, default=None,
                        help="输入分辨率宽度 (默认: 自动)")
    parser.add_argument("--input-height", type=int, default=None,
                        help="输入分辨率高度 (默认: 自动)")
    parser.add_argument("--output-width", type=int, default=1920,
                        help="输出分辨率宽度 (默认: 1920)")
    parser.add_argument("--output-height", type=int, default=1080,
                        help="输出分辨率高度 (默认: 1080)")

    parser.add_argument("--framerate", "-f", type=int, default=30,
                        help="帧率 (默认: 30)")
    parser.add_argument("--flip", type=int, default=0, choices=range(8),
                        help="图像翻转方式 0-7 (仅 CSI 相机, 默认: 0)")

    args = parser.parse_args()

    # 处理查询命令
    if args.list_cameras:
        print("扫描系统摄像头设备...")
        print("=" * 60)
        cameras = list_all_cameras()
        if cameras:
            print(f"找到 {len(cameras)} 个摄像头设备:\n")
            for device, name in cameras:
                print(f"  {device}: {name}")
            print("\n使用 --list-formats -d <设备> 查看支持的格式")
        else:
            print("未找到摄像头设备")
        sys.exit(0)

    if args.list_formats:
        success = list_camera_formats(args.device)
        sys.exit(0 if success else 1)

    # 生成示例配置文件
    if args.generate_config:
        MultiCameraRTSPServer.generate_sample_config(args.generate_config)
        sys.exit(0)

    # 多路相机模式
    if args.config:
        try:
            server = MultiCameraRTSPServer.from_config_file(args.config)
            server.start()
        except FileNotFoundError:
            print(f"错误: 配置文件不存在: {args.config}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"错误: 配置文件格式错误: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    # 单路相机模式
    try:
        server = CameraRTSPServer(
            source_type=args.source,
            device=args.device,
            rtsp_url=args.url,
            port=args.port,
            mount_point=args.mount,
            codec=args.codec,
            input_codec=args.input_codec,
            bitrate=args.bitrate * 1000,
            input_width=args.input_width,
            input_height=args.input_height,
            output_width=args.output_width,
            output_height=args.output_height,
            framerate=args.framerate,
            flip_method=args.flip
        )
        server.start()
    except ValueError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
