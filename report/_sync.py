# -*- coding: utf-8 -*-
"""하나사인몰 시트 -> 매출 리포트 + 재주문 이력 동기화 (GitHub Pages / Firestore)
환경변수: GHT(GitHub token), SA_PATH(서비스계정 json 경로), WORKDIR
- 매 실행: 일자별 매출 집계 -> report/index|board|sales.html + sales-all.json + Firestore meta
- 하루 1회: 거래처 재주문 이력 -> report/reorder.json + reorder-single.json + reorder-meta.json
"""
import json,base64,csv,sys,glob,os,datetime,collections,re
import urllib.request as _u
csv.field_size_limit(sys.maxsize)
WD=os.environ.get("WORKDIR",os.path.dirname(os.path.abspath(__file__)))
GH=os.environ["GHT"]; OWNER="hj92kk-hash"; REPO="HANA-Design-Team"
hdr={"Authorization":"token "+GH,"User-Agent":"hanasm-sync","Accept":"application/vnd.github+json"}
KST=datetime.timezone(datetime.timedelta(hours=9))

def gh_get(p): return _u.urlopen(_u.Request(f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{p}?ref=main",headers=hdr),timeout=90)
def gh_txt(p): return base64.b64decode(json.load(gh_get(p))["content"]).decode()
def gh_put(p,text,msg):
    try: sha=json.load(gh_get(p)).get("sha")
    except Exception: sha=None
    b={"message":msg,"content":base64.b64encode(text.encode()).decode(),"branch":"main"}
    if sha: b["sha"]=sha
    _u.urlopen(_u.Request(f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{p}",data=json.dumps(b).encode(),method="PUT",headers={**hdr,"Content-Type":"application/json"}),timeout=180)

def find_csv():
    c=[x for x in glob.glob('/sessions/*/mnt/.claude/projects/*/*/tool-results/*download_file_content*.txt') if os.path.getsize(x)>100000]
    if not c:
        for root,_,files in os.walk('/sessions'):
            for f in files:
                if 'download_file_content' in f and f.endswith('.txt'):
                    fp=os.path.join(root,f)
                    try:
                        if os.path.getsize(fp)>100000: c.append(fp)
                    except: pass
    if not c: return None
    c.sort(key=os.path.getmtime)
    d=json.load(open(c[-1])); p=WD+'/sheet.csv'
    open(p,'wb').write(base64.b64decode(d['content']))
    return p

# -*- coding: utf-8 -*-
"""하나사인몰 재주문 이력 데이터 빌더
병합규칙: ① 관리주체 접미어 ② 끝의 '아파트' ③ 법인표기 ④-A 담당자·전화 괄호
'개인*' 은 제외."""
import csv,sys,re,json,collections,datetime,os
csv.field_size_limit(sys.maxsize)
WD=os.path.dirname(os.path.abspath(__file__))

SITE=r"(아파트|오피스텔|빌라|타운|자이|푸르지오|힐스테이트|더샵|편한세상|래미안|아이파크|롯데캐슬|호반|중흥|모아|우방|프라임|단지|지구|시티|파크|포레|캐슬|하임|에듀|리버|센트럴|스타|써밋|그랑|위브|센트레빌|한신|현대|삼성|대우|쌍용)"
SURNAME="김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용진태피동경준"
def _paren(n):
    """④-A: 괄호 안이 담당자·사람이름이면 제거. 현장명·전화번호·기타는 유지."""
    def rep(m):
        inner=m.group(1)
        if re.search(r"(담당|님|씨|과장|대리|부장|팀장|소장|실장|주임|사원|차장)",inner): return ""
        if re.search(SITE,inner): return m.group(0)
        if re.fullmatch(r"[가-힣]{2,4}",inner) and inner[0] in SURNAME: return ""
        return m.group(0)
    return re.sub(r"[\(\[]([^\)\]]*)[\)\]]",rep,n)

def base(n):
    n=re.sub(r"\s+","",(n or "").replace("\t"," ").strip())
    if not n: return ""
    n=_paren(n)                       # ④-A
    core=n
    c2=re.sub(r"^(\(주\)|㈜|주식회사|\(유\)|유한회사|\(재\)|\(사\))","",core)   # ③
    c2=re.sub(r"(\(주\)|㈜|주식회사|\(유\)|유한회사)$","",c2)
    corp=(c2!=core); core=c2
    for _ in range(2):                # ①
        core=re.sub(r"(입주자대표회의|입대의|관리사무소|관리위원회|생활지원센터|관리단|자치회|부녀회|경비실|관리소)$","",core)
    core=re.sub(r"아파트$","",core)     # ②
    core=core.replace("(e)","").replace("(E)","").strip()
    # 법인표기 제거가 개입하면서 4자 이하로 짧아지면 오병합 위험(예: (주)대동 vs 대동아파트) → 롤백
    if corp and len(core)<5 and len(core)<len(n): return n.replace("(e)","").replace("(E)","").strip()
    return core

def amt(s):
    s=(s or "").strip().replace(",","")
    if s=="": return None
    try: return int(s)
    except:
        try:
            f=float(s); return int(f) if f==int(f) else None
        except: return None
def qty(s):
    s=(s or "").strip().replace(",","")
    try: return int(float(s))
    except: return 0
def classify(name):
    n=(name or "").replace(" ","")
    if "피난안내도" in n: return "피난안내도"
    if "말뚝" in n: return "말뚝안내판"
    if (("주차" in n and "스티커" in n) or "주차증" in n or "경고장" in n or ("자전거" in n and "스티커" in n)): return "주차스티커"
    if "게시판" in n: return "게시판"
    if "A형" in n or "입간판" in n or "오뚜기" in n: return "A형입간판"
    if any(k in n for k in ["현수막","가림막","휀스","펜스","후렉스"]): return "현수막"
    if "배너" in n: return "배너"
    if "엘리베이터" in n or "승강기" in n: return "엘리베이터간판·스티커"
    if "명함" in n: return "명함"
    if any(k in n for k in ["관리규약","경비일지","회보"]): return "인쇄물(규약/일지)"
    if any(k in n for k in ["표찰","명판","명패","이름표","팻말","표지판","진입판"]): return "표지판·명판"
    if "바닥" in n: return "바닥스티커"
    if "안내판" in n: return "안내판(포맥스류)"
    if "쿠폰" in n: return "쿠폰·판촉"
    if any(k in n for k in ["디자인","추가금액","사이즈조정","현위치"]): return "디자인·부가"
    if "포맥스" in n: return "포맥스(기타)"
    if "스티커" in n: return "기타스티커"
    return "기타"

def build(csv_path):
    rows=list(csv.reader(open(csv_path,encoding='utf-8')))
    G={}
    for r in rows:
        if len(r)<18: continue
        yy,mm,dd=r[0].strip(),r[1].strip(),r[2].strip()
        if not(yy.isdigit() and mm.isdigit() and dd.isdigit()): continue
        try: d=datetime.date(2000+int(yy),int(mm),int(dd))
        except: continue
        prog=r[3].strip()
        if not prog: continue
        raw=re.sub(r"\s+","",(r[11] or "").replace("\t"," ").strip())
        if not raw or raw.startswith("개인"): continue
        key=base(raw)
        if not key: continue
        a=amt(r[17])
        if a is None: continue
        item=(r[12] or "").replace("\t","").strip()
        g=G.setdefault(key,{"alias":collections.Counter(),"hist":[],"type":collections.Counter(),"cats":collections.defaultdict(lambda:[0,0,0])})
        g["alias"][raw]+=1
        ct=(r[7] or "").strip()
        if ct: g["type"][ct]+=1
        cat=classify(item)
        c=g["cats"][cat]; c[0]+=1; c[1]+=a; c[2]+=qty(r[16])
        g["hist"].append([d.isoformat(),a,item[:60],prog,cat])
    out_multi={}; out_single={}
    for k,g in G.items():
        g["hist"].sort(key=lambda x:x[0])
        n=len(g["hist"]); tot=sum(x[1] for x in g["hist"])
        first=g["hist"][0][0]; last=g["hist"][-1][0]
        # 평균 재주문 주기(서로 다른 주문일 기준)
        udays=sorted(set(x[0] for x in g["hist"]))
        if len(udays)>=2:
            d0=datetime.date(*map(int,udays[0].split("-")))
            d1=datetime.date(*map(int,udays[-1].split("-")))
            cycle=round((d1-d0).days/(len(udays)-1))
        else: cycle=None
        rep=g["alias"].most_common(1)[0][0]
        rec={"nm":rep,"n":n,"tot":tot,"first":first,"last":last,"cyc":cycle,
             "ty":(g["type"].most_common(1)[0][0] if g["type"] else ""),
             "al":[a for a,_ in g["alias"].most_common()],
             "ct":{c:v for c,v in sorted(g["cats"].items(),key=lambda x:-x[1][1])},
             "h":[[x[0],x[1],x[2],x[3]] for x in g["hist"]]}
        (out_multi if n>=2 else out_single)[k]=rec
    return out_multi,out_single

def pack(m,s,gen):
    """문자열 테이블로 진행자·고객유형·품목분류를 인덱스화해 용량 절감"""
    P=[];PI={};T=[];TI={};C=[];CI={}
    def pi(x):
        if x not in PI: PI[x]=len(P); P.append(x)
        return PI[x]
    def ti(x):
        if x not in TI: TI[x]=len(T); T.append(x)
        return TI[x]
    def ci(x):
        if x not in CI: CI[x]=len(C); C.append(x)
        return CI[x]
    mm={}
    for k,v in m.items():
        mm[k]={"nm":v["nm"],"n":v["n"],"tot":v["tot"],"first":v["first"],"last":v["last"],
               "cyc":v["cyc"],"ty":ti(v["ty"]),"al":v["al"] if len(v["al"])>1 else [],
               "ct":[[ci(c),x[0],x[1],x[2]] for c,x in v["ct"].items()],
               "h":[[h[0],h[1],h[2][:40],pi(h[3])] for h in v["h"]]}
    ss=[]
    for k,v in s.items():
        h=v["h"][0]
        ss.append([k,v["nm"],h[0],h[1],h[2][:40],pi(h[3]),ti(v["ty"])])
    return ({"generated":gen,"prog":P,"type":T,"cat":C,"cust":mm},
            {"generated":gen,"prog":P,"type":T,"rows":ss})


# ---------- 일일 매출 집계 ----------
EMP=["정란","태경","현주","민주","영호","현정","글이","흥구"]
def norm(s): return (s or "").strip()
def is_hq(p):
    p=norm(p); return p.startswith("사인몰") or any(e in p for e in EMP)

def build_daily(path):
    rows=list(csv.reader(open(path,encoding='utf-8')))
    days={}
    for r in rows:
        if len(r)<18: continue
        yy,mm,dd=norm(r[0]),norm(r[1]),norm(r[2])
        if not(yy.isdigit() and mm.isdigit() and dd.isdigit()): continue
        try: dtv=datetime.date(2000+int(yy),int(mm),int(dd))
        except: continue
        prog=norm(r[3])
        if prog=="": continue
        key=dtv.isoformat()
        rec=days.setdefault(key,{"date":key,"hq":{},"op":{},"items":{},"items_hq":{},"items_op":{},"excl":0,"total":0,"cnt":0,"hq_total":0,"hq_cnt":0,"op_total":0,"op_cnt":0,"top5":[]})
        a=amt(r[17])
        if a is None: rec["excl"]+=1; continue
        q=qty(r[16]); cat=classify(r[12])
        rec["total"]+=a; rec["cnt"]+=1
        rec["top5"].append([a,norm(r[11]),norm(r[12]),prog])
        rec["items"].setdefault(cat,[0,0]); rec["items"][cat][0]+=a; rec["items"][cat][1]+=1
        if is_hq(prog):
            rec["hq"].setdefault(prog,[0,0]); rec["hq"][prog][0]+=a; rec["hq"][prog][1]+=1
            rec["hq_total"]+=a; rec["hq_cnt"]+=1
            rec["items_hq"].setdefault(cat,[0,0]); rec["items_hq"][cat][0]+=1; rec["items_hq"][cat][1]+=q
        else:
            rec["op"].setdefault(prog,[0,0]); rec["op"][prog][0]+=a; rec["op"][prog][1]+=1
            rec["op_total"]+=a; rec["op_cnt"]+=1
            rec["items_op"].setdefault(cat,[0,0]); rec["items_op"][cat][0]+=1; rec["items_op"][cat][1]+=q
    days={k:v for k,v in days.items() if v["cnt"]>0}
    for v in days.values(): v["top5"]=sorted(v["top5"],key=lambda x:-x[0])[:5]
    return days

def push_firestore(days,gen):
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        import requests
        PID="hanasm-daily-sales"
        creds=service_account.Credentials.from_service_account_file(os.environ["SA_PATH"],scopes=["https://www.googleapis.com/auth/datastore"])
        creds.refresh(Request())
        FH={"Authorization":"Bearer "+creds.token,"Content-Type":"application/json"}
        w=[{"update":{"name":f"projects/{PID}/databases/(default)/documents/meta/index",
           "fields":{"dates":{"stringValue":json.dumps([{"date":k,"total":days[k]['total'],"cnt":days[k]['cnt']} for k in sorted(days)],ensure_ascii=False)},
                     "generated":{"stringValue":gen}}}}]
        requests.post(f"https://firestore.googleapis.com/v1/projects/{PID}/databases/(default)/documents:commit",headers=FH,json={"writes":w},timeout=90)
        return True
    except Exception: return False

def main():
    path=find_csv()
    if not path: print("NO_CSV_FOUND"); return 1
    gen=datetime.datetime.now(KST).strftime('%Y-%m-%d %H:%M')
    today=datetime.datetime.now(KST).strftime('%Y-%m-%d')
    days=build_daily(path)
    djson=json.dumps({"generated":gen,"data":days},ensure_ascii=False,separators=(',',':'))
    fb=push_firestore(days,gen)
    tmpl=gh_txt("report/template.html"); page=tmpl.replace("__DATA__",djson)
    for f in ["report/index.html","report/board.html","report/sales.html"]: gh_put(f,page,"hanasm sync "+gen)
    gh_put("report/sales-all.json",djson,"hanasm sync "+gen)
    # ---- 재주문 이력: 하루 1회 ----
    ro="skip"
    try: due=json.loads(gh_txt("report/reorder-meta.json")).get("date")!=today
    except Exception: due=True
    if due:
        m,s=build(path)
        A,B=pack(m,s,gen)
        gh_put("report/reorder.json",json.dumps(A,ensure_ascii=False,separators=(',',':')),"reorder "+gen)
        gh_put("report/reorder-single.json",json.dumps(B,ensure_ascii=False,separators=(',',':')),"reorder "+gen)
        gh_put("report/reorder-meta.json",json.dumps({"date":today,"generated":gen,"multi":len(m),"single":len(s)},ensure_ascii=False),"reorder "+gen)
        ro="rebuilt(%d곳)"%len(m)
    print("SYNC_OK days=%d reorder=%s firestore=%s updated=%s KST"%(len(days),ro,"ok" if fb else "skip",gen))
    return 0

if __name__=="__main__":
    sys.exit(main())
