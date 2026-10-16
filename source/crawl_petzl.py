"""Crawl publicly readable Petzl category pages, respecting robots.txt.
Stdlib only. Saves title/link metadata, never copies article bodies.
"""
from urllib.request import Request,urlopen
from urllib.parse import urljoin,urlsplit
from urllib.robotparser import RobotFileParser
from pathlib import Path
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor
import json,re,html,time,hashlib,argparse
BASE=Path(__file__).resolve().parent
DOMAIN='https://www.petzl.com'
UA='Mozilla/5.0 (compatible; PersonalPetzlIndex/1.0; public metadata only)'
CORE={'indoor-and-outdoor-climbing':'室内外攀岩','multi-pitch-climbing':'多段攀岩'}
PRODUCTS='grigri grigri- neox reverso verso connect-adjust dual-connect-adjust dual-evolv-adjust spirit spirit-express djinn-axess ange-s ange-l ange-finesse attache attache-bar amd william ok smd anneau tibloc micro-traxion nano-traxion mini-traxion ascension basic pur-line-6-mm arial-9.5-mm contact-9.8-mm mambo-10.1-mm volta-9.2-mm volta-guide-9-mm tango-8.5-mm rumba-8-mm paso-guide-7.7-mm pulse-8-mm hirundos sama selena adjama luna aquila corax sitta meteor sirocco coeur-stainless coeur-bolt-stainless coeur-pulse-12-mm coll inox batinox bolt-stainless vrillee coudee universel livanos v-conique rocher-mixte'.split()
PRODUCTS=[x for x in PRODUCTS if x not in ('coll','inox')]+['collinox','rad-line-6-mm','rad-system']
DATE=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
CACHE=BASE/'_抓取校验资料'/'cache'; CACHE.mkdir(parents=True,exist_ok=True)
REFRESH=False
logs=[]
def get(url,refresh=False):
    if not robot.can_fetch('*',url): raise RuntimeError('Blocked by robots.txt: '+url)
    key=hashlib.sha256(url.encode()).hexdigest()[:20]; f=CACHE/(key+'.json')
    if f.exists() and not refresh and not REFRESH:
        d=json.loads(f.read_text(encoding='utf-8')); logs.append({'url':url,'status':d['status'],'cached':True}); return d
    last=None
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={'User-Agent':UA}),timeout=40) as r:
                d={'url':url,'final_url':r.url,'status':r.status,'html':r.read().decode('utf-8','replace'),'fetched_at':datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')}
            f.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8'); logs.append({'url':url,'status':d['status'],'cached':False}); time.sleep(.35); return d
        except Exception as e: last=e; time.sleep(1+attempt)
    logs.append({'url':url,'status':'error','error':str(last)}); raise last
robot=RobotFileParser(); rob=urlopen(Request(DOMAIN+'/robots.txt',headers={'User-Agent':UA}),timeout=40).read().decode(); robot.parse(rob.splitlines()); (BASE/'robots_snapshot.txt').write_text(rob,encoding='utf-8')

def parse(d):
    text=d['html']; count=re.search(r'(\d+)\s+Tech Tips?',text)
    start=text.find('<div class="product-grid grid-container')
    if start < 0:return [],int(count.group(1)) if count else None
    end=text.find('<div class="grid-item full-width grid-footer',start)
    if end < 0:end=text.find('id="content-search-results-pane"',start)
    text=text[start:end if end >= 0 else len(text)]
    # The des-link paragraphs are the real grid; excludes recommendation carousel.
    pairs=re.findall(r'<p class="pdp-link des-link">\s*<a[^>]+href="([^"]+)"[^>]*>\s*(.*?)\s*</a>',text,re.S)
    rows=[]
    for a,b in pairs:
        if '/sport/tech-tips' not in a: continue
        u=urljoin(DOMAIN,html.unescape(a)); title=html.unescape(re.sub('<[^>]+>','',b)).strip(); title=re.sub(r'\s+',' ',title)
        rid=re.search(r'_SPO_([A-Za-z0-9]{18})\.html',u)
        if not rid: continue
        title=title.replace('�C','–').replace('�c','–')
        rows.append({'id':rid.group(1),'title_en':title,'url':u,'section_slug':re.split(r'/tech-tips(?:-by-product)?/',u)[1].split('/')[0]})
    return rows,int(count.group(1)) if count else None

def job(seed):
    kind,label,url=seed
    try:
        d=get(url+'?start=0&sz=200'); rows,total=parse(d)
        if total is not None and len(rows)<total:
            rows=[]
            for start in range(0,total,12):
                part,_=parse(get(url+f'?start={start}&sz=12')); rows.extend(part)
        print(label,':',len(rows),'/',total,flush=True)
        return {'kind':kind,'label':label,'url':url,'reported_count':total,'row_count':len(rows),'unique_id_count':len({r['id'] for r in rows}),'rows':rows,'status':d['status'],'fetched_at':d['fetched_at']}
    except Exception as e:
        print('FAILED',label,str(e),flush=True); return {'kind':kind,'label':label,'url':url,'error':str(e),'rows':[]}

def main():
    global REFRESH
    ap=argparse.ArgumentParser(); ap.add_argument('--core-only',action='store_true'); ap.add_argument('--refresh',action='store_true'); args=ap.parse_args(); REFRESH=args.refresh
    seeds=[('activity',label,DOMAIN+'/us/en/sport/tech-tips/'+slug) for slug,label in CORE.items()]
    if not args.core_only: seeds += [('product',slug.upper(),DOMAIN+'/us/en/sport/tech-tips-by-product/'+slug) for slug in PRODUCTS]
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(job,seeds))
    bad=[s for s in results if s.get('error') or s.get('reported_count') is None or s['row_count']!=s['reported_count']]
    if bad:raise RuntimeError('Core category incomplete; previous snapshot kept: '+str(bad))
    records={}
    for s in results:
        for r in s['rows']:
            rec=records.setdefault(r['id'],{**r,'aliases':[],'activities':[],'product_sources':[],'source_urls':[],'scope':'装备扩展'})
            if r['url']!=rec['url'] and r['url'] not in rec['aliases']:rec['aliases'].append(r['url'])
            if s['url'] not in rec['source_urls']:rec['source_urls'].append(s['url'])
            if s['kind']=='activity':
                rec['scope']='主目录'
                if s['label'] not in rec['activities']:rec['activities'].append(s['label'])
            elif s['label'] not in rec['product_sources']:rec['product_sources'].append(s['label'])
    out={'meta':{'date':DATE[:10],'crawled_at':DATE,'core_count':sum(r['scope']=='主目录' for r in records.values()),'total_count':len(records),'seed_count':len(seeds),'source_fetched_from':min(s['fetched_at'] for s in results),'source_fetched_until':max(s['fetched_at'] for s in results)},'articles':list(records.values()),'sources':results,'requests':logs}
    (BASE/'crawl_snapshot.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    (BASE/'titles_for_translation.json').write_text(json.dumps([{'id':r['id'],'title_en':r['title_en'],'scope':r['scope']} for r in records.values()],ensure_ascii=False,indent=2),encoding='utf-8')
    print('SUMMARY',json.dumps(out['meta'],ensure_ascii=False),flush=True)
if __name__=='__main__':main()