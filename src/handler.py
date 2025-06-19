import runpod
import os
import sys
import time
import json
import requests
import base64
import subprocess
import threading
import uuid
from pathlib import Path
from PIL import Image
import io

# Configuración
WORKSPACE_PATH = "/runpod-volume"
COMFYUI_PATH = f"{WORKSPACE_PATH}/ComfyUI"
WORKFLOW_PATH = "/app/workflow.json"
COMFYUI_URL = "http://localhost:8188"

def save_base64_image(base64_string, filename):
    """Guardar imagen base64 en el sistema de archivos"""
    try:
        # Remover el prefijo data:image si existe
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        # Decodificar base64
        image_data = base64.b64decode(base64_string)
        
        # Crear directorio input si no existe
        input_dir = f"{COMFYUI_PATH}/input"
        os.makedirs(input_dir, exist_ok=True)
        
        # Guardar imagen
        image_path = f"{input_dir}/{filename}"
        with open(image_path, 'wb') as f:
            f.write(image_data)
        
        print(f"✅ Image saved: {image_path}")
        return filename
        
    except Exception as e:
        print(f"❌ Error saving image: {e}")
        raise Exception(f"Failed to save input image: {e}")

def modify_workflow(workflow, image_filename, prompt, negative_prompt):
    """Modificar workflow con los parámetros del usuario"""
    try:
        # Nodo 294 - LoadImage (Input Image)
        for node in workflow["nodes"]:
            if node["id"] == 294 and node["type"] == "LoadImage":
                node["widgets_values"][0] = image_filename
                print(f"✅ Updated LoadImage node with: {image_filename}")
            
            # Nodo 243 - CLIPTextEncode (Positive Prompt) 
            elif node["id"] == 243 and node["type"] == "CLIPTextEncode":
                node["widgets_values"][0] = prompt
                print(f"✅ Updated positive prompt: {prompt[:50]}...")
            
            # Nodo 244 - CLIPTextEncode (Negative Prompt)
            elif node["id"] == 244 and node["type"] == "CLIPTextEncode":
                node["widgets_values"][0] = negative_prompt
                print(f"✅ Updated negative prompt: {negative_prompt[:50]}...")
        
        return workflow
        
    except Exception as e:
        print(f"❌ Error modifying workflow: {e}")
        raise Exception(f"Failed to modify workflow: {e}")

def execute_workflow(workflow):
    """Ejecutar workflow en ComfyUI y esperar resultado"""
    try:
        # Generar ID único para este prompt
        prompt_id = str(uuid.uuid4())
        
        # Preparar payload para ComfyUI API
        payload = {
            "prompt": workflow,
            "client_id": prompt_id
        }
        
        print(f"🚀 Sending workflow to ComfyUI with ID: {prompt_id}")
        
        # Enviar workflow a ComfyUI
        response = requests.post(f"{COMFYUI_URL}/prompt", json=payload)
        response.raise_for_status()
        
        result = response.json()
        prompt_id = result["prompt_id"]
        print(f"✅ Workflow submitted successfully, prompt_id: {prompt_id}")
        
        # Polling para esperar a que termine
        print("⏳ Waiting for workflow execution...")
        max_wait = 300  # 5 minutos máximo
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            # Verificar estado
            history_response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
            
            if history_response.status_code == 200:
                history = history_response.json()
                
                if prompt_id in history:
                    execution_data = history[prompt_id]
                    
                    # Verificar si terminó
                    if "outputs" in execution_data:
                        print("✅ Workflow execution completed!")
                        return extract_output_files(execution_data["outputs"])
                    
                    # Verificar si hay error
                    elif "status" in execution_data:
                        status = execution_data["status"]
                        if status.get("status_str") == "error":
                            error_msg = status.get("messages", ["Unknown error"])
                            raise Exception(f"Workflow execution failed: {error_msg}")
            
            # Esperar antes del siguiente check
            time.sleep(5)
            
            # Log de progreso cada 30 segundos
            if int(time.time() - start_time) % 30 == 0:
                elapsed = int(time.time() - start_time)
                print(f"⏳ Still waiting... ({elapsed}s elapsed)")
        
        raise Exception("Workflow execution timeout after 5 minutes")
        
    except Exception as e:
        print(f"❌ Error executing workflow: {e}")
        raise Exception(f"Failed to execute workflow: {e}")

