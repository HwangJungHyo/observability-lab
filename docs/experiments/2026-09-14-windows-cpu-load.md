# Windows CPU 부하 및 메트릭 수집 검증

## 목적과 판정

Windows에서 실제 CPU 부하를 발생시켜 windows_exporter → Prometheus → Grafana 경로에서 사용률 상승과 종료 후 하락을 확인한다. 부하 중 수집 성공 여부도 함께 확인한다.

**판정: 부하 반영과 종료 후 하락 확인. 표시된 그래프에서 수집 실패·공백은 관찰되지 않음. 부하 전 수준으로의 완전 복귀는 미확인.**

이 보고서는 사용자가 제공한 실행 로그와 Grafana 캡처를 근거로 작성했다. CPU 수치는 그래프를 육안으로 읽은 근삿값이며 원시 시계열을 내려받아 산출한 통계가 아니다.

## 환경과 실험 조건

| 항목 | 값 |
|---|---|
| 실험일 | 2026-09-14 |
| 시간대 | KST, UTC+09:00 |
| 환경 | Windows + Git Bash + Docker Desktop |
| 저장소 브랜치 | lab/002-windows-metrics |
| 수집 대상 | host.docker.internal:9182 |
| job / environment | windows / lab |
| Prometheus 수집 주기 | 15초 |
| 논리 프로세서 조회 결과 | 24 |
| 부하 작업 수 | 4 |
| 작업별 실행 시간 | 약 90초 |
| 관측 쿼리 | CPU idle counter의 1분 rate 기반 사용률, up |
| 이미지 버전 | Compose는 latest 사용. 실험 시 실행 버전·digest 별도 기록 없음 |

24는 스크립트의 `[Environment]::ProcessorCount` 조회 결과다. 물리 CPU 칩 24개 또는 물리 코어 24개를 의미하지 않는다. CPU 모델, 소켓 수, 물리 코어 수는 이번 증거로 확인하지 않았다.

작업 수는 논리 프로세서 수의 절반을 기준으로 최소 1개, 최대 4개로 제한했다. 이번 환경에서는 4개가 선택됐다. 4/24 ≈ 16.7%는 각 작업이 논리 프로세서 하나를 계속 사용한다고 가정한 단순 참고치이며, 정확한 예상 사용률이나 합격 기준이 아니다.

## 재현 절차

1. Grafana Explore에서 Prometheus 데이터 소스를 선택한다.
2. 아래 CPU 쿼리를 Range로 실행하고, 부하 전 약 2분의 기준값을 관찰한다.
3. Windows Git Bash에서 부하 명령을 실행한다. CPU를 관측하는 Windows 호스트에서 실행해야 한다.
4. 실행 중 15~30초마다 쿼리를 새로고침한다.
5. 모든 작업의 Completed 상태와 START/END 시각을 확인한다.
6. 실행 시각 전후를 포함하는 절대 시간 범위로 CPU와 up을 비교한다. 이번 실험의 권장 조회 범위는 08:54~09:05 KST다. 실제 제출 캡처는 약 08:48~09:02 구간을 표시했다.
7. 종료 후 기준 수준으로의 복귀 여부와 수집 상태를 기록한다.

### CPU 사용률

```promql
100 * (
  1 - avg by (instance) (
    rate(windows_cpu_time_total{job="windows",mode="idle"}[1m])
  )
)
```

기존 대시보드의 5분 쿼리는 유지하고 Explore에서 1분 쿼리를 사용했다. 1분 구간에도 이전 샘플이 포함되므로 작업 시작·종료와 그래프 변화 시점이 정확히 일치할 필요는 없다.

### 수집 성공 여부

```promql
up{job="windows"}
```

up=1은 해당 수집 성공을 의미한다. Windows의 모든 기능이나 애플리케이션 정상 여부를 보장하지 않는다. 화면에서 선이 연속이라는 사실만으로 모든 원본 샘플의 무결성까지 입증한 것은 아니다.

### 실행 명령: Windows Git Bash

