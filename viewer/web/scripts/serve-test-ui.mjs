import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve, extname, sep} from 'node:path';
const root=resolve('dist');
const types={'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml','.json':'application/json'};
createServer(async(req,res)=>{
 try {
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  if (/^\/(api|control)(\/|$)/.test(pathname)) {
   res.writeHead(503,{'Content-Type':'application/json'});res.end('{"error":"Test server has no backend"}');return;
  }
  const target=resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
  if(!target.startsWith(root+sep)){res.writeHead(403);res.end();return;}
  const data=await readFile(target);res.writeHead(200,{'Content-Type':types[extname(target)]||'application/octet-stream'});res.end(data);
 } catch {res.writeHead(404);res.end();}
}).listen(4175,'127.0.0.1');
