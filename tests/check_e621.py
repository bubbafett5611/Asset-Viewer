import requests, urllib.parse
headers={'User-Agent':'BubbaAssetViewer/1.0 (contact:none@example.com)'}
queries=["solo order:score","solo","solo -type:webm -type:mp4 -type:gif date:month order:score"]
for q in queries:
    tags=urllib.parse.quote(q)
    url=f"https://e621.net/posts.json?tags={tags}&limit=5"
    try:
        r=requests.get(url, headers=headers, timeout=15)
        print('QUERY:', q, 'STATUS', r.status_code)
        try:
            data=r.json()
            posts=data.get('posts', [])
            print('posts count', len(posts))
            for p in posts[:3]:
                file=p.get('file') or {}
                print('id', p.get('id'), 'url', file.get('url'), 'score', p.get('score'))
        except Exception as e:
            print('JSON parse error', e)
    except Exception as e:
        print('REQUEST ERROR', e)
