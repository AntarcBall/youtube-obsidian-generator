# utils/youtube_helper.py
# YouTube Data API와 youtube-transcript-api 라이브러리를 사용하여
# 유튜브 관련 데이터를 처리하는 함수들을 포함합니다.

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
import re
from isodate import parse_duration
from .file_helper import load_api_key

YOUTUBE_API_KEY = load_api_key("myapi")
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

def parse_iso8601_duration(duration_str):
    """ISO 8601 형식의 기간을 'HH:MM:SS' 또는 'MM:SS' 형태로 변환합니다."""
    try:
        duration = parse_duration(duration_str)
        total_seconds = int(duration.total_seconds())
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        else:
            return f"{minutes:02}:{seconds:02}"
    except:
        return "00:00" # 기간 파싱 오류 시 기본값

def get_channel_id_from_url(url):
    """
    다양한 형태의 유튜브 URL에서 채널 ID를 안정적으로 추출합니다.
    """
    # 1. /channel/UC... 형식 (가장 확실한 ID)
    match = re.search(r'(?:youtube\.com/channel/)(UC[a-zA-Z0-9_-]{22})', url)
    if match:
        return match.group(1)

    # 2. /@handle, /c/, /user/ 형식 (검색 필요)
    searchable_patterns = [
        r'(?:youtube\.com/@)([^/?&]+)',
        r'(?:youtube\.com/c/)([^/?&]+)',
        r'(?:youtube\.com/user/)([^/?&]+)'
    ]
    for pattern in searchable_patterns:
        match = re.search(pattern, url)
        if match:
            identifier = match.group(1)
            try:
                search_response = youtube.search().list(
                    q=identifier,
                    part='id',
                    type='channel',
                    maxResults=1
                ).execute()
                # API 응답에 'items'가 있고, 비어있지 않은지 확인
                if search_response and search_response.get('items'):
                    return search_response['items'][0]['id']['channelId']
            except Exception as e:
                print(f"'{identifier}'로 채널 ID를 검색하는 중 오류 발생: {e}")
                return None # 검색 실패 시 None 반환
    return None

