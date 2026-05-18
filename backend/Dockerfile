FROM python:3.11-slim

WORKDIR /app

# System dependencies: backend + parser (ML libs) + redis-server
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    libffi-dev \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    poppler-utils \
    redis-server \
    && rm -rf /var/lib/apt/lists/*

# Performance / memory environment variables (from parser)
ENV OMP_NUM_THREADS=4
ENV MKL_NUM_THREADS=4
ENV MALLOC_ARENA_MAX=2
ENV TOKENIZERS_PARALLELISM=false

# Build arg: set INSTALL_GPU=true for CUDA torch + onnxruntime-gpu
ARG INSTALL_GPU=false

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --upgrade pip

# Install PyTorch (CPU by default, CUDA if INSTALL_GPU=true)
RUN if [ "$INSTALL_GPU" = "true" ]; then \
      pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121; \
    else \
      pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu; \
    fi

# Install onnxruntime (GPU variant if INSTALL_GPU=true)
RUN if [ "$INSTALL_GPU" = "true" ]; then \
      pip install --no-cache-dir onnxruntime-gpu; \
    else \
      pip install --no-cache-dir onnxruntime; \
    fi

RUN pip install --no-cache-dir -r requirements.txt

# Startup script
COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy service code (volume-mounted in development, used directly in production)
COPY backend/ /app/
COPY worker/ /worker/
COPY parser/ /parser/

EXPOSE 8000 8001

ENTRYPOINT ["/entrypoint.sh"]
