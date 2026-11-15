"""插件配置 WebUI Schema 的多语言元数据。"""

from collections.abc import Iterable
from maibot_sdk import PluginConfigBase
from typing import Dict, Tuple, Type


_LOCALES = ("en_US", "ja_JP", "ko_KR")

_SECTION_TEXTS: Dict[str, Tuple[Tuple[str, str, str], Tuple[str, str, str]]] = {
    "MiniMaxModelConfig": (("MiniMax Settings", "MiniMax 設定", "MiniMax 설정"), ("Official MiniMax image models.", "MiniMax 公式画像モデルの設定。", "MiniMax 공식 이미지 모델 설정.")),
    "AgnesModelConfig": (
        ("Agnes Settings", "Agnes 設定", "Agnes 설정"),
        ("Agnes image generation and editing.", "Agnes の画像生成・編集設定です。", "Agnes 이미지 생성 및 편집 설정입니다."),
    ),
    "PluginSectionConfig": (
        ("Plugin Settings", "プラグイン設定", "플러그인 설정"),
        ("Basic plugin settings.", "プラグインの基本設定です。", "플러그인의 기본 설정입니다."),
    ),
    "GeneralConfig": (
        ("General Settings", "一般設定", "일반 설정"),
        (
            "General drawing behavior and permissions.",
            "描画動作と権限の一般設定です。",
            "그리기 동작과 권한의 일반 설정입니다.",
        ),
    ),
    "StylePresetConfig": (
        ("Style Preset", "スタイルプリセット", "스타일 프리셋"),
        ("A reusable drawing style preset.", "再利用できる描画スタイルです。", "재사용 가능한 그리기 스타일입니다."),
    ),
    "StyleConfig": (
        ("Drawing Styles", "描画スタイル", "그리기 스타일"),
        (
            "Prompt templates shared by all providers.",
            "全プロバイダー共通のプロンプトテンプレートです。",
            "모든 제공자가 공유하는 프롬프트 템플릿입니다.",
        ),
    ),
    "ProxyConfig": (
        ("Proxy Settings", "プロキシ設定", "프록시 설정"),
        (
            "Global proxy settings for image providers.",
            "画像プロバイダー用の共通プロキシ設定です。",
            "이미지 제공자용 전역 프록시 설정입니다.",
        ),
    ),
    "WorldSearchConfig": (
        ("World Knowledge Image Search", "ワールドナレッジ画像検索", "월드 지식 이미지 검색"),
        (
            "Search services used to find reference images when fixed sources have none.",
            "固定ソースに参考画像がないときに使う画像検索サービスです。",
            "고정 소스에 참고 이미지가 없을 때 사용하는 이미지 검색 서비스입니다.",
        ),
    ),
    "OpenAICompatibleInstanceConfig": (
        ("OpenAI-Compatible Instance", "OpenAI 互換インスタンス", "OpenAI 호환 인스턴스"),
        (
            "Settings for one OpenAI-compatible endpoint.",
            "OpenAI 互換エンドポイントの設定です。",
            "OpenAI 호환 엔드포인트 설정입니다.",
        ),
    ),
    "OpenAIModelConfig": (
        ("OpenAI Settings", "OpenAI 設定", "OpenAI 설정"),
        ("OpenAI image model settings.", "OpenAI 画像モデルの設定です。", "OpenAI 이미지 모델 설정입니다."),
    ),
    "GoogleModelConfig": (
        ("Google Settings", "Google 設定", "Google 설정"),
        (
            "Google Gemini and Imagen model settings.",
            "Google Gemini と Imagen の設定です。",
            "Google Gemini 및 Imagen 모델 설정입니다.",
        ),
    ),
    "ZhipuModelConfig": (
        ("Zhipu Settings", "智譜設定", "Zhipu 설정"),
        (
            "Zhipu GLM-Image and CogView settings.",
            "智譜 GLM-Image と CogView の設定です。",
            "Zhipu GLM-Image 및 CogView 설정입니다.",
        ),
    ),
    "AliyunModelConfig": (
        ("Alibaba Cloud Model Studio", "Alibaba Cloud Model Studio", "Alibaba Cloud Model Studio"),
        (
            "Alibaba Cloud image model settings.",
            "Alibaba Cloud 画像モデルの設定です。",
            "Alibaba Cloud 이미지 모델 설정입니다.",
        ),
    ),
    "VolcengineModelConfig": (
        ("Volcengine Settings", "Volcengine 設定", "Volcengine 설정"),
        (
            "Volcengine Ark image model settings.",
            "Volcengine Ark 画像モデルの設定です。",
            "Volcengine Ark 이미지 모델 설정입니다.",
        ),
    ),
    "SiliconFlowModelConfig": (
        ("SiliconFlow Settings", "SiliconFlow 設定", "SiliconFlow 설정"),
        (
            "SiliconFlow image model settings.",
            "SiliconFlow 画像モデルの設定です。",
            "SiliconFlow 이미지 모델 설정입니다.",
        ),
    ),
    "NovelAIModelConfig": (
        ("NovelAI / NovelAPI Settings", "NovelAI / NovelAPI 設定", "NovelAI / NovelAPI 설정"),
        (
            "NovelAI and NovelAPI image model settings.",
            "NovelAI と NovelAPI の設定です。",
            "NovelAI 및 NovelAPI 이미지 모델 설정입니다.",
        ),
    ),
    "ComfyUIModelConfig": (
        ("ComfyUI Settings", "ComfyUI 設定", "ComfyUI 설정"),
        (
            "Local ComfyUI workflow settings.",
            "ローカル ComfyUI ワークフローの設定です。",
            "로컬 ComfyUI 워크플로 설정입니다.",
        ),
    ),
    "CodexAgentConfig": (
        ("Codex Agent Settings", "Codex エージェント設定", "Codex 에이전트 설정"),
        (
            "Local Codex CLI agent that researches references and generates images.",
            "ローカルの Codex CLI エージェントが資料を調べて画像を生成します。",
            "로컬 Codex CLI 에이전트가 자료를 조사하고 이미지를 생성합니다.",
        ),
    ),
    "PromptModerationConfig": (
        ("Prompt Review", "プロンプト審査", "프롬프트 검토"),
        ("Prompt review settings.", "プロンプト審査の設定です。", "프롬프트 검토 설정입니다."),
    ),
    "ImageModerationConfig": (
        ("Generated Image Review", "生成画像の審査", "생성 이미지 검토"),
        ("Generated image review settings.", "生成画像を審査する設定です。", "생성 이미지를 검토하는 설정입니다."),
    ),
}

