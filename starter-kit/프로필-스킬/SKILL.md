---
name: instructor-profile
description: |
  강사 개인 브랜딩 프로필 덱을 HTML 슬라이드(1920×1080)로 생성하는 범용 스킬.
  workspace/memory/facts.md 의 브랜드 색 4개를 적용하며, 표지→강사소개→강의이력→언론보도→WHY→교육후기→교육현장→감사 구조를 내장한다.
  '강사 프로필 만들어줘', '프로필 덱', '강사 소개서', '강사 프로필 슬라이드', '프로필 자료',
  '강사 포트폴리오', '강사 소개 자료', '프로필 HTML', '강사 프로필 제작', '프로필 PPT',
  '강사 이력 자료', '강사 브로슈어' 등의 요청에 반드시 이 스킬을 사용할 것.
  특정 강사(본인 또는 협업 강사)의 경력·자격·레퍼런스를 소개하는 자료를 만들 때 적극 활용할 것.
version: 1.0
---

> **참고 자료 순서 (2026-09-14 확정)**
> 1순위 `C:/Agent/MyData/Profile` — 내가 실제로 쓴 프로필·이력서. 내용의 근거는 여기서만 나온다.
> 2순위 `workspace/memory/facts.md` — 회사 이름·로고 글자·색 4개.
> 이 문서의 슬라이드 골격은 **모양만** 정한다. 골격 안의 `{{ }}` 는 반드시 내 자료로 바꾼다.
> 근거가 없으면 지어내지 말고 그 줄을 통째로 뺀다. 남의 실적·고객사를 남겨 두지 않는다.

# 강사 프로필 덱 스킬 (범용)

강사 1인의 개인 브랜딩 프로필을 **HTML 슬라이드(1920×1080px, 16:9)** 로 생성한다.

> 이 스킬은 **강사 소개 전용**이다. 교육 과정·커리큘럼·견적을 제안하는 문서는
> 제안서 스킬(P4)을 사용한다. 두 스킬을 섞지 않는다.

---

## 0. 워크플로우 (순서 고정, 생략 금지)

```
# STEP 0. 내 자료 먼저 — C:/Agent/MyData/Profile 폴더를 먼저 훑는다. (1순위)
#         거기 있는 내 프로필·이력서가 이름·경력·자격·실적의 **유일한 출처**다.
#         이 문서 §4 의 슬라이드 골격은 '화면 모양'만 정한다. 거기 적힌 문구는 예시가 아니라
#         빈칸({{ }})이며, MyData 에 근거가 없는 항목은 채우지 말고 그 줄을 뺀다.

# STEP 1. 입력 수집 — §2 입력 스키마의 필수 항목을 확인한다.
#         빠진 항목은 추정하지 말고 사용자에게 묻는다. (§3-1)
#         workspace/memory/facts.md 를 읽어 회사 이름·로고 글자·색 4개를 가져온다.

# STEP 2. HTML 작성 — §4 슬라이드 골격 + references/full_css.md
#         저장 경로: workspace/결과물/<날짜>_<강사명>_프로필.html

# STEP 3. QA 게이트 ① 자동 검사 — PASS 전 완료 선언 금지
py -3 .claude/skills/프로필/scripts/validate.py workspace/결과물/<파일명>.html

# STEP 4. QA 게이트 ② 육안 검사 — 전 슬라이드 캡처 후 직접 확인 (필수)
py -3 .claude/skills/프로필/scripts/qa_screenshot.py workspace/결과물/<파일명>.html

# STEP 5. 전달 — 파일 경로와 슬라이드 장수를 사용자에게 보고한다.
```

**산출 형식은 HTML만**이다. PDF는 사용자가 브라우저에서 `Ctrl+P → PDF로 저장`으로 직접 만든다.

---

## 1. 절대 금지 (위반 시 결과물 무효)

1. ❌ **슬라이드 크기 변경** — 전 슬라이드 1920×1080px 고정.
2. ❌ **경력·자격·고객사·수치 창작** — 제공된 정보만 사용. 부족하면 §3-1대로 확인한다.
   특히 강의 횟수·만족도 점수·연차는 **절대 추정하지 않는다.**
