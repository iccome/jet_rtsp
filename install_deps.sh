#!/bin/bash
# Jetson Nano RTSP Server 依赖安装脚本

set -e

echo "=== 安装 RTSP Server 依赖 ==="

# 更新包列表
sudo apt-get update

# 安装 GStreamer RTSP Server 库和 Python GI 绑定
sudo apt-get install -y \
    libgstrtspserver-1.0-0 \
    gstreamer1.0-rtsp \
    gir1.2-gst-rtsp-server-1.0 \
    python3-gi \
    python3-gst-1.0

echo "=== 安装完成 ==="
echo "你可以运行 'python3 rtsp_server.py --help' 查看使用方法"
