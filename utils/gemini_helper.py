# utils/gemini_helper.py
# Google AI (Gemini) API 관련 함수들을 포함합니다.

import google.generativeai as genai
import json
import os
import numpy as np
import time
from .file_helper import load_api_key

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

            if '```json' in response_text:
                json_part = response_text.split('```json')[1].split('```')[0].strip()
            elif 'JSON' in response_text:
                json_start_index = response_text.upper().find('JSON') + 4
                first_bracket = -1
                for char in ['[', '{']:
                    pos = response_text.find(char, json_start_index)
                    if pos != -1 and (first_bracket == -1 or pos < first_bracket):
                        first_bracket = pos
                
                if first_bracket != -1:
                    json_part = response_text[first_bracket:]
                else:
                    json_part = response_text
            else:
                json_part = response_text

            results = json.loads(json_part)
            print(f"[Gemini] Batch response received and parsed successfully.")
            return results

        except (json.JSONDecodeError, IndexError, ValueError) as e:
            last_error = e
            print(f"[Gemini] Error parsing batch response on attempt {attempt + 1}: {e}")
            if attempt < retry_count - 1:
                print("[Gemini] Retrying after a short delay...")
                time.sleep(1)
            else:
                print(f"[Gemini] All {retry_count} retries failed.")
                raw_response = response_text if 'response_text' in locals() else 'No response text captured'
                print(f"[Gemini] Raw response text: {raw_response}")
                raise BatchProcessingError(f"Failed to process batch after {retry_count} attempts. Last error: {last_error}\nRaw response: {raw_response}")

    # 이 코드는 이제 실행되지 않지만, 만약의 경우를 대비해 남겨둡니다.
    raise BatchProcessingError(f"An unexpected error occurred in process_batch_with_gemini after {retry_count} retries.")
