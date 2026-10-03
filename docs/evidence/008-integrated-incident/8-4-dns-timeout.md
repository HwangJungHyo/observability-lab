# 8-4 이름 조회 실패·응답 시간 초과 비교

실습일: 2026-10-03 KST. 브랜치: `lab/008-integrated-incident`.
근거: 사용자가 Windows Git Bash와 Docker Desktop에서 실행해 제공한 출력. 원본 출력의 핵심 필드를 정리한 기록이다.

## 1. 목표와 완료 조건

같은 호출 실패라도 내부 오류에 따라 조사 방향이 달라짐을 확인한다. 이름 조회 실패와 응답 시간 초과를 비교하고, 정상 지연 설정으로 복구한 뒤 주문 성공을 확인한다.

**판정: 이름 조회 실패 재현, 실제 주문 timeout, 복구 주문 성공 확인 완료.**
연결 거부는 직접 재현하지 않았다. 원래 목차의 연결 거부 항목을 수행한 것으로 처리하지 않고, 실제 확인한 실패 유형에 맞춰 기록한다.

## 2. 결과 비교

| 구분 | 실행 경로 | 조건 | 확인 결과 | 시간 |
|---|---|---|---|---|
| 정상 연결 진단 | order-api 컨테이너의 별도 Python 프로세스 | payment 실행 | DNS·TCP·HTTP 성공 | 아래 별도 기록 |
| 중지 진단 | 동일 컨테이너에서 urlopen으로 POST /payments | payment 중지, timeout=2 | URLError → gaierror, errno=-5 | 4.010874초 |
| 응답 지연 | curl → order-api → payment | payment 지연 3초, 호출 제한 2초 | HTTP 504, payment_timeout | 2.014662초 |
| 복구 | curl → order-api → payment | payment 지연 0.08초로 재생성 | HTTP 201, confirmed | 0.086822초 |

중지 진단은 별도 호출을 재현한 결과다. 8-3의 과거 실패 요청에 기록되지 않은 내부 원인을 소급해 확정하지 않는다.

## 3. 정상 연결 진단과 범위 정리

```text
HOST=payment PORT=8081 TIMEOUT_SECONDS=2.0
DNS: OK result=['172.18.0.9']
DNS_MS=4.599
TCP: OK result=connected
TCP_MS=0.404
HTTP: OK result=200
HTTP_MS=6.467
```

현재 연결 상태는 확인했지만, 이미 주문 복구까지 확인한 상황에서 과거 URLError 원인을 밝히는 추가 가치는 작았다. 이 진단은 /healthz에 대한 검사이며 실제 장애 요청인 POST /payments와 다르다. 각 측정은 독립 시도로 TCP·HTTP 단계도 이름 조회를 포함할 수 있어 시간을 단순 합산·차감하지 않는다.

실습 원칙: 학습 목표와 완료 조건에 필요한 증거를 확보한 뒤 다음 단계로 이동한다. 결과에 따라 조치가 달라지지 않는 중복 정상 검사는 반복하지 않는다.

## 4. payment 중지 상태의 내부 오류 확인

실행 순서: payment 중지 → order-api 컨테이너의 별도 Python 프로세스에서 결제 POST 요청 → payment 시작.

```bash
bash scripts/mimir-compose.sh stop payment

bash scripts/mimir-compose.sh exec -T order-api python - <<'PY'
import json
import os
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

request = Request(
    os.getenv("PAYMENT_URL", "http://payment:8081/payments"),
    data=json.dumps({"amount": 10000}).encode(),
    headers={"Content-Type": "application/json",
             "X-Request-ID": "diagnostic-payment-down"},
    method="POST",
)
timeout = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "2"))
print(f"TIMEOUT_SECONDS={timeout}", flush=True)
started = time.perf_counter()
try:
    with urlopen(request, timeout=timeout) as response:
        response.read()
        print(f"HTTP={response.status}")
except Exception as exc:
    reason = exc.reason if isinstance(exc, URLError) else exc
    print(f"EXCEPTION_TYPE={type(exc).__name__}")
    print(f"REASON_TYPE={type(reason).__name__}")
    print(f"ERRNO={getattr(reason, 'errno', None)}")
    print(f"REASON={reason}")
finally:
    print(f"ELAPSED_SECONDS={time.perf_counter() - started:.6f}")
PY

bash scripts/mimir-compose.sh start payment
```

관측 결과:

```text
TIMEOUT_SECONDS=2.0
EXCEPTION_TYPE=URLError
REASON_TYPE=gaierror
ERRNO=-5
REASON=[Errno -5] No address associated with hostname
ELAPSED_SECONDS=4.010874
```

이름을 주소로 바꾸는 단계에서 실패했다. 연결 거부 또는 payment의 응답 지연으로 판정하지 않는다. 약 4초는 전체 진단 호출 시간이며, resolver의 세부 재시도 횟수나 각 단계 시간은 측정하지 않았다.

urlopen의 timeout은 DNS 등 모든 단계를 포함하는 호출 전체의 절대 종료 시각을 보장하지 않는다. 이 결과만으로 제한 시간이 2회 적용됐다고 추정하지 않는다.

## 5. 실제 주문의 응답 시간 초과

기존 order-api 제한 시간은 2초다. payment의 지연만 3초로 변경했다.

```bash
PAYMENT_DELAY_SECONDS=3 \
  bash scripts/mimir-compose.sh up -d \
  --no-deps --force-recreate --no-build --pull never payment
```

