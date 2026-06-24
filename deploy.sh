#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# IT 资产管理系统 — 一键部署脚本
#
# 用法:
#   sudo ./deploy.sh                                              # 默认安装
#   sudo ./deploy.sh --dir /opt/my-app --port 9090                # 自定义路径和端口
#   sudo ./deploy.sh --clone https://github.com/yobai-cc/it-asset-manager.git
# ==================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 默认参数
APP_DIR="/opt/it-asset-manager"
APP_PORT=5000
APP_USER=""
APP_GROUP=""
CLONE_URL=""
SKIP_SYSTEMD=false

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

usage() {
    cat <<'EOF'
IT 资产管理系统 — 一键部署脚本

用法: sudo ./deploy.sh [选项]

选项:
  --dir DIR         安装目录 (默认: /opt/it-asset-manager)
  --port PORT       监听端口 (默认: 5000)
  --user USER       运行用户 (默认: 当前用户)
  --group GROUP     运行用户组 (默认: 当前用户组)
  --clone URL       从 Git 仓库克隆代码 (默认: 从当前目录复制)
  --no-systemd      跳过 systemd 配置，仅安装
  -h, --help        显示帮助信息

示例:
  sudo ./deploy.sh
  sudo ./deploy.sh --dir /opt/it-asset-manager --port 9090
  sudo ./deploy.sh --clone https://github.com/yobai-cc/it-asset-manager.git
EOF
    exit 0
}

# ---- 参数解析 ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)         APP_DIR="$2"; shift 2 ;;
        --port)        APP_PORT="$2"; shift 2 ;;
        --user)        APP_USER="$2"; shift 2 ;;
        --group)       APP_GROUP="$2"; shift 2 ;;
        --clone)       CLONE_URL="$2"; shift 2 ;;
        --no-systemd)  SKIP_SYSTEMD=true; shift ;;
        -h|--help)     usage ;;
        *)             error "未知参数: $1" ;;
    esac
done

# 默认用户为当前 sudo 用户或当前用户
SUDO_USER="${SUDO_USER:-$(whoami)}"
APP_USER="${APP_USER:-$SUDO_USER}"
APP_GROUP="${APP_GROUP:-$APP_USER}"

echo -e "${CYAN}"
echo "============================================"
echo "  IT 资产管理系统 — 一键部署"
echo "============================================"
echo -e "${NC}"
info "安装目录: ${APP_DIR}"
info "监听端口: ${APP_PORT}"
info "运行用户: ${APP_USER}:${APP_GROUP}"
[[ -n "${CLONE_URL}" ]] && info "代码来源: git clone ${CLONE_URL}" || info "代码来源: 本地目录 ${SCRIPT_DIR}"
echo ""

# ---- 1. 前置检查 ----
info "检查系统环境..."

if ! command -v python3 &>/dev/null; then
    error "未找到 python3，请先安装 Python 3.11+"
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
    error "需要 Python 3.11+，当前版本: ${PY_VERSION}"
fi
info "Python ${PY_VERSION} ✓"

if ! python3 -m venv --help &>/dev/null; then
    error "venv 模块不可用，请安装: sudo apt install python3-venv (Debian/Ubuntu)"
fi

if [[ "$SKIP_SYSTEMD" == false ]] && [[ ! -w /etc/systemd/system ]]; then
    error "需要 root 权限配置 systemd，请使用 sudo 运行或加 --no-systemd 跳过"
fi

# ---- 2. 部署代码 ----
info "部署代码到 ${APP_DIR}..."

if [[ -n "${CLONE_URL}" ]]; then
    if [[ -d "${APP_DIR}" ]]; then
        warn "${APP_DIR} 已存在，尝试 git pull 更新..."
        cd "${APP_DIR}"
        git pull || warn "git pull 失败，继续使用现有代码"
    else
        git clone "${CLONE_URL}" "${APP_DIR}"
    fi
else
    if [[ "${SCRIPT_DIR}" == "${APP_DIR}" ]]; then
        info "已在目标目录，跳过复制"
    else
        mkdir -p "${APP_DIR}"
        rsync -a --exclude='.venv' --exclude='*.db' --exclude='.secret_key' \
              --exclude='.git' --exclude='__pycache__' --exclude='.hermes' \
              --exclude='android' \
              "${SCRIPT_DIR}/" "${APP_DIR}/"
        info "代码已复制到 ${APP_DIR}"
    fi
fi

cd "${APP_DIR}"

# ---- 3. 虚拟环境与依赖 ----
info "创建虚拟环境并安装依赖..."

if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
fi

.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