def get_videos_from_channel(channel_url, include_shorts=False, min_duration_seconds=0, max_results=50, page_token=None):
    """
    채널의 영상 목록을 지정된 개수만큼 가져와 반환합니다.
    page_token을 사용하여 다음 페이지를 가져올 수 있습니다.
    """
    channel_id = get_channel_id_from_url(channel_url)
    if not channel_id:
        raise ValueError("유효한 채널 URL이 아니거나 채널 ID를 찾을 수 없습니다.")

    try:
        res = youtube.channels().list(id=channel_id, part='contentDetails').execute()
        if not res.get('items'):
            raise ValueError(f"채널 ID '{channel_id}'에 대한 정보를 찾을 수 없습니다.")
        
        playlist_id = res['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except Exception as e:
        raise ValueError(f"채널의 업로드 목록을 가져오는 중 오류 발생: {e}")

    video_ids = []
    video_titles = {}
    
    # 첫 번째 요청에서 maxResults를 사용하여 지정된 개수만큼만 가져옵니다.
    # 이후 요청에서는 page_token을 사용하여 다음 페이지를 가져옵니다.
    res = youtube.playlistItems().list(
        playlistId=playlist_id,
        part='snippet',
        maxResults=max_results, # 요청된 max_results 사용
        pageToken=page_token
    ).execute()
    
    for item in res.get('items', []):
        snippet = item.get('snippet', {})
        title = snippet.get('title', "")
        
        # Shorts 영상 필터링
        if not include_shorts and title.strip().endswith('#비밀치트키'):
            continue

        if snippet.get('resourceId', {}).get('videoId'):
            video_id = snippet['resourceId']['videoId']
            video_ids.append(video_id)
            video_titles[video_id] = title

    next_page_token = res.get('nextPageToken')
    
    videos = []
    # video_ids가 50개 미만일 수도 있으므로 len(video_ids)를 사용
    for i in range(0, len(video_ids), 50): 
        chunk_ids = video_ids[i:i+50]
        try:
            video_details_res = youtube.videos().list(
                id=','.join(chunk_ids),
                part='contentDetails'
            ).execute()

            for item in video_details_res.get('items', []):
                video_id = item['id']
                duration_iso = item.get('contentDetails', {}).get('duration', 'PT0S')
                duration_parsed = parse_duration(duration_iso)
                total_seconds = int(duration_parsed.total_seconds())

                # 최소 영상 길이 필터링
                if total_seconds < min_duration_seconds:
                    continue

                duration_formatted = parse_iso8601_duration(duration_iso)
                
                videos.append({
                    'id': video_id,
                    'title': video_titles.get(video_id, "제목 없음"),
                    'duration': duration_formatted,
                    'total_seconds': total_seconds
                })
        except Exception as e:
            print(f"영상 길이 정보를 가져오는 중 오류 발생 (ID: {chunk_ids}): {e}")

    videos_dict = {v['id']: v for v in videos}
    sorted_videos = [videos_dict[vid_id] for vid_id in video_ids if vid_id in videos_dict]

    return sorted_videos, next_page_token

def get_transcript(video_id, proxy_url=None):
    """
    주어진 영상 ID의 스크립트를 우선순위에 따라 추출하여 텍스트와 세그먼트 수를 반환합니다.
    개선된 자막 검색 및 오류 처리 포함.
    """
    print(f"[자막 검색] 영상 ID: {video_id}")
    
    proxies = None
    if proxy_url and proxy_url.strip():
        proxies = {'http': proxy_url.strip(), 'https': proxy_url.strip()}

    try:
        # 자막 목록 가져오기
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxies)
        
        # 사용 가능한 자막 목록 출력
        available_transcripts = []
        for transcript in transcript_list:
            lang_code = transcript.language_code
            lang_name = getattr(transcript, 'language', lang_code)
            is_generated = transcript.is_generated
            is_translatable = transcript.is_translatable
            status = "자동생성" if is_generated else "수동작성"
            translatable = " (번역가능)" if is_translatable else ""
            available_transcripts.append(f"{lang_name}({lang_code}) - {status}{translatable}")
        
        print(f"[자막 검색] 사용 가능한 자막: {len(available_transcripts)}개")
        for transcript_info in available_transcripts:
            print(f"  - {transcript_info}")
        
    except NoTranscriptFound:
        print(f"[자막 검색] 자막 없음: {video_id}")
        return None, 0
    except TranscriptsDisabled:
        print(f"[자막 검색] 자막 비활성화: {video_id}")
        return None, 0
    except Exception as e:
        print(f"[자막 검색] 오류 발생: {e}")
        return None, 0

    # 자막 검색 우선순위 정의
    search_priorities = [
        # 1. 한국어 수동 자막
        ("한국어 수동 자막", lambda: transcript_list.find_manually_created_transcript(['ko', 'ko-KR', 'kor'])),
        
        # 2. 한국어 자동생성 자막
        ("한국어 자동생성 자막", lambda: transcript_list.find_generated_transcript(['ko', 'ko-KR', 'kor'])),
        
        # 3. 영어 수동 자막
        ("영어 수동 자막", lambda: transcript_list.find_manually_created_transcript(['en', 'en-US', 'en-GB'])),
        
        # 4. 영어 자동생성 자막
        ("영어 자동생성 자막", lambda: transcript_list.find_generated_transcript(['en', 'en-US', 'en-GB'])),
        
        # 5. 직접 검색 - 한국어 관련
        ("한국어 직접 검색", lambda: find_korean_transcript_direct(transcript_list)),
        
        # 6. 번역 가능한 자막 → 한국어 번역
        ("한국어 번역", lambda: find_translatable_to_korean(transcript_list)),
        
        # 7. 번역 가능한 자막 → 영어 번역
        ("영어 번역", lambda: find_translatable_to_english(transcript_list)),
        
        # 8. 첫 번째 사용 가능한 자막
        ("첫 번째 자막", lambda: get_first_available_transcript(transcript_list))
    ]
    
    # 우선순위에 따라 자막 검색 시도
    for priority_name, search_func in search_priorities:
        try:
            print(f"[자막 검색] {priority_name} 시도 중...")
            transcript = search_func()
            if transcript:
                print(f"[자막 검색] {priority_name} 성공!")
                return extract_transcript_text(transcript, video_id)
        except NoTranscriptFound:
            print(f"[자막 검색] {priority_name} - 자막 없음")
            continue
        except Exception as e:
            print(f"[자막 검색] {priority_name} - 오류: {e}")
            continue

    print(f"[자막 검색] 모든 시도 실패: {video_id}")
    return None, 0

