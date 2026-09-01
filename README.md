# EosWos

메자닌 후보군 선별 및 등급평가 서비스의 공개 웹사이트와 AI 패널 저장소입니다.

## 창건이 확장 개발 시작점

대부분의 AI 패널 기능은 `ai_single_evaluation.py`에서 개발합니다.

| 개발 목적 | 수정할 파일 |
|---|---|
| AI 패널 화면, 버튼, 입력폼, 결과 표시 | `ai_single_evaluation.py` |
| 자연어 질문의 TYPE A~D 의도 분류 | `chat_intent_router.py` |
| Chatbase REST 요청, 인증, 오류 정제 | `chatbase_client.py` |
| 확정 평가결과의 읽기 전용 설명 컨텍스트 | `chat_evaluation_context.py` |
| 정형 평가폼의 검증과 API payload 계약 | `mezz_evaluation_contract.py` |
| 평가 API 주소, 요청 또는 응답 처리 변경 | `mezz_api_client.py` |
| eoswos.com의 풍선 버튼과 패널 열기/닫기 변경 | `ai_widget.js` |
| Agent Home 질문 전달 상태와 메시지 계약 | `agent_home_first_prompt.js` |
| E-AGENT Agent Home 질문 payload 검증과 Streamlit component | `agent_home_prompt_bridge.py`, `initial_prompt_bridge/index.html` |
| 풍선과 패널의 크기, 색상, 위치 변경 | `ai_widget.css` |
| eoswos.com의 iframe, SEO, 분석 코드 변경 | `index.html` |

## 파일 설명

| 파일 | 역할 |
|---|---|
| `ai_single_evaluation.py` | Streamlit AI 패널 본체입니다. 메자닌 평가·자연어 질의 모드, 평가 입력폼, 세션 상태, API 호출, 결과 화면을 담당합니다. |
| `chat_intent_router.py` | 자연어 입력을 일반질문, 평가요청, 결과설명, 차단요청으로 분류합니다. 평가값을 추출하거나 자동채움하지 않습니다. |
| `chatbase_client.py` | 커스텀 AI 패널에서 Chatbase REST API를 서버 측으로 호출하고 외부 오류를 정제합니다. |
| `chat_evaluation_context.py` | 확정 평가결과 중 허용 필드만 복사해 Chatbase 설명용 읽기 전용 컨텍스트를 만듭니다. |
| `mezz_evaluation_contract.py` | 사용자가 정형 평가폼에 직접 입력한 값을 검증하고 Mezz API payload를 구성합니다. |
| `mezz_api_client.py` | EC2의 단건평가 API와 HTTPS로 통신하고 인증 헤더, 시간 측정, 오류 정제를 담당합니다. |
| `code.xlsx` | 발행사와 기초자산 종목코드 검색형 풀다운에 사용하는 회사명 및 종목코드 목록입니다. |
| `requirements.txt` | AI 패널의 Streamlit Cloud 배포에 필요한 추가 Python 패키지 목록입니다. |
| `ai_widget.js` | eoswos.com 우측 하단 풍선, AI 패널 iframe, 닫기 버튼, Escape 및 세 구역 크기 조절 동작을 만듭니다. |
| `agent_home_first_prompt.js` | Agent Home 질문의 READY/INITIAL_PROMPT/ACK 전달 계약과 1회 재시도를 관리합니다. |
| `agent_home_prompt_bridge.py` | exact parent origin과 Agent Home 질문 payload를 검증하고 browser-side Streamlit component를 렌더링합니다. |
| `initial_prompt_bridge/index.html` | Agent Home과 E-AGENT iframe 사이 strict-origin postMessage handshake를 수행합니다. |
| `ai_widget.css` | 풍선과 AI 패널의 크기, 위치, 반응형 화면, 애니메이션 및 크기 조절 영역을 정의합니다. |
| `index.html` | eoswos.com 정적 진입점입니다. 본 서비스와 AI 패널을 iframe으로 연결하고 SEO 및 방문 통계를 설정합니다. |
| `CNAME` | GitHub Pages 사용자 도메인을 `eoswos.com`으로 연결합니다. |
| `robots.txt` | 검색엔진 크롤링 허용 범위와 사이트맵 주소를 정의합니다. |
| `sitemap.xml` | 검색엔진에 공개할 대표 URL을 제공합니다. |
| `.gitignore` | 캐시, 가상환경, `.env`, `secrets.toml`이 GitHub에 올라가지 않도록 차단합니다. |
| `README.md` | 저장소 구조와 확장 개발 방법을 설명하는 현재 문서입니다. |

