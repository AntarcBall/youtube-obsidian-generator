import os

def add_space_after_even_bold(directory):
    """
    지정된 디렉토리의 모든 .md 파일에서 짝수 번째 '**' 뒤에 공백을 추가합니다.

    Args:
        directory (str): 대상 디렉토리 경로.
    """
    try:
        # 현재 디렉토리의 파일 목록을 가져옵니다.
        files_in_directory = os.listdir(directory)
    except FileNotFoundError:
        print(f"오류: 디렉토리를 찾을 수 없습니다: '{directory}'")
        return

    # .md 확장자를 가진 파일만 필터링합니다.
    md_files = [f for f in files_in_directory if f.endswith('.md')]

    if not md_files:
        print("처리할 .md 파일을 찾지 못했습니다.")
        return

    print(f"총 {len(md_files)}개의 .md 파일을 처리합니다.")

    # 각 .md 파일에 대해 작업을 수행합니다.
    for filename in md_files:
        filepath = os.path.join(directory, filename)
        print(f"-> 처리 중: {filename}")

        try:
            # 파일을 읽기 모드로 엽니다.
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # '**'를 기준으로 문자열을 분리합니다.
            parts = content.split('**')
            
            # 분리된 조각이 3개 미만이면 (즉, '**'가 2개 미만이면) 처리할 필요가 없습니다.
            if len(parts) < 3:
                print(f"   '{filename}' 파일에는 수정할 내용이 없습니다.")
                continue

            # 새로운 내용을 저장할 변수를 초기화합니다.
            new_content = parts[0]

            # 분리된 조각들을 다시 합치면서 규칙을 적용합니다.
            for i in range(1, len(parts)):
                # i가 짝수일 때 (두 번째, 네 번째... '**'에 해당) 뒤에 공백을 추가합니다.
                if i % 2 == 0:
                    new_content += '** ' + parts[i]
                else:
                    new_content += '**' + parts[i]

            # 수정된 내용으로 파일을 덮어씁니다.
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"   '{filename}' 파일 수정 완료.")

        except Exception as e:
            print(f"오류: '{filename}' 파일 처리 중 예외 발생 - {e}")

if __name__ == "__main__":
    # 스크립트가 실행되는 현재 디렉토리를 대상으로 합니다.
    current_directory = '.'
    add_space_after_even_bold(current_directory)
    print("\n모든 작업이 완료되었습니다.")
