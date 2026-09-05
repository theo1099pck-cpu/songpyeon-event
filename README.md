# 빠른티비 한가위 송편 랜덤 뽑기 v2

실제 링크 배포를 전제로 만든 Flask + PostgreSQL 버전입니다.

## 운영 흐름

1. 회원이 텔레그램으로 이벤트 참여/업체 이용 인증
2. 운영자가 `/admin/login` 접속
3. 관리자에서 1회용 참여코드 생성
4. 회원에게 `웹주소 + 참여코드` 전달
5. 회원이 닉네임/코드를 입력하고 송편 1~10번 중 하나 선택
6. 서버가 자동 추첨
7. 당첨 결과 + 12자리 확인번호 표시
8. 관리자 페이지에 같은 결과가 자동 저장
9. 참여코드는 즉시 사용완료 처리되어 재사용 불가

## 포함 기능

- 1회용 참여코드
- 서버 측 랜덤 추첨 (`secrets.randbelow`)
- 코드 중복 사용 방지
- PostgreSQL 영구 DB 지원
- 로컬 테스트 시 SQLite 자동 사용
- 관리자 로그인
- 참여코드 일괄 생성
- 코드별 메모
- 보상명 / 포인트 / 확률 관리자 수정
- 확률 합계 100% 검증
- 전체 당첨 결과 조회
- 결과 확인번호(HMAC)
- CSV 다운로드
- 미사용 코드 삭제 / 사용코드 초기화
- 회원 화면에 현재 확률 공개
- Render Blueprint용 `render.yaml` 포함

## 기본 확률

- 일반 송편 5,000P: 60%
- 복 송편 10,000P: 25%
- 대박 송편 30,000P: 10%
- 황금 송편 50,000P: 5%

관리자 페이지에서 변경할 수 있습니다.

---

# 가장 쉬운 Render 무료 배포

Render 공식 문서 기준 Flask 웹서비스와 Free Postgres를 사용할 수 있습니다.
Free Postgres는 생성 후 30일이 지나면 만료되므로, 추석 단기 이벤트용으로 사용하세요.

## 방법 A — Blueprint 사용(추천)

### 1. GitHub에 새 저장소 만들기
예: `songpyeon-event`

### 2. 이 ZIP의 압축을 풀고 모든 파일을 GitHub 저장소에 업로드
루트에 아래 파일들이 보여야 합니다.

- app.py
- requirements.txt
- render.yaml
- .python-version
- templates/

### 3. Render 가입/로그인 후 Blueprint 생성
Render Dashboard → New → Blueprint

GitHub 저장소를 연결하면 `render.yaml`을 읽어서:
- 무료 Web Service 1개
- 무료 PostgreSQL DB 1개

를 함께 만들도록 구성되어 있습니다.

### 4. ADMIN_PASSWORD 입력
Blueprint 생성 과정에서 `ADMIN_PASSWORD` 값을 묻습니다.
원하는 관리자 비밀번호를 넣으세요.

예:
`MySongpyeon-2026-StrongPassword`

절대로 회원에게 알려주지 마세요.

### 5. 배포 완료
웹서비스 주소가 아래처럼 생깁니다.

`https://songpyeon-event.onrender.com`

회원용:
`https://...onrender.com/`

관리자:
`https://...onrender.com/admin/login`

---

# 방법 B — Render에서 수동 생성

1. Render → New → Postgres
2. Free 플랜 선택
3. DB 생성
4. Render → New → Web Service
5. GitHub 저장소 연결
6. 설정:
   - Language: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Plan: Free
7. Environment Variables 추가:
   - `DATABASE_URL`: 위 PostgreSQL의 Internal Database URL
   - `ADMIN_PASSWORD`: 관리자 비밀번호
   - `SECRET_KEY`: 긴 임의 문자열
   - `RECEIPT_SECRET`: 긴 임의 문자열
   - `PYTHON_VERSION`: `3.13.5`
8. Deploy

---

# 무료 플랜 주의사항

- Render Free Web Service는 일정 시간 요청이 없으면 sleep 상태로 들어갑니다.
- 첫 회원 접속 때 서버가 다시 켜지면서 잠시 기다릴 수 있습니다.
- Free Postgres는 30일 후 만료됩니다.
- 이벤트 종료 전 관리자 페이지에서 CSV를 다운로드하여 결과를 백업하세요.
- 중요한 이벤트라면 당일 시작 전에 반드시 휴대폰/PC에서 실제 테스트 코드를 2~3개 사용해보세요.

---

# 로컬 테스트

Windows CMD:

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set ADMIN_PASSWORD=test1234
python app.py
```

그 후:

회원 화면:
`http://127.0.0.1:5000`

관리자:
`http://127.0.0.1:5000/admin/login`

DATABASE_URL이 없으면 자동으로 SQLite를 사용합니다.

---

# 신뢰성에 대한 설명

회원에게 이렇게 안내할 수 있습니다.

> 이벤트 참여코드는 1회만 사용할 수 있으며, 송편 선택 후 당첨 결과는 서버에서 자동 추첨되어 즉시 기록됩니다. 결과에는 고유 확인번호가 발급되며 운영진 관리자 기록에서도 동일한 결과를 확인할 수 있습니다.

현재 버전은 운영자가 추첨 버튼을 눌러 결과를 정하는 방식이 아닙니다.
서버의 `secrets` 난수로 자동 결정합니다.

다만 이것은 '자동 랜덤 추첨 + 서버 기록' 구조이지 블록체인식 provably-fair 시스템은 아닙니다.
대외적으로 "조작이 수학적으로 불가능하다" 같은 표현은 사용하지 않는 것이 좋습니다.