def extract_output_files(outputs):
    """Extraer archivos de salida del resultado del workflow"""
    try:
        output_files = []
        
        # Los nodos de video suelen ser VHS_VideoCombine
        for node_id, node_output in outputs.items():
            if "videos" in node_output:
                for video_info in node_output["videos"]:
                    video_path = f"{COMFYUI_PATH}/output/{video_info['filename']}"
                    if os.path.exists(video_path):
                        output_files.append({
                            "type": "video",
                            "filename": video_info['filename'],
                            "path": video_path,
                            "node_id": node_id
                        })
                        print(f"✅ Found output video: {video_info['filename']}")
            
            if "images" in node_output:
                for image_info in node_output["images"]:
                    image_path = f"{COMFYUI_PATH}/output/{image_info['filename']}"
                    if os.path.exists(image_path):
                        output_files.append({
                            "type": "image", 
                            "filename": image_info['filename'],
                            "path": image_path,
                            "node_id": node_id
                        })
                        print(f"✅ Found output image: {image_info['filename']}")
        
        return output_files
        
    except Exception as e:
        print(f"❌ Error extracting output files: {e}")
        return []

def file_to_base64(file_path):
    """Convertir archivo a base64"""
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
            base64_data = base64.b64encode(file_data).decode('utf-8')
            return base64_data
    except Exception as e:
        print(f"❌ Error converting file to base64: {e}")
        return None

def generate_video(input_image_base64, prompt, negative_prompt=""):
    """Generar video usando el workflow completo"""
    try:
        print("🎬 Starting video generation...")
        
        # 1. Guardar imagen de input
        image_filename = f"input_{int(time.time())}.png"
        saved_filename = save_base64_image(input_image_base64, image_filename)
        
        # 2. Cargar y modificar workflow
        print("📝 Loading and modifying workflow...")
        with open(WORKFLOW_PATH, 'r') as f:
            workflow = json.load(f)
        
        modified_workflow = modify_workflow(workflow, saved_filename, prompt, negative_prompt)
        
        # 3. Ejecutar workflow
        print("⚡ Executing workflow...")
        output_files = execute_workflow(modified_workflow)
        
        if not output_files:
            raise Exception("No output files generated")
        
        # 4. Convertir outputs a base64
        print("📦 Processing output files...")
        results = []
        
        for output_file in output_files:
            base64_data = file_to_base64(output_file["path"])
            if base64_data:
                results.append({
                    "type": output_file["type"],
                    "filename": output_file["filename"], 
                    "data": base64_data,
                    "node_id": output_file["node_id"]
                })
        
        print(f"✅ Video generation completed! Generated {len(results)} files")
        
        return {
            "status": "success",
            "message": f"Video generation completed successfully",
            "output_files": results,
            "total_files": len(results)
        }
        
    except Exception as e:
        print(f"❌ Video generation failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

# ... resto de funciones (check_models, start_comfyui, handler) sin cambios

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
    
    print(f"📂 Changing directory to: {COMFYUI_PATH}")
    os.chdir(COMFYUI_PATH)
    
    # Verificar que main.py existe
    if not os.path.exists("main.py"):
        raise Exception(f"❌ main.py not found in {COMFYUI_PATH}")
    
    print("🔧 Starting ComfyUI process...")
    cmd = [
        "python", "main.py", 
        "--listen", "0.0.0.0",
        "--port", "8188"
    ]
    
    print(f"🚀 Command: {' '.join(cmd)}")
    
    # Iniciar ComfyUI con logs visibles
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Mostrar logs en tiempo real
    def show_logs():
        for line in process.stdout:
            print(f"ComfyUI: {line.strip()}")
    
    thread = threading.Thread(target=show_logs, daemon=True)
    thread.start()
    
    # Esperar a que ComfyUI esté listo
    print("⏳ Waiting for ComfyUI to be ready...")
    for i in range(300):  # 5 minutos
        try:
            response = requests.get(f"{COMFYUI_URL}/history", timeout=5)
            if response.status_code == 200:
                print("✅ ComfyUI is ready!")
                return True
        except Exception as e:
            if i % 30 == 0:  # Log cada 30 segundos
                print(f"⏳ Still waiting... ({i//60}m {i%60}s) - {e}")
        time.sleep(1)
    
    print("❌ ComfyUI logs:")
    if process.poll() is not None:
        print(f"Process exited with code: {process.returncode}")
    
    raise Exception("❌ ComfyUI failed to start within 5 minutes")

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