_FIELD_LABELS: Dict[str, Tuple[str, str, str]] = {
    "world_knowledge_enabled": ("Enable World Knowledge", "ワールドナレッジを有効化", "세계 지식 사용"),
    "world_knowledge_model": ("World Knowledge Model", "ワールドナレッジのモデル", "세계 지식 모델"),
    "world_knowledge_timeout_seconds": (
        "World Knowledge Wait (seconds)", "ワールドナレッジの待機時間（秒）", "세계 지식 대기 시간(초)"
    ),
    "world_knowledge_max_entities": ("Max Recognized Subjects", "認識する対象の上限", "최대 인식 대상 수"),
    "world_knowledge_max_searches": ("Max Web Searches", "Web 検索の上限", "최대 웹 검색 횟수"),
    "world_knowledge_max_reference_images": ("Max Reference Images", "参照画像の上限", "최대 참고 이미지 수"),
    "world_knowledge_auto_images": ("Find Reference Images Automatically", "参照画像を自動で探す", "참고 이미지 자동 찾기"),
    "world_knowledge_screen_images": ("Screen Reference Images with a Model", "モデルで参照画像を確認", "모델로 참고 이미지 확인"),
    "world_knowledge_allow_fake_ip": ("Allow Fake-IP Addresses", "Fake-IP アドレスを許可", "Fake-IP 주소 허용"),
    "world_knowledge_verify_enabled": ("Check After Drawing", "生成後に確認", "생성 후 확인"),
    "world_knowledge_verify_model": ("Check Model", "確認モデル", "확인 모델"),
    "world_knowledge_redraw_enabled": ("Redraw Once on Severe Errors", "重大な誤りは 1 回だけ再生成", "심각한 오류 시 한 번 다시 그리기"),
    "access_scope": ("Access Scope", "利用範囲", "사용 범위"),
    "agent_instructions": ("Agent Instructions", "エージェント指示", "에이전트 지침"),
    "allow_proxy_fake_ip": ("Allow Proxy Fake-IP Addresses", "プロキシの fake-ip を許可", "프록시 fake-ip 주소 허용"),
    "codex_home": ("CODEX_HOME Directory", "CODEX_HOME ディレクトリ", "CODEX_HOME 디렉터리"),
    "codex_path": ("Codex Executable", "Codex 実行ファイル", "Codex 실행 파일"),
    "deliver_all_images": ("Send All Images of the Turn", "このターンの全画像を送信", "이번 턴의 모든 이미지 전송"),
    "max_concurrent_tasks": ("Concurrent Tasks", "同時実行タスク数", "동시 실행 작업 수"),
    "max_queued_tasks": ("Maximum Queued Tasks", "最大待機タスク数", "최대 대기 작업 수"),
    "queue_timeout_seconds": ("Queue Wait Limit (Seconds)", "待機時間の上限（秒）", "대기 시간 한도(초)"),
    "max_reference_downloads": ("Reference Downloads per Task", "タスクごとの参照画像ダウンロード数", "작업당 참조 이미지 다운로드 수"),
    "reasoning_effort": ("Reasoning Effort", "推論強度", "추론 강도"),
    "resume_enabled": ("Resume Source Session for Edits", "再調整で元のセッションを継続", "재조정 시 원래 세션 이어가기"),
    "task_timeout_seconds": ("Task Timeout (Seconds)", "タスクのタイムアウト（秒）", "작업 시간 제한(초)"),
    "thread_retention_days": ("Session Retention (Days)", "セッション保持日数", "세션 보존 일수"),
    "integration_api_enabled": ("Plugin Integration API", "プラグイン連携 API", "플러그인 연동 API"),
    "group_access_mode": ("Group List Mode", "グループ一覧モード", "그룹 목록 모드"),
    "group_access_ids": ("Group Access List", "グループアクセス一覧", "그룹 접근 목록"),
    "private_access_mode": ("Private Chat List Mode", "個人チャット一覧モード", "개인 대화 목록 모드"),
    "private_access_ids": ("Private Chat Access List", "個人チャットアクセス一覧", "개인 대화 접근 목록"),
    "prompt_review_retry_count": ("Prompt Review Retries", "プロンプト審査の再試行回数", "프롬프트 검토 재시도 횟수"),
    "image_review_retry_count": ("Image Review Retries", "画像審査の再試行回数", "이미지 검토 재시도 횟수"),
    "prompt_review_model": ("Prompt Review Model", "プロンプト審査モデル", "프롬프트 검토 모델"),
    "image_review_model": ("Image Review Model", "画像審査モデル", "이미지 검토 모델"),
    "prompt_review_timeout_seconds": ("Prompt Review Wait (seconds)", "プロンプト審査の待機時間（秒）", "프롬프트 검토 대기 시간(초)"),
    "image_review_timeout_seconds": ("Image Review Wait (seconds)", "画像審査の待機時間（秒）", "이미지 검토 대기 시간(초)"),
    "skip_image_url_ip_check": (
        "Skip Image URL IP Checks", "画像 URL の IP 検証を省略", "이미지 URL IP 검사 건너뛰기"
    ),
    "ratio": ("Aspect Ratio", "アスペクト比", "화면 비율"),
    "image_cache_max_mb": ("Image Cache Limit (MB)", "画像キャッシュ上限（MB）", "이미지 캐시 한도(MB)"),
    "log_max_mb": ("Total Log Limit (MB)", "ログ合計上限（MB）", "전체 로그 한도(MB)"),
    "upload_cache_max_mb": ("Upload Cache Limit (MB)", "アップロードキャッシュ上限（MB）", "업로드 캐시 한도(MB)"),
    "add_watermark": ("Add Watermark", "ウォーターマークを追加", "워터마크 추가"),
    "admin_user_ids": ("Administrators", "管理者一覧", "관리자 목록"),
    "api_key": ("API Key", "API キー", "API 키"),
    "aspect_ratio": ("Aspect Ratio", "アスペクト比", "화면 비율"),
    "async_poll_interval_seconds": ("Async Poll Interval", "非同期ポーリング間隔", "비동기 폴링 간격"),
    "background": ("Background", "背景", "배경"),
    "base_url": ("Base URL", "ベース URL", "기본 URL"),
    "cfg": ("Qwen Image CFG", "Qwen Image CFG", "Qwen Image CFG"),
    "batch_size": ("Batch Size", "バッチサイズ", "배치 크기"),
    "bypass_china_providers": (
        "Bypass Proxy for China Providers",
        "中国プロバイダーはプロキシを回避",
        "중국 제공자 프록시 우회",
    ),
    "command_reply_mode": ("Command Reply Mode", "コマンド応答モード", "명령 응답 모드"),
    "sync_generated_images_to_history": (
        "Sync Generated Images to Chat History", "生成画像を会話履歴に同期", "생성 이미지를 대화 기록에 동기화",
    ),
    "config_version": ("Configuration Version", "設定バージョン", "설정 버전"),
    "custom_models": ("Custom Models", "カスタムモデル", "사용자 지정 모델"),
    "default_artist_tags": ("Default Artist Tags", "既定のアーティストタグ", "기본 아티스트 태그"),
    "default_mode": ("Default Mode", "既定モード", "기본 모드"),
    "default_model": ("Default Model", "既定モデル", "기본 모델"),
    "default_openai_compatibility_mode": (
        "Default OpenAI Compatibility Mode",
        "既定の OpenAI 互換モード",
        "기본 OpenAI 호환 모드",
    ),
    "default_size": ("Default Resolution", "既定の解像度", "기본 해상도"),
    "edit_size_mode": ("Image Edit Size", "画像編集のサイズ", "이미지 편집 크기"),
    "request_mode": ("Request Mode", "リクエスト方式", "요청 방식"),
    "responses_main_model": ("Responses Main Model", "Responses メインモデル", "Responses 메인 모델"),
    "responses_poll_interval_seconds": ("Responses Poll Interval", "Responses ポーリング間隔", "Responses 폴링 간격"),
    "default_style": ("Default Style", "既定スタイル", "기본 스타일"),
    "description": ("Description", "説明", "설명"),
    "enabled": ("Enabled", "有効", "활성화"),
    "extra_parameters": ("Extra Parameters", "追加パラメータ", "추가 매개변수"),
    "failure_reason_enabled": ("Include Failure Reason", "失敗理由を表示", "실패 원인 표시"),
    "fallback_model": ("Fallback Model", "フォールバックモデル", "대체 모델"),
    "fallback_models": ("Ordered Fallback Models", "代替モデルの優先順位", "대체 모델 우선순위"),
    "request_retry_count": ("Maximum Retries per Model", "モデルごとの最大再試行回数", "모델별 최대 재시도 횟수"),
    "group_default_quota": ("Default Group Quota", "グループ既定クォータ", "그룹 기본 할당량"),
    "group_quota_enabled": ("Enable Group Quota", "グループクォータを有効化", "그룹 할당량 활성화"),
    "group_quota_period": ("Group Quota Period", "グループクォータ期間", "그룹 할당량 기간"),
    "guidance_scale": ("Guidance Scale", "ガイダンス強度", "가이던스 강도"),
    "height": ("Height", "高さ", "높이"),
    "host": ("Proxy Host", "プロキシホスト", "프록시 호스트"),
    "i2i_image_node_id": ("Image-to-Image Source Node ID", "画像変換の元画像ノード ID", "이미지 변환 원본 노드 ID"),
    "i2i_models": ("Image-to-Image Models", "画像変換モデル", "이미지 변환 모델"),
    "i2i_negative_prompt": (
        "Image-to-Image Negative Prompt",
        "画像変換のネガティブプロンプト",
        "이미지 변환 네거티브 프롬프트",
    ),
    "i2i_negative_prompt_node_id": (
        "Image-to-Image Negative Prompt Node ID",
        "画像変換ネガティブノード ID",
        "이미지 변환 네거티브 노드 ID",
    ),
    "i2i_positive_prompt_node_id": (
        "Image-to-Image Positive Prompt Node ID",
        "画像変換ポジティブノード ID",
        "이미지 변환 포지티브 노드 ID",
    ),
    "i2i_prompt_mode": ("Image-to-Image Prompt Mode", "画像変換プロンプトモード", "이미지 변환 프롬프트 모드"),
    "i2i_prompt_node_id": (
        "Image-to-Image Prompt Node ID",
        "画像変換プロンプトノード ID",
        "이미지 변환 프롬프트 노드 ID",
    ),
    "i2i_seed_node_id": ("Image-to-Image Seed Node ID", "画像変換シードノード ID", "이미지 변환 시드 노드 ID"),
    "i2i_workflow_path": ("Image-to-Image Workflow JSON", "画像変換ワークフロー JSON", "이미지 변환 워크플로 JSON"),
    "image_edit_unsupported_models": (
        "Models Without Image Editing",
        "画像編集非対応モデル",
        "이미지 편집 미지원 모델",
    ),
    "image_input_mode": ("Source Image Input Mode", "元画像入力モード", "원본 이미지 입력 모드"),
    "image_input_name": ("Source Image Input Field", "元画像入力フィールド", "원본 이미지 입력 필드"),
    "image_review_enabled": ("Enable Generated Image Review", "生成画像の審査を有効化", "생성 이미지 검토 활성화"),
    "image_review_prompt": ("Generated Image Review Template", "生成画像審査テンプレート", "생성 이미지 검토 템플릿"),
    "image_size": ("Image Size", "画像サイズ", "이미지 크기"),
    "img2img_noise": ("Image-to-Image Noise", "画像変換ノイズ", "이미지 변환 노이즈"),
    "img2img_strength": ("Image-to-Image Strength", "画像変換強度", "이미지 변환 강도"),
    "instances": ("OpenAI-Compatible Instances", "OpenAI 互換インスタンス", "OpenAI 호환 인스턴스"),
    "kling_aspect_ratio": ("Kling Aspect Ratio", "Kling アスペクト比", "Kling 화면 비율"),
    "kling_extra_parameters": ("Kling Extra Parameters", "Kling 追加パラメータ", "Kling 추가 매개변수"),
    "kling_resolution": ("Kling Resolution", "Kling 解像度", "Kling 해상도"),
    "kling_result_type": ("Kling Omni Result Mode", "Kling Omni 結果モード", "Kling Omni 결과 모드"),
    "kling_series_amount": ("Kling Omni Series Count", "Kling Omni シリーズ枚数", "Kling Omni 시리즈 수"),
    "layer_decomposition": ("Layer Decomposition", "レイヤー分解", "레이어 분해"),
    "max_images": ("Maximum Images", "最大画像数", "최대 이미지 수"),
    "model_endpoint_overrides": (
        "Per-Model Endpoint Overrides",
        "モデル別エンドポイント上書き",
        "모델별 엔드포인트 재정의",
    ),
    "model_size_overrides": ("Per-Model Resolution Overrides", "モデル別解像度上書き", "모델별 해상도 재정의"),
    "models": ("Models", "モデル一覧", "모델 목록"),
    "moderation": ("Moderation Level", "モデレーション強度", "검토 강도"),
    "name": ("Name", "名前", "이름"),
    "negative_prompt": ("Default Negative Prompt (Optional)", "既定のネガティブプロンプト（任意）", "기본 네거티브 프롬프트(선택 사항)"),
    "negative_prompt_enabled": ("Enable Negative Prompts", "ネガティブプロンプトを有効化", "네거티브 프롬프트 활성화"),
    "negative_prompt_template": (
        "Negative Prompt Template",
        "ネガティブプロンプトテンプレート",
        "네거티브 프롬프트 템플릿",
    ),
    "noise_schedule": ("Noise Schedule", "ノイズスケジュール", "노이즈 스케줄"),
    "num_inference_steps": ("Inference Steps", "推論ステップ数", "추론 단계"),
    "number_of_images": ("Number of Images", "生成画像数", "생성 이미지 수"),
    "output_format": ("Output Format", "出力形式", "출력 형식"),
    "output_mime_type": ("Output MIME Type", "出力 MIME タイプ", "출력 MIME 형식"),
    "optimize_prompt_mode": ("Prompt Optimization Mode", "プロンプト最適化モード", "프롬프트 최적화 모드"),
    "password": ("Proxy Password", "プロキシパスワード", "프록시 비밀번호"),
    "permission_enabled": ("Enable Command Permissions", "コマンド権限を有効化", "명령 권한 활성화"),
    "person_generation": ("Person Generation", "人物生成", "인물 생성"),
    "poll_interval_seconds": ("Poll Interval", "ポーリング間隔", "폴링 간격"),
    "port": ("Proxy Port", "プロキシポート", "프록시 포트"),
    "positive_prompt": ("Default Positive Prompt", "既定のポジティブプロンプト", "기본 포지티브 프롬프트"),
    "positive_prompt_template": (
        "Positive Prompt Template",
        "ポジティブプロンプトテンプレート",
        "포지티브 프롬프트 템플릿",
    ),
    "presets": ("Style Presets", "スタイルプリセット", "스타일 프리셋"),
    "private_default_quota": ("Default Private Quota", "個人チャット既定クォータ", "개인 채팅 기본 할당량"),
    "private_quota_enabled": ("Enable Private Quota", "個人チャットクォータを有効化", "개인 채팅 할당량 활성화"),
    "private_quota_period": ("Private Quota Period", "個人チャットクォータ期間", "개인 채팅 할당량 기간"),
    "prompt_extend": ("Smart Prompt Expansion", "スマートプロンプト拡張", "스마트 프롬프트 확장"),
    "prompt_input_name": ("Prompt Input Field", "プロンプト入力フィールド", "프롬프트 입력 필드"),
    "prompt_review_enabled": ("Enable Prompt Review", "プロンプト審査を有効化", "프롬프트 검토 활성화"),
    "prompt_review_prompt": ("Prompt Review Template", "プロンプト審査テンプレート", "프롬프트 검토 템플릿"),
    "quality": ("Quality", "品質", "품질"),
    "quality_toggle": ("Quality Enhancement", "品質強化", "품질 향상"),
    "qwen_enable_thinking": ("Qwen 3.0 Thinking Mode", "Qwen 3.0 思考モード", "Qwen 3.0 사고 모드"),
    "qwen_extra_parameters": ("Qwen Extra Parameters", "Qwen 追加パラメータ", "Qwen 추가 매개변수"),
    "qwen_prompt_extend_mode": ("Qwen 3.0 Expansion Mode", "Qwen 3.0 拡張モード", "Qwen 3.0 확장 모드"),
    "request_timeout_seconds": ("Image Request Timeout", "画像リクエストのタイムアウト", "이미지 요청 시간 제한"),
    "response_format": ("Response Format", "応答形式", "응답 형식"),
    "review_prompt": ("Review Prompt", "審査プロンプト", "검토 프롬프트"),
    "rewrite_prompt_to_english": ("Rewrite Prompt in English", "英語プロンプトに書き換え", "영어 프롬프트로 재작성"),
    "sampler": ("Sampler", "サンプラー", "샘플러"),
    "scale": ("Prompt Guidance", "プロンプトガイダンス", "프롬프트 가이던스"),
    "scheme": ("Proxy Protocol", "プロキシプロトコル", "프록시 프로토콜"),
    "seed": ("Random Seed", "ランダムシード", "무작위 시드"),
    "seed_input_name": ("Seed Input Field", "シード入力フィールド", "시드 입력 필드"),
    "sequential_image_generation": ("Sequential Image Generation", "組画像生成", "연속 이미지 생성"),
    "size": ("Resolution", "解像度", "해상도"),
    "sm": ("SMEA", "SMEA", "SMEA"),
    "sm_dyn": ("Dynamic SMEA", "ダイナミック SMEA", "동적 SMEA"),
    "steps": ("Sampling Steps", "サンプリングステップ数", "샘플링 단계"),
    "t2i_models": ("Text-to-Image Models", "テキスト画像生成モデル", "텍스트 이미지 생성 모델"),
    "t2i_negative_prompt": (
        "Text-to-Image Negative Prompt",
        "テキスト画像生成ネガティブプロンプト",
        "텍스트 이미지 생성 네거티브 프롬프트",
    ),
    "t2i_negative_prompt_node_id": (
        "Text-to-Image Negative Prompt Node ID",
        "テキスト画像生成ネガティブノード ID",
        "텍스트 이미지 생성 네거티브 노드 ID",
    ),
    "t2i_positive_prompt_node_id": (
        "Text-to-Image Positive Prompt Node ID",
        "テキスト画像生成ポジティブノード ID",
        "텍스트 이미지 생성 포지티브 노드 ID",
    ),
    "t2i_prompt_mode": (
        "Text-to-Image Prompt Mode",
        "テキスト画像生成プロンプトモード",
        "텍스트 이미지 생성 프롬프트 모드",
    ),
    "t2i_prompt_node_id": (
        "Text-to-Image Prompt Node ID",
        "テキスト画像生成プロンプトノード ID",
        "텍스트 이미지 생성 프롬프트 노드 ID",
    ),
    "t2i_seed_node_id": (
        "Text-to-Image Seed Node ID",
        "テキスト画像生成シードノード ID",
        "텍스트 이미지 생성 시드 노드 ID",
    ),
    "t2i_workflow_path": (
        "Text-to-Image Workflow JSON",
        "テキスト画像生成ワークフロー JSON",
        "텍스트 이미지 생성 워크플로 JSON",
    ),
    "text_to_image_unsupported_models": (
        "Models Without Text-to-Image",
        "テキスト画像生成非対応モデル",
        "텍스트 이미지 생성 미지원 모델",
    ),
    "uc_preset": ("Legacy UC Preset", "旧 UC プリセット", "레거시 UC 프리셋"),
    "unified_models": ("Unified Models", "統合モデル", "통합 모델"),
    "use_system_proxy": ("Use System Proxy", "システムプロキシを使用", "시스템 프록시 사용"),
    "user_id": ("End-User ID", "エンドユーザー ID", "최종 사용자 ID"),
    "username": ("Proxy Username", "プロキシユーザー名", "프록시 사용자 이름"),
    "v4_noise_schedule": ("V4 / V4.5 Noise Schedule", "V4 / V4.5 ノイズスケジュール", "V4 / V4.5 노이즈 스케줄"),
    "vidu_extra_parameters": ("Vidu Extra Parameters", "Vidu 追加パラメータ", "Vidu 추가 매개변수"),
    "watermark": ("Add Watermark", "ウォーターマークを追加", "워터마크 추가"),
    "watermark_enabled": ("Enable Watermark", "ウォーターマークを有効化", "워터마크 활성화"),
    "web_search_enabled": ("Enable Web Search", "ウェブ検索を有効化", "웹 검색 활성화"),
    "width": ("Width", "幅", "너비"),
    "zimage_extra_parameters": ("Z-Image Extra Parameters", "Z-Image 追加パラメータ", "Z-Image 추가 매개변수"),
    "zimage_prompt_extend": ("Z-Image Prompt Expansion", "Z-Image プロンプト拡張", "Z-Image 프롬프트 확장"),
}