3. ❌ **서양인 스톡 사진 사용.** 사진 미제공 시 `full_css.md`의 플레이스홀더 규칙을 따른다.
4. ❌ **`facts.md` 에 없는 임의 색상 사용.**
5. ❌ **고객사 로고를 외부 URL로 직접 링크** — 이미지가 없으면 텍스트 타일(`<span>사명</span>`)로 대체한다.
6. ❌ **전체 HTML 재생성으로 부분 수정** — 이미 만든 파일을 고칠 때는 필요한 부분만 바꾼다.
7. ❌ **QA 게이트(STEP 3·4) 생략 후 완료 선언.**
8. ❌ **제3자 교육업체명 언급.**

---

## 2. 입력 스키마 (변수)

프로필 덱은 아래 변수로 완전히 결정된다. `[]`는 필수, `()`는 선택.
`instructor_name`을 제외한 대부분은 **workspace/memory/facts.md 에 이미 있는 값을 우선** 쓴다.

| 키 | 필수 | 설명 | 예 |
|---|---|---|---|
| `instructor_name` | ● | 강사명 | (내 이름) |
| `catchphrase` | ● | 한 줄 캐치프레이즈(연차 포함) | {{내 캐치프레이즈 — MyData/Profile 에서 뽑는다}} |
| `cover_lead` | ● | 표지 슬로건 | 여러분의 성장을 함께합니다 |
| `cover_tag` | ● | 표지 태그라인 | 기업과 교육생 모두의 성장을 위한 실전 중심 교육 솔루션을 제공합니다 |
| `career` | ● | 경력 리스트. `현)`/`전)` 접두 | 현) {{내 소속}} {{직함}} |
| `certs` | ● | 자격 리스트 (2열 배치, 8~14개 권장) | 이미지 컨설턴트 1급 |
| `refs.corp` | ● | 기업 교육 레퍼런스 (쉼표 나열) | |
| `refs.public` | ○ | 공공기관 교육 레퍼런스 | |
| `refs.edu` | ○ | 교육기관 교육 레퍼런스 | |
| `top_logos` | ○ | 대표 고객사 3~5곳 (로고 타일, 이미지 없으면 텍스트) | |
| `press` | ○ | 언론 보도 4건 (스크린샷 + 캡션) | |
| `why` | ● | 선택 이유 3개 (수식어 / 키워드 / 근거배지 2개) | |
| `reviews` | ○ | 후기 3건 (업종 라벨 + 본문) | |
| `field_photos` | ○ | 현장 사진 (8장 = 1슬라이드) | |
| `stat_line` | ● | 실적 한 줄 | (내 실적 한 줄. 없으면 비워 둔다) |
| `contact` | ● | 이메일 · 휴대폰 | |

`certs`는 홀수 개면 좌열이 1개 더 오도록 배치한다.

---

## 3. 콘텐츠 규칙

### 3-1. 정보가 부족할 때
멈추고 **한 번에 모아서** 묻는다. 항목을 하나씩 순차 질문하지 않는다.
필수 항목 중 무엇이 비었는지 목록으로 제시하고, 선택 슬라이드는 "제외하고 진행 가능"임을 함께 알린다.

### 3-2. 문체
- 명사형 종결 중심. 경력·자격은 완전문장으로 늘리지 않는다.
- 근거 없는 형용사 대신 **수치**로 표현한다. ("경험 풍부" → "누적 ○○회" — 숫자는 MyData 의 내 자료에서만 가져온다)
- 금지 표현: 정말/아주/굉장히, ~인 것 같습니다, ~하게 됩니다, 확 달라집니다.
- 표지 슬로건·후기 리드·현장 서브카피는 **감성 문체 허용**(손글씨 느낌 구간). 그 외 본문은 HRD 문서 문체를 유지한다.

### 3-3. 이미지 처리
- 사용자 제공 이미지는 **base64 인라인** 또는 로컬 복사 후 상대경로. 외부 핫링크 금지.
- 인물 사진은 **누끼(배경 투명 PNG) 우선**. 배경이 있으면 얼굴 중심으로 크롭한다.
- 고객사 로고가 없으면 `.logo-tile` 안에 `<span>사명</span>` 텍스트로 대체한다.
- 언론 보도 스크린샷은 세로 비율(기사 캡처). `object-position:top`으로 헤드라인이 보이게 한다.
- 현장 사진에 교육생 얼굴이 식별되면 **블러 처리 여부를 사용자에게 확인**한다.

