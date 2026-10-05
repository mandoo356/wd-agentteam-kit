' 슬랙 서버가 계속 안 뜰 때 supervisor.ps1 이 한 번 띄우는 안내 창.
' ? 이 파일은 ANSI(CP949) 로 저장한다 ? wscript 는 UTF-8 BOM 을 읽지 못한다.
msg = "슬랙 서버가 떴다가 바로 꺼지는 일이 반복되고 있습니다." & vbCrLf & vbCrLf & _
      "거의 모든 경우 원인은 슬랙 열쇠 3개입니다." & vbCrLf & _
      "스타터킷 폴더의 [환경점검.bat] 을 다시 누르고" & vbCrLf & _
      "열쇠 3개(xoxb- / xapp- / 내 슬랙 아이디)를 확인해 주세요." & vbCrLf & vbCrLf & _
      "자세한 내용: slack-server\logs\서버가_안뜹니다.txt"
MsgBox msg, 48, "위드드림 에이전트팀 - 슬랙 서버"