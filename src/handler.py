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
import shutil


# Configuración
WORKSPACE_PATH = "/runpod-volume"
COMFYUI_PATH = f"{WORKSPACE_PATH}/ComfyUI"
WORKFLOW_PATH = "/app/workflow.json"
COMFYUI_URL = "http://localhost:8188"

# 🔥 NUEVO: Configuración para RunPod output. Rutas absolutas para evitar problemas con cambios de directorio
OUTPUT_DIR = Path(f"{COMFYUI_PATH}/output")           # Donde ComfyUI guarda
RP_OUTPUT_DIR  = Path("/output_objects")   # <- raíz del contenedor 🔥 Network volume
RP_OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

def save_base64_image(base64_string, filename):
    """Guardar imagen base64 en el sistema de archivos con procesamiento PIL"""
    try:
        # Remover el prefijo data:image si existe
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]

        # Añadir padding si es necesario para evitar el error "Incorrect padding"
        missing_padding = len(base64_string) % 4
        if missing_padding:
            base64_string += '=' * (4 - missing_padding)

        # Decodificar base64
        image_data = base64.b64decode(base64_string)
                
        # Cargar imagen desde bytes
        image = Image.open(io.BytesIO(image_data))
        
        # Manejar diferentes modos de color correctamente
        if image.mode == 'RGBA':
            # Crear fondo blanco para transparencias
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])  # Alpha channel
            image = background
        elif image.mode == 'P':
            # Paleta de colores
            image = image.convert('RGB')
        elif image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        
        # Crear directorio input si no existe
        input_dir = f"{COMFYUI_PATH}/input"
        os.makedirs(input_dir, exist_ok=True)
        
        # Guardar imagen con máxima calidad
        image_path = f"{input_dir}/{filename}"
        image.save(image_path, 'PNG', optimize=False, compress_level=0)
        
        print(f"✅ Image saved: {image_path} (Mode: {image.mode}, Size: {image.size})")
        return filename
        
    except Exception as e:
        print(f"❌ Error saving image: {e}")
        raise Exception(f"Failed to save input image: {e}")


def download_image_from_url(image_url):
    """Descargar imagen desde URL"""
    try:
        
        print(f"📥 Downloading image from: {image_url}")
        
        # Descargar imagen
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        # Procesar con PIL
        image = Image.open(io.BytesIO(response.content))
        
        # Manejar diferentes modos de color
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background
        elif image.mode == 'P':
            image = image.convert('RGB')
        elif image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        
        # Guardar
        input_dir = f"{COMFYUI_PATH}/input"
        os.makedirs(input_dir, exist_ok=True)
        
        timestamp = int(time.time() * 1000000)
        filename = f"input_{timestamp}.png"
        image_path = f"{input_dir}/{filename}"
        
        image.save(image_path, 'PNG', optimize=False, compress_level=0)
        
        print(f"✅ Image downloaded and saved: {image_path} (Mode: {image.mode}, Size: {image.size})")
        return filename  # ✅ Devolver solo filename para consistencia
        
    except Exception as e:
        print(f"❌ Error downloading image: {e}")
        raise Exception(f"Failed to download image: {e}")

def process_image_input(image_input):
    """Procesar imagen desde cualquier formato"""
    try:
        if isinstance(image_input, str):
            if image_input.startswith(("http://", "https://")):
                # URL
                print("🔗 Processing image from URL")
                return download_image_from_url(image_input)
            elif image_input.startswith("data:image") or len(image_input) > 100:
                # Base64
                print("📄 Processing image from Base64")
                timestamp = int(time.time() * 1000000)
                filename = f"input_{timestamp}.png"
                return save_base64_image(image_input, filename)
            else:
                raise ValueError(f"Invalid image string format: {image_input[:50]}...")
        else:
            raise ValueError(f"Unknown image input format: {type(image_input)}")
            
    except Exception as e:
        print(f"❌ Error processing image: {e}")
        raise Exception(f"Failed to process image: {e}")


