# 4장. 주문 API 가시화

[챕터 지도](../roadmap.md) · [구조도](../architecture.md)

## 4-1 목적과 범위

Windows → 주문 API → 모의 결제 → 주문 응답 경로를 먼저 검증한다.
observability-lab에는 API 소스가 없으므로 Python 표준 라이브러리로 작은 실습 서비스를 추가했다.
한 소스를 SERVICE_NAME 환경변수로 두 역할에 사용한다. 기존 별도 프로젝트는 수정하지 않는다.

이 서비스는 로컬 관측 실험용이다. DB·영구 주문 저장·중복 결제 방지·실제 결제·인증은 구현하지 않는다.
Python http.server 기반 서버는 운영용 웹 서버로 권장되지 않는다.
5장 측정값도 이 합성 서비스와 실행 조건 범위에서만 해석한다.
https://docs.python.org/3/library/http.server.html

## 파일

| 파일 | 역할 |
|---|---|
| compose.orders.yaml | 기존 Compose에 두 API 서비스 추가 |
| services/order-lab/app.py | 주문 검증, 결제 호출, 타임아웃·오류 처리 |
| services/order-lab/Dockerfile | Python 3.12 이미지, UID 10001 |
| services/order-lab/.dockerignore | 필요한 소스만 빌드에 포함 |

이미지 태그 python:3.12-slim은 digest 고정이 아니므로 완전한 빌드 재현은 보장하지 않는다.
주문 API healthz는 해당 프로세스 확인용이며 결제 서비스 정상까지 보장하지 않는다.

## Windows Git Bash 실행

```bash
cd /c/Users/PC/Desktop/git-devops/observability-lab
git status --short --branch
git fetch origin
git switch --track origin/lab/004-order-api
```

같은 이름의 로컬 브랜치가 이미 있다면 git switch lab/004-order-api 후 git pull --ff-only를 사용한다.
로컬 변경이 전환을 막으면 강제 덮어쓰지 않는다.

```bash
docker compose -f compose.yaml -f compose.orders.yaml config --quiet
docker compose -f compose.yaml -f compose.orders.yaml up -d --build payment order-api
docker compose -f compose.yaml -f compose.orders.yaml ps payment order-api
```

두 서비스가 healthy인지 확인한다. 초기 기동 중 starting이면 잠시 후 다시 조회한다.
payment는 내부 포트 8081만 사용하고, order-api만 127.0.0.1:18080에 공개한다.
기존 prometheus·grafana·alertmanager를 재생성할 필요는 없다.

```bash
curl -sS --max-time 5 http://localhost:18080/healthz
curl -i --max-time 5 -X POST http://localhost:18080/orders -H 'Content-Type: application/json' -d '{"amount":10000}'
```

정상 기준: healthz HTTP 200 및 service=order-api, 주문 HTTP 201 및 status=confirmed.
order_id와 payment_id는 매 요청 달라진다. amount는 최소 1, 최대 100000000의 정수다.
모의 결제는 약 80ms 대기 후 승인한다. 이 대기는 실제 CPU 처리 부하 모델이 아니다.

## 오류 점검 및 종료

```bash
docker compose -f compose.yaml -f compose.orders.yaml logs --tail=100 order-api payment
```

| 증상 | 확인 |
|---|---|
| 18080 바인딩 실패 | 기존 사용 프로세스 확인 |
| HTTP 400 | JSON과 amount 정수 범위 |
| HTTP 502 | 결제 서비스 실행·주소·응답 |
| HTTP 504 | 결제 응답 타임아웃(기본 2초) |
| 이미지 빌드 실패 | Docker Desktop 및 이미지 다운로드 연결 |

두 서비스만 중지:

```bash
docker compose -f compose.yaml -f compose.orders.yaml stop order-api payment
```

4장 서비스 작업에는 항상 두 -f 옵션을 함께 사용한다.
전체 down이나 --remove-orphans는 다른 관측 서비스까지 영향을 줄 수 있으므로 이번 종료에 사용하지 않는다.

## 검증 범위

준비 환경 Python에서 HTTP 정상 주문·잘못된 요청·결제 중단 경로를 검사했다.
Docker 이미지 빌드와 Windows에서의 실제 실행은 사용자 검증 대기다.
현재 /metrics는 없다. 주문 HTTP 201 확인 후 4-2에서 계측·수집을 추가한다.
