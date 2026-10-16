"""Bounded local comparison signals; no inference, execution of code or misconduct verdict."""
import ast
import base64
import hashlib
import io
import json
import keyword
import math
import re
import unicodedata
import zipfile
from collections import Counter
from PIL import Image, ImageOps, ImageStat
import pymupdf

VERSION = 'whole-file-v3-geometric-winnowing'
MAX_WORKS = 40
MAX_PAGES = 200
MAX_BYTES = 60 * 1024 * 1024
MAX_CHARS = 500000
STOP = set('the a an and or of to in is are for with this that и в во на с со к от по из для или это как что'.split())
WORDS = re.compile(r'[^\W_]+', re.UNICODE)
FORMULA = re.compile(r'[=∫∑√≤≥≈]')
CODE = {'py','js','ts','tsx','jsx','java','c','cpp','h','rs','go','sql','zip'}
KEYWORDS = set(keyword.kwlist) | set('function return if else for while class const let var public private static void int float double import export new switch case break continue null true false'.split())


def words(text):
    return [w for w in WORDS.findall(unicodedata.normalize('NFKC', text).casefold()) if len(w) > 1 and w not in STOP]


def grams(tokens, n):
    return Counter(' '.join(tokens[i:i+n]) for i in range(len(tokens)-n+1))


def text_features(text, context):
    tokens = words(text[:MAX_CHARS])
    counts = Counter(tokens)
    counts.update(grams(tokens, 2))
    common = Counter(words(context)); common.update(grams(words(context), 2))
    for key in common:
        counts.pop(key, None)
    return Counter(dict(counts.most_common(8000))) if len(tokens) >= 8 else Counter()


def formula_features(text):
    lines = [unicodedata.normalize('NFKC', line).casefold() for line in text[:MAX_CHARS].splitlines() if FORMULA.search(line) and len(line) <= 300]
    return Counter(line.replace(' ', '') for line in lines if len(line.strip()) >= 5)


def code_features(pages, kind):
    if kind not in CODE:
        return Counter()
    counts = Counter()
    for page in pages[:200]:
        text = page.get('text', '')[:MAX_CHARS]
        # Identifiers and literals are abstracted; no code is compiled or executed.
        tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\b\w+\b|[^\w\s]', text)
        tokens = [t if t in KEYWORDS or not (t[0].isalnum() or t[0] in '_\"\'') else 'NUM' if t[0].isdigit() else 'STR' if t[0] in '\"\'' else 'ID' for t in tokens]
        if len(tokens) >= 20:
            counts.update(grams(tokens[:20000], 5))
        if kind == 'py' or page.get('file_name','').endswith('.py'):
            try:
                tree = ast.parse(text)
                nodes = [type(node).__name__ for node in ast.walk(tree)]
                if 12 <= len(nodes) <= 12000:
                    counts.update({'AST:'+k:v for k,v in grams(nodes, 4).items()})
            except (SyntaxError, ValueError, RecursionError, MemoryError):
                pass
    return Counter(dict(counts.most_common(8000)))


def image_feature(image):
    if __package__: from .visual_matching import feature
    else: from visual_matching import feature
    return feature(image)


