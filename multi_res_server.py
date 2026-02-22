#!/usr/bin/env python3
"""
Jetson 多分辨率 RTSP 服务器
一路摄像头输出多个不同分辨率的 H.265 RTSP 流，每个分辨率使用独立端口
使用 GStreamer tee 元素实现真正的单源多流

优化架构 (相同分辨率共享编码器):
                      +-> nvvidconv (1080p) -> encoder -> tee_0 -> rtph265pay -> udpsink :15000 (stream0)
                      |                                       |-> rtph265pay -> udpsink :15001 (stream1)
                      |                                       +-> rtph265pay -> udpsink :15002 (stream2)
v4l2src -> decode -> tee
                      |
                      +-> nvvidconv (720p) -> encoder -> tee_1 -> rtph265pay -> udpsink :15003 (stream3)
                                                             +-> rtph265pay -> udpsink :15004 (stream4)

优势: 13路输出只需要 4 个编码器 (按分辨率分组)，大幅降低 CPU/NVENC 负载

RTSP Server: udpsrc -> rtph265depay -> rtph265pay -> client
"""

import sys
import os
import argparse
import json
import ctypes

# 抑制 GStreamer CRITICAL 警告 (gst_buffer_resize_range)
os.environ['GST_DEBUG'] = '0'

# 使用 ctypes 抑制 GLib 日志
def _suppress_glib_warnings():
    """抑制 GLib/GStreamer CRITICAL 警告"""
    try:
        # 加载 GLib 库
        libglib = ctypes.CDLL('libglib-2.0.so.0')
        # 设置日志处理器为空函数
        G_LOG_LEVEL_CRITICAL = 1 << 3
        G_LOG_LEVEL_WARNING = 1 << 4
        # g_log_set_handler returns handler_id
        log_func = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)

        def null_handler(domain, level, message, user_data):
            pass

        _null_handler = log_func(null_handler)
        libglib.g_log_set_handler(b"GStreamer", G_LOG_LEVEL_CRITICAL | G_LOG_LEVEL_WARNING, _null_handler, None)
    except Exception:
        pass  # 如果失败，忽略

_suppress_glib_warnings()

import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib


