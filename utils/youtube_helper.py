# utils/youtube_helper.py
# YouTube Data API와 pytube 라이브러리를 사용하여
# 유튜브 관련 데이터를 처리하는 함수들을 포함합니다.

from googleapiclient.discovery import build
from pytubefix import YouTube
import re
import subprocess
from isodate import parse_duration
from .file_helper import load_api_key
import os
import json

YOUTUBE_API_KEY = load_api_key("myapi")
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# --- Cache Setup ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, '..', 'cache')
PROCESSED_VIDEOS_LOG_PATH = os.path.join(CACHE_DIR, 'processed_videos.json')
VIDEO_LIST_CACHE_PATH = os.path.join(CACHE_DIR, 'video_list_cache.json')

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def load_processed_videos_log():
    """처리된 비디오 ID 목록을 로그 파일에서 로드합니다."""
    if not os.path.exists(PROCESSED_VIDEOS_LOG_PATH):
        return []
    try:
        with open(PROCESSED_VIDEOS_LOG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def log_processed_video(video_id):
    """처리된 비디오 ID를 로그에 추가합니다."""
    log = load_processed_videos_log()
    if video_id not in log:
        log.append(video_id)
        try:
            with open(PROCESSED_VIDEOS_LOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(log, f, ensure_ascii=False, indent=4)
        except IOError as e:
            print(f"Error saving to processed videos log: {e}")

def load_video_list_cache():
    """JSON 캐시 파일에서 비디오 목록 데이터를 로드합니다."""
    if not os.path.exists(VIDEO_LIST_CACHE_PATH):
        return {}
    try:
        with open(VIDEO_LIST_CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_video_list_to_cache(channel_id, videos):
    """채널의 비디오 목록을 JSON 캐시에 저장합니다."""
    cache = load_video_list_cache()
    cache[channel_id] = videos
    try:
        with open(VIDEO_LIST_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=4)
    except IOError as e:
        print(f"Error saving to video list cache: {e}")

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

def get_videos_from_channel(channel_url):
    """
    채널의 모든 영상 목록을 가져옵니다.
    먼저 캐시를 확인하고, 없으면 YouTube API를 통해 가져온 후 캐시에 저장합니다.
    """
    channel_id = get_channel_id_from_url(channel_url)
    if not channel_id:
        raise ValueError("유효한 채널 URL이 아니거나 채널 ID를 찾을 수 없습니다.")

    # 1. 캐시 확인
    video_cache = load_video_list_cache()
    if channel_id in video_cache:
        print(f"'{channel_id}' 채널의 영상 목록을 캐시에서 불러옵니다.")
        return video_cache[channel_id]

    # 2. 캐시에 없는 경우 API를 통해 가져오기
    print(f"'{channel_id}' 채널의 전체 영상 목록을 API로부터 가져옵니다. 잠시만 기다려주세요...")
    try:
        res = youtube.channels().list(id=channel_id, part='contentDetails').execute()
        if not res.get('items'):
            raise ValueError(f"채널 ID '{channel_id}'에 대한 정보를 찾을 수 없습니다.")
        
        playlist_id = res['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except Exception as e:
        raise ValueError(f"채널의 업로드 목록을 가져오는 중 오류 발생: {e}")

    all_video_ids = []
    all_video_titles = {}
    next_page_token = None

    # 모든 페이지를 순회하며 영상 ID와 제목 수집
    while True:
        res = youtube.playlistItems().list(
            playlistId=playlist_id,
            part='snippet',
            maxResults=50,
            pageToken=next_page_token
        ).execute()
        
        for item in res.get('items', []):
            snippet = item.get('snippet', {})
            video_id = snippet.get('resourceId', {}).get('videoId')
            if video_id:
                title = snippet.get('title', "제목 없음")
                all_video_ids.append(video_id)
                all_video_titles[video_id] = title
        
        next_page_token = res.get('nextPageToken')
        if not next_page_token:
            break
    
    all_videos = []
    # 모든 영상의 길이를 50개씩 묶어 요청
    for i in range(0, len(all_video_ids), 50): 
        chunk_ids = all_video_ids[i:i+50]
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
                duration_formatted = parse_iso8601_duration(duration_iso)
                
                all_videos.append({
                    'id': video_id,
                    'title': all_video_titles.get(video_id, "제목 없음"),
                    'duration': duration_formatted,
                    'total_seconds': total_seconds
                })
        except Exception as e:
            print(f"영상 길이 정보를 가져오는 중 오류 발생 (ID: {chunk_ids}): {e}")

    # API에서 가져온 순서대로 정렬
    videos_dict = {v['id']: v for v in all_videos}
    sorted_videos = [videos_dict[vid_id] for vid_id in all_video_ids if vid_id in videos_dict]

    # 3. 캐시에 저장
    save_video_list_to_cache(channel_id, sorted_videos)
    
    return sorted_videos

def get_transcript(video_id, proxy_url=None):
    """
    pytubefix를 사용하여 주어진 영상 ID의 스크립트를 추출하고, 실패 시 yt-dlp로 대체합니다.
    이 함수는 더 이상 캐시를 사용하지 않습니다.
    """
    text_only = None
    word_count = 0

    try:
        video_url = f'https://www.youtube.com/watch?v={video_id}'
        yt = YouTube(video_url)
        
        available_captions = yt.captions
        caption = None

        if available_captions:
            if 'ko' in available_captions:
                caption = available_captions['ko']
            elif 'a.ko' in available_captions:
                caption = available_captions['a.ko']
            elif 'en' in available_captions:
                caption = available_captions['en']
            else:
                caption = list(available_captions)[0]

        if caption:
            srt_captions = caption.generate_srt_captions()
            text_only = re.sub(r'\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n', '', srt_captions)
            text_only = text_only.replace('\n', ' ').strip()
            word_count = len(text_only.split())
            
    except Exception as e:
        print(f"pytubefix로 자막을 가져오는 중 오류 발생 (ID: {video_id}): {e}")
        print("yt-dlp를 사용하여 다시 시도합니다...")

    # pytubefix 실패 시 또는 스크립트를 찾지 못한 경우 yt-dlp 사용
    if not text_only:
        try:
            command = [
                'yt-dlp',
                '--write-auto-sub',
                '--sub-lang', 'ko,en',
                '--sleep-subtitles', '5',
                '--skip-download',
                '--sub-format', 'vtt',
                '-o', '-', # 표준 출력으로 내보내기
                f'https://www.youtube.com/watch?v={video_id}'
            ]
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', check=True)
            vtt_content = result.stdout
            
            lines = vtt_content.strip().split('\n')
            text_parts = [line for line in lines if not line.startswith(('WEBVTT', 'Kind:', 'Language:')) and '-->' not in line and line.strip()]
            text_only = " ".join(text_parts)
            word_count = len(text_only.split())

        except subprocess.CalledProcessError as e:
            print(f"yt-dlp 실행 중 오류 발생 (ID: {video_id}): {e.stderr}")
            return None, 0
        except Exception as e:
            print(f"yt-dlp로 자막을 가져오는 중 알 수 없는 오류 발생 (ID: {video_id}): {e}")
            return None, 0

    return text_only, word_count