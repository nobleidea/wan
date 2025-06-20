##############################################################################
# WAN 2.1 I2V – Dockerfile PARA RUNPOD SERVERLESS (funciona con Python 3.12)
##############################################################################
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 AS base

# ────────────── env ───────────────
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    GIT_PYTHON_REFRESH=quiet \
    PATH="/opt/venv/bin:$PATH"

# ───── sistema + python 3.12 + git (NO se purga) ─────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3.12-dev python3-pip \
        git curl wget ffmpeg build-essential libgl1 libglib2.0-0 && \
    python3.12 -m venv /opt/venv && \
    ln -sf /usr/bin/python3.12 /usr/local/bin/python && \
    python -m pip install --upgrade pip

# ───── torch nightly cu128 (wheels cp312) ─────
RUN pip install --pre torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/nightly/cu128

# ───── runtime libs iguales al Pod (sin fijar OpenCV) ─────
RUN pip install packaging setuptools wheel \
                 pyyaml gdown triton comfy-cli \
                 websocket-client requests pillow

# ───── ComfyUI core ─────
RUN yes | comfy --workspace /ComfyUI install

##############################################################################
# segunda etapa: plugins, SAM, etc.
##############################################################################
FROM base AS final
ENV PATH="/opt/venv/bin:$PATH"

# 1️⃣  OpenCV wheel cp312 (igual que Pod)
RUN pip install opencv-python      # ← resuelve a 4.11.0.86 cp312

# 2️⃣  (opcional) Segment-Anything + ONNX-GPU  
#     *solo* si tus flujos lo necesitan; si no, omite todo el bloque
RUN curl -L -o /tmp/sam.tar.gz \
        https://codeload.github.com/facebookresearch/segment-anything/tar.gz/6325eb80 && \
    pip install /tmp/sam.tar.gz onnxruntime-gpu==1.18.0 && \
    rm /tmp/sam.tar.gz

# 3️⃣  clonar nodos (idéntico al Pod)
RUN set -eux; cd /ComfyUI/custom_nodes && \
    for repo in \
        https://github.com/kijai/ComfyUI-KJNodes.git \
        https://github.com/cubiq/ComfyUI_essentials.git \
        https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git \
        https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git \
        https://github.com/chrisgoringe/cg-use-everywhere.git \
        https://github.com/rgthree/rgthree-comfy.git \
        https://github.com/M1kep/ComfyLiterals.git \
        https://github.com/ltdrdata/ComfyUI-Impact-Pack.git \
        https://github.com/yolain/ComfyUI-Easy-Use.git ; \
    do \
        git clone "$repo"; \
        req="/ComfyUI/custom_nodes/$(basename "$repo" .git)/requirements.txt"; \
        [ -f "$req" ] && pip install -r "$req" || true ; \
    done

# 4️⃣  tu handler
COPY src/ /app/
WORKDIR /app
CMD ["python", "handler.py"]

