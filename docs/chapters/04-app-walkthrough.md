# app.py 요청 처리 순서

## 1. 프로세스 시작과 역할 선택

SERVICE_NAME 환경변수는 order-api 또는 payment다. 두 컨테이너가 같은 app.py를 별도 프로세스로 실행한다.
PORT는 각 서버의 리슨 포트다. PAYMENT_URL은 주문 서버에서 결제 서버로 요청할 주소다.
PAYMENT_TIMEOUT은 결제 HTTP 호출의 타임아웃 설정이며 전체 주문 처리의 엄격한 마감 시간은 아니다.

파일 마지막 ThreadingHTTPServer(..., Handler).serve_forever()가 요청을 기다린다.
요청마다 Handler가 만들어지고, HTTP 메서드에 따라 do_GET 또는 do_POST가 실행된다.

## 2. GET 분기

- /healthz: 현재 프로세스가 응답 가능한지 확인. 결제 성공까지 보장하지 않는다.
- /metrics: prometheus-client가 현재 프로세스의 메트릭을 텍스트로 직렬화한다.
- 그 외: 404.

이 GET 요청들은 업무 요청 Counter와 Histogram에 포함하지 않는다.

## 3. POST 계측 시작

고정 경로 /orders(order-api) 또는 /payments(payment)인지 확인한다.
그 외 경로는 404이며 업무 계측에서 제외한다.

time.perf_counter()로 시작 시간을 저장하고 handle_business_post()를 호출한다.
finally는 정상·오류 반환 뒤 모두 실행되며 처리 횟수와 소요 시간을 기록한다.

## 4. 요청 본문 검증

Content-Length로 읽을 바이트 수를 정한다. 1~4096바이트 범위를 벗어나면 400이다.
json.loads로 JSON 텍스트를 Python 객체로 바꾼다. dict인지 확인하고 amount를 꺼낸다.
amount는 1~100000000의 정수여야 한다. bool도 int의 하위 타입이므로 type(amount) is int로 true를 제외한다.
실패 시 reply(400, ...) 후 return하므로 결제를 호출하지 않는다.

## 5. 주문 서버의 결제 호출

Request로 PAYMENT_URL에 보낼 POST 요청을 만든다. amount를 JSON으로 직렬화해서 보낸다.
urlopen(request, timeout=PAYMENT_TIMEOUT)이 실제 HTTP 통신을 수행한다.
Docker 내부 DNS 이름 payment가 결제 컨테이너 주소로 해석된다.
이 호출이 진행되는 동안 주문 서버의 해당 요청 스레드는 결제 응답을 기다린다.

## 6. 결제 서버의 처리

결제 컨테이너의 do_POST도 같은 검증과 계측 과정을 거친다.
SERVICE == payment 분기에서 time.sleep(0.08)로 80ms를 기다린다.
UUID 결제 식별자를 만들고 200/approved를 반환한다. 외부 결제·실제 금액 처리는 없다.

## 7. 주문 확정 또는 오류 응답

주문 서버는 결제 응답 JSON의 status가 approved인지 확인한다.
정상이면 UUID 주문 식별자와 결제 식별자를 담아 201/confirmed를 반환한다.
DB 저장이나 주문 조회 기능은 없다.

| 경로 | 주문 응답 |
|---|---|
| 정상 결제 | 201 |
| 입력 검증 실패 | 400 |
| 결제 HTTP 오류·연결 실패·비정상 응답 | 502 |
| 결제 타임아웃 | 504 |
| 처리 중 예상하지 못한 예외 | 500 |

## 8. reply와 계측 마무리

reply는 response_status를 저장하고, JSON을 바이트로 변환하고, HTTP 상태·헤더·본문을 쓴다.
finally에서 REQUESTS.labels(...).inc()로 해당 코드의 횟수를 1 증가시킨다.
DURATION.labels(...).observe(경과 시간)으로 Histogram을 갱신한다.
이는 서버 처리 결과이며 클라이언트가 응답을 온전히 수신했다는 보장은 아니다.

## 9. Prometheus 수집

Prometheus가 15초마다 각 서비스의 /metrics를 읽는다.
요청할 때마다 Prometheus로 전송하는 구조가 아니다. 메트릭은 프로세스 메모리에 누적되고 수집 시 노출된다.
Counter는 누적 횟수, Histogram은 구간별 누적 횟수·총 시간·총 건수를 노출한다.
라벨은 서비스·고정 경로·메서드·상태 코드로 제한하며 주문별 식별자를 넣지 않는다.

## 실습 범위

Python http.server 기반의 합성 서비스로 운영 배포용 서버가 아니다.
프로세스 중단 시 메모리의 계측값은 초기화된다. 서버 처리 시간과 클라이언트 체감 시간은 측정 범위가 다르다.
계측과 장애 분석 방법을 학습한 후 실제 서비스의 프레임워크·구조에 맞게 적용한다.
