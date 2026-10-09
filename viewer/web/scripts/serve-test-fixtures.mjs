// Serve source fixtures without the development proxy to real API/control services.
import {createServer} from 'vite';
import react from '@vitejs/plugin-react';

const server=await createServer({
  configFile:false,
  plugins:[react()],
  server:{host:'127.0.0.1',port:4177,strictPort:true},
});
server.middlewares.use((req,res,next)=>{
  if (/^\/(api|control)(\/|$)/.test(req.url||'')) {
    res.writeHead(503,{'Content-Type':'application/json'});
    res.end('{"error":"Fixture server has no backend"}');
    return;
  }
  next();
});
await server.listen();
for(const signal of ['SIGINT','SIGTERM']) process.once(signal,async()=>{
  await server.close();
  process.exit(0);
});
