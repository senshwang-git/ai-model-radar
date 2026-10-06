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

## 동작 방식

1. 매일 08:47 KST(23:47 UTC)에 `.github/workflows/radar.yml` 실행 (수동 실행 가능)
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
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY`, `DEEPSEEK_API_KEY` | 선택. 설정한 프로바이더만 감지 |

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
