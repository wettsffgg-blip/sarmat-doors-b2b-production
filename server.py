#!/usr/bin/env python3
import os, json, io, urllib.request, urllib.parse, time, secrets, html
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parent

def load_env_file():
    env = ROOT / '.env'
    if not env.exists(): return
    for raw in env.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v = line.split('=',1); k=k.strip(); v=v.strip().strip('"').strip("'")
        if k and k not in os.environ: os.environ[k]=v
load_env_file()

FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
if Path(FONT).exists():
    pdfmetrics.registerFont(TTFont('DV',FONT)); pdfmetrics.registerFont(TTFont('DVB',FONTB))
    BASEFONT='DV'; BOLD='DVB'
else:
    BASEFONT='Helvetica'; BOLD='Helvetica-Bold'

TOKEN=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
CHAT_ID=os.environ.get('TELEGRAM_CHAT_ID','').strip()


def money(n):
    return f"{round(float(n)):,}".replace(',',' ')+' сум'

def esc(v): return html.escape(str(v if v is not None else ''))

def tg_request(method, fields=None, files=None):
    if not TOKEN or not CHAT_ID: raise RuntimeError('Telegram не настроен: задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID')
    fields=fields or {}
    if not files:
        data=urllib.parse.urlencode(fields).encode()
        req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/{method}',data=data,method='POST')
    else:
        boundary='----SarmatBoundary'+secrets.token_hex(8); chunks=[]
        for k,v in fields.items():
            chunks += [f'--{boundary}\r\n'.encode(),f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode(),str(v).encode(),b'\r\n']
        for name,(filename,content,ctype) in files.items():
            chunks += [f'--{boundary}\r\n'.encode(),f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),f'Content-Type: {ctype}\r\n\r\n'.encode(),content,b'\r\n']
        chunks.append(f'--{boundary}--\r\n'.encode()); data=b''.join(chunks)
        req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/{method}',data=data,method='POST',headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(req,timeout=25) as r: result=json.loads(r.read().decode())
    if not result.get('ok'): raise RuntimeError(result.get('description','Telegram API error'))
    return result

def tg_send(text): return tg_request('sendMessage',{'chat_id':CHAT_ID,'text':text})
def tg_send_pdf(pdf_bytes,filename,caption): return tg_request('sendDocument',{'chat_id':CHAT_ID,'caption':caption},{'document':(filename,pdf_bytes,'application/pdf')})


