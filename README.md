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

- `app.py` - Flask 应用主文件，包含 webhook 接口
- `config.py` - 配置文件，从环境变量读取配置
- `init_testnet.py` - 测试网初始化脚本
- `requirements.txt` - Python 依赖包列表

## 环境变量说明

- `BINANCE_MODE`: 运行模式，`testnet` 或 `main`
- `BINANCE_TEST_API_KEY`: 测试网 API Key
- `BINANCE_TEST_API_SECRET`: 测试网 API Secret
- `BINANCE_MAIN_API_KEY`: 主网 API Key（生产环境）
- `BINANCE_MAIN_API_SECRET`: 主网 API Secret（生产环境）
- `WEBHOOK_SECRET`: Webhook 安全密钥
- `FEISHU_WEBHOOK`: 飞书通知 Webhook（可选）
- `PORT`: Flask 服务端口（默认 80）

## 注意事项

- 首次使用建议在测试网（testnet）模式下运行
- 确保 `.env` 文件已添加到 `.gitignore`，不要提交敏感信息
- 生产环境使用前请充分测试

