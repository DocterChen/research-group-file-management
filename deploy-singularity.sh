#!/bin/bash
# 科研成果管理软件 - Singularity 部署脚本
# 适用于 Ubuntu 20.04+ 服务器
# 生成时间：2026-06-24

set -e

echo "🚀 开始部署科研成果管理软件（Singularity 版本）"
echo "================================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 步骤 1：系统环境检查
echo -e "${YELLOW}📋 步骤 1/6：检查系统环境${NC}"
echo "系统信息："
uname -a
echo ""
echo "内存信息："
free -h
echo ""
echo "硬盘空间："
df -h | grep -E "/$|/home"
echo ""

INTERNAL_IP=$(hostname -I | awk '{print $1}')
echo "内网 IP 地址：$INTERNAL_IP"
echo ""

read -p "按 Enter 继续..."

# 步骤 2：安装 Singularity/Apptainer
echo -e "${YELLOW}📦 步骤 2/6：安装 Singularity (Apptainer)${NC}"

if command -v singularity &> /dev/null; then
    echo -e "${GREEN}✅ Singularity 已安装${NC}"
    singularity --version
elif command -v apptainer &> /dev/null; then
    echo -e "${GREEN}✅ Apptainer 已安装${NC}"
    apptainer --version
    # 创建 singularity 别名
    sudo ln -sf $(which apptainer) /usr/local/bin/singularity
else
    echo "正在安装 Apptainer（Singularity 的新名字）..."

    # 添加 Apptainer PPA（使用清华镜像加速）
    sudo apt-get update
    sudo apt-get install -y software-properties-common

    # 安装依赖
    sudo apt-get install -y \
        build-essential \
        libssl-dev \
        uuid-dev \
        libgpgme-dev \
        squashfs-tools \
        libseccomp-dev \
        wget \
        pkg-config \
        git \
        cryptsetup-bin

    # 下载并安装 Apptainer
    APPTAINER_VERSION=1.3.1
    cd /tmp
    wget https://github.com/apptainer/apptainer/releases/download/v${APPTAINER_VERSION}/apptainer_${APPTAINER_VERSION}_amd64.deb
    sudo dpkg -i apptainer_${APPTAINER_VERSION}_amd64.deb
    sudo apt-get install -f

    # 创建 singularity 别名（兼容性）
    sudo ln -sf /usr/bin/apptainer /usr/local/bin/singularity

    echo -e "${GREEN}✅ Apptainer 安装完成${NC}"
    singularity --version
fi
echo ""

read -p "按 Enter 继续..."

# 步骤 3：创建必要目录
echo -e "${YELLOW}📁 步骤 3/6：创建必要目录${NC}"
mkdir -p data/local
mkdir -p singularity
mkdir -p logs
echo -e "${GREEN}✅ 目录创建完成${NC}"
echo ""

# 步骤 4：创建 Singularity 定义文件
echo -e "${YELLOW}📝 步骤 4/6：生成 Singularity 定义文件${NC}"

cat > singularity/research-manager.def << 'SINGULARITY_DEF_EOF'
Bootstrap: docker
From: python:3.11-slim

%files
    pyproject.toml /app/
    src /app/src

