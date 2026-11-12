"""사이트와 같은 조문·연혁 데이터로 경사형 연혁집 보완 PDF를 만든다.

현재 본문과 기존 55개 연혁을 보존하고, 검토한 종전 기술조항을 해당 조항 아래에 둔다.
수식·표·그림은 검토한 원문 이미지로, 후반 검사자료는 원본 PDF 페이지로 보존한다.
"""
import argparse
import hashlib
from html import escape
from functools import lru_cache
import io
import json
import os
from pathlib import Path
import re

from PIL import Image as PILImage
import pymupdf
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                              Spacer, PageBreak, Image, LongTable, TableStyle, Flowable)
from reportlab.platypus.tableofcontents import TableOfContents

BASE = Path(__file__).parent
ROOT = BASE.parent
FIG = re.compile(r'\x10([^|\x11]+)\|(\d+)\|(\d+)(?:\x0e([^\x11]*))?\x11')
GRAY = colors.HexColor('#f1f1f1')


class SourcePage(Flowable):
    def __init__(self, source_page, title=None):
        super().__init__()
        self.source_page, self.section_title = source_page, title
        self.width, self.height = 470, 680
    def draw(self):
        pass


class BookDoc(BaseDocTemplate):
    def beforeDocument(self):
        self.clause_pages, self.source_pages = {}, {}
    def afterFlowable(self, flow):
        if hasattr(flow,'clause'):
            self.clause_pages[flow.clause]=self.page
        title = getattr(flow,'section_title',None)
        if title:
            key='section-'+str(self.page)
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title,key,level=0)
            self.notify('TOCEntry',(0,markup(title),self.page,key))
        if isinstance(flow,SourcePage):
            self.source_pages[self.page]=flow.source_page


def register_fonts():
    folder=Path(os.environ.get('KIJUN_FONT_DIR','C:/Windows/Fonts'))
    pdfmetrics.registerFont(TTFont('BookBody',str(folder/'batang.ttc'),subfontIndex=0))
    pdfmetrics.registerFont(TTFont('BookSans',str(folder/'malgun.ttf')))
    pdfmetrics.registerFont(TTFont('BookBold',str(folder/'malgunbd.ttf')))
    pdfmetrics.registerFont(TTFont('BookSymbols',str(folder/'times.ttf')))
    pdfmetrics.registerFontFamily('BookBody',normal='BookBody',bold='BookBold')
    pdfmetrics.registerFontFamily('BookSans',normal='BookSans',bold='BookBold')


def plain(text):
    return re.sub(r'[\x01-\x08\x0e-\x11]','',text)


def rich_text(text):
    return markup(plain(text)).replace('\n','<br/>')


@lru_cache(maxsize=1)
def font_support():
    maps={name:pdfmetrics.getFont(name).face.charToGlyph for name in ('BookBody','BookSans','BookBold','BookSymbols')}
    common=set(maps['BookBody']) & set(maps['BookSans']) & set(maps['BookBold'])
    return maps,common


def markup(text):
    """한글 글꼴에 없는 중점·로마숫자 XI/XII를 누락시키지 않는다."""
    maps,common=font_support()
    out=[]
    for char in text:
        escaped=escape(char)
        if ord(char) in common or char.isspace():out.append(escaped)
        else:
            font=next((name for name in ('BookSymbols','BookSans','BookBody') if ord(char) in maps[name]),None)
            if font is None:raise ValueError('PDF 글꼴에 없는 원문 문자: '+repr(char))
            out.append(f'<font name="{font}">{escaped}</font>')
    return ''.join(out)


def image_flow(filename,width,height,max_width=470,max_height=650):
    path=BASE/'fig'/filename
    if not path.exists():path=ROOT/'fig'/filename
    bitmap=PILImage.open(path).convert('RGB')
    stream=io.BytesIO();bitmap.save(stream,'PNG');stream.seek(0)
    factor=min(max_width/width,max_height/height)
    return Image(stream,width=width*factor,height=height*factor,hAlign='LEFT')


def contents(text,style,max_width=470,max_height=650):
    items=[];pos=0
    for match in FIG.finditer(text):
        before=text[pos:match.start()].strip()
        if before:items.append(Paragraph(rich_text(before),style))
        filename,width,height,_=match.groups()
        items.append(image_flow(filename,int(width),int(height),max_width,max_height))
        pos=match.end()
    tail=text[pos:].strip()
    if tail:items.append(Paragraph(rich_text(tail),style))
    return items


