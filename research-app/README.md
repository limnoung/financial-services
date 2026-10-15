# DartLab Research · 통합 리서치

**DartLab의 기본 메인화면을 그대로 사용하면서 financial-services 검토 절차와 Gems 매력도 평가를 함께 여는 로컬 프로그램**입니다. DartLab을 별도 창이나 별도 서버로 실행할 필요가 없습니다.

| 구성 | 맡은 역할 | 현재 연결 범위 |
|---|---|---|
| DartLab 0.12.0 | 메인화면·종목 검색·차트·공시·재무·AI 인터페이스 | 공식 배포본 화면과 원래 API를 그대로 사용 |
| financial-services | 경쟁사 비교·가치평가 가정·검산·실적 시나리오 | 입력 점검, 검토 질문, 원문 절차, AI 검토 요청, 보고서 반영 |
| Gems Research | 21개 항목 매력도 평가와 근거 관리 | 정량 계산·정성 평가·미평가 처리·기록·Markdown/JSON 내보내기 |

financial-services는 LLM이 따르는 분석 절차 모음입니다. 설치만으로 동작하는 독립적인 예측 모델이나 DCF 계산 서버가 아닙니다. 통합 앱의 재무 검토는 현재 입력의 날짜·기간·자료 부족을 점검하고 추가 검토 절차를 제공합니다. Excel 수식 감사·DCF 생성·실시간 컨센서스 조회는 구현하지 않았습니다.

## 가장 간단한 실행

Python **3.12 이상**을 설치하고 ZIP을 압축 해제합니다. 전체 GitHub 저장소 ZIP을 받았다면 `research-app` 폴더로 이동하세요.

- Windows: `start.cmd`를 실행합니다.
- macOS / Linux: 터미널에서 `sh start.sh`를 실행합니다.
- 공통: `python -X utf8 start.py`로 실행할 수도 있습니다.

첫 실행에 전용 가상환경과 DartLab 의존성을 설치합니다. 이후 같은 환경을 재사용하며 브라우저에서 **http://127.0.0.1:8766** 을 엽니다. 첫 화면은 해당 DartLab 배포본의 기본 메인화면입니다. 종료는 실행한 터미널에서 `Ctrl+C`입니다.

브라우저 자동 실행을 끄려면 `python -X utf8 start.py --no-browser`, 포트를 바꾸려면 `--port 9000`을 추가합니다. 설치 오류는 실행한 터미널에 표시됩니다. Python·Node·1TB 금융 데이터를 ZIP에 넣은 실행 파일 형태가 아니라 소스 배포입니다.

## 한 화면에서 사용하는 순서

1. DartLab 메인화면에서 종목을 검색하고 재무·공시·차트를 확인합니다.
2. 우측 하단 **Gems · 재무 검토**를 누릅니다. 기본 화면 위에 분석 패널이 열립니다.
3. DartLab에 선택된 종목이 있으면 첫 열기에 넘겨 받아 재무 자료를 불러오고 평가 가능한 항목을 계산합니다. 선택된 종목이 없으면 패널에 종목코드를 입력하고 불러옵니다.
4. **재무 검토**에서 기준일·CAGR 기간·업종 기준·경쟁사·목표가 근거·리스크의 입력 상태를 확인합니다. 네 가지 financial-services 원문 절차도 열 수 있습니다.
5. **매력도 평가**에서 나머지 정량 수치와 정성 점수, 근거·출처·기준일을 보완합니다. 모든 자료를 자동으로 찾아 점수를 확정하는 기능은 아닙니다.
6. **보고서**에서 결과를 확인하고 Markdown·JSON으로 내보내거나 분석 기록을 저장합니다.
7. **AI 검토 요청 복사**를 눌러 DartLab AI 채팅 또는 Gemini Gems에 붙여 넣어 검토합니다. AI가 제안한 근거를 앱에 반영해 점수를 다시 계산합니다.

패널을 닫아도 DartLab 기본 화면과 입력은 유지됩니다. DartLab에서 다른 종목을 선택하면 패널 상단의 조회 종목이 갱신됩니다. 평가 입력을 바꾸려면 **현재 종목 가져오기**를 누릅니다. 기존 입력이 있을 때는 교체 여부를 확인합니다. 최신 조회가 실패하면 오류를 표시하며 이전 기업의 수치를 새 기업의 값으로 바꾸지 않습니다.

DartLab AI 기능은 DartLab에서 지원하는 에이전트 실행환경의 설치·로그인 상태에 따라 사용할 수 있습니다. **기본 데이터 조회와 규칙 채점에는 LLM 키가 필요하지 않습니다.** 이 앱이 AI 계정을 자동 연결하거나 AI 요청을 자동 전송하지는 않습니다.

## 설치 환경이 이미 있는 경우

이 폴더에서 실행합니다.

    python -m venv .venv

Windows PowerShell:

    .\.venv\Scripts\Activate.ps1
    python -m pip install -e ".[data]"
    gems-research serve

macOS / Linux:

    source .venv/bin/activate
    python -m pip install -e ".[data]"
    gems-research serve

