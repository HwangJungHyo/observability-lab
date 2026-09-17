# 001. 잘못된 수집 대상 주소로 인한 수집 실패

## 목적
서비스의 실행 상태와 Prometheus의 메트릭 수집 성공 여부를 구분한다.

## 변경 전 상태
- 기존 prometheus 대상의 up=1 확인.

## 변경 내용
- job_name: scrape-failure-lab
- target: localhost:19090
- 기존 localhost:9090 대상 유지.
- promtool 검사 후 SIGHUP으로 설정 적용.

## 확인된 결과
- up{instance="localhost:9090",job="prometheus"} = 1
- up{instance="localhost:19090",job="scrape-failure-lab"} = 0
- Targets 실제 오류: [복사한 문구 입력]
- 실험 시각 및 시간대: [입력]

## 원복
- HEAD의 prometheus.yml로 복원.
- promtool 검사 후 SIGHUP으로 설정 적용.
- 실험 대상이 Targets에서 제거됨: [확인 후 작성]
- 기존 대상의 up=1 유지: [확인 후 작성]
- prometheus.yml의 Git diff 없음: [확인 후 작성]

## 운영 관점의 해석
- 기존 수집을 유지하면서 별도 대상의 수집 실패를 재현했다.
- up=0은 수집 실패를 나타내며, 대상 프로세스 중단을 단독으로 증명하지 않는다.
- 대상 주소와 Targets의 실제 오류를 함께 확인해야 한다.