info "依赖安装完成 ✓"

# ---- 4. 初始化/升级数据库 ----
if [[ -f "it_asset.db" ]]; then
    info "数据库已存在，执行升级检查..."
    .venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from models import Database
db = Database('it_asset.db')
db.upgrade_db()
print('数据库升级完成')
"
    info "数据库升级完成 ✓"
else
    info "初始化数据库..."
    .venv/bin/python init_db.py
    info "数据库初始化完成（含演示数据）✓"
fi

# ---- 5. 目录权限 ----
info "设置文件权限..."

mkdir -p static/uploads backup
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
chmod 755 static/uploads

# 保护敏感文件
[[ -f it_asset.db ]] && chmod 600 it_asset.db
[[ -f .secret_key ]] && chmod 600 .secret_key

# ---- 6. 配置端口 ----
if [[ "${APP_PORT}" != "5000" ]]; then
    info "配置监听端口: ${APP_PORT}..."
    cat > gunicorn.conf.py <<EOF
bind = "0.0.0.0:${APP_PORT}"
workers = 3
threads = 2
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"
EOF
fi

# ---- 7. 配置 systemd ----
if [[ "${SKIP_SYSTEMD}" == false ]]; then
    info "配置 systemd 服务..."

    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    sed -e "s|__APP_USER__|${APP_USER}|g" \
        -e "s|__APP_GROUP__|${APP_GROUP}|g" \
        -e "s|__APP_DIR__|${APP_DIR}|g" \
        -e "s|__CHANGE_ME__|${SECRET_KEY}|g" \
        contrib/it-asset-manager.service > /etc/systemd/system/it-asset-manager.service

    systemctl daemon-reload
    systemctl enable it-asset-manager

    # 如果服务已在运行则重启
    if systemctl is-active --quiet it-asset-manager 2>/dev/null; then
        systemctl restart it-asset-manager
    else
        systemctl start it-asset-manager
    fi

    sleep 1

    if systemctl is-active --quiet it-asset-manager; then
        info "服务启动成功 ✓"
    else
        error "服务启动失败，请检查: systemctl status it-asset-manager"
    fi
fi

# ---- 8. 完成 ----
echo ""
echo -e "${GREEN}============================================"
echo "  部署完成！"
echo -e "============================================${NC}"
echo ""

# 获取本机 IP
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<服务器IP>")

# 从 gunicorn.conf.py 读取实际监听地址，让访问提示与真实绑定一致
# （默认端口走已提交配置 bind=127.0.0.1；--port 自定义端口时脚本改写为 0.0.0.0）
BIND_HOST=$(grep -E '^bind\s*=' gunicorn.conf.py 2>/dev/null \
            | sed -E 's/.*"([^:]+):.*/\1/' | head -1)
BIND_HOST="${BIND_HOST:-127.0.0.1}"

if [[ "${BIND_HOST}" == "0.0.0.0" ]]; then
    echo -e "  访问地址:  ${CYAN}http://${LOCAL_IP}:${APP_PORT}${NC}"
else
    echo -e "  本机访问:  ${CYAN}http://${BIND_HOST}:${APP_PORT}${NC}  ${YELLOW}（仅监听 ${BIND_HOST}，外部访问请配置反向代理 Caddy/Nginx）${NC}"
fi
echo ""
echo "  演示账号:"
echo "    管理员  admin / admin123"
echo "    员工    emp001 / emp001"
echo ""
echo -e "  ${YELLOW}安全提醒:${NC}"
echo "    1. 上线后请立即修改 admin 默认密码"
echo "    2. 建议配置反向代理 (Caddy/Nginx) 并启用 HTTPS"
echo "    3. 定期备份: sqlite3 ${APP_DIR}/it_asset.db \".backup ${APP_DIR}/backup/\$(date +%Y%m%d).db\""
echo ""

if [[ "${SKIP_SYSTEMD}" == false ]]; then
    echo "  管理命令:"
    echo "    systemctl status it-asset-manager    # 查看状态"
    echo "    systemctl restart it-asset-manager   # 重启服务"
    echo "    journalctl -u it-asset-manager -f    # 查看日志"
    echo ""
fi

# 健康检查
if [[ "${SKIP_SYSTEMD}" == false ]]; then
    info "健康检查..."
    HEALTH=$(curl -sf http://127.0.0.1:${APP_PORT}/api/health 2>/dev/null || echo "")
    if [[ -n "${HEALTH}" ]]; then
        info "健康检查通过 ✓"
    else
        warn "健康检查未通过，服务可能需要几秒启动"
    fi
fi
