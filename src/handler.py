from runpod.serverless.utils import rp_upload
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
import boto3
from datetime import timedelta


ENDPOINT_URL = os.environ["BUCKET_ENDPOINT_URL"]   
BUCKET_NAME  = os.environ["BUCKET_NAME"]          
REGION       = os.getenv("AWS_REGION", "EU-RO-1")

s3 = boto3.client(
    "s3",
    region_name           = REGION,
    endpoint_url          = ENDPOINT_URL,
    aws_access_key_id     = os.environ["BUCKET_ACCESS_KEY_ID"],
    aws_secret_access_key = os.environ["BUCKET_SECRET_ACCESS_KEY"],
)

# Configuración
WORKSPACE_PATH = "/runpod-volume"
COMFYUI_PATH = f"{WORKSPACE_PATH}/ComfyUI"
WORKFLOW_PATH = "/app/workflow.json"
COMFYUI_URL = "http://localhost:8188"

# 🔥 NUEVO: Configuración para RunPod output. Rutas absolutas para evitar problemas con cambios de directorio
OUTPUT_DIR = Path(f"{COMFYUI_PATH}/output")           # Donde ComfyUI guarda
RP_OUTPUT_DIR = Path("/runpod-volume/output_objects")   # <- raíz del contenedor 🔥 Network volume
RP_OUTPUT_DIR.mkdir(exist_ok=True, parents=True)


TARGET_NODE = "94"          # manténlo como string. Nodo del que sacamos el vídeo en extract_outpu...


def upload_video_hybrid(src: Path, job_id: str) -> str:
    """Función híbrida mejorada que intenta múltiples métodos de subida"""
    
    # MÉTODO 1: RunPod nativo (preferido) - probar diferentes funciones
    print("🔄 Intentando RunPod upload nativo...")
    try:
        # Opción A: rp_upload con diferentes métodos
        try:
            upload_result = rp_upload.upload_file_to_bucket(
                file_name=str(src),
                bucket_creds=None
            )
            if upload_result:
                if isinstance(upload_result, dict) and 'url' in upload_result:
                    print("✅ Éxito con rp_upload.upload_file_to_bucket")
                    return upload_result['url']
                elif isinstance(upload_result, str):
                    print("✅ Éxito con rp_upload (string)")
                    return upload_result
        except AttributeError:
            print("⚠️ upload_file_to_bucket no existe, probando otros métodos...")
        
        # Opción B: rp_upload directo
        try:
            upload_result = rp_upload.upload_file(str(src))
            if upload_result:
                print("✅ Éxito con rp_upload.upload_file")
                return upload_result if isinstance(upload_result, str) else upload_result.get('url', str(upload_result))
        except AttributeError:
            print("⚠️ upload_file no existe...")
        
        # Opción C: rp_upload simple
        try:
            upload_result = rp_upload(str(src))
            if upload_result:
                print("✅ Éxito con rp_upload directo")
                return upload_result if isinstance(upload_result, str) else upload_result.get('url', str(upload_result))
        except (AttributeError, TypeError):
            print("⚠️ rp_upload directo no funciona...")
            
    except Exception as e:
        print(f"❌ RunPod nativo falló completamente: {e}")
    
    # MÉTODO 2: boto3 con configuración corregida
    print("🔄 Intentando boto3 con signature v4...")
    try:
        return upload_video_boto3_fixed(src, job_id)
    except Exception as e:
        print(f"❌ boto3 falló: {e}")
    
    # MÉTODO 3: Múltiples fallbacks locales
    print("🔄 Fallback: probando directorios locales...")
    fallback_dirs = [
        "/tmp/outputs",
        "/runpod-volume/outputs", 
        "/outputs",
        f"{WORKSPACE_PATH}/outputs",
        "/app/outputs"
    ]
    
    for output_dir_path in fallback_dirs:
        try:
            output_dir = Path(output_dir_path)
            output_dir.mkdir(exist_ok=True, parents=True)
            
            # Crear nombre único con timestamp
            timestamp = int(time.time())
            output_file = output_dir / f"{job_id}_{timestamp}_{src.name}"
            
            # Copiar archivo
            shutil.copy2(src, output_file)
            
            print(f"📁 Archivo copiado exitosamente a: {output_file}")
            
            # Verificar que el archivo se copió correctamente
            if output_file.exists() and output_file.stat().st_size > 0:
                # Devolver una URL que RunPod pueda manejar
                relative_path = str(output_file).replace("/runpod-volume", "").lstrip("/")
                return f"https://your-runpod-endpoint.com/outputs/{relative_path}"
            
        except Exception as dir_error:
            print(f"❌ Fallback a {output_dir_path} falló: {dir_error}")
            continue
    
    # MÉTODO 4: Último recurso - devolver path original
    print("🔄 Último recurso: devolviendo path original...")
    if src.exists():
        print(f"📁 Archivo existe en: {src}")
        return str(src)
    
    # Si todo falla
    raise Exception("No se pudo subir el archivo con ningún método disponible")

