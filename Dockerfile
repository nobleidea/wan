# WAN 2.1 I2V Serverless - Direct Installation
FROM runpod/worker-comfyui:5.2.0-base

RUN apt-get update && apt-get install -y git wget zlib1g-dev && rm -rf /var/lib/apt/lists/*

# Create all necessary model directories
RUN mkdir -p \
    /comfyui/models/diffusion_models \
    /comfyui/models/vae \
    /comfyui/models/text_encoders \
    /comfyui/models/clip_vision \
    /comfyui/models/upscale_models

# Download WAN 2.1 models
RUN echo "=== Downloading WAN 2.1 models ===" && \
    wget --timeout=600 --tries=3 --user-agent="Mozilla/5.0" -c \
    -O "/comfyui/models/diffusion_models/wan2.1_i2v_480p_14B_bf16.safetensors" \
    "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_i2v_480p_14B_bf16.safetensors"

RUN wget --timeout=600 --tries=3 --user-agent="Mozilla/5.0" -c \
    -O "/comfyui/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
    "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"

RUN wget --timeout=600 --tries=3 --user-agent="Mozilla/5.0" -c \
    -O "/comfyui/models/vae/wan_2.1_vae.safetensors" \
    "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"

RUN wget --timeout=600 --tries=3 --user-agent="Mozilla/5.0" -c \
    -O "/comfyui/models/clip_vision/clip_vision_h.safetensors" \
    "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors"

RUN wget --timeout=600 --tries=3 --user-agent="Mozilla/5.0" -c \
    -O "/comfyui/models/upscale_models/4xLSDIR.pth" \
    "https://github.com/Phhofm/models/releases/download/4xLSDIR/4xLSDIR.pth"

# Install custom nodes with conditional checking
WORKDIR /comfyui/custom_nodes

RUN echo "=== Installing custom nodes ===" && \
    if [ ! -d "ComfyUI-KJNodes" ]; then \
        echo "Cloning ComfyUI-KJNodes..." && \
        git clone https://github.com/kijai/ComfyUI-KJNodes.git && \
        echo "ComfyUI-KJNodes cloned successfully"; \
    fi && \
    if [ ! -d "ComfyUI_essentials" ]; then \
        echo "Cloning ComfyUI_essentials..." && \
        git clone https://github.com/cubiq/ComfyUI_essentials.git && \
        echo "ComfyUI_essentials cloned successfully"; \
    fi && \
    if [ ! -d "ComfyUI-VideoHelperSuite" ]; then \
        echo "Cloning ComfyUI-VideoHelperSuite..." && \
        git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
        echo "ComfyUI-VideoHelperSuite cloned successfully"; \
    fi && \
    if [ ! -d "ComfyUI-Frame-Interpolation" ]; then \
        echo "Cloning ComfyUI-Frame-Interpolation..." && \
        git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git && \
        echo "ComfyUI-Frame-Interpolation cloned successfully"; \
    fi && \
    if [ ! -d "cg-use-everywhere" ]; then \
        echo "Cloning cg-use-everywhere..." && \
        git clone https://github.com/chrisgoringe/cg-use-everywhere.git && \
        echo "cg-use-everywhere cloned successfully"; \
    fi && \
    if [ ! -d "rgthree-comfy" ]; then \
        echo "Cloning rgthree-comfy..." && \
        git clone https://github.com/rgthree/rgthree-comfy.git && \
        echo "rgthree-comfy cloned successfully"; \
    fi && \
    if [ ! -d "ComfyLiterals" ]; then \
        echo "Cloning ComfyLiterals..." && \
        git clone https://github.com/M1kep/ComfyLiterals.git && \
        echo "ComfyLiterals cloned successfully"; \
    fi && \
    if [ ! -d "ComfyUI-Impact-Pack" ]; then \
        echo "Cloning ComfyUI-Impact-Pack..." && \
        git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
        echo "ComfyUI-Impact-Pack cloned successfully"; \
    fi && \
    if [ ! -d "ComfyUI-Easy-Use" ]; then \
        echo "Cloning ComfyUI-Easy-Use..." && \
        git clone https://github.com/yolain/ComfyUI-Easy-Use.git && \
        echo "ComfyUI-Easy-Use cloned successfully"; \
    fi && \
    if [ ! -d "customNode" ]; then \
        echo "Cloning customNode..." && \
        git clone https://github.com/nobleidea/customNode.git && \
        echo "customNode cloned successfully"; \
    fi

# Install requirements for each node
RUN echo "=== Installing dependencies ===" && \
    for dir in ComfyUI-KJNodes ComfyUI_essentials ComfyUI-VideoHelperSuite ComfyUI-Frame-Interpolation cg-use-everywhere rgthree-comfy ComfyLiterals ComfyUI-Impact-Pack ComfyUI-Easy-Use customNode; do \
        if [ -f "/comfyui/custom_nodes/$dir/requirements.txt" ]; then \
            echo "Installing requirements for $dir"; \
            cd "/comfyui/custom_nodes/$dir" && pip install -r requirements.txt || true; \
        else \
            echo "No requirements.txt found for $dir"; \
        fi; \
    done

# Set final workdir and copy files
WORKDIR /comfyui

# Copy application files
COPY src/ /app/
COPY Legacy-Native-I2V-32FPS.json /app/workflow.json
WORKDIR /app

CMD ["python", "handler.py"]
