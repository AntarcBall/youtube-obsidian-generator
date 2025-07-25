# utils/file_helper.py
# 파일 이름 생성 및 저장 등 파일 관련 처리 함수들을 포함합니다.

import os
import re
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

def _sanitize_filename(title, insert_dash):
    """
    주어진 문자열을 파일 이름으로 사용할 수 있도록 정리합니다.
    """
    # 마크다운 제목 제거 (예: # 제목 -> 제목)
    sanitized_title = re.sub(r'^\s*#+\s*', '', title)
    # 파일명으로 사용할 수 없는 문자 제거
    sanitized_title = re.sub(r'[\\/*?:"<>|]', "", sanitized_title)
    # 공백 및 연속된 하이픈을 단일 하이픈으로 변경
    if insert_dash:
        filename = re.sub(r'\s+', '-', sanitized_title)
        filename = re.sub(r'-+', '-', filename).strip('-')
    else:
        filename = sanitized_title
    # 너무 길 경우 자르기 (예: 200자)
    filename = (filename[:200]) if len(filename) > 200 else filename
    return filename

def generate_filename_from_content(content, insert_dash, config):
    """
    내용의 첫 줄을 기반으로 파일명을 생성합니다.
    """
    if not content:
        return config.get("default_filename", "untitled")
        
    # 내용의 첫 줄을 제목으로 가정
    first_line = content.strip().split('\n')[0]
    return _sanitize_filename(first_line, insert_dash)

def save_as_obsidian_note(path, content, keep_original_title=False, original_title="", insert_dash=True, config=None):
    """
    지정된 경로에 가공된 내용을 마크다운 파일로 저장합니다.
    파일 이름은 내용 또는 원본 제목에서 생성됩니다.
    """
    if config is None:
        config = {}
        
    if not os.path.isdir(path):
        os.makedirs(path)
        print(f"'{path}' 폴더를 생성했습니다.")

    base_filename = ""
    if keep_original_title and original_title:
        base_filename = _sanitize_filename(original_title, insert_dash)
    
    if not base_filename:
        base_filename = generate_filename_from_content(content, insert_dash, config)

    if not base_filename:
        base_filename = config.get("default_filename", "untitled")

    filename = f"{base_filename}.md"
    file_path = os.path.join(path, filename)

    # 파일명 중복 방지
    counter = 1
    while os.path.exists(file_path):
        # 기존 파일명에서 카운터 제거 (예: title-1.md -> title.md)
        temp_base, ext = os.path.splitext(base_filename)
        temp_base = re.sub(r'-\d+$', '', temp_base)
        filename = f"{temp_base}-{counter}.md"
        file_path = os.path.join(path, filename)
        counter += 1

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"파일 저장 완료: {file_path}")