def modify_workflow(workflow: dict,
                    image_filename: str,
                    prompt: str,
                    negative_prompt: str,
                    width: int = 832,
                    height: int = 480) -> dict:
    """
    Modifica el workflow con los parámetros del usuario
    """
    import time
    
    # Generar seed único
    unique_seed = int(time.time() * 1000000) % 2147483647  # Más variación
    print(f"🎲 Generated unique seed: {unique_seed}")
    
    # Crear una copia del workflow para no modificar el original
    modified_workflow = workflow.copy()
    
    # NODO 294: LoadImage - Actualizar imagen de entrada
    if "294" in modified_workflow:
        if "inputs" in modified_workflow["294"]:
            modified_workflow["294"]["inputs"]["image"] = image_filename
            print(f"✅ Updated LoadImage (294) with image: {image_filename}")
        else:
            print(f"❌ Node 294 missing inputs section")
    else:
        print(f"❌ Node 294 (LoadImage) not found in workflow")
    
    # NODO 243: Prompt positivo
    if "243" in modified_workflow:
        if "inputs" in modified_workflow["243"]:
            modified_workflow["243"]["inputs"]["text"] = prompt
            print(f"✅ Updated positive prompt (243): {prompt[:50]}...")
        else:
            print(f"❌ Node 243 missing inputs section")
    else:
        print(f"❌ Node 243 (positive prompt) not found in workflow")
    
    # NODO 244: Prompt negativo
    if "244" in modified_workflow:
        if "inputs" in modified_workflow["244"]:
            modified_workflow["244"]["inputs"]["text"] = negative_prompt
            print(f"✅ Updated negative prompt (244): {negative_prompt[:50]}...")
        else:
            print(f"❌ Node 244 missing inputs section")
    else:
        print(f"❌ Node 244 (negative prompt) not found in workflow")
    
    # NODO 259: KSampler - Actualizar seed
    if "259" in modified_workflow:
        if "inputs" in modified_workflow["259"]:
            modified_workflow["259"]["inputs"]["seed"] = unique_seed
            print(f"✅ Updated KSampler (259) seed: {unique_seed}")
        else:
            print(f"❌ Node 259 missing inputs section")
    else:
        print(f"❌ Node 259 (KSampler) not found in workflow")

    # NODO 236: WanImageToVideo - width y height
    if "236" in modified_workflow and "inputs" in modified_workflow["236"]:
        modified_workflow["236"]["inputs"]["width"] = width
        modified_workflow["236"]["inputs"]["height"] = height
        print(f"✅ Updated WanImageToVideo dimensions: {width}x{height}")
    
    # Verificar que los cambios se aplicaron
    print("🔍 Verification:")
    if "294" in modified_workflow and "inputs" in modified_workflow["294"]:
        print(f"  - Image: {modified_workflow['294']['inputs'].get('image', 'NOT SET')}")
    if "243" in modified_workflow and "inputs" in modified_workflow["243"]:
        print(f"  - Positive: {modified_workflow['243']['inputs'].get('text', 'NOT SET')[:30]}...")
    if "244" in modified_workflow and "inputs" in modified_workflow["244"]:
        print(f"  - Negative: {modified_workflow['244']['inputs'].get('text', 'NOT SET')[:30]}...")
    if "259" in modified_workflow and "inputs" in modified_workflow["259"]:
        print(f"  - Seed: {modified_workflow['259']['inputs'].get('seed', 'NOT SET')}")
    
    return modified_workflow


# FUNCIÓN DE DEBUG
def debug_workflow_connections(workflow: dict):
    """Debug para entender las conexiones actuales del workflow"""
    print("🔍 === WORKFLOW DEBUG ===")
    
    # Verificar nodos críticos
    critical_nodes = ["231", "232", "233", "302", "243", "244", "236", "290"]
    
    for node_id in critical_nodes:
        if node_id in workflow:
            node = workflow[node_id]
            class_type = node.get("class_type", "Unknown")
            inputs = node.get("inputs", {})
            print(f"🔍 Node {node_id} ({class_type}):")
            for input_name, input_value in inputs.items():
                print(f"    {input_name}: {input_value}")
        else:
            print(f"❌ Node {node_id} NOT FOUND in workflow")
    
    # Verificar específicamente los nodos Anything Everywhere
    anything_everywhere_nodes = ["280", "281", "282"]
    print("\n🔍 === ANYTHING EVERYWHERE NODES ===")
    for node_id in anything_everywhere_nodes:
        if node_id in workflow:
            node = workflow[node_id]
            print(f"🔍 Node {node_id}: {node}")
        else:
            print(f"❌ Anything Everywhere node {node_id} NOT FOUND")
    
    print("🔍 === END DEBUG ===\n")


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
        max_wait = 900  # antes era 5 minutos máximo ahora es 15
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
        
        raise Exception("Workflow execution timeout after 15 minutes")
        
    except Exception as e:
        print(f"❌ Error executing workflow: {e}")
        raise Exception(f"Failed to execute workflow: {e}")