def visuals(content, kind, used, context=""):
    result = []
    if kind == 'pdf':
        with pymupdf.open(stream=content, filetype='pdf') as doc:
            if doc.needs_pass or not 1 <= doc.page_count <= 50 or used[0]+doc.page_count > MAX_PAGES:
                raise ValueError('Page limit exceeded.')
            used[0] += doc.page_count
            for index,page in enumerate(doc):
                edge = max(page.rect.width,page.rect.height)
                if edge <= 0:
                    continue
                pix = page.get_pixmap(matrix=pymupdf.Matrix(850/edge,850/edge), colorspace=pymupdf.csGRAY, alpha=False)
                image = Image.frombytes('L',(pix.width,pix.height),pix.samples)
                # Mask exact teacher-supplied task lines, leaving the original
                # intact. Geometric baseline matching handles shared drawings.
                from PIL import ImageDraw
                draw = ImageDraw.Draw(image)
                for line in context.splitlines()[:100]:
                    if len(line.strip()) < 18: continue
                    for box in page.search_for(line.strip()[:500]):
                        box = box * page.rotation_matrix
                        draw.rectangle((box.x0*850/edge,box.y0*850/edge,box.x1*850/edge,box.y1*850/edge), fill=255)
                f = image_feature(image)
                if f:
                    result.append({'page':index+1, 'unit':'page', **f})
    elif kind in {'docx','pptx'}:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if len(archive.infolist()) > 3000:
                raise ValueError('Archive entry limit exceeded.')
            images = [e for e in archive.infolist() if '/media/' in e.filename and e.filename.lower().endswith(('.png','.jpg','.jpeg'))]
            if len(images)>50 or sum(e.file_size for e in images)>30*1024*1024 or used[0]+len(images)>MAX_PAGES:
                raise ValueError('Image limit exceeded.')
            used[0] += len(images)
            for entry in images:
                if entry.file_size > 5*1024*1024:
                    raise ValueError('An embedded image exceeds the supported size.')
                with Image.open(io.BytesIO(archive.read(entry))) as image:
                    if image.width*image.height>20_000_000:
                        raise ValueError('An embedded image exceeds the supported dimensions.')
                    f=image_feature(image)
                    if f:
                        result.append({'asset':entry.filename,'unit':'embedded_image',**f})
    return result


def tfidf(counters):
    frequency = Counter(key for counts in counters for key in counts)
    vectors=[]
    for counts in counters:
        v={k:(1+math.log(n))*(1+math.log((1+len(counters))/(1+frequency[k]))) for k,n in counts.items()}
        norm=math.sqrt(sum(n*n for n in v.values()))
        vectors.append({k:n/norm for k,n in v.items()} if norm else {})
    return vectors


def cosine(a,b):
    if len(a)>len(b): a,b=b,a
    return min(1.0,max(0.0,sum(v*b.get(k,0) for k,v in a.items())))


def visual_signal(a,b):
    if __package__: from .visual_matching import signal
    else: from visual_matching import signal
    return signal(a,b)



