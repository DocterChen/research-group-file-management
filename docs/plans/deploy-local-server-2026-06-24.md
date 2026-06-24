# 现有硬件内网部署方案

> **场景：** 利用课题组现有电脑/服务器进行内网部署  
> **优势：** 零成本、数据完全掌控、适合内网访问  
> **制定时间：** 2026-06-24

---

## 📋 部署场景选择

### 场景 1：纯内网访问（推荐 ⭐⭐⭐⭐⭐）

**适用情况：**
- 课题组成员都在同一局域网（办公室、实验室）
- 不需要外网访问
- 数据安全性要求高

**优势：**
- 配置最简单
- 访问速度最快（局域网）
- 最安全（不暴露到公网）
- 完全免费

**架构：**
```
课题组成员电脑（局域网）
    ↓
内网服务器（192.168.x.x:8080）
    ↓
数据存储（本地硬盘）
```

---

### 场景 2：内网 + 外网访问

**适用情况：**
- 课题组成员有时需要在家/出差访问
- 需要外网访问但不想购买云服务器

**方案 2.1：内网穿透（免费）**
- 使用 frp / ngrok / Cloudflare Tunnel
- 优势：完全免费
- 劣势：访问速度较慢，依赖第三方服务

**方案 2.2：动态域名 + 端口映射（需要公网 IP）**
- 使用 DDNS（花生壳、阿里云 DDNS）
- 优势：访问速度快
- 劣势：需要公网 IP（有些宽带没有）

---

## 🔍 硬件需求评估

### 最低配置
- **CPU**：2 核心（近 10 年的任何电脑都满足）
- **内存**：2GB（系统占用 + 应用需要）
- **硬盘**：20GB 空闲空间（系统 + Docker + 数据）
- **网络**：有线网络（WiFi 也行，但有线更稳定）
- **操作系统**：
  - Linux（Ubuntu 20.04+、Debian 11+、CentOS 8+）⭐ 推荐
  - macOS（10.15+）
  - Windows 10/11（需要 WSL2 或 Docker Desktop）

### 推荐配置（更流畅）
- **CPU**：4 核心
- **内存**：4GB+
- **硬盘**：50GB+ SSD（更快）
- **网络**：千兆网卡

### 现有硬件评估

**请确认以下信息：**

1. **设备类型**
   - [ ] 台式机（一直开机）
   - [ ] 笔记本（偶尔开机）
   - [ ] 旧服务器（专用）
   - [ ] 工作站（白天开机）

2. **操作系统**
   - [ ] Linux（哪个发行版？Ubuntu / CentOS / Debian）
   - [ ] macOS（哪个版本？）
   - [ ] Windows（哪个版本？）

3. **网络环境**
   - [ ] 有固定内网 IP（如 192.168.1.100）
   - [ ] DHCP 自动分配 IP（需要配置静态 IP）
   - [ ] 有公网 IP（可以配置外网访问）
   - [ ] 无公网 IP（只能内网或内网穿透）

4. **使用时间**
   - [ ] 24/7 一直开机
   - [ ] 工作日白天开机（8:00-18:00）
   - [ ] 偶尔开机（需要时才开）

---

## 🚀 快速部署方案（纯内网）

### 方案 A：Linux 服务器（推荐）

#### 步骤 1：检查系统环境
```bash
# 查看系统信息
uname -a
cat /etc/os-release

# 查看 CPU 和内存
lscpu | grep "^CPU(s):"
free -h

# 查看硬盘空间
df -h

# 查看 IP 地址
ip addr show | grep "inet "
# 或者
ifconfig | grep "inet "
```

#### 步骤 2：安装 Docker
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker

# CentOS/RHEL
sudo yum install -y docker docker-compose
sudo systemctl enable docker
sudo systemctl start docker

# 验证安装
docker --version
docker-compose --version

# 将当前用户加入 docker 组（避免每次 sudo）
sudo usermod -aG docker $USER
newgrp docker
```

#### 步骤 3：克隆项目（如果已有代码）
```bash
# 如果项目在 Git 仓库
git clone <your-repo-url>
cd research-group-file-management

