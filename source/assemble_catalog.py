from pathlib import Path
from collections import Counter
from datetime import datetime,timezone,timedelta
import json,csv,re,html
P=Path(__file__).resolve().parent
S={'choosing-the-right-equipment':'装备选择','product-information-and-specifications':'产品信息与性能','basic-techniques':'基础技术','expert-techniques':'进阶技术','rescue':'救援'}
TOPICS=['出发准备与互检','绳结与连接','保护操作与制动','快挂与绳索管理','多段保护站与协作','下降与撤离','拖拽与自救','锁扣与装备选择','绳索性能与坠落力学','装备检查与保养','传统与器械攀登','独攀自我保护与适用限制','待归类']
EQUIP={'GRIGRI-':'GRIGRI +','MICRO-TRAXION':'MICRO TRAXION','NANO-TRAXION':'NANO TRAXION','MINI-TRAXION':'MINI TRAXION','CONNECT-ADJUST':'CONNECT ADJUST','DUAL-CONNECT-ADJUST':'DUAL CONNECT ADJUST','DUAL-EVOLV-ADJUST':'DUAL EVOLV ADJUST','PUR-LINE-6-MM':'PUR LINE 6 mm'}
def classify(r):
 t=r['title_en'].lower(); primary='待归类'; tags=[]
 if r['section_slug']=='choosing-the-right-equipment' or 'carabiner' in t:primary='锁扣与装备选择'
 elif any(w in t for w in ['self-rescue','self rescue','self-belay','self-belaying','ascending','ascender','hauling','stuck:','assisting the second','lowering a load']):primary='拖拽与自救'
 elif any(w in t for w in ['pitons','aid climbing']):primary='传统与器械攀登'
 elif any(w in t for w in ['clean and maintain','cleaned','protect the rope','replaced','remove the magnets','replacing the rope','drying']):primary='装备检查与保养'
 elif any(w in t for w in ['rappel','clean the anchor','recovering quickdraws']):primary='下降与撤离'
 elif any(w in t for w in ['knot','hitch','tying']):primary='绳结与连接'
 elif any(w in t for w in ['quickdraw','coil','rope drag','manage the rope','stowing']):primary='快挂与绳索管理'
 elif any(w in t for w in ['impact','half rope','elongation','forces','rigid/human','force','new ropes','length of','primary dangers','rope too short','influence of the belay']):primary='绳索性能与坠落力学'
 elif any(w in t for w in ['multi-pitch','anchor','alternate leaders','the second','belaying a second','second from above']):primary='多段保护站与协作'
 elif any(w in t for w in ['partner check','communication','tie-in','attaching a rope','string,']):primary='出发准备与互检'
 elif any(w in t for w in ['belay','lowering','spotting','taking up slack','hands-free','stopping a climbing fall','unblocking','tensioning a tyrolean']):primary='保护操作与制动'
 tags=[primary]
 if 'multi-pitch' in t or 'the second' in t or 'second climber' in t or 'second from above' in t:tags.append('多段保护站与协作')
 if 'knot' in t or 'hitch' in t:tags.append('绳结与连接')
 if 'carabiner' in t:tags.append('锁扣与装备选择')
 if 'rappel' in t:tags.append('下降与撤离')
 if 'quickdraw' in t:tags.append('快挂与绳索管理')
 return list(dict.fromkeys(tags))
def equipment(r):
 tags=[EQUIP.get(x,x.replace('-',' ')) for x in r.get('product_sources',[])]
 t=r['title_en'].upper()
 for term in ('GRIGRI','NEOX','REVERSO','VERSO','CONNECT ADJUST','MICRO TRAXION','NANO TRAXION','PUR LINE','STRING','TIBLOC','HUIT','RACK'):
  if term in t and term not in tags:tags.append(term)
 for term,key in [('CARABINER','锁扣'),('ROPE','绳索'),('HARNESS','安全带'),('HELMET','头盔'),('QUICKDRAW','快挂'),('LANYARD','挽索'),('PULLEY','滑轮'),('PULLEYS','滑轮'),('ASCENDER','上升器'),('PITON','岩钉')]:
  if term in t and key not in tags:tags.append(key)
 return tags