## 실행과 배포 구조

1. `eoswos.com`은 `index.html`, `ai_widget.js`, `ai_widget.css`를 사용합니다.
2. 풍선을 클릭하면 `ai-contest-win.streamlit.app`의 `ai_single_evaluation.py`가 iframe으로 열립니다.
3. 직접 평가는 `mezz_api_client.py`를 통해 EC2 단건평가 API를 호출합니다.
4. 실제 DEA/ML 계산은 공개 저장소가 아니라 Private `Mezz_DEA` 모델 API에서 수행됩니다.
5. 일반질문은 `chat_intent_router.py`를 거쳐 `chatbase_client.py`가 Chatbase REST API로 전달합니다.
6. 평가요청 문장은 평가폼만 열며, 문장에서 조건을 추출하거나 평가를 자동 실행하지 않습니다.
7. 평가 완료 후 결과질문에는 허용된 확정 결과의 복사본만 Chatbase에 전달합니다. Chatbase는 평가상태를 변경할 수 없습니다.
8. `main` 브랜치에 push하면 연결된 GitHub Pages와 Streamlit Cloud가 변경사항을 다시 배포합니다.
9. Agent Home 질문은 AI 패널이 닫혀 있을 때마다 새 request ID와 함께 strict-origin `postMessage`로 전달되며, 패널이 열려 있는 동안의 대화는 기존 AI 패널에서 계속됩니다.

## 자연어 라우팅

| 유형 | 처리 |
|---|---|
| TYPE A 일반·방법론 질문 | Chatbase 호출 |
| TYPE B 평가 의도 | 정형 평가폼만 열기, 값 추출·자동채움·자동평가 금지 |
| TYPE C 확정 결과 설명 | 읽기 전용 결과 컨텍스트와 함께 Chatbase 호출 |
| TYPE D 민감·범위 외 요청 | Chatbase를 호출하지 않고 로컬 고정 응답 |

직접 평가는 사용자가 정형폼을 완성하고 `평가시작` 버튼을 눌렀을 때만 Mezz API를 호출합니다.

## 변경 금지 및 보안

- 모델 공식, 등급 경계, operating reference를 이 저장소에 복제하거나 재구현하지 않습니다.
- `MEZZ_API_BASE_URL`과 `MEZZ_API_TOKEN`은 Streamlit Cloud Secrets에만 저장합니다.
- `CHATBASE_API_KEY`와 `CHATBASE_AGENT_ID`도 Streamlit Cloud Secrets에만 저장합니다.
- 토큰, API 키, 비밀번호, `.streamlit/secrets.toml`을 GitHub에 커밋하지 않습니다.
- API 계약을 변경할 때는 Private `Mezz_DEA` API의 Request/Response 규격과 함께 검토합니다.
- UI 확장만 필요한 경우 `mezz_api_client.py`와 평가 payload는 변경하지 않습니다.
- Production E-AGENT는 `https://eoswos.com`만 parent origin으로 허용합니다. Staging origin은 명시적인 staging deployment mode에서만 단일값으로 허용합니다.
- Agent Home 질문 원문과 request ID는 URL, localStorage 또는 sessionStorage에 저장하지 않습니다. request ID는 전달 및 중복 방지를 위한 런타임과 E-AGENT 세션 상태에서만 처리합니다.

## Streamlit Cloud Secrets

실제 값은 저장소가 아니라 `ai-contest-win` 앱의 Secrets 화면에 다음 이름으로 저장합니다.

```toml
MEZZ_API_BASE_URL = "https://api-staging.eoswos.com"
MEZZ_API_TOKEN = "..."
CHATBASE_API_KEY = "..."
CHATBASE_AGENT_ID = "..."
AGENT_HOME_PARENT_ORIGIN = "https://eoswos.com"
AGENT_HOME_DEPLOYMENT_ENVIRONMENT = "production"
```

Staging E-AGENT는 별도 앱에서 `AGENT_HOME_DEPLOYMENT_ENVIRONMENT = "staging"`과 해당 static staging의 exact HTTPS origin을 함께 지정합니다. Production 앱에 staging origin을 지정하면 bridge가 fail-closed 됩니다.

## 기본 확인 명령

```powershell
python -m py_compile ai_single_evaluation.py mezz_api_client.py mezz_evaluation_contract.py chat_intent_router.py chat_evaluation_context.py chatbase_client.py
python -m pytest -q
node --test tests/js/test_agent_home_first_prompt.cjs
streamlit run ai_single_evaluation.py
```
