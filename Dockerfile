# Dockerfile optimizado para WAN 2.1 I2V Serverless
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_PREFER_BINARY=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Instalar dependencias del sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev python3-pip \
    curl git wget vim libgl1 libglib2.0-0 build-essential && \
    ln -sf /usr/bin/python3.12 /usr/bin/python && \
    python3.12 -m venv /opt/venv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Instalar PyTorch
RUN pip install --no-cache-dir --pre torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/nightly/cu128

# Instalar dependencias base
RUN pip install --no-cache-dir runpod websocket-client requests pillow opencv-python

# ❗ CLAVE: Instalar versiones compatibles ANTES de ComfyUI-WanVideoWrapper
RUN pip install --no-cache-dir \
    "huggingface_hub>=0.16.0,<0.26.0" \
    "diffusers>=0.21.0,<0.29.0" \
    "transformers>=4.25.0,<4.37.0" \
    accelerate \
    scikit-image \
    numba \
    omegaconf \
    blend-modes \
    piexif

# Instalar ComfyUI
RUN pip install --no-cache-dir comfy-cli && \
    /usr/bin/yes | comfy --workspace /ComfyUI install

# Instalar custom nodes base PRIMERO
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-KJNodes.git && \
    git clone https://github.com/cubiq/ComfyUI_essentials.git && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git && \
    git clone https://github.com/chrisgoringe/cg-use-everywhere.git && \
    git clone https://github.com/rgthree/rgthree-comfy.git && \
    git clone https://github.com/M1kep/ComfyLiterals.git && \
    git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    git clone https://github.com/yolain/ComfyUI-Easy-Use.git

# ❗ AHORA instalar ComfyUI-WanVideoWrapper CON versiones fijas
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git

# Instalar requirements con versiones controladas
RUN pip install --no-cache-dir -r /ComfyUI/custom_nodes/ComfyUI-KJNodes/requirements.txt || true
RUN pip install --no-cache-dir -r /ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt || true
RUN pip install --no-cache-dir -r /ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation/requirements.txt || true

# ❗ CRUCIAL: Instalar requirements de WanVideoWrapper SIN actualizar las versiones que ya fijamos
RUN pip install --no-cache-dir --no-deps \
    ftfy \
    einops \
    sentencepiece \
    fire \
    openai-whisper \
    soundfile \
    timm \
    kornia

# Copiar archivos
COPY src/ /app/
COPY Legacy-Native-I2V-32FPS.json /app/workflow.json
WORKDIR /app

CMD ["python", "handler.py"]
