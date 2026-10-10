# ai-model-radar 🛰️

새로 공개되는 AI 모델을 매일 자동으로 감지해 **GitHub Issue**와 **Telegram**으로 알려주는 GitHub Action.

## 감지 소스

| 소스 | 내용 | 필요 설정 |
|---|---|---|
| 🤗 Hugging Face | `config.yaml`의 조직(meta-llama, Qwen, deepseek-ai …) 신규 모델 업로드 + 전체 trending top-N 신규 진입 | 없음 |
| 🔌 Provider API | OpenAI / Anthropic / Gemini / Mistral / xAI / DeepSeek `/models` 목록에 새로 추가된 모델 | 각 API 키 Secret (없으면 건너뜀) |
| 📦 GitHub 릴리스 | vLLM, SGLang, TensorRT-LLM, transformers, llama.cpp 등 | 없음 (`GITHUB_TOKEN` 자동) |
| 📄 논문 | HF Daily Papers(업보트 기준) + arXiv 검색 | 없음 |
| 📰 뉴스/매거진 | OpenAI, DeepMind, HF Blog, The Decoder, TechCrunch, The Verge, VentureBeat, MIT TR, AI타임스 등 RSS | 없음 |

GGUF/AWQ/GPTQ 같은 양자화 파생 레포는 기본 제외. 뉴스는 "출시 키워드 + 모델 키워드"가 모두 들어간 기사만 알림 (공식 랩 블로그는 `filter: false`로 전부 알림).

## 한국어 요약 (Claude 후처리)

수집된 항목은 Claude(`claude-opus-5-5`)가 한 번 더 걸러 **실제 신규 모델 출시만** 남기고, 같은 모델에 대한 여러 기사·HF 레포를 하나로 묶어 한국어 요약본을 만듭니다. 서빙 프레임워크 주요 릴리스 등은 "그 밖에 볼 만한 소식"으로 최대 5개까지 붙습니다.

- `ANTHROPIC_API_KEY` Secret이 필요합니다. 없으면 기존처럼 필터링된 원본 목록을 보냅니다.
- 걸러낸 결과 볼 만한 게 없는 날은 알림을 보내지 않습니다.
- 설정: `config.yaml`의 `digest:` (모델, effort, 최대 항목 수)

## 관심 주제 따라가기

신규 모델 외에 받아보고 싶은 주제는 `config.yaml`의 `topics:`에 추가합니다. 주제마다 요약에 `🔎 주제 이름` 섹션이 생깁니다(주제당 최대 3건, `digest.max_per_topic`).

```yaml
topics:
  - name: 온디바이스 AI
    description: on-device / edge LLM inference, NPU, mobile deployment
    keywords: [on-device, edge AI, NPU, mobile LLM, 온디바이스]
    arxiv: true        # arXiv 신규 논문도 키워드로 검색
```

- `keywords`는 뉴스 기사와 HF Daily Papers를 넓게 걸러 오는 1차 필터입니다(단어 시작 기준, 대소문자 무시).
- Claude가 `description`을 기준으로 실제 관련 있는 것만 남기므로 키워드는 넉넉히 넣어도 됩니다.
- 새 주제를 추가한 첫날은 과거 논문이 쏟아지지 않도록 조용히 기록만 합니다.

## 동작 방식

1. 매일 05:17 KST에 `.github/workflows/radar.yml`이 시작해 수집·요약을 마치고, **06:00 KST에 알림 발송** (GitHub 예약 실행 지연 대비. 06:41 KST 백업 실행은 첫 실행이 없었을 때만 동작)
2. 각 소스에서 항목 수집 → `state/seen.json`과 비교해 새 항목만 추림
3. 새 항목을 하나의 Issue(라벨 `new-models`)로 생성하고 Telegram으로 전송
4. `state/seen.json` 갱신 후 커밋

**첫 실행은 조용히 기록만 합니다.** 처음 보는 조직/피드/프로바이더(버킷)의 항목은 알림 없이 기록되므로, 나중에 `config.yaml`에 조직이나 피드를 추가해도 과거 항목이 쏟아지지 않습니다.
알림이 모두 실패하면 상태를 갱신하지 않아 다음 실행에서 다시 시도합니다.

## 설정

### Secrets (Settings → Secrets and variables → Actions)

| 이름 | 용도 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather)에서 `/newbot`으로 발급 |
| `TELEGRAM_CHAT_ID` | 봇에게 메시지를 보낸 뒤 `https://api.telegram.org/bot<TOKEN>/getUpdates`의 `chat.id` (채널이면 `@채널명` 또는 `-100…`) |
| `ANTHROPIC_API_KEY` | 한국어 요약 후처리 (권장). Anthropic 모델 목록 감지에도 사용 |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY`, `DEEPSEEK_API_KEY` | 선택. 설정한 프로바이더만 감지 |

### 날짜 지정 다시보기

Actions → Run workflow에서 `lookback_date`(예: `2026-10-05` 또는 `2026-10-01..2026-10-05`)를 넣으면 상태와 무관하게 그 날짜(UTC)에 나온 항목을 요약해 Job Summary에 보여줍니다. `lookback_telegram`을 체크하면 텔레그램으로도 보냅니다.

### Actions 권한

Settings → Actions → General → Workflow permissions가 **Read and write**여야 상태 커밋과 Issue 생성이 됩니다 (워크플로에 `permissions:`도 명시되어 있음).

### 감시 대상 변경

`config.yaml`에서 조직, 레포, RSS 피드, 키워드, trending 개수 등을 수정하세요.

## 로컬 실행

```bash
pip install -r requirements.txt
python -m radar --dry-run                 # 알림/상태 갱신 없이 결과만 출력
python -m radar --dry-run --only huggingface news
python -m radar --no-notify               # 상태만 갱신
pip install pytest && pytest -q
```
