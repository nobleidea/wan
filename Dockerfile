# Updated handler path - rebuild trigger
# Dockerfile optimizado para WAN 2.1 I2V Serverless
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_PREFER_BINARY=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Instalar dependencias del sistema en pasos separados
RUN apt-get update

RUN apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev python3-pip

RUN apt-get install -y --no-install-recommends \
    curl git wget vim libgl1 libglib2.0-0 build-essential

RUN ln -sf /usr/bin/python3.12 /usr/bin/python && \
    python3.12 -m venv /opt/venv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Instalar PyTorch
RUN pip install --no-cache-dir --pre torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/nightly/cu128

# Instalar dependencias base
RUN pip install --no-cache-dir runpod websocket-client requests pillow opencv-python

# Instalar dependencias adicionales para WAN nodes con versiones compatibles
RUN pip install --no-cache-dir \
    accelerate \
    scikit-image \
    numba \
    omegaconf \
    blend-modes \
    piexif \
    "diffusers>=0.21.0,<0.30.0" \
    "huggingface_hub>=0.16.0,<0.20.0"

# Instalar ComfyUI
RUN pip install --no-cache-dir comfy-cli && \
    /usr/bin/yes | comfy --workspace /ComfyUI install

# Instalar custom nodes uno por uno
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-KJNodes.git

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/cubiq/ComfyUI_essentials.git

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/chrisgoringe/cg-use-everywhere.git && \
    git clone https://github.com/rgthree/rgthree-comfy.git && \
    git clone https://github.com/M1kep/ComfyLiterals.git && \
    git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    git clone https://github.com/yolain/ComfyUI-Easy-Use.git

# Instalar requirements
RUN pip install --no-cache-dir -r /ComfyUI/custom_nodes/ComfyUI-KJNodes/requirements.txt || true
RUN pip install --no-cache-dir -r /ComfyUI/custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt || true
RUN pip install --no-cache-dir -r /ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation/requirements.txt || true

# Copiar archivos
COPY src/ /app/
COPY Legacy-Native-I2V-32FPS.json /app/workflow.json
WORKDIR /app

CMD ["python", "handler.py"]