`serve`는 DartLab 메인화면과 Gems 패널을 같은 서버에서 실행합니다. DartLab 설치 파일이나 UI 번들을 수정하지 않습니다. 내부 API와 UI의 호환 범위를 `dartlab==0.12.0`으로 고정했습니다.

기존 독립 Gems 화면만 필요하다면 `gems-research serve --standalone`을 사용합니다. 이 모드는 DartLab 없이 `python -m pip install -e .`로도 사용할 수 있습니다. 통합 화면은 `[data]` 설치가 필요합니다.

DartLab만 별도로 실행해 보고 싶다면 같은 가상환경에서 `dartlab ai`를 실행하면 됩니다. 기본 주소는 http://127.0.0.1:8400 입니다. 이 명령으로 연 원래 DartLab 화면에는 이 앱의 Gems 패널이 추가되지 않습니다. 통합 실행에는 `start.cmd` / `start.sh` / `gems-research serve`를 사용하세요.

## 데이터와 채점 범위

DartLab 메인화면은 시장 요약 파일과 필요한 상세 파일을 조회합니다. Gems의 한국 재무 조회는 회사별 파일, 미국 재무는 공개 표준화 파일을 사용합니다. 전체 1TB 데이터를 미리 받지 않습니다. 첫 화면과 첫 종목 조회에는 인터넷이 필요할 수 있습니다.

자동 입력은 연결 우선 매출·순이익 3년 CAGR, 부채비율입니다. 충분한 가격 기간과 분할 감지 입력이 있으면 52주 최고 종가와 이동평균 항목도 평가합니다. 뉴스·컨센서스·시장 점유율·정성 판단은 근거를 확인해 보완해야 합니다.

21개 항목이 모두 평가됐을 때 최종 점수를 표시합니다. 자료가 빠지면 잠정 점수·자료 충족률·가능한 범위를 표시합니다. 금융업·리츠·적자 성장기업에는 일반 PER·PEG·부채비율 기준 적용을 보류합니다. 자세한 정의는 [평가 기준서](GEMS_SCORING_GUIDE.md)를 참고하세요.

가격은 공개 파일의 종가이며 실시간 시세가 아닙니다. 조회 성공이 최신 공시·시세 반영을 보증하지는 않습니다. 목표주가는 사용자가 별도 가치평가 근거와 함께 입력하며 매력도 점수로 역산하지 않습니다.

## 로컬 데이터 위치

- `GEMS_DARTLAB_DATA_DIR`: DartLab 서버와 Gems 조회가 공유할 공개 파일 캐시 경로.
- `GEMS_STATE_DIR`: 분석 기록 SQLite를 보관할 폴더.
- 미설정 시 사용자 캐시·데이터 폴더 아래 `gems-research`를 사용합니다. DartLab 자체의 AI 상태는 DartLab의 `DARTLAB_HOME` 설정을 따릅니다.

PowerShell 예시:

    $env:GEMS_DARTLAB_DATA_DIR = "D:\ResearchData\dartlab"
    $env:GEMS_STATE_DIR = "D:\ResearchData\gems"
    .\start.cmd

패널의 **로컬 캐시만 사용**은 Gems 회사 자료 조회에 적용됩니다. 캐시가 없으면 다운로드하지 않고 오류를 표시합니다. DartLab 기본 화면 전체를 오프라인으로 바꾸는 설정은 아닙니다. DartLab 메인화면의 브라우저 캐시와 서버 공개 파일 캐시는 별개입니다.

JSON 내보내기는 입력 근거를 저장합니다. 분석 기록은 입력·점수·기준 버전을 로컬 SQLite에 추가하며 이전 기록을 덮어쓰지 않습니다. 프로그램 코드·데이터 캐시·개인 분석 기록은 분리해 보관합니다.

## 명령행과 검증

    gems-research analyze --demo
    gems-research analyze 005930 --offline
    gems-research analyze --input evidence.json --format json
    python -m pip install -e ".[data,test]"
    python -m pytest -q

테스트는 채점 경계·자료 부족·기준일·업종 예외·CAGR·API·기록 보존과 통합 화면의 경로·원본 정적 파일을 검증합니다. 투자 성과나 예측 정확도 검증은 포함하지 않습니다.

0.2.0 검증 환경은 Linux·Python 3.12·Chromium입니다. 55개 테스트와 브라우저에서 패널·입력 보존·기록·내보내기·모바일 표시를 확인했습니다. 네트워크 제한 때문에 브라우저 검증에는 고정 응답과 로컬 Samsung 재무 캐시를 사용했습니다. 실시간 외부 데이터 갱신, AI 계정 연결·응답, Windows에서의 `start.cmd` 실행은 이 환경에서 검증하지 않았습니다.

DartLab과 이 저장소 코드는 Apache 2.0 라이선스입니다. financial-services 원문 절차와 출처 고정 링크는 패키지의 `reference`에 포함합니다. DartLab 공개 데이터셋은 제공자가 CC BY 4.0으로 안내합니다. 개별 데이터 재배포 시 해당 출처와 조건을 확인하고 표시하세요. Built with dartlab (https://github.com/eddmpython/dartlab).
