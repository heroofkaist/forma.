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

VERSION = 'whole-file-v2'
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
    image = ImageOps.grayscale(image)
    if image.width * image.height > 20_000_000:
        return None
    image.thumbnail((128,128))
    if ImageStat.Stat(image).stddev[0] < 10:
        return None  # Uniform and empty pages carry no visual comparison evidence.
    small = image.resize((32,32), Image.Resampling.LANCZOS)
    ink = bytes(255-v for v in small.getdata())
    if sum(v > 8 for v in ink) < 8:
        return None
    norm = math.sqrt(sum(v*v for v in ink))
    return {'ink': ink, 'norm': norm, 'digest': hashlib.sha256(ink).hexdigest()}


def visuals(content, kind, used):
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
                pix = page.get_pixmap(matrix=pymupdf.Matrix(128/edge,128/edge), colorspace=pymupdf.csGRAY, alpha=False)
                f = image_feature(Image.frombytes('L',(pix.width,pix.height),pix.samples))
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
                    continue
                with Image.open(io.BytesIO(archive.read(entry))) as image:
                    if image.width*image.height>20_000_000:
                        continue
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
    if not a or not b:
        return {'status':'insufficient', 'score':None, 'evidence':[]}
    best_a=[0.0]*len(a); best_b=[0.0]*len(b); evidence=[]
    for i,x in enumerate(a):
        for j,y in enumerate(b):
            score = sum(v*w for v,w in zip(x['ink'],y['ink']))/(x['norm']*y['norm'])
            if score >= .985:
                best_a[i]=max(best_a[i],score); best_b[j]=max(best_b[j],score)
                evidence.append({'current':{k:v for k,v in x.items() if k in ('page','asset','unit')},'candidate':{k:v for k,v in y.items() if k in ('page','asset','unit')},'score':round(score,6),'identical_thumbnail':x['digest']==y['digest']})
    # A single matching cover page must not turn a whole document into 100%.
    score=min(sum(best_a)/len(a),sum(best_b)/len(b))
    return {'status':'completed','score':round(min(1,score),6),'evidence':sorted(evidence,key=lambda e:e['score'],reverse=True)[:10],
            'matched_units_current':sum(v>0 for v in best_a),'matched_units_candidate':sum(v>0 for v in best_b),
            'units_current':len(a),'units_candidate':len(b)}



def analyze(payload):
    docs=payload['documents']
    if not 2 <= len(docs) <= MAX_WORKS:
        raise ValueError('Compare 2–40 works.')
    context=payload.get('context','')[:20000]
    profiles=[]; used=[0]; total=0
    for doc in docs:
        raw=base64.b64decode(doc['content'],validate=True); total+=len(raw)
        if len(raw)>30*1024*1024 or total>MAX_BYTES:
            raise ValueError('File limit exceeded.')
        text=doc.get('text',''); pages=doc.get('pages',[]); kind=doc['file_type']
        profiles.append({'text':text_features(text,context),'formula':formula_features(text), 'code':code_features(pages,kind),
                         'visual':visuals(raw,kind,used),'truncated':len(text)>MAX_CHARS, 'digest':hashlib.sha256(raw).hexdigest(),
                         'semantic':Counter(f['concept'].casefold() for f in doc.get('semantic_features',[])) if len(doc.get('semantic_features',[]))>=3 else Counter()})
    vectors={name:tfidf([p[name] for p in profiles]) for name in ('text','formula','code','semantic')}
    pairs=[]
    for i in range(len(docs)):
        for j in range(i+1,len(docs)):
            if docs[i]['student_id']==docs[j]['student_id']:
                continue
            metrics={}
            for name in ('text','formula','code','semantic'):
                a,b=vectors[name][i],vectors[name][j]
                metrics[name]={'status':'completed' if a and b else 'insufficient','score':round(cosine(a,b),6) if a and b else None,
                    'evidence':sorted(set(a)&set(b),key=lambda k:a[k]*b[k],reverse=True)[:10]}
            metrics['visual']=visual_signal(profiles[i]['visual'],profiles[j]['visual'])
            identical=profiles[i]['digest']==profiles[j]['digest']
            meaningful_identity=identical and bool(docs[i].get('text','').strip() or profiles[i]['visual'])
            eligible=[metrics[k]['score'] for k in ('text','code','visual') if metrics[k]['score'] is not None]
            metrics['document']={'status':'completed' if eligible or meaningful_identity else 'insufficient', 'score':1.0 if meaningful_identity else max(eligible) if eligible else None,
                'evidence':['Файлы полностью совпадают по SHA-256.'] if identical else [], 'identical_file':identical}
            if metrics['semantic']['status']=='completed':
                common=metrics['semantic']['evidence']
                metrics['semantic']['source_evidence']=[{'concept':concept,
                    'current':next((f for f in docs[i].get('semantic_features',[]) if f['concept'].casefold()==concept),None),
                    'candidate':next((f for f in docs[j].get('semantic_features',[]) if f['concept'].casefold()==concept),None)} for concept in common[:5]]
            pairs.append({'submission_id':docs[i]['id'],'candidate_id':docs[j]['id'],'metrics':metrics})
    return {'version':VERSION,'pairs':pairs,'documents':[{'id':d['id'],'student_id':d['student_id'],'file_name':d['file_name'],'file_type':d['file_type'],'truncated':p['truncated'],'units_total':len(d.get('pages',[])),'visual_units':len(p['visual']),'text_chars':len(d.get('text',''))} for d,p in zip(docs,profiles)],
            'context':context,'scope':'latest_attempt_per_student_in_assignment','limits':{'works':MAX_WORKS,'pages_or_images':MAX_PAGES,'text_chars_per_work':MAX_CHARS},
            'limitations':['TF-IDF is lexical, not semantic embeddings or proof of copying.','Formula strings are compared without proving algebraic equivalence.','Visual score aggregates matching nonblank pages/images across both files; shared templates can match and crops/rotation can be missed.','Code features abstract identifiers and literals; algorithms are not executed.', 'Semantic profiles are advisory Qwen-extracted concepts, not neural embeddings or proof of shared authorship.']}


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
