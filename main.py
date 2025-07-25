# main.py
# tkinter를 사용하여 GUI 애플리케이션을 생성하고 전체 프로세스를 제어합니다.

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import queue
import json
import os
from datetime import datetime
import pytz
import time
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')
from utils import youtube_helper, gemini_helper, file_helper

def load_config(filepath="config.json"):
    """JSON 파일에서 설정을 로드합니다."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, filepath)
    defaults = {
        "font_size": 12, 
        "theme": "dark",
        "obsidian_path": "C:/Users/bounc/OneDrive/Document/SummerVCT/Notes",
        "gemini_batch_size": 30,
        "youtube_url": "https://www.youtube.com/@slow_doctor",
        "min_video_duration": 120, # Default to 2 minutes (120 seconds)
        "run_ip_test": True, # Default to True
        "gemini_model": "gemini-2.0-flash", # Default Gemini model
        "list_load_batch_size": 50, # Default to 50
        "include_shorts": False, # Default to False
        "keep_original_title": False, # Default to False
        "auto_quit_on_completion": False, # Default to False
        "ignore_shorter_duplicates": False # Default to False
    }

    if not os.path.exists(config_path):
        return defaults

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # 모든 키에 대해 get을 사용하여 기본값 처리
            for key, value in defaults.items():
                if key not in config:
                    config[key] = value
            return config
    except (json.JSONDecodeError, IOError):
        return defaults

def load_prompt_from_json(filepath="default_prompt.json"):
    """JSON 파일에서 기본 프롬프트를 로드합니다."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, filepath)
    
    if not os.path.exists(json_path):
        print(f"경고: {json_path} 파일을 찾을 수 없습니다. 기본 프롬프트를 사용합니다.")
        return "다음 텍스트를 요약하고 정리해주세요:\n\n"
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("prompt", "다음 텍스트를 요약하고 정리해주세요:\n\n")
    except (json.JSONDecodeError, IOError) as e:
        print(f"경고: 프롬프트 파일 로딩 실패 - {e}. 기본 프롬프트를 사용합니다.")
        return "다음 텍스트를 요약하고 정리해주세요:\n\n"

