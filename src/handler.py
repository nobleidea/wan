import runpod
import os
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
import boto3

# 설정
COMFYUI_PATH = "/comfyui"
WORKFLOW_PATH = "/app/workflow.json"
COMFYUI_URL = "http://localhost:8188"
TARGET_NODE = "94"  # 최종 비디오 노드

def upload_video_to_digitalocean(src: Path, job_id: str) -> str:
    """공개 URL로 DigitalOcean Spaces에 업로드"""
    print(f"🚀 Subiendo a DigitalOcean Spaces...")
    
    s3_client = boto3.client(
        's3',
        region_name=os.environ["DO_SPACES_REGION"],
        endpoint_url=os.environ["DO_SPACES_ENDPOINT"],
        aws_access_key_id=os.environ["DO_SPACES_ACCESS_KEY"],
        aws_secret_access_key=os.environ["DO_SPACES_SECRET_KEY"]
    )
    
    bucket_name = os.environ["DO_SPACES_BUCKET"]
    object_key = f"videos/{job_id}/{src.name}"
    
    # 공개 ACL로 업로드
    print(f"📤 Subiendo {src.name} como público...")
    with open(src, 'rb') as file_data:
        s3_client.upload_fileobj(
            file_data,
            bucket_name,
            object_key,
            ExtraArgs={
                'ContentType': 'video/mp4',
                'ACL': 'public-read'
            }
        )
    
    # 공개 URL 생성
    public_url = f"https://{bucket_name}.{os.environ['DO_SPACES_REGION']}.digitaloceanspaces.com/{object_key}"
    
    print(f"✅ Upload exitoso!")
    print(f"🌐 URL pública: {public_url}")
    
    return public_url

def save_base64_image(base64_string, filename):
    """base64 이미지를 파일 시스템에 저장"""
    try:
        # data:image 접두사가 있으면 제거
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]

        # 필요한 경우 패딩 추가
        missing_padding = len(base64_string) % 4
        if missing_padding:
            base64_string += '=' * (4 - missing_padding)

        # base64 디코딩
        image_data = base64.b64decode(base64_string)
        image = Image.open(io.BytesIO(image_data))
        
        # 다양한 색상 모드 처리
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background
        elif image.mode == 'P':
            image = image.convert('RGB')
        elif image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        
        # 이미지 저장
        input_dir = f"{COMFYUI_PATH}/input"
        os.makedirs(input_dir, exist_ok=True)
        
        image_path = f"{input_dir}/{filename}"
        image.save(image_path, 'PNG', optimize=False, compress_level=0)
        
        print(f"✅ Image saved: {image_path}")
        return filename
        
    except Exception as e:
        print(f"❌ Error saving image: {e}")
        raise Exception(f"Failed to save input image: {e}")

def download_image_from_url(image_url):
    """URL에서 이미지 다운로드"""
    try:
        print(f"📥 Downloading image from: {image_url}")
        
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        image = Image.open(io.BytesIO(response.content))
        
        # 다양한 색상 모드 처리
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background
        elif image.mode == 'P':
            image = image.convert('RGB')
        elif image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        
        # 저장
        input_dir = f"{COMFYUI_PATH}/input"
        os.makedirs(input_dir, exist_ok=True)
        
        timestamp = int(time.time() * 1000000)
        filename = f"input_{timestamp}.png"
        image_path = f"{input_dir}/{filename}"
        
        image.save(image_path, 'PNG', optimize=False, compress_level=0)
        
        print(f"✅ Image downloaded and saved: {image_path}")
        return filename
        
    except Exception as e:
        print(f"❌ Error downloading image: {e}")
        raise Exception(f"Failed to download image: {e}")

def process_image_input(image_input):
    """모든 형식의 이미지 처리"""
    try:
        if isinstance(image_input, str):
            if image_input.startswith(("http://", "https://")):
                print("🔗 Processing image from URL")
                return download_image_from_url(image_input)
            elif image_input.startswith("data:image") or len(image_input) > 100:
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