%post
    # 设置时区
    export DEBIAN_FRONTEND=noninteractive
    ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

    # 安装依赖
    apt-get update
    apt-get install -y curl
    rm -rf /var/lib/apt/lists/*

    # 安装 Python 包（使用清华镜像加速）
    cd /app
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
    pip install --no-cache-dir -e .
    pip install openpyxl requests PyJWT

    # 创建数据目录
    mkdir -p /data

%environment
    export LC_ALL=C.UTF-8
    export LANG=C.UTF-8
    export PYTHONUNBUFFERED=1

%runscript
    exec litman --data-dir /data web serve --host 0.0.0.0 --port 8080 --auth-file /data/web_auth.json

%labels
    Author Research Group
    Version 1.0
    Description 科研成果管理软件

%help
    这是科研成果管理软件的 Singularity 容器

    使用方法：
    singularity run --bind ./data/local:/data research-manager.sif

    更多信息：
    https://github.com/your-org/research-group-file-management
SINGULARITY_DEF_EOF

echo -e "${GREEN}✅ Singularity 定义文件创建完成${NC}"
echo ""

read -p "按 Enter 继续..."

# 步骤 5：构建 Singularity 镜像
echo -e "${YELLOW}🔧 步骤 5/6：构建 Singularity 镜像${NC}"
echo "这可能需要 5-10 分钟，请耐心等待..."
echo ""

# 检查是否需要 sudo（Apptainer 3.0+ 不需要）
if singularity --version | grep -q "apptainer"; then
    # 使用 Apptainer（不需要 sudo）
    singularity build singularity/research-manager.sif singularity/research-manager.def
else
    # 旧版 Singularity（需要 sudo）
    sudo singularity build singularity/research-manager.sif singularity/research-manager.def
fi

if [ -f singularity/research-manager.sif ]; then
    echo -e "${GREEN}✅ 镜像构建完成${NC}"
    ls -lh singularity/research-manager.sif
else
    echo -e "${RED}❌ 镜像构建失败${NC}"
    exit 1
fi
echo ""

read -p "按 Enter 继续..."

# 步骤 6：启动服务
echo -e "${YELLOW}🔧 步骤 6/6：启动服务${NC}"

# 创建启动脚本
cat > start-service.sh << 'START_SCRIPT_EOF'
#!/bin/bash
# 科研成果管理软件启动脚本

# 检查是否已在运行
if [ -f singularity.pid ]; then
    PID=$(cat singularity.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "服务已在运行 (PID: $PID)"
        exit 0
    fi
fi

# 启动服务
echo "正在启动服务..."
singularity run \
    --bind ./data/local:/data \
    --bind ./logs:/logs \
    singularity/research-manager.sif \
    > logs/service.log 2>&1 &

# 保存 PID
echo $! > singularity.pid

echo "✅ 服务已启动 (PID: $!)"
echo "访问地址：http://$(hostname -I | awk '{print $1}'):8080"
echo "查看日志：tail -f logs/service.log"
START_SCRIPT_EOF

chmod +x start-service.sh

# 创建停止脚本
cat > stop-service.sh << 'STOP_SCRIPT_EOF'
#!/bin/bash
# 科研成果管理软件停止脚本

if [ ! -f singularity.pid ]; then
    echo "服务未运行"
    exit 0
fi

PID=$(cat singularity.pid)
if ps -p $PID > /dev/null 2>&1; then
    echo "正在停止服务 (PID: $PID)..."
    kill $PID
    sleep 2

    # 强制杀死（如果还在运行）
    if ps -p $PID > /dev/null 2>&1; then
        kill -9 $PID
    fi

    rm singularity.pid
    echo "✅ 服务已停止"
else
    echo "服务进程不存在"
    rm singularity.pid
fi
STOP_SCRIPT_EOF

chmod +x stop-service.sh

# 创建重启脚本
cat > restart-service.sh << 'RESTART_SCRIPT_EOF'
#!/bin/bash
# 科研成果管理软件重启脚本

./stop-service.sh
sleep 2
./start-service.sh
RESTART_SCRIPT_EOF

chmod +x restart-service.sh

# 创建管理脚本
cat > manage.sh << 'MANAGE_SCRIPT_EOF'
#!/bin/bash
# 科研成果管理软件管理脚本

case "$1" in
    start)
        ./start-service.sh
        ;;
    stop)
        ./stop-service.sh
        ;;
    restart)
        ./restart-service.sh
        ;;
    status)
        if [ -f singularity.pid ]; then
            PID=$(cat singularity.pid)
            if ps -p $PID > /dev/null 2>&1; then
                echo "✅ 服务运行中 (PID: $PID)"
                echo "内存使用："
                ps -p $PID -o rss= | awk '{printf "%.2f MB\n", $1/1024}'
            else
                echo "❌ 服务已停止"
            fi
        else
            echo "❌ 服务未运行"
        fi
        ;;
    logs)
        tail -f logs/service.log
        ;;
    backup)
        BACKUP_DIR="backups"
        mkdir -p $BACKUP_DIR
        DATE=$(date +%Y%m%d-%H%M%S)
        echo "创建备份..."
        tar -czf $BACKUP_DIR/data-$DATE.tar.gz data/local/
        echo "✅ 备份完成：$BACKUP_DIR/data-$DATE.tar.gz"
        # 保留最近 7 天的备份
        find $BACKUP_DIR -name "data-*.tar.gz" -mtime +7 -delete
        ;;
    shell)
        singularity shell \
            --bind ./data/local:/data \
            singularity/research-manager.sif
        ;;
    *)
        echo "科研成果管理软件 - 管理脚本"
        echo ""
        echo "用法：./manage.sh [命令]"
        echo ""
        echo "命令："
        echo "  start    - 启动服务"
        echo "  stop     - 停止服务"
        echo "  restart  - 重启服务"
        echo "  status   - 查看状态"
        echo "  logs     - 查看日志"
        echo "  backup   - 备份数据"
        echo "  shell    - 进入容器交互式 Shell"
        exit 1
        ;;
esac
MANAGE_SCRIPT_EOF

chmod +x manage.sh

# 启动服务
echo ""
echo "正在启动服务..."
./start-service.sh

# 等待服务启动
echo "等待服务就绪..."
for i in {1..30}; do
    if curl -f http://localhost:8080 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 服务启动成功！${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ 服务启动超时${NC}"
        echo "查看日志："
        tail -n 50 logs/service.log
        exit 1
    fi
    sleep 1
done
echo ""

# 配置 systemd 服务（可选）
echo "是否配置为系统服务（开机自启）？"
read -p "(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo tee /etc/systemd/system/research-manager.service << EOF
[Unit]
Description=Research Group File Management System
After=network.target

[Service]
Type=forking
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/start-service.sh
ExecStop=$(pwd)/stop-service.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable research-manager
    echo -e "${GREEN}✅ 系统服务已配置${NC}"
    echo "管理命令："
    echo "  sudo systemctl start research-manager   - 启动"
    echo "  sudo systemctl stop research-manager    - 停止"
    echo "  sudo systemctl status research-manager  - 状态"
fi
echo ""

# 完成
echo "🎉 部署完成！"
echo "================================================"
echo ""
echo -e "${GREEN}✅ 服务已成功启动${NC}"
echo ""
echo "📍 访问方式："
echo "   内网访问：http://$INTERNAL_IP:8080"
echo ""
echo "🔐 默认账号："
echo "   用户名：admin"
echo "   密码：ChangeMe123"
echo ""
echo -e "${RED}⚠️  重要：请立即登录并修改默认密码！${NC}"
echo ""
echo "📝 管理命令："
echo "   查看状态：./manage.sh status"
echo "   查看日志：./manage.sh logs"
echo "   停止服务：./manage.sh stop"
echo "   重启服务：./manage.sh restart"
echo "   备份数据：./manage.sh backup"
echo "   进入容器：./manage.sh shell"
echo ""
echo "📚 镜像位置："
echo "   singularity/research-manager.sif"
echo ""