def main():
 snap=json.loads((P/'crawl_snapshot.json').read_text(encoding='utf-8'))
 selected=json.loads((P/'selected_articles.json').read_text(encoding='utf-8'))
 trans=json.loads((P/'title_translations.json').read_text(encoding='utf-8'))
 verify=json.loads((P/'verification.json').read_text(encoding='utf-8'))
 resources=json.loads((P/'resources.json').read_text(encoding='utf-8'))
 overrides=json.loads((P/'catalog_overrides.json').read_text(encoding='utf-8')) if (P/'catalog_overrides.json').exists() else {}
 for r in selected:
  v=verify.get(r['id'],{})
  r.update(title_zh=trans.get(r['id'],'待译：'+r['title_en']),official_sections=[S.get(r['section_slug'],r['section_slug'])],topics=classify(r),equipment=equipment(r),http_status=v.get('http_status','未校验'),verified_at=v.get('verified_at',''),has_video=bool(v.get('has_video_embed') or re.search('video',r['title_en'],re.I)),title_matches=v.get('title_matches',False),language='英语',translation_status='已译并校对' if r['id'] in trans else '待译')
  ov=overrides.get(r['id'],{})
  if ov.get('topics'):r['topics']=ov['topics']
  r['equipment']=list(dict.fromkeys(r['equipment']+ov.get('equipment_add',[])))
  if ov.get('context_note'):r['context_note']=ov['context_note']
  if not r['activities']:r['activities']=['相关绳索技术']
 core_count=sum(r['scope']=='主目录' for r in selected)
 meta={**snap['meta'],'core_count':core_count,'total_count':len(selected),'extension_count':len(selected)-core_count,'resource_count':len(resources),'verified_count':sum(r['http_status']==200 and r['title_matches'] for r in selected),'topic_order':TOPICS,'coverage_note':'覆盖本次可访问的 Petzl 室内外攀岩、多段攀岩两大 Tech Tips 活动栏目全部列表记录，合并相关器材栏目中的攀岩与通用绳索技术；电子手册与装备资料另列。未将滑雪、冰川救援、洞穴、攀冰全栏目混入。中文为检索标题，技术条件与步骤以官方原文和当前型号说明书为准。','language_note':'原文入口为英语；中文检索标题为本目录译写，并非 Petzl 官方中文译本。','scope_note':'不声称穷尽官网所有历史新闻、撤下页面、所有语言版本和视频频道；完整性以当前两大活动栏目对账为依据。'}
 generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
 fetched=[s.get('fetched_at','') for s in snap['sources'] if s.get('fetched_at')]
 checked=[r['verified_at'] for r in selected if r.get('verified_at')]
 meta.update(date=generated_at[:10],catalog_generated_at=generated_at,source_fetched_from=min(fetched) if fetched else '',source_fetched_until=max(fetched) if fetched else '',verification_completed_at=max(checked) if checked else '',verification_started_at=min(checked) if checked else '',resource_verified_count=sum(r.get('verification_status')=='已核验' for r in resources))
 meta['downloads']={'csv':'Petzl攀岩教程目录.csv','markdown':'Petzl攀岩教程目录.md','zip':'Petzl攀岩教程目录_'+generated_at[:10]+'.zip'}
 meta['topic_order']=[t for t in TOPICS if any(t in r['topics'] for r in selected)]
 meta['coverage_note']='完整展开本次可访问的 Petzl 室内外攀岩和多段攀岩活动列表，按文章编号去重；另列经适用范围复核的器材教程与跨活动装备限制。中文为检索译题，操作条件与型号限制请查看官方原文。'
 if (P/'audit_scope_candidates.json').exists():
  audit=json.loads((P/'audit_scope_candidates.json').read_text(encoding='utf-8'))
  meta['product_scope_audit']={k:audit['meta'][k] for k in ('audited_at','sitemap_product_root_count','difference_root_count','fetched_difference_roots','new_unique_id_count')}
 catalog={'meta':meta,'articles':selected,'resources':resources}; (P/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
 with (P/'Petzl攀岩教程目录.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields=['中文检索标题','英文原题','主题','活动栏目','官方章节','器材关键词','收录范围','原文语言','官方链接','文章编号','链接状态','校验时间']
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in selected:w.writerow(dict(zip(fields,[r['title_zh'],r['title_en'],'；'.join(r['topics']),'；'.join(r['activities']),'；'.join(r['official_sections']),'；'.join(r['equipment']),r['scope'],r['language'],r['url'],r['id'],r['http_status'],r['verified_at']])))
 activity_rows_total=sum(s['reported_count'] for s in snap['sources'] if s['kind']=='activity')
 lines=['# Petzl 攀岩教程中文索引','',f'整理日期：{meta["date"]}。{core_count} 篇主目录教程 + {meta["extension_count"]} 篇相关绳索技术 + {len(resources)} 个补充资料入口。','',meta['coverage_note'],'',meta['language_note'],'','## 怎么查','', '- 快速查问题：浏览下方主题，或用 Ctrl+F 搜“收站、下放、下降、先锋、跟攀、GRIGRI、NEOX、REVERSO”。','- 按装备查：打开同文件夹的 index.html，使用搜索与器材筛选；所有目录信息已内嵌，双击可用。','- 官方章节是网站分类，不等同于学习难度或能力认证。相同教程可能归属于多个活动，但只计一篇。','- 抱石目前以官方 Access Book #6 作为专题入口；多段不自动等同于传统攀岩。','','## 常用入口','']
 quick=['a77w0000000PBmDAAW','a77w0000000CcBIAA0','a77w0000000GnbSAAS','a77w0000000KyxIAAS','a77Tx0000003XsHIAU','a77w0000000Kyn8AAC','a77w0000000Kyn3AAC','a77w0000000KypxAAC','a77Tx000000E3MEIA0','a77w0000000PBmcAAG']
 byid={r['id']:r for r in selected}
 lines += [f'- [{byid[i]["title_zh"]}]({byid[i]["url"]})' for i in quick if i in byid]
 for topic in TOPICS:
  rows=[r for r in selected if r['topics'][0]==topic]
  if not rows:continue
  lines += ['',f'## {topic}（{len(rows)} 篇）','']
  for r in rows:
   lines += [f'- [{r["title_zh"]}]({r["url"]})',f'  - 原题：{r["title_en"]}',f'  - 归属：{" / ".join(r["activities"])} · {r["official_sections"][0]}'+(' · 装备扩展' if r['scope']!='主目录' else '')]
 lines += ['','## 官方电子手册与装备资料','']
 for r in resources:lines += [f'- [{r["title_zh"]}]({r["url"]})：{r["description"]}']
 lines += ['','## 覆盖与去重依据','', '| 官方活动栏目 | 官网列表记录 | 去重文章数 |', '|---|---:|---:|']
 for s in snap['sources']:
  if s['kind']=='activity':lines += [f'| [{s["label"]}]({s["url"]}) | {s["reported_count"]} | {s["unique_id_count"]} |']
 lines += ['',f'两栏合计 {activity_rows_total} 条列表记录；以文章编号合并后为 {core_count} 篇。两栏共享的文章不重复计数，快挂挂绳的两个 URL 别名也合并。', '',meta['scope_note'],'',f'正文链接核验：{meta["verified_count"]}/{len(selected)} 个返回 HTTP 200 且页面主标题与目录原题一致。核验仅说明本次访问有效；官网后续可能调整。','','## 使用与更新方法','', '目录按照“活动场景 → 要解决的问题 → 对应器材 → 官方原文”组织：活动用于限定场景，主题用于查问题，器材标签用于定位相关型号，官方章节用于保留来源结构。标签不构成兼容性结论。主题可以交叉，Markdown 中每篇只放在一个主主题下。', '', '这是一份查找索引，不是将操作步骤缩写成的速查卡。尤其注意下放（lowering）与自主下降（rappelling）、保护环与系绳连接点、可靠固定锚栓线路与传统保护线路的区别；在原文中核对适用条件、警示和型号。', '', '运行“更新目录.ps1”可重新抓取和校验并生成目录。新出现而尚无中文映射的标题会标“待译”，保留英文原题；更新失败时可继续使用已保存目录。收藏仅保存在当前浏览器，可在网页中导出备份。']
 (P/'Petzl攀岩教程目录.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 lines += ['', '时间记录：目录生成 '+generated_at+'；来源抓取 '+meta['source_fetched_from']+' 至 '+meta['source_fetched_until']+'；正文核验 '+meta['verification_started_at']+' 至 '+meta['verification_completed_at']+'。']
 (P/'Petzl攀岩教程目录.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 # Machine-readable provenance report, including filtered product totals.
 for src in snap['sources']:
  src.pop('rows',None)
 report={'meta':meta,'activity_counts':[{k:s.get(k) for k in ('label','url','reported_count','row_count','unique_id_count')} for s in snap['sources'] if s['kind']=='activity'],'sources':snap['sources'],'duplicate_aliases':[{'id':r['id'],'title_en':r['title_en'],'url':r['url'],'aliases':r['aliases']} for r in selected if r['aliases']],'excluded_topics':['滑雪','冰川救援','洞穴专用行进','攀冰全栏目','铁道攀登全栏目','职业高空作业'],'verification':verify}
 (P/'覆盖与链接核验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(meta,ensure_ascii=False,indent=2))
if __name__=='__main__':main()