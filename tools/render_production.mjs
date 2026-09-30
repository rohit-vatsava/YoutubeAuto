// Fully local Canvas/WebCodecs preview renderer; Remotion uses the same drawFrame.
import fs from 'node:fs';import path from 'node:path';import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const args=process.argv.slice(2);const get=k=>args[args.indexOf(k)+1];
if(!args.includes('--spec'))throw Error('Usage: node tools/render_production.mjs --spec PATH [--render]');
const specPath=path.resolve(get('--spec')),out=path.dirname(specPath),spec=JSON.parse(fs.readFileSync(specPath));
const playwright=process.env.PLAYWRIGHT_MODULE||'/Users/rohit/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright';
const {chromium}=require(playwright);
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--disable-default-apps']});
try{
 const page=await browser.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:1});
 await page.route('**/*',r=>r.request().url().startsWith('file:')?r.continue():r.abort());
 const draw=fs.readFileSync('production/remotion/src/draw.js','utf8').replaceAll('export const ','const ').replaceAll('export function ','function ');
 const html=`<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#081321}canvas{display:block}</style><canvas id="video"></canvas><script>${draw}\nwindow.draw=drawFrame;</script>`;
 const preview=path.join(out,'preview.html');fs.writeFileSync(preview,html);
 await page.goto('file://'+preview);await page.evaluate(s=>{window.spec=s;window.frame=0;window.draw(document.querySelector('canvas'),s,0);},spec);
 const qa=await page.evaluate(()=>{let overflows=[],scenes=new Set();const canvas=document.querySelector('canvas');for(let f=0;f<Math.round(spec.duration_target*spec.fps);f++){const r=draw(canvas,spec,f);scenes.add(r.scene_id);if(r.overflow.length)overflows.push(r);}return {frames_checked:Math.round(spec.duration_target*spec.fps),overflow_count:overflows.length,examples:overflows.slice(0,3),scenes_checked:scenes.size,webcodecs:typeof VideoEncoder!=='undefined'};});
 fs.writeFileSync(path.join(out,'render-qa.json'),JSON.stringify(qa,null,2));if(qa.overflow_count)throw Error('Text safe-bound overflow');
 for(const scene of spec.scenes){await page.evaluate(f=>draw(document.querySelector('canvas'),spec,f),Math.floor((scene.start_frame+scene.end_frame)/2));await page.screenshot({path:path.join(out,scene.scene_id+'.png')});}
 if(args.includes('--render')){
  const encoded=await page.evaluate(async()=>{
   if(typeof VideoEncoder==='undefined')return {blocked:'WebCodecs VideoEncoder unavailable'};
   const config={codec:'avc1.420028',width:1080,height:1920,bitrate:4500000,framerate:30,latencyMode:'realtime',avc:{format:'avc'},hardwareAcceleration:'prefer-software'};
   const supported=await VideoEncoder.isConfigSupported(config);if(!supported.supported)return {blocked:'Local H.264 encoder unavailable'};
   let samples=[],description=null,error=null;const canvas=document.querySelector('canvas');
   function b64(bytes){let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s);}
   const encoder=new VideoEncoder({output(chunk,metadata){let bytes=new Uint8Array(chunk.byteLength);chunk.copyTo(bytes);samples.push({data:b64(bytes),key:chunk.type==='key',timestamp:chunk.timestamp});if(metadata.decoderConfig?.description)description=b64(new Uint8Array(metadata.decoderConfig.description));},error(e){error=String(e);}});
   encoder.configure(config);const count=Math.round(spec.duration_target*spec.fps);
   for(let f=0;f<count;f++){draw(canvas,spec,f);let frame=new VideoFrame(canvas,{timestamp:Math.round(f*1000000/30),duration:Math.round((f+1)*1000000/30)-Math.round(f*1000000/30)});encoder.encode(frame,{keyFrame:f%60===0});frame.close();if(encoder.encodeQueueSize>8)await new Promise(resolve=>setTimeout(resolve,5));if(error)throw Error(error);}
   await encoder.flush();encoder.close();if(error)throw Error(error);return {samples,description};
  });
  if(encoded.blocked){fs.writeFileSync(path.join(out,'render-blocker.json'),JSON.stringify(encoded,null,2));console.log(encoded);}
  else{
   if(encoded.samples.length!==Math.round(spec.duration_target*30)||!encoded.description)throw Error('Incomplete encoded frame sequence');
   for(let i=1;i<encoded.samples.length;i++)if(encoded.samples[i].timestamp<=encoded.samples[i-1].timestamp)throw Error('Reordered encoding unsupported');
   const buf=mux(encoded,spec);const video=path.join(out,'preview.mp4');fs.writeFileSync(video,buf);
   // Independently load the completed container in the browser media decoder.
   await page.goto('file://'+video);const probe=await page.evaluate(async()=>{const v=document.querySelector('video');if(v.readyState<1)await new Promise((resolve,reject)=>{v.onloadedmetadata=resolve;v.onerror=reject;});return {width:v.videoWidth,height:v.videoHeight,duration:v.duration};});
   if(probe.width!==1080||probe.height!==1920||Math.abs(probe.duration-spec.duration_target)>.04)throw Error('MP4 probe mismatch');
   qa.mp4={...probe,fps:30,frames:encoded.samples.length,frame_duration_timescale:1000,timescale:30000,bytes:buf.length,audio:'none',status:'SILENT_PREVIEW',path:video};fs.writeFileSync(path.join(out,'render-qa.json'),JSON.stringify(qa,null,2));console.log(JSON.stringify(qa,null,2));
  }
 }else console.log(JSON.stringify(qa,null,2));
 // Preview file can be opened locally and played without Node or external assets.
 fs.writeFileSync(preview,html.replace('</script>',`window.spec=${JSON.stringify(spec).replaceAll('<','\\u003c')};let started=null;function tick(t){if(started===null)started=t;draw(document.querySelector('canvas'),spec,Math.floor((t-started)*spec.fps/1000)%Math.round(spec.duration_target*spec.fps));requestAnimationFrame(tick);}requestAnimationFrame(tick);</script>`));
}finally{await browser.close();}