def make_pdf(payload, signed=False):
    """Generate the single canonical SARMAT DOORS commercial-proposal PDF.

    The same function is used for preview/download/print and for the final
    signed+stamped document.  Installation is stored inside each configurator
    row's total, so it is explicitly separated from the door price here.
    """
    buf=io.BytesIO()
    doc=SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=32, rightMargin=32, topMargin=104, bottomMargin=34,
        title='SARMAT DOORS — Коммерческое предложение',
        author='ООО SARMAT DOORS'
    )
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='RU',fontName=BASEFONT,fontSize=8.5,leading=10.5))
    styles.add(ParagraphStyle(name='RUB',parent=styles['RU'],fontName=BOLD))
    styles.add(ParagraphStyle(name='TitleSD',fontName=BOLD,fontSize=19,leading=21,textColor=colors.HexColor('#102332'),alignment=TA_CENTER,spaceAfter=3))
    styles.add(ParagraphStyle(name='GoldSD',fontName=BOLD,fontSize=10.5,leading=12,textColor=colors.HexColor('#c49a37'),alignment=TA_CENTER,spaceAfter=6))
    styles.add(ParagraphStyle(name='SecSD',fontName=BOLD,fontSize=10,leading=11.5,textColor=colors.HexColor('#c49a37'),spaceBefore=6,spaceAfter=3))
    styles.add(ParagraphStyle(name='StageSD',fontName=BOLD,fontSize=8.5,leading=10,textColor=colors.HexColor('#c49a37'),alignment=TA_CENTER,spaceBefore=8,spaceAfter=4))
    styles.add(ParagraphStyle(name='SmallSD',parent=styles['RU'],fontSize=7.6,leading=9.2))
    c=payload.get('customer') or {}
    order=payload.get('order') or []
    oid=payload.get('orderId','SARMAT_DOORS')

    def qty_of(x):
        try: return max(1,int(x.get('qty',1) or 1))
        except Exception: return 1
    def per_total(x):
        try: return float(x.get('total',0) or 0)
        except Exception: return 0.0
    def inst_per(x):
        try: return float(x.get('inst',0) or 0)
        except Exception: return 0.0

    doors=sum(qty_of(x) for x in order)
    # The configurator's x.total includes installation when installation is selected.
    # Separate it here so the proposal never double-counts installation.
    door_total=sum(max(0,per_total(x)-inst_per(x))*qty_of(x) for x in order)
    install_total=sum(inst_per(x)*qty_of(x) for x in order)
    grand_total=door_total+install_total

    story=[]
    story += [
        Paragraph(f'<b>№ {esc(oid)}</b><br/>Дата: {datetime.now().strftime("%d.%m.%Y")}',styles['RU']),
        Spacer(1,3),
        Paragraph('КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ',styles['TitleSD']),
        Paragraph('Поставка и монтаж металлических и противопожарных дверей.',styles['GoldSD']),
        Paragraph('<b>Уважаемые коллеги!</b><br/>ООО «SARMAT DOORS» предлагает изготовление, поставку и монтаж металлических и противопожарных дверей по представленному перечню. Все позиции изготавливаются индивидуально по выбранным клиентом размерам, техническим требованиям и комплектации.',styles['RU']),
        Paragraph('ОСНОВНЫЕ ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ',styles['SecSD']),
    ]
    bullets=[
        'Заполнение противопожарных дверей — каменная вата высокой плотности с учетом требований конструкции и испытаний.',
        'Противопожарные двери комплектуются необходимыми уплотнениями и доводчиками согласно соответствующей позиции.',
        'Для позиций с выпадающим порогом предусматривается соответствующая фурнитура.',
        'Противопожарные двери SARMAT DOORS имеют сертификаты пожарной безопасности и протоколы испытаний на соответствующий предел огнестойкости.'
    ]
    story.append(Table([[Paragraph('• '+esc(b),styles['SmallSD'])] for b in bullets],colWidths=[531]))
    story.append(Paragraph('СТОИМОСТЬ',styles['SecSD']))

    data=[[Paragraph('<b>№</b>',styles['SmallSD']),Paragraph('<b>Наименование</b>',styles['SmallSD']),Paragraph('<b>Размер, м</b>',styles['SmallSD']),Paragraph('<b>Кол-во</b>',styles['SmallSD']),Paragraph('<b>Примечание</b>',styles['SmallSD']),Paragraph('<b>Цена за 1 шт., сум</b>',styles['SmallSD']),Paragraph('<b>Сумма, сум</b>',styles['SmallSD'])]]
    for i,x in enumerate(order,1):
        q=qty_of(x)
        door_price=max(0,per_total(x)-inst_per(x))
        note='<br/>'.join(filter(None,[
            f"Тип двери: {esc(x.get('doorType','Противопожарная'))}",
            f"Класс огнестойкости: {esc('Не применяется' if x.get('doorType')=='Техническая' else x.get('cls','—'))}",
            f"Открывание: {esc(x.get('opening','—'))}; полотно: {esc(x.get('leafMm','—'))} мм; коробка: {esc(x.get('frameMm','—'))} мм",
            f"Фурнитура: {esc(x.get('hwText','—'))}; доводчик: {'да — '+money(400000) if x.get('closer') else 'нет'}; {esc(x.get('ralText','RAL —'))}",
            f"Монтаж и доставка: {money(inst_per(x))} / дверь" if inst_per(x)>0 else '',
            f"Примечание клиента: {esc(x.get('comment'))}" if x.get('comment') else ''
        ]))
        name=' '.join(filter(None,[str(x.get('doorType','Противопожарная')),str(x.get('cls','') if x.get('doorType')!='Техническая' else ''),f"{x.get('w','—')}×{x.get('h','—')} мм"]))
        data.append([
            str(i), Paragraph(esc(name),styles['SmallSD']),
            Paragraph(f"{esc(x.get('w','—'))}×{esc(x.get('h','—'))}",styles['SmallSD']),
            str(q), Paragraph(note,styles['SmallSD']),
            Paragraph(money(door_price),styles['SmallSD']),
            Paragraph(money(door_price*q),styles['SmallSD'])
        ])
    data.append([Paragraph('<b>Итого двери (%d шт.):</b>'%doors,styles['SmallSD']),'','','','','',Paragraph('<b>%s</b>'%money(door_total),styles['SmallSD'])])
    tbl=Table(data,colWidths=[18,115,52,35,157,78,76],repeatRows=1)
    tbl.setStyle(TableStyle([
      ('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#c7cdd1')),
      ('ROWBACKGROUNDS',(0,1),(-1,-2),[colors.white,colors.HexColor('#fbfbfb')]),
      ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f0f0f0')),
      ('BACKGROUND',(5,1),(-1,-1),colors.HexColor('#fff8df')),
      ('VALIGN',(0,0),(-1,-1),'TOP'),
      ('ALIGN',(0,0),(0,-1),'CENTER'),('ALIGN',(2,0),(3,-1),'CENTER'),('ALIGN',(5,1),(-1,-1),'RIGHT'),
      ('FONTSIZE',(0,0),(-1,-1),7.1),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
      ('SPAN',(0,-1),(5,-1)),('FONTNAME',(0,-1),(-1,-1),BOLD),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#fff3c9'))
    ]))
    story.append(tbl)
    install_text=(f'600 000 сум за 1 дверь — отдельная позиция. Всего за {doors} дверей: {money(install_total)}.' if install_total>0 else 'Монтаж и доставка не включены в выбранные позиции.')
    terms=[
      ('Монтаж, доставка и пена',install_text),
      ('Стоимость дверей',money(door_total)),
      ('Общая стоимость с монтажом, доставкой и пеной',money(grand_total)),
      ('Оплата','70% — предоплата; 30% — до поставки товара.'),
      ('Цена','Указанные цены рассчитаны с учетом НДС.'),
      ('Сроки поставки и изготовления','Согласовывается при подписании заказа и утверждении рабочих размеров.'),
      ('Гарантия 1 год','Предоставляется на изготовленные изделия и выполненные монтажные работы согласно договору.')]
    t2=Table([[Paragraph(esc(a),styles['SmallSD']),Paragraph(esc(b),styles['SmallSD'])] for a,b in terms],colWidths=[155,376])
    t2.setStyle(TableStyle([
      ('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#c9cfd3')),('VALIGN',(0,0),(-1,-1),'TOP'),
      ('BACKGROUND',(0,0),(0,-1),colors.HexColor('#f3f3f3')),
      ('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)
    ]))
    terms_block=[Paragraph('УСЛОВИЯ ПОСТАВКИ И ОПЛАТЫ',styles['SecSD']),t2]
    stage = int(payload.get('stage', 3 if signed else 2) or (3 if signed else 2))
    if signed:
        stage_text='ЭТАП 3 — ФИНАЛЬНОЕ КП ПОСЛЕ ОТПРАВКИ ЗАКАЗА • ПОДПИСЬ И ПЕЧАТЬ'
    elif stage == 1:
        stage_text='ЭТАП 1 — ПРОСМОТР КП БЕЗ ПОДПИСИ И ПЕЧАТИ'
    else:
        stage_text='ЭТАП 2 — КП БЕЗ ПОДПИСИ И ПЕЧАТИ'
    if signed:
        sig=ROOT/'signature_clean.png'; stamp=ROOT/'stamp_clean.png'
        cells=[Paragraph('<b>С уважением,</b><br/>ООО «SARMAT DOORS»<br/>Директор<br/>Сапаркулов Нурлан Ергешевич',styles['RU'])]
        imgs=[]
        if sig.exists(): imgs.append(Image(str(sig),width=105,height=44))
        if stamp.exists(): imgs.append(Image(str(stamp),width=62,height=62))
        cells.append(imgs)
        st=Table([cells],colWidths=[190,343])
        st.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
        terms_block += [Spacer(1,7),st]
    if signed:
        terms_block.append(Paragraph(stage_text,styles['StageSD']))
    # Never split the conditions block so the last row cannot land alone on a new page.
    story.append(KeepTogether(terms_block))

    def header_footer(canvas,doc):
        W,H=A4; canvas.saveState()
        header=ROOT/'sarmat_header_crop.jpg'
        header_h=80
        if header.exists():
            try:
                canvas.drawImage(str(header),0,H-header_h,width=W,height=header_h,preserveAspectRatio=False,mask='auto')
            except Exception:
                canvas.setFillColor(colors.HexColor('#061a2b')); canvas.rect(0,H-header_h,W,header_h,fill=1,stroke=0)
        else:
            canvas.setFillColor(colors.HexColor('#061a2b')); canvas.rect(0,H-header_h,W,header_h,fill=1,stroke=0)
            logo=ROOT/'sarmat_logo.png'
            if logo.exists():
                try: canvas.drawImage(str(logo),28,H-74,width=64,height=64,preserveAspectRatio=True,mask='auto')
                except Exception: pass
            canvas.setFillColor(colors.white); canvas.setFont(BOLD,9.2); canvas.drawString(116,H-28,'ООО "SARMAT DOORS"')
            canvas.setFont(BASEFONT,6.6); canvas.drawString(116,H-41,'Республика Узбекистан, г. Ташкент, Яккасарайский район, Кушбеги 18.')
            canvas.drawString(116,H-52,'+998 33 373 33 33  •  enery-uz@bk.ru')
        canvas.setFillColor(colors.HexColor('#d7b25a')); canvas.rect(32,H-header_h-4,W-64,1,fill=1,stroke=0)
        canvas.setFillColor(colors.HexColor('#68737b')); canvas.setFont(BASEFONT,6.2); canvas.drawCentredString(W/2,18,'ООО "SARMAT DOORS" • ИНН 313 122 742 • Р/С 2020 8000 9074 8926 7001 • МФО 01071')
        canvas.restoreState()
    doc.build(story,onFirstPage=header_footer,onLaterPages=header_footer)
    raw=buf.getvalue()
    if not raw.startswith(b'%PDF-'): raise RuntimeError('PDF generation returned invalid data')
    return raw