def upload_video_boto3_fixed(src: Path, job_id: str) -> str:
    """boto3 con configuración corregida como función separada"""
    from botocore.config import Config
    
    config = Config(signature_version='s3v4')
    s3_client = boto3.client(
        's3',
        region_name=REGION,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=os.environ["BUCKET_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["BUCKET_SECRET_ACCESS_KEY"],
        config=config
    )
    
    key = f"{job_id}/{src.name}"
    
    with open(src, "rb") as fh:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=fh,
            ContentType="video/mp4"
        )
    
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': BUCKET_NAME, 'Key': key},
        ExpiresIn=int(timedelta(days=7).total_seconds())
    )

def debug_rp_upload():
    """Debug para ver qué métodos están disponibles en rp_upload"""
    try:
        print("🔍 Debugging rp_upload capabilities...")
        print(f"rp_upload module: {rp_upload}")
        print(f"rp_upload dir: {dir(rp_upload)}")
        
        # Probar métodos comunes
        methods_to_test = [
            'upload_file_to_bucket',
            'upload_file', 
            'upload',
            'bucket_upload',
            'file_upload'
        ]
        
        for method in methods_to_test:
            if hasattr(rp_upload, method):
                print(f"✅ Método disponible: {method}")
            else:
                print(f"❌ Método no disponible: {method}")
                
    except Exception as e:
        print(f"❌ Error debugging rp_upload: {e}")

def upload_video(src: Path, job_id: str) -> str:
    from botocore.config import Config
    
    # Configuración específica para RunPod S3
    config = Config(
        signature_version='s3v4',
        region_name=REGION,
        retries={'max_attempts': 4, 'mode': 'adaptive'}
    )
    
    # Recrear el cliente S3 con la configuración correcta
    s3_client = boto3.client(
        "s3",
        region_name=REGION,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=os.environ["BUCKET_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["BUCKET_SECRET_ACCESS_KEY"],
        config=config  # ← Esta es la clave
    )
    
    key = f"{job_id}/{src.name}"
    
    # 1. Subida del archivo
    with open(src, "rb") as fh:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=fh,
            ContentType="video/mp4"
        )
    
    # 2. Generar URL presignada con la configuración correcta
    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': key
            },
            ExpiresIn=int(timedelta(days=7).total_seconds())
        )
        
        print(f"✅ URL presignada generada: {presigned_url}")
        return presigned_url
        
    except Exception as e:
        print(f"❌ Error generando URL presignada: {e}")
        raise Exception(f"Failed to generate presigned URL: {e}")

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


def execute_workflow(job_id, workflow):
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
                        # Pasa el job_id a extract_output_files
                        return extract_output_files(job_id, execution_data["outputs"]) # <-- AÑADE job_id
                    
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



def extract_output_files(job_id, outputs): # <-- Acepta job_id
    """Usar rp_upload para obtener URLs descargables y devolver la URL del video."""
    # Debug de rp_upload al inicio
    debug_rp_upload()
    
    for node_id, node_output in outputs.items():
        if str(node_id) != TARGET_NODE:  # TARGET_NODE es '94'
            continue

        # La salida puede estar en 'videos' o 'gifs', sé flexible
        for key in ("videos", "gifs"):
            if key not in node_output:
                continue

            video_info = node_output[key][0]
            # La ruta completa del archivo generado en el contenedor
            src = Path(video_info["fullpath"])

            if not src.exists():
                raise FileNotFoundError(f"El archivo de video no se encontró en la ruta: {src}")

            # Sube el archivo a RunPod y obtén la URL segura
            try:
                print(f"🚀 Subiendo {src.name} al bucket con el job_id: {job_id}")
                
                # --- Usando la llamada a la función 100% correcta ---
                video_url = upload_video_hybrid(src, job_id)
                # ----------------------------------------------------
                
                print(f"✅ Video subido exitosamente. URL: {video_url}")
                
                return {
                    "type": "video",
                    "url": video_url,
                    "filename": src.name,
                    "original_path": str(src),
                    "file_size": f"{round(src.stat().st_size / 1_048_576, 2)} MB",
                    "node_id": TARGET_NODE
                }
                
            except Exception as e:
                print(f"❌ Error al subir el video con rp_upload: {e}")
                # Si la subida falla, es un error crítico
                raise RuntimeError(f"No se pudo subir el archivo de video: {e}")

    # Si no se encuentra el nodo de salida, lanza un error
    raise RuntimeError(f"No se encontró ninguna salida de video en el nodo esperado ({TARGET_NODE})")


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

def generate_video(job_id, input_image, prompt, negative_prompt="", width=832, height=480):
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

                  
        # 3. Ejecutar workflow y obtener el diccionario con la URL
        output_data = execute_workflow(job_id, modified_workflow) # <-- AÑADE job_id
        
        if not output_data or "url" not in output_data:
            raise Exception("No se generó la URL del video de salida")
        
        print(f"✅ Generación de video completada. URL: {output_data['url']}")
        
        # 4. Devuelve el resultado incluyendo el diccionario completo de salida
        return {
            "status": "success",
            "output": output_data  # Devuelve directamente el objeto con la URL
        }
        
    except Exception as e:
        print(f"❌ La generación de video falló: {e}")
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
        job_id = event.get("id") # <-- AÑADE ESTA LÍNEA
        
        if not job_input:
            return { 
                "message": "No input provided"
            }
        
        # Generar video
        result = generate_video(
            job_id, # <-- AÑADE ESTE ARGUMENTO
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
