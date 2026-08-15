# EosWos

메자닌 후보군 선별 및 등급평가 서비스의 공개 웹사이트와 AI 패널 저장소입니다.

## 창건이 확장 개발 시작점

대부분의 AI 패널 기능은 `ai_single_evaluation.py`에서 개발합니다.

| 개발 목적 | 수정할 파일 |
|---|---|
| AI 패널 화면, 버튼, 입력폼, 결과 표시 | `ai_single_evaluation.py` |
| `Temp` 버튼에 새로운 화면이나 기능 연결 | `ai_single_evaluation.py` |
| 자연어에서 평가조건을 추출하는 규칙 변경 | `mezz_chat_parser.py` |
| 평가 API 주소, 요청 또는 응답 처리 변경 | `mezz_api_client.py` |
| eoswos.com의 풍선 버튼과 패널 열기/닫기 변경 | `ai_widget.js` |
| 풍선과 패널의 크기, 색상, 위치 변경 | `ai_widget.css` |
| eoswos.com의 iframe, SEO, 분석 코드 변경 | `index.html` |

`Temp`는 현재 `자연어 질의`와 같은 대화창을 열지만 `panel_mode == "Temp"`로 별도 상태가 유지됩니다. 독립 기능으로 확장할 때는 `ai_single_evaluation.py`에서 `Temp`를 검색한 뒤 다음 구조로 분리합니다.

```python
if input_mode == "Temp":
    _render_temp_feature(client, today_seoul)
```

독립 화면을 만들면 기존 채팅 조건인 아래 코드에서는 `Temp`를 제외해야 중복 표시되지 않습니다.

```python
if input_mode in {"자연어 질의", "Temp"}:
    ...
```

## 파일 설명

| 파일 | 역할 |
|---|---|
| `ai_single_evaluation.py` | Streamlit AI 패널 본체입니다. 세 모드, 평가 입력폼, 세션 상태, API 호출, 결과 화면을 담당합니다. |
| `mezz_chat_parser.py` | 자연어 질의를 평가 필드로 변환하고 필수값과 범위를 검증합니다. 모델 계산은 수행하지 않습니다. |
| `mezz_api_client.py` | EC2의 단건평가 API와 HTTPS로 통신하고 인증 헤더, 시간 측정, 오류 정제를 담당합니다. |
| `code.xlsx` | 발행사와 기초자산 종목코드 검색형 풀다운에 사용하는 회사명 및 종목코드 목록입니다. |
| `requirements.txt` | AI 패널의 Streamlit Cloud 배포에 필요한 추가 Python 패키지 목록입니다. |
| `ai_widget.js` | eoswos.com 우측 하단 풍선, AI 패널 iframe, 닫기 버튼과 Escape 동작을 만듭니다. |
| `ai_widget.css` | 풍선과 AI 패널의 크기, 위치, 반응형 화면, 애니메이션을 정의합니다. |
| `index.html` | eoswos.com 정적 진입점입니다. 본 서비스와 AI 패널을 iframe으로 연결하고 SEO 및 방문 통계를 설정합니다. |
| `CNAME` | GitHub Pages 사용자 도메인을 `eoswos.com`으로 연결합니다. |
| `robots.txt` | 검색엔진 크롤링 허용 범위와 사이트맵 주소를 정의합니다. |
| `sitemap.xml` | 검색엔진에 공개할 대표 URL을 제공합니다. |
| `.gitignore` | 캐시, 가상환경, `.env`, `secrets.toml`이 GitHub에 올라가지 않도록 차단합니다. |
| `README.md` | 저장소 구조와 확장 개발 방법을 설명하는 현재 문서입니다. |

## 실행과 배포 구조

1. `eoswos.com`은 `index.html`, `ai_widget.js`, `ai_widget.css`를 사용합니다.
2. 풍선을 클릭하면 `ai-contest-win.streamlit.app`의 `ai_single_evaluation.py`가 iframe으로 열립니다.
3. AI 패널은 `mezz_api_client.py`를 통해 EC2 단건평가 API를 호출합니다.
4. 실제 DEA/ML 계산은 공개 저장소가 아니라 Private `Mezz_DEA` 모델 API에서 수행됩니다.
5. `main` 브랜치에 push하면 연결된 GitHub Pages와 Streamlit Cloud가 변경사항을 다시 배포합니다.

## 변경 금지 및 보안

- 모델 공식, 등급 경계, operating reference를 이 저장소에 복제하거나 재구현하지 않습니다.
- `MEZZ_API_BASE_URL`과 `MEZZ_API_TOKEN`은 Streamlit Cloud Secrets에만 저장합니다.
- 토큰, API 키, 비밀번호, `.streamlit/secrets.toml`을 GitHub에 커밋하지 않습니다.
- API 계약을 변경할 때는 Private `Mezz_DEA` API의 Request/Response 규격과 함께 검토합니다.
- UI 확장만 필요한 경우 `mezz_api_client.py`와 평가 payload는 변경하지 않습니다.

## 기본 확인 명령

```powershell
python -m py_compile ai_single_evaluation.py mezz_chat_parser.py mezz_api_client.py
streamlit run ai_single_evaluation.py
```
