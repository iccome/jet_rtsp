#!/usr/bin/env python3
"""
Jetson Nano RTSP Server
使用 GStreamer RTSP Server 推送视频文件，支持 H.265 硬件加速编码
"""

import sys
import argparse
import os
import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib


class RTSPServer:
    def __init__(self, video_file: str, port: int = 8554, mount_point: str = "/stream",
                 codec: str = "h265", bitrate: int = 4000000, loop: bool = True):
        """
        初始化 RTSP 服务器

        Args:
            video_file: 视频文件路径
            port: RTSP 端口号
            mount_point: RTSP 挂载点
            codec: 编码格式 (h264 或 h265)
            bitrate: 编码比特率 (bps)
            loop: 是否循环播放
        """
        self.video_file = os.path.abspath(video_file)
        self.port = port
        self.mount_point = mount_point
        self.codec = codec
        self.bitrate = bitrate
        self.loop = loop

        if not os.path.exists(self.video_file):
            raise FileNotFoundError(f"视频文件不存在: {self.video_file}")

        Gst.init(None)

    def _build_pipeline(self) -> str:
        """构建 GStreamer pipeline 字符串 - H.265 透传模式"""

        # H.265 输入直接透传，无需重新编码
        pipeline = (
            f"( filesrc location=\"{self.video_file}\" ! "
            f"qtdemux ! h265parse ! "
            f"rtph265pay name=pay0 pt=96 config-interval=1 )"
        )

        return pipeline

    def _build_loop_pipeline(self) -> str:
        """构建支持循环播放的 GStreamer pipeline 字符串"""

        # H.265 输入循环播放，透传模式
        pipeline = (
            f"( multifilesrc location=\"{self.video_file}\" loop=true ! "
            f"qtdemux ! h265parse ! "
            f"rtph265pay name=pay0 pt=96 config-interval=1 )"
        )

        return pipeline

    def start(self):
        """启动 RTSP 服务器"""

        server = GstRtspServer.RTSPServer()
        server.set_service(str(self.port))

        factory = GstRtspServer.RTSPMediaFactory()

        if self.loop:
            pipeline = self._build_loop_pipeline()
        else:
            pipeline = self._build_pipeline()

        print(f"Pipeline: {pipeline}")
        factory.set_launch(pipeline)
        factory.set_shared(True)

        mounts = server.get_mount_points()
        mounts.add_factory(self.mount_point, factory)

        server.attach(None)

        # 获取所有网卡 IP
        ips = self._get_all_ips()

        print("=" * 50)
        print(f"RTSP 服务器已启动")
        print(f"视频文件: {self.video_file}")
        print(f"编码格式: {self.codec.upper()}")
        print(f"比特率: {self.bitrate // 1000} kbps")
        print(f"循环播放: {'是' if self.loop else '否'}")
        print("=" * 50)
        print("RTSP 地址:")
        for iface, ip in ips:
            print(f"  [{iface}] rtsp://{ip}:{self.port}{self.mount_point}")
        print("=" * 50)
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
            # 获取所有网络接口
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
        description="Jetson Nano RTSP Server - 使用硬件加速编码推送视频文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认设置 (H.265, 端口 8554)
  python3 rtsp_server.py video.mp4

  # 使用 H.264 编码
  python3 rtsp_server.py video.mp4 --codec h264

  # 指定端口和比特率
  python3 rtsp_server.py video.mp4 --port 8555 --bitrate 8000

  # 不循环播放
  python3 rtsp_server.py video.mp4 --no-loop

播放:
  # VLC
  vlc rtsp://<jetson-ip>:8554/stream

  # FFplay
  ffplay rtsp://<jetson-ip>:8554/stream

  # GStreamer
  gst-launch-1.0 rtspsrc location=rtsp://<jetson-ip>:8554/stream ! decodebin ! autovideosink
        """
    )

    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--port", "-p", type=int, default=8554,
                        help="RTSP 端口号 (默认: 8554)")
    parser.add_argument("--mount", "-m", default="/stream",
                        help="RTSP 挂载点 (默认: /stream)")
    parser.add_argument("--codec", "-c", choices=["h264", "h265"], default="h265",
                        help="编码格式 (默认: h265)")
    parser.add_argument("--bitrate", "-b", type=int, default=4000,
                        help="编码比特率 kbps (默认: 4000)")
    parser.add_argument("--no-loop", action="store_true",
                        help="不循环播放视频")

    args = parser.parse_args()

    try:
        server = RTSPServer(
            video_file=args.video,
            port=args.port,
            mount_point=args.mount,
            codec=args.codec,
            bitrate=args.bitrate * 1000,  # 转换为 bps
            loop=not args.no_loop
        )
        server.start()
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
