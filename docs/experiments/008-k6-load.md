# 8-5 k6 부하 실습 실행 가이드

작성일: 2026-10-03. 사용자 환경에서 초기 smoke와 자원 제한·중단 기준 추가 후 smoke를 각각 106건·실패 0건으로 완료했다. 이후 1→3→5 VU 단계 부하는 2080건·실패 0건이었다. 상세 수치는 [8-5 결과](../evidence/008-integrated-incident/8-5-load-results.md)에 기록한다.

이번 장의 실행 범위는 여기서 종료했다. 아래 명령은 재현용이며 추가 부하 실행을 요구하지 않는다. spike·soak와 자동 중단 실제 발동은 미검증이다.

## 목적과 파일

동시 요청 수 증가에 따른 처리량·지연·실패·자원 변화를 비교한다. 장애를 반드시 일으키거나 운영 최대 용량을 산정하는 시험은 아니다.

| 파일 | 목적 |
|---|---|
| scripts/k6-orders.js | 주문 호출, 응답 검증, 부하 구성, 단계별 결과 |
| scripts/run-k6-orders.sh | 고유 실행 ID 생성, Compose 실행, 출력 저장 |
| compose.k6.yaml | 기존 네트워크에 임시 k6 컨테이너 추가 |
| compose.load-limits.yaml | 실습 대상 두 서비스의 CPU·메모리 제한 |

저장소 루트에 위 상대 경로대로 설치한다. 기존 mimir-compose.sh와 .env.mimir 및 로컬 이미지 잠금 파일을 사용한다. 기본 Compose 파일은 수정하지 않고 추가 overlay로 실습 자원 제한을 적용한다. 아래 적용 명령은 두 애플리케이션을 재생성한다.

## 호출 경로

k6 컨테이너 → Compose 기본 네트워크 → order-api:8080 → payment:8081.

컨테이너 안의 localhost는 해당 컨테이너 자신이다. 따라서 k6의 대상은 Windows의 localhost:18080이 아니라 같은 네트워크의 서비스 이름이다. 기존 Windows curl과 접속 경로·연결 재사용 조건이 달라 지연을 직접 동등 비교하지 않는다. 이번 smoke를 k6 기준선으로 사용한다.

## 실행 순서

payment 지연 0.08초, order-api 제한 2초인 정상 상태에서 실행한다. 8-4 복구 요청은 201 / 86.822ms였다. 시간이 지났거나 설정을 바꿨다면 현재 상태를 확인한다.

먼저 [자원 제한 적용 가이드](008-k6-limits.md)에 따라 제한 적용과 inspect 확인을 수행한다. 이후 최초 부하는 다음 명령 하나만 실행한다.

```bash
bash scripts/run-k6-orders.sh smoke
```

grafana/k6:1.3.0 이미지가 없으면 Docker가 내려받는다. 버전 태그를 고정했으며 digest까지 고정한 구성은 아니다. 필요하면 실행 후 실제 이미지 정보를 증거로 기록한다.

```bash
docker image inspect grafana/k6:1.3.0 --format '{{.Id}} {{json .RepoDigests}}'
```

smoke가 정상이고 저장 결과가 확인된 다음 단계 부하를 실행한다.

```bash
bash scripts/run-k6-orders.sh steps
```

다음 두 프로필은 선택 심화용으로 준비했으며 이번 장에서는 실행하지 않았다. 310초 soak는 짧은 지속 부하 연습이며 장기 안정성 시험을 대신하지 않는다.

```bash
# 선택 심화: 별도 실험으로 실행
bash scripts/run-k6-orders.sh spike
# steps의 5 VU가 안정적이었을 때만 실행
bash scripts/run-k6-orders.sh soak
```

| PROFILE | 목표 VU와 시간 | 본 실행 시간 |
|---|---|---|
| smoke | 1 VU 유지 30초 | 30초 |
| steps | 1 VU 60초 → 10초에 걸쳐 3 VU → 3 VU 60초 → 10초에 걸쳐 5 VU → 5 VU 60초 | 200초 |
| spike | 1 VU 30초 → 1초에 걸쳐 10 VU → 10 VU 30초 → 1초에 걸쳐 1 VU → 1 VU 60초 | 122초 |
| soak | 1 VU에서 10초에 걸쳐 5 VU → 5 VU 300초 | 310초 |

종료 유예 최대 6초가 추가될 수 있다. ramp-down에서도 진행 중 요청을 최대 6초 기다려 목표 VU에 바로 도달하지 않을 수 있다. steady 구간의 시작에도 이 영향이 일부 포함될 수 있다.

## 설정의 의미

| 설정 | 값 | 의미 |
|---|---|---|
| executor | ramping-vus | 가상 사용자 수를 시간에 따라 변경 |
| startVUs | 1 | 가상 사용자 1명으로 시작 |
| stages | 프로필별 목록 | 각 구간 끝의 목표 VU와 구간 시간 |
| sleep | 0.2초 | 각 VU가 요청 종료 후 쉬는 시간 |
| HTTP timeout | 5초 | k6 요청의 제한 시간. 서버의 payment 제한 2초와 별개 |
| gracefulStop / gracefulRampDown | 6초 | 진행 중 요청 종료를 기다리는 유예 |
| redirects | 0 | 주문 응답의 리다이렉트를 자동으로 따라가지 않음 |
| expectedStatuses | 201 | 이 테스트의 HTTP 성공 코드 |
| checks | 201, confirmed, amount, 주문·결제 ID | 본문까지 업무 성공 검증 |
| business_failed threshold | rate==0 | 실패가 있으면 종료 코드를 실패로 반환. 운영 SLO 아님 |
| 자동 중단 | 누적 실패율 5% 이상 또는 누적 HTTP p95 1000ms 이상 | 시작 30초 이후 주기적 평가 시 중단 |
| summaryTrendStats | 평균·최소·중앙·최대·p95·p99 | 지연 분포 기록 |

