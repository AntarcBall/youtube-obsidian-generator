# utils/config_helper.py
# API 키 및 기타 설정 로드와 관련된 함수들을 포함합니다.

import os
import json

def load_api_key(key_name="myapi", filepath="MYAPI.json"):
    """
    지정된 JSON 파일에서 API 키를 로드합니다.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 상위 디렉토리로 이동하여 MYAPI.json 찾기
    json_path = os.path.join(script_dir, "..", filepath) 
    
    if not os.path.exists(json_path):
        print(f"경고: {json_path} 파일을 찾을 수 없습니다.")
        return None
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get(key_name)
    except (json.JSONDecodeError, IOError) as e:
        print(f"경고: API 키 파일 로딩 실패 - {e}.")
        return None
