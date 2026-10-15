# Gems Research

DartLab의 공개 재무 데이터를 읽고, 근거가 있는 정량·정성 평가를 합쳐 투자 매력도를 계산하는 로컬 프로그램입니다. 별도 예측 모델 학습, KIS 계정, 유료 데이터 API 또는 LLM 키 없이 사용할 수 있습니다. 뉴스·컨센서스·정성 평가는 출처를 확인해 보완합니다.

## 설치와 실행

Python 3.12 이상이 필요합니다. 이 폴더에서 실행하세요.

    python -m venv .venv

Windows PowerShell:

    .\.venv\Scripts\Activate.ps1
    python -m pip install -e ".[data]"
    gems-research serve

macOS 또는 Linux:

    source .venv/bin/activate
    python -m pip install -e ".[data]"
    gems-research serve

브라우저에서 http://127.0.0.1:8766 을 엽니다. 프로그램은 기본적으로 로컬 인터페이스에만 바인딩합니다.

DartLab 없이 화면·수동 채점·가상 예시만 사용하려면 extras 없이 설치합니다.

    python -m pip install -e .

## 사용 순서

1. 가상 예시로 점수 계산·근거 입력·보고서 저장 흐름을 확인합니다. 가상 예시는 실제 기업의 투자 결론이 아닙니다.
2. 종목과 시장을 선택하고 DartLab 데이터를 불러옵니다. 한국 재무는 회사별 파일, 미국 재무는 공개 표준화 파일을 사용합니다. 모든 1TB 데이터를 다운로드하지 않습니다.
3. 자동 입력된 매출·순이익 3년 CAGR, 부채비율의 근거와 날짜를 확인합니다. 가격 파일에 충분한 기간과 분할 감지 입력이 있으면 52주 최고 종가와 이동평균 항목도 평가합니다.
4. 남은 항목의 수치 또는 정성 점수, 근거, 출처명, 기준일을 입력합니다. 금융업·리츠·적자 성장기업은 일반 PER·PEG·부채비율 기준 적용을 보류합니다.
5. 매력도를 계산합니다. 21개 항목이 모두 평가됐을 때 최종 점수를 표시합니다. 자료가 빠지면 잠정 점수·자료 충족률·가능한 범위를 함께 표시합니다.
6. 투자 논리·경쟁사·핵심 리스크·목표주가 근거를 보완하고 다시 계산합니다.
7. 분석 기록을 저장하거나 Markdown·JSON으로 내보냅니다. JSON은 다시 불러와 검토할 수 있습니다.
8. 필요하면 Gems 검토 요청을 복사해 [평가 기준서](GEMS_SCORING_GUIDE.md)와 함께 Gemini에 제공합니다. 검색 결과로 근거를 수정한 뒤 프로그램에서 점수를 다시 계산합니다.

자동 채점은 최신 공시 검색이나 모든 정보의 검증을 대신하지 않습니다. 가격은 공개 파일의 종가이며 실시간 시세가 아닙니다. 기관 보유율·컨센서스·시장 점유율은 원문 출처를 직접 확인해야 합니다. 근거를 입력했다는 사실이 근거의 정확성을 보증하지는 않습니다.

## 로컬 데이터 위치

설정은 비밀정보가 아닌 경로만 받습니다.

- GEMS_DARTLAB_DATA_DIR: DartLab 공개 파일 캐시 경로. 기존 DartLab 캐시를 재사용할 때 설정합니다.
- GEMS_STATE_DIR: 분석 기록 SQLite를 보관할 폴더.
- 미설정 시 사용자 캐시·데이터 폴더 아래 gems-research를 사용합니다. 소스 저장소에는 금융 데이터를 넣지 않습니다.

PowerShell 예시:

    $env:GEMS_DARTLAB_DATA_DIR = "D:\ResearchData\dartlab"
    $env:GEMS_STATE_DIR = "D:\ResearchData\gems"
    gems-research serve

로컬 캐시만 사용을 체크하면 DartLab 파일 로더의 local_only 정책을 사용합니다. 파일이 없으면 오류를 표시하고 다운로드하지 않습니다.

## 명령행

    gems-research analyze --demo
    gems-research analyze 005930 --offline
    gems-research analyze --input evidence.json --format json

JSON 내보내기는 입력 근거를 저장합니다. 분석 기록 저장은 입력과 점수·기준 버전을 함께 로컬 SQLite에 추가하며, 같은 종목의 이전 기록을 덮어쓰지 않습니다. 예측 정확도 자동 채점은 아직 포함하지 않습니다.

## 구성과 연결 범위

- rubric.py: 평가 기준과 가중치의 정본. Gems 프롬프트가 점수를 자유롭게 바꾸는 구조가 아닙니다.
- scoring.py: 자료 검증, 점수 계산, 충족률·범위 산출.
- data.py: DartLab 0.12.0 연결. 프레임 정규화 내부 API의 변경 영향을 이 파일에 격리합니다.
- reports.py: 기존 financial-services 스킬의 검토 순서를 참고한 보고서와 Gems 검토 요청.
- server.py 및 static/: 로컬 API와 화면.
- storage.py: 입력·기준 버전·결과를 함께 보존.

financial-services의 comps-analysis, dcf-model, audit-xls, earnings-preview를 검토 절차로 참고합니다. 원본 Claude Managed Agent를 자동 실행하거나, DCF·목표주가를 생성하거나, 최신 뉴스·컨센서스를 자동 수집하는 기능은 포함하지 않습니다. 목표주가는 사용자가 별도 근거와 함께 입력하며 점수에서 역산하지 않습니다.

DartLab 코드는 Apache 2.0 라이선스이며 공개 데이터셋은 제공자가 CC BY 4.0으로 안내합니다. 재배포 시 코드 및 개별 데이터 출처의 조건을 확인하고 표시합니다. Built with dartlab (https://github.com/eddmpython/dartlab).

## 검증

    python -m pip install -e ".[test]"
    python -m pytest -q

테스트는 규칙 경계, 가중치, 자료 부족, 기준일 이후 근거 차단, 업종 예외, CAGR 기간, 보고서·기록 API를 검증합니다. 이 결과는 투자 성과 검증을 뜻하지 않습니다.
