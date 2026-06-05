# IT 资产管理系统 — 部署指南

## 服务器要求

- Ubuntu 22.04+ 或其他 Linux 发行版
- Python 3.11+
- 2GB+ 内存
- 网络可达（局域网或公网）

## 快速部署

### 1. 上传代码

将项目上传到服务器，例如 `/opt/it-asset-manager`：

```bash
# 方式一：git clone（如果有远程仓库）
git clone <repo-url> /opt/it-asset-manager

# 方式二：rsync 从开发机同步
rsync -avz --exclude='.venv' --exclude='it_asset.db' --exclude='.secret_key' \
  ./ user@server:/opt/it-asset-manager/
```

### 2. 创建虚拟环境并安装依赖

```bash
cd /opt/it-asset-manager
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
.venv/bin/python init_db.py
```

这会创建 `it_asset.db` 并插入演示数据（admin/admin123、emp001/emp001 等）。**生产环境上线后请立即修改默认密码。**

### 4. 配置 systemd 服务

```bash
# 编辑 service 文件，替换占位符
cp contrib/it-asset-manager.service /tmp/it-asset-manager.service

# 替换以下占位符为实际值：
#   __APP_USER__    → 运行用户，如 itadmin
#   __APP_GROUP__   → 运行用户组，如 itadmin
#   __APP_DIR__     → 项目目录，如 /opt/it-asset-manager
#   __CHANGE_ME__   → 随机密钥，用下面的命令生成：
python3 -c "import secrets; print(secrets.token_hex(32))"

# 替换示例（根据实际情况修改）：
sed -i 's|__APP_USER__|itadmin|g; s|__APP_GROUP__|itadmin|g; s|__APP_DIR__|/opt/it-asset-manager|g; s|__CHANGE_ME__|你的随机密钥|g' /tmp/it-asset-manager.service

# 安装并启用服务
sudo cp /tmp/it-asset-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now it-asset-manager

# 检查状态
sudo systemctl status it-asset-manager
```

### 5. 配置反向代理

#### Caddy（推荐）

```bash
# /etc/caddy/Caddyfile
http://10.18.0.68:9090 {
    reverse_proxy 127.0.0.1:5000
}
```

#### Nginx

```nginx
server {
    listen 9090;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/it-asset-manager/static/;
        expires 7d;
    }
}
```

### 6. 防火墙

```bash
sudo ufw allow 9090/tcp
```

### 7. 验证

```bash
# 健康检查
curl http://127.0.0.1:5000/api/health

# 浏览器访问
# http://<服务器IP>:9090
# 用 admin / admin123 登录
```

## 数据备份

数据库是单个 SQLite 文件，备份很简单：

```bash
# 手动备份（安全方式，不锁库）
sqlite3 /opt/it-asset-manager/it_asset.db ".backup /opt/it-asset-manager/backup/$(date +%Y%m%d).db"

# 建议加到 crontab，每天凌晨备份
# 0 2 * * * sqlite3 /opt/it-asset-manager/it_asset.db ".backup /opt/it-asset-manager/backup/$(date +\%Y\%m\%d).db"
```

备份目录需提前创建：`mkdir -p /opt/it-asset-manager/backup`

## 更新升级

```bash
cd /opt/it-asset-manager

# 1. 备份数据库
sqlite3 it_asset.db ".backup backup/$(date +%Y%m%d).db"

# 2. 更新代码
git pull  # 或 rsync 新版本

# 3. 更新依赖（如有变化）
.venv/bin/pip install -r requirements.txt

# 4. 重启服务（数据库升级会在启动时自动执行）
sudo systemctl restart it-asset-manager

# 5. 验证
sudo systemctl status it-asset-manager
curl http://127.0.0.1:5000/api/health
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECRET_KEY` | Flask 会话密钥，**生产环境必须设置** | 自动生成并保存到 `.secret_key` |
| `DB_PATH` | SQLite 数据库路径 | `it_asset.db`（相对 WorkingDirectory） |
| `FLASK_DEBUG` | 开发调试模式 | 关闭（仅 `python server.py` 启动时生效，gunicorn 下不生效） |

## 上传目录

Logo 等上传文件存储在 `static/uploads/`，确保运行用户有写权限：

```bash
chown -R <运行用户>:<运行用户组> /opt/it-asset-manager/static/uploads/
chmod 755 /opt/it-asset-manager/static/uploads/
```

## 安全提醒

- 上线后立即修改 `admin` 的默认密码
- `SECRET_KEY` 不要使用默认值，建议在 systemd 环境变量中设置固定值
- 确保数据库文件和 `.secret_key` 仅运行用户可读：`chmod 600 it_asset.db .secret_key`
- `.gitignore` 已排除 `*.db`、`.secret_key`、`static/uploads/*`，确保敏感文件不进入版本控制