def modify_workflow(workflow: dict, image_filename: str, prompt: str, negative_prompt: str, width: int = 832, height: int = 480) -> dict:
    """사용자 매개변수로 워크플로우 수정"""
    # 고유한 시드 생성
    unique_seed = int(time.time() * 1000000) % 2147483647
    print(f"🎲 Generated unique seed: {unique_seed}")
    
    modified_workflow = workflow.copy()
    
    # 워크플로우 노드 업데이트
    if "294" in modified_workflow and "inputs" in modified_workflow["294"]:
        modified_workflow["294"]["inputs"]["image"] = image_filename
        print(f"✅ Updated LoadImage with: {image_filename}")
    
    if "243" in modified_workflow and "inputs" in modified_workflow["243"]:
        modified_workflow["243"]["inputs"]["text"] = prompt
        print(f"✅ Updated positive prompt: {prompt[:50]}...")
    
    if "244" in modified_workflow and "inputs" in modified_workflow["244"]:
        modified_workflow["244"]["inputs"]["text"] = negative_prompt
        print(f"✅ Updated negative prompt: {negative_prompt[:50]}...")
    
    if "259" in modified_workflow and "inputs" in modified_workflow["259"]:
        modified_workflow["259"]["inputs"]["seed"] = unique_seed
        print(f"✅ Updated seed: {unique_seed}")
    
    if "236" in modified_workflow and "inputs" in modified_workflow["236"]:
        modified_workflow["236"]["inputs"]["width"] = width
        modified_workflow["236"]["inputs"]["height"] = height
        print(f"✅ Updated dimensions: {width}x{height}")
    
    return modified_workflow

def execute_workflow(job_id, workflow):
    """ComfyUI에서 워크플로우 실행 및 결과 대기"""
    try:
        prompt_id = str(uuid.uuid4())
        
        payload = {
            "prompt": workflow,
            "client_id": prompt_id
        }
        
        print(f"🚀 Sending workflow to ComfyUI...")
        
        response = requests.post(f"{COMFYUI_URL}/prompt", json=payload)
        response.raise_for_status()
        
        result = response.json()
        prompt_id = result["prompt_id"]
        print(f"✅ Workflow submitted, prompt_id: {prompt_id}")
        
        # 결과 대기
        print("⏳ Waiting for workflow execution...")
        max_wait = 900  # 15분
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            history_response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
            
            if history_response.status_code == 200:
                history = history_response.json()
                
                if prompt_id in history:
                    execution_data = history[prompt_id]
                    
                    if "outputs" in execution_data:
                        print("✅ Workflow execution completed!")
                        return extract_output_files(job_id, execution_data["outputs"])
                    
                    elif "status" in execution_data:
                        status = execution_data["status"]
                        if status.get("status_str") == "error":
                            error_msg = status.get("messages", ["Unknown error"])
                            raise Exception(f"Workflow execution failed: {error_msg}")
            
            time.sleep(5)
            
            # 30초마다 진행 상황 로그
            if int(time.time() - start_time) % 30 == 0:
                elapsed = int(time.time() - start_time)
                print(f"⏳ Still waiting... ({elapsed}s elapsed)")
        
        raise Exception("Workflow execution timeout after 15 minutes")
        
    except Exception as e:
        print(f"❌ Error executing workflow: {e}")
        raise Exception(f"Failed to execute workflow: {e}")

