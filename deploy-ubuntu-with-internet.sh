#!/bin/bash
# 科研成果管理系统 - Ubuntu 服务器部署脚本
# 支持内网 + Cloudflare Tunnel 外网访问
# 生成时间：2026-06-24

set -e

echo "🚀 开始部署科研成果管理系统（Ubuntu + 外网访问）"
echo "================================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为 root 用户
if [ "$EUID" -eq 0 ]; then
   echo -e "${RED}❌ 请不要使用 root 用户运行此脚本${NC}"
   echo "请使用普通用户，脚本会在需要时自动请求 sudo 权限"
   exit 1
fi

# 步骤 1：系统环境检查
echo -e "${YELLOW}📋 步骤 1/7：检查系统环境${NC}"
echo "系统信息："
uname -a
echo ""
echo "CPU 核心数："
nproc
echo ""
echo "内存信息："
free -h
echo ""
echo "硬盘空间："
df -h | grep -E "/$|/home"
echo ""
echo "内网 IP 地址："
hostname -I | awk '{print $1}'
INTERNAL_IP=$(hostname -I | awk '{print $1}')
echo ""

read -p "按 Enter 继续..."

# 步骤 2：安装 Docker
echo -e "${YELLOW}📦 步骤 2/7：安装 Docker${NC}"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✅ Docker 已安装${NC}"
    docker --version
else
    echo "正在安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo -e "${GREEN}✅ Docker 安装完成${NC}"
    echo -e "${YELLOW}⚠️  需要重新登录以使 Docker 权限生效${NC}"
    echo "请运行：newgrp docker"
fi
echo ""

if command -v docker-compose &> /dev/null; then
    echo -e "${GREEN}✅ Docker Compose 已安装${NC}"
    docker-compose --version
else
    echo "正在安装 Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}✅ Docker Compose 安装完成${NC}"
fi
echo ""

read -p "按 Enter 继续..."

# 步骤 3：创建项目目录和数据目录
echo -e "${YELLOW}📁 步骤 3/7：创建必要目录${NC}"
mkdir -p data/local
mkdir -p ssl
echo -e "${GREEN}✅ 目录创建完成${NC}"
echo ""

# 步骤 4：创建 Docker 配置文件
echo -e "${YELLOW}📝 步骤 4/7：生成 Docker 配置文件${NC}"

# 创建 Dockerfile
cat > Dockerfile << 'DOCKERFILE_EOF'
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装 curl（用于健康检查）
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml ./
COPY src/ ./src/

# 安装依赖
RUN pip install --no-cache-dir -e . && \
    pip install openpyxl requests PyJWT

# 创建非 root 用户（安全加固）
RUN useradd -m -u 1000 litman && \
    chown -R litman:litman /app

USER litman

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/ || exit 1

# 启动命令
CMD ["litman", "--data-dir", "/data", "web", "serve", "--host", "0.0.0.0", "--port", "8080", "--auth-file", "/data/web_auth.json"]
DOCKERFILE_EOF

echo -e "${GREEN}✅ Dockerfile 创建完成${NC}"

# 创建 docker-compose.yml
cat > docker-compose.yml << 'COMPOSE_EOF'
version: '3.8'

services:
  app:
    build: .
    container_name: research-manager
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./data/local:/data
    environment:
      - TZ=Asia/Shanghai
      - PYTHONUNBUFFERED=1
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
COMPOSE_EOF

echo -e "${GREEN}✅ docker-compose.yml 创建完成${NC}"

