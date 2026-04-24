export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const BUCKET = env.IA_BUCKET || 'junk-manage-caution';
    const IA_BASE = `https://archive.org/download/${BUCKET}`;
    const S3_BASE = `https://${BUCKET}.s3.us.archive.org`;
    
    // CORS preflight
    if (req.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders() });
    }

    // Health
    if (url.pathname === '/health') return json({ok:true, pop:req.cf?.colo, ts:Date.now()});

    // Share API
    if (url.pathname === '/api/share' && req.method === 'POST') {
      const {file} = await req.json();
      const id = crypto.randomUUID().slice(0,8);
      await env.SHARES.put(id, file, {expirationTtl: 604800});
      return json({url: `/s/${id}`, id});
    }

    if (url.pathname.startsWith('/s/')) {
      const id = url.pathname.split('/')[2];
      const file = await env.SHARES.get(id);
      if (!file) return new Response('Not found', {status:404});
      return streamFile(`${IA_BASE}/${file}`, req, false);
    }

    // Thumbnails with R2 cache
    if (url.pathname.startsWith('/thumb/')) {
      const key = decodeURIComponent(url.pathname.slice(7));
      const cacheKey = `thumb_${btoa(key).replace(/=/g,'')}.webp`;
      const cached = await env.THUMBS.get(cacheKey, {type:'stream'});
      if (cached) {
        return new Response(cached, { headers: {
          'Content-Type':'image/webp',
          'Cache-Control':'public, max-age=31536000, immutable',
          ...corsHeaders()
        }});
      }
      const src = `${IA_BASE}/${key}`;
      const img = await fetch(src, { cf: { image: { width:400, height:300, fit:'cover', format:'webp', quality:80 } } });
      if (!img.ok) return new Response('', {status:404});
      ctx.waitUntil(env.THUMBS.put(cacheKey, img.clone().body));
      return new Response(img.body, { headers: {
        'Content-Type':'image/webp',
        'Cache-Control':'public, max-age=31536000, immutable',
        ...corsHeaders()
      }});
    }

    // Direct upload to IA via Worker (streams, no memory limit)
    if (url.pathname === '/upload' && req.method === 'PUT') {
      const key = url.searchParams.get('name') || crypto.randomUUID();
      const uploadUrl = `${S3_BASE}/${encodeURIComponent(key)}`;
      
      // Stream directly to IA S3
      const iaRes = await fetch(uploadUrl, {
        method: 'PUT',
        headers: {
          'Authorization': `LOW ${env.IA_ACCESS}:${env.IA_SECRET}`,
          'x-amz-auto-make-bucket': '1',
          'x-archive-meta-mediatype': 'data',
          'x-archive-meta-collection': 'opensource',
          'x-archive-meta-title': BUCKET,
          'Content-Type': req.headers.get('Content-Type') || 'application/octet-stream'
        },
        body: req.body,
        duplex: 'half'
      });
      
      if (!iaRes.ok) {
        const txt = await iaRes.text();
        return json({ok:false, error:txt}, 500);
      }
      return json({ok:true, key, url:`/${key}`});
    }

    // URL fetch → IA (server-side, up to 100GB)
    if (url.pathname === '/api/fetch' && req.method === 'POST') {
      const {url:src, key} = await req.json();
      const name = key || src.split('/').pop().split('?')[0];
      ctx.waitUntil((async()=>{
        const srcRes = await fetch(src);
        if (!srcRes.ok) return;
        await fetch(`${S3_BASE}/${encodeURIComponent(name)}`, {
          method:'PUT',
          headers:{
            'Authorization': `LOW ${env.IA_ACCESS}:${env.IA_SECRET}`,
            'x-amz-auto-make-bucket':'1',
            'x-archive-meta-mediatype':'data'
          },
          body: srcRes.body,
          duplex: 'half'
        });
      })());
      return json({ok:true, key:name, queued:true});
    }

    // R2 staging (for resumable)
    if (url.pathname === '/upload-r2' && req.method === 'PUT') {
      const name = url.searchParams.get('name');
      await env.UPLOADS.put(name, req.body);
      ctx.waitUntil(copyR2toIA(name, env, BUCKET, S3_BASE));
      return json({ok:true, staged:name});
    }

    // Download with attachment
    if (url.pathname.startsWith('/download/')) {
      const key = decodeURIComponent(url.pathname.slice(10));
      const res = await fetch(`${IA_BASE}/${key}`);
      const headers = new Headers(res.headers);
      headers.set('Content-Disposition', `attachment; filename="${key.split('/').pop()}"`);
      headers.set('Cache-Control', 'private, max-age=0');
      Object.entries(corsHeaders()).forEach(([k,v])=>headers.set(k,v));
      return new Response(res.body, {status:res.status, headers});
    }

    // Stream file (default route)
    if (req.method === 'GET' && url.pathname.length > 1) {
      const key = decodeURIComponent(url.pathname.slice(1));
      if (key.includes('..')) return new Response('Bad', {status:400});
      const isVideo = /\.(mp4|mkv|webm|mov|m4v|avi)$/i.test(key);
      const isLarge = url.searchParams.get('large') === '1';
      return streamFile(`${IA_BASE}/${key}`, req, isVideo || isLarge);
    }

    return new Response('IA Drive Worker v2', {headers:corsHeaders()});
  }
};

async function streamFile(iaUrl, req, noCache) {
  const range = req.headers.get('Range');
  const headers = {};
  if (range) headers['Range'] = range;
  
  const res = await fetch(iaUrl, {
    headers,
    cf: {
      cacheTtl: noCache ? 0 : 31536000,
      cacheEverything: !noCache,
      cacheKey: iaUrl
    }
  });

  const outHeaders = new Headers(res.headers);
  outHeaders.set('Accept-Ranges', 'bytes');
  outHeaders.set('Access-Control-Allow-Origin', '*');
  outHeaders.set('Access-Control-Expose-Headers', 'Content-Range, Accept-Ranges, Content-Length');
  outHeaders.set('Cache-Control', noCache ? 'public, max-age=60' : 'public, max-age=31536000');
  outHeaders.delete('Set-Cookie');
  
  // Fix CORS for video scrubbing
  if (range && res.status === 206) {
    outHeaders.set('Content-Range', res.headers.get('Content-Range') || '');
  }

  return new Response(res.body, {
    status: res.status,
    headers: outHeaders
  });
}

async function copyR2toIA(name, env, bucket, S3_BASE) {
  const obj = await env.UPLOADS.get(name);
  if (!obj) return;
  await fetch(`${S3_BASE}/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {
      'Authorization': `LOW ${env.IA_ACCESS}:${env.IA_SECRET}`,
      'x-amz-auto-make-bucket': '1'
    },
    body: obj.body,
    duplex: 'half'
  });
  await env.UPLOADS.delete(name);
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
    'Access-Control-Allow-Headers': '*, Range, Content-Type',
    'Access-Control-Max-Age': '86400'
  };
}

function json(data, status=200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type':'application/json', ...corsHeaders() }
  });
}
