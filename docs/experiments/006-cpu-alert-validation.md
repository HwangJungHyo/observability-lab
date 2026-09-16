# 006. CPU 부하 알림 발생·복구 검증

## 결과
WindowsCpuHighLab의 Pending → Firing 전환을 Prometheus 화면에서 확인했다.
Slack의 FIRING·RESOLVED 메시지는 사용자 캡처로 확인했고, 이메일의 양쪽 메시지 수신은 사용자 확인을 근거로 기록한다.

## 조건과 근거
- CPU idle counter의 1분 rate를 instance, job, environment별로 평균하여 사용률 계산
- CPU 사용률 > 15%, for: 1m, up{job="windows"} == 1
- purpose=lab, severity=warning
- 과거 실험에서 평상시 약 3%, 부하 시 약 20%를 관측하여 동작 검증용 15%를 선택
- 안내한 부하 절차: Windows PowerShell 작업 4개, 각 180초
- 이번 실행의 작업 종료 로그는 제공되지 않았으므로 실행 시간을 실측 확정하지 않음
- 15%는 서비스 성능 저하와 연계해 도출한 운영 임계값이 아님

## 증거
| 증거 | 확인 내용 |
|---|---|
| promtool 사용자 출력 | windows-cpu.yml과 windows.yml 각각 1개 규칙 검사 성공 |
| 최초 Alerts 화면 | 두 알림 Inactive |
| Pending 화면 | CPU 평가값 약 21.41%, WindowsExporterDown Inactive |
| Firing 화면 | CPU 평가값 약 23.67%, Active Since 약 2분 23초 |
| Slack 캡처 | [FIRING] WindowsCpuHighLab, 메시지 평가값 20.3%, 표시 시각 오후 4:11 |
| 동일 Slack 캡처 | [RESOLVED] WindowsCpuHighLab |
| 사용자 확인 | Slack과 이메일 모두 장애·복구 수신 |

각 수치는 서로 다른 평가·캡처 시점의 값이며 최대 사용률 측정값이 아니다.
Active Since에는 Pending 시간이 포함된다.
Slack 복구 메시지의 별도 시각과 정확한 부하 시작·종료 시각은 확인되지 않았다.
캡처 원본은 이 문서에 첨부하지 않았고 관측 내용을 전사했다.

## 발견한 메시지 결함
CPU 복구 메시지 본문이 "Windows 메트릭 수집이 복구되었습니다."로 출력됐다.
이는 수집 중단 알림용 고정 문구가 남아 있는 문제다. CPU 알림의 복구를 수집 복구로 표현하면 오해를 만든다.

Slack 템플릿의 resolved 분기를 다음과 같은 공통 문구로 변경한다.

```text
*내용:* {{ .Labels.alertname }} 알림 조건이 해제되었습니다. 대상 상태를 확인하세요.
```

문구 수정과 재검증은 아직 미완료다.
RESOLVED는 규칙이 해제됐다는 뜻이며, 그 자체로 CPU가 최초 기준값까지 복귀했다는 증거는 아니다.
특히 이 규칙은 up==1 조건을 포함하므로 수집 실패·시계열 소실에 따른 조건 해제도 별도로 구분해야 한다.

## 임계값 주변 반복 전환(플래핑)
for는 조건이 잠깐 참이 되는 경우 발동을 늦춘다.
하지만 발동 이후 잠깐 조건이 거짓이 되는 경우의 즉시 해제까지 방지하지는 않는다.

후속 검토 옵션:
- keep_firing_for: 2m: 조건이 해제된 뒤에도 일정 시간 Firing을 유지해 짧은 하락을 흡수한다.
  정상 복구 통보도 지연되며, 데이터 소실을 실제 복구로 해석하지 않도록 up을 함께 확인한다.
- 평균 계산 구간 확대: 급등락을 완화하지만 감지·복구도 늦어진다.
- 발생·해제 임계값 분리: 예를 들어 발생 80%, 해제 70%의 이력 기반 제어.
  별도 상태 유지 로직이 필요하며 단순 for 옵션과 다르다.
- repeat_interval은 같은 활성 알림의 반복 통지 간격이다. Firing/Resolved 전환 자체의 제어와 다르다.

이번 실험에는 keep_firing_for를 적용하지 않았다.
참고: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/

## 소스 및 정리 상태
보고서 작성 시 원격 lab/003-alerting의 prometheus/rules/windows-cpu.yml은 없었다.
로컬 규칙 소스 push와 낮은 임계값의 실습 규칙 비활성화가 필요하다.
비활성화는 파일을 rules/*.yml 검색 범위 밖의 예제 폴더로 옮긴 후 검사·재로드하는 방식으로 수행한다.
기존 WindowsExporterDown은 유지한다.

다음 단계는 주문 API 계측, 오픈 요건 정의, 부하 시험을 통해 근거 있는 초기 운영 임계값을 도출하는 것이다.

## 관련 기록
- [005. Slack·Gmail 알림 검증](005-slack-gmail-notification.md)