RATE={}; RATE_WINDOW=60; RATE_MAX=20; MAX_BODY=1024*1024
SENT_ORDERS=set()

def safe_filename(value, suffix):
    raw=str(value or 'SARMAT_DOORS').strip()
    cleaned=''.join(ch if ch.isalnum() or ch in '-.' else '_' for ch in raw)
    cleaned=cleaned.strip('._') or 'SARMAT_DOORS'
    return f'{cleaned}{suffix}'
class Handler(SimpleHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS'); self.send_header('Access-Control-Allow-Headers','Content-Type')
    def _json(self,code,obj):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(code); self._cors(); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def _pdf(self,b,filename):
        if not b.startswith(b'%PDF-'): raise RuntimeError('Сервер сформировал некорректный PDF')
        self.send_response(200); self._cors(); self.send_header('Content-Type','application/pdf'); self.send_header('Content-Disposition',f'attachment; filename="{filename}"'); self.send_header('Cache-Control','no-store, no-cache, must-revalidate'); self.send_header('Content-Length',str(len(b))); self.send_header('X-SARMAT-PDF-TEMPLATE','SARMAT_APPROVED_CP_V1'); self.send_header('X-SARMAT-PDF-STAGE', '3' if 'FINAL' in filename else '2'); self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self): self.send_response(204); self._cors(); self.end_headers()
    def do_GET(self):
        if self.path=='/api/health': return self._json(200,{'ok':True,'telegramConfigured':bool(TOKEN and CHAT_ID),'pdf':True,'finalPdf':True,'pdfEngine':'reportlab-sarmat-approved-v1','pdfTemplate':'SARMAT_APPROVED_CP_V1'})
        return super().do_GET()
    def do_POST(self):
        ip=self.client_address[0]; now=time.time(); hist=[t for t in RATE.get(ip,[]) if now-t<RATE_WINDOW]
        if len(hist)>=RATE_MAX: return self._json(429,{'ok':False,'error':'Слишком много запросов. Попробуйте позже.'})
        hist.append(now); RATE[ip]=hist
        try: n=int(self.headers.get('Content-Length','0'))
        except: n=0
        if n<1 or n>MAX_BODY: return self._json(413,{'ok':False,'error':'Некорректный размер запроса'})
        body=self.rfile.read(n)
        try: p=json.loads(body.decode())
        except: return self._json(400,{'ok':False,'error':'Некорректный JSON'})
        if self.path=='/api/pdf':
            if not (p.get('order') or []): return self._json(400,{'ok':False,'error':'Заказ пуст. Добавьте хотя бы одну позицию.'})
            try: return self._pdf(make_pdf(p,False),safe_filename(p.get('orderId'), '_SARMAT_DOORS.pdf'))
            except Exception as e: return self._json(500,{'ok':False,'error':f'PDF: {e}'})
        if self.path=='/api/final-pdf':
            if not (p.get('order') or []): return self._json(400,{'ok':False,'error':'Заказ пуст. Нельзя сформировать финальное КП.'})
            oid=str(p.get('orderId') or '')
            if oid not in SENT_ORDERS: return self._json(403,{'ok':False,'error':'Финальное КП доступно только после успешной отправки заказа в Telegram.'})
            try: return self._pdf(make_pdf(p,True),safe_filename(p.get('orderId'), '_SARMAT_DOORS_FINAL.pdf'))
            except Exception as e: return self._json(500,{'ok':False,'error':f'Final PDF: {e}'})
        if self.path=='/api/order':
            try:
                order=p.get('order') or []; total=sum(float(x.get('total',0) or 0)*int(x.get('qty',1) or 1) for x in order); qty=sum(int(x.get('qty',1) or 1) for x in order)
                c=p.get('customer') or {}; lines=[f'🟢 SARMAT DOORS — новая заявка',f'№ {p.get("orderId","—")}',f'Клиент: {c.get("company","")} / {c.get("person","")}',f'Телефон: {c.get("phone","")}',f'Дверей: {qty}',f'Позиций: {len(order)}',f'Итого: {money(total)}','']
                for i,x in enumerate(order,1): lines += [f'Позиция {i}: {x.get("doorType","Противопожарная")} {x.get("cls","—")} {x.get("w","—")}×{x.get("h","—")} · {x.get("qty",1)} шт.',f'Открывание: {x.get("opening","—")} · Сталь: {x.get("leafMm","—")}/{x.get("frameMm","—")} мм · RAL: {x.get("ralText","—")}',f'Фурнитура: {x.get("hwText","—")}',f'Доводчик: {"Да — "+money(400000) if x.get("closer") else "Нет"}',f'Примечание: {x.get("comment") or "—"}','']
                pdf=make_pdf(p,True)
                tg_send('\n'.join(lines)); tg_send_pdf(pdf,safe_filename(p.get('orderId'), '_SARMAT_DOORS_FINAL.pdf'),f'Финальное коммерческое предложение {p.get("orderId","SARMAT_DOORS")} · {qty} дверей · {money(total)}')
                SENT_ORDERS.add(str(p.get('orderId') or ''))
                return self._json(200,{'ok':True,'orderId':p.get('orderId'),'pdfSent':True,'finalPdf':True})
            except Exception as e: return self._json(502,{'ok':False,'error':f'Не удалось отправить заявку в Telegram: {e}'})
        if self.path=='/api/telegram-test':
            try: tg_send('🟢 ТЕСТ TELEGRAM — SARMAT DOORS\nСвязь сайта с рабочей группой проверена.'); return self._json(200,{'ok':True})
            except Exception as e: return self._json(502,{'ok':False,'error':str(e)})
        return self._json(404,{'ok':False,'error':'Not found'})
    def log_message(self,format,*args): pass

if __name__=='__main__':
    os.chdir(ROOT); port=int(os.environ.get('PORT','8080')); print(f'SARMAT DOORS APPROVED PDF V1: http://0.0.0.0:{port}'); ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