def find_korean_transcript_direct(transcript_list):
    """한국어 자막을 직접 검색"""
    for transcript in transcript_list:
        lang_code = transcript.language_code.lower()
        if any(korean in lang_code for korean in ['ko', 'kor', 'korean']):
            return transcript
    raise NoTranscriptFound("한국어 자막을 찾을 수 없습니다")

def find_translatable_to_korean(transcript_list):
    """번역 가능한 자막을 한국어로 번역"""
    for transcript in transcript_list:
        if transcript.is_translatable:
            try:
                return transcript.translate('ko')
            except Exception as e:
                print(f"[자막 번역] {transcript.language_code} → 한국어 실패: {e}")
                continue
    raise NoTranscriptFound("번역 가능한 자막을 찾을 수 없습니다")

def find_translatable_to_english(transcript_list):
    """번역 가능한 자막을 영어로 번역"""
    for transcript in transcript_list:
        if transcript.is_translatable:
            try:
                return transcript.translate('en')
            except Exception as e:
                print(f"[자막 번역] {transcript.language_code} → 영어 실패: {e}")
                continue
    raise NoTranscriptFound("번역 가능한 자막을 찾을 수 없습니다")

def get_first_available_transcript(transcript_list):
    """첫 번째 사용 가능한 자막 반환"""
    for transcript in transcript_list:
        return transcript
    raise NoTranscriptFound("사용 가능한 자막이 없습니다")

def extract_transcript_text(transcript, video_id):
    """
    자막 객체에서 텍스트와 세그먼트 수를 안전하게 추출합니다.
    """
    try:
        print(f"[자막 추출] 자막 데이터 가져오는 중...")
        fetched_transcript = transcript.fetch()
        
        if not fetched_transcript:
            print(f"[자막 추출] 빈 자막 데이터")
            return None, 0
        
        segment_count = len(fetched_transcript)
        print(f"[자막 추출] 자막 세그먼트 수: {segment_count}")
        
        # 자막 조각들을 텍스트로 변환
        text_parts = []
        for i, segment in enumerate(fetched_transcript):
            try:
                if isinstance(segment, dict) and 'text' in segment:
                    text_parts.append(segment['text'])
                elif hasattr(segment, 'text'):
                    text_parts.append(segment.text)
                else:
                    print(f"[자막 추출] 알 수 없는 세그먼트 형태 (인덱스 {i}): {type(segment)}")
            except Exception as e:
                print(f"[자막 추출] 세그먼트 {i} 처리 오류: {e}")
                continue
        
        if not text_parts:
            print(f"[자막 추출] 추출된 텍스트가 없음")
            return None, 0
        
        full_transcript = " ".join(text_parts)
        print(f"[자막 추출] 완료 - 총 {len(full_transcript)} 문자")
        
        # 텍스트 샘플 출력 (처음 200자)
        sample_text = full_transcript[:200] + "..." if len(full_transcript) > 200 else full_transcript
        print(f"[자막 추출] 텍스트 샘플: {sample_text}")
        
        return full_transcript, segment_count
        
    except Exception as e:
        print(f"[자막 추출] 오류 발생: {e}")
        # Check for the specific "no element found" error
        if "no element found" in str(e):
            print(f"[자막 추출] XML 파싱 오류: 자막이 비어있을 수 있습니다.")
            return None, 0
        return None, 0