def save_config(config, filepath="config.json"):
    """지정된 설정 객체를 JSON 파일에 저장합니다."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, filepath)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    except IOError as e:
        print(f"설정 파일 저장 실패: {e}")

# --- 기본 설정 ---
DEFAULT_PROMPT = load_prompt_from_json()
CONFIG = load_config()
print(f"Loaded gemini_batch_size from config: {CONFIG.get('gemini_batch_size')}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube 스크립트 분석기")
        self.geometry("1224x568")

        # --- UI 상태 변수 ---
        self.font_size = CONFIG['font_size']
        self.is_dark_mode = tk.BooleanVar(value=(CONFIG['theme'] == 'dark'))
        self.include_shorts = tk.BooleanVar(value=CONFIG.get('include_shorts', False))
        self.min_duration_seconds = tk.IntVar(value=CONFIG.get('min_video_duration', 120))
        self.max_duration_seconds = tk.IntVar(value=CONFIG.get('max_video_duration', 3600)) # Default to 60 minutes (3600 seconds)
        self.keep_original_title = tk.BooleanVar(value=CONFIG.get('keep_original_title', False))
        self.auto_quit_on_completion = tk.BooleanVar(value=CONFIG.get('auto_quit_on_completion', False))
        self.insert_dash_in_titles = tk.BooleanVar(value=CONFIG.get('insert_dash_in_titles', True))
        self.ignore_shorter_duplicates = tk.BooleanVar(value=CONFIG.get('ignore_shorter_duplicates', False))
        self.gemini_model_var = tk.StringVar(value=CONFIG.get('gemini_model', 'gemini-2.0-flash-lite'))
        
        # --- 스타일 설정 ---
        self.style = ttk.Style(self)
        self.update_styles()

        self.q = queue.Queue()
        self.after(100, self.process_queue)

        self.current_scene = None
        self.current_scene = self.create_scene1()
        self.update_styles() # 초기 다크모드 적용

        self.all_videos = [] # 모든 로드된 영상을 저장할 리스트
        self.next_page_token = None # 다음 페이지 로드를 위한 토큰
        self.channel_url_for_batch = None # 현재 로드 중인 채널 URL

    def _normalize_title_for_deduplication(self, title):
        """Deduplication을 위해 영상 제목을 정규화합니다."""
        # 소문자로 변환
        title = title.lower()
        # 괄호와 그 안의 내용 제거 (e.g., [Full], (Official))
        title = re.sub(r'\[.*?\]', '', title)
        title = re.sub(r'\(.*?\)', '', title)
        # 특수문자를 공백으로 변환 (알파벳, 숫자, 한글, 공백 제외)
        title = re.sub(r'[^\w\s가-힣]', ' ', title)
        # 여러 공백을 하나로
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    def update_styles(self):
        """UI의 폰트와 색상 테마를 업데이트합니다."""
        font_family = "Helvetica"
        current_font = (font_family, self.font_size)
        heading_font = (font_family, int(self.font_size * 1.2), "bold")

        if self.is_dark_mode.get():
            bg_color, fg_color, entry_bg, btn_bg, tree_bg, tree_heading_bg = "#2E2E2E", "#FFFFFF", "#3C3C3C", "#555555", "#3C3C3C", "#555555"
            self.configure(bg=bg_color)
            self.style.theme_use('clam')
        else:
            bg_color, fg_color, entry_bg, btn_bg, tree_bg, tree_heading_bg = "#F0F0F0", "#000000", "#FFFFFF", "#E1E1E1", "#FFFFFF", "#E1E1E1"
            self.configure(bg=bg_color)
            self.style.theme_use('default')

        self.style.configure('.', background=bg_color, foreground=fg_color, font=current_font)
        self.style.configure('TLabel', background=bg_color, foreground=fg_color)
        self.style.configure('TButton', background=btn_bg, foreground=fg_color, font=current_font)
        self.style.map('TButton', background=[('active', '#6E6E6E' if self.is_dark_mode.get() else '#C0C0C0')])
        self.style.configure('TEntry', fieldbackground=entry_bg, foreground=fg_color, insertcolor=fg_color)
        self.style.configure('Treeview', background=tree_bg, fieldbackground=tree_bg, foreground=fg_color, rowheight=self.font_size + 10)
        self.style.configure('Treeview.Heading', background=tree_heading_bg, foreground=fg_color, font=heading_font)
        self.style.map('Treeview.Heading', background=[('active', '#6E6E6E' if self.is_dark_mode.get() else '#D0D0D0')])

        if hasattr(self, 'prompt_text') and self.prompt_text.winfo_exists():
            self.prompt_text.config(bg=entry_bg, fg=fg_color, insertbackground=fg_color, font=current_font)
        
        if hasattr(self, 'progress_text') and self.progress_text.winfo_exists():
            self.progress_text.config(bg=entry_bg, fg=fg_color, font=current_font)
            
    def update_min_duration_label(self, *args):
        total_seconds = self.min_duration_seconds.get()
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        self.min_duration_label.config(text=f"{minutes}분 {seconds}초")

    def update_max_duration_label(self, *args):
        total_seconds = self.max_duration_seconds.get()
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        self.max_duration_label.config(text=f"{minutes}분 {seconds}초")

    def change_font_size(self, delta):
        new_size = self.font_size + delta
        if 8 <= new_size <= 24:
            self.font_size = new_size
            self.update_styles()
            
    def switch_scene(self, new_scene_creator, *args):
        if self.current_scene:
            self.current_scene.destroy()
        self.current_scene = new_scene_creator(*args)
        self.update_styles()

    def create_scene1(self):
        scene1 = ttk.Frame(self, padding=(20, 10))
        scene1.pack(fill="both", expand=True)

        control_frame = ttk.Frame(scene1)
        control_frame.pack(fill='x', pady=(0, 10), anchor='n')

        # 첫 번째 줄 체크박스
        row1_frame = ttk.Frame(control_frame)
        row1_frame.pack(fill='x')
        ttk.Checkbutton(row1_frame, text="다크 모드", variable=self.is_dark_mode, command=self.update_styles).pack(side="left", padx=10)
        ttk.Checkbutton(row1_frame, text="Shorts 영상 포함", variable=self.include_shorts).pack(side="left", padx=10)
        ttk.Checkbutton(row1_frame, text="제목 원본 유지", variable=self.keep_original_title).pack(side="left", padx=10)

        # 두 번째 줄 체크박스
        row2_frame = ttk.Frame(control_frame)
        row2_frame.pack(fill='x', pady=(5, 0))
        ttk.Checkbutton(row2_frame, text="완료 시 자동 종료", variable=self.auto_quit_on_completion).pack(side="left", padx=10)
        ttk.Checkbutton(row2_frame, text="제목에 대시 삽입", variable=self.insert_dash_in_titles).pack(side="left", padx=10)
        ttk.Checkbutton(row2_frame, text="중복 영상 짧은 제목 무시", variable=self.ignore_shorter_duplicates).pack(side="left", padx=10)

        # 슬라이더 프레임
        sliders_frame = ttk.Frame(control_frame)
        sliders_frame.pack(fill='x', pady=(5, 0))



        # 슬라이더 프레임
        sliders_frame = ttk.Frame(control_frame)
        sliders_frame.pack(fill='x', pady=(5, 0))

        # 최소 영상 길이 설정 (슬라이더)
        min_duration_frame = ttk.Frame(sliders_frame)
        min_duration_frame.pack(side="left", padx=10)
        ttk.Label(min_duration_frame, text="최소 영상 길이 (분):").pack(side="left")
        self.min_duration_slider = ttk.Scale(min_duration_frame , length=150,from_=0, to=60, orient="horizontal", variable=self.min_duration_seconds, command=self.update_min_duration_label)
        self.min_duration_slider.pack(side="left", padx=5)
        self.min_duration_label = ttk.Label(min_duration_frame, text="2분 0초")
        self.min_duration_label.pack(side="left")
        self.update_min_duration_label() # 초기값 설정

        # 최대 영상 길이 설정 (슬라이더)
        max_duration_frame = ttk.Frame(sliders_frame)
        max_duration_frame.pack(side="left", padx=10)
        ttk.Label(max_duration_frame, text="최대 영상 길이 (분):").pack(side="left")
        self.max_duration_slider = ttk.Scale(max_duration_frame, length=500,from_=0, to=3000, orient="horizontal", variable=self.max_duration_seconds, command=self.update_max_duration_label)
        self.max_duration_slider.pack(side="left", padx=5)
        self.max_duration_label = ttk.Label(max_duration_frame, text="20분 0초")
        self.max_duration_label.pack(side="left")
        self.update_max_duration_label() # 초기값 설정

        # Gemini 모델 선택 라디오 버튼
        model_frame = ttk.Frame(control_frame)
        model_frame.pack(fill='x', pady=(5, 0))
        ttk.Label(model_frame, text="Gemini 모델:").pack(side="left")
        ttk.Radiobutton(model_frame, text="1.5 Flash", variable=self.gemini_model_var, value="gemini-1.5-flash").pack(side="left", padx=2)
        ttk.Radiobutton(model_frame, text="2.0 Flash", variable=self.gemini_model_var, value="gemini-2.0-flash").pack(side="left", padx=2)
        ttk.Radiobutton(model_frame, text="2.5 Flash", variable=self.gemini_model_var, value="gemini-2.5-flash").pack(side="left", padx=2)
        ttk.Radiobutton(model_frame, text="2.0 Flash Lite", variable=self.gemini_model_var, value="gemini-2.0-flash-lite").pack(side="left", padx=2)

        main_content_frame = ttk.Frame(scene1)
        main_content_frame.pack(fill="both", expand=True, pady=10)

        # URL 입력
        url_frame = ttk.Frame(main_content_frame)
        url_frame.pack(fill='x', pady=(5, 5))
        ttk.Label(url_frame, text="YouTube 채널 URL:").pack(side="left", padx=(0, 10))
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side="left", expand=True, fill="x")
        self.url_entry.insert(0, CONFIG.get("youtube_url", ""))

        # 저장 경로 입력
        path_frame = ttk.Frame(main_content_frame)
        path_frame.pack(fill='x', pady=(0, 10))
        ttk.Label(path_frame, text="Obsidian 저장 경로:").pack(side="left", padx=(0, 10))
        self.path_entry = ttk.Entry(path_frame)
        self.path_entry.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.path_entry.insert(0, CONFIG.get("obsidian_path", ""))
        ttk.Button(path_frame, text="찾아보기", command=self.browse_path).pack(side="left")

        ttk.Label(main_content_frame, text="Gemini 프롬프트:").pack(pady=(0, 5), anchor='w')
        self.prompt_text = scrolledtext.ScrolledText(main_content_frame, height=10, relief="solid", borderwidth=1)
        self.prompt_text.pack(fill="both", expand=True, pady=(0, 15))
        self.prompt_text.insert(tk.END, DEFAULT_PROMPT)

        bottom_button_frame = ttk.Frame(main_content_frame)
        bottom_button_frame.pack(fill="x", pady=10)

        self.confirm_btn1 = ttk.Button(bottom_button_frame, text="영상 목록 불러오기", command=self.start_fetching_videos)
        self.confirm_btn1.pack(side="left", ipady=5, expand=True, fill="x")

        # 폰트 크기 조절 버튼
        ttk.Button(bottom_button_frame, text="글씨 작게", command=lambda: self.change_font_size(-1)).pack(side="right", padx=5)
        ttk.Button(bottom_button_frame, text="글씨 크게", command=lambda: self.change_font_size(1)).pack(side="right", padx=5)
        
        return scene1

    def browse_path(self):
        directory = filedialog.askdirectory()
        if directory:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, directory)

    def start_fetching_videos(self):
        self.channel_url = self.url_entry.get()
        self.obsidian_path = self.path_entry.get()
        self.user_prompt = self.prompt_text.get("1.0", tk.END)
        self.min_video_duration = self.min_duration_seconds.get()

        if not self.channel_url or not self.obsidian_path:
            messagebox.showerror("입력 오류", "채널 URL과 저장 경로는 필수입니다.")
            return

        # 설정 저장
        CONFIG['youtube_url'] = self.channel_url
        CONFIG['obsidian_path'] = self.obsidian_path
        save_config(CONFIG)

        self.confirm_btn1.config(state="disabled", text="불러오는 중...")
        self.all_videos = [] # 새 채널 로드 시 초기화
        self.next_page_token = None # 새 채널 로드 시 초기화
        self.channel_url_for_batch = self.channel_url # 현재 로드 중인 채널 URL 저장
        threading.Thread(target=self.fetch_videos_thread, daemon=True).start()

    def fetch_videos_thread(self):
        try:
            self.channel_id = youtube_helper.get_channel_id_from_url(self.channel_url)
            if not self.channel_id:
                raise ValueError("유효한 채널 ID를 찾을 수 없습니다.")

            video_cache = youtube_helper.load_video_list_cache()
            cached_data = video_cache.get(self.channel_id)

            # 캐시 데이터 형식 확인 (오래된 캐시 형식일 경우 무효화)
            if cached_data and not isinstance(cached_data, dict):
                print("오래된 형식의 캐시를 발견하여 무효화합니다. 새로 목록을 불러옵니다.")
                cached_data = None # 캐시를 무효화하여 새로 불러오도록 함

            if cached_data:
                print(f"'{self.channel_id}' 채널의 영상 목록을 캐시에서 불러옵니다.")
                self.all_videos = cached_data.get("videos", [])
                self.next_page_token = cached_data.get("nextPageToken")
            else:
                print("캐시된 영상 목록이 없습니다. API에서 새로 가져옵니다.")
                videos_batch, self.next_page_token = youtube_helper.get_videos_from_channel(
                    self.channel_url, 
                    max_results=CONFIG.get("list_load_batch_size", 100)
                )
                self.all_videos = videos_batch
                # 원본 비디오 목록을 캐시에 저장
                youtube_helper.save_video_list_to_cache(self.channel_id, self.all_videos, self.next_page_token)
            
            # 필터링과 중복 제거를 적용할 원본 데이터 복사
            videos_to_process = list(self.all_videos)

            # 중복 제거 및 필터링
            final_videos = []
            if self.ignore_shorter_duplicates.get():
                # 제목을 키로 하고 가장 긴 영상을 값으로 하는 딕셔너리
                unique_videos_by_title = {}
                for video in videos_to_process:
                    normalized_title = self._normalize_title_for_deduplication(video['title'])
                    if not normalized_title: # 정규화 후 제목이 비는 경우 건너뛰기
                        continue
                    if normalized_title not in unique_videos_by_title or \
                       video.get('total_seconds', 0) > unique_videos_by_title[normalized_title].get('total_seconds', 0):
                        unique_videos_by_title[normalized_title] = video
                final_videos = list(unique_videos_by_title.values())
            else:
                final_videos = videos_to_process

            # 필터링 및 'is_processed' 플래그 적용
            processed_log = youtube_helper.load_processed_videos_log()
            filtered_videos = []
            for video in final_videos: # final_videos를 사용
                if not self.include_shorts.get() and video['title'].strip().endswith('#비밀치트키'):
                    continue
                if video.get('total_seconds', 0) < self.min_duration_seconds.get():
                    continue
                if video.get('total_seconds', 0) > self.max_duration_seconds.get():
                    continue
                
                video['is_processed'] = video['id'] in processed_log
                filtered_videos.append(video)
            
            # UI에 표시될 비디오는 필터링된 목록이지만, self.all_videos는 원본을 유지
            self.q.put(("videos_fetched", filtered_videos))

        except Exception as e:
            self.q.put(("error", f"영상 목록 로딩 실패: {e}"))

    def create_scene2(self, videos_batch):
        scene2 = ttk.Frame(self, padding=(20, 20))
        scene2.pack(fill="both", expand=True)

        top_frame = ttk.Frame(scene2)
        top_frame.pack(fill='x', pady=(0, 10))

        ttk.Label(top_frame, text="처리할 영상을 선택하세요. (이미 처리된 항목은 파란색으로 표시됩니다)", font=("Helvetica", int(self.font_size*1.3), "bold")).pack(side="left", anchor='w')
        
        self.selection_count_label = ttk.Label(top_frame, text="선택된 항목: 0개")
        self.selection_count_label.pack(side="right", anchor='e')

        cols = ("제목", "영상 길이")
        self.tree = ttk.Treeview(scene2, columns=cols, show="headings")
        self.tree.heading("제목", text="영상 제목")
        self.tree.heading("영상 길이", text="영상 길이")
        self.tree.column("제목", width=600)
        self.tree.column("영상 길이", width=100, anchor='center')
        
        processed_color = "#5DADE2"
        self.tree.tag_configure('processed', foreground=processed_color)
        
        self.tree.pack(fill="both", expand=True, pady=10)

        scrollbar = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

        for video in videos_batch:
            tags = ('processed',) if video.get('is_processed') else ()
            self.tree.insert("", "end", values=(video['title'], video['duration']), iid=video['id'], tags=tags)
        
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

        ttk.Label(scene2, text="* Ctrl 또는 Shift 키를 사용하여 여러 영상을 선택할 수 있습니다.").pack(pady=5, anchor='w')

        button_frame = ttk.Frame(scene2)
        button_frame.pack(fill='x', pady=10)

        self.confirm_btn2 = ttk.Button(button_frame, text="선택한 영상 분석 시작", command=self.start_processing)
        self.confirm_btn2.pack(side="left", expand=True, fill="x", ipady=5, padx=(0, 5))

        self.load_more_btn = ttk.Button(button_frame, text="추가 로드", command=self.load_more_videos)
        self.load_more_btn.pack(side="right", expand=True, fill="x", ipady=5, padx=(5, 0))
        
        if not self.next_page_token:
            self.load_more_btn.config(state="disabled")
            
        return scene2

    def on_tree_select(self, event):
        """Treeview 선택 변경 시 호출되어 선택된 항목 수를 업데이트합니다."""
        selected_items = self.tree.selection()
        self.selection_count_label.config(text=f"선택된 항목: {len(selected_items)}개")

    def load_more_videos(self):
        self.load_more_btn.config(state="disabled", text="로딩 중...")
        threading.Thread(target=self._load_more_videos_thread, daemon=True).start()

    def _load_more_videos_thread(self):
        try:
            videos_batch, self.next_page_token = youtube_helper.get_videos_from_channel(
                self.channel_url,
                max_results=CONFIG.get("list_load_batch_size", 100),
                page_token=self.next_page_token
            )
            
            # 새로 로드된 비디오를 기존 원본 목록에 추가
            self.all_videos.extend(videos_batch)
            
            # 업데이트된 전체 원본 목록을 캐시에 저장
            youtube_helper.save_video_list_to_cache(self.channel_id, self.all_videos, self.next_page_token)

            # 필터링과 중복 제거를 적용할 데이터 복사
            videos_to_process = list(self.all_videos)
            
            final_videos_after_load_more = []
            if self.ignore_shorter_duplicates.get():
                unique_videos_by_title = {}
                for video in videos_to_process:
                    normalized_title = self._normalize_title_for_deduplication(video['title'])
                    if not normalized_title: # 정규화 후 제목이 비는 경우 건너뛰기
                        continue
                    if normalized_title not in unique_videos_by_title or \
                       video.get('total_seconds', 0) > unique_videos_by_title[normalized_title].get('total_seconds', 0):
                        unique_videos_by_title[normalized_title] = video
                final_videos_after_load_more = list(unique_videos_by_title.values())
            else:
                final_videos_after_load_more = videos_to_process

            # 필터링 및 'is_processed' 플래그 추가
            processed_log = youtube_helper.load_processed_videos_log()
            filtered_videos_for_all = []
            for video in final_videos_after_load_more:
                if not self.include_shorts.get() and video['title'].strip().endswith('#비밀치트키'):
                    continue
                if video.get('total_seconds', 0) < self.min_duration_seconds.get():
                    continue
                if video.get('total_seconds', 0) > self.max_duration_seconds.get():
                    continue
                video['is_processed'] = video['id'] in processed_log
                filtered_videos_for_all.append(video)

            # videos_fetched 이벤트를 사용하여 Treeview 전체 갱신
            self.q.put(("videos_fetched", filtered_videos_for_all))
        except Exception as e:
            self.q.put(("error", f"추가 영상 로딩 실패: {e}"))

    def start_processing(self):
        selected_ids = self.tree.selection()
        if not selected_ids:
            messagebox.showerror("선택 오류", "하나 이상의 영상을 선택하세요.")
            return
        
        self.selected_videos = [v for v in self.all_videos if v['id'] in selected_ids]
        
        self.switch_scene(self.create_scene3)
        threading.Thread(target=self.process_videos_thread, daemon=True).start()

    def create_scene3(self):
        scene3 = ttk.Frame(self, padding=(20, 20))
        scene3.pack(fill="both", expand=True)
        
        ttk.Label(scene3, text="작업 진행 상황", font=("Helvetica", int(self.font_size*1.3), "bold")).pack(pady=10, anchor='w')
        self.progress_text = scrolledtext.ScrolledText(scene3, height=20, relief="solid", borderwidth=1, state="disabled")
        self.progress_text.pack(fill="both", expand=True)
        
        self.update_idletasks()
        return scene3

    def process_videos_thread(self):
        total = len(self.selected_videos)
        batch_size = CONFIG.get("gemini_batch_size", 30)
        
        video_map = {v['id']: v for v in self.selected_videos}

        self.q.put(("log", f"--- 총 {total}개 영상 배치 처리 시작 ---"))
        
        # 배치 처리를 위한 루프
        for i in range(0, total, batch_size):
            batch_videos = self.selected_videos[i:i + batch_size]
            tasks = []
            for j, video in enumerate(batch_videos):
                video_id = video['id']
                video_title = video['title']
                self.q.put(("log", f"  - [{i+j+1}/{total}] '{video_title}' 스크립트 준비 중..."))
                try:
                    transcript, _ = youtube_helper.get_transcript(video_id)
                    if not transcript:
                        self.q.put(("log", f"  - 경고: '{video_title}' 스크립트를 찾을 수 없어 건너뜁니다."))
                        continue
                    
                    prompt_with_title = f"영상 제목: {video_title}\n\n{self.user_prompt}"
                    full_prompt = f"{prompt_with_title}\n\n--- 원본 스크립트 ---\n{transcript}\n--- 원본 스크립트 끝 ---"
                    tasks.append({"id": video_id, "task": full_prompt, "original_title": video_title}) # original_title 추가

                except Exception as e:
                    self.q.put(("log", f"  - ✗ 오류: '{video_title}' 스크립트 추출 중 문제 발생 - {e}"))

            if not tasks:
                self.q.put(("log", "--- 현재 배치에 처리할 작업이 없습니다. ---"))
                continue

            try:
                self.q.put(("log", f"  - Gemini API로 {len(tasks)}개 작업 배치 요청 중 (배치 {i//batch_size + 1})..."))
                results = gemini_helper.process_batch_with_gemini(tasks, self.gemini_model_var.get())
                
                result_map = {res['id']: res.get('result', f"No result found for ID {res.get('id')}") for res in results}

                for task in tasks:
                    video_id = task['id']
                    video_title = task['original_title'] # original_title 사용
                    
                    if video_id in result_map:
                        processed_content = result_map[video_id]
                        
                        # 결과에 오류 메시지가 포함되어 있는지 확인
                        if "Error processing batch response" in processed_content:
                            self.q.put(("log", f"  - ✗ 오류: '{video_title}' 처리 중 API 오류 발생 - {processed_content}"))
                            continue # 오류가 있으면 노트 저장을 건너뜀

                        self.q.put(("log", f"  - '{video_title}' 내용 가공 완료. 노트 저장 중..."))
                        file_helper.save_as_obsidian_note(self.obsidian_path, processed_content, self.keep_original_title.get(), video_title, self.insert_dash_in_titles.get())
                        
                        # 성공적으로 저장된 비디오를 로그에 기록
                        youtube_helper.log_processed_video(video_id)
                        
                        self.q.put(("log", f"  - ✓ 완료: '{video_title}' 노트 생성 완료"))
                    else:
                        self.q.put(("log", f"  - ✗ 오류: '{video_title}' 처리 결과가 없습니다."))

            except Exception as e:
                self.q.put(("log", f"  - ✗ 오류: Gemini 배치 처리 중 문제 발생 - {e}"))
            
        self.q.put(("done", "모든 작업이 완료되었습니다!"))

    def log_message(self, message):
        try:
            if hasattr(self, 'progress_text') and self.progress_text.winfo_exists():
                kst_now = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')
                self.progress_text.config(state="normal")
                if isinstance(message, tuple) and message[0] == 'progress':
                    # 마지막 줄을 캐리지 리턴으로 덮어쓰기
                    self.progress_text.delete("end-1l", "end")
                    self.progress_text.insert(tk.END, f"[{kst_now}]   - Gemini 처리 진행도: {message[1]}%\r")
                else:
                    self.progress_text.insert(tk.END, f"[{kst_now}] {message}\n")
                self.progress_text.config(state="disabled")
                self.progress_text.see(tk.END)
        except Exception as e:
            print(f"로그 메시지 표시 오류: {e}")
            print(f"원본 메시지: {message}")

    def process_queue(self):
        try:
            msg_type, data = self.q.get_nowait()
            if msg_type == "videos_fetched":
                self.switch_scene(self.create_scene2, data)
            elif msg_type == "add_videos_to_tree":
                for video in data:
                    tags = ('processed',) if video.get('is_processed') else ()
                    self.tree.insert("", "end", values=(video['title'], video['duration']), iid=video['id'], tags=tags)
                if self.next_page_token:
                    self.load_more_btn.config(state="normal", text="추가 로드")
                else:
                    self.load_more_btn.config(state="disabled", text="더 이상 영상 없음")
            elif msg_type == "error":
                messagebox.showerror("오류", data)
                if hasattr(self, 'confirm_btn1'):
                    self.confirm_btn1.config(state="normal", text="영상 목록 불러오기")
                if hasattr(self, 'load_more_btn'):
                    self.load_more_btn.config(state="normal", text="추가 로드")
            elif msg_type == "log":
                self.log_message(data)
            elif msg_type == "progress":
                self.log_message(("progress", data))
            elif msg_type == "done":
                self.log_message(f"\n--- {data} ---")
                messagebox.showinfo("완료", data)
            elif msg_type == "shutdown":
                self.log_message(f"\n--- {data} ---")
                messagebox.showerror("종료", data)
                self.destroy()

        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_queue)

if __name__ == "__main__":
    try:
        if not youtube_helper.YOUTUBE_API_KEY:
            raise ValueError("YouTube API 키가 설정되지 않았습니다. MYAPI.json 파일을 확인해주세요.")
        if not gemini_helper.GEMINI_API_KEY:
            raise ValueError("Gemini API 키가 설정되지 않았습니다. MYAPI.json 파일을 확인해주세요.")
        
        # Gemini API 접근성 확인 (config.json 설정에 따름)
        if CONFIG.get("run_ip_test", True):
            is_accessible, message = gemini_helper.check_gemini_api()
            if not is_accessible:
                # API 접근 불가 시, 사용자에게 알리고 프로그램 종료
                print(f"오류: {message}")
                messagebox.showerror("API 연결 오류", f"{message}\n\nIP가 차단되었거나 네트워크 연결에 문제가 있을 수 있습니다. 프로그램을 종료합니다.")
                sys.exit() # 프로그램 종료
            else:
                print(message) # API 접근 가능 메시지 출력
        
        app = App()
        app.mainloop()

    except ValueError as e:
        print(f"오류: {e}")
        print("MYAPI.json 파일에 유효한 API 키를 설정해주세요.")
        messagebox.showerror("설정 오류", str(e))