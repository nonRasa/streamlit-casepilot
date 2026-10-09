"""Persist assistant's blind, excerpt-assisted relevance judgments.

This is NOT an independent assessor or a model quality oracle. Explicitly
unreviewed windows stay null; neither source authority nor absent references
imply relevance/irrelevance. Exact pre-authored witness containment is an
auditable positive rule; other grades below record this session's blind review.
"""
import sys,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from casepilot.common import read_json,write_json,digest
from prepare_quality_v27_completion import RUN
from report_quality_v27_completion import labels

# Prefixes refer to variant-blind window hashes, never variant or rank.
# Deliberately not exhaustive: truncated/unreviewed text stays unjudged.
GRADES={
'D01':{0:'03792a8f 221aeb97 788aaa50 e157f1ee',1:'272443e2 2865146d 5fa847bb 698d5b5d 7c3a302f 81349015 95a84db8 b1b26731 e97092b9',2:'458eaad0 96301725 9d9797d5'},
'D02':{0:'33bbc4fb 440012b1 4f9448ad b5500eda b86626e0 db7170af f7f11cc1',1:'1eae0671 43df89a3 70b823ad aa3ba645 b3ec8463',2:'0df82520 8c6df7a1'},
'D03':{0:'222194d8 69ebb24e 6a207b9f 6c7273ca e5412295 eae26be5 f85fc11d',1:'0bb1d1bc 34f83bfd 4f9b4494 6ebb429c 756f2da3 841cc446 9cc0bdfe e2f9eb2c e818614f'},
'D04':{0:'0709fac9 179e0180 4abf09d1 611b2b14 8b21a503 a3c91dae bdfd3a07 f60f5238 f78da6bc',1:'2486a6bb 2e85f387 7758f95a 8d26af1b e5df83f7',2:'09c627a5 62726300'},
'D06':{0:'0bc67b64 14747e79 19553d03 1bf1ca44 1cf4db76 5964277f 5f98b9f9 db9f7748 fee6f720',2:'6865d8ae ab1b412d bbed10c4 d9501781 daee925a f4ff3aa8'},
'D07':{0:'7ba36a3d e75ec4d0',1:'1247315c 42391042 6fa10d2d 72888b69 a14fc948 d0f0f935 d6f08eee f021a764 fc66dbc1',2:'35afe75e 589df5a8 5d5795f3 d49e6dd0'},
'D08':{0:'27fbeb7c f725782b',1:'214d64bc 7a907b41 b252346e c77655e7 f1acb3dd',2:'0fd0706c 76225a0a 3a00a2e8 9355c124 94a0acc3 9957844b efb94b02'},
'D09':{0:'95a84db8',1:'1237de73 1ab51d05 23c37a79 252de886 2e85f387 39ef2f92 7b0b7353 872450e3 936dc7d6 a4ad5d15 ca122efc f22c092f f5a89a2b faef549a'},
'D10':{0:'134686e4 40309773 4b639561 c92d5fc2',1:'44ad791f 6fa10d2d efd830c9',2:'058fcd60 20c00330',3:'8f89a4ae'},
'D11':{0:'04c4c76f 46b21302 e19b0617 e2f9eb2c',1:'115d2f29 2d06b570 4dad9f75 4eb78f27 5f5fa891 73bf350e aabf38cd af1fe259 dc793109 ef23878a',3:'97642c2f'},
'D12':{0:'2e332ceb 9504b58a 989f20d9',1:'19553d03 1cf4db76 1eae0671 26fc958b 30409bac 473270c6 5f98b9f9 7a2d82c4 a15feb9f b5500eda b86626e0 db9f7748',2:'3171ca7e db7170af'},
'H01':{0:'04115433 4b0e49cd cc3a9882 ef7fcf82',1:'018f9bec 0c30d993 23d355f1 71f08e72 7d894d02 b4ff9774',2:'3a611859 a15bcd5f',3:'310c0488 7f341a5b'},
'H02':{0:'13cbcecc 36f475f5 3ba57db4 5af8b7a4 62e830e3 751282ab bc1f5dcb be89b355 c8705bf6 ff633563',1:'0cc1fc15 57fc4288 6019d3ae 6f39c693 9294f670 e78688ee e8bcfdca'},
'H03':{0:'440012b1 53ed3e35 57d1b469 f7f11cc1',1:'1667ff8d 20f664de 24051aa4 4dbdfec0 54cbc631 5561b8b9 ad1b8861 baef6793',2:'4d28f94b'},
'H04':{0:'0a41d797 222194d8 9c665ee9 d495d386',1:'16fc3379 4ba32900 595b1bd2 5ef48080 7810ec83 a2561d93 a6614d56 a75b60ec bb7882e9 cacd5235 d0a67374 f85fc11d'},
'H05':{0:'60d53f62 949b8c50 a1ec7b62 b322a29b',1:'1cb81263 6c793d49 71a06370 ad45e9f6 d495d386 d7239bfe',2:'0e53f6a3 593388d3 82bc8436 8ea2d3d1 b9f0e4b4 efe07574'},
'H07':{0:'8266b9a0 d9d72990',1:'2704d856 31cbd974 44f3952b 71176f23 780f68e5 fa90cf90',2:'09008605 22c116c6 6c0992e8 7f40afb0 8f010876 9fb2f968 cbc468ab'},
'H08':{0:'010c8d2a 8f0a8428',1:'05e3f081 0fed07a0 2775a41d 2b279b62 71176f23 7a59a1d0 7c1ea0b7 ccadb46b',2:'31cbd974 44f3952b 56389f50 8afd1e39',3:'6c0992e8 7665c958 ccecb3f7'},
'H09':{0:'4ee7b70f 8b21a503 a70d0f4f b9c6806e',1:'1c61ecb7 565c813d 6f113ce3 9359f005 f4ba50b2',2:'3c077106 50bdba6e 5b3390cb',3:'8c583598 daa84ed4'},
'H10':{0:'0da8b5d5 46b21302 46d649a9 7fe7fa50 90af5a03 9972dd0c a5866392 e19b0617 f3455cc4',1:'2f7b6364 f01258cf fb036eac',2:'66c40d69 7e6bf248'},
'H11':{0:'38c23b27 46280794 621189dc 882b1c40 92b2d95f 9eb970a0 a3c0b566 a94e9518 bdc633ef da7be034',1:'418adaf3 5eae05d7 ac757097',2:'7915ae2d'},
'H12':{0:'2ecb408c 6980ceda 86127231 adc35afb f71e7cd6',1:'0aae5673 2f74f93e 48891a54 54a999fa 77b43988 abd94da3 ace7e748 d34de48b da7be034 df1753d4 e48573fd fd83f71f'},
}


