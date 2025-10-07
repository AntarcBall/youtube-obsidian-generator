# utils/gemini_helper.py
# Google AI (Gemini) API 관련 함수들을 포함합니다.

import google.generativeai as genai
import json
import os
import re
import numpy as np
import time
from .config_helper import load_api_key

class BatchProcessingError(Exception):
    """배치 처리가 모든 재시도 후에도 실패했을 때 발생하는 예외입니다."""
    pass

GEMINI_API_KEY = load_api_key("myapi")
genai.configure(api_key=GEMINI_API_KEY)

def get_embeddings(texts, model="embedding-001"):
    """
    주어진 텍스트 목록에 대한 임베딩을 생성합니다.
    """
    return genai.embed_content(model=model,
                                content=texts,
                                task_type="RETRIEVAL_QUERY")

def calculate_cosine_similarity(vec1, vec2):
    """
    두 벡터 간의 코사인 유사도를 계산합니다.
    """
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

def load_gemini_config():
    """config.json에서 Gemini 관련 설정을 로드합니다."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return {
                "model": config.get("gemini_model", "gemini-1.5-flash"),
                "retry_count": config.get("gemini_retry_count", 3)
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "model": "gemini-1.5-flash",
            "retry_count": 3
        }

def check_gemini_api():
    """
    Gemini API에 간단한 요청을 보내 접근성을 확인합니다.
    config.json에 지정된 모델을 사용합니다.
    """
    try:
        gemini_config = load_gemini_config()
        model_name = gemini_config["model"]
        print(f"Checking Gemini API accessibility with model: {model_name}")
        model = genai.GenerativeModel(model_name)
        model.generate_content("test")
        return True, f"Gemini API is accessible with model {model_name}."
    except Exception as e:
        return False, f"Failed to access Gemini API: {e}"

def process_batch_with_gemini(tasks, model_name=None):
    """
    여러 작업을 배치로 묶어 Gemini API에 한 번에 요청하고 결과를 반환합니다.
    배치 크기가 1인 경우, JSON 래핑 없이 직접 처리하여 파싱 오류를 방지합니다.
    파싱 오류 발생 시 설정된 횟수만큼 재시도하며, 최종 실패 시 BatchProcessingError를 발생시킵니다.
    
    Args:
        tasks (list): 각 항목이 {"id": "...", "task": "..."} 형태의 딕셔너리인 리스트
        model_name (str, optional): 사용할 Gemini 모델 이름. None이면 config.json에서 로드합니다.
        
    Returns:
        list: 각 항목이 {"id": "...", "result": "..."} 형태의 딕셔너리인 리스트
        
    Raises:
        BatchProcessingError: 모든 재시도 후에도 배치 처리에 실패한 경우.
    """
    gemini_config = load_gemini_config()
    effective_model_name = model_name if model_name is not None else gemini_config["model"]
    retry_count = gemini_config["retry_count"]
    
    model = genai.GenerativeModel(effective_model_name)

    # 배치 크기가 1인 경우, JSON 래핑 없이 직접 처리
    if len(tasks) == 1:
        task = tasks[0]
        task_id = task['id']
        task_content = task['task']
        
        print(f"[Gemini] Single task request sent for task ID: {task_id}")
        
        last_error = None
        for attempt in range(retry_count):
            try:
                response = model.generate_content(task_content)
                response_text = "".join([part.text for part in response.parts])
                
                if not response_text.strip():
                    raise ValueError("Received empty response from Gemini API.")
                
                print(f"[Gemini] Single task response received successfully.")
                return [{"id": task_id, "result": response_text.strip()}]
                
            except Exception as e:
                last_error = e
                print(f"[Gemini] Error processing single task on attempt {attempt + 1}: {e}")
                
                if attempt < retry_count - 1:
                    print("[Gemini] Retrying after a short delay...")
                    time.sleep(2)
                else:
                    print(f"[Gemini] All {retry_count} retries failed for single task.")
                    raise BatchProcessingError(f"Failed to process single task after {retry_count} attempts. Last error: {last_error}")
        
        # 재시도 루프 후에도 실패한 경우
        raise BatchProcessingError(f"Failed to process single task after {retry_count} attempts. Last error: {last_error}")

        # 재시도 루프 후에도 실패한 경우
        raise BatchProcessingError(f"Failed to process single task after {retry_count} attempts. Last error: {last_error}")

    # 배치 크기가 2 이상인 경우, JSON 래핑 방식 사용
    prompt = f"""
You are a bot that responds only in JSON format.
Below is a JSON array of tasks to perform. Execute the 'task' for each item and return the results as a JSON array with the corresponding 'id'.
The response MUST be a valid JSON array.
Each 'result' string must be properly escaped to be valid within a JSON string. For example, double quotes must be escaped as \", and backslashes as \\.

Example Input:
[
  {{"id": "video1", "task": "Summarize: He said \"Hello World!\""}}
]

Example Output:
[
  {{"id": "video1", "result": "He said \\\"Hello World!\\\""}}
]