function mux(encoded,spec){
 const cat=(...a)=>Buffer.concat(a),u32=x=>{let b=Buffer.alloc(4);b.writeUInt32BE(x);return b;},u16=x=>{let b=Buffer.alloc(2);b.writeUInt16BE(x);return b;},zero=n=>Buffer.alloc(n),txt=s=>Buffer.from(s,'ascii');
 const box=(name,...payload)=>{const p=cat(...payload);return cat(u32(p.length+8),txt(name),p);};const full=(name,flags,...p)=>box(name,u32(flags),...p);
 const matrix=cat(u32(65536),u32(0),u32(0),u32(0),u32(65536),u32(0),u32(0),u32(0),u32(0x40000000));
 const chunks=encoded.samples.map(s=>Buffer.from(s.data,'base64'));const duration=chunks.length*1000;
 const ftyp=box('ftyp',txt('isom'),u32(512),txt('isomiso2avc1mp41'));
 const avc1=box('avc1',zero(6),u16(1),zero(16),u16(1080),u16(1920),u32(0x480000),u32(0x480000),u32(0),u16(1),zero(32),u16(24),u16(65535),box('avcC',Buffer.from(encoded.description,'base64')));
 const stsd=full('stsd',0,u32(1),avc1),stts=full('stts',0,u32(1),u32(chunks.length),u32(1000));
 const stsc=full('stsc',0,u32(1),u32(1),u32(chunks.length),u32(1));const stsz=full('stsz',0,u32(0),u32(chunks.length),...chunks.map(b=>u32(b.length)));
 const keys=encoded.samples.flatMap((s,i)=>s.key?[i+1]:[]);const stss=full('stss',0,u32(keys.length),...keys.map(u32));
 const mdhd=full('mdhd',0,u32(0),u32(0),u32(30000),u32(duration),u16(0x55c4),u16(0));
 const hdlr=full('hdlr',0,u32(0),txt('vide'),zero(12),txt('VideoHandler\0'));
 const dinf=box('dinf',full('dref',0,u32(1),full('url ',1)));
 const tkhd=full('tkhd',7,u32(0),u32(0),u32(1),u32(0),u32(duration),zero(8),u16(0),u16(0),u16(0),u16(0),matrix,u32(1080*65536),u32(1920*65536));
 const mvhd=full('mvhd',0,u32(0),u32(0),u32(30000),u32(duration),u32(65536),u16(256),zero(10),matrix,zero(24),u32(2));
 const moov=offset=>box('moov',mvhd,box('trak',tkhd,box('mdia',mdhd,hdlr,box('minf',full('vmhd',1,zero(8)),dinf,box('stbl',stsd,stts,stsc,stsz,full('stco',0,u32(1),u32(offset)),stss)))));
 const header=moov(0);return cat(ftyp,moov(ftyp.length+header.length+8),box('mdat',...chunks));
}
