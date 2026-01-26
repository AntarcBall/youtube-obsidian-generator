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

sys.stdout.reconfigure(encoding='utf-8')
from utils import youtube_helper, gemini_helper, file_helper, failed_video_logger

def load_config(filepath="config.json"):
    """JSON 파일에서 설정을 로드합니다."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, filepath)
    defaults = {
        "font_size": 12, 
        "theme": "dark",
        "obsidian_path": "C:/Users/bounc/OneDrive/Document/SummerVCT/Notes",
        "gemini_batch_size": 30,
        "gemini_retry_count": 3, # Gemini API 재시도 횟수
        "youtube_url": "https://www.youtube.com/@slow_doctor",
        "min_video_duration": 120, # Default to 2 minutes (120 seconds)
        "max_video_duration": 7200, # Default to 120 minutes (7200 seconds)
        "run_ip_test": True, # Default to True
        "gemini_model": "gemini-1.5-flash", # Default Gemini model
        "list_load_batch_size": 50, # Default to 50
        "include_shorts": False, # Default to False
        "keep_original_title": False, # Default to False
        "auto_quit_on_completion": False, # Default to False
        "use_other_prompt": False,
        "split_transcript": False,
        "split_mode": "none", # "none", "half", "smart"
        "smart_split_interval": 20 # 10, 20, 30, 40
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

def load_prompt(use_other=False):
    """프롬프트 파일(.json 또는 .txt)에서 프롬프트를 로드합니다."""
    if use_other:
        filename = "other_prompt.txt"
    else:
        filename = "default_prompt.json"
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(script_dir, filename)

    if not os.path.exists(prompt_path):
        print(f"경고: {prompt_path} 파일을 찾을 수 없습니다. 기본 프롬프트를 사용합니다.")
        if use_other:
            # other_prompt.txt가 없을 경우 default_prompt.json으로 대체
            return load_prompt(use_other=False)
        return "다음 텍스트를 요약하고 정리해주세요:\n\n"

    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            if filename.endswith(".json"):
                data = json.load(f)
                return data.get("prompt", "다음 텍스트를 요약하고 정리해주세요:\n\n")
            else: # .txt 파일의 경우
                return f.read()
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
CONFIG = load_config()
DEFAULT_PROMPT = load_prompt(use_other=CONFIG.get("use_other_prompt", False))
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
        self.max_duration_seconds = tk.IntVar(value=CONFIG.get('max_video_duration', 7200)) # Default to 120 minutes (7200 seconds)
        self.keep_original_title = tk.BooleanVar(value=CONFIG.get('keep_original_title', False))
        self.auto_quit_on_completion = tk.BooleanVar(value=CONFIG.get('auto_quit_on_completion', False))
        self.insert_dash_in_titles = tk.BooleanVar(value=CONFIG.get('insert_dash_in_titles', True))
        self.gemini_model_var = tk.StringVar(value=CONFIG.get('gemini_model', 'gemini-1.5-flash'))
        self.keyword = tk.StringVar()
        self.min_cos_similarity = tk.StringVar(value="0.8")
        self.use_other_prompt = tk.BooleanVar(value=CONFIG.get('use_other_prompt', False))
        self.use_other_prompt = tk.BooleanVar(value=CONFIG.get('use_other_prompt', False))
        # self.split_transcript removed in favor of split_mode
        self.split_mode_var = tk.StringVar(value=CONFIG.get('split_mode', 'none'))
        if CONFIG.get('split_transcript', False) and self.split_mode_var.get() == 'none':
             self.split_mode_var.set('half') # Backward compatibility
        self.smart_split_interval = tk.IntVar(value=CONFIG.get('smart_split_interval', 20))
                
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
            
    def toggle_min_cos_entry(self, *args):
        if self.keyword.get().strip():
            self.min_cos_entry.config(state="normal")
        else:
            self.min_cos_entry.config(state="disabled")
            self.min_cos_similarity.set("0.8")

    def update_prompt_display(self):
        new_prompt = load_prompt(use_other=self.use_other_prompt.get())
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert(tk.END, new_prompt)
        CONFIG['use_other_prompt'] = self.use_other_prompt.get()
        save_config(CONFIG)
            
    def switch_scene(self, new_scene_creator, *args):
        if self.current_scene:
            self.current_scene.destroy()
        self.current_scene = new_scene_creator(*args)
        self.update_styles()

    def go_to_scene1(self):
        self.switch_scene(self.create_scene1)

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
        ttk.Checkbutton(row1_frame, text="다른 프롬프트 사용", variable=self.use_other_prompt, command=self.update_prompt_display).pack(side="left", padx=10)

        # 두 번째 줄 체크박스
        row2_frame = ttk.Frame(control_frame)
        row2_frame.pack(fill='x', pady=(5, 0))
        ttk.Checkbutton(row2_frame, text="완료 시 자동 종료", variable=self.auto_quit_on_completion).pack(side="left", padx=10)
        ttk.Checkbutton(row2_frame, text="제목에 대시 삽입", variable=self.insert_dash_in_titles).pack(side="left", padx=10)

        # 스크립트 분할 설정 프레임
        split_frame = ttk.LabelFrame(control_frame, text="스크립트 분할 설정", padding=(10, 5))
        split_frame.pack(fill='x', pady=(5, 0))
        
        ttk.Radiobutton(split_frame, text="분할 안 함", variable=self.split_mode_var, value="none", command=self.update_split_ui).pack(side="left", padx=5)
        ttk.Radiobutton(split_frame, text="반으로 나누기", variable=self.split_mode_var, value="half", command=self.update_split_ui).pack(side="left", padx=5)
        ttk.Radiobutton(split_frame, text="지능적 분할하기", variable=self.split_mode_var, value="smart", command=self.update_split_ui).pack(side="left", padx=5)
        
        self.smart_slider_frame = ttk.Frame(split_frame)
        self.smart_slider_frame.pack(side="left", padx=20)
        
        ttk.Label(self.smart_slider_frame, text="단위(분):").pack(side="left")
        self.smart_split_slider = ttk.Scale(self.smart_slider_frame, from_=10, to=40, orient="horizontal", variable=self.smart_split_interval, command=self.snap_smart_slider)
        self.smart_split_slider.pack(side="left", padx=5)
        self.smart_split_label = ttk.Label(self.smart_slider_frame, text="20분")
        self.smart_split_label.pack(side="left")
        
        self.update_split_ui() # 초기 상태 설정

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
        self.min_duration_slider = ttk.Scale(min_duration_frame , length=150,from_=60, to=240, orient="horizontal", variable=self.min_duration_seconds, command=self.update_min_duration_label)
        self.min_duration_slider.pack(side="left", padx=5)
        self.min_duration_label = ttk.Label(min_duration_frame, text="2분 0초")
        self.min_duration_label.pack(side="left")
        self.update_min_duration_label() # 초기값 설정

        # 최대 영상 길이 설정 (슬라이더)
        max_duration_frame = ttk.Frame(sliders_frame)
        max_duration_frame.pack(side="left", padx=10)
        ttk.Label(max_duration_frame, text="최대 영상 길이 (분):").pack(side="left")
        self.max_duration_slider = ttk.Scale(max_duration_frame, length=500,from_=0, to=12000, orient="horizontal", variable=self.max_duration_seconds, command=self.update_max_duration_label)
        self.max_duration_slider.pack(side="left", padx=5)
        self.max_duration_label = ttk.Label(max_duration_frame, text="120분 0초")
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
        ttk.Radiobutton(model_frame, text="3 Flash", variable=self.gemini_model_var, value="gemini-3-flash-preview").pack(side="left", padx=2)

        main_content_frame = ttk.Frame(scene1)
        main_content_frame.pack(fill="both", expand=True, pady=10)

        # URL 입력
        url_frame = ttk.Frame(main_content_frame)
        url_frame.pack(fill='x', pady=(5, 5))
        ttk.Label(url_frame, text="YouTube 채널 URL:").pack(side="left", padx=(0, 10))
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side="left", expand=True, fill="x")
        self.url_entry.insert(0, CONFIG.get("youtube_url", ""))

        # 키워드 입력
        keyword_frame = ttk.Frame(main_content_frame)
        keyword_frame.pack(fill='x', pady=(5, 5))
        ttk.Label(keyword_frame, text="키워드:").pack(side="left", padx=(0, 10))
        self.keyword_entry = ttk.Entry(keyword_frame, textvariable=self.keyword)
        self.keyword_entry.pack(side="left", expand=True, fill="x")

        # 최소 코사인 유사도 입력
        min_cos_frame = ttk.Frame(main_content_frame)
        min_cos_frame.pack(fill='x', pady=(5, 5))
        ttk.Label(min_cos_frame, text="최소 코사인 유사도:").pack(side="left", padx=(0, 10))
        self.min_cos_entry = ttk.Entry(min_cos_frame, textvariable=self.min_cos_similarity)
        self.min_cos_entry.pack(side="left", expand=True, fill="x")
        
        self.keyword.trace_add("write", self.toggle_min_cos_entry)
        self.toggle_min_cos_entry() # 초기 상태 설정을 위해 호출

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

    def update_split_ui(self):
        if self.split_mode_var.get() == "smart":
            for child in self.smart_slider_frame.winfo_children():
                child.configure(state="normal")
        else:
            for child in self.smart_slider_frame.winfo_children():
                child.configure(state="disabled")
                
    def snap_smart_slider(self, val):
        val = float(val)
        step = 10
        snapped_val = round(val / step) * step
        self.smart_split_interval.set(int(snapped_val))
        self.smart_split_label.config(text=f"{int(snapped_val)}분")

    def calculate_smart_splits(self, total_seconds, interval_minutes):
        unit = interval_minutes * 60
        if total_seconds < unit:
            return [total_seconds]
        
        # 61분 (20단위) -> 20, 20, 21 (OK)
        # 70분 (20단위) -> 20, 20, 30 (OK - 30 is 1.5x)
        # 75분 (20단위) -> 20, 20, 20, 15 (OK - 15 is 0.75x)
        
        count = int(total_seconds // unit)
        remainder = total_seconds % unit
        
        chunks = [unit] * count
        
        if remainder > 0:
            # 0.5배 미만이면 앞부분과 합침
            if remainder <= (0.5 * unit):
                if chunks:
                    chunks[-1] += remainder
                else:
                    chunks.append(remainder)
            else:
                chunks.append(remainder)
        
        # 만약 chunks끼리 합쳐서 너무 큰 것이 있으면 (없을 것으로 예상되지만) 확인
        # 현재 로직상 chunks[-1]은 최대 1.5 * unit 미만임 (remainder < 0.5 unit 이므로 unit + remainder < 1.5 unit)
        return chunks

    def smart_split_transcript(self, transcript, time_chunks, total_seconds):
        if not transcript:
            return []
            
        total_len = len(transcript)
        text_chunks = []
        start_idx = 0
        
        current_cumulative_time = 0
        
        for i, chunk_duration in enumerate(time_chunks):
            if i == len(time_chunks) - 1:
                # 마지막 청크는 남은 텍스트 전부 사용
                text_chunks.append(transcript[start_idx:].strip())
                break
                
            current_cumulative_time += chunk_duration
            target_ratio = current_cumulative_time / total_seconds
            target_idx = int(total_len * target_ratio)
            
            # target_idx 근처에서 가장 적절한 문장 끊김 찾기
            # 검색 범위: 전체 길이의 ±5%
            margin = max(100, int(total_len * 0.05))
            search_start = max(start_idx, target_idx - margin)
            search_end = min(total_len, target_idx + margin)
            
            candidates = []
            
            # 1. 줄바꿈 찾기
            pos = transcript.rfind('\n', search_start, search_end)
            if pos != -1: candidates.append(pos)
            pos = transcript.find('\n', search_start, search_end)
            if pos != -1: candidates.append(pos)
            
            # 2. 문장 부호 찾기
            for p in ['. ', '? ', '! ']:
                pos = transcript.rfind(p, search_start, search_end)
                if pos != -1: candidates.append(pos + 1)
                pos = transcript.find(p, search_start, search_end)
                if pos != -1: candidates.append(pos + 1)
                
            best_split = target_idx
            if candidates:
                best_split = min(candidates, key=lambda x: abs(x - target_idx))
            else:
                # 공백이라도 찾기
                pos = transcript.rfind(' ', search_start, search_end)
                if pos != -1:
                    best_split = pos

            if best_split <= start_idx:
                best_split = target_idx
                
            chunk_text = transcript[start_idx:best_split].strip()
            text_chunks.append(chunk_text)
            start_idx = best_split
            
        return text_chunks

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
        self.keyword_text = self.keyword.get().strip()

        try:
            self.min_cos_float = float(self.min_cos_similarity.get())
        except ValueError:
            messagebox.showerror("입력 오류", "최소 코사인 유사도는 숫자여야 합니다.")
            return

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
            # 채널 URL인지 플레이리스트 URL인지 확인
            playlist_id = youtube_helper.get_playlist_id_from_url(self.channel_url)
            
            if playlist_id:
                # 플레이리스트 처리
                self.playlist_id = playlist_id
                video_cache = youtube_helper.load_video_list_cache()
                cached_data = video_cache.get(f"playlist_{self.playlist_id}")

                if cached_data and not isinstance(cached_data, dict):
                    print("오래된 형식의 캐시를 발견하여 무효화합니다. 새로 목록을 불러옵니다.")
                    cached_data = None

                if cached_data:
                    print(f"'{self.playlist_id}' 플레이리스트의 영상 목록을 캐시에서 불러옵니다.")
                    self.all_videos = cached_data.get("videos", [])
                    self.next_page_token = cached_data.get("nextPageToken")
                else:
                    print("캐시된 영상 목록이 없습니다. API에서 새로 가져옵니다.")
                    videos_batch, self.next_page_token = youtube_helper.get_videos_from_playlist(
                        self.playlist_id,
                        max_results=CONFIG.get("list_load_batch_size", 100)
                    )
                    self.all_videos = videos_batch
                    youtube_helper.save_playlist_videos_to_cache(self.playlist_id, self.all_videos, self.next_page_token)
            else:
                # 채널 처리 (기존 로직)
                self.channel_id = youtube_helper.get_channel_id_from_url(self.channel_url)
                if not self.channel_id:
                    raise ValueError("유효한 채널 ID를 찾을 수 없습니다.")

                video_cache = youtube_helper.load_video_list_cache()
                cached_data = video_cache.get(self.channel_id)

                if cached_data and not isinstance(cached_data, dict):
                    print("오래된 형식의 캐시를 발견하여 무효화합니다. 새로 목록을 불러옵니다.")
                    cached_data = None

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
                    youtube_helper.save_video_list_to_cache(self.channel_id, self.all_videos, self.next_page_token)

            processed_log = youtube_helper.load_processed_videos_log()
            videos_to_process = []
            for video in self.all_videos:
                if not self.include_shorts.get() and video['title'].strip().endswith('#비밀치트키'):
                    continue
                if video.get('total_seconds', 0) < self.min_duration_seconds.get():
                    continue
                if video.get('total_seconds', 0) > self.max_duration_seconds.get():
                    continue
                
                video['is_processed'] = video['id'] in processed_log
                videos_to_process.append(video)
            
            if self.keyword_text:
                self.q.put(("log", "키워드와 영상 제목의 코사인 유사도를 계산합니다..."))
                titles = [video['title'] for video in videos_to_process]
                
                try:
                    keyword_embedding = gemini_helper.get_embeddings([self.keyword_text])['embedding']
                    title_embeddings = gemini_helper.get_embeddings(titles)['embedding']

                    for i, video in enumerate(videos_to_process):
                        similarity = gemini_helper.calculate_cosine_similarity(keyword_embedding[0], title_embeddings[i])
                        video['cosine_similarity'] = float(f"{similarity:.2f}")
                
                except Exception as e:
                    self.q.put(("error", f"코사인 유사도 계산 실패: {e}"))
                    for video in videos_to_process:
                        video['cosine_similarity'] = 0.0

                final_videos = []
                for v in videos_to_process:
                    keyword_in_title = self.keyword_text.lower() in v['title'].lower()
                    similarity_above_threshold = v.get('cosine_similarity', 0) >= self.min_cos_float
                    if keyword_in_title or similarity_above_threshold:
                        final_videos.append(v)
                videos_to_process = final_videos

            self.all_videos = videos_to_process
            # 실패한 비디오 목록을 로드하여 상태를 업데이트합니다.
            failed_ids = failed_video_logger.load_failed_videos()
            for video in self.all_videos:
                if video['id'] in failed_ids:
                    video['is_failed'] = True

            self.q.put(("videos_fetched", self.all_videos))

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
        if self.keyword_text:
            cols += ("코사인 유사도",)

        self.tree = ttk.Treeview(scene2, columns=cols, show="headings")
        self.tree.heading("제목", text="영상 제목")
        self.tree.heading("영상 길이", text="영상 길이")
        self.tree.column("제목", width=550)
        self.tree.column("영상 길이", width=80, anchor='center', stretch=tk.NO)

        if self.keyword_text:
            self.tree.heading("코사인 유사도", text="코사인 유사도")
            self.tree.column("코사인 유사도", width=130, anchor='center', stretch=tk.NO)
        
        processed_color = "#5DADE2"
        failed_color = "#FF6B6B"
        self.tree.tag_configure('processed', foreground=processed_color)
        self.tree.tag_configure('failed', foreground=failed_color)
        self.tree.tag_configure('selected', foreground=failed_color)
        
        self.tree.pack(fill="both", expand=True, pady=10)

        scrollbar = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

        for video in videos_batch:
            tags = ()
            if video.get('is_processed'):
                tags = ('processed',)
            if video.get('is_failed'):
                tags = ('failed',)

            values = (video['title'], video['duration'])
            if self.keyword_text:
                values += (video.get('cosine_similarity', 'N/A'),)
            self.tree.insert("", "end", values=values, iid=video['id'], tags=tags)
        
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

        ttk.Label(scene2, text="* Ctrl 또는 Shift 키를 사용하여 여러 영상을 선택할 수 있습니다.").pack(pady=5, anchor='w')

        button_frame = ttk.Frame(scene2)
        button_frame.pack(fill='x', pady=10)

        self.prev_btn = ttk.Button(button_frame, text="이전", command=self.go_to_scene1)
        self.prev_btn.pack(side="left", ipady=5, padx=(0, 5))

        self.confirm_btn2 = ttk.Button(button_frame, text="선택한 영상 분석 시작", command=self.start_processing)
        self.confirm_btn2.pack(side="left", expand=True, fill="x", ipady=5, padx=(0, 5))

        self.load_more_btn = ttk.Button(button_frame, text="추가 로드", command=self.load_more_videos)
        self.load_more_btn.pack(side="right", expand=True, fill="x", ipady=5, padx=(5, 0))
        
        if not self.next_page_token:
            self.load_more_btn.config(state="disabled")
            
        return scene2

    def on_tree_select(self, event):
        """Treeview 선택 변경 시 호출되어 선택된 항목 수를 업데이트하고, 선택된 항목을 빨간색으로 표시합니다."""
        selected_items = self.tree.selection()
        self.selection_count_label.config(text=f"선택된 항목: {len(selected_items)}개")

        for item_id in self.tree.get_children(""):
            current_tags = list(self.tree.item(item_id, 'tags'))
            
            # 'selected' 태그가 있으면 제거
            if 'selected' in current_tags:
                current_tags.remove('selected')

            # 현재 선택된 항목이면 'selected' 태그 추가
            if item_id in selected_items:
                current_tags.append('selected')
            
            self.tree.item(item_id, tags=tuple(current_tags))

    def load_more_videos(self):
        self.load_more_btn.config(state="disabled", text="로딩 중...")
        threading.Thread(target=self._load_more_videos_thread, daemon=True).start()

    def _load_more_videos_thread(self):
        try:
            # 채널 URL인지 플레이리스트 URL인지 확인하여 적절한 함수 호출
            playlist_id = youtube_helper.get_playlist_id_from_url(self.channel_url)
            
            if playlist_id:
                videos_batch, self.next_page_token = youtube_helper.get_videos_from_playlist(
                    playlist_id,
                    max_results=CONFIG.get("list_load_batch_size", 100),
                    page_token=self.next_page_token
                )
            else:
                videos_batch, self.next_page_token = youtube_helper.get_videos_from_channel(
                    self.channel_url,
                    max_results=CONFIG.get("list_load_batch_size", 100),
                    page_token=self.next_page_token
                )
            
            processed_log = youtube_helper.load_processed_videos_log()
            filtered_batch = []
            for video in videos_batch:
                if not self.include_shorts.get() and video['title'].strip().endswith('#비밀치트키'):
                    continue
                if video.get('total_seconds', 0) < self.min_duration_seconds.get():
                    continue
                if video.get('total_seconds', 0) > self.max_duration_seconds.get():
                    continue
                video['is_processed'] = video['id'] in processed_log
                filtered_batch.append(video)

            if self.keyword_text:
                titles = [video['title'] for video in filtered_batch]
                try:
                    keyword_embedding = gemini_helper.get_embeddings([self.keyword_text])['embedding']
                    title_embeddings = gemini_helper.get_embeddings(titles)['embedding']

                    for i, video in enumerate(filtered_batch):
                        similarity = gemini_helper.calculate_cosine_similarity(keyword_embedding[0], title_embeddings[i])
                        video['cosine_similarity'] = float(f"{similarity:.2f}")

                except Exception as e:
                    self.q.put(("error", f"코사인 유사도 계산 실패: {e}"))
                    for video in filtered_batch:
                        video['cosine_similarity'] = 0.0
                
                final_videos = []
                for v in filtered_batch:
                    keyword_in_title = self.keyword_text.lower() in v['title'].lower()
                    similarity_above_threshold = v.get('cosine_similarity', 0) >= self.min_cos_float
                    if keyword_in_title or similarity_above_threshold:
                        final_videos.append(v)
                filtered_batch = final_videos

            self.all_videos.extend(filtered_batch)
            
            # 캐시 저장 시 플레이리스트인지 채널인지에 따라 다르게 처리
            if playlist_id:
                youtube_helper.save_playlist_videos_to_cache(playlist_id, self.all_videos, self.next_page_token)
            else:
                youtube_helper.save_video_list_to_cache(self.channel_id, self.all_videos, self.next_page_token)
            
            self.q.put(("add_videos_to_tree", filtered_batch))
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
        batch_size = CONFIG.get("gemini_batch_size", 30)
        video_map = {v['id']: v for v in self.selected_videos}
        
        # 처리할 영상 목록과 배치별 실패 횟수를 관리합니다.
        videos_to_process = list(self.selected_videos)
        failure_counts = {} # Key: batch_id (tuple of video ids), Value: failure count

        total_initial_videos = len(videos_to_process)
        self.q.put(("log", f"--- 총 {total_initial_videos}개 영상 배치 처리 시작 ---"))
        
        processed_count = 0

        # 처리할 영상이 남아있는 동안 루프를 계속합니다.
        while videos_to_process:
            # 현재 처리할 배치를 가져옵니다.
            batch_videos = videos_to_process[:batch_size]
            videos_to_process = videos_to_process[batch_size:]

            tasks = []
            total_transcript_length = 0
            batch_start_time = time.time()

            # 배치 내의 각 영상에 대해 스크립트를 준비합니다.
            for video in batch_videos:
                video_id = video['id']
                video_title = video['title']
                # UI에 진행 상황을 표시합니다. (전체 영상 수 기준)
                self.q.put(("log", f"  - [{processed_count + len(tasks) + 1}/{total_initial_videos}] '{video_title}' 스크립트 준비 중..."))
                try:
                    transcript, _ = youtube_helper.get_transcript(video_id)
                    if not transcript:
                        self.q.put(("log", f"  - 경고: '{video_title}' 스크립트를 찾을 수 없어 건너뜁니다."))
                        processed_count += 1 # 건너뛰는 것도 처리된 것으로 간주
                        continue
                    
                    total_transcript_length += len(transcript)
                    prompt_with_title = f"영상 제목: {video_title}\n\n{self.user_prompt}"
                    
                    split_mode = self.split_mode_var.get()
                    
                    if split_mode == 'half':
                        mid = len(transcript) // 2
                        left_break = transcript.rfind('\n', 0, mid)
                        right_break = transcript.find('\n', mid)

                        split_idx = mid
                        if left_break != -1 and right_break != -1:
                            if (mid - left_break) < (right_break - mid):
                                split_idx = left_break
                            else:
                                split_idx = right_break
                        elif left_break != -1:
                            split_idx = left_break
                        elif right_break != -1:
                            split_idx = right_break
                        
                        part1 = transcript[:split_idx].strip()
                        part2 = transcript[split_idx:].strip()

                        full_prompt_1 = f"{prompt_with_title} (Part 1)\n\n--- 원본 스크립트 (1/2) ---{part1}\n--- 원본 스크립트 끝 ---"
                        tasks.append({"id": f"{video_id}_1", "task": full_prompt_1, "original_title": f"{video_title}_1", "original_video_id": video_id})
                        
                        full_prompt_2 = f"{prompt_with_title} (Part 2)\n\n--- 원본 스크립트 (2/2) ---{part2}\n--- 원본 스크립트 끝 ---"
                        tasks.append({"id": f"{video_id}_2", "task": full_prompt_2, "original_title": f"{video_title}_2", "original_video_id": video_id})
                    
                    elif split_mode == 'smart':
                        # 지능적 분할
                        interval_min = self.smart_split_interval.get()
                        total_secs = video.get('total_seconds', 0)
                        
                        if total_secs == 0: 
                             # fallback
                             full_prompt = f"{prompt_with_title}\n\n--- 원본 스크립트 ---{transcript}\n--- 원본 스크립트 끝 ---"
                             tasks.append({"id": video_id, "task": full_prompt, "original_title": video_title, "original_video_id": video_id})
                        else:
                            time_chunks = self.calculate_smart_splits(total_secs, interval_min)
                            text_chunks = self.smart_split_transcript(transcript, time_chunks, total_secs)
                            
                            total_parts = len(text_chunks)
                            for i, part in enumerate(text_chunks):
                                part_num = i + 1
                                full_prompt = f"{prompt_with_title} (Part {part_num})\n\n--- 원본 스크립트 ({part_num}/{total_parts}) ---{part}\n--- 원본 스크립트 끝 ---"
                                tasks.append({
                                    "id": f"{video_id}_{part_num}", 
                                    "task": full_prompt, 
                                    "original_title": f"{video_title}_{part_num}", 
                                    "original_video_id": video_id
                                })
                    
                    else:
                        full_prompt = f"{prompt_with_title}\n\n--- 원본 스크립트 ---{transcript}\n--- 원본 스크립트 끝 ---"
                        tasks.append({"id": video_id, "task": full_prompt, "original_title": video_title, "original_video_id": video_id})

                except Exception as e:
                    self.q.put(("log", f"  - ✗ 오류: '{video_title}' 스크립트 추출 중 문제 발생 - {e}"))
                    processed_count += 1 # 오류 발생도 처리된 것으로 간주

            if not tasks:
                if videos_to_process: # 처리할 영상이 더 남아있으면 계속
                    self.q.put(("log", "--- 현재 배치에 처리할 작업이 없습니다. 다음으로 넘어갑니다. ---"))
                    continue
                else: # 처리할 영상이 더 없으면 종료
                    break

            # Gemini API로 배치 처리를 시도합니다.
            try:
                self.q.put(("log", f"  - Gemini API로 {len(tasks)}개 작업 배치 요청 중..."))
                results = gemini_helper.process_batch_with_gemini(tasks, self.gemini_model_var.get())
                
                batch_end_time = time.time()
                batch_duration = batch_end_time - batch_start_time
                
                if batch_duration > 0:
                    speed = total_transcript_length / batch_duration
                    self.q.put(("log", f"  - 배치 처리 완료. 평균 처리 속도: {speed:.2f} 자/초"))
                    
                    log_data = {
                        "date": datetime.now().strftime('%Y-%m-%d'),
                        "model": self.gemini_model_var.get(),
                        "speed": f"{speed:.2f}"
                    }
                    file_helper.log_processing_speed(log_data)

                result_map = {res['id']: res.get('result', f"No result found for ID {res.get('id')}") for res in results}

                # 성공적으로 처리된 결과를 저장합니다.
                for task in tasks:
                    video_id = task['id']
                    video_title = task['original_title']
                    real_video_id = task.get('original_video_id', video_id)
                    
                    if video_id in result_map:
                        processed_content = result_map[video_id]
                        
                        if "Error processing batch response" in processed_content:
                            self.q.put(("log", f"  - ✗ 오류: '{video_title}' 처리 중 API 오류 발생 - {processed_content}"))
                            continue

                        self.q.put(("log", f"  - '{video_title}' 내용 가공 완료. 노트 저장 중..."))
                        file_helper.save_as_obsidian_note(self.obsidian_path, processed_content, self.keep_original_title.get(), video_title, self.insert_dash_in_titles.get())
                        
                        youtube_helper.log_processed_video(real_video_id)
                        
                        self.q.put(("log", f"  - ✓ 완료: '{video_title}' 노트 생성 완료"))
                        processed_count += 1 if self.split_mode_var.get() == 'none' else (1.0 / max(1, len(tasks))) # 대략적 카운트
                    else:
                        self.q.put(("log", f"  - ✗ 오류: '{video_title}' 처리 결과가 없습니다."))
                        processed_count += 1 if self.split_mode_var.get() == 'none' else (1.0 / max(1, len(tasks)))

            except gemini_helper.BatchProcessingError as e:
                # 배치 처리 실패 시 재시도 로직
                batch_id = tuple(sorted([t['id'] for t in tasks]))
                failure_counts[batch_id] = failure_counts.get(batch_id, 0) + 1
                count = failure_counts[batch_id]

                self.q.put(("log", f"  - ✗ 경고: Gemini 배치 처리 실패 (시도 {count}/4). 오류: {e}"))

                if count >= 4:
                    if not videos_to_process:  # 현재 배치가 마지막 남은 배치인 경우
                        self.q.put(("log", f"  - ✗ 치명적 오류: 마지막 배치가 4회 연속 실패하여 프로그램을 종료합니다."))
                        
                        failed_original_ids = set()
                        for t in tasks:
                            failed_original_ids.add(t.get('original_video_id', t['id']))
                        
                        failed_videos_in_batch = [v for v in video_map.values() if v['id'] in failed_original_ids]
                        failed_video_logger.log_failed_videos(failed_videos_in_batch)
                        self.q.put(("shutdown", "치명적 오류로 인해 작업이 중단되었습니다."))
                        return
                    else:
                        # 마지막 배치가 아니면 대기열 맨 뒤로 이동
                        self.q.put(("log", f"  - ⓘ 정보: 배치가 4회 실패하여 대기열의 맨 뒤로 이동합니다. 다른 배치 처리 후 재시도합니다."))
                        videos_to_process.extend(batch_videos)
                        failure_counts[batch_id] = 0  # 다른 배치를 처리하는 동안 카운트 초기화
                else:
                    # 4회 미만 실패 시 대기열 맨 뒤로 이동하여 재시도
                    self.q.put(("log", f"  - ⓘ 정보: 배치 처리 실패. 잠시 후 재시도하기 위해 대기열 뒤로 보냅니다."))
                    videos_to_process.extend(batch_videos)

            except Exception as e:
                # 기타 예외 처리
                self.q.put(("log", f"  - ✗ 오류: Gemini 배치 처리 중 예상치 못한 문제 발생 - {e}"))
                # 실패한 배치를 재시도 목록에 추가할 수 있습니다.
                self.q.put(("log", f"  - ⓘ 정보: 예상치 못한 오류 발생. 해당 배치를 대기열 뒤로 보냅니다."))
                videos_to_process.extend(batch_videos)
            
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
                    values = (video['title'], video['duration'])
                    if self.keyword_text:
                        values += (video.get('cosine_similarity', 'N/A'),)
                    self.tree.insert("", "end", values=values, iid=video['id'], tags=tags)
                
                if hasattr(self, 'load_more_btn') and self.load_more_btn.winfo_exists():
                    if self.next_page_token:
                        self.load_more_btn.config(state="normal", text="추가 로드")
                    else:
                        self.load_more_btn.config(state="disabled", text="더 이상 영상 없음")
            elif msg_type == "error":
                messagebox.showerror("오류", data)
                if hasattr(self, 'confirm_btn1') and self.confirm_btn1.winfo_exists():
                    self.confirm_btn1.config(state="normal", text="영상 목록 불러오기")
                if hasattr(self, 'load_more_btn') and self.load_more_btn.winfo_exists():
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