class MultiResolutionRTSPServer:
    """多分辨率 RTSP 服务器 - 真正的单源多流"""

    def __init__(self, config_path: str):
        """
        初始化服务器

        Args:
            config_path: 配置文件路径
        """
        Gst.init(None)

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.camera_config = self.config['camera']
        self.stream_configs = [s for s in self.config['streams'] if s.get('enable', True)]
        self.on_demand = self.config.get('on_demand', False)

        if not self.stream_configs:
            raise ValueError("没有启用任何输出流")

        self.main_pipeline = None
        self.servers = {}  # port -> RTSPServer
        self.loop = None
        self.client_count = 0  # 当前连接的客户端数量
        self.pipeline_str = None  # 缓存的 pipeline 字符串

        # UDP 基础端口（内部使用，用于 pipeline 到 RTSP 的连接）
        self.udp_base_port = 15000

    def _start_pipeline(self):
        """启动主 pipeline"""
        if self.main_pipeline is not None:
            return  # 已经在运行

        print("\n[按需启动] 启动编码 pipeline...")
        try:
            self.main_pipeline = Gst.parse_launch(self.pipeline_str)
            bus = self.main_pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)
            ret = self.main_pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                print("[按需启动] 错误: 无法启动 pipeline")
                self.main_pipeline = None
            else:
                print("[按需启动] Pipeline 已启动")
        except GLib.Error as e:
            print(f"[按需启动] 错误: {e.message}")
            self.main_pipeline = None

    def _stop_pipeline(self):
        """停止主 pipeline"""
        if self.main_pipeline is None:
            return  # 没有在运行

        print("\n[按需启动] 停止编码 pipeline...")
        self.main_pipeline.set_state(Gst.State.NULL)
        self.main_pipeline = None
        print("[按需启动] Pipeline 已停止")

    def _on_client_connected(self, client, media):
        """客户端连接回调"""
        self.client_count += 1
        print(f"\n[客户端] 连接 (当前: {self.client_count})")
        if self.on_demand and self.client_count == 1:
            self._start_pipeline()

    def _on_client_disconnected(self, client):
        """客户端断开回调"""
        self.client_count = max(0, self.client_count - 1)
        print(f"\n[客户端] 断开 (当前: {self.client_count})")
        if self.on_demand and self.client_count == 0:
            # 延迟停止，避免频繁启停
            GLib.timeout_add_seconds(5, self._check_and_stop_pipeline)

    def _check_and_stop_pipeline(self):
        """检查并停止 pipeline（延迟执行）"""
        if self.client_count == 0:
            self._stop_pipeline()
        return False  # 不重复执行

    def _build_main_pipeline(self) -> str:
        """
        构建主 pipeline 字符串 (优化版：相同分辨率共享编码器)

        摄像头 -> 解码 -> tee -> 多个分支 (缩放 -> 编码 -> tee2 -> 多个 UDP)
        """
        cam = self.camera_config
        device = cam.get('device', '/dev/video0')
        input_format = cam.get('input_format', 'mjpeg').lower()
        width = cam.get('input_width', 1920)
        height = cam.get('input_height', 1080)
        framerate = cam.get('framerate', 30)

        # 源和解码
        pipeline = f'v4l2src device="{device}"'

        if input_format == 'mjpeg':
            pipeline += (
                f' ! image/jpeg,width={width},height={height},'
                f'framerate={framerate}/1'
                f' ! nvv4l2decoder mjpeg=1'
            )
        elif input_format == 'h264':
            pipeline += (
                f' ! video/x-h264,width={width},height={height},'
                f'framerate={framerate}/1'
                f' ! h264parse ! nvv4l2decoder'
            )
        elif input_format == 'nv12':
            pipeline += (
                f' ! video/x-raw,format=NV12,width={width},height={height},'
                f'framerate={framerate}/1'
                f' ! nvvidconv ! video/x-raw(memory:NVMM),format=NV12'
            )
        else:
            # YUYV or other raw formats
            pipeline += (
                f' ! video/x-raw,width={width},height={height},'
                f'framerate={framerate}/1'
                f' ! nvvidconv ! video/x-raw(memory:NVMM),format=NV12'
            )

        # 添加主 tee
        pipeline += ' ! tee name=t'

        # 按分辨率分组流配置
        resolution_groups = {}
        for i, stream_config in enumerate(self.stream_configs):
            out_width = stream_config.get('width', 1920)
            out_height = stream_config.get('height', 1080)
            key = (out_width, out_height)
            if key not in resolution_groups:
                resolution_groups[key] = []
            resolution_groups[key].append((i, stream_config))

        # 记录分组信息用于显示
        self.resolution_groups = resolution_groups

        # 为每个分辨率组创建一个编码分支
        for group_idx, ((out_width, out_height), streams) in enumerate(resolution_groups.items()):
            # 使用组内第一个流的比特率
            first_stream = streams[0][1]
            bitrate = first_stream.get('bitrate', 4000) * 1000
            out_framerate = first_stream.get('framerate', cam.get('framerate', 30))

            # 分辨率组的 tee 名称
            tee_name = f'tee_{group_idx}'

            # 编码分支：源 tee -> 缩放 -> 编码 -> 组内 tee
            branch = (
                f' t. ! queue max-size-buffers=10 max-size-time=0 max-size-bytes=0 leaky=downstream'
                f' ! nvvidconv'
                f' ! video/x-raw(memory:NVMM),width={out_width},height={out_height},format=NV12'
                f' ! nvv4l2h265enc bitrate={bitrate} preset-level=1 iframeinterval=10 insert-sps-pps=true maxperf-enable=true'
                f' ! h265parse config-interval=1'
                f' ! tee name={tee_name}'
            )
            pipeline += branch

            # 为组内每个流添加 UDP 输出
            for stream_idx, stream_config in streams:
                udp_port = self.udp_base_port + stream_idx
                udp_branch = (
                    f' {tee_name}. ! queue max-size-buffers=10 max-size-time=0 max-size-bytes=0'
                    f' ! rtph265pay pt=96 config-interval=1 mtu=1400'
                    f' ! udpsink host=127.0.0.1 port={udp_port} sync=false async=false buffer-size=4194304'
                )
                pipeline += udp_branch

        return pipeline

    def _create_rtsp_factory(self, stream_index: int) -> GstRtspServer.RTSPMediaFactory:
        """
        创建 RTSP MediaFactory

        从 UDP 接收已编码的 RTP 流，直接转发给 RTSP 客户端
        """
        udp_port = self.udp_base_port + stream_index

        # 从 UDP 接收 RTP 包，解包后重新打包发送
        pipeline = (
            f'( udpsrc port={udp_port} buffer-size=4194304 caps="application/x-rtp,media=video,'
            f'encoding-name=H265,payload=96,clock-rate=90000"'
            f' ! queue max-size-buffers=10 max-size-time=0 max-size-bytes=0'
            f' ! rtph265depay ! h265parse config-interval=1'
            f' ! rtph265pay name=pay0 pt=96 config-interval=1 mtu=1400 )'
        )

        factory = GstRtspServer.RTSPMediaFactory()
        factory.set_launch(pipeline)
        factory.set_shared(True)

        return factory

    def _on_bus_message(self, bus, message):
        """处理 pipeline 消息"""
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Pipeline 错误: {err.message}")
            print(f"调试信息: {debug}")
            if self.loop:
                self.loop.quit()
        elif t == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            print(f"Pipeline 警告: {err.message}")
        elif t == Gst.MessageType.EOS:
            print("Pipeline 结束")
            if self.loop:
                self.loop.quit()
        return True

    def start(self):
        """启动多分辨率 RTSP 服务器"""
        print("=" * 60)
        print("多分辨率 RTSP 服务器 (单源多流)")
        print("=" * 60)

        # 打印相机配置
        cam = self.camera_config
        print(f"\n相机配置:")
        print(f"  设备: {cam.get('device', '/dev/video0')}")
        print(f"  输入: {cam.get('input_width', 1920)}x{cam.get('input_height', 1080)} "
              f"{cam.get('input_format', 'mjpeg').upper()} @ {cam.get('framerate', 30)}fps")

        # 构建并启动主 pipeline
        pipeline_str = self._build_main_pipeline()
        print(f"\n主 Pipeline:")
        # 打印格式化的 pipeline（每个分支一行）
        parts = pipeline_str.split(' t. !')
        print(f"  {parts[0]}")
        for part in parts[1:]:
            print(f"  t. !{part}")

        try:
            self.main_pipeline = Gst.parse_launch(pipeline_str)
        except GLib.Error as e:
            print(f"\n错误: 无法创建 pipeline: {e.message}")
            sys.exit(1)

        # 设置 bus 消息处理
        bus = self.main_pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        # 启动主 pipeline
        ret = self.main_pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("错误: 无法启动主 pipeline")
            sys.exit(1)

        # 显示优化信息
        print(f"\n编码器优化:")
        print(f"  总流数: {len(self.stream_configs)} 路")
        print(f"  编码器数: {len(self.resolution_groups)} 个 (按分辨率共享)")
        for (w, h), streams in self.resolution_groups.items():
            stream_names = [s[1]['name'] for s in streams]
            print(f"    {w}x{h}: {len(streams)} 路 ({', '.join(stream_names)})")

        print(f"\n输出流 ({len(self.stream_configs)} 路):")

        # 为每个流创建 RTSP 服务器
        for i, stream_config in enumerate(self.stream_configs):
            port = stream_config['port']
            mount = stream_config['mount']
            name = stream_config['name']

            # 每个端口一个 RTSP 服务器
            if port not in self.servers:
                server = GstRtspServer.RTSPServer()
                server.set_service(str(port))
                self.servers[port] = server

            server = self.servers[port]
            mounts = server.get_mount_points()

            # 创建并添加 factory
            factory = self._create_rtsp_factory(i)
            mounts.add_factory(mount, factory)

            out_framerate = stream_config.get('framerate', self.camera_config.get('framerate', 30))
            print(f"\n  [{name}]")
            print(f"    分辨率: {stream_config['width']}x{stream_config['height']} @ {out_framerate}fps")
            print(f"    比特率: {stream_config['bitrate']} kbps")
            print(f"    端口: {port}")
            print(f"    挂载点: {mount}")
            print(f"    内部 UDP: 127.0.0.1:{self.udp_base_port + i}")

        # 启动所有 RTSP 服务器
        for port, server in self.servers.items():
            server.attach(None)

        # 获取所有 IP 地址
        ips = self._get_all_ips()

        print("\n" + "=" * 60)
        print("RTSP 地址:")
        for iface, ip in ips:
            print(f"\n  [{iface}] {ip}")
            for stream_config in self.stream_configs:
                name = stream_config['name']
                port = stream_config['port']
                mount = stream_config['mount']
                print(f"    {name}: rtsp://{ip}:{port}{mount}")

        print("\n" + "=" * 60)
        print("验证命令:")
        for stream_config in self.stream_configs[:3]:  # 只显示前3个
            print(f"  ffprobe rtsp://localhost:{stream_config['port']}{stream_config['mount']}")
        if len(self.stream_configs) > 3:
            print(f"  ...")
        print("=" * 60)
        print("\n按 Ctrl+C 停止服务器")

        # 运行主循环
        self.loop = GLib.MainLoop()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            print("\n正在停止...")
            self.main_pipeline.set_state(Gst.State.NULL)
            print("服务器已停止")

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


