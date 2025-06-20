###############################################################################
# WAN 2.1 I2V – Dockerfile estable para RunPod Serverless  (20-jun-2025)
#  • Ubuntu 24.04 + CUDA 12.8 runtime
#  • Python 3.11  (todas las wheels oficiales existen)
#  • Torch 2.3.0 + cu121 (compatible con libcuda 12.8)
###############################################################################

FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04

# ────────────────────────────────  ENV  ───────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GIT_PYTHON_REFRESH=quiet \
    PATH="/opt/venv/bin:$PATH"

# ──────────────────────────  SISTEMA + PYTHON  ────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev python3-pip \
        git curl wget ca-certificates build-essential \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 && \
    python3.11 -m venv /opt/venv && \
    ln -s /usr/bin/python3.11 /usr/local/bin/python && \
    python -m pip install --upgrade pip && \
    rm -rf /var/lib/apt/lists/*

# ─────────────────────────────  PyTorch 2.3  ──────────────────────────────────
RUN python -m pip install --extra-index-url https://download.pytorch.org/whl/cu121 \
        torch==2.3.0 torchvision==0.18.0 torchaudio==2.3.0

# ────────────────────────  DEPENDENCIAS BÁSICAS  ─────────────────────────────
RUN python -m pip install runpod websocket-client requests pillow

# ───────────  SEGMENT ANYTHING (+ONNX & OpenCV cp311/cp312)  ──────────────────
RUN curl -L -o /tmp/sam.tar.gz \
        https://codeload.github.com/facebookresearch/segment-anything/tar.gz/6325eb80 && \
    python -m pip install /tmp/sam.tar.gz \
        onnxruntime-gpu==1.18.0 \
        opencv-contrib-python-headless==4.11.0.86 && \
    rm /tmp/sam.tar.gz

# ───────────  LIBS PARA NODOS WAN / DIFFUSION  ────────────────────────────────
RUN python -m pip install \
        accelerate scikit-image numba omegaconf blend-modes piexif ftfy einops \
        sentencepiece fire \
        "huggingface_hub>=0.20.0,<0.30.0" \
        "diffusers>=0.30.0,<0.35.0" \
        "transformers>=4.37.0,<4.45.0"

# ─────────────────────────────  ComfyUI  ──────────────────────────────────────
RUN python -m pip install comfy-cli && \
    yes | comfy --workspace /ComfyUI install

# ─────────────────────  CUSTOM NODES (clonados con git)  ──────────────────────
RUN set -eux; cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-KJNodes.git && \
    git clone https://github.com/cubiq/ComfyUI_essentials.git && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git && \
    git clone https://github.com/chrisgoringe/cg-use-everywhere.git && \
    git clone https://github.com/rgthree/rgthree-comfy.git && \
    git clone https://github.com/M1kep/ComfyLiterals.git && \
    git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    git clone https://github.com/yolain/ComfyUI-Easy-Use.git

# Requisitos opcionales de algunos nodos (si fallan no rompen el build)
RUN python -m pip install -r /ComfyUI/custom_nodes/ComfyUI-KJNodes/requirements.txt  || true
RUN python -m pip install -r /ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt || true
RUN python -m pip install -r /ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation/requirements.txt || true

# ─────────────────────  TU CÓDIGO & WORKFLOW  ────────────────────────────────
COPY src/ /app/
COPY Legacy-Native-I2V-32FPS.json /app/workflow.json
WORKDIR /app

CMD ["python", "handler.py"]

