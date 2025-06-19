import runpod
import os
import sys
import time
import json
import requests
import base64
import subprocess
import threading
from pathlib import Path

# Configuración
WORKSPACE_PATH = "/runpod-volume"
COMFYUI_PATH = f"{WORKSPACE_PATH}/ComfyUI"
WORKFLOW_PATH = "/app/workflow.json"
COMFYUI_URL = "http://localhost:8188"

def check_models():
    """Verificar que los modelos estén disponibles en el network volume"""
    required_models = {
        "diffusion_models": ["wan2.1_i2v_480p_14B_bf16.safetensors"],
        "text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
        "vae": ["wan_2.1_vae.safetensors"],
        "clip_vision": ["clip_vision_h.safetensors"],
        "upscale_models": ["4xLSDIR.pth"]
    }
    
    for model_type, models in required_models.items():
        model_path = f"{COMFYUI_PATH}/models/{model_type}"
        if not os.path.exists(model_path):
            raise Exception(f"Model directory not found: {model_path}")
        
        for model in models:
            model_file = f"{model_path}/{model}"
            if not os.path.exists(model_file):
                raise Exception(f"Required model not found: {model_file}")
    
    print("✅ All required models found!")
    return True

def start_comfyui():
    """Iniciar ComfyUI server"""
    # Crear symlink si no existe
    if not os.path.exists("/ComfyUI"):
        os.symlink(COMFYUI_PATH, "/ComfyUI")
    
    os.chdir(COMFYUI_PATH)
    
    cmd = [
        "python", "main.py", 
        "--listen", "0.0.0.0",
        "--port", "8188",
        "--use-sage-attention"
    ]
    
    def run_comfyui():
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    thread = threading.Thread(target=run_comfyui, daemon=True)
    thread.start()
    
    # Esperar a que ComfyUI esté listo
    for i in range(300):  # 5 minutos timeout
        try:
            response = requests.get(f"{COMFYUI_URL}/history", timeout=5)
            if response.status_code == 200:
                print("✅ ComfyUI is ready!")
                return True
        except:
            pass
        time.sleep(1)
    
    raise Exception("❌ ComfyUI failed to start within 5 minutes")

def generate_video(input_image_base64, prompt, negative_prompt=""):
    """Generar video usando el workflow"""
    
    # Cargar workflow
    with open(WORKFLOW_PATH, 'r') as f:
        workflow = json.load(f)
    
    # TODO: Modificar workflow con inputs del usuario
    # Por ahora, solo iniciamos ComfyUI y retornamos éxito
    
    return {
        "status": "success",
        "message": "Video generation started",
        "workflow_loaded": True
    }

def handler(event):
    """Handler principal de RunPod"""
    try:
        print("🚀 Starting WAN 2.1 I2V serverless handler...")
        
        # Verificar modelos
        print("🔍 Checking models...")
        check_models()
        
        # Iniciar ComfyUI
        print("⚡ Starting ComfyUI...")
        start_comfyui()
        
        # Obtener inputs
        job_input = event.get("input", {})
        
        if not job_input:
            return {
                "status": "error", 
                "message": "No input provided"
            }
        
        # Generar video
        result = generate_video(
            job_input.get("image", ""),
            job_input.get("prompt", ""),
            job_input.get("negative_prompt", "")
        )
        
        return result
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

if __name__ == "__main__":
    # Para testing local
    test_event = {
        "input": {
            "image": "test_base64_image",
            "prompt": "A beautiful woman walking"
        }
    }
    result = handler(test_event)
    print(json.dumps(result, indent=2))
else:
    # Para RunPod serverless
    runpod.serverless.start({"handler": handler})