_FIELD_LABEL_OVERRIDES: Dict[str, Tuple[str, str, str]] = {
    "SiliconFlowModelConfig.watermark_enabled": (
        "Enable Visible AI-generated Watermark",
        "AI 生成の可視透かしを有効化",
        "AI 생성 표시 워터마크 활성화",
    ),
    "MiniMaxModelConfig.enabled": ("Enabled", "有効", "활성화"),
    "MiniMaxModelConfig.api_key": ("API Key", "API キー", "API 키"),
    "MiniMaxModelConfig.base_url": ("API Base URL", "API 基本 URL", "API 기본 URL"),
    "MiniMaxModelConfig.models": ("Models", "モデル", "모델"),
    "MiniMaxModelConfig.size": ("Output Size", "出力サイズ", "출력 크기"),
    "MiniMaxModelConfig.model_size_overrides": ("Per-model Sizes", "モデル別サイズ", "모델별 크기"),
    "MiniMaxModelConfig.aspect_ratio": ("Aspect Ratio", "アスペクト比", "화면 비율"),
    "MiniMaxModelConfig.area": ("H3 Area", "H3 面積", "H3 면적"),
    "MiniMaxModelConfig.n": ("Image Count", "生成枚数", "생성 수"),
    "MiniMaxModelConfig.response_format": ("Response Format", "応答形式", "응답 형식"),
    "MiniMaxModelConfig.output_format": ("H3 Output Format", "H3 出力形式", "H3 출력 형식"),
    "MiniMaxModelConfig.output_compression": ("H3 Compression Quality", "H3 圧縮品質", "H3 압축 품질"),
    "MiniMaxModelConfig.stream": ("H3 Streaming", "H3 ストリーミング", "H3 스트리밍"),
    "MiniMaxModelConfig.disable_prompt_enhanced": ("Disable H3 Prompt Enhancement", "H3 プロンプト強化を無効化", "H3 프롬프트 강화 비활성화"),
    "MiniMaxModelConfig.prompt_optimizer": ("image-01 Prompt Optimizer", "image-01 プロンプト最適化", "image-01 프롬프트 최적화"),
    "MiniMaxModelConfig.seed": ("image-01 Seed", "image-01 シード", "image-01 시드"),
    "MiniMaxModelConfig.style_type": ("image-01-live Style", "image-01-live スタイル", "image-01-live 스타일"),
    "MiniMaxModelConfig.style_weight": ("image-01-live Style Weight", "image-01-live スタイル強度", "image-01-live 스타일 가중치"),
    "MiniMaxModelConfig.aigc_watermark": ("Visible AIGC Watermark", "AIGC 可視透かし", "AIGC 표시 워터마크"),
    "MiniMaxModelConfig.request_timeout_seconds": ("MiniMax Request Timeout", "MiniMax リクエスト制限時間", "MiniMax 요청 제한 시간"),
    "MiniMaxModelConfig.extra_parameters": ("Extra Parameters", "追加パラメータ", "추가 매개변수"),
    "MiniMaxModelConfig.rewrite_prompt_to_english": ("Rewrite Prompt in English", "英語プロンプトに変換", "영어 프롬프트로 변환"),
    "PluginSectionConfig.enabled": ("Enable Plugin", "プラグインを有効化", "플러그인 활성화"),
    "StylePresetConfig.enabled": ("Enable Preset", "プリセットを有効化", "프리셋 활성화"),
    "ProxyConfig.enabled": ("Enable Global Proxy", "共通プロキシを有効化", "전역 프록시 활성화"),
    "WorldSearchConfig.order": ("Search Service Order", "検索サービスの順序", "검색 서비스 순서"),
    "WorldSearchConfig.strategy": ("Usage Strategy", "使用方式", "사용 방식"),
    "WorldSearchConfig.max_candidates": ("Candidate Images", "候補画像数", "후보 이미지 수"),
    "WorldSearchConfig.openai_api_key": ("OpenAI API Key", "OpenAI API キー", "OpenAI API 키"),
    "WorldSearchConfig.openai_base_url": ("OpenAI Base URL", "OpenAI ベース URL", "OpenAI 기본 URL"),
    "WorldSearchConfig.openai_model": ("OpenAI Model", "OpenAI モデル", "OpenAI 모델"),
    "WorldSearchConfig.brave_api_key": ("Brave API Key", "Brave API キー", "Brave API 키"),
    "WorldSearchConfig.tavily_api_key": ("Tavily API Key", "Tavily API キー", "Tavily API 키"),
    "OpenAICompatibleInstanceConfig.enabled": ("Enable Instance", "インスタンスを有効化", "인스턴스 활성화"),
    "OpenAIModelConfig.enabled": ("Enable This Platform Instance", "このプラットフォームインスタンスを有効化", "이 플랫폼 인스턴스 활성화"),
    "OpenAIModelConfig.api_key": ("OpenAI API Key", "OpenAI API キー", "OpenAI API 키"),
    "OpenAIModelConfig.models": ("OpenAI Models", "OpenAI モデル一覧", "OpenAI 모델 목록"),
    "GoogleModelConfig.enabled": ("Enable Google Platform", "Google プラットフォームを有効化", "Google 플랫폼 활성화"),
    "GoogleModelConfig.api_key": ("Google API Key", "Google API キー", "Google API 키"),
    "GoogleModelConfig.models": ("Google Models", "Google モデル一覧", "Google 모델 목록"),
    "ZhipuModelConfig.enabled": ("Enable Zhipu Platform", "智譜プラットフォームを有効化", "Zhipu 플랫폼 활성화"),
    "ZhipuModelConfig.api_key": ("Zhipu API Key (Required)", "智譜 API キー（必須）", "Zhipu API 키(필수)"),
    "ZhipuModelConfig.models": ("Zhipu Models (Required)", "智譜モデル一覧（必須）", "Zhipu 모델 목록(필수)"),
    "ZhipuModelConfig.quality": ("Generation Quality (Optional)", "生成品質（任意）", "생성 품질(선택 사항)"),
    "ZhipuModelConfig.size": ("Resolution (Optional)", "解像度（任意）", "해상도(선택 사항)"),
    "ZhipuModelConfig.watermark_enabled": (
        "Enable Watermark (Optional)",
        "ウォーターマークを有効化（任意）",
        "워터마크 활성화(선택 사항)",
    ),
    "ZhipuModelConfig.user_id": ("End-User ID (Optional)", "エンドユーザー ID（任意）", "최종 사용자 ID(선택 사항)"),
    "ZhipuModelConfig.extra_parameters": (
        "Extra Parameters (Optional)",
        "追加パラメータ（任意）",
        "추가 매개변수(선택 사항)",
    ),
    "AliyunModelConfig.enabled": (
        "Enable Alibaba Cloud Platform",
        "Alibaba Cloud を有効化",
        "Alibaba Cloud 플랫폼 활성화",
    ),
    "AliyunModelConfig.base_url": (
        "DashScope Base URL (Required)",
        "DashScope ベース URL（必須）",
        "DashScope 기본 URL(필수)",
    ),
    "AliyunModelConfig.api_key": (
        "DashScope API Key (Required)",
        "DashScope API キー（必須）",
        "DashScope API 키(필수)",
    ),
    "AliyunModelConfig.models": (
        "Alibaba Cloud Models (Required)",
        "Alibaba Cloud モデル一覧（必須）",
        "Alibaba Cloud 모델 목록(필수)",
    ),
    "VolcengineModelConfig.enabled": (
        "Enable Volcengine Platform",
        "Volcengine プラットフォームを有効化",
        "Volcengine 플랫폼 활성화",
    ),
    "VolcengineModelConfig.base_url": (
        "Volcengine Base URL",
        "Volcengine ベース URL",
        "Volcengine 기본 URL",
    ),
    "VolcengineModelConfig.api_key": ("Volcengine API Key", "Volcengine API キー", "Volcengine API 키"),
    "VolcengineModelConfig.models": (
        "Volcengine Image Models",
        "Volcengine 画像モデル一覧",
        "Volcengine 이미지 모델 목록",
    ),
    "SiliconFlowModelConfig.enabled": (
        "Enable SiliconFlow Platform",
        "SiliconFlow プラットフォームを有効化",
        "SiliconFlow 플랫폼 활성화",
    ),
    "SiliconFlowModelConfig.api_key": ("SiliconFlow API Key", "SiliconFlow API キー", "SiliconFlow API 키"),
    "SiliconFlowModelConfig.models": ("SiliconFlow Models", "SiliconFlow モデル一覧", "SiliconFlow 모델 목록"),
    "NovelAIModelConfig.enabled": (
        "Enable NovelAI / NovelAPI",
        "NovelAI / NovelAPI を有効化",
        "NovelAI / NovelAPI 활성화",
    ),
    "NovelAIModelConfig.api_key": ("NovelAI API Key", "NovelAI API キー", "NovelAI API 키"),
    "NovelAIModelConfig.models": ("NovelAI Models", "NovelAI モデル一覧", "NovelAI 모델 목록"),
    "ComfyUIModelConfig.enabled": ("Enable ComfyUI", "ComfyUI を有効化", "ComfyUI 활성화"),
    "CodexAgentConfig.enabled": ("Enable Codex Agent Platform", "Codex エージェントを有効化", "Codex 에이전트 플랫폼 활성화"),
    "CodexAgentConfig.models": ("Codex Chat Models", "Codex 対話モデル", "Codex 대화 모델"),
    "PromptModerationConfig.enabled": ("Enable Prompt Review", "プロンプト審査を有効化", "프롬프트 검토 활성화"),
    "PromptModerationConfig.review_prompt": ("Prompt Review Instructions", "プロンプト審査指示", "프롬프트 검토 지침"),
    "ImageModerationConfig.enabled": (
        "Enable Generated Image Review",
        "生成画像の審査を有効化",
        "생성 이미지 검토 활성화",
    ),
    "ImageModerationConfig.review_prompt": ("Image Review Instructions", "画像審査指示", "이미지 검토 지침"),
}

_PLACEHOLDER_TEXTS: Dict[str, Tuple[str, str, str]] = {
    "StylePresetConfig.name": ("e.g. Watercolor or Cyberpunk", "例：水彩、サイバーパンク", "예: 수채화, 사이버펑크"),
    "OpenAICompatibleInstanceConfig.name": (
        "e.g. platform-1 or newapi-1",
        "例：platform-1、newapi-1",
        "예: platform-1, newapi-1",
    ),
}

_OPENAI_MODE_HINTS = (
    "auto / images_api / chat_completions (New API image chat) / rinkoai (RinkoAI NAI). "
    "auto uses endpoint metadata and model families. Legacy novelai_images_api means rinkoai.",
    "auto / images_api / chat_completions（New API 画像チャット）/ rinkoai（RinkoAI NAI）。"
    "auto は端点情報とモデル系列を使用します。旧 novelai_images_api は rinkoai の別名です。",
    "auto / images_api / chat_completions(New API 이미지 채팅) / rinkoai(RinkoAI NAI). "
    "auto는 엔드포인트 정보와 모델 계열을 사용합니다. 이전 novelai_images_api는 rinkoai의 별칭입니다.",
)


