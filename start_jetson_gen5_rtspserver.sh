#!/bin/bash
# Jetson Gen5 RTSP Server 启动脚本

#############################################
# 配置变量 - 根据需要修改
#############################################
DEFAULT_VIDEO="/path/to/your/video.mp4"
DEFAULT_PORT="8554"
DEFAULT_CODEC="h265"
DEFAULT_BITRATE="4000"
JETSON_IP="192.168.1.2"
CLIENT_IP="192.168.1.1"

#############################################
# 参数解析
#############################################
VIDEO_FILE=""
PORT="$DEFAULT_PORT"
CODEC="$DEFAULT_CODEC"
BITRATE="$DEFAULT_BITRATE"
NO_LOOP=""

show_help() {
    echo "用法: $0 [选项] <视频文件>"
    echo ""
    echo "选项:"
    echo "  -p, --port <端口>      RTSP 端口 (默认: $DEFAULT_PORT)"
    echo "  -c, --codec <编码>     编码格式 h264/h265 (默认: $DEFAULT_CODEC)"
    echo "  -b, --bitrate <比特率> 比特率 kbps (默认: $DEFAULT_BITRATE)"
    echo "  --no-loop              不循环播放"
    echo "  -h, --help             显示帮助"
    echo ""
    echo "示例:"
    echo "  $0 video.mp4"
    echo "  $0 video.mp4 -p 8555"
    echo "  $0 video.mp4 --port 8555 --codec h264"
    echo "  $0 -p 8555 video.mp4"
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        -c|--codec)
            CODEC="$2"
            shift 2
            ;;
        -b|--bitrate)
            BITRATE="$2"
            shift 2
            ;;
        --no-loop)
            NO_LOOP="--no-loop"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        -*)
            echo "错误: 未知选项 $1"
            show_help
            exit 1
            ;;
        *)
            VIDEO_FILE="$1"
            shift
            ;;
    esac
done

# 如果未指定视频文件，使用默认值
VIDEO_FILE="${VIDEO_FILE:-$DEFAULT_VIDEO}"

#############################################
# 检查和启动
#############################################

# 检查视频文件是否存在
if [ ! -f "$VIDEO_FILE" ]; then
    echo "错误: 视频文件不存在: $VIDEO_FILE"
    echo ""
    show_help
    exit 1
fi

echo "=== 启动 Jetson Gen5 RTSP Server ==="
echo "服务器 IP: $JETSON_IP"
echo "客户端 IP: $CLIENT_IP"
echo "视频文件: $VIDEO_FILE"
echo "端口: $PORT"
echo "编码: $CODEC"
echo "比特率: ${BITRATE} kbps"
echo "循环播放: $([ -z "$NO_LOOP" ] && echo '是' || echo '否')"
echo ""
echo "RTSP 地址: rtsp://${JETSON_IP}:${PORT}/stream"
echo ""
echo "客户端 ($CLIENT_IP) 可使用以下命令播放:"
echo "  ffplay rtsp://${JETSON_IP}:${PORT}/stream"
echo "  vlc rtsp://${JETSON_IP}:${PORT}/stream"
echo ""

# 启动 RTSP 服务器
python3 "$(dirname "$0")/rtsp_server.py" "$VIDEO_FILE" \
    --port "$PORT" \
    --codec "$CODEC" \
    --bitrate "$BITRATE" \
    $NO_LOOP