def analyze(payload):
    docs=payload['documents']
    if not 2 <= len(docs) <= MAX_WORKS:
        raise ValueError('Compare 2–40 works.')
    context=payload.get('context','')[:20000]
    if __package__:
        from . import document_fingerprints as fingerprints
        from .visual_matching import remove_baseline
    else:
        import document_fingerprints as fingerprints
        from visual_matching import remove_baseline
    profiles=[]; used=[0]; total=0; baselines=[]
    for baseline in payload.get('baselines',[])[:6]:
        raw=base64.b64decode(baseline['content'],validate=True); total+=len(raw)
        if total>MAX_BYTES: raise ValueError('Baseline file limit exceeded.')
        baselines.extend(visuals(raw,baseline['file_type'],used))
    for doc in docs:
        raw=base64.b64decode(doc['content'],validate=True); total+=len(raw)
        if len(raw)>30*1024*1024 or total>MAX_BYTES:
            raise ValueError('File limit exceeded.')
        text=doc.get('text',''); pages=doc.get('pages',[]); kind=doc['file_type']
        profiles.append({'text':text_features(text,context),'formula':formula_features(text), 'code':code_features(pages,kind),
                         'visual':[remove_baseline(v,baselines) for v in visuals(raw,kind,used,context)],'fingerprints':fingerprints.profile(text,context,pages),'truncated':len(text)>MAX_CHARS, 'digest':hashlib.sha256(raw).hexdigest(),
                         'semantic':Counter(f['concept'].casefold() for f in doc.get('semantic_features',[])) if len(doc.get('semantic_features',[]))>=3 else Counter()})
    vectors={name:tfidf([p[name] for p in profiles]) for name in ('text','formula','code','semantic')}
    pairs=[]
    for i in range(len(docs)):
        for j in range(i+1,len(docs)):
            if payload.get('target_id') and payload['target_id'] not in {docs[i]['id'],docs[j]['id']}: continue
            if docs[i]['student_id']==docs[j]['student_id']:
                continue
            metrics={}
            for name in ('text','formula','code','semantic'):
                a,b=vectors[name][i],vectors[name][j]
                metrics[name]={'status':'completed' if a and b else 'insufficient','score':round(cosine(a,b),6) if a and b else None,
                    'evidence':sorted(set(a)&set(b),key=lambda k:a[k]*b[k],reverse=True)[:10]}
            metrics['passages']=fingerprints.compare(profiles[i]['fingerprints'],profiles[j]['fingerprints'])
            metrics['visual']=visual_signal(profiles[i]['visual'],profiles[j]['visual'])
            identical=profiles[i]['digest']==profiles[j]['digest']
            meaningful_identity=identical and bool(profiles[i]['fingerprints']['eligible']>=4 or metrics['code']['score'] is not None or any(not v.get('all_baseline') for v in profiles[i]['visual']))
            eligible=[metrics[k]['score'] for k in ('passages','code','visual') if metrics[k]['score'] is not None]
            metrics['document']={'status':'completed' if eligible or meaningful_identity else 'insufficient', 'score':1.0 if meaningful_identity else max(eligible) if eligible else None,
                'evidence':['Файлы полностью совпадают по SHA-256.'] if identical else [], 'identical_file':identical,'common_material_excluded':bool(context.strip() or baselines),
                'partial':profiles[i]['truncated'] or profiles[j]['truncated'] or metrics['passages'].get('bounded',False)}
            if metrics['semantic']['status']=='completed':
                common=metrics['semantic']['evidence']
                metrics['semantic']['source_evidence']=[{'concept':concept,
                    'current':next((f for f in docs[i].get('semantic_features',[]) if f['concept'].casefold()==concept),None),
                    'candidate':next((f for f in docs[j].get('semantic_features',[]) if f['concept'].casefold()==concept),None)} for concept in common[:5]]
            pairs.append({'submission_id':docs[i]['id'],'candidate_id':docs[j]['id'],'metrics':metrics})
    return {'version':VERSION,'pairs':pairs,'documents':[{'id':d['id'],'student_id':d['student_id'],'file_name':d['file_name'],'file_type':d['file_type'],'truncated':p['truncated'],'units_total':len(d.get('pages',[])),'visual_units':len(p['visual']),'text_chars':len(d.get('text',''))} for d,p in zip(docs,profiles)],
            'context':context,'scope':'authorized_files_different_authors','limits':{'works':MAX_WORKS,'pages_or_images':MAX_PAGES,'text_chars_per_work':MAX_CHARS},
            'limitations':['Long matching passages use word winnowing with original offsets. TF-IDF is supplemental and never the document index. All signals require teacher review.','Formula strings are compared without proving algebraic equivalence.','ORB feature matches require RANSAC geometric agreement; visual index is not the percentage of copied content. Rewritten handwriting and heavily changed images may be missed. Known task material is excluded where found.','Code features abstract identifiers and literals; algorithms are not executed.', 'Semantic profiles are advisory Qwen-extracted concepts, not neural embeddings or proof of shared authorship.']}


if __name__ == '__main__':
    import sys
    try:
        import resource
        # Linux workers have a hard address-space/CPU ceiling; parent also enforces wall time.
        if sys.platform.startswith('linux'):
            resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(25,25))
        value=analyze(json.load(sys.stdin))
        print(json.dumps(value,ensure_ascii=False,allow_nan=False))
    except Exception:
        print(json.dumps({'error':'Local comparison could not complete within supported limits.'}))
        sys.exit(1)
