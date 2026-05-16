FROM python:3.11-slim

WORKDIR /app

# System dependencies for Docling and its ML pipeline:
#   libgl1, libglib2.0-0  — required by opencv-python-headless (used by Docling)
#   libgomp1              — OpenMP runtime required by PyTorch / EasyOCR
#   poppler-utils         — PDF rendering utilities used by Docling's PDF pipeline
#   gcc / libc-dev / libffi-dev — general build tools for compiled Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    libffi-dev \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --upgrade pip
# 1. PyTorchのCUDA 12.1対応版をインストールする
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
# 2. 次に、requirements.txt の中身を通常のルート（PyPI）からインストールする
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Docling ML models during image build so the first request
# is not delayed by model downloads at runtime.
RUN python - <<'EOF'
from docling.document_converter import DocumentConverter
# Instantiating the converter triggers model downloads.
_ = DocumentConverter()
print("Docling models pre-loaded successfully.")
EOF

COPY . .

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
