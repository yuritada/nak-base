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

# ── Performance / memory environment variables ────────────────────────────────
# Limit OpenMP threads so CPU preprocessing does not starve GPU inference.
ENV OMP_NUM_THREADS=4
ENV MKL_NUM_THREADS=4
# Reduce glibc arena count to prevent fragmented virtual-memory growth.
ENV MALLOC_ARENA_MAX=2
# PyTorch expandable memory segments reduce VRAM fragmentation (PyTorch ≥ 2.0).
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# Suppress tokenizer parallelism warnings from HuggingFace.
ENV TOKENIZERS_PARALLELISM=false

# Install Python dependencies
COPY requirements.txt .

RUN pip install --upgrade pip
# 1. Install PyTorch with CUDA 12.1 support
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
# 2. Install remaining dependencies from PyPI
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Docling ML models during image build so the first request
# is not delayed by model downloads at runtime.
#
# IMPORTANT: Use the same PdfPipelineOptions that pdf_parser.py uses at
# runtime (do_table_structure=True, do_ocr=False) so that all required
# model weights are cached here and none are fetched on first request.
RUN python - <<'EOF'
import torch

print(f"CUDA available: {torch.cuda.is_available()}")

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from docling.datamodel.base_models import InputFormat

pipeline_options = PdfPipelineOptions()
pipeline_options.do_table_structure = True
pipeline_options.do_ocr = False  # matches PARSER_USE_OCR=false default

# Apply AcceleratorOptions when available (docling >= 2.5)
try:
    from docling.datamodel.pipeline_options import AcceleratorOptions, AcceleratorDevice
    device = AcceleratorDevice.CUDA if torch.cuda.is_available() else AcceleratorDevice.CPU
    pipeline_options.accelerator_options = AcceleratorOptions(num_threads=4, device=device)
    print(f"AcceleratorOptions set: device={device.value}")
except (ImportError, AttributeError):
    print("AcceleratorOptions not available in this docling version; skipping")

converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
)
print("Docling models pre-loaded successfully.")
EOF

COPY . .

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