# 或者直接在本地项目目录操作
cd /path/to/research-group-file-management
```

#### 步骤 4：创建部署文件

参考 [deploy-2026-06-24.md](./deploy-2026-06-24.md) 中的文件：
- Dockerfile
- docker-compose.yml
- nginx.conf（如果需要反向代理）
- .dockerignore

**简化版 docker-compose.yml（仅内网访问）：**
```yaml
version: '3.8'

services:
  app:
    build: .
    container_name: research-manager
    restart: unless-stopped
    ports:
      - "8080:8080"  # 直接暴露 8080 端口到局域网
    volumes:
      - ./data/local:/data
    environment:
      - TZ=Asia/Shanghai
      - PYTHONUNBUFFERED=1
```

#### 步骤 5：启动服务
```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f app

# 查看状态
docker-compose ps
```

#### 步骤 6：获取内网 IP 并访问
```bash
# 获取服务器内网 IP
hostname -I | awk '{print $1}'
# 假设输出：192.168.1.100

# 在同一局域网的其他电脑浏览器访问：
# http://192.168.1.100:8080
```

---

### 方案 B：macOS 电脑

#### 步骤 1：安装 Docker Desktop
```bash
# 下载并安装 Docker Desktop for Mac
# https://www.docker.com/products/docker-desktop/

# 或使用 Homebrew
brew install --cask docker

# 启动 Docker Desktop（从应用程序启动）
```

#### 步骤 2-6：与 Linux 方案相同
```bash
# 后续步骤完全一致
cd /path/to/research-group-file-management
docker-compose build
docker-compose up -d
```

#### 获取 Mac 内网 IP
```bash
# 方式 1：命令行
ipconfig getifaddr en0  # WiFi
ipconfig getifaddr en1  # 有线

# 方式 2：系统偏好设置 → 网络
```

---

### 方案 C：Windows 电脑

#### 步骤 1：安装 Docker Desktop
```powershell
# 下载并安装 Docker Desktop for Windows
# https://www.docker.com/products/docker-desktop/

# 确保启用 WSL2 后端（推荐）
```

#### 步骤 2：在 WSL2 或 PowerShell 中操作
```powershell
# 进入 WSL2（推荐）
wsl

# 或直接在 PowerShell 中操作
cd C:\path\to\research-group-file-management
docker-compose build
docker-compose up -d
```

#### 获取 Windows 内网 IP
```powershell
# PowerShell
ipconfig | Select-String "IPv4"

# 假设输出：192.168.1.100
# 访问：http://192.168.1.100:8080
```

---

## 🌐 外网访问方案（可选）

### 方案 1：frp 内网穿透（推荐，免费）

#### 服务端（需要一台有公网 IP 的服务器，可以用最便宜的云服务器）
```bash
# 下载 frp
wget https://github.com/fatedier/frp/releases/download/v0.52.0/frp_0.52.0_linux_amd64.tar.gz
tar -xzf frp_0.52.0_linux_amd64.tar.gz
cd frp_0.52.0_linux_amd64

# 编辑 frps.ini
cat > frps.ini << EOF
[common]
bind_port = 7000
token = your-secret-token
EOF

# 启动服务端
./frps -c frps.ini
```

#### 客户端（内网服务器）
```bash
# 下载 frp（版本与服务端一致）
wget https://github.com/fatedier/frp/releases/download/v0.52.0/frp_0.52.0_linux_amd64.tar.gz
tar -xzf frp_0.52.0_linux_amd64.tar.gz
cd frp_0.52.0_linux_amd64

# 编辑 frpc.ini
cat > frpc.ini << EOF
[common]
server_addr = your-server-ip
server_port = 7000
token = your-secret-token

[research-manager]
type = http
local_ip = 127.0.0.1
local_port = 8080
custom_domains = your-domain.com
EOF

# 启动客户端
./frpc -c frpc.ini
```

**访问方式：** http://your-domain.com（需要域名解析到服务端 IP）

---

### 方案 2：Cloudflare Tunnel（免费，最简单）

```bash
# 安装 cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/