def sort_history(block):
    return block.get('from') or block.get('to') or block.get('sortdate') or '9'


def history_panel(block,styles):
    label=block.get('when_label') or block['head']
    rows=[[Paragraph('<b>종전 · '+markup(label)+'</b>',styles['history_head'])]]
    if label!=block['head'] and not block.get('legacy_supplement'):
        rows.append([Paragraph(markup(block['head']),styles['history_source'])])
    if block.get('scope'):
        rows.append([Paragraph('대상 조항: '+markup(block['scope']),styles['history_source'])])
    if block.get('g'):
        rows.append([Paragraph('<b>기술 요지</b> · '+markup(block['g']),styles['history'])])
    if block.get('legacy_supplement'):
        when='준용한 일반기준의 적용일. 개별 특례 인정일·준용판은 해당 설비의 인정서와 대조.'
        rows.append([Paragraph('구 '+markup(block['old_num'])+' · '+markup(block['applies_to'])+'<br/>'+markup(when),styles['history_source'])])
    elif block.get('date_unknown'):
        rows.append([Paragraph(markup(block['date_note']),styles['history_source'])])
    # 문단별 행으로 나누어 긴 연혁을 다음 쪽으로 자연스럽게 이어간다.
    body_start=len(rows)
    for text in re.split(r'\n+',block['text']):
        for flow in contents(text,styles['history'],448,590):
            rows.append([flow])
    if block.get('source'):
        rows.append([Paragraph('원문: '+markup(block['source']),styles['history_source'])])
    if block.get('figure_source'):
        rows.append([Paragraph('참고그림: '+markup(block['figure_source']),styles['history_source'])])
    keep_through=min(body_start,len(rows)-1)
    while keep_through>1 and sum(row[0].wrap(450,700)[1]+9 for row in rows[:keep_through+1])>680:
        keep_through-=1
    table=LongTable(rows,colWidths=[470],repeatRows=1,hAlign='LEFT',splitByRow=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),GRAY),
        ('LINEABOVE',(0,0),(-1,0),.5,colors.HexColor('#bbbbbb')),
        ('LINEBELOW',(0,-1),(-1,-1),.5,colors.HexColor('#bbbbbb')),
        ('NOSPLIT',(0,0),(-1,keep_through)),
        ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    return [table,Spacer(1,10)]


