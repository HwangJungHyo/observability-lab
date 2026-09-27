# 8-0 준비 점검 결과

## 목적과 판정

통합 장애 실습 전에 정상 주문 처리와 메트릭·로그·트레이스 조회 경로를 확인했다. 핵심 경로 점검은 통과했다. 장시간 안정성, 최대 처리량, 모든 관측 데이터의 무손실 수집까지 검증한 결과는 아니다.

## 환경과 시작 상태

- 실행 환경: Windows Git Bash, Docker Desktop.
- 사용자 작업 브랜치: `lab/007-mimir`.
- 최초 `git status --short --branch`: 변경 파일 없음. 당시 출력만으로 원격 최신 상태까지 보장하지는 않는다.
- 실행 구성: `bash scripts/mimir-compose.sh`.
- order-api: 호스트 `127.0.0.1:18080`, payment: 내부 `8081`.
- Prometheus: `9090`, Mimir: `9009`, Grafana: `3001`.
- Mimir 테넌트: `lab`.

초기 확인에서 order-api, payment, Prometheus, Alertmanager가 `Exited (255)` 상태였다. 기동 후 order-api와 payment의 healthy 상태, Prometheus와 Alertmanager의 준비 응답을 확인했다. 공통 종료의 근본 원인은 확정하지 않았다.

## Mimir 실험 설정 복원

보존 만료 실습에서 단축했던 설정이 아래 값으로 복원된 것을 `/config`로 확인했다.

| 항목 | 확인값 |
|---|---|
| `compactor_blocks_retention_period` | `1w` |
| `cleanup_interval` | `15m0s` |
| `deletion_delay` | `12h0m0s` |
| `/ready` | HTTP 200, `ready` |

## 정상 주문과 관측 경로

2026-09-27 10:58 KST에 `POST /orders`로 `{"amount":10000}`을 전송했다.

| 항목 | 결과 |
|---|---|
| order-api `/healthz` | HTTP 200, `status: ok` |
| 주문 응답 | HTTP 201, `status: confirmed` |
| 요청 ID | `baseline-20260927T015803Z-31977` |
| Trace ID | `0a4ce377f71b7d73799f103082a5980b` |
| Tempo | 2개 서비스, 3개 span, 전체 98.01ms |
| Loki | 해당 요청 ID로 로그 2줄 검색 |

Loki 첫 화면은 본문이 접혀 있었으므로 두 줄의 개별 서비스·필드까지 확인한 것으로 기록하지 않는다. 이후 8-1의 76번 요청에서는 두 서비스의 로그 본문과 동일 Trace ID를 확인했다.

Prometheus와 Mimir에서 다음 쿼리로 5개 대상이 모두 `1`임을 확인했다.

```promql
up{job=~"order-api|payment|mimir|windows|prometheus"}
```

| job | instance | Prometheus | Mimir |
|---|---|---:|---:|
| order-api | order-api:8080 | 1 | 1 |
| payment | payment:8081 | 1 | 1 |
| mimir | mimir:9009 | 1 | 1 |
| windows | host.docker.internal:9182 | 1 | 1 |
| prometheus | localhost:9090 | 1 | 1 |

Mimir 조회는 `X-Scope-OrgID: lab`과 `/prometheus/api/v1/query`를 사용했다. 정상 수집·전송·조회 경로의 근거이며, 전체 샘플의 무손실 전송을 증명하지는 않는다.

Prometheus 로그를 `--since 5m --tail 100`으로 제한해 오류 관련 문자열을 검색했을 때 출력이 없었다. 이는 해당 범위에서 일치 항목이 없다는 의미이며 과거 오류 전체의 해소를 단정하지 않는다.

## 한계와 후속 작업

- 주문 한 건의 98.01ms를 성능 기준선으로 사용하지 않는다. 반복 측정은 8-1에서 수행했다.
- `up=1`은 수집 성공을 뜻하며 주문 성공이나 SLO 충족을 대신하지 않는다.
- 컨테이너 공통 종료와 과거 out-of-order 로그의 원인은 미확정이다.
- 이 준비 점검에서 실시간 Slack 알림 발송이나 장애 복구 자동화를 재검증하지 않았다.
- 실행 이미지 ID, 자원 사용량 및 현재 Git 커밋과 실행 이미지의 일치 여부는 이번 증거에 포함되지 않는다.
