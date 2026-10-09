"""Fetch a pinned official docs tree plus versioned API docstrings."""
import ast, concurrent.futures, hashlib, re
from collect_data import ROOT, COMMIT, fetch, write

DOC_PATHS=[
 'develop/concepts/architecture/session-state',
 'develop/concepts/architecture/widget-behavior',
 'develop/concepts/architecture/caching',
 'develop/concepts/architecture/forms',
 'develop/concepts/architecture/fragments',
 'develop/concepts/architecture/architecture',
 'develop/concepts/app-design/button-behavior-and-examples',
 'develop/concepts/multipage-apps/overview',
 'develop/concepts/multipage-apps/page-and-navigation',
 'develop/concepts/multipage-apps/widgets',
 'develop/concepts/configuration/static-file-serving',
 'develop/api-reference/caching-and-state/session_state',
 'develop/api-reference/caching-and-state/cache-data',
 'develop/api-reference/caching-and-state/cache-resource',
 'develop/api-reference/caching-and-state/context',
 'develop/api-reference/widgets/file_uploader',
 'develop/api-reference/navigation/navigation',
 'develop/api-reference/navigation/page',
 'kb/FAQ/serializable-session-state',
 'kb/FAQ/widget-updating-session-state',
 'develop/quick-references/release-notes/2023',
 'develop/quick-references/release-notes/2024',
 'develop/quick-references/release-notes/2025',
 'develop/quick-references/release-notes/2026',
 'develop/concepts/custom-components/components-v2/state-and-triggers',
 'develop/concepts/app-design/dataframes',
 'develop/concepts/configuration/theming',
 'develop/concepts/app-testing/get-started',
 'develop/api-reference/caching-and-state/query_params',
 'develop/api-reference/layout/bottom',
 'develop/api-reference/configuration/config-toml',
 'develop/api-reference/configuration/set_page_config',
 'develop/tutorials/multipage-apps/dynamic-navigation',
 'kb/FAQ/where-file-uploader-store-when-deleted',
]

def collect_doc(path):
    raw_url=f'https://raw.githubusercontent.com/streamlit/docs/{COMMIT}/content/{path}.md'
    text=fetch(raw_url)
    source_id='docs:'+path.rsplit('/',1)[-1]
    kind='release' if 'release-notes/' in path else 'docs'
    return {'id':source_id,'kind':kind,'title':path.rsplit('/',1)[-1], 'text':text,
            'url':f'https://github.com/streamlit/docs/blob/{COMMIT}/content/{path}.md',
            'official_url':'https://docs.streamlit.io/'+path.replace('quick-references','quick-reference'),
            'revision':COMMIT,'product_version':None, 'source_path':'content/'+path+'.md',
            'sha256':hashlib.sha256(text.encode()).hexdigest(), 'auto_generated':bool(re.search(r'<(Autofunction|ApiFunction|RefCard)',text,re.I))}

API_SOURCES={
 'file_uploader':'lib/streamlit/elements/widgets/file_uploader.py',
 'cache_data':'lib/streamlit/runtime/caching/cache_data_api.py',
 'cache_resource':'lib/streamlit/runtime/caching/cache_resource_api.py',
 'navigation':'lib/streamlit/commands/navigation.py',
 'set_page_config':'lib/streamlit/commands/page_config.py',
}

def collect_api(pair):
    name,path=pair; tag='1.49.0'
    url=f'https://raw.githubusercontent.com/streamlit/streamlit/{tag}/{path}'
    text=fetch(url); tree=ast.parse(text); entries=[]
    for node in ast.walk(tree):
        if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            doc=ast.get_docstring(node)
            if doc and len(doc)>500: entries.append(f'## {node.name} (line {node.lineno})\n\n{doc}')
    return {'id':'api:'+name,'kind':'docs','title':f'{name} API docstrings {tag}',
            'text':'\n\n'.join(entries),'url':f'https://github.com/streamlit/streamlit/blob/{tag}/{path}',
            'official_url':'https://docs.streamlit.io/','revision':tag,'product_version':tag,
            'source_path':path,'sha256':hashlib.sha256(text.encode()).hexdigest(), 'auto_generated':False}

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        docs=list(pool.map(collect_doc,DOC_PATHS))+list(pool.map(collect_api,API_SOURCES.items()))
    write(ROOT/'data'/'docs_snapshot.json',docs)
    print('docs',len(docs),'characters',sum(len(x['text']) for x in docs),flush=True)