def main():
    target=RUN/'pool_judgments.json';assert not target.exists(),'Keep completed judgments immutable.'
    labs=labels();out={};counts={0:0,1:0,2:0,3:0,None:0}
    for cid,label in labs.items():
        revised=RUN/'blind_pool_revised'/(cid+'.json');path=revised if revised.exists() else RUN/'blind_pool'/(cid+'.json')
        packet=read_json(path);case={}
        manual={p:g for g,ps in GRADES.get(cid,{}).items() for p in ps.split()}
        for row in packet['candidates']:
            key=row['candidate_key'];grade=None;quote=None;origin=None;reason='Full relevance not certified; retained as unjudged.'
            anchors=[w for w in label['required_evidence'] if w['source_id']==row['source_id'] and w['quote'] in row['text']]
            if anchors:
                grade=3;quote=anchors[0]['quote'];origin='assistant reference + exact containment rule, not independent'
                reason='Contains the behavior-bearing, preregistered source witness verbatim; relevance and version applicability remain separate.'
            elif key[:8] in manual:
                grade=manual[key[:8]];origin='assistant blind excerpt-assisted review in this session, not independent'
                reason={0:'Inspected excerpt concerns a different behavior or only empty/administrative context.',
                        1:'Related topic/report/example but does not establish the requested behavior or cause.',
                        2:'Useful partial requirement/procedure/context; not a complete answer or proof of cause.',
                        3:'Inspected source passage directly describes the requested behavior.'}[grade]
                quote=row['text'][:650]
            elif cid in ('D05','H06'):
                assert not any(w in row['text'] for w in ('MoonBridge','EZX991','ZephyrQ','ZX77'))
                grade=0;origin='assistant out-of-domain review + identity absence check, not independent'
                reason='Streamlit source does not establish this undocumented private vendor/device error.'
                quote=row['text'][:300]
            counts[grade]+=1
            case[key]={'grade':grade,'origin':origin,'reason':reason,'review_excerpt':quote,
                       'excerpt_assisted_not_exhaustive':True,'human':False,'independent':False,
                       'source_id':row['source_id'],'source_span':row['source_span'],'revision':row['revision']}
        out[cid]=case
    write_json(target,{'origin':'Assistant blind excerpt-assisted judgments and explicit witness containment rules; not human, not independent; not exhaustive semantic annotation.',
        'limitations':'Relevance positives do not prove causality, version applicability or independent quality. Excerpt review can miss tail context. Unlisted windows remain null.',
        'cases':out,'counts':{str(k):v for k,v in counts.items()},'frozen_before_metric_computation':True,
        'pool_hashes':{cid:digest(out[cid]) for cid in out}})
    print('Judgments frozen:',counts)

if __name__=='__main__':main()
