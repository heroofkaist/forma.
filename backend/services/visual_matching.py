"""Local ORB matching with geometric verification; no handwriting identity claims."""
import hashlib
import math
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import cv2
import numpy as np
from PIL import ImageOps, ImageStat

cv2.setNumThreads(1)


def feature(image):
    image=ImageOps.grayscale(image)
    if image.width*image.height>20000000: return None
    image.thumbnail((850,850))
    if ImageStat.Stat(image).stddev[0]<10: return None
    array=np.asarray(image)
    keypoints,descriptors=cv2.ORB_create(nfeatures=700,fastThreshold=12).detectAndCompute(array,None)
    if descriptors is None: descriptors=np.empty((0,32),dtype=np.uint8)
    points=np.float32([k.pt for k in keypoints]).reshape(-1,2)
    return {'points':points,'descriptors':descriptors,'width':image.width,'height':image.height,
        'digest':hashlib.sha256(array.tobytes()+str(array.shape).encode()).hexdigest(),'baseline_removed':0}


def alignment(a,b):
    da,db=a['descriptors'],b['descriptors']
    if min(len(da),len(db))<14: return None
    matcher=cv2.BFMatcher(cv2.NORM_HAMMING)
    forward=matcher.knnMatch(da,db,k=2);backward=matcher.knnMatch(db,da,k=2)
    reverse={(m.queryIdx,m.trainIdx) for pair in backward if len(pair)==2 for m,n in [pair] if m.distance<.72*n.distance}
    matches=[m for pair in forward if len(pair)==2 for m,n in [pair] if m.distance<.72*n.distance and (m.trainIdx,m.queryIdx) in reverse]
    if len(matches)<14: return None
    aa=np.float32([a['points'][m.queryIdx] for m in matches]);bb=np.float32([b['points'][m.trainIdx] for m in matches])
    matrix,mask=cv2.findHomography(aa,bb,cv2.RANSAC,3.5,maxIters=1200,confidence=.995)
    if matrix is None or mask is None or not np.isfinite(matrix).all(): return None
    keep=mask.ravel().astype(bool);inliers=int(keep.sum())
    if inliers<12 or inliers/len(matches)<.65: return None
    areas=[cv2.contourArea(cv2.convexHull(points[keep]))/(doc['width']*doc['height']) for points,doc in ((aa,a),(bb,b))]
    if min(areas)<.025: return None
    # Homography must map a finite, non-folded image with a plausible area.
    corners=np.float32([[0,0],[a['width'],0],[a['width'],a['height']],[0,a['height']]]).reshape(-1,1,2)
    mapped=cv2.perspectiveTransform(corners,matrix)
    if not np.isfinite(mapped).all() or not cv2.isContourConvex(mapped) or not .04<abs(cv2.contourArea(mapped))/(b['width']*b['height'])<25: return None
    def region(points,doc):
        x,y,w,h=cv2.boundingRect(points[keep])
        return {'x':round(max(0,x)/doc['width'],6),'y':round(max(0,y)/doc['height'],6),
            'width':round(min(w,doc['width']-max(0,x))/doc['width'],6),'height':round(min(h,doc['height']-max(0,y))/doc['height'],6)}
    return {'inliers':inliers,'inlier_ratio':round(inliers/len(matches),6),'area_current':float(areas[0]),'area_candidate':float(areas[1]),
        'current_region':region(aa,a),'candidate_region':region(bb,b),
        'indices_current':[matches[i].queryIdx for i in range(len(matches)) if keep[i]],
        'indices_candidate':[matches[i].trainIdx for i in range(len(matches)) if keep[i]]}


def remove_baseline(document,baselines):
    removed=set()
    for baseline in baselines:
        if document['digest']==baseline['digest']:
            return {**document,'points':document['points'][:0],'descriptors':document['descriptors'][:0],'all_baseline':True,'baseline_removed':len(document['points'])}
        match=alignment(document,baseline)
        if match: removed.update(match['indices_current'])
    if removed:
        keep=[i for i in range(len(document['points'])) if i not in removed]
        document={**document,'points':document['points'][keep],'descriptors':document['descriptors'][keep], 'baseline_removed':len(removed)}
    return document


def signal(a,b):
    if not a or not b or not any(not x.get('all_baseline') for x in a) or not any(not x.get('all_baseline') for x in b): return {'status':'insufficient','score':None,'evidence':[]}
    best_a=[0.0]*len(a);best_b=[0.0]*len(b);evidence=[]
    for i,x in enumerate(a):
        for j,y in enumerate(b):
            if x.get('all_baseline') or y.get('all_baseline'): continue
            match=alignment(x,y)
            identical=x['digest']==y['digest']
            if not match and not identical: continue
            value=1.0 if identical else min(1.0,math.sqrt(min(match['area_current'],match['area_candidate']))*match['inlier_ratio'])
            best_a[i]=max(best_a[i],value);best_b[j]=max(best_b[j],value)
            evidence.append({'current':{k:v for k,v in x.items() if k in ('page','asset','unit')},
                'candidate':{k:v for k,v in y.items() if k in ('page','asset','unit')},'score':round(value,6),'identical_thumbnail':identical,
                'method':'orb_ransac','inliers':match['inliers'] if match else len(x['points']),
                'current_region':match['current_region'] if match else {'x':0,'y':0,'width':1,'height':1},
                'candidate_region':match['candidate_region'] if match else {'x':0,'y':0,'width':1,'height':1}})
    return {'status':'completed','score':round(min(sum(best_a)/len(a),sum(best_b)/len(b)),6),
        'evidence':sorted(evidence,key=lambda e:e['score'],reverse=True)[:10],
        'matched_units_current':sum(v>0 for v in best_a),'matched_units_candidate':sum(v>0 for v in best_b),
        'units_current':len(a),'units_candidate':len(b),'common_keypoints_removed':sum(x.get('baseline_removed',0) for x in a+b)}