Here is the actual task list:
{json.dumps(tasks, indent=2, ensure_ascii=False)}
"""
    
    last_error = None
    for attempt in range(retry_count):
        try:
            print(f"[Gemini] Batch request sent with {len(tasks)} tasks (Attempt {attempt + 1}/{retry_count}).")
            response = model.generate_content(prompt)
            
            response_text = "".join([part.text for part in response.parts])
            
            if not response_text.strip():
                raise ValueError("Received empty response from Gemini API.")

            # 정규식을 사용하여 JSON 블록을 찾습니다.
            # Markdown 코드 블록 (```json ... ```) 또는 일반 텍스트에 포함된 JSON을 모두 처리합니다.
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```|([\s\S]*\]|[{{\s\S]*\}})', response_text)
            
            if json_match:
                # 첫 번째 캡처 그룹 (```json ... ```) 또는 두 번째 캡처 그룹 (일반 JSON) 중 내용이 있는 것을 사용합니다.
                json_part = json_match.group(1) if json_match.group(1) else json_match.group(2)
                json_part = json_part.strip()
            else:
                # JSON을 찾지 못한 경우, 응답 텍스트 전체를 파싱 시도합니다.
                json_part = response_text.strip()

            results = json.loads(json_part)
            print(f"[Gemini] Batch response received and parsed successfully.")
            return results

        except (json.JSONDecodeError, IndexError, ValueError) as e:
            last_error = e
            print(f"[Gemini] Error parsing batch response on attempt {attempt + 1}: {e}")
            
            # 실패 시 원본 응답을 파일에 저장
            if 'response_text' in locals():
                error_log_path = os.path.join(os.path.dirname(__file__), '..', 'gemini_error_response.txt')
                with open(error_log_path, 'w', encoding='utf-8') as f:
                    f.write(response_text)
                print(f"[Gemini] Raw response saved to {error_log_path}")

            if attempt < retry_count - 1:
                print("[Gemini] Retrying after a short delay...")
                time.sleep(2)
            else:
                print(f"[Gemini] All {retry_count} retries failed.")
                raw_response = response_text if 'response_text' in locals() else 'No response text captured'
                raise BatchProcessingError(f"Failed to process batch after {retry_count} attempts. Last error: {last_error}\nRaw response: {raw_response}")

    # 이 코드는 이제 실행되지 않지만, 만약의 경우를 대비해 남겨둡니다.
    raise BatchProcessingError(f"An unexpected error occurred in process_batch_with_gemini after {retry_count} retries.")

def generate_title_with_gemini(content, model_name="gemini-1.5-flash"):
    """
    주어진 내용(content)을 기반으로 파일명을 생성하기 위해 Gemini API를 호출합니다.
    
    Args:
        content (str): 파일명 생성을 위한 원본 내용 (예: 유튜브 스크립트).
        model_name (str): 사용할 Gemini 모델 이름.
        
    Returns:
        str: 생성된 파일명 (정리된 문자열).
    """
    try:
        print(f"[Gemini] Generating title with model: {model_name}")
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
Please create a concise, descriptive filename based on the following text.
The filename should be in English, under 15 words, and suitable for use as a file name.
Do not include any special characters that are not allowed in filenames (e.g., \\, /, :, *, ?, \", <, >, |).
Do not include the file extension.

Content:
{content[:4000]}

Filename:
"""
        
        response = model.generate_content(prompt)
        generated_title = "".join([part.text for part in response.parts]).strip()
        
        # 추가적인 정리 작업
        sanitized_title = re.sub(r'[\\/*?:\"<>|]', "", generated_title)
        sanitized_title = re.sub(r'\s+', '-', sanitized_title)
        sanitized_title = re.sub(r'-+', '-', sanitized_title).strip('-')
        
        print(f"[Gemini] Generated title: {sanitized_title}")
        return sanitized_title
        
    except Exception as e:
        print(f"[Gemini] Error generating title: {e}")
        return None

def generate_korean_youtube_title(content):
    """
    주어진 내용의 일부를 기반으로 한국어 유튜브 영상 제목을 생성합니다.
    """
    try:
        model_name = "gemini-2.5-flash-lite"
        print(f"[Gemini] Generating Korean YouTube title with model: {model_name}")
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
다음 텍스트의 내용을 기반으로, 흥미를 유발하는 한국어 유튜브 영상 제목을 1문장으로 생성해주세요.
제목은 짧고 간결해야 합니다.

내용:
{content[:300]}

제목:
"""
        
        response = model.generate_content(prompt)
        generated_title = "".join([part.text for part in response.parts]).strip()
        
        # 제목에서 따옴표나 해시태그 제거
        generated_title = generated_title.replace('"', '').replace("'", "").replace("#", "")
        
        print(f"[Gemini] Generated Korean title: {generated_title}")
        return generated_title
        
    except Exception as e:
        print(f"[Gemini] Error generating Korean title: {e}")
        return None