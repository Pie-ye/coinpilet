# ============================================
# CoinPilot AI - Docker 映像檔
# ============================================
# 多階段建置：
#   1. Hugo Extended 二進位檔案
#   2. Python 運行環境
# ============================================

# Stage 1: 下載 Hugo Extended
FROM alpine:3.19 AS hugo-builder

ARG HUGO_VERSION=0.124.1

RUN apk add --no-cache curl tar && \
    curl -L "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_Linux-64bit.tar.gz" | \
    tar -xz -C /usr/local/bin hugo

# Stage 2: Python 運行環境
FROM python:3.11-slim

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    # Hugo 需要的依賴 (Extended 版本需要 libstdc++)
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# 從 Stage 1 複製 Hugo
COPY --from=hugo-builder /usr/local/bin/hugo /usr/local/bin/hugo

# 驗證 Hugo 安裝
RUN hugo version

# 設定工作目錄
WORKDIR /app

# 複製依賴檔案
COPY pyproject.toml ./

# 安裝 Python 依賴
RUN pip install --no-cache-dir -e .

# 複製專案檔案
COPY . .

# 初始化 Hugo 模組 (下載 Stack 主題)
WORKDIR /app/site
RUN hugo mod get -u || true

# 回到專案根目錄
WORKDIR /app

# 建立資料目錄
RUN mkdir -p data

# 預設指令
CMD ["python", "main.py", "run", "--mock"]

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# 標籤
LABEL maintainer="CoinPilot Team" \
      version="0.1.0" \
      description="CoinPilot AI - 自動化加密貨幣分析系統"