rate==0 조건 자체는 조기 중단하지 않는다. 별도 abortOnFail 조건이 누적 실패율 5% 이상 또는 누적 p95 1000ms 이상이면 시작 30초 이후 평가 시 중단한다. 최근 30초 이동 구간이나 정확히 30초 시각의 검사가 아니다. 실험 종료 시에도 threshold를 평가하므로 짧은 smoke에서는 종료 판정에 주로 사용될 수 있다. 자동 중단은 진행 중 요청을 끊을 수 있으며 결과는 부분 기록이다. 계속되는 오류·자원 부족·관측 불능이면 Ctrl+C로 중단하고 상태를 확인한다.

VU는 동시에 작업하는 가상 사용자이며 고정 RPS가 아니다. 응답 0.08초와 대기 0.2초라면 이론상 1 VU당 약 3.6회/초이나 네트워크·처리 비용에 따라 실제 값은 달라진다. 응답이 느려지면 같은 VU 수에서도 요청률이 줄어드는 닫힌 부하 모델이다.

## 결과 파일

기존 .gitignore에서 제외한 .local/k6-results/에 실행 ID별 파일을 생성한다.

| 파일 | 내용 |
|---|---|
| RUN_ID.summary.json | 프로필, 단계별 완료 요청·실패·지연, k6 집계 |
| RUN_ID.points.json | 타임스탬프가 있는 원시 메트릭. 줄 단위 JSON이며 단일 JSON 배열이 아님 |
| RUN_ID.console.log | 콘솔과 요청·Trace ID 표본 |

요청 ID는 RUN_ID-VU-ITER 형태다. 각 VU의 첫 요청과 최대 3개 실패의 연결 정보를 콘솔에 남긴다. 모든 요청의 ID 목록을 별도로 보존하지는 않는다. Request ID나 Trace ID를 요청별 메트릭 태그로 넣지 않는다.

단계별 요청은 시작 시각 기준으로 분류한다. 단계 경계를 넘어 끝난 요청도 시작 단계에 포함한다. 평균·p95는 성공과 실패를 모두 포함하며, 연결 실패처럼 짧은 오류가 늘면 지연 평균이 낮아질 수 있어 실패율과 함께 해석한다. 원시 메트릭에는 상태·단계 태그가 남는다.

http_req_duration은 전송·응답 대기·수신 시간이며 연결 준비 등은 제외한다. curl time_total과 같은 지표가 아니다. 연결 시간은 원시 k6 지표의 http_req_connecting 등으로 별도 확인한다.

전체 처리량은 summary의 k6.metrics.http_reqs.values.rate로 확인한다. 단계별 정밀 요청률은 points 파일의 시각과 단계로 집계한다. 완료 건수를 계획 시간으로 나눈 값은 경계 요청·종료 유예를 고려하지 않은 근사치다.

표본이 적은 smoke의 p95·p99는 기능 확인용이다. 장기 성능이나 운영 SLO로 일반화하지 않는다. summary의 오류 Rate에서 passes는 true 관측 수이며, business_failed에서는 실패 수를 뜻한다.

## 관측과 학습 완료 조건

재현 시 별도 터미널에서 생성기·애플리케이션·관측 서비스의 자원을 함께 확인한다.

```bash
docker stats
```

Windows CPU·메모리는 기존 Grafana 호스트 대시보드로 본다. k6와 관측 서비스도 같은 PC의 자원을 사용하므로 생성기 부하를 서버 병목으로 단정하지 않는다. Prometheus의 lab_http_requests_total과 duration histogram도 같은 실험 시간대로 비교한다.

모든 요청마다 Loki·Tempo 화면을 열지 않는다. 5xx·timeout·지연 증가처럼 설명이 필요한 사례에서 표본 요청을 골라 연결한다.

이번 학습의 완료 범위는 smoke와 단계 부하의 처리량·평균/p95·실패율을 해석하고 증거의 한계를 기록하는 것이다. 부하 중 자원 추세와 종료 후 별도 정상 주문은 제공된 자료에서 확인하지 못해 미검증으로 남겼다. 부하 범위에서 저하가 없다면 그 사실을 기록하고 부하를 계속 늘리지 않는다. 선택 프로필까지 모두 실행해야 이번 장을 마치는 것은 아니다.

## 검증 범위

사용자가 제공한 출력으로 smoke 2회와 단계 부하의 실제 실행 성공을 확인했다. 리뷰 환경에서는 Bash·JavaScript 문법, YAML 및 모의 응답 분류·단계 경계·요약·중단 설정을 검사했다. Docker와 k6 실행기가 없는 리뷰 환경에서 추가 부하를 실행하지 않았다.

두 앱의 메모리 상한 512MiB는 docker stats로 확인했지만 CPU·스왑·생성기 제한 적용값의 inspect 출력은 제공되지 않았다. 자동 중단 기준을 넘긴 실행도 없어 실제 중단 동작은 미검증이다. 설정 검토와 실제 동작 검증을 구분한다. 최신 완료 범위는 [최종 보고서](../evidence/008-integrated-incident/8-7-final-report.md)를 따른다.

## 공식 참고

- https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-vus/
- https://grafana.com/docs/k6/latest/using-k6/metrics/reference/
- https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/
- https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/