_FIELD_HINT_OVERRIDES: Dict[str, Tuple[str, str, str]] = {
    "GeneralConfig.world_knowledge_enabled": (
        "Off by default. When on, chat drawing, the workbench and plugin APIs first recognize real-world subjects in the prompt "
        "(game characters, teams, events, new products), look them up in the entry library or search the web, and pass "
        "appearance notes and reference images to the image model. Requires Host web search. Any failure continues with the original prompt.",
        "既定は無効です。有効にすると、チャット描画・ワークベンチ・プラグイン API はプロンプト内の実在の対象（ゲームキャラクター、チーム、大会、新製品）を"
        "認識し、エントリー辞書または Web 検索で調べて、外見メモと参照画像を画像モデルに渡します。Host の Web 検索設定が必要です。失敗しても元のプロンプトで続行します。",
        "기본값은 꺼짐입니다. 켜면 채팅 그리기, 워크벤치, 플러그인 API가 프롬프트 속 실제 대상(게임 캐릭터, 팀, 대회, 신제품)을 인식하고 항목 사전이나 "
        "웹 검색으로 찾아 외형 설명과 참고 이미지를 이미지 모델에 전달합니다. Host 웹 검색 설정이 필요합니다. 실패해도 원래 프롬프트로 계속합니다.",
    ),
    "GeneralConfig.world_knowledge_model": (
        "Default: planner. Uses the models configured for the Host replyer, planner or vlm task group.",
        "既定は planner。Host の replyer、planner、vlm タスクグループに設定されたモデルを使用します。",
        "기본값은 planner입니다. Host의 replyer, planner 또는 vlm 작업 그룹에 설정된 모델을 사용합니다.",
    ),
    "GeneralConfig.world_knowledge_timeout_seconds": (
        "Default: 60 seconds, range 5–600. On timeout, drawing continues with the entries found so far; the task never fails because of it.",
        "既定は 60 秒、範囲は 5～600 秒。時間切れの場合はそれまでに得たエントリーで描画を続け、タスクは失敗しません。",
        "기본 60초, 범위 5~600초. 시간이 지나면 그때까지 찾은 항목으로 계속 그리며 작업이 실패하지 않습니다.",
    ),
    "GeneralConfig.world_knowledge_max_entities": (
        "Default: 3, range 0–5. 0 uses only entries you created or edited in the library, without model recognition.",
        "既定は 3、範囲は 0～5。0 の場合はモデルで認識せず、辞書で手動作成・編集したエントリーだけを使います。",
        "기본 3, 범위 0~5. 0이면 모델 인식 없이 사전에서 직접 만들거나 수정한 항목만 사용합니다.",
    ),
    "GeneralConfig.world_knowledge_max_searches": (
        "Default: 4, range 0–8. Unexpired library entries are not searched again; 0 uses the library only.",
        "既定は 4、範囲は 0～8。期限内の辞書エントリーは再検索しません。0 は辞書のみを使います。",
        "기본 4, 범위 0~8. 만료되지 않은 사전 항목은 다시 검색하지 않으며 0이면 사전만 사용합니다.",
    ),
    "GeneralConfig.world_knowledge_max_reference_images": (
        "Default: 2, range 0–2, also limited by how many source images the model accepts. Reference images turn text-to-image into "
        "image editing; models without image editing use the text notes only.",
        "既定は 2、範囲は 0～2。モデルが受け付ける元画像の枚数にも制限されます。参照画像を付けると文生図は画像編集になり、"
        "画像編集に対応しないモデルでは文字の説明だけを使います。",
        "기본 2, 범위 0~2이며 모델이 받는 원본 이미지 수에도 제한됩니다. 참고 이미지를 붙이면 텍스트 생성이 이미지 편집으로 바뀌고, "
        "이미지 편집을 지원하지 않는 모델은 텍스트 설명만 사용합니다.",
    ),
    "GeneralConfig.world_knowledge_auto_images": (
        "On by default. Checks game data sites and wikis first; if nothing is found and World Knowledge Image Search has a key, "
        "searches the web and lets the verification model pick one. Players and public figures are never fetched automatically; "
        "upload them in the workbench.",
        "既定は有効。まずゲーム資料サイトと wiki を探し、見つからず「ワールドナレッジ画像検索」にキーがあればウェブ検索し、"
        "検証モデルが 1 枚選びます。選手と著名人は自動取得せず、ワークベンチで手動アップロードできます。",
        "기본값은 켜짐입니다. 먼저 게임 자료 사이트와 위키를 찾고, 없으면 '월드 지식 이미지 검색'에 키가 있을 때 웹을 검색해 "
        "검증 모델이 한 장을 고릅니다. 선수와 공인은 자동으로 가져오지 않으며 워크벤치에서 직접 올릴 수 있습니다.",
    ),
    "GeneralConfig.world_knowledge_screen_images": (
        "Off by default. When on, each automatically found image costs one more image-review model call to confirm it shows the subject.",
        "既定は無効。有効にすると、自動で見つけた画像ごとに画像審査モデルを 1 回呼び出して対象かどうか確認します。",
        "기본값은 꺼짐입니다. 켜면 자동으로 찾은 이미지마다 이미지 검토 모델을 한 번 더 호출해 대상이 맞는지 확인합니다.",
    ),
    "GeneralConfig.world_knowledge_allow_fake_ip": (
        "Off by default. Enable only when a TUN proxy (Clash, sing-box) resolves sites to 198.18.x.x and downloads fail. Other private addresses are always refused.",
        "既定は無効。TUN プロキシ（Clash、sing-box など）でサイトが 198.18.x.x に解決されて取得に失敗する場合だけ有効にしてください。その他の内部アドレスは常に拒否します。",
        "기본값은 꺼짐입니다. TUN 프록시(Clash, sing-box 등)에서 사이트가 198.18.x.x로 해석되어 다운로드가 실패할 때만 켜세요. 다른 내부 주소는 항상 거부합니다.",
    ),
    "GeneralConfig.world_knowledge_verify_enabled": (
        "Off by default. Checks only when this drawing used entries with appearance notes or reference images, comparing against "
        "the supplied references only; differences in style and pose are not errors.",
        "既定は無効。外見メモや参照画像のあるエントリーを使った場合だけ、与えた参照資料とだけ照合します。画風やポーズの違いは誤りとしません。",
        "기본값은 꺼짐입니다. 외형 설명이나 참고 이미지가 있는 항목을 사용한 경우에만 제공된 참고 자료와만 비교하며, 화풍과 자세 차이는 오류로 보지 않습니다.",
    ),
    "GeneralConfig.world_knowledge_verify_model": (
        "Default: vlm. Models in the selected group must accept several images; otherwise the check is treated as passed.",
        "既定は vlm。選択したグループのモデルは複数画像の入力に対応している必要があります。対応しない場合は確認を合格扱いにします。",
        "기본값은 vlm입니다. 선택한 그룹의 모델은 여러 이미지 입력을 지원해야 하며, 그렇지 않으면 확인을 통과로 처리합니다.",
    ),
    "GeneralConfig.world_knowledge_redraw_enabled": (
        "On by default. Redraws once with no extra quota, roughly doubling task time; compares again and keeps the more accurate image. "
        "A failed redraw keeps the original.",
        "既定は有効。追加の回数消費なしで 1 回だけ再生成し、所要時間はおよそ 2 倍になります。再度比較してより正確な方を残し、再生成に失敗した場合は元の画像を残します。",
        "기본값은 켜짐입니다. 추가 횟수 차감 없이 한 번만 다시 그리며 작업 시간이 약 두 배가 됩니다. 다시 비교해 더 정확한 이미지를 남기고, 다시 그리기에 실패하면 원본을 남깁니다.",
    ),
    "OpenAIModelConfig.request_mode": (
        "images: call the image generation/edit endpoints directly (default). responses_background: submit a "
        "Responses API background task and poll for the result, so every HTTP request stays short and proxies that "
        "drop connections idle for ~100 seconds cannot cut long requests. Only for OpenAI or services fully "
        "compatible with /v1/responses; applies to gpt-image models only and leaves chat drawing and RinkoAI modes "
        "unchanged. OpenAI keeps the result for about 10 minutes. Raise the general image request timeout to about "
        "300 seconds as well.",
        "images：画像生成／編集エンドポイントを直接呼び出します（既定）。responses_background：Responses API の"
        "バックグラウンドタスクとして送信し結果をポーリングします。各 HTTP リクエストが短くなり、約 100 秒無通信の接続を"
        "切断するプロキシでも長い生成が途切れません。OpenAI 公式または /v1/responses に完全対応したサービスのみ対応し、"
        "gpt-image 系列にだけ適用され、チャット描画と RinkoAI モードには影響しません。結果は OpenAI 側に約 10 分保持されます。"
        "一般設定の画像リクエストのタイムアウトも 300 秒程度に上げてください。",
        "images: 이미지 생성/편집 엔드포인트를 직접 호출합니다(기본값). responses_background: Responses API 백그라운드 "
        "작업으로 제출한 뒤 결과를 폴링합니다. 모든 HTTP 요청이 짧아져 약 100초 동안 데이터가 없으면 연결을 끊는 프록시에서도 "
        "긴 생성이 끊기지 않습니다. OpenAI 공식 또는 /v1/responses를 완전히 지원하는 서비스에서만 사용할 수 있으며, "
        "gpt-image 계열에만 적용되고 채팅 그리기와 RinkoAI 모드에는 영향이 없습니다. 결과는 OpenAI 측에 약 10분간 보관됩니다. "
        "일반 설정의 이미지 요청 시간 제한도 300초 정도로 늘리세요.",
    ),
    "OpenAICompatibleInstanceConfig.request_mode": (
        "images calls the image endpoints directly; responses_background submits a Responses API background task and "
        "polls, avoiding proxy idle disconnects. gpt-image models only.",
        "images は画像エンドポイントを直接呼び出し、responses_background は Responses API のバックグラウンドタスクを"
        "送信してポーリングし、プロキシの無通信切断を避けます。gpt-image 系列のみ対象です。",
        "images는 이미지 엔드포인트를 직접 호출하고, responses_background는 Responses API 백그라운드 작업을 제출해 "
        "폴링하여 프록시의 무통신 연결 끊김을 피합니다. gpt-image 계열에만 적용됩니다.",
    ),
    "OpenAIModelConfig.responses_main_model": (
        "Used only by responses_background. The main model just forwards the prompt verbatim, so a cheap small model "
        "is enough.",
        "responses_background でのみ使用します。メインモデルはプロンプトをそのまま渡すだけなので、安価な小型モデルで十分です。",
        "responses_background에서만 사용합니다. 메인 모델은 프롬프트를 그대로 전달하기만 하므로 저렴한 소형 모델이면 충분합니다.",
    ),
    "OpenAIModelConfig.responses_poll_interval_seconds": (
        "Seconds between status checks, 1 to 30, default 3; very low values may hit query rate limits.",
        "状態確認の間隔（秒）。1～30、既定 3。低すぎると照会のレート制限に当たることがあります。",
        "상태 확인 간격(초), 1～30, 기본값 3. 너무 낮으면 조회 속도 제한에 걸릴 수 있습니다.",
    ),
    "OpenAIModelConfig.edit_size_mode": (
        "source: follow the aspect ratio of the first source image (default). configured: always use the default "
        "resolution or per-model override above; useful when reference images differ from the target canvas, "
        "such as portrait comics drawn with character references.",
        "source：1 枚目のソース画像の縦横比に従います（既定）。configured：常に上の既定の解像度またはモデル別上書きを使います。"
        "キャラクター参照画像付きの縦長漫画など、参照画像と目標キャンバスの比率が異なる場合に使います。",
        "source: 첫 번째 원본 이미지의 비율을 따릅니다(기본값). configured: 항상 위의 기본 해상도 또는 모델별 재정의를 사용합니다. "
        "캐릭터 참조 이미지를 쓰는 세로 만화처럼 참조 이미지와 목표 캔버스 비율이 다를 때 사용합니다.",
    ),
    "OpenAICompatibleInstanceConfig.edit_size_mode": (
        "source follows the first source image's aspect ratio; configured always uses the default resolution, "
        "useful when reference images differ from the target canvas.",
        "source は 1 枚目のソース画像の比率に従い、configured は常に既定の解像度を使います。参照画像と目標キャンバスの比率が異なる場合に使います。",
        "source는 첫 번째 원본 이미지 비율을 따르고, configured는 항상 기본 해상도를 사용합니다. 참조 이미지와 목표 캔버스 비율이 다를 때 사용합니다.",
    ),
    "CodexAgentConfig.access_scope": (
        "admin follows the general permission setting: only plugin administrators may use it (everyone when command "
        "permissions are disabled). all allows every user. The agent browses the web and consumes Codex quota.",
        "admin は一般設定の権限管理に従い、プラグイン管理者のみ使用できます（権限管理が無効なら全員）。"
        "all は全ユーザーが使用できます。エージェントはウェブを検索し Codex の利用枠を消費します。",
        "admin은 일반 설정의 권한 관리를 따르며 플러그인 관리자만 사용할 수 있습니다(권한 관리가 꺼져 있으면 모두). "
        "all은 모든 사용자가 사용할 수 있습니다. 에이전트는 웹을 검색하고 Codex 사용량을 소모합니다.",
    ),
    "CodexAgentConfig.models": (
        "Chat models available in Codex. Images are produced by Codex's built-in image tool, which picks the image model.",
        "Codex で利用できる対話モデルを入力します。画像は Codex 内蔵の画像ツールが生成し、画像モデルは Codex が選びます。",
        "Codex에서 사용 가능한 대화 모델을 입력하세요. 이미지는 Codex 내장 이미지 도구가 생성하며 이미지 모델은 Codex가 결정합니다.",
    ),
    "CodexAgentConfig.reasoning_effort": (
        "default keeps the Codex default. Higher effort researches more thoroughly but takes longer and uses more quota.",
        "default は Codex の既定値を使用します。強度が高いほど調査は丁寧になりますが、時間と利用枠を多く消費します。",
        "default는 Codex 기본값을 사용합니다. 강도가 높을수록 조사가 충실하지만 시간과 사용량이 늘어납니다.",
    ),
    "CodexAgentConfig.codex_path": (
        "Leave empty to search PATH and the newest Codex desktop codex.exe under %LOCALAPPDATA%\\OpenAI\\Codex\\bin.",
        "空欄では PATH と %LOCALAPPDATA%\\OpenAI\\Codex\\bin 配下の最新の codex.exe を自動検出します。",
        "비워 두면 PATH와 %LOCALAPPDATA%\\OpenAI\\Codex\\bin 아래 최신 codex.exe를 자동으로 찾습니다.",
    ),
    "CodexAgentConfig.codex_home": (
        "Leave empty to use CODEX_HOME or ~/.codex. It must be signed in, and MaiBot must run as the same OS user.",
        "空欄では CODEX_HOME または ~/.codex を使用します。ログイン済みで、MaiBot が同じ OS ユーザーで動作している必要があります。",
        "비워 두면 CODEX_HOME 또는 ~/.codex를 사용합니다. 로그인되어 있어야 하며 MaiBot이 같은 OS 사용자로 실행되어야 합니다.",
    ),
    "CodexAgentConfig.task_timeout_seconds": (
        "Maximum run time once the task starts, excluding queue time and independent of the general image request timeout. Research and refinement often take minutes.",
        "順番が来て Codex が動き始めてからの最大時間です。待機時間は含まず、一般の画像リクエストタイムアウトとも別です。調査と調整には数分かかることがあります。",
        "차례가 되어 Codex가 실행된 뒤의 최대 시간입니다. 대기 시간은 포함하지 않으며 일반 이미지 요청 시간 제한과 별개입니다. 조사와 조정에 몇 분이 걸릴 수 있습니다.",
    ),
    "CodexAgentConfig.max_concurrent_tasks": (
        "Maximum Codex tasks running at once for the same CODEX_HOME. Extra tasks wait in submission order.",
        "同じ CODEX_HOME で同時に実行する Codex タスクの上限です。超えたタスクは提出順に待機します。",
        "같은 CODEX_HOME에서 동시에 실행할 Codex 작업 수입니다. 초과한 작업은 제출 순서대로 대기합니다.",
    ),
    "CodexAgentConfig.max_queued_tasks": (
        "Tasks allowed to wait when all run slots are busy. A full queue is refused before quota is charged; 0 disables queueing.",
        "実行枠が埋まっているときに待機できるタスク数です。満杯なら利用回数を消費する前に拒否します。0 は待機なしです。",
        "실행 슬롯이 모두 사용 중일 때 대기할 수 있는 작업 수입니다. 가득 차면 횟수를 차감하기 전에 거부하며 0이면 대기하지 않습니다.",
    ),
    "CodexAgentConfig.queue_timeout_seconds": (
        "Give up after waiting this long; the request was never sent. Use a fallback model if configured, otherwise fail and refund without queueing again.",
        "この時間待っても順番が来なければ諦めます（リクエストは未送信）。代替モデルがあれば使用し、なければ失敗として回数を返却し、再度は待機しません。",
        "이 시간 동안 차례가 오지 않으면 포기합니다(요청은 전송되지 않음). 대체 모델이 있으면 사용하고, 없으면 실패 처리 후 횟수를 반환하며 다시 대기하지 않습니다.",
    ),
    "CodexAgentConfig.max_reference_downloads": (
        "The agent fetches references only through the plugin's restricted downloader (public HTTP(S), verified images). 0 disables it.",
        "エージェントはプラグインの制限付きダウンロードツール（公開 HTTP(S)、画像検証あり）のみで参照画像を取得します。0 で無効です。",
        "에이전트는 플러그인의 제한된 다운로드 도구(공개 HTTP(S), 이미지 검증)로만 참조 이미지를 가져옵니다. 0이면 사용하지 않습니다.",
    ),
    "CodexAgentConfig.allow_proxy_fake_ip": (
        "Proxy TUN fake-ip modes resolve domains to 198.18.0.0/15. When enabled, reference downloads allow that range; other private addresses stay blocked.",
        "プロキシ TUN の fake-ip モードではドメインが 198.18.0.0/15 に解決されます。有効にすると参照画像の取得でこの範囲を許可し、他のプライベートアドレスは拒否します。",
        "프록시 TUN fake-ip 모드는 도메인을 198.18.0.0/15로 해석합니다. 켜면 참조 이미지 다운로드에서 이 범위를 허용하며 다른 사설 주소는 계속 차단합니다.",
    ),
    "CodexAgentConfig.resume_enabled": (
        "When an edit's source image was recently generated by this platform, continue the Codex session that produced it.",
        "画像変換の元画像がこのプラットフォームで最近生成されたものなら、それを生成した Codex セッションを継続します。",
        "이미지 변환의 원본이 최근 이 플랫폼에서 생성된 경우 해당 Codex 세션을 이어갑니다.",
    ),
    "CodexAgentConfig.thread_retention_days": (
        "Older sessions are no longer resumed, and the plugin's stored references and inputs for them are removed.",
        "期間を過ぎたセッションは継続せず、プラグインが保存した参照画像と入力画像を削除します。",
        "기간이 지난 세션은 이어가지 않으며 플러그인이 저장한 참조 이미지와 입력 이미지를 삭제합니다.",
    ),
    "CodexAgentConfig.deliver_all_images": (
        "Off sends only the final image chosen by the agent; on sends every image generated in the turn.",
        "オフではエージェントが選んだ最終画像のみ、オンではこのターンで生成した全画像を送信します。",
        "끄면 에이전트가 선택한 최종 이미지만, 켜면 이번 턴에 생성된 모든 이미지를 전송합니다.",
    ),
    "CodexAgentConfig.agent_instructions": (
        "Fixed instructions added to every request. Tool and safety restrictions are enforced by the plugin regardless.",
        "毎回のリクエストに付加する固定指示です。ツールと安全上の制限はプラグインが常に適用します。",
        "모든 요청에 덧붙이는 고정 지침입니다. 도구와 보안 제한은 플러그인이 항상 적용합니다.",
    ),
    "ReferenceConfig.material_model": (
        "A fast multimodal model is recommended. Use planner, replyer, vlm, or a configured MaiBot model name.",
        "高速なマルチモーダルモデルを推奨します。planner、replyer、vlm、またはMaiBotに設定済みのモデル名を指定できます。",
        "빠른 멀티모달 모델을 권장합니다. planner, replyer, vlm 또는 MaiBot에 설정된 모델 이름을 사용할 수 있습니다.",
    ),
    "ReferenceConfig.web_search_provider": (
        "MaiBot uses the host's configured search service. DeepSeek uses a separate API key.",
        "MaiBotはホストの検索設定を使い、DeepSeekは別途入力したAPIキーを使います。",
        "MaiBot은 호스트의 검색 서비스를 사용하고 DeepSeek은 별도 API 키를 사용합니다.",
    ),
    "ReferenceConfig.deepseek_api_key": (
        "Leave empty to keep the saved key. Search API returns web pages; candidate images are extracted from them.",
        "空欄では保存済みキーを保持します。Search APIのウェブ結果から候補画像を抽出します。",
        "비워 두면 저장된 키를 유지합니다. Search API가 반환한 웹 페이지에서 후보 이미지를 추출합니다.",
    ),
    "ReferenceConfig.allow_chat_material_search": (
        "Read prior images only for clear follow-up edits or regeneration requests.",
        "前図の編集・再生成を明確に続ける場合だけ履歴画像を探します。",
        "이전 그림의 수정이나 재생성을 명확히 이어갈 때만 대화 이미지를 찾습니다.",
    ),
    "ReferenceConfig.self_reference_ids": (
        "Leave empty to select one image by gallery tags, using the default image when no tag matches. Select images only to keep a fixed appearance.",
        "空欄ではギャラリーのタグで1枚を選び、一致しなければ既定画像を使います。外見を固定する場合に画像を選択してください。",
        "비워 두면 갤러리 태그로 한 장을 선택하고 일치하지 않으면 기본 이미지를 사용합니다. 외형을 고정하려면 이미지를 선택하세요.",
    ),
    "StylePresetConfig.tags": (
        "Keywords for automatic selection, such as watercolor. More matching tags take priority; ties follow list order. With no match, use the default preset. Explicit preset choices ignore tags.",
        "水彩など、自動選択に使うキーワードです。一致数が多い項目を優先し、同数ならリスト順、一致なしなら既定項目を使います。手動選択はタグに依存しません。",
        "수채화 같은 자동 선택 키워드입니다. 일치 태그가 많은 항목을 우선하고 동점이면 목록 순서, 일치하지 않으면 기본 프리셋을 사용합니다. 직접 선택은 태그와 무관합니다.",
    ),
    "StylePresetConfig.description": (
        "Describe the look and suitable scenes to help users and the chat model choose a style. Web automatic selection uses tags.",
        "見た目や適した場面を説明し、ユーザーとチャットモデルの選択を助けます。Webの自動選択はタグを使います。",
        "시각적 특징과 적합한 장면을 설명하여 사용자와 대화 모델의 스타일 선택을 돕습니다. 웹 자동 선택은 태그를 사용합니다.",
    ),
    "ReferenceConfig.chat_material_search_limit": (
        "Recommended: 50 messages; range: 1–200. Search only the current chat within the last 24 hours and select at most 6 candidate images.",
        "推奨は50件、設定範囲は1～200件です。現在のチャットの直近24時間のみ検索し、候補画像は最大6枚です。",
        "권장값은 50개이며 1~200개로 설정할 수 있습니다. 현재 대화의 최근 24시간만 검색하고 후보 이미지는 최대 6장 선택합니다.",
    ),
    "ReferenceConfig.allow_web_material_search": (
        "Search only for named characters, specific objects or explicit reference requests.",
        "指定キャラ、特定物品、明示的な参照画像探しのみ検索します。",
        "지정 캐릭터, 특정 물건 또는 명시적인 참고 이미지 요청만 검색합니다.",
    ),
    "ReferenceConfig.self_keywords": (
        "For example: selfie, draw, drawing. Matching tags remind the planner to consider drawing; bot identity still depends on meaning. Add with Enter or commas; leave empty to disable reminders.",
        "例：自撮り、描いて、作画。一致したら描画の判断を促し、自身かどうかは文意で判断します。Enterまたはカンマで追加、空欄で通知を無効にします。",
        "예: 셀카, 그려, 그림. 일치하면 그림 요청인지 판단하도록 알리며 봇 자신인지는 의미로 구분합니다. Enter 또는 쉼표로 추가하고 비우면 알림을 끕니다.",
    ),
    "SiliconFlowModelConfig.watermark_enabled": (
        "Enabled by default. The invisible watermark remains when disabled.",
        "既定は有効です。無効にしても不可視の透かしは残ります。",
        "기본적으로 켜져 있으며 꺼도 비표시 워터마크는 유지됩니다.",
    ),
    "MiniMaxModelConfig.enabled": ("Enabled. See the MiniMax model-specific limits in the platform guide.", "有効。モデルごとの制約はプラットフォームガイドを参照してください。", "활성화. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.api_key": ("API Key. See the MiniMax model-specific limits in the platform guide.", "API キー。モデルごとの制約はプラットフォームガイドを参照してください。", "API 키. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.base_url": ("API Base URL. See the MiniMax model-specific limits in the platform guide.", "API 基本 URL。モデルごとの制約はプラットフォームガイドを参照してください。", "API 기본 URL. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.models": ("Defaults to MiniMax-H3-Image. Add H3 Highspeed or image-01 variants from the documented presets; image-01 editing is character reference only.", "既定は MiniMax-H3-Image。公式プリセットから他の H3/image-01 を追加できます。image-01 の編集は人物参照です。", "기본 모델은 MiniMax-H3-Image입니다. 공식 문서 프리셋에서 다른 H3/image-01 모델을 추가하세요. image-01 편집은 인물 참조입니다."),
    "MiniMaxModelConfig.size": ("auto or WIDTHxHEIGHT. H3 explicit dimensions cannot be combined with aspect_ratio/area. image-01 dimensions must be multiples of 8 in 512–2048; not supported by live.", "auto または 幅x高さ。H3 の固定サイズは比率・面積と併用不可。image-01 は 512～2048 の8の倍数、live は固定サイズ不可。", "auto 또는 너비x높이. H3 고정 크기는 비율/면적과 함께 사용할 수 없습니다. image-01은 512~2048 범위의 8의 배수이며 live에는 고정 크기를 지원하지 않습니다."),
    "MiniMaxModelConfig.model_size_overrides": ("Per-model Sizes. See the MiniMax model-specific limits in the platform guide.", "モデル別サイズ。モデルごとの制約はプラットフォームガイドを参照してください。", "모델별 크기. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.aspect_ratio": ("Aspect Ratio. See the MiniMax model-specific limits in the platform guide.", "アスペクト比。モデルごとの制約はプラットフォームガイドを参照してください。", "화면 비율. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.area": ("H3 only, with size=auto. Leave blank for the server default of 4K; choose 1K/2K to reduce output area.", "H3 の size=auto のみ。空欄はサーバー既定の 4K。面積を抑えるには 1K/2K を選択します。", "H3의 size=auto에서만 사용합니다. 비우면 서버 기본 4K이며 면적을 줄이려면 1K/2K를 선택하세요."),
    "MiniMaxModelConfig.n": ("H3: 1–10; image-01: 1–9. Partial success returns only successful images without regenerating failed items.", "H3 は1～10枚、image-01 は1～9枚。部分成功時は成功画像のみ返し、失敗分を再生成しません。", "H3는 1~10장, image-01은 1~9장입니다. 일부 성공 시 성공한 이미지만 반환하고 실패 이미지를 다시 생성하지 않습니다."),
    "MiniMaxModelConfig.response_format": ("Response Format. See the MiniMax model-specific limits in the platform guide.", "応答形式。モデルごとの制約はプラットフォームガイドを参照してください。", "응답 형식. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.output_format": ("H3 Output Format. See the MiniMax model-specific limits in the platform guide.", "H3 出力形式。モデルごとの制約はプラットフォームガイドを参照してください。", "H3 출력 형식. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.output_compression": ("H3 Compression Quality. See the MiniMax model-specific limits in the platform guide.", "H3 圧縮品質。モデルごとの制約はプラットフォームガイドを参照してください。", "H3 압축 품질. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.stream": ("H3 only and URL responses only. Results are collected in image-index order; interrupted streams never resubmit generation.", "H3 の URL 応答のみ。画像番号順に収集し、ストリーム切断時も再生成しません。", "H3의 URL 응답에만 적용됩니다. 이미지 인덱스 순서로 수집하며 스트림 중단 시 다시 생성하지 않습니다."),
    "MiniMaxModelConfig.disable_prompt_enhanced": ("H3 text-to-image only. Disabling enhancement requires explicit dimensions or a fixed ratio. Editing always uses enhancement.", "H3 文生図のみ。無効化時は固定サイズか比率が必須。画像編集は常に強化を使用します。", "H3 텍스트 이미지 생성에만 적용됩니다. 끄려면 고정 크기나 비율을 지정해야 하며 편집은 항상 강화를 사용합니다."),
    "MiniMaxModelConfig.prompt_optimizer": ("image-01 Prompt Optimizer. See the MiniMax model-specific limits in the platform guide.", "image-01 プロンプト最適化。モデルごとの制約はプラットフォームガイドを参照してください。", "image-01 프롬프트 최적화. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.seed": ("image-01 only. -1 omits the parameter; zero is a valid seed. H3 does not declare a seed parameter.", "image-01 のみ。-1 は未送信、0 は有効です。H3 は seed 非対応です。", "image-01에만 사용합니다. -1이면 생략하며 0은 유효한 시드입니다. H3는 seed를 지원하지 않습니다."),
    "MiniMaxModelConfig.style_type": ("image-01-live Style. See the MiniMax model-specific limits in the platform guide.", "image-01-live スタイル。モデルごとの制約はプラットフォームガイドを参照してください。", "image-01-live 스타일. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.style_weight": ("image-01-live Style Weight. See the MiniMax model-specific limits in the platform guide.", "image-01-live スタイル強度。モデルごとの制約はプラットフォームガイドを参照してください。", "image-01-live 스타일 가중치. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.aigc_watermark": ("Visible AIGC Watermark. See the MiniMax model-specific limits in the platform guide.", "AIGC 可視透かし。モデルごとの制約はプラットフォームガイドを参照してください。", "AIGC 표시 워터마크. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "MiniMaxModelConfig.request_timeout_seconds": ("Instance timeout in seconds, default/minimum 600. MiniMax is non-idempotent: timeout and result-read failures never regenerate.", "インスタンスごとの秒数、既定・最小600秒。MiniMax は冪等でなく、タイムアウトや結果読込失敗時も再生成しません。", "인스턴스별 제한 시간(초)으로 기본/최솟값은 600입니다. MiniMax는 멱등하지 않으며 시간 초과나 결과 읽기 실패 시 다시 생성하지 않습니다."),
    "MiniMaxModelConfig.extra_parameters": ("KEY=VALUE extensions. Cannot replace model, prompt or source images, or mix known H3/image-01 protocol fields.", "名前=値。モデル・プロンプト・元画像の上書きや H3/image-01 の異なるプロトコル項目の混在は禁止です。", "이름=값 형식의 확장입니다. 모델, 프롬프트, 원본 이미지를 덮어쓰거나 H3/image-01의 서로 다른 프로토콜 필드를 혼합할 수 없습니다."),
    "MiniMaxModelConfig.rewrite_prompt_to_english": ("Rewrite Prompt in English. See the MiniMax model-specific limits in the platform guide.", "英語プロンプトに変換。モデルごとの制約はプラットフォームガイドを参照してください。", "영어 프롬프트로 변환. 모델별 제한은 플랫폼 가이드를 참조하세요."),
    "GeneralConfig.integration_api_enabled": (
        "On by default. Disable all public plugin integration APIs. Workspace, chat commands and AI tools remain available. Accepted tasks continue.",
        "既定は有効です。無効にすると公開連携 API を拒否します。ワークスペース、コマンド、AI ツールは使用可能で、受理済みタスクは継続します。",
        "기본적으로 켜져 있습니다. 끄면 모든 공개 연동 API를 거부합니다. 작업 공간, 명령, AI 도구는 계속 사용할 수 있으며 접수된 작업도 계속 실행됩니다.",
    ),
    "GeneralConfig.group_access_mode": (
        "Blacklist by default: an empty list allows all groups. An empty whitelist denies all groups. Administrators follow the same rules.",
        "既定はブラックリストで、空欄なら全グループを許可します。空のホワイトリストは全グループを拒否します。管理者も対象です。",
        "기본은 차단 목록이며 빈 목록은 모든 그룹을 허용합니다. 빈 허용 목록은 모든 그룹을 거부합니다. 관리자에게도 적용됩니다.",
    ),
    "GeneralConfig.group_access_ids": (
        "One group number per entry; use group OpenID for the official QQ adapter. Do not enter stream IDs, session hashes or member QQ numbers.",
        "各項目にグループ番号を入力します。QQ 公式アダプターはグループ OpenID を使用します。stream ID、会話ハッシュ、メンバー番号は不要です。",
        "항목마다 그룹 번호를 입력합니다. QQ 공식 어댑터는 그룹 OpenID를 사용합니다. 스트림 ID, 대화 해시, 멤버 QQ 번호는 입력하지 마세요.",
    ),
    "GeneralConfig.private_access_mode": (
        "Blacklist by default: an empty list allows all private chats. An empty whitelist denies all private chats. Does not restrict users inside groups.",
        "既定はブラックリストで、空欄なら全個人チャットを許可します。空のホワイトリストは全個人チャットを拒否します。グループ内での利用には影響しません。",
        "기본은 차단 목록이며 빈 목록은 모든 개인 대화를 허용합니다. 빈 허용 목록은 모든 개인 대화를 거부합니다. 그룹 내 사용에는 영향을 주지 않습니다.",
    ),
    "GeneralConfig.private_access_ids": (
        "One QQ number per entry; use user OpenID for the official QQ adapter. No stream ID or session hash is needed. OpenIDs are matched exactly.",
        "各項目に QQ 番号を入力します。QQ 公式アダプターはユーザー OpenID を使用します。stream ID や会話ハッシュは不要です。OpenID は完全一致で照合します。",
        "항목마다 QQ 번호를 입력합니다. QQ 공식 어댑터는 사용자 OpenID를 사용합니다. 스트림 ID나 대화 해시는 필요하지 않습니다. OpenID는 정확히 일치해야 합니다.",
    ),
    "GeneralConfig.sync_generated_images_to_history": (
        "Off by default. After successful delivery, let a visual Planner view generated images; a text Planner uses image descriptions. May increase visual context and background recognition costs. Tasks without chat delivery and command reply cards are unaffected.",
        "既定は無効です。送信成功後、視覚 Planner は生成画像を参照でき、テキスト Planner は画像説明を使用します。視覚コンテキストとバックグラウンド画像認識のコストが増える場合があります。会話に送信しないタスクとコマンド応答カードには適用しません。",
        "기본적으로 꺼져 있습니다. 전송 성공 후 시각 Planner는 생성 이미지를 볼 수 있고 텍스트 Planner는 이미지 설명을 사용합니다. 시각 컨텍스트 및 백그라운드 이미지 인식 비용이 늘어날 수 있습니다. 대화로 전송하지 않는 작업과 명령 응답 카드에는 적용하지 않습니다.",
    ),
    "StyleConfig.default_style": (
        "Automatically applied when AI tools, ordinary drawing commands, the workspace or plugin APIs omit a style. Select an enabled preset. Leave blank to disable automatic styling; explicitly choose no style to skip it for one request.",
        "AI ツール、通常の描画コマンド、ワークスペース、プラグイン API でスタイル未指定の場合に自動適用します。有効なプリセットを選択してください。空欄は自動適用なしで、明示的にスタイルなしを選べば今回だけ省略できます。",
        "AI 도구, 일반 그리기 명령, 작업 공간, 플러그인 API가 스타일을 생략하면 자동 적용합니다. 활성 프리셋을 선택하세요. 비워 두면 자동 적용하지 않으며 명시적으로 스타일 없음을 선택하면 이번 요청에서 건너뜁니다.",
    ),
    "negative_prompt_enabled": (
        "When disabled, ignore negative prompts from AI tools, commands, the workspace and APIs, including this instance's defaults. Style presets keep their own positive and negative content.",
        "無効時は AI ツール、コマンド、ワークスペース、API のネガティブプロンプトと、このインスタンスの既定値を無視します。スタイル固有の正負プロンプトは保持されます。",
        "비활성화하면 AI 도구, 명령, 작업 공간, API의 네거티브 프롬프트와 이 인스턴스의 기본값을 무시합니다. 스타일 자체의 긍정 및 부정 내용은 유지됩니다.",
    ),
    "negative_prompt": (
        "Used only when negative prompts are enabled. Append to the request, remove duplicate terms with the style preset, and include in English rewriting. Providers without a separate negative field receive the merged prompt.",
        "ネガティブプロンプトが有効な場合のみ使用します。今回の入力に追加し、スタイルとの重複語を除去して英語書き換えにも含めます。専用フィールドのないサービスでは本文に統合します。",
        "네거티브 프롬프트가 활성화된 경우에만 사용합니다. 요청 뒤에 추가하고 스타일과 중복되는 항목을 제거하며 영어 변환에도 포함합니다. 별도 필드가 없는 제공자는 본문에 합칩니다.",
    ),
    "GeneralConfig.prompt_review_retry_count": (
        "Default: 2 extra retries, at most 3 calls. Range 0–5; 0 disables retries. Explicit rejection and cancellation never retry.",
        "既定は追加 2 回、最大 3 回の呼び出しです。範囲は 0～5、0 で無効。明確な拒否とキャンセルは再試行しません。",
        "기본 추가 2회, 최대 3회 호출합니다. 범위 0~5, 0이면 재시도하지 않습니다. 명시적 거부와 취소는 재시도하지 않습니다.",
    ),
    "GeneralConfig.image_review_retry_count": (
        "Default: 2 extra retries, at most 3 calls. Range 0–5. Retry only review of the same image, never generation; rejection and cancellation do not retry.",
        "既定は追加 2 回、最大 3 回の呼び出しです。範囲は 0～5。同じ画像の審査だけを再試行し、再生成は行いません。拒否とキャンセルは再試行しません。",
        "기본 추가 2회, 최대 3회 호출합니다. 범위 0~5. 같은 이미지의 검토만 재시도하고 이미지를 다시 생성하지 않습니다. 거부와 취소는 재시도하지 않습니다.",
    ),
    "GeneralConfig.prompt_review_model": (
        "Default: vlm. Use the models configured for the Host replyer, planner or vlm task group.",
        "既定は vlm。Host の replyer、planner、vlm タスクグループに設定されたモデルを使用します。",
        "기본값은 vlm입니다. Host의 replyer, planner 또는 vlm 작업 그룹에 설정된 모델을 사용합니다.",
    ),
    "GeneralConfig.image_review_model": (
        "Default: vlm. replyer and planner are also available, but every model in the selected group must support images or review fails.",
        "既定は vlm。replyer と planner も選択できますが、選択したグループのモデルが画像入力に対応していない場合は審査に失敗します。",
        "기본값은 vlm입니다. replyer와 planner도 선택할 수 있지만 선택한 그룹의 모델이 이미지 입력을 지원하지 않으면 검토에 실패합니다.",
    ),
    "GeneralConfig.prompt_review_timeout_seconds": (
        "Default: 60 seconds per attempt, range 5–600; retries have separate budgets. Continue immediately when review finishes, without bypassing failed review.",
        "1 回の既定は 60 秒、範囲は 5～600 秒。再試行は別の待機枠です。完了後すぐに続行し、失敗した審査は省略しません。",
        "시도당 기본 60초, 범위 5~600초. 재시도마다 별도의 대기 시간을 사용합니다. 검토 완료 시 즉시 진행하며 실패한 검토를 생략하지 않습니다.",
    ),
    "GeneralConfig.image_review_timeout_seconds": (
        "Default: 60 seconds per image per attempt, range 5–600; retries are separate. Independent of generation and prompt review. Failed review never releases or regenerates images.",
        "画像 1 枚の 1 回あたり既定 60 秒、範囲 5～600 秒。再試行は別枠で、画像生成・プロンプト審査とは独立しています。失敗した審査で送信や再生成は行いません。",
        "이미지별 시도당 기본 60초, 범위 5~600초. 재시도는 별도로 계산하며 생성 및 프롬프트 검토와 독립적입니다. 검토 실패 시 전송하거나 다시 생성하지 않습니다.",
    ),
    "GeneralConfig.skip_image_url_ip_check": (
        "Off by default. Enable only for trusted services to allow private or special-DNS image hosts. HTTP(S) URL and redirect checks remain. Proxied hostnames are always resolved by the proxy.",
        "既定は無効です。信頼できるサービスの内部ネットワークや特殊 DNS の画像ホストにのみ使用してください。HTTP(S) URL と各リダイレクトの検証は継続します。プロキシ経由のドメインは常にプロキシ側で解決します。",
        "기본적으로 꺼져 있습니다. 신뢰할 수 있는 서비스의 사설망 또는 특수 DNS 이미지 호스트에만 사용하세요. HTTP(S) URL 및 리디렉션 검사는 유지됩니다. 프록시를 사용하는 도메인은 항상 프록시에서 해석합니다.",
    ),
    "NovelAIModelConfig.models": (
        "Add official presets or enter compatible-service model IDs in this single list. Save the platform to apply changes.",
        "公式プリセットの追加と互換サービスのモデル ID の入力を同じ一覧で行います。プラットフォームを保存すると反映されます。",
        "공식 프리셋 추가와 호환 서비스 모델 ID 입력을 하나의 목록에서 관리합니다. 플랫폼을 저장하면 적용됩니다.",
    ),
    "NovelAIModelConfig.custom_models": (
        "Legacy custom models are merged into the unified model list and are no longer edited separately.",
        "旧カスタムモデルは統一モデル一覧へ統合され、個別には編集しません。",
        "기존 사용자 지정 모델은 통합 모델 목록에 병합되며 별도로 편집하지 않습니다.",
    ),
    "AgnesModelConfig.base_url": (
        "Use the API base URL, not the console or documentation URL.",
        "コンソールやドキュメントではなく API のベース URL を入力します。",
        "콘솔이나 문서 주소가 아닌 API 기본 URL을 입력하세요.",
    ),
    "AgnesModelConfig.models": (
        "Image models available to your account, supporting generation and editing with multiple reference images.",
        "アカウントで利用可能な画像モデルを指定します。画像生成と複数の参照画像による編集に対応します。",
        "계정에서 사용 가능한 이미지 모델을 입력하세요. 이미지 생성과 여러 참조 이미지 편집을 지원합니다.",
    ),
    "AgnesModelConfig.default_size": (
        "For 2.1 / 2.5, prefer 1K–4K tiers with an aspect ratio; pixel dimensions are also accepted but may be adjusted. Use only pixel dimensions for 2.0, with per-model overrides below.",
        "2.1 / 2.5 は 1K～4K と縦横比の組み合わせを推奨します。ピクセル寸法も指定できますが、調整される場合があります。2.0 はピクセル寸法のみを使用し、下でモデル別に上書きできます。",
        "2.1 / 2.5는 1K~4K와 화면 비율 조합을 권장합니다. 픽셀 크기도 사용할 수 있지만 조정될 수 있습니다. 2.0은 픽셀 크기만 사용하며 아래에서 모델별로 설정할 수 있습니다.",
    ),
    "AgnesModelConfig.ratio": (
        "Aspect ratio for tier-based sizes in 2.1 / 2.5; omitted for 2.0, which uses pixel dimensions.",
        "2.1 / 2.5 の段階サイズ用の縦横比です。ピクセル寸法を使う 2.0 には送信しません。",
        "2.1 / 2.5의 단계별 크기에 사용하는 비율입니다. 픽셀 크기를 사용하는 2.0에는 전송하지 않습니다.",
    ),
    "AgnesModelConfig.response_format": (
        "Automatically uses the nested parameters required by Agnes.",
        "Agnes が要求するネストされたパラメーターを自動的に使用します。",
        "Agnes에서 요구하는 중첩 매개변수 형식을 자동으로 사용합니다.",
    ),
    "AgnesModelConfig.extra_parameters": (
        "Add provider extensions only when needed; extra_body must be a JSON object.",
        "必要な拡張パラメーターのみ追加します。extra_body は JSON オブジェクトで指定します。",
        "필요할 때만 확장 매개변수를 추가하세요. extra_body는 JSON 객체여야 합니다.",
    ),
    "OpenAIModelConfig.enabled": (
        "When disabled, this instance's models are excluded from routing. Other platform instances can remain enabled independently.",
        "無効にすると、このインスタンスのモデルはルーティング対象外になります。他のプラットフォームインスタンスは個別に有効化できます。",
        "비활성화하면 이 인스턴스의 모델은 라우팅에서 제외됩니다. 다른 플랫폼 인스턴스는 개별적으로 활성화할 수 있습니다.",
    ),
    "StylePresetConfig.positive_prompt_template": (
        "{prompt} inserts the drawing description, for example watercolor, {prompt}. Without the placeholder, the description is appended.",
        "{prompt} は今回の描画内容に置換されます。例：水彩、{prompt}。省略すると描画内容を末尾に追加します。",
        "{prompt}는 이번 그림 설명으로 바뀝니다. 예: 수채화, {prompt}. 생략하면 설명을 뒤에 추가합니다.",
    ),
    "StylePresetConfig.negative_prompt_template": (
        "Describe unwanted content, for example blurry, {negative_prompt}. The placeholder inserts this request's negative prompt.",
        "避けたい内容を入力します。例：ぼやけ、{negative_prompt}。今回のネガティブプロンプトを挿入します。",
        "원치 않는 내용을 입력하세요. 예: 흐림, {negative_prompt}. 자리표시자에는 이번 제외 프롬프트를 넣습니다.",
    ),
    "PluginSectionConfig.image_cache_max_mb": (
        "Default 300 MB for originals and WebP previews in the plugin temporary directory. Old images are removed automatically; task records remain.",
        "既定は 300 MB。プラグイン一時ディレクトリの原画像と WebP プレビューが対象です。古い画像を自動削除し、タスク記録は保持します。",
        "기본 300 MB. 플러그인 임시 폴더의 원본과 WebP 미리보기에 적용하며, 오래된 이미지를 자동 삭제하고 작업 기록은 보존합니다.",
    ),
    "PluginSectionConfig.log_max_mb": (
        "Default 10 MB across the current log and all rotated backups. Old logs are removed automatically.",
        "既定は 10 MB。現在のログと全ローテーションバックアップの合計です。古いログを自動削除します。",
        "기본 10 MB. 현재 로그와 모든 순환 백업의 합계이며 오래된 로그를 자동 삭제합니다.",
    ),
    "PluginSectionConfig.upload_cache_max_mb": (
        "Default 256 MB, minimum 40 MB. Uploads and input images also expire after 24 hours or 100 files.",
        "既定は 256 MB、最小 40 MB。アップロードと入力画像は 24 時間または 100 ファイルの上限でも削除します。",
        "기본 256 MB, 최소 40 MB. 업로드와 입력 이미지는 24시간 또는 100개 파일 제한도 적용합니다.",
    ),
    "GeneralConfig.default_model": (
        "Leave empty to automatically choose an available model, or select a model from a specific platform instance.",
        "空欄では利用可能なモデルを自動選択します。特定のプラットフォームのモデルも選択できます。",
        "비워 두면 사용 가능한 모델을 자동으로 선택하며 특정 플랫폼 인스턴스의 모델을 지정할 수도 있습니다.",
    ),
    "GeneralConfig.fallback_models": (
        "Add models as needed and reorder them. Move to the next model after retries are exhausted; empty disables fallback.",
        "必要なモデルを追加して順序を変更します。再試行後に次のモデルへ進みます。空欄で無効です。",
        "필요한 모델을 추가하고 순서를 변경하세요. 재시도 소진 후 다음 모델을 시도하며 비어 있으면 사용하지 않습니다.",
    ),
    "GeneralConfig.request_retry_count": (
        "Default: 1 extra attempt; configurable from 0 to 5, only for safe failures such as an unestablished connection or explicit rate limiting. Never regenerate after review rejection, result download failure, or an uncertain remote outcome.",
        "既定は追加1回、0～5回で設定できます。接続未確立や明示的なレート制限など安全な失敗のみ再試行します。審査拒否、結果取得失敗、リモート状態不明時は再生成しません。",
        "기본 추가 재시도 1회, 0~5회로 설정합니다. 연결 전 실패나 명시적 속도 제한 등 안전한 실패만 재시도합니다. 심사 거부, 결과 다운로드 실패, 원격 처리 상태 불명 시 재생성하지 않습니다.",
    ),
    "ComfyUIModelConfig.t2i_workflow_path": (
        "Default file: MaiBot/data/plugins/maimai-drawpic-plugin/workflows/t2i.json, under the MaiBot application root. Enter data/workflows/t2i.json here to use that file. This is not the plugin source directory's data folder. Export an API-format workflow from ComfyUI. Absolute paths are also supported.",
        "既定のファイル：MaiBot 本体のルート配下の MaiBot/data/plugins/maimai-drawpic-plugin/workflows/t2i.json。この欄に data/workflows/t2i.json と入力すると、そのファイルを使用します。プラグインのソースディレクトリ内の data フォルダーではありません。ComfyUI の API 形式でエクスポートしてください。絶対パスも使用できます。",
        "기본 파일: MaiBot 프로그램 루트 아래의 MaiBot/data/plugins/maimai-drawpic-plugin/workflows/t2i.json. 여기에 data/workflows/t2i.json을 입력하면 해당 파일을 사용합니다. 플러그인 소스 디렉터리의 data 폴더가 아닙니다. ComfyUI API 형식으로 내보내세요. 절대 경로도 지원합니다.",
    ),
    "ComfyUIModelConfig.i2i_workflow_path": (
        "Default file: MaiBot/data/plugins/maimai-drawpic-plugin/workflows/i2i.json, under the MaiBot application root. Enter data/workflows/i2i.json here to use that file. This is not the plugin source directory's data folder. Use API-format JSON with a source-image node. Absolute paths are also supported.",
        "既定のファイル：MaiBot 本体のルート配下の MaiBot/data/plugins/maimai-drawpic-plugin/workflows/i2i.json。この欄に data/workflows/i2i.json と入力すると、そのファイルを使用します。プラグインのソースディレクトリ内の data フォルダーではありません。元画像を読み込むノードを含む API 形式 JSON を使用してください。絶対パスも使用できます。",
        "기본 파일: MaiBot 프로그램 루트 아래의 MaiBot/data/plugins/maimai-drawpic-plugin/workflows/i2i.json. 여기에 data/workflows/i2i.json을 입력하면 해당 파일을 사용합니다. 플러그인 소스 디렉터리의 data 폴더가 아닙니다. 원본 이미지 노드를 포함한 API 형식 JSON을 사용하세요. 절대 경로도 지원합니다.",
    ),
    "GoogleModelConfig.image_size": (
        "1K / 2K / 4K; Gemini 3.1 Flash also supports 512. Use uppercase K; leave blank for the model default.",
        "1K / 2K / 4K。Gemini 3.1 Flash は 512 にも対応します。大文字 K を使用し、空欄はモデルの既定値を使用します。",
        "1K / 2K / 4K. Gemini 3.1 Flash는 512도 지원합니다. 대문자 K를 사용하며 비워 두면 모델 기본값을 사용합니다.",
    ),
    "SiliconFlowModelConfig.cfg": (
        "Qwen Image only; 0 omits the parameter. A common value is 4. Kolors uses guidance_scale instead.",
        "Qwen Image のみ使用します。0 は送信しません。一般的な値は 4 です。Kolors は guidance_scale を使用します。",
        "Qwen Image 전용입니다. 0이면 전송하지 않습니다. 일반적인 값은 4입니다. Kolors는 guidance_scale을 사용합니다.",
    ),
    "AliyunModelConfig.models": (
        "Required. Defaults include Qwen 3.0/2.0, Z-Image, Kling v3 and current Vidu image models. "
        "Add older models or dated snapshots manually when needed.",
        "必須。既定は Qwen 3.0/2.0、Z-Image、Kling v3 と現行の Vidu 画像モデルです。"
        "旧モデルや日付付きスナップショットは必要に応じて手動で追加できます。",
        "필수. 기본 목록에는 Qwen 3.0/2.0, Z-Image, Kling v3와 현재 Vidu 이미지 모델만 포함됩니다. "
        "이전 모델과 날짜별 스냅샷은 필요할 때 직접 추가할 수 있습니다.",
    ),
    "ZhipuModelConfig.quality": (
        "Leave blank for the model default. GLM-Image supports hd; CogView supports hd or standard.",
        "空欄はモデルの既定値を使用します。GLM-Image は hd、CogView は hd または standard に対応します。",
        "비워 두면 모델 기본값을 사용합니다. GLM-Image는 hd, CogView는 hd 또는 standard를 지원합니다.",
    ),
    "VolcengineModelConfig.output_format": (
        "Enter png or jpeg, or leave blank for the model default. Supported by Seedream 5.0 models only.",
        "png または jpeg を入力します。空欄はモデルの既定値を使用します。Seedream 5.0 系列のみ対応します。",
        "png 또는 jpeg를 입력합니다. 비워 두면 모델 기본값을 사용합니다. Seedream 5.0 계열만 지원합니다.",
    ),
    "VolcengineModelConfig.optimize_prompt_mode": (
        "Enter standard or fast; leave blank to omit. fast is supported by Seedream 5.0 pro and 4.0 only.",
        "standard または fast を入力します。空欄は送信しません。fast は Seedream 5.0 pro と 4.0 のみ対応します。",
        "standard 또는 fast를 입력합니다. 비워 두면 전송하지 않습니다. fast는 Seedream 5.0 pro와 4.0만 지원합니다.",
    ),
    "VolcengineModelConfig.background": (
        "Enter opaque or transparent; leave blank to omit. Seedream 5.0 pro/flash edits only. "
        "transparent requires one transparent source image and non-JPEG output.",
        "opaque または transparent を入力します。空欄は送信しません。Seedream 5.0 pro/flash の画像変換のみ対応します。"
        "transparent は透過した元画像 1 枚が必要で、JPEG 出力は使用できません。",
        "opaque 또는 transparent를 입력합니다. 비워 두면 전송하지 않습니다. Seedream 5.0 pro/flash 이미지 변환만 지원합니다. "
        "transparent는 투명 원본 이미지 한 장이 필요하며 JPEG 출력은 사용할 수 없습니다.",
    ),
}



_FIELD_LABEL_OVERRIDES.update({
    "StylePresetConfig.name": ("Preset name", "プリセット名", "프리셋 이름"),
    "StylePresetConfig.description": ("Preset description", "プリセットの説明", "프리셋 설명"),
    "StyleConfig.default_style": ("Default text-to-image preset", "文生図の既定プリセット", "기본 텍스트 이미지 프리셋"),
    "StyleConfig.presets": ("Drawing presets", "描画プリセット", "그리기 프리셋"),
})

_FIELD_HINT_OVERRIDES.update({
    "StyleConfig.default_style": ("Default for text-to-image. Image editing requires its preset switch and per-preset compatibility. Select none to skip.", "文生図の既定項目です。画像編集には総スイッチと各項目の互換設定が必要です。未使用を選択すると適用しません。", "텍스트 이미지의 기본값입니다. 이미지 편집에는 전체 스위치와 항목별 호환 설정이 필요합니다. 사용 안 함으로 건너뜁니다."),
    "StyleConfig.presets": ("Both types share text templates. Image-edit presets may bind images and uses; text-to-image presets contain text only. Platform modes and session models stay unchanged.", "両種類で文字テンプレートを共有します。画像編集には画像と用途を紐付けられ、文生図は文字のみです。プラットフォームモードや会話モデルは変えません。", "두 유형은 텍스트 템플릿을 공유합니다. 이미지 편집에는 이미지와 용도를 연결할 수 있으며 텍스트 이미지에는 텍스트만 저장합니다. 플랫폼 모드와 대화 모델은 바꾸지 않습니다."),
})

_SECTION_TEXTS.update({
    "StyleConfig": (("Drawing presets", "描画プリセット", "그리기 프리셋"), ("Text-to-image and optional image-edit presets.", "文生図と任意の画像編集プリセット。", "텍스트 이미지 및 선택적 이미지 편집 프리셋.")),
    "ReferenceConfig": (("References and materials", "参照と素材", "참조 및 소재"), ("Self references and permitted sources.", "自身の参照画像と許可された素材元。", "자신의 참조 이미지와 허용된 소재 출처.")),
    "ReferenceBindingConfig": (("Reference image use", "参照画像の用途", "참조 이미지 용도"), ("Image and subject binding.", "画像と被写体の対応。", "이미지와 대상 연결.")),
})
_FIELD_LABELS.update({
    "web_search_provider": ("Search service", "検索サービス", "검색 서비스"),
    "deepseek_api_key": ("DeepSeek API Key", "DeepSeek APIキー", "DeepSeek API 키"),
    "material_model": ("Recognition model", "識別モデル", "인식 모델"),
    "self_keywords": ("Trigger keywords", "トリガーキーワード", "트리거 키워드"),
    "references": ("References and materials", "参照と素材", "참조 및 소재"),
    "self_reference_enabled": ("Enable self references", "自身の参照を有効化", "자신의 참조 활성화"),
    "self_names": ("Bot names and aliases", "ボットの名前と別名", "봇 이름 및 별칭"),
    "self_reference_ids": ("Self reference images", "自身の参照画像", "자신의 참조 이미지"),
    "multi_reference_confirmed": ("Multiple references confirmed", "複数参照を確認済み", "다중 참조 확인됨"),
    "allow_chat_material_search": ("Allow chat materials", "チャット内の素材を許可", "대화 소재 허용"),
    "chat_material_search_limit": ("Chat search limit (messages)", "チャット検索の上限（件）", "대화 검색 상한(메시지 수)"),
    "allow_web_material_search": ("Allow web materials", "ウェブ素材を許可", "웹 소재 허용"),
    "preset_type": ("Preset type", "プリセットの種類", "프리셋 유형"),
    "tags": ("Tags", "タグ", "태그"),
    "apply_to_image_edit": ("Also apply to image editing", "画像編集にも適用", "이미지 편집에도 적용"),
    "reference_bindings": ("Preset reference images", "プリセットの参照画像", "프리셋 참조 이미지"),
    "asset_id": ("Reference image", "参照画像", "참조 이미지"),
    "role": ("Image use", "画像の用途", "이미지 용도"),
    "subject_id": ("Subject", "被写体", "대상"),
    "note": ("Use description", "用途の説明", "용도 설명"),
    "image_edit_presets_enabled": ("Enable image editing presets", "画像編集プリセットを有効化", "이미지 편집 프리셋 활성화"),
    "default_image_edit_preset": ("Default image editing preset", "画像編集の既定プリセット", "기본 이미지 편집 프리셋"),
})

_FIELD_HINT_OVERRIDES.update({
    f"{name}.enabled": (
        "When disabled, this platform's models cannot be selected.",
        "無効にすると、このプラットフォームのモデルは選択できません。",
        "끄면 이 플랫폼의 모델을 선택할 수 없습니다.",
    )
    for name in ("AliyunModelConfig", "GoogleModelConfig", "MiniMaxModelConfig", "NovelAIModelConfig", "SiliconFlowModelConfig", "OpenAIModelConfig", "VolcengineModelConfig", "ZhipuModelConfig")
})
_FIELD_HINT_OVERRIDES.update({
    "ComfyUIModelConfig.poll_interval_seconds": ("Default: 1 second. A longer interval reduces polling frequency.", "既定は1秒です。間隔を長くすると確認頻度が下がります。", "기본값은 1초입니다. 간격을 늘리면 조회 빈도가 줄어듭니다."),
    "NovelAIModelConfig.max_images": ("Images per request; 1–4 recommended.", "1回の生成枚数です。1～4枚を推奨します。", "한 번에 생성할 이미지 수입니다. 1~4장을 권장합니다."),
})

def _localized_field_entries(
    class_name: str,
    field_name: str,
    json_schema_extra: Dict[str, object],
) -> Dict[str, Dict[str, str]]:
    """生成一个字段的三语 WebUI 元数据。"""

    field_path = f"{class_name}.{field_name}"
    labels = _FIELD_LABEL_OVERRIDES.get(field_path, _FIELD_LABELS.get(field_name))
    if labels is None:
        raise ValueError(f"配置字段缺少 i18n 标签：{field_path}")

    placeholder_values = _PLACEHOLDER_TEXTS.get(field_path)
    default_placeholder = str(json_schema_extra.get("placeholder") or "").strip()
    translations: Dict[str, Dict[str, str]] = {}
    for index, locale in enumerate(_LOCALES):
        label = labels[index]
        localized: Dict[str, str] = {"label": label}
        if str(json_schema_extra.get("hint") or "").strip():
            hints = _FIELD_HINT_OVERRIDES.get(field_path, _FIELD_HINT_OVERRIDES.get(field_name))
            if hints is not None:
                localized["hint"] = hints[index]
            elif field_name == "default_openai_compatibility_mode":
                localized["hint"] = _OPENAI_MODE_HINTS[index]
            elif locale == "en_US":
                localized["hint"] = f"Configure {label}."
            elif locale == "ja_JP":
                localized["hint"] = f"{label}を設定します。"
            else:
                localized["hint"] = f"{label}을(를) 설정합니다."
        if default_placeholder:
            localized["placeholder"] = (
                placeholder_values[index] if placeholder_values is not None else default_placeholder
            )
        translations[locale] = localized
    return translations


def apply_config_i18n(config_classes: Iterable[Type[PluginConfigBase]]) -> None:
    """把集中维护的多语言元数据注入所有插件配置模型。"""

    for config_class in config_classes:
        class_name = config_class.__name__
        section_texts = _SECTION_TEXTS.get(class_name)
        if section_texts is None:
            raise ValueError(f"配置节缺少 i18n 文案：{class_name}")

        titles, descriptions = section_texts
        config_class.__ui_i18n__ = {
            locale: {
                "title": titles[index],
                "description": descriptions[index],
            }
            for index, locale in enumerate(_LOCALES)
        }

        for field_name, field_info in config_class.model_fields.items():
            json_schema_extra = (
                dict(field_info.json_schema_extra) if isinstance(field_info.json_schema_extra, dict) else {}
            )
            json_schema_extra["i18n"] = _localized_field_entries(
                class_name,
                field_name,
                json_schema_extra,
            )
            field_info.json_schema_extra = json_schema_extra
