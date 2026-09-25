# 7-7. Mimir 7일 보존 만료에 따른 블록 삭제 검증

- 실습일: 2026-09-25 (KST)
- 브랜치: `lab/007-mimir`
- 권장 기록 경로: `docs/evidence/007-mimir/7-7-retention-result.md`
- 판정: **7일 보존 만료 판정 및 테스트 블록의 주요 S3 객체 제거 확인**
- 후속 작업: **임시 설정 복원 및 실행 설정 확인 대기**

## 1. 목적과 검증 범위

블록을 오늘 생성·업로드하더라도 블록 안의 데이터가 7일 보존 기간을 초과하면 Compactor가 삭제 대상으로 판정하는지 확인한다. 삭제 표시 생성과 실제 S3 객체 제거를 별도로 검증한다.

기존 실습의 병합 원본 블록 삭제와 달리, 이번 삭제 사유는 **보존 기간 초과**다. 실제 7일 보존 정책은 유지했으며, 대기 시간을 줄이기 위해 삭제 표시 후 유예와 정리 주기만 임시 단축했다.

## 2. 환경과 대상

| 항목 | 값 |
|---|---|
| Mimir | 3.2.1, 단일 프로세스 실습 환경 |
| 객체 저장소 | SeaweedFS의 S3 호환 API |
| 버킷 | `mimir-lab` |
| 테스트 테넌트 | `retention-7d-d330b735` |
| 블록 ID | `01M3CEKGHCAVMYZCFNKQH3WAJH` |
| S3 블록 접두사 | `blocks/retention-7d-d330b735/01M3CEKGHCAVMYZCFNKQH3WAJH/` |
| 데이터 시각 | 2026-09-17 13:39:00~13:41:00 UTC |
| 블록 minTime | `1789652340000` |
| 블록 maxTime | `1789652460001` (배타적 상한) |
| 블록 내용 | 시계열 1개, 청크 1개, 샘플 3개 |

## 3. 실행 조건

| 설정 | 원래 값 | 삭제 가속 테스트 값 |
|---|---|---|
| `limits.compactor_blocks_retention_period` | `168h` (`1w`) | 유지 |
| `compactor.cleanup_interval` | `15m` | `1m` |
| `compactor.deletion_delay` | `12h` | `1m` |

수정 파일은 `mimir/mimir.yaml`이다. 기존 `compactor:` 하위에 다음 두 항목을 추가한 뒤 Mimir를 재시작했다.

```yaml
compactor:
  cleanup_interval: 1m
  deletion_delay: 1m
```

기존 compactor 하위 설정은 유지했다. 이 설정은 전역 적용되므로 기존 `lab` 테넌트의 삭제 표시된 블록도 조기 삭제 대상이 될 수 있다. 이번 증거 수집은 테스트 블록에 한정하며, 다른 블록에 대한 영향은 전수 검증하지 않았다.

실제 `/config` 출력:

```text
compactor_blocks_retention_period: 1w
cleanup_interval: 1m0s
deletion_delay: 1m0s
```

## 4. 절차와 관측 결과

### 4.1 과거 샘플 수신 및 Head 확인

전용 테넌트에 약 8일 전 시각의 샘플 3개를 OTLP로 전송했다.

```text
HTTP: 200
Response: {}
```

응답에 부분 거부 보고는 없었다. Ingester TSDB 화면에서 시계열 1개와 지정한 데이터 시간 범위를 확인했다. 이 시점에는 Blocks 표가 비어 있었다.

### 4.2 해당 테넌트만 flush

```bash
curl -sS --max-time 120 \
  -X POST \
  -w '\nHTTP: %{http_code}\n' \
  'http://localhost:9009/ingester/flush?tenant=retention-7d-d330b735&wait=true'
```

HTTP 상태만으로 완료를 판단하지 않고, TSDB 화면과 다음 로그로 블록 생성·업로드를 확인했다.

```text
2026-09-25T14:13:13.44365182Z
msg="write block completed" ulid=01M3CEKGHCAVMYZCFNKQH3WAJH

2026-09-25T14:13:13.452033108Z
msg="finished uploading new block to long-term storage" block=01M3CEKGHCAVMYZCFNKQH3WAJH
```

생성된 블록은 시계열 1개, 청크 1개, 샘플 3개를 포함했고 Uploaded 시각이 표시됐다.

### 4.3 보존 만료 판정 확인

23:22 KST에는 주요 객체 3개가 HTTP 200이었고 삭제 표시 두 경로는 HTTP 404였다.

23:29:41 KST에 다음 로그가 기록됐다.

```text
msg="applied retention: marking block for deletion"
block=01M3CEKGHCAVMYZCFNKQH3WAJH maxTime=1789652460001

msg="block has been marked for deletion"
block=01M3CEKGHCAVMYZCFNKQH3WAJH

msg="marked blocks for deletion" num_blocks=1 retention=168h0m0s
```

23:35:11 KST에 다음 두 경로에서 동일한 삭제 표시를 HTTP 200으로 읽었다.

```text
blocks/retention-7d-d330b735/01M3CEKGHCAVMYZCFNKQH3WAJH/deletion-mark.json
blocks/retention-7d-d330b735/markers/01M3CEKGHCAVMYZCFNKQH3WAJH-deletion-mark.json
```

