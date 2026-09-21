from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import ssl
import urllib.parse
import urllib.request

# ==========================================================
# 1. API 인증키 및 클라우드 포트 설정
# ==========================================================
# ⚠️ 본인의 K-Startup 디코딩 인증키를 입력하세요!
KSTARTUP_API_KEY = "45e101197d8af56d931e7e4117374d4337e7faca09a774bc54c3094f11138790"

# Render 등 클라우드 환경에서 자동 부여하는 포트 인식 (기본 8000)
PORT = int(os.environ.get("PORT", 8000))

ssl_context = ssl._create_unverified_context()
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


# ==========================================================
# 2. D-Day 및 카테고리/대상 분류 로직
# ==========================================================
def calculate_dday_info(end_dt_str, period_str):
  today = datetime.now().date()
  target_date = None

  if end_dt_str:
    clean_end = re.sub(r"[^0-9]", "", str(end_dt_str))
    if len(clean_end) >= 8:
      try:
        target_date = datetime.strptime(clean_end[:8], "%Y%m%d").date()
      except:
        pass

  if not target_date and period_str:
    if "상시" in str(period_str):
      return "상시모집", "bg-blue-50 text-blue-600 border-blue-200", "접수중"
    dates = re.findall(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", str(period_str))
    if dates:
      last_d = dates[-1]
      try:
        target_date = datetime(
            int(last_d[0]), int(last_d[1]), int(last_d[2])
        ).date()
      except:
        pass

  if target_date:
    diff = (target_date - today).days
    if diff < 0:
      return "마감", "bg-slate-100 text-slate-500 border-slate-200", "모집완료"
    elif diff == 0:
      return (
          "오늘마감(D-Day)",
          "bg-red-50 text-red-600 border-red-200",
          "마감임박",
      )
    elif diff <= 7:
      return f"D-{diff}", "bg-red-50 text-red-600 border-red-200", "마감임박"
    else:
      return (
          f"D-{diff}",
          "bg-emerald-50 text-emerald-600 border-emerald-200",
          "접수중",
      )

  if "상시" in str(period_str):
    return "상시모집", "bg-blue-50 text-blue-600 border-blue-200", "상시운영"
  return "접수중", "bg-emerald-50 text-emerald-600 border-emerald-200", "접수중"


def classify_category(text):
  if any(k in text for k in ["공간", "입주", "오피스", "보육", "인큐베이팅"]):
    return "space", "무상 입주/공간"
  if any(
      k in text for k in ["멘토", "상담", "컨설팅", "교육", "자문", "특허", "IP"]
  ):
    return "mentor", "멘토링 & 상담"
  if any(
      k in text
      for k in ["경진대회", "챌린지", "IR", "피칭", "데모데이", "어워즈"]
  ):
    return "contest", "경진대회/IR"
  return "funding", "사업화 자금"


def classify_target(text):
  t = text.lower()
  if any(k in t for k in ["예비", "아이디어", "미창업", "창업준비", "예비창업자"]):
    return "pre", "예비 창업자"
  if any(
      k in t
      for k in [
          "초기",
          "스타트업",
          "기업",
          "대표",
          "법인",
          "3년",
          "5년",
          "7년",
          "창업기업",
      ]
  ):
    return "early", "초기 스타트업"
  return "all", "전체 대상"


def identify_agency(text):
  t = text.lower()
  if "창조경제" in t or "ccei" in t or "창경" in t or "원스톱" in t:
    return "부산창조경제혁신센터"
  if "경제진흥원" in t or "bepa" in t or "특례자금" in t:
    return "부산경제진흥원"
  if "테크노파크" in t or "btp" in t:
    return "부산테크노파크"
  if "투자원" in t or "챌린지" in t or "투자쇼" in t:
    return "부산기술창업투자원"
  return "부산창업포털(부산광역시)"


# ==========================================================
# 3. 데이터 파이프라인 (부산창업포털 + 테크노파크 + K-Startup)
# ==========================================================
def scrape_busan_startup():
  items = []
  url = "https://www.busanstartup.kr/biz_sup?mcode=biz02"
  try:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(
        req, timeout=6, context=ssl_context
    ) as response:
      html = response.read().decode("utf-8", errors="ignore")

    matches = re.findall(
        r'href=["\'](/biz_sup/(\d+)[^"\']*)["\'][^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )
    seen = set()
    for link, post_id, raw_title in matches:
      if post_id in seen:
        continue
      clean_t = re.sub(
          r"\s+", " ", re.sub(r"<[^>]+>", "", raw_title)
      ).strip()
      if len(clean_t) < 5 or "페이지" in clean_t or clean_t == "신청":
        continue
      seen.add(post_id)

      agency_name = identify_agency(clean_t)
      cat_k, cat_n = classify_category(clean_t)
      tgt_k, tgt_n = classify_target(clean_t)
      dday, badge, status = calculate_dday_info("", clean_t)

      items.append({
          "id": f"bs-{post_id}",
          "title": clean_t,
          "agency": agency_name,
          "category": cat_k,
          "categoryName": cat_n,
          "target": tgt_k,
          "targetName": tgt_n,
          "area": "부산",
          "period": "공고문 상세 확인",
          "dday": dday,
          "badgeColor": badge,
          "status": status,
          "link": f"https://www.busanstartup.kr/biz_sup/{post_id}?mcode=biz02",
          "description": (
              f"[{agency_name} 공식 공고] {clean_t}의 세부 지원 요강 및"
              " 신청서입니다."
          ),
          "isLocal": True,
      })
      if len(items) >= 12:
        break
  except:
    pass

  # 접속 지연 시 부산 4대 기관 필수 공고 자동 보장
  if len(items) < 3:
    items.extend([
        {
            "id": "bs-2255",
            "title": (
                "[부산창조경제혁신센터] 스타트업 원스톱 지원센터 - 전문가 상담"
                " 지원"
            ),
            "agency": "부산창조경제혁신센터",
            "category": "mentor",
            "categoryName": "멘토링 & 상담",
            "target": "pre",
            "targetName": "예비 창업자",
            "area": "부산",
            "period": "연중 상시 접수",
            "dday": "상시모집",
            "badgeColor": "bg-blue-50 text-blue-600 border-blue-200",
            "status": "상시운영",
            "link": "https://www.busanstartup.kr/biz_sup/2255?mcode=biz02",
            "description": (
                "예비창업자 대상 법률, 특허, 세무 1:1 무료 전문가 상담 지원"
            ),
            "isLocal": True,
        },
        {
            "id": "bs-530",
            "title": "2026년 부산광역시 청년 창업특례자금 지원",
            "agency": "부산경제진흥원",
            "category": "funding",
            "categoryName": "사업화 자금",
            "target": "early",
            "targetName": "초기 스타트업",
            "area": "부산",
            "period": "자금 한도 소진 시까지",
            "dday": "상시접수",
            "badgeColor": "bg-emerald-50 text-emerald-600 border-emerald-200",
            "status": "접수중",
            "link": "https://www.busanstartup.kr/biz_sup/530",
            "description": "청년 창업가를 위한 시제품 양산 및 특례보증 지원",
            "isLocal": True,
        },
    ])
  return items


def scrape_btp():
  items = []
  url = "https://www.btp.or.kr/kor/CMS/Board/Board.do?mCode=MN013"
  try:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(
        req, timeout=5, context=ssl_context
    ) as response:
      html = response.read().decode("utf-8", errors="ignore")

    matches = re.findall(
        r'board_seq=(\d+)[^"\']*["\'][^>]*>(.*?)</a>', html, re.DOTALL
    )
    seen = set()
    for b_seq, raw_title in matches:
      if b_seq in seen:
        continue
      clean_t = re.sub(
          r"\s+", " ", re.sub(r"<[^>]+>", "", raw_title)
      ).strip()
      if len(clean_t) < 5:
        continue
      seen.add(b_seq)

      dday, badge, status = calculate_dday_info("", clean_t)
      cat_k, cat_n = classify_category(clean_t)
      tgt_k, tgt_n = classify_target(clean_t)

      items.append({
          "id": f"btp-{b_seq}",
          "title": clean_t,
          "agency": "부산테크노파크",
          "category": cat_k,
          "categoryName": cat_n,
          "target": tgt_k,
          "targetName": tgt_n,
          "area": "부산",
          "period": "공고문 상세 확인",
          "dday": dday,
          "badgeColor": badge,
          "status": status,
          "link": f"https://www.btp.or.kr/kor/CMS/Board/Board.do?mCode=MN013&mode=view&mgr_seq=16&board_seq={b_seq}",
          "description": (
              f"[부산테크노파크 기술지원] {clean_t} - 특허, 시제품 제작 지원"
          ),
          "isLocal": True,
      })
      if len(items) >= 6:
        break
  except:
    pass
  return items


def fetch_kstartup_api():
  items = []
  if not KSTARTUP_API_KEY or KSTARTUP_API_KEY.startswith("YOUR_"):
    return items

  base_url = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"
  params = {
      "serviceKey": KSTARTUP_API_KEY,
      "page": 1,
      "perPage": 30,
      "returnType": "json",
  }
  try:
    req_url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(req_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=6, context=ssl_context) as res:
      gov_json = json.loads(res.read().decode("utf-8"))

    raw_items = []
    if isinstance(gov_json.get("data"), list):
      raw_items = gov_json.get("data")
    elif (
        isinstance(gov_json.get("response"), dict)
        and "body" in gov_json["response"]
    ):
      raw_items = gov_json["response"]["body"].get("items", [])

    for idx, item in enumerate(raw_items, start=1):
      title = (
          item.get("biz_pbanc_nm")
          or item.get("bizTitle")
          or item.get("pblancNm")
          or ""
      )
      if not title:
        continue
      agency = (
          item.get("pbanc_ntrp_nm")
          or item.get("sprv_inst")
          or "중소벤처기업부"
      )
      bgng = item.get("pbanc_rcpt_bgng_dt", "")
      end = item.get("pbanc_rcpt_end_dt", "")
      period = (
          f"{bgng} ~ {end}"
          if (bgng and end)
          else (item.get("rcrit_prd") or "공고문 참조")
      )
      target_raw = (
          item.get("aply_trgt_ctnt")
          or item.get("target")
          or "예비창업자 및 초기기업"
      )
      area = item.get("supt_regin") or item.get("area") or "전국"

      dday, badge, status = calculate_dday_info(end, period)
      pbanc_sn = item.get("pbanc_sn")
      direct_url = (
          item.get("detl_pg_url")
          or item.get("biz_aply_url")
          or item.get("biz_gdnc_url")
      )
      if (not direct_url or direct_url == "https://www.k-startup.go.kr") and pbanc_sn:
        direct_url = f"https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn={pbanc_sn}"
      elif not direct_url:
        direct_url = (
            "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do"
        )

      cat_k, cat_n = classify_category(f"{title} {agency}")
      tgt_k, tgt_n = classify_target(f"{title} {target_raw}")

      items.append({
          "id": f"kstart-{pbanc_sn or idx}",
          "title": title,
          "agency": agency,
          "category": cat_k,
          "categoryName": cat_n,
          "target": tgt_k,
          "targetName": tgt_n,
          "area": area,
          "period": period,
          "dday": dday,
          "badgeColor": badge,
          "status": status,
          "link": direct_url,
          "description": (
              f"[{area}] {agency}에서 주관하는 정부 공식 창업지원 공고입니다."
          ),
          "isLocal": "부산" in area or "부산" in title,
      })
  except:
    pass
  return items


# ==========================================================
# 4. HTTP 라우터 (웹 프론트엔드 + API를 1개 서버에서 동시 처리)
# ==========================================================
class DeploymentServer(BaseHTTPRequestHandler):

  def do_OPTIONS(self):
    self.send_response(200)
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "*")
    self.end_headers()

  def do_GET(self):
    # 1) 사이트 주소로 접속 시 index.html 화면 서빙
    if self.path == "/" or self.path == "/index.html" or self.path.startswith("/?"):
      try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, "index.html")
        with open(html_path, "rb") as f:
          content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content)
        return
      except Exception as e:
        self.send_response(404)
        self.end_headers()
        self.wfile.write(f"index.html 파일을 찾을 수 없습니다: {e}".encode("utf-8"))
        return

    # 2) 프론트엔드가 요청하는 실시간 공고 API
    elif self.path.startswith("/api/programs"):
      busan_items = scrape_busan_startup()
      btp_items = scrape_btp()
      kstartup_items = fetch_kstartup_api()

      all_raw = busan_items + btp_items + kstartup_items
      final_list = []
      seen = set()
      for p in all_raw:
        norm = re.sub(r"[\s\-_\[\]\(\)]", "", p["title"])[:15]
        if norm not in seen:
          seen.add(norm)
          final_list.append(p)

      final_list.sort(
          key=lambda x: (
              0
              if x.get("isLocal") or "부산" in x["area"]
              else (1 if "청년" in x["title"] else 2)
          )
      )

      body = json.dumps(
          {"status": "success", "count": len(final_list), "data": final_list},
          ensure_ascii=False,
      ).encode("utf-8")

      self.send_response(200)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Access-Control-Allow-Origin", "*")
      self.end_headers()
      self.wfile.write(body)
    else:
      self.send_response(404)
      self.end_headers()


if __name__ == "__main__":
  print(f"🚀 웹 서버 가동 완료: http://0.0.0.0:{PORT}")
  server = HTTPServer(("0.0.0.0", PORT), DeploymentServer)
  server.serve_forever()