# 创建 .dockerignore
cat > .dockerignore << 'DOCKERIGNORE_EOF'
.git
.gitignore
__pycache__
*.pyc
*.pyo
*.pyd
.Python
data/local/*
!data/local/.gitkeep
tmp/
docs/
tests/
*.md
.vscode
.idea
.DS_Store
*.log
deploy-*.sh
nginx.conf
ssl/
DOCKERIGNORE_EOF

echo -e "${GREEN}✅ .dockerignore 创建完成${NC}"
echo ""

read -p "按 Enter 继续..."

# 步骤 5：构建并启动服务
echo -e "${YELLOW}🔧 步骤 5/7：构建并启动服务${NC}"
echo "正在构建 Docker 镜像..."
docker-compose build

echo "正在启动服务..."
docker-compose up -d

echo "等待服务就绪（最多等待 30 秒）..."
for i in {1..30}; do
    if curl -f http://localhost:8080 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 服务启动成功！${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ 服务启动超时${NC}"
        echo "查看日志："
        docker-compose logs app
        exit 1
    fi
    sleep 1
done
echo ""

# 步骤 6：配置 Cloudflare Tunnel（外网访问）
echo -e "${YELLOW}🌐 步骤 6/7：配置外网访问（Cloudflare Tunnel）${NC}"
echo ""
echo "Cloudflare Tunnel 可以让您通过域名从外网访问系统，完全免费且自动 HTTPS。"
echo ""
read -p "是否现在配置 Cloudflare Tunnel？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 安装 cloudflared
    if command -v cloudflared &> /dev/null; then
        echo -e "${GREEN}✅ cloudflared 已安装${NC}"
    else
        echo "正在安装 cloudflared..."
        curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
        chmod +x cloudflared
        sudo mv cloudflared /usr/local/bin/
        echo -e "${GREEN}✅ cloudflared 安装完成${NC}"
    fi
    echo ""

    echo "请按照以下步骤配置 Cloudflare Tunnel："
    echo ""
    echo "1️⃣ 登录 Cloudflare（会打开浏览器）"
    echo "   运行：cloudflared tunnel login"
    echo ""
    echo "2️⃣ 创建隧道"
    echo "   运行：cloudflared tunnel create research-manager"
    echo ""
    echo "3️⃣ 创建配置文件"
    echo "   运行以下命令（替换 <tunnel-id> 和域名）："
    echo ""
    echo "   mkdir -p ~/.cloudflared"
    echo "   cat > ~/.cloudflared/config.yml << EOF"
    echo "   tunnel: <tunnel-id>"
    echo "   credentials-file: /home/$USER/.cloudflared/<tunnel-id>.json"
    echo "   "
    echo "   ingress:"
    echo "     - hostname: research.your-domain.com"
    echo "       service: http://localhost:8080"
    echo "     - service: http_status:404"
    echo "   EOF"
    echo ""
    echo "4️⃣ 配置 DNS（在 Cloudflare 控制台）"
    echo "   运行：cloudflared tunnel route dns research-manager research.your-domain.com"
    echo ""
    echo "5️⃣ 启动隧道"
    echo "   运行：cloudflared tunnel run research-manager"
    echo ""
    echo "6️⃣ 设置开机自启（可选）"
    echo "   运行：sudo cloudflared service install"
    echo ""
    echo -e "${YELLOW}详细教程已保存到 docs/cloudflare-tunnel-setup.md${NC}"

    # 创建详细教程文档
    mkdir -p docs
    cat > docs/cloudflare-tunnel-setup.md << 'TUTORIAL_EOF'
# Cloudflare Tunnel 配置教程

## 前提条件
- 拥有一个域名（可以在 Cloudflare 免费托管）
- 域名的 DNS 已托管在 Cloudflare

## 步骤 1：安装 cloudflared

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

## 步骤 2：登录 Cloudflare

```bash
cloudflared tunnel login
```

这会打开浏览器，选择您的域名并授权。

## 步骤 3：创建隧道

```bash
cloudflared tunnel create research-manager
```

记录返回的 Tunnel ID，例如：`a1b2c3d4-e5f6-7890-abcd-ef1234567890`

## 步骤 4：创建配置文件

```bash
mkdir -p ~/.cloudflared

cat > ~/.cloudflared/config.yml << EOF
tunnel: a1b2c3d4-e5f6-7890-abcd-ef1234567890
credentials-file: /home/$(whoami)/.cloudflared/a1b2c3d4-e5f6-7890-abcd-ef1234567890.json

ingress:
  - hostname: research.your-domain.com
    service: http://localhost:8080
  - service: http_status:404
EOF
```

**注意：**
- 替换 `a1b2c3d4-e5f6-7890-abcd-ef1234567890` 为实际的 Tunnel ID
- 替换 `research.your-domain.com` 为您的域名

## 步骤 5：配置 DNS

```bash
cloudflared tunnel route dns research-manager research.your-domain.com
```

## 步骤 6：测试隧道

```bash
cloudflared tunnel run research-manager
```

打开浏览器访问 `https://research.your-domain.com`，应该能看到登录页面。

## 步骤 7：设置开机自启

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

## 查看状态

```bash
sudo systemctl status cloudflared
```

## 查看日志

```bash
sudo journalctl -u cloudflared -f
```

## 停止服务

```bash
sudo systemctl stop cloudflared
```

## 重启服务

```bash
sudo systemctl restart cloudflared
```

## 常见问题

### Q1：域名必须在 Cloudflare 吗？
A：是的，域名的 DNS 必须托管在 Cloudflare。免费账号即可。

### Q2：需要备案吗？
A：如果是国内域名，需要备案。如果是国外域名（如 .com .net），不需要备案。

### Q3：访问速度如何？
A：Cloudflare 在全球有 CDN 节点，访问速度一般较好。但不如直接访问内网快。

### Q4：是否安全？
A：是的。流量通过 Cloudflare 的加密隧道传输，且自动启用 HTTPS。

### Q5：完全免费吗？
A：是的，Cloudflare Tunnel 对个人用户完全免费。
TUTORIAL_EOF

    echo -e "${GREEN}✅ Cloudflare Tunnel 安装完成${NC}"
    echo -e "${YELLOW}请按照 docs/cloudflare-tunnel-setup.md 中的步骤配置${NC}"
else
    echo "跳过 Cloudflare Tunnel 配置"
    echo "您仍然可以通过内网 IP 访问系统"
fi
echo ""

read -p "按 Enter 继续..."

# 步骤 7：安全配置和后续步骤
echo -e "${YELLOW}🔒 步骤 7/7：安全配置${NC}"
echo ""
echo "📊 部署完成！"
echo "================================================"
echo ""
echo -e "${GREEN}✅ 服务已成功启动${NC}"
echo ""
echo "📍 访问方式："
echo "   内网访问：http://$INTERNAL_IP:8080"
echo "   外网访问：配置 Cloudflare Tunnel 后通过域名访问"
echo ""
echo "🔐 默认账号："
echo "   用户名：admin"
echo "   密码：ChangeMe123"
echo ""
echo -e "${RED}⚠️  重要：请立即登录并修改默认密码！${NC}"
echo ""
echo "📝 常用命令："
echo "   查看状态：docker-compose ps"
echo "   查看日志：docker-compose logs -f app"
echo "   停止服务：docker-compose down"
echo "   重启服务：docker-compose restart"
echo "   更新代码：git pull && docker-compose up -d --build"
echo ""
echo "📚 文档位置："
echo "   部署计划：docs/plans/deploy-local-server-2026-06-24.md"
echo "   Cloudflare 教程：docs/cloudflare-tunnel-setup.md"
echo ""

# 创建日常管理脚本
cat > manage.sh << 'MANAGE_EOF'
#!/bin/bash
# 科研成果管理系统 - 日常管理脚本

case "$1" in
  start)
    echo "启动服务..."
    docker-compose up -d
    echo "✅ 服务已启动"
    ;;
  stop)
    echo "停止服务..."
    docker-compose down
    echo "✅ 服务已停止"
    ;;
  restart)
    echo "重启服务..."
    docker-compose restart
    echo "✅ 服务已重启"
    ;;
  status)
    docker-compose ps
    ;;
  logs)
    docker-compose logs -f app
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
  update)
    echo "更新服务..."
    git pull
    docker-compose up -d --build
    echo "✅ 更新完成"
    ;;
  *)
    echo "科研成果管理系统 - 管理脚本"
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
    echo "  update   - 更新并重启服务"
    exit 1
    ;;
esac
MANAGE_EOF

chmod +x manage.sh
echo -e "${GREEN}✅ 管理脚本已创建：./manage.sh${NC}"
echo ""

# 创建自动备份的 cron 任务（可选）
echo "是否配置每天自动备份？(每天凌晨 2 点执行)"
read -p "(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    CRON_CMD="0 2 * * * cd $(pwd) && ./manage.sh backup >> /tmp/research-manager-backup.log 2>&1"
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo -e "${GREEN}✅ 自动备份已配置（每天凌晨 2 点）${NC}"
    echo "查看 cron 任务：crontab -l"
else
    echo "跳过自动备份配置"
fi
echo ""

echo "🎉 全部完成！"
echo ""
echo "下一步："
echo "1. 在浏览器访问 http://$INTERNAL_IP:8080"
echo "2. 使用 admin / ChangeMe123 登录"
echo "3. 立即修改默认密码"
echo "4. 如需外网访问，配置 Cloudflare Tunnel（见 docs/cloudflare-tunnel-setup.md）"
echo ""