# 登录 Cloudflare
cloudflared tunnel login

# 创建隧道
cloudflared tunnel create research-manager

# 配置隧道
cat > ~/.cloudflared/config.yml << EOF
tunnel: <tunnel-id>
credentials-file: /home/user/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: research.your-domain.com
    service: http://localhost:8080
  - service: http_status:404
EOF

# 启动隧道
cloudflared tunnel run research-manager
```

**优势：**
- 完全免费
- 自动 HTTPS
- 不需要公网 IP
- 不需要配置防火墙

---

## 🔒 安全加固（内网部署）

### 1. 修改默认密码
```bash
# 首次访问后立即修改 admin 账号密码
# 访问：http://192.168.1.100:8080
# 登录：admin / ChangeMe123
# 进入账号管理 → 修改密码
```

### 2. 配置防火墙（可选）
```bash
# Ubuntu/Debian
sudo ufw allow 8080/tcp
sudo ufw enable

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

### 3. 限制访问 IP（可选）
```nginx
# 在 nginx.conf 中添加
location / {
    allow 192.168.1.0/24;  # 仅允许局域网访问
    deny all;
    proxy_pass http://app:8080;
}
```

---

## 📊 成本对比

| 项目 | 纯内网部署 | 内网 + frp | 内网 + Cloudflare |
|------|-----------|-----------|------------------|
| 硬件成本 | ¥0（利用现有） | ¥0 | ¥0 |
| 服务器成本 | ¥0 | ¥25-50/月（frp 服务端）| ¥0 |
| 域名成本 | ¥0 | ¥50/年（可选） | ¥50/年（可选） |
| **总计/年** | **¥0** | **¥300-600** | **¥50** |

---

## ✅ 推荐方案总结

| 使用场景 | 推荐方案 | 理由 |
|---------|---------|------|
| **仅办公室/实验室内访问** | 纯内网部署 | 零成本、最安全、最快 ⭐⭐⭐⭐⭐ |
| **偶尔需要外网访问** | Cloudflare Tunnel | 免费、安全、零配置 ⭐⭐⭐⭐ |
| **需要自定义域名** | frp + 域名 | 灵活、可控 ⭐⭐⭐ |
| **高安全性要求** | 纯内网 + VPN | 企业级安全 ⭐⭐⭐⭐ |

---

## 🎯 下一步行动

### 立即可执行（10 分钟）

1. **确认硬件信息**
   ```bash
   # 在现有电脑/服务器上运行
   uname -a
   free -h
   df -h
   ip addr show
   ```

2. **告诉我以下信息：**
   - 操作系统类型和版本
   - 内网 IP 地址
   - 是否需要外网访问
   - 设备是否 24/7 开机

3. **我将为您生成定制化的部署脚本**

---

## 📞 常见问题

### Q1：电脑关机后服务会停吗？
**A：** 是的。建议：
- 使用专用服务器/工作站（一直开机）
- 或配置"来电自启动"
- 或设置定时唤醒

### Q2：内网 IP 会变吗？
**A：** DHCP 分配的 IP 可能会变。解决方案：
```bash
# 方案 1：路由器设置 DHCP 静态绑定（推荐）
# 在路由器管理界面，将 MAC 地址绑定到固定 IP

# 方案 2：手动配置静态 IP
# Ubuntu/Debian
sudo vim /etc/netplan/01-netcfg.yaml
```

### Q3：数据会丢失吗？
**A：** 不会。数据存储在 `data/local/` 目录，持久化到硬盘。建议：
- 定期备份（参考原部署计划的备份脚本）
- 使用 UPS 不间断电源（防止突然断电）

### Q4：局域网其他人能访问吗？
**A：** 可以。任何连接到同一局域网的设备都能访问 `http://192.168.1.100:8080`。建议：
- 设置强密码
- 启用角色权限控制
- 必要时配置防火墙限制 IP

---

**需要我根据您的具体情况生成定制化部署脚本吗？请告诉我您的硬件和网络环境！**