def build_book(output):
    register_fonts()
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    data=json.loads((BASE/'data.json').read_text(encoding='utf-8'))
    review=json.loads((BASE/'hist_incline/legacy_technical.json').read_text(encoding='utf-8'))
    entries=[e for e in data['b23'] if not e.get('group')]
    history=data['hist_incline']
    styles={
        'body':ParagraphStyle('body',fontName='BookBody',fontSize=10.5,leading=17,wordWrap='CJK',spaceAfter=8),
        'heading':ParagraphStyle('heading',fontName='BookBold',fontSize=11,leading=17,wordWrap='CJK',spaceBefore=9,spaceAfter=6,keepWithNext=True),
        'chapter':ParagraphStyle('chapter',fontName='BookBold',fontSize=14,leading=22,wordWrap='CJK',spaceBefore=15,spaceAfter=12,keepWithNext=True),
        'history':ParagraphStyle('history',fontName='BookSans',fontSize=8.8,leading=13.5,wordWrap='CJK'),
        'history_head':ParagraphStyle('history_head',fontName='BookBold',fontSize=9,leading=14,wordWrap='CJK'),
        'history_source':ParagraphStyle('history_source',fontName='BookSans',fontSize=8,leading=12,wordWrap='CJK',textColor=colors.HexColor('#555555')),
        'title':ParagraphStyle('title',fontName='BookBold',fontSize=30,leading=46,alignment=TA_CENTER,wordWrap='CJK'),
        'subtitle':ParagraphStyle('subtitle',fontName='BookSans',fontSize=15,leading=24,alignment=TA_CENTER,wordWrap='CJK'),
        'intro':ParagraphStyle('intro',fontName='BookSans',fontSize=9,leading=15,wordWrap='CJK',spaceAfter=12),
    }
    width,height=A4
    doc=BookDoc(str(output),pagesize=A4,leftMargin=62,rightMargin=63,topMargin=64,bottomMargin=52,
        title='경사형 엘리베이터 안전기준 연혁집 · 보완 v0.3',author='',
        subject='기술조항별 종전 유압식 특례 및 준용기준 보완')
    frame=Frame(62,52,470,height-116,id='body',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
    def page_header(canvas,document):
        if document.page==1:return
        canvas.saveState();canvas.setFont('BookSans',8);canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawRightString(width-63,height-35,'경사형 엘리베이터 안전기준 연혁집 · 보완 v0.3')
        canvas.setStrokeColor(colors.HexColor('#bbbbbb'));canvas.line(62,height-43,width-63,height-43)
        canvas.drawRightString(width-63,28,str(document.page))
        canvas.restoreState()
    doc.addPageTemplates(PageTemplate(id='book',frames=frame,onPage=page_header))
    story=[Spacer(1,110),Paragraph('경사형 엘리베이터<br/>안전기준 연혁집',styles['title']),
        Spacer(1,35),Paragraph('기술 연혁 보완 v0.3',styles['subtitle']),Spacer(1,12),
        Paragraph('2026. 11.',styles['subtitle']),Spacer(1,70),
        Paragraph('현행 기술 조항 아래에 종전 안전장치·구조·검사요건과 확인된 적용시점을 배치했습니다. 회색 연혁란은 해당 구조·준용기준의 적용 범위에 따라 읽습니다.',styles['intro']),
        Paragraph(escape(review['scope_note']),styles['intro']),PageBreak()]
    toc=TableOfContents()
    toc.levelStyles=[ParagraphStyle('toc',fontName='BookSans',fontSize=9.5,leading=16,wordWrap='CJK',leftIndent=0,rightIndent=20)]
    story.extend([Paragraph('목차',styles['chapter']),toc,PageBreak()])
    used_images=[]
    for entry in entries:
        chapter='.' not in entry['num']
        if chapter and story and not isinstance(story[-1],PageBreak):story.append(PageBreak())
        heading=Paragraph(markup(entry['num']+' '+entry['title']),styles['chapter'] if chapter else styles['heading'])
        heading.clause=entry['num']
        if chapter:heading.section_title=('부속서 ' if not entry['num'].isdigit() else '')+entry['num']+' '+entry['title']
        story.append(heading)
        if entry['text']:
            story.extend(contents(entry['text'],styles['body']))
            used_images.extend(m[0] for m in FIG.findall(entry['text']))
        for block in sorted(history.get(entry['num'],{}).get('blocks',[]),key=sort_history):
            story.extend(history_panel(block,styles))
            used_images.extend(m[0] for m in FIG.findall(block['text']))
        for ref in entry.get('unresolved_refs',[]):
            story.append(Paragraph(escape(ref['note']),styles['history_source']))
    for pn in range(161,208):
        story.append(PageBreak())
        title={161:'경사형 엘리베이터 설치검사기준',182:'경사형 엘리베이터 정밀안전검사기준',183:'검사방법·판정기준'}.get(pn)
        story.append(SourcePage(pn,title))
    doc.multiBuild(story)
    book=pymupdf.open(output)
    source=pymupdf.open(BASE/'hist_incline/hist.pdf')
    source[198].add_redact_annot(pymupdf.Rect(95,580,511,750),fill=(.92,.92,.92))
    source[198].apply_redactions(images=2,graphics=1,text=0)
    for target,pn in doc.source_pages.items():
        book[target-1].show_pdf_page(pymupdf.Rect(0,55,width,798),source,pn-1,
                                   clip=pymupdf.Rect(0,55,width,798))
    canonical=json.dumps({'b23':data['b23'],'hist_incline':history},ensure_ascii=False,sort_keys=True).encode()
    metadata=book.metadata
    metadata['keywords']='kijun-canonical-sha256:'+hashlib.sha256(canonical).hexdigest()
    book.set_metadata(metadata)
    final=output.with_name(output.stem+'.final.pdf')
    book.save(final,garbage=4,deflate=True)
    pages=len(book);book.close();source.close();final.replace(output)
    report=dict(version='v0.3',pages=pages,main_clauses=len(entries),history_blocks=sum(len(h['blocks']) for h in history.values()),
        source_appendix_pages=doc.source_pages,clause_pages=doc.clause_pages,
        images=used_images,canonical_sha256=hashlib.sha256(canonical).hexdigest(),
        pdf_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (BASE/'incline-book-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_appendix_pages','clause_pages','images')},ensure_ascii=False))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'output/pdf/경사형_엘리베이터_안전기준_연혁집_v0.3.pdf'))
    args=parser.parse_args()
    build_book(args.output)
