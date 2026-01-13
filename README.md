# Binance 交易机器人

基于 Flask 和 Binance API 的自动化交易机器人。

## 环境要求

- Python 3.8 或更高版本

## 快速开始

### 1. 创建虚拟环境

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并填写你的配置：

```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

然后编辑 `.env` 文件，填入你的 API 密钥等信息。

### 4. 运行应用

```bash
python app.py
```

应用将在 `http://0.0.0.0:80` 启动。

## 项目结构

- `app.py` - Flask 应用主文件，包含所有配置、webhook 接口和工具函数
- `init_testnet.py` - 测试网连接测试脚本
- `streamlit_history.py` - Streamlit 交易历史展示页面
- `requirements.txt` - Python 依赖包列表
- `env.example` - 环境变量配置模板

## API 端点

### POST /webhook
接收交易信号并执行交易

**请求体（JSON）：**
```json
{
  "secret": "your_webhook_secret",
  "side": "LONG",
  "entry": 50000.0,
  "stop": 49000.0
}
```

**或者通过 URL 查询参数传递 secret：**
```
POST /webhook?secret=your_webhook_secret
Content-Type: application/json

{
  "side": "LONG",
  "entry": 50000.0,
  "stop": 49000.0
}
```

**TradingView Alert 配置：**
在 TradingView 中配置 webhook URL 时，可以：
1. 在 URL 中添加 secret：`http://your-server/webhook?secret=your_webhook_secret`
2. 或者在 JSON 消息中包含 secret 字段

**响应：**
```json
{
  "status": "ok",
  "qty": 0.001,
  "side": "LONG",
  "order_id": 123456
}
```

### GET /health
健康检查端点，用于监控服务状态

### GET /status
获取机器人状态信息（余额、持仓、配置、交易历史）

**响应示例：**
```json
{
  "status": "ok",
  "mode": "testnet",
  "symbol": "BTCUSDT",
  "balance": {
    "usdt": 1000.0,
    "total_wallet_balance": 1000.0,
    "available_balance": 1000.0
  },
  "position": {
    "quantity": 0.0,
    "side": "NONE"
  },
  "config": {
    "leverage": 3,
    "risk_pct": 0.01,
    "qty_precision": 3
  },
  "recent_trades": [...],
  "trade_history_count": 10
}
```

### GET /history
Flask 内置的交易历史 HTML 页面（简单版本）

### Streamlit 交易历史页面
使用 Streamlit 构建的现代化交易历史展示界面

**运行方式：**
```bash
streamlit run streamlit_history.py
```

**功能特性：**
- 📊 美观的数据表格展示
- 🔍 支持按方向、标的筛选
- 📈 统计信息（总记录数、做多/做空次数等）
- 📥 导出 CSV 功能
- 🔄 自动刷新（可配置刷新间隔）
- 📱 响应式设计，支持移动端
- ⚙️ 侧边栏配置面板

页面会在浏览器中自动打开（通常是 `http://localhost:8501`）

## 环境变量说明

### 必需变量
- `BINANCE_MODE`: 运行模式，`testnet` 或 `main`
- `BINANCE_TEST_API_KEY`: 测试网 API Key
- `BINANCE_TEST_API_SECRET`: 测试网 API Secret
- `BINANCE_MAIN_API_KEY`: 主网 API Key（生产环境）
- `BINANCE_MAIN_API_SECRET`: 主网 API Secret（生产环境）
- `WEBHOOK_SECRET`: Webhook 安全密钥

### 可选变量
- `FEISHU_WEBHOOK`: 飞书通知 Webhook URL
- `PORT`: Flask 服务端口（默认 80）
- `LEVERAGE`: 杠杆倍数（默认 3，范围 1-125）
- `RISK_PCT`: 风险百分比（默认 0.01，范围 0-1）
- `QTY_PRECISION`: 数量精度（默认 3，范围 0-8）

## 功能特性

- ✅ 自动交易执行（通过 webhook）
- ✅ 风险控制（基于余额百分比）
- ✅ 持仓管理（自动平反向持仓）
- ✅ 交易历史记录（保存在 `logs/trade_history.json`）
- ✅ 健康检查和状态查询
- ✅ 完整的错误处理和日志记录
- ✅ 飞书通知集成

## 注意事项

- 首次使用建议在测试网（testnet）模式下运行
- 确保 `.env` 文件已添加到 `.gitignore`，不要提交敏感信息
- 生产环境使用前请充分测试
- 交易历史文件保存在 `logs/trade_history.json`，最多保留最近 1000 条记录
- 建议定期备份交易历史文件