실행 직후 상태 출력은 health: starting이었다. 이후 아래 실제 주문 요청에서 timeout을 확인했다.

```bash
REQUEST_ID="timeout-3s-$(date -u +%Y%m%dT%H%M%SZ)"
printf 'REQUEST_ID=%s\n' "$REQUEST_ID"

curl -4 -sS -i --max-time 10 \
  -X POST http://localhost:18080/orders \
  -H 'Content-Type: application/json' \
  -H "X-Request-ID: $REQUEST_ID" \
  -d '{"amount":10000}' \
  -w '\nHTTP=%{http_code}\nTOTAL_SECONDS=%{time_total}\n'
```

| 항목 | 결과 |
|---|---|
| Request ID | timeout-3s-20261003T004522Z |
| Trace ID | 3482ae471b7ca667df02f27d02763ea0 |
| 응답 시각 KST | 2026-10-03 09:45:25 |
| HTTP | 504 Gateway Timeout |
| 본문 | {"error": "payment_timeout"} |
| curl 전체 시간 | 2.014662초 |

위 실행은 3초 지연 조건에서 애플리케이션의 timeout 처리를 확인한 것이다. 해당 요청의 payment 로그·트레이스 상세 및 하위 처리 완료 여부는 추가 수집하지 않았다.

## 6. 기본 설정 복구와 실제 주문 검증

```bash
PAYMENT_DELAY_SECONDS=0.08 \
  bash scripts/mimir-compose.sh up -d \
  --no-deps --force-recreate --no-build --pull never payment
```

복구 후 같은 POST /orders 요청을 고유 요청 ID로 실행했다.

| 항목 | 결과 |
|---|---|
| Request ID | timeout-recovery-20261003T004826Z |
| Trace ID | a5f6b8a4d14ac509f4029ad5d8f1577e |
| 응답 시각 KST | 2026-10-03 09:48:27 |
| HTTP / 본문 상태 | 201 / confirmed |
| curl 전체 시간 | 86.822ms |

8-3의 정상 주문 83.556ms와 유사한 수준으로 복구됐다. 단일 요청 검증이며 지속 안정성을 입증하는 부하 시험은 아니다.

## 7. 환경변수 전달 개념

명령 앞의 `PAYMENT_DELAY_SECONDS=3`은 해당 명령에 환경변수를 전달하는 Bash 문법이다. 줄 끝 역슬래시는 명령을 다음 줄로 이어준다.

1. Bash가 변수를 가진 환경으로 mimir-compose.sh를 실행한다.
2. 스크립트의 exec docker compose가 환경을 이어받는다.
3. compose.orders.yaml의 `PAYMENT_DELAY_SECONDS: "${PAYMENT_DELAY_SECONDS:-0.08}"`에서 값을 치환한다.
4. Compose가 새 payment 컨테이너 환경에 값을 설정한다.
5. Python이 os.getenv로 읽어 time.sleep의 지연 값으로 사용한다.

명령에 전달한 환경변수가 --env-file의 같은 이름 값보다 우선한다. 파일 자체는 수정하지 않는다. 만들어진 컨테이너에는 설정이 유지되므로 0.08을 전달해 재생성하는 복구가 필요하다.

## 8. timeout과 하위 처리 완료는 별개

현재 저장소 코드에는 payment가 time.sleep 이후 승인 응답을 생성하는 경로가 있고, 상위 호출자의 timeout을 받아 작업을 취소하는 로직은 없다. 따라서 order-api가 기다리기를 끝내도 payment의 작업은 계속될 수 있다.

이는 코드 기반 해석이며 이번 요청이 실제로 끝까지 처리됐다는 관측 증거는 아니다. 이 앱에는 실제 결제 처리나 영속 결제 원장이 없다.

실무 결제에서는 timeout을 결제 미실행으로 단정해 즉시 새 결제를 요청하면 중복 처리 위험이 있다. 동일 업무의 재시도에는 서버가 지원하는 멱등성 키와 기존 거래 상태 조회가 필요하다. 현재 X-Request-ID는 추적용으로, 중복 실행을 막는 기능이 구현돼 있지 않다.

## 9. 실무 조사 방향과 남은 항목

| 실패 유형 | 먼저 확인할 대상 | 이번 검증 |
|---|---|---|
| 이름 조회 실패 | 대상 서비스 상태, 서비스 이름·DNS 설정 | 직접 재현 |
| 연결 거부 | 대상 IP·포트, 리스닝 프로세스 | 미실습 |
| 응답 시간 초과 | 하위 서비스 처리 지연, 부하, 제한 시간 | 실제 주문으로 확인 |

후속 항목: 8-3 과거 요청의 내부 원인 확정, 약 4초의 resolver 세부 동작, curl과 서버 시간 차이, 코드·이미지 일치 검증, timeout 이후 하위 완료의 직접 관측.
이 항목들은 8-5 진입의 필수 조건으로 두지 않는다.

다음 단계: 8-5에서 동시 요청을 증가시켜 처리량·지연·오류·자원을 함께 비교한다.

## 참고

- [Python URLError](https://docs.python.org/3.12/library/urllib.error.html)
- [Python socket](https://docs.python.org/3.12/library/socket.html)
- [Python urlopen](https://docs.python.org/3.12/library/urllib.request.html)
- [Bash 환경변수](https://www.gnu.org/software/bash/manual/html_node/Environment.html)
- [Docker Compose 변수 치환](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
- [AWS: 안전한 재시도와 멱등성](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
