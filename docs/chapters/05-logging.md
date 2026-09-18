# 5장 — Alloy·Loki 로그 조사

[챕터 지도](../roadmap.md)

## 목표와 현재 단계
5-1: 주문·결제 컨테이너의 기존 stdout/stderr 로그를 Grafana에서 검색한다.
5-2: JSON 로그와 request_id 전달을 추가해 주문·결제 요청을 연결한다.
5-3: 장애 재현 → 메트릭의 시간대 확인 → 로그 검색 → 복구·기록.
현재는 5-1 소스 준비 및 설정 검증 완료, Windows 실제 수집 검증 대기다.

## 구조와 파일

| 저장소 파일 | 적용 대상 | 역할 |
|---|---|---|
| compose.logs.yaml | Docker Compose | Loki·Alloy 서비스와 저장 볼륨 |
| loki/loki.yml | Loki /etc/loki/loki.yml | 단일 프로세스 TSDB·filesystem·7일 보관 |
| alloy/config.alloy | Alloy /etc/alloy/config.alloy | Docker 대상 탐색·라벨 지정·로그 전송 |
| grafana/provisioning/datasources/loki.yml | Grafana 데이터 소스 | 내부 http://loki:3100 조회 |

주문·결제 app.py는 HTTP 접근 로그를 stderr에 기록한다. Docker가 이를 보관하고 Alloy가 Docker API로 읽어 Loki로 보낸다.
Grafana는 Loki를 조회한다. 로그 수집 경로에 Prometheus는 들어가지 않는다.
Docker 프로젝트 observability-lab의 order-api, payment 두 서비스만 대상으로 선정한다.
라벨은 service_name, environment=lab, job=order-lab-logs 중심으로 제한한다.
기존 로그에는 request_id, 처리 시간, 상세 결제 오류 원인이 없다. 5-2에서 계측한다.
healthz·metrics 로그도 현재는 수집한다. 5-1에서는 쿼리로 POST 요청을 좁힌다.

## 제품과 운영 범위
- grafana/loki:3.7.8, grafana/alloy:v1.19.2 태그 고정. digest 고정은 아직 아니다.
- Loki는 로컬 디스크 단일 인스턴스다. HA·운영 부하 검증 환경이 아니다.
- retention_period=168h와 compactor로 약 7일 보관 정책을 적용한다. 삭제는 비동기이며 용량 상한을 보장하지 않는다.
- Alloy positions는 명명 볼륨에 보존한다. 최초 연결 시 Docker에 남아 있는 이전 로그를 읽을 수 있다.
- 새 로그의 수집을 검증해야 한다. 시작 이전 로그의 완전한 복구를 보장하지 않는다.
- Loki auth_enabled=false. Loki와 Alloy UI 호스트 포트는 127.0.0.1에만 바인딩한다.
- Alloy는 Docker 소켓 접근을 위해 root로 실행한다. 소켓의 :ro 마운트는 Docker API를 읽기 전용으로 제한하지 않는다.
  이 로컬 실습에서 사용하는 직접 소켓 접근 구성은 운영 배포 전 최소 권한 API 중계·노드 로그 접근 방식 등을 재검토해야 한다.
- 수집 대상 필터는 로그 범위를 제한하지만 Docker 소켓 권한 자체를 제한하지 않는다.

## 1. 브랜치 가져오기 (Windows Git Bash)
~~~bash
cd /c/Users/PC/Desktop/git-devops/observability-lab
git status --short --branch
git fetch origin
git switch --track origin/lab/005-logging
~~~
이미 로컬 브랜치가 있으면 git switch lab/005-logging 후 git pull --ff-only를 사용한다.
로컬 변경과 충돌하면 강제로 덮어쓰지 않는다. main은 병합하지 않는다.

## 2. Compose·제품 설정 검사
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml config --quiet
MSYS_NO_PATHCONV=1 docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml run --rm --no-deps loki -config.file=/etc/loki/loki.yml -verify-config=true
MSYS_NO_PATHCONV=1 docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml run --rm --no-deps alloy validate /etc/alloy/config.alloy
~~~
Loki config is valid, Alloy는 오류 없이 종료돼야 한다. 최초 실행은 이미지를 다운로드한다.

## 3. 로그 수집기 실행
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml up -d loki alloy
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml ps loki alloy
curl -sS --max-time 5 http://localhost:3100/ready
curl -sS --max-time 5 http://localhost:12345/-/ready
~~~
Loki는 기동 후 준비까지 수십 초 걸릴 수 있다. 준비 중 메시지가 보이면 잠시 후 다시 확인한다.
서비스 Up은 로그 수집 완료를 뜻하지 않는다.
Alloy UI http://localhost:12345 에서 discovery와 loki 컴포넌트를 점검할 수 있다.
이 실습의 설정 검증 통과는 Docker 소켓 접근·실제 전송 성공을 보장하지 않는다.

## 4. Grafana 데이터 소스 적용
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml restart grafana
~~~
기존 디렉터리 마운트 안에 새 데이터 소스 파일을 추가했으므로 재시작해 provisioning을 읽는다.
Grafana만 잠시 재시작되며 Prometheus 수집과 주문 API는 계속 실행된다.
http://localhost:3001 에서 Explore를 열고 데이터 소스 Loki를 선택한다.

## 5. 현재 로그 발생과 검색
Alloy 시작 후 대상 탐색까지 약 5~10초 기다린 뒤 주문을 생성한다.
~~~bash
date -Iseconds
curl -i --max-time 5 -X POST http://localhost:18080/orders -H 'Content-Type: application/json' -d '{"amount":10000}'
~~~
201/confirmed 확인. Explore에서 Last15m, 현재 시간으로 조회한다. Code 모드의 LogQL:
~~~logql
{environment="lab", service_name="order-api"} |= "POST /orders"
~~~
~~~logql
{environment="lab", service_name="payment"} |= "POST /payments"
~~~
새 요청 시각에 주문201과 결제200 접근 로그를 확인한다.
현재는 request_id가 없어 시간대·서비스·경로·코드로 좁힌다. 동일 요청을 확정적으로 연결하는 것은 다음 단계다.

## 6. 수집 문제 점검
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml logs --since=5m --tail=100 alloy loki
docker compose -f compose.yaml -f compose.orders.yaml logs --since=5m --tail=30 order-api payment
~~~
- API에 로그가 없음: 새 주문을 발생시키고 해당 서비스의 실행·응답 확인.
- API에는 있고 Loki에는 없음: Alloy Docker 접근·discovery 대상·라벨·Loki readiness·전송 오류 확인.
- Loki 데이터 소스 없음: Grafana 재시작 후 provisioning 로그 확인.
- 과거 시각으로 고정된 조회는 해제하고 현재 새 요청 시각으로 확인.
- 전송 오류가 있었다면 readiness 이후 새 요청으로 다시 검증.

## 종료·원복
~~~bash
docker compose -f compose.yaml -f compose.orders.yaml -f compose.logs.yaml stop alloy loki
~~~
다른 관측·API 서비스를 중지하지 않는다. 볼륨은 남긴다.
계속 실습한다면 종료하지 않고 5-2로 이어간다.

## 검증
준비 환경에서 위 버전 공식 Linux 실행 파일로 Loki -verify-config와 Alloy validate를 실행해 성공했다.
YAML 파싱도 확인했다. Docker Desktop 실제 소켓 수집, 이미지 기동, Grafana 조회는 사용자 실행 대기다.

## 근거
- https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.docker/
- https://grafana.com/docs/alloy/latest/reference/components/discovery/discovery.docker/
- https://grafana.com/docs/loki/latest/get-started/quick-start/quick-start/