def extract_output_files(job_id, outputs):
    """출력 파일 추출 및 DigitalOcean에 업로드"""
    for node_id, node_output in outputs.items():
        if str(node_id) != TARGET_NODE:
            continue

        # 출력에서 비디오 검색
        for key in ("videos", "gifs"):
            if key not in node_output:
                continue

            video_info = node_output[key][0]
            src = Path(video_info["fullpath"])

            if not src.exists():
                raise FileNotFoundError(f"Video file not found: {src}")

            try:
                print(f"🚀 Subiendo {src.name}...")
                video_url = upload_video_to_digitalocean(src, job_id)
                
                return {
                    "type": "video",
                    "url": video_url,
                    "filename": src.name,
                    "original_path": str(src),
                    "file_size": f"{round(src.stat().st_size / 1_048_576, 2)} MB",
                    "node_id": TARGET_NODE
                }
                
            except Exception as e:
                print(f"❌ Error uploading video: {e}")
                raise RuntimeError(f"Failed to upload video: {e}")

    raise RuntimeError(f"No video output found in node {TARGET_NODE}")

def generate_video(job_id, input_image, prompt, negative_prompt="", width=832, height=480):
    """전체 워크플로우를 사용한 비디오 생성"""
    try:
        print("🎬 Starting video generation...")
        
        # 1. 입력 이미지 처리
        saved_filename = process_image_input(input_image)
        
        # 2. 워크플로우 로드 및 수정
        print("📝 Loading and modifying workflow...")
        with open(WORKFLOW_PATH, 'r') as f:
            workflow = json.load(f)
        
        modified_workflow = modify_workflow(workflow, saved_filename, prompt, negative_prompt, width, height)
        
        # 3. 워크플로우 실행
        output_data = execute_workflow(job_id, modified_workflow)
        
        if not output_data or "url" not in output_data:
            raise Exception("No video output generated")
        
        print(f"✅ Video generation completed. URL: {output_data['url']}")
        
        return {
            "status": "success",
            "output": output_data
        }
        
    except Exception as e:
        print(f"❌ Video generation failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

def check_models():
    """모델 가용성 확인"""
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
    """ComfyUI 서버 시작"""
    # ComfyUI가 이미 실행 중인지 확인
    try:
        response = requests.get(f"{COMFYUI_URL}/history", timeout=5)
        if response.status_code == 200:
            print("✅ ComfyUI already running!")
            return True
    except Exception:
        print("🔧 Starting ComfyUI...")
        
    os.chdir(COMFYUI_PATH)
    
    if not os.path.exists("main.py"):
        raise Exception(f"main.py not found in {COMFYUI_PATH}")
    
    # ComfyUI 시작
    cmd = ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188"]
    
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # 실시간 로그 표시
    def show_logs():
        for line in process.stdout:
            print(f"ComfyUI: {line.strip()}")
    
    thread = threading.Thread(target=show_logs, daemon=True)
    thread.start()
    
    # ComfyUI 준비 대기
    print("⏳ Waiting for ComfyUI to be ready...")
    for i in range(300):  # 5분
        try:
            response = requests.get(f"{COMFYUI_URL}/history", timeout=5)
            if response.status_code == 200:
                print("✅ ComfyUI is ready!")
                return True
        except Exception:
            if i % 30 == 0:
                print(f"⏳ Still waiting... ({i//60}m {i%60}s)")
        time.sleep(1)
    
    raise Exception("ComfyUI failed to start within 5 minutes")

def handler(event):
    """RunPod 메인 핸들러"""
    try:
        print("🚀 Starting WAN 2.1 I2V serverless handler...")
        
        # 모델 확인
        print("🔍 Checking models...")
        check_models()
        
        # ComfyUI 시작
        print("⚡ Starting ComfyUI...")
        start_comfyui()
        
        # 입력 값 가져오기
        job_input = event.get("input", {})
        job_id = event.get("id")
        
        if not job_input:
            return {"message": "No input provided"}
        
        # 비디오 생성
        result = generate_video(
            job_id,
            job_input.get("image", ""),
            job_input.get("prompt", ""),
            job_input.get("negative_prompt", ""),
            job_input.get("width", 832),
            job_input.get("height", 480)
        )
        
        return result
        
    except Exception as e:
        return {"message": str(e)}

print("🚀 Starting RunPod Serverless handler...")
runpod.serverless.start({"handler": handler})
