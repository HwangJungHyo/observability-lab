# 실험 009 — Docker 로그 수집과 Loki 조회
## 범위
5-1 Alloy → Loki → Grafana에서 주문·결제 접근 로그 조회.
브랜치 lab/005-logging, 구성 커밋 cf3275d.
2026-09-18 대화에서 제공한 Grafana 캡처를 근거로 한다. 원본 이미지 파일은 포함하지 않았다.
## 확인
- 주문 service_name=order-api, POST /orders, HTTP201 로그 2건.
- 결제 service_name=payment, POST /payments, HTTP200 로그 2건.
- 공통 라벨 environment=lab, job=order-lab-logs 확인.
- 과거 로그가 초기 수집될 수 있으므로 수집 지연·과거 로그 완전성은 이 캡처만으로 판정하지 않는다.
- request_id가 없으므로 시각이 같다는 이유만으로 두 서비스 로그의 동일 요청 관계를 확정하지 않는다.
## 문제와 조치
Prometheus 데이터 소스에 LogQL을 입력해 unexpected character '|' 발생.
Explore에서 Loki를 선택한 뒤 조회 성공.
Grafana datasource URL http://loki:3100은 Docker 내부 주소다.
Windows 직접 점검은 http://localhost:3100/ready, 로그 조회 UI는 Grafana다.
## 해석
UNK는 unknown 로그 레벨이며 결제 오류를 의미하지 않는다.
화면 14:33:36.628과 로그 본문 05:33:36의 차이는 UTC와 KST 표시 차이에 부합한다.
Grafana 표시 시각과 애플리케이션 본문 시각은 출처·정밀도가 다르므로 수집 지연으로 단정하지 않는다.
로그 앞 172.18.0.6은 결제 서버가 본 클라이언트 주소이며 최종 사용자 공인 IP가 아니다.
## 판정
5-1 양쪽 서비스 로그 조회 완료.
5-2에서 명시적인 level·UTC timestamp·request_id·처리시간·오류분류를 JSON으로 추가한다.
