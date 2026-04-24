export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const BUCKET = env.IA_BUCKET || 'junk-manage-caution';
    const IA_BASE = `https://archive.org/download/${BUCKET}`;
    const path = decodeURIComponent(url.pathname.slice(1));

    if (url.pathname === '/health') return new Response('ok');

    if (url.pathname === '/api/share' && req.method === 'POST') {
      const {file} = await req.json();
      const id = Math.random().toString(36).slice(2,10);
      await env.SHARES.put(id, file, {expirationTtl: 604800});
      return Response.json({url: `/s/${id}`});
    }

    if (url.pathname.startsWith('/s/')) {
      const id = url.pathname.split('/')[2];
      const file = await env.SHARES.get(id);
      if (!file) return new Response('Not found', {status:404});
      return fetch(`${IA_BASE}/${file}`, {cf:{cacheTtl:31536000, cacheEverything:true}});
    }

    if (url.pathname.startsWith('/thumb/')) {
      const file = url.pathname.replace('/thumb/','');
      const thumbKey = file.replace(/[^a-z0-9]/gi,'_') + '.webp';
      let obj = await env.THUMBS.get(thumbKey, {type:'arrayBuffer'});
      if (obj) {
        return new Response(obj, {headers:{'Content-Type':'image/webp','Cache-Control':'public, max-age=31536000, immutable'}});
      }
      const iaUrl = `${IA_BASE}/${file}`;
      const imgReq = new Request(iaUrl, {cf:{image:{width:400,height:300,fit:'cover',format:'webp',quality:80}}});
      const res = await fetch(imgReq);
      if (res.ok) {
        ctx.waitUntil(env.THUMBS.put(thumbKey, res.clone().body));
        return new Response(res.body, {headers:{'Content-Type':'image/webp','Cache-Control':'public, max-age=31536000, immutable'}});
      }
      return new Response('thumb error', {status:502});
    }

    if (url.pathname === '/upload-r2' && req.method === 'PUT') {
      const name = url.searchParams.get('name');
      await env.UPLOADS.put(name, req.body);
      ctx.waitUntil(copyToIA(name, env, BUCKET));
      return Response.json({ok:true, staged:name});
    }

    if (path && !path.includes('..')) {
      const iaUrl = `${IA_BASE}/${path}`;
      const isVideo = /\.(mp4|mkv|mov|webm)$/i.test(path);
      const cacheTtl = isVideo? 0 : 31536000;
      const res = await fetch(iaUrl, {
        method: req.method,
        headers: req.headers,
        cf: {cacheTtl, cacheEverything:true}
      });
      const headers = new Headers(res.headers);
      headers.set('Access-Control-Allow-Origin','*');
      headers.set('Cache-Control', isVideo? 'public, max-age=60' : 'public, max-age=31536000');
      return new Response(res.body, {status: res.status, headers});
    }

    return new Response('IA Drive Worker', {status:200});
  }
}

async function copyToIA(name, env, bucket) {
  const obj = await env.UPLOADS.get(name);
  if (!obj) return;
  const url = `https://s3.us.archive.org/${bucket}/${encodeURIComponent(name)}`;
  await fetch(url, {
    method: 'PUT',
    headers: {
      'Authorization': `LOW ${env.IA_ACCESS}:${env.IA_SECRET}`,
      'x-amz-auto-make-bucket':'1',
      'x-archive-meta-title': bucket
    },
    body: obj.body
  });
  await env.UPLOADS.delete(name);
}