### 3-4. 슬라이드 밀도
표지(`.p-cover`)·감사(`.p-thanks`)를 제외한 전 슬라이드는 세로 공간의 **85~90%**를 채운다.
여백이 남으면 글자만 키우지 말고 실제 정보를 추가한다.

---

## 4. 슬라이드 골격

| 순서 | 슬라이드 | 클래스 | 필수 | 비고 |
|---|---|---|---|---|
| 1 | 표지 | `.p-cover` | ● | 좌측 정렬, 로고 우상단 |
| 2 | 강사 소개 | `.p-intro` | ● | 좌 인물 / 우 경력·자격 2열 |
| 3 | 강의 이력 | `.p-history` | ● | 상단 로고 타일 + 3분류 나열 |
| 3 | 강의 분야 | `.p-domain` | ○ | 3열 카드. 분야별 주제 리스트 |
| 4 | 언론 보도 | `.p-press` | ○ | 4카드. 저서·포스터는 `.pr-shot.fit` |
| 5 | WHY | `.p-why` | ● | **유일한 밝은 배경** |
| 6 | 교육 후기 | `.p-review` | ○ | 폰 목업 3개 |
| 7~N | 교육 현장 | `.p-field` | ○ | 8장/슬라이드, 사진 수만큼 반복 |
| 끝 | 감사 | `.p-thanks` | ● | 연락처 캡슐 2개 |

- 선택 슬라이드를 빼도 **순서는 바꾸지 않는다.** 순서: cover → intro → domain → history → press → why → review → field → thanks
- `.p-history`는 레퍼런스 나열용이다. 항목이 짧아 세로가 비면 `.p-domain` 카드형을 쓴다.
- 인물 사진이 흰 배경 사진뿐이면 플러드필로 배경을 제거하고, 알파를 2~3px 침식해 흰 테두리를 없앤다.
- 슬라이드를 늘리거나 줄이면 `.page-num`을 전부 재부여한다 (표지 제외).
- `.p-field`는 사진 8장 단위로 자른다. 마지막 슬라이드가 4장 이하로 남으면
  앞 슬라이드와 합치지 말고 `grid-template-rows:1fr`로 1행 처리한다.

### 슬라이드별 마크업 골격

