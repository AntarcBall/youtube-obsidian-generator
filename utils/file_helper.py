# utils/file_helper.py
# 파일 이름 생성 및 저장 등 파일 관련 처리 함수들을 포함합니다.

import os
import re
import json
from .gemini_helper import generate_title_with_gemini

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

def generate_filename_from_content(content, insert_dash):
    """
    내용의 첫 줄을 기반으로 파일명을 생성합니다.
    """
    if not content:
        return "untitled"
        
    # 내용의 첫 줄을 제목으로 가정
    first_line = content.strip().split('\n')[0]
    return _sanitize_filename(first_line, insert_dash)

def _format_bold_spacing(content):
    """
    내용에서 짝수 번째 '**' 뒤에 공백을 추가하여 마크다운 뷰어에서 더 잘 보이게 합니다.
    """
    parts = content.split('**')
    if len(parts) < 3:
        return content

    new_content = parts[0]
    for i in range(1, len(parts)):
        if i % 2 == 0:
            new_content += '** ' + parts[i]
        else:
            new_content += '**' + parts[i]
    return new_content

def save_as_obsidian_note(path, content, keep_original_title=False, original_title="", insert_dash=True):
    """
    지정된 경로에 가공된 내용을 마크다운 파일로 저장합니다.
    파일 이름은 내용 또는 원본 제목에서 생성됩니다.
    """
    if not os.path.isdir(path):
        os.makedirs(path)
        print(f"'{path}' 폴더를 생성했습니다.")

    base_filename = ""
    if keep_original_title and original_title:
        base_filename = _sanitize_filename(original_title, insert_dash)
    else:
        # Gemini를 사용하여 파일명 생성
        generated_title = generate_title_with_gemini(content)
        if generated_title:
            base_filename = _sanitize_filename(generated_title, insert_dash)
        else:
            # Gemini 호출 실패 시 기존 방식으로 대체
            print("경고: Gemini 파일명 생성 실패. 내용의 첫 줄을 기반으로 파일명을 생성합니다.")
            base_filename = generate_filename_from_content(content, insert_dash)

    if not base_filename:
        base_filename = "untitled"

    filename = f"{base_filename}.md"
    file_path = os.path.join(path, filename)

    # 파일명 중복 방지
    counter = 1
    while os.path.exists(file_path):
        # 기존 파일명에서 카운터 제거 (예: title-1.md -> title.md)
        temp_base, ext = os.path.splitext(base_filename)
        temp_base = re.sub(r'-\d+', '', temp_base)
        filename = f"{temp_base}-{counter}.md"
        file_path = os.path.join(path, filename)
        counter += 1
    
    # 최종 저장 전 내용 포맷팅
    formatted_content = _format_bold_spacing(content)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(formatted_content)
    
    print(f"파일 저장 완료: {file_path}")

def log_processing_speed(log_data, filename="processing_log.csv"):
    """
    처리 속도 및 관련 데이터를 CSV 파일에 기록합니다.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(script_dir, "..", filename)
    
    # 파일이 없으면 헤더와 함께 생성
    if not os.path.exists(log_path):
        with open(log_path, 'w', encoding='utf-8', newline='') as f:
            f.write("date,model,speed_chars_per_sec\n")
            
    # 데이터 추가
    with open(log_path, 'a', encoding='utf-8', newline='') as f:
        f.write(f"{log_data['date']},{log_data['model']},{log_data['speed']}\n")