```json
{
  "id": "01M3CEKGHCAVMYZCFNKQH3WAJH",
  "version": 1,
  "details": "block exceeding retention of 168h0m0s",
  "deletion_time": 1790346581
}
```

이 시점에는 `meta.json`, `index`, `chunks/000001` 모두 HTTP 200이었다. 따라서 삭제 표시 생성과 실제 객체 제거는 별도 단계임을 확인했다.

### 4.4 유예 단축 후 실제 삭제

설정을 1분으로 단축하고 재시작한 뒤, 시작 시 정리 작업에서 삭제 로그가 기록됐다.

```text
2026-09-25T14:40:30.649841673Z
component=cleaner task=clean_up_users_during_startup
user=retention-7d-d330b735
msg="deleted block marked for deletion"
block=01M3CEKGHCAVMYZCFNKQH3WAJH
```

이후 `deleted bucket index for tenant with no blocks remaining` 로그가 이어졌다. 재시작 후에도 기존 삭제 표시를 사용했으며, 새로 12시간을 기다리지 않았다.

23:41 및 23:42 KST에는 같은 ID에 대해 `skipped partial block when updating bucket index`와 `cleaned up partial blocks`가 관측됐다. 잔여 항목의 발생 원인은 이 기록만으로 확정하지 않는다.

23:53:33 KST에는 Store-gateway의 다음 로그가 기록됐다.

```text
msg="closed bucket store for user" user=retention-7d-d330b735
msg="deleted user sync directory" dir=/data/tsdb-sync/retention-7d-d330b735
```

23:54:00 KST에 서명된 S3 HEAD로 주요 객체 제거를 확인했다.

```text
HTTP 404: blocks/retention-7d-d330b735/01M3CEKGHCAVMYZCFNKQH3WAJH/meta.json
HTTP 404: blocks/retention-7d-d330b735/01M3CEKGHCAVMYZCFNKQH3WAJH/index
HTTP 404: blocks/retention-7d-d330b735/01M3CEKGHCAVMYZCFNKQH3WAJH/chunks/000001
```

## 5. 시간표

모든 시각은 2026-09-25 KST다.

| 시각 | 사건 |
|---|---|
| 23:13:13 | 테스트 블록 생성 및 S3 업로드 |
| 23:13:52 | cleaner가 새 블록 1개 발견 |
| 23:22:25 | 주요 객체 존재, 삭제 표시 없음 |
| 23:29:41 | 7일 보존 만료로 삭제 표시 생성 |
| 23:35:11 | 삭제 표시 내용과 원본 객체 공존 확인 |
| 23:40:30 | 단축 설정으로 재시작 후 블록 삭제 로그 |
| 23:53:33 | Store-gateway의 해당 테넌트 조회 저장소·동기화 디렉터리 정리 |
| 23:54:00 | 주요 S3 객체 3개의 HTTP 404 확인 |

원래 12시간 유예를 유지했다면 유예 종료 기준은 2026-09-26 11:29:41 KST였다. 이번 실습은 유예를 단축했으므로 원래 12시간 대기 동작을 끝까지 검증한 결과로 기록하지 않는다.

## 6. 판정과 한계

- [x] 7일 보존 정책을 유지했다.
- [x] 약 8일 전 샘플 3개가 블록에 포함됐음을 확인했다.
- [x] Compactor 로그와 삭제 표시의 사유로 보존 만료 판정을 확인했다.
- [x] 삭제 표시 후 원본 객체가 일시적으로 유지됨을 확인했다.
- [x] 삭제 로그와 주요 객체 3개의 HTTP 404를 교차 확인했다.
- [ ] 원래 설정으로 복원하고 `/config`에서 확인한다.

검증하지 않은 범위:

- 원래 `12h` 유예를 실제로 모두 기다린 삭제 동작
- 7일 경계 직전·직후의 정밀한 경계값 테스트
- 해당 접두사의 모든 객체가 없어졌는지에 대한 최종 LIST 전수 확인
- Ingester 로컬 블록 제거 및 물리 디스크 공간 회수
- 삭제 후 과거 데이터 쿼리 결과
- 전역 설정 단축에 따른 다른 테넌트의 모든 영향

결론: **7일 보존 만료 판정과, 삭제 유예를 1분으로 단축한 조건에서의 테스트 블록 주요 객체 제거를 검증했다.**

## 7. 설정 복원 절차 (실행 결과 확인 대기)

`mimir/mimir.yaml`에서 이번에 추가한 `cleanup_interval: 1m`과 `deletion_delay: 1m` 두 줄만 제거한다. 다른 compactor 설정과 보존 기간은 유지한다.

```bash
bash scripts/mimir-compose.sh restart mimir
```

Mimir HTTP 서버가 준비되면 적용값을 확인한다.

```bash
curl -fsS --max-time 10 http://localhost:9009/config \
  | grep -E '^[[:space:]]*(compactor_blocks_retention_period|cleanup_interval|deletion_delay):'
```

복원 기대값 (아직 실제 확인 결과가 아님):

```text
compactor_blocks_retention_period: 1w
cleanup_interval: 15m0s
deletion_delay: 12h0m0s
```

복원 후 설정 차이를 검토한다.

```bash
git diff -- mimir/mimir.yaml
```

복원 확인 시 위 체크리스트와 이 절의 상태를 실제 결과에 맞게 갱신한다.

