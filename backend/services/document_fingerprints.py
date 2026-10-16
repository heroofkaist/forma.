"""Position-aware word fingerprints inspired by Schleimer et al. (SIGMOD 2003)."""
import hashlib
import re
import unicodedata
from collections import defaultdict

K, WINDOW, MIN_MATCH = 7, 5, 11
TOKEN = re.compile(r'[^\W_]+', re.UNICODE)


def tokenize(text):
    return [(unicodedata.normalize('NFKC', m[0]).casefold(), m.start(), m.end()) for m in TOKEN.finditer(text)]


def hashes(tokens):
    return [int.from_bytes(hashlib.blake2b('\x1f'.join(t[0] for t in tokens[i:i+K]).encode(), digest_size=8).digest(), 'big') for i in range(max(0,len(tokens)-K+1))]


def profile(text, context='', pages=()):
    text = text[:500000]
    tokens = tokenize(text)
    values = hashes(tokens)
    common = set(hashes(tokenize(context)))
    excluded = set()
    for i, value in enumerate(values):
        if value in common: excluded.update(range(i,i+K))
    selected = {}
    for start in range(max(0,len(values)-WINDOW+1)):
        window = [(values[i],-i,i) for i in range(start,start+WINDOW) if not any(j in excluded for j in range(i,i+K))]
        if window:
            value, _, index = min(window)
            selected[index] = value
    fingerprints = defaultdict(list)
    for index, value in selected.items(): fingerprints[value].append(index)
    locations, offset = [], 0
    for page in pages:
        part = page.get('text','')
        at = text.find(part,offset) if part else -1
        if at >= 0:
            locations.append((at,at+len(part),page.get('number'))); offset=at+len(part)
    return {'text':text,'tokens':tokens,'hashes':fingerprints,'excluded':excluded,'eligible':len(tokens)-len(excluded),'locations':locations}


def passage(source, start, end):
    a, b = source['tokens'][start][1], source['tokens'][end-1][2]
    page = next((n for x,y,n in source['locations'] if x <= a < y),None)
    return {'page':page,'start':a,'end':b,'quote':source['text'][a:b]}


def compare(a,b):
    if min(a['eligible'],b['eligible']) < MIN_MATCH:
        return {'status':'insufficient','score':None,'evidence':[]}
    spans=[]; covered_a=set(); covered_b=set(); operations=0
    for value in sorted(set(a['hashes'])&set(b['hashes'])):
        if len(a['hashes'][value])>20 or len(b['hashes'][value])>20: continue
        for i in a['hashes'][value]:
            for j in b['hashes'][value]:
                if operations>200000: break
                if any(a['tokens'][i+t][0]!=b['tokens'][j+t][0] for t in range(K)): continue
                if any(x<=i<y and p<=j<q and i-x==j-p for x,y,p,q in spans): continue
                x,y,p,q=i,i+K,j,j+K
                while x>0 and p>0 and x-1 not in a['excluded'] and p-1 not in b['excluded'] and a['tokens'][x-1][0]==b['tokens'][p-1][0]:
                    x-=1;p-=1;operations+=1
                    if operations>200000: break
                while y<len(a['tokens']) and q<len(b['tokens']) and y not in a['excluded'] and q not in b['excluded'] and a['tokens'][y][0]==b['tokens'][q][0]:
                    y+=1;q+=1;operations+=1
                    if operations>200000: break
                if y-x>=MIN_MATCH:
                    spans.append((x,y,p,q));covered_a.update(range(x,y));covered_b.update(range(p,q))
    spans.sort(key=lambda s:s[1]-s[0],reverse=True)
    evidence=[]
    for x,y,p,q in spans[:10]:
        # Bound the displayed quote while keeping exact original offsets.
        end=min(y,x+80);other=min(q,p+80)
        evidence.append({'current':passage(a,x,end),'candidate':passage(b,p,other),'matched_words':y-x})
    ca,cb=len(covered_a)/a['eligible'],len(covered_b)/b['eligible']
    return {'status':'completed','score':round(min(ca,cb),6),'evidence':evidence,
        'coverage_current':round(ca,6),'coverage_candidate':round(cb,6),
        'matched_words_current':len(covered_a),'eligible_words_current':a['eligible'],
        'matched_words_candidate':len(covered_b),'eligible_words_candidate':b['eligible'],
        'common_words_excluded_current':len(a['excluded']),'common_words_excluded_candidate':len(b['excluded']),
        'bounded':operations>200000}