```bash
powershell.exe -NoProfile -Command '
$ErrorActionPreference = "Stop"

$duration = 90
$logical = [Environment]::ProcessorCount
$workers = [int][Math]::Max(1, [Math]::Min(4, [Math]::Floor($logical / 2)))
$jobs = @()

Write-Output ("Logical CPUs={0}, Workers={1}, Duration={2}s" -f $logical, $workers, $duration)

try {
    for ($n = 1; $n -le $workers; $n++) {
        $jobs += Start-Job -ArgumentList $duration, $n -ScriptBlock {
            param($seconds, $worker)

            Write-Output ("START worker={0} time={1}" -f $worker, (Get-Date -Format o))
            $clock = [Diagnostics.Stopwatch]::StartNew()

            while ($clock.Elapsed.TotalSeconds -lt $seconds) {
                for ($i = 1; $i -le 10000; $i++) {
                    $null = [Math]::Sqrt($i)
                }
            }

            Write-Output ("END worker={0} time={1}" -f $worker, (Get-Date -Format o))
        }
    }

    $jobs | Wait-Job -Timeout 120 | Out-Null
    $jobs | Select-Object Id, State | Format-Table -AutoSize
    $jobs | Receive-Job
}
finally {
    if ($jobs.Count -gt 0) {
        $jobs | Stop-Job
        $jobs | Remove-Job
    }
    Write-Output ("CLEANUP time={0}" -f (Get-Date -Format o))
}
'
```

작업마다 실행 시간을 제한하며, finally에서 이번 실행으로 생성한 작업만 정리한다. 작업 생성·대기 시간 때문에 명령 전체 실행 시간은 90초보다 길 수 있다.

## 실행 증거

사용자가 제공한 출력에서 Markdown 표시를 정리한 로그:

```text
Logical CPUs=24, Workers=4, Duration=90s

Id State
1  Completed
3  Completed
5  Completed
7  Completed

START worker=1 time=2026-09-14T08:57:08.5509140+09:00
END worker=1 time=2026-09-14T08:58:38.5542670+09:00
START worker=2 time=2026-09-14T08:57:08.6531535+09:00
END worker=2 time=2026-09-14T08:58:38.6602776+09:00
START worker=3 time=2026-09-14T08:57:08.7592956+09:00
END worker=3 time=2026-09-14T08:58:38.7650472+09:00
START worker=4 time=2026-09-14T08:57:08.8627138+09:00
END worker=4 time=2026-09-14T08:58:38.8744901+09:00
CLEANUP time=2026-09-14T08:58:38.9594487+09:00
```

## 관측 결과

| 검증 항목 | 관측 결과 | 판정 |
|---|---|---|
| 부하 작업 | 4개 모두 Completed, 각 약 90초 | 완료 |
| 부하 전 CPU | 약 2.5~4%, 대표값 약 3% | 기준값 확인 |
| 부하 중 CPU | 08:57~08:59 부근 두 번째 봉우리에서 약 19~20% | 부하 반영 확인 |
| 부하 종료 후 CPU | 약 5~8%로 하락 | 하락 확인 |
| 기준 수준 복귀 | 관측 종료 시 부하 전보다 높은 수준 | 완전 복귀 미확인 |
| Windows up | 표시 구간에서 노란 선이 1로 유지 | 화면상 실패·공백 미관찰 |

두 번째 봉우리는 실행 로그 시간대와 대체로 일치한다. 그래프의 약 08:54 부근 첫 번째 봉우리는 이 실행 로그와 시간이 다르며, 원인을 확인하지 않았으므로 이번 실행의 결과로 포함하지 않았다.

사용자 제공 Grafana 캡처를 판독했으나 캡처 원본과 원시 시계열은 이 문서에 포함하지 않았다. 따라서 최대값, 전체 샘플 수, 수집 성공률을 정밀 계산한 결과로 해석하지 않는다.

## 해석과 한계

- 실제 호스트 부하가 CPU 메트릭에 반영되는 것을 확인했다.
- 작업 종료 후 사용률이 뚜렷하게 하락했다.
- 부하 중에도 표시된 up 그래프는 1을 유지했다.
- 종료 후 약 5~8%인 이유는 확인하지 않았다. 다른 프로그램의 활동 등은 가능성일 뿐 원인으로 확정하지 않았다.
- 프로세스별 CPU, 메모리·디스크 부하, 애플리케이션 응답 시간, 알림 발송은 검증 범위에 포함하지 않았다.
- 이 실험은 모니터링 경로 검증이며 서버 최대 처리량이나 서비스 성능을 측정한 벤치마크가 아니다.

## 정리 및 후속 과제

실행 로그에서 작업 4개의 Completed와 CLEANUP 출력을 확인했다. 이 실험을 위해 영구적인 수집 설정이나 대시보드 JSON을 변경하지 않았고, Explore에서 조회했다.

후속 확인:
- CPU가 계속 기준값보다 높으면 작업 관리자에서 CPU 사용량순으로 정렬해 프로세스를 확인한다.
- 같은 시간대의 1분·5분 쿼리를 비교해 평균 구간의 영향을 확인한다.
- 다음 알림 실습에서는 실험용 임계값·지속 시간과 운영 기준을 구분하고 발생·해제까지 검증한다.

## 관련 문서

- [환경 구성과 재현 절차](../../README.md)
