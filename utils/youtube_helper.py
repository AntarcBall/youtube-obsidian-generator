# utils/youtube_helper.py
# YouTube Data API와 pytube 라이브러리를 사용하여
# 유튜브 관련 데이터를 처리하는 함수들을 포함합니다.

from googleapiclient.discovery import build
from pytube import YouTube
import re
import subprocess
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
    
    res = youtube.playlistItems().list(
        playlistId=playlist_id,
        part='snippet',
        maxResults=max_results,
        pageToken=page_token
    ).execute()
    
    for item in res.get('items', []):
        snippet = item.get('snippet', {})
        title = snippet.get('title', "")
        
        if not include_shorts and title.strip().endswith('#비밀치트키'):
            continue

        if snippet.get('resourceId', {}).get('videoId'):
            video_id = snippet['resourceId']['videoId']
            video_ids.append(video_id)
            video_titles[video_id] = title

    next_page_token = res.get('nextPageToken')
    
    videos = []
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
    pytube를 사용하여 주어진 영상 ID의 스크립트를 추출하고, 실패 시 yt-dlp로 대체합니다.
    """
    try:
        video_url = f'https://www.youtube.com/watch?v={video_id}'
        yt = YouTube(video_url)
        caption = yt.captions.get_by_language_code('ko')
        if not caption:
            caption = yt.captions.get_by_language_code('en')
        if not caption and yt.caption_tracks:
            caption = yt.caption_tracks[0]

        if caption:
            srt_captions = caption.generate_srt_captions()
            text_only = re.sub(r'\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n', '', srt_captions)
            text_only = text_only.replace('\n', ' ').strip()
            return text_only, len(text_only.split())
    except Exception as e:
        print(f"pytube로 자막을 가져오는 중 오류 발생 (ID: {video_id}): {e}")
        print("yt-dlp를 사용하여 다시 시도합니다...")

    # pytube 실패 시 yt-dlp 사용
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
        return text_only, len(text_only.split())

    except subprocess.CalledProcessError as e:
        print(f"yt-dlp 실행 중 오류 발생 (ID: {video_id}): {e.stderr}")
        return None, 0
    except Exception as e:
        print(f"yt-dlp로 자막을 가져오는 중 알 수 없는 오류 발생 (ID: {video_id}): {e}")
        return None, 0