```html
<!-- 1. 표지 -->
<div class="slide p-cover">
  <div class="cv-logo"><span>[로고글자]</span></div>
  <div class="cv-body">
    <div class="cv-lead">여러분의 <span>성장</span>을 함께합니다.</div>
    <div class="cv-name">{{강사명}} 강사</div>
    <div class="cv-tag">기업과 교육생 모두의 성장을 위한 실전 중심 교육 솔루션을 제공합니다</div>
  </div>
  <div class="cv-rule"></div>
</div>

<!-- 2. 강사 소개 -->
<div class="slide p-intro">
  <div class="sec-head"><div class="sec-bar"></div><div class="sec-title">강사 소개</div></div>
  <div class="dots"><i></i><i></i><i></i></div>
  <div class="in-photo"><img src="..." alt="강사"></div>
  <div class="in-right">
    <div class="in-catch">{{캐치프레이즈 앞부분}} <span>{{캐치프레이즈 뒷부분}}</span></div>
    <div class="in-name">{{강사명}} 강사</div>
    <div class="in-cols">
      <div class="in-col">
        <span class="pill">강의 경력</span>
        <ul class="in-list">
          <li class="now">현) {{내 소속}} {{직함}}</li>
          <li>전) ○○전자 교육센터 선임 강사</li>
        </ul>
      </div>
      <div class="in-col">
        <span class="pill">자격 사항</span>
        <ul class="in-list in-cert">
          <li>- {{내 자격 1}}</li><li>- {{내 자격 2}}</li>
        </ul>
      </div>
    </div>
    <div class="in-logos">
      <div class="logo-tile"><span>{{고객사1}}</span></div>
      <div class="logo-tile"><span>{{고객사2}}</span></div>
      <div class="logo-tile"><span>{{고객사3}}</span></div>
    </div>
  </div>
  <div class="page-num">02</div><div class="brand-mark"><span>[로고글자]</span></div>
</div>

<!-- 3. 강의 이력 -->
<div class="slide p-history">
  <div class="sec-head"><div class="sec-bar"></div><div class="sec-title">강의 이력</div></div>
  <div class="dots"><i></i><i></i><i></i></div>
  <div class="hs-top">
    <div class="logo-tile"><span>{{고객사3}}</span></div><!-- 3~5개 -->
  </div>
  <div class="hs-body">
    <div class="hs-row"><span class="pill">기업 교육</span><div class="hs-text">A, B, C 그 외 다수</div></div>
    <div class="hs-row"><span class="pill">공공 기관 교육</span><div class="hs-text">…</div></div>
    <div class="hs-row"><span class="pill">교육 기관 교육</span><div class="hs-text">…</div></div>
  </div>
  <div class="page-num">03</div><div class="brand-mark"><span>[로고글자]</span></div>
</div>

<!-- 5. WHY -->
<div class="slide p-why">
  <div class="sec-head"><div class="sec-bar dark"></div><div class="sec-title dark">WHY</div></div>
  <div class="dots dark"><i></i><i></i><i></i></div>
  <div class="why-q">왜 {{강사명}} 강사를 선택해야 하는가?</div>
  <div class="why-grid">
    <div class="why-card">
      <div class="why-ico">🎓</div>
      <div class="why-pre">12년 강의 경력을 바탕으로 한</div>
      <div class="why-key">현장 강의 기반 <span>전문가</span></div>
    </div><!-- ×3 -->
  </div>
  <div class="why-badges">
    <div class="why-col">
      <div class="why-badge">누적 <strong>{{누적 강의 횟수}}</strong> 이상 강의</div>
      <div class="why-badge">다양한 산업군 출강</div>
    </div><!-- ×3 -->
  </div>
  <div class="page-num dark">05</div><div class="brand-mark"><span>[로고글자]</span></div>
</div>

<!-- 7. 교육 현장 -->
<div class="slide p-field">
  <div class="sec-head"><div class="sec-bar"></div><div class="sec-title">교육 현장</div></div>
  <div class="sec-sub">교육생의 <em>성장</em> 여정에 함께하는 강사, {{강사명}}입니다.</div>
  <div class="dots"><i></i><i></i><i></i></div>
  <div class="fd-grid">
    <div class="fd-cell"><img src="..."></div><!-- ×8 -->
  </div>
  <div class="fd-foot">{{실적 한 줄 — 모르면 이 줄을 통째로 뺀다}}</div>
  <div class="page-num">07</div>
</div>

<!-- 8. 감사 -->
<div class="slide p-thanks">
  <div class="tk-photo"><img src="..." alt="강사"></div>
  <div class="tk-right">
    <div class="tk-lead">오늘의 <em>선택</em>이 내일의 <em>성장</em>으로 이어지길 바랍니다.</div>
    <div class="tk-big">감사합니다</div>
    <div class="tk-chip">hong@example.com</div>
    <div class="tk-chip">010-0000-0000</div>
  </div>
  <div class="brand-mark"><span>[로고글자]</span></div>
</div>
```

---

## 5. 색·서체

색 4개(`--main` `--deep` `--accent` `--pale`)는 **`workspace/memory/facts.md` 값을 그대로 쓴다.**
새 색을 만들지 않는다 — 제안서(P4)·교재(P8)와 같은 값을 써야 오늘 만든 자료 전체가 한 회사처럼 보인다.

```css
:root{
  --main:#메인색; --deep:#진한색; --accent:#강조색; --pale:#옅은색;
  --f:"Noto Sans KR","Noto Sans Korean","Noto Sans CJK KR","NotoSansKR","Malgun Gothic","맑은 고딕",sans-serif;
}
```

- 딥 배경 그라데이션: `linear-gradient(135deg, var(--deep) 0%, var(--main) 100%)`
- 강조 하이라이트: `--accent` 하나만 쓴다 (표지 슬로건, WHY 키워드, 섹션 바 전부 동일 색)
- **WHY 슬라이드만 밝은 배경**이다. 이 대비가 덱의 리듬을 만든다. 다른 슬라이드를 밝게 바꾸지 않는다.

서체는 **"Noto Sans KR" 계열 하나만** 쓴다. 인터넷에서 폰트를 불러오지 않는다 —
강의장 와이파이 없이도 그대로 열려야 한다.

---

## 6. 참고 파일

| 파일 | 용도 |
|---|---|
| `references/full_css.md` | 전체 CSS (생성 전 전문 읽기) |
| `scripts/validate.py` | 자동 QA 게이트 |
| `scripts/qa_screenshot.py` | 전 슬라이드 캡처 (육안 QA) |
