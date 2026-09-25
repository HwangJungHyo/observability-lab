# 실험 016: Mimir・S3 저장소 기동 검증

기록일 2026-09-24. 사용자 제공 출력, 소스 f90bcc353c9b8dc65f3042c6ff2a9de4e5e82cf0.
판정: 7-1 기동·S3 기본 API·인증·쿼리 준비 상태 확인 완료.

| 검증 | 사용자 출력 |
|---|---|
| 이미지 pull | 고정 digest의 Mimir 3.2.1, SeaweedFS 4.47, Python 3.12.14-alpine 성공 |
| Mimir 설정 | -modules 목록 출력, 설정 검사 통과 |
| 버킷 | signed bucket HEAD PASS |
| S3 기능 | signed PUT/GET/LIST PASS |
| 인증 | unsigned GET denied PASS |
| 정리 | DELETE and missing object confirmed PASS |
| 준비 상태 | Mimir /ready PASS |
| 조회 | tenant lab query vector(1) PASS |
| Mimir 자원 제한 | Memory=4294967296, NanoCPUs=2000000000 |
| SeaweedFS 자원 제한 | Memory=2147483648, NanoCPUs=1000000000 |
| 포트 | Mimir 127.0.0.1:9009→9009, 저장소 포트는 호스트 publish 없음 |

SeaweedFS docker ps에 표시된 8333/tcp 등은 이미지의 노출 포트 정보다.
호스트 주소→컨테이너 포트 매핑이 없으므로 해당 출력은 Windows 외부 공개의 증거가 아니다.

7-1은 성공했지만 remote_write는 당시 비활성이다.
vector(1)은 상수 쿼리이므로 실제 메트릭 수신이나 S3 블록 저장 증거가 아니다.
S3 프로브가 확인한 것은 임시 객체의 CRUD와 무인증 읽기 거부다.
7-2에서 실제 메트릭 전송을 확인하고, 블록 업로드·재전송·보존은 후속 실험으로 남긴다.
