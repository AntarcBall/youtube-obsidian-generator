# utils/gemini_helper.py
# Google AI (Gemini) API 관련 함수들을 포함합니다.

import google.generativeai as genai
import json
import os
from .file_helper import load_api_key

GEMINI_API_KEY = load_api_key("myapi")
genai.configure(api_key=GEMINI_API_KEY)

def load_gemini_model_from_config():
    """config.json에서 사용할 Gemini 모델 이름을 로드합니다."""
    try:
        # 스크립트의 상위 디렉토리 (프로젝트 루트)를 기준으로 config.json 경로 설정
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, '..', 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get("gemini_model", "gemini-1.5-flash")
    except (FileNotFoundError, json.JSONDecodeError):
        return "gemini-1.5-flash" # 파일이 없거나 오류 발생 시 기본값

def check_gemini_api():
    """
    Gemini API에 간단한 요청을 보내 접근성을 확인합니다.
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        model.generate_content("test")
        return True, "Gemini API is accessible."
    except Exception as e:
        return False, f"Failed to access Gemini API: {e}"

def process_batch_with_gemini(tasks, model_name=None):
    """
    여러 작업을 배치로 묶어 Gemini API에 한 번에 요청하고 결과를 반환합니다.
    
    Args:
        tasks (list): 각 항목이 {"id": "...", "task": "..."} 형태의 딕셔너리인 리스트
        model_name (str, optional): 사용할 Gemini 모델 이름. None이면 config.json에서 로드합니다.
        
    Returns:
        list: 각 항목이 {"id": "...", "result": "..."} 형태의 딕셔너리인 리스트
    """
    if model_name is None:
        model_name = load_gemini_model_from_config()
    model = genai.GenerativeModel(model_name)

    # Gemini API에 전달할 프롬프트 구성
    prompt = f"""
너는 이제부터 질문 목록에 대해 JSON 형식으로만 답변하는 봇이야.
다음은 처리해야 할 작업 목록이 담긴 JSON 배열이야. 각 항목의 'task'를 수행하고 'id'와 함께 결과를 JSON 배열 형식으로 반환해 줘.
모든 결과 문자열의 내부 큰따옴표는 `"`로 이스케이프 처리해야 해.

JSON

{json.dumps(tasks, indent=2, ensure_ascii=False)}
"""
    
    print(f"[Gemini] Batch request sent with {len(tasks)} tasks.")
    response = model.generate_content(prompt)
    
    try:
        # 응답 텍스트에서 JSON 부분만 추출
        # 응답이 "JSON\n[...]" 또는 "```json\n[...]```" 형식일 수 있음
        response_text = "".join([part.text for part in response.parts])
        
        # 응답이 비어있는 경우 처리
        if not response_text.strip():
            raise ValueError("Received empty response from Gemini API.")

        if '```json' in response_text:
            json_part = response_text.split('```json')[1].split('```')[0].strip()
        elif 'JSON' in response_text:
            # 'JSON'이라는 단어 바로 뒤부터 시작하는 JSON 콘텐츠를 찾음
            # 대소문자를 구분하지 않고, 유연하게 찾기
            json_start_index = response_text.upper().find('JSON') + 4
            # JSON 시작 부분( '[' 또는 '{' )을 찾음
            first_bracket = -1
            for char in ['[', '{']:
                pos = response_text.find(char, json_start_index)
                if pos != -1:
                    if first_bracket == -1 or pos < first_bracket:
                        first_bracket = pos
            
            if first_bracket != -1:
                json_part = response_text[first_bracket:]
            else:
                json_part = response_text # 순수 JSON만 반환된 경우로 가정

        else:
            json_part = response_text # 순수 JSON만 반환된 경우

        results = json.loads(json_part)
        print(f"[Gemini] Batch response received and parsed successfully.")
        return results
    except (json.JSONDecodeError, IndexError, ValueError) as e:
        print(f"[Gemini] Error parsing batch response: {e}")
        # response.text 대신 response_text 사용
        print(f"[Gemini] Raw response text: {response_text}")
        # 오류 발생 시, 각 태스크에 대해 오류 메시지를 포함한 결과 반환
        return [{"id": task["id"], "result": f"Error processing batch response: {e}"} for task in tasks]