def main():
    parser = argparse.ArgumentParser(
        description="Jetson 多分辨率 RTSP 服务器 - 单摄像头多分辨率 H.265 输出",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用配置文件启动
  python3 multi_res_server.py --config multi_res_config.json

配置文件格式:
  {
    "camera": {
      "device": "/dev/video0",
      "input_format": "mjpeg",
      "input_width": 1920,
      "input_height": 1080,
      "framerate": 30
    },
    "streams": [
      {
        "name": "camera0",
        "enable": true,
        "port": 8554,
        "mount": "/stream",
        "width": 1920,
        "height": 1080,
        "bitrate": 8000
      },
      {
        "name": "camera1",
        "enable": true,
        "port": 8555,
        "mount": "/stream",
        "width": 1280,
        "height": 720,
        "framerate": 15,
        "bitrate": 4000
      }
    ]
  }

验证:
  ffprobe rtsp://<ip>:8554/stream
  ffprobe rtsp://<ip>:8555/stream
        """
    )

    parser.add_argument("--config", "-c", type=str, default="multi_res_config.json",
                        help="配置文件路径 (默认: multi_res_config.json)")

    args = parser.parse_args()

    try:
        server = MultiResolutionRTSPServer(args.config)
        server.start()
    except FileNotFoundError:
        print(f"错误: 配置文件不存在: {args.config}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误: 配置文件格式错误: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