def extract_output_files(outputs):
    """Extraer archivos de salida y copiarlos a output_objects para RunPod"""
    try:
        output_files = []
        
        # 🔍 DEBUG: Ver estructura real de outputs Y tipos de datos
        print("🔍 DEBUG - Estructura completa de outputs:")
        for node_id, node_output in outputs.items():
            print(f"  Node {node_id} (tipo: {type(node_id)}): {list(node_output.keys())}")
            
            # 🔥 NUEVO: Verificar tanto string como int para nodo 94
            if str(node_id) == "94" or node_id == 94:
                print(f"    ✅ ENCONTRADO NODO 94!")
                print(f"    Tipo de node_id: {type(node_id)}")
                print(f"    Contenido completo: {node_output}")
                print(f"    Claves disponibles: {list(node_output.keys())}")
        
        # Procesar estructura oficial de ComfyUI
        for node_id, node_output in outputs.items():
            # 🔥 MEJORADO: Verificar todas las variantes del nodo 94
            is_target_node = (str(node_id) == "94" or node_id == 94)
            
            # Probar ambas claves posibles (videos primero, luego gifs como fallback)
            for key in ["videos", "gifs"]:
                if key in node_output:
                    print(f"🔍 Procesando {key} del nodo {node_id}")
                    
                    for video_info in node_output[key]:
                        src = Path(video_info['fullpath'])
                        if src.exists():
                            # 🔥 USAR RUTA ABSOLUTA (corregido del problema anterior)
                            dest = RP_OUTPUT_DIR / f"{uuid.uuid4()}{src.suffix}"
                            shutil.copy2(src, dest)
                            
                            output_files.append({
                                "type": "video",
                                "filename": dest.name,
                                "original_path": str(src),
                                "runpod_path": str(dest),
                                "node_id": str(node_id),  # 🔥 NUEVO: Normalizar a string
                                "source_key": key,
                                "format": video_info.get('format', 'mp4'),
                                "frame_rate": video_info.get('frame_rate', 32),
                                "is_target_node": is_target_node  # Para debug
                            })
                            print(f"✅ Video copiado desde {key} (nodo {node_id}): {dest.name}")
                            print(f"   Origen: {src}")
                            print(f"   Destino en output_objects: {dest}")
                        else:
                            print(f"❌ Archivo no encontrado: {src}")
        
        if not output_files:
            print("❌ WARNING: No se encontraron archivos de salida!")
            print("🔍 Estructura completa para debug:")
            import json
            print(json.dumps(outputs, indent=2, default=str))
        
        return output_files
        
    except Exception as e:
        print(f"❌ Error extracting output files: {e}")
        import traceback
        traceback.print_exc()
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

def generate_video(input_image, prompt, negative_prompt="", width=832, height=480):
    """Generar video usando el workflow completo"""
    try:
        print("🎬 Starting video generation...")
        
       # 1. Procesar imagen de entrada (híbrido)
        saved_filename = process_image_input(input_image)
        
        # 2. Cargar y modificar workflow
        print("📝 Loading and modifying workflow...")
        with open(WORKFLOW_PATH, 'r') as f:
            workflow = json.load(f)

        # 🔥 NUEVO: Debug inicial
        print("🔍 BEFORE modifications:")
     #   debug_workflow_connections(workflow)
        
        modified_workflow = modify_workflow(workflow, saved_filename, prompt, negative_prompt, width, height)

        # 🔥 NUEVO: Debug después de modify_workflow
        print("🔍 AFTER modify_workflow:")
      #  debug_workflow_connections(modified_workflow)

                  
        # 3. Ejecutar workflow
        print("⚡ Executing workflow...")
        output_files = execute_workflow(modified_workflow) #Ejecutamos el workflow que hemos pasado por _ensure_defaults
        
        if not output_files:
            raise Exception("No output files generated")
        
        # 4. Preparar resultados (RunPod añadirá URLs automáticamente)
        print("📦 Preparing results for RunPod...")
        results = []
        
        for output_file in output_files:
            results.append({
                "type": output_file["type"],
                "filename": output_file["filename"],  # Nombre en output_objects
                "file_size": get_file_size(output_file["original_path"]),
                "node_id": output_file["node_id"],
                "source_key": output_file.get("source_key", "unknown")  # Para debug
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

def get_file_size(file_path):
    """Obtener tamaño del archivo en MB"""
    try:
        size_bytes = os.path.getsize(file_path)
        size_mb = round(size_bytes / (1024 * 1024), 2)
        return f"{size_mb} MB"
    except:
        return "Unknown"


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
    """Iniciar ComfyUI server o verificar si ya está ejecutándose"""
    # 🔥 NUEVO: Verificar si ComfyUI ya está ejecutándose
    try:
        response = requests.get(f"{COMFYUI_URL}/history", timeout=5)
        if response.status_code == 200:
            print("✅ ComfyUI already running! Reusing existing instance.")
            return True
    except Exception:
        print("🔧 ComfyUI not running, starting new instance...")
        
     # 🔥 SOLUCIÓN ELEGANTE: Verificar/crear symlink solo si no existe
    symlink_path = "/ComfyUI"
    if not (os.path.exists(symlink_path) or os.path.islink(symlink_path)):
        os.symlink(COMFYUI_PATH, symlink_path)
        print(f"🔗 Symlink creado: {symlink_path} → {COMFYUI_PATH}")
    else:
        print(f"ℹ️ {symlink_path} ya existe: se reutiliza (link o directorio).")
    
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
                "message": "No input provided"
            }
        
        # Generar video
        result = generate_video(
            job_input.get("image", ""),
            job_input.get("prompt", ""),
            job_input.get("negative_prompt", ""),
            job_input.get("width", 832),      # Valor por defecto
            job_input.get("height", 480)      # Valor por defecto
        )
        
        return result
        
    except Exception as e:
        return {
            "message": str(e)
        }

print("🚀 Starting RunPod Serverless handler...")
runpod.serverless.start({"handler": handler})
