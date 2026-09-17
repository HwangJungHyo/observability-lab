# 4-3b 제어된 결제 지연 실험

## 목적
서비스 중단 없이도 고객 주문이 느려지는 상황을 검증한다.
이전 중단 실험은 연결 실패 502였다. 이번에는 결제를 정상 승인하되 대기 시간을 0.08초에서 1초로 변경한다.
1초는 2초 결제 타임아웃보다 여유가 있고 정상 대비 차이가 잘 드러나는 기능 검증 값이다. 운영 임계값이 아니다.
PAYMENT_DELAY_SECONDS는 추가 지연이 아니라 기존 80ms를 대체하는 전체 모의 대기 시간이다.
범위 0~10초 유한값만 허용한다. 이번 실험에서는 1초만 사용한다.

## 구현
- app.py: PAYMENT_DELAY_SECONDS 읽기, 유한값·범위 검사, payment 분기의 sleep에 적용
- compose.orders.yaml: 환경변수 전달, 미지정 시 0.08
- 컨테이너 시작 시 설정을 읽으므로 값 변경 시 payment 재생성이 필요하다.
- healthz와 metrics는 지연 주입 대상이 아니다.
- 주문 서버와 Prometheus는 재생성하지 않는다.

## 실행 (Windows Git Bash, 저장소 루트)
~~~bash
git status --short --branch
git pull --ff-only origin lab/004-order-api
PAYMENT_DELAY_SECONDS=1 docker compose -f compose.yaml -f compose.orders.yaml config --quiet
~~~
오류가 없을 때:
~~~bash
date -Iseconds
PAYMENT_DELAY_SECONDS=1 docker compose -f compose.yaml -f compose.orders.yaml up -d --build --no-deps --force-recreate payment
docker compose -f compose.yaml -f compose.orders.yaml ps payment order-api
docker compose -f compose.yaml -f compose.orders.yaml exec -T payment printenv PAYMENT_DELAY_SECONDS
~~~
payment healthy와 환경변수 1을 확인한 뒤 요청한다.
~~~bash
curl -sS --max-time 5 -w '\nHTTP %{http_code} duration=%{time_total}s\n' -X POST http://localhost:18080/orders -H 'Content-Type: application/json' -d '{"amount":10000}'
~~~
201과 약 1초 이상의 응답을 확인하고 반복한다.
~~~bash
for i in {1..90}; do
  curl -sS --max-time 5 -o /dev/null -w 'HTTP %{http_code} duration=%{time_total}s\n' -X POST http://localhost:18080/orders -H 'Content-Type: application/json' -d '{"amount":10000}'
  sleep 1
done
~~~
약 3분 이상 걸리는 순차 요청이다. Grafana last15m, refresh15s로 본다.

## 기대와 해석
- 재생성 직후 짧은 중단은 있을 수 있다. healthy 후 안정 구간을 분석한다.
- 안정 구간에서 up은 두 대상 모두 1, 주문201, 시스템 오류율0%.
- 평균 지연 상승. p95도 상승하지만 1~2초 버킷 때문에 약 1.95초로 추정될 수 있다. 실제 요청이 1.95초라는 뜻은 아니다.
- 순차 요청은 응답1초 + sleep1초 이상이므로 약 0.5req/s 이하. 최대 처리량 시험이 아니다.
- sleep으로 의존 서비스 대기를 모사한다. CPU 병목이나 실제 네트워크 지연을 재현한 것은 아니다.
- 5xx가 나오면 정상 지연 시나리오의 기대에서 벗어난 결과이므로 그대로 기록하고 진단한다.

## 원복 (반드시 명시적으로 0.08 적용)
~~~bash
date -Iseconds
PAYMENT_DELAY_SECONDS=0.08 docker compose -f compose.yaml -f compose.orders.yaml up -d --no-deps --force-recreate payment
docker compose -f compose.yaml -f compose.orders.yaml ps payment order-api
docker compose -f compose.yaml -f compose.orders.yaml exec -T payment printenv PAYMENT_DELAY_SECONDS
~~~
healthy와 0.08을 확인하고 같은 반복 요청으로 2분 이상 정상 데이터를 쌓는다.
두 대상 UP, 오류율0%, 평균·p95 안정화를 확인한다.
명령 앞의 변수는 해당 Compose 실행에만 전달되지만 생성된 컨테이너에는 값이 유지된다. 명령이 끝났다고 지연이 자동 원복되지 않는다.

## 검증 상태
준비 환경 Python 실제 HTTP 호출: 0.08 설정에서 주문201 약0.086초, 1 설정에서 주문201 약1.006초 확인.
payment healthz200, -1/nan/inf/11 입력 기동 거부 확인.
Windows Docker 빌드·실제 지연·Grafana 반응·원복은 사용자 실행 확인 대기.
결과 수치는 기대와 분리해서 기록한다.

참고: https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/
