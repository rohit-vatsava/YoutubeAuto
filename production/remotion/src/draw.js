// Shared deterministic frame drawing for Remotion and the offline browser renderer.
export const archetypes=['HeroReveal','AvatarHost','ProductCard','DocumentationCard','ScreenshotFocus','FeatureList','ComparisonCards','ArchitectureDiagram','Timeline','MetricCounter','QuoteCard','ThreeStepProcess','FinalPayoff'];
const colors={ink:'#081321',panel:'#12283c',line:'#254057',white:'#eef5fc',muted:'#9bb1c7',teal:'#42dcc4',orange:'#ffb764'};
function box(ctx,x,y,w,h,r=26){ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fill();}
function lines(ctx,text,width){let out=[],line='';for(const word of text.split(/\s+/)){let next=line?line+' '+word:word;if(ctx.measureText(next).width>width&&line){out.push(line);line=word;}else line=next;}if(line)out.push(line);return out;}
function safeText(ctx,text,x,y,width,font,lineHeight,maxLines,checks){ctx.font=`600 ${font}px Arial`;let ls=lines(ctx,text,width);while((ls.length>maxLines||ls.some(s=>ctx.measureText(s).width>width))&&font>26){font-=2;ctx.font=`600 ${font}px Arial`;ls=lines(ctx,text,width);}for(let i=0;i<ls.length;i++){ctx.fillText(ls[i],x,y+i*lineHeight);checks.push({text:ls[i],x,y:y+i*lineHeight-font,width:ctx.measureText(ls[i]).width,height:font});}return ls.length;}
const motifs={
 HeroReveal(c,p){c.strokeStyle=colors.teal;c.lineWidth=4;c.beginPath();c.arc(540,470,135+30*p,0,Math.PI*2);c.stroke();},
 ProductCard(c){c.fillStyle=colors.teal;box(c,436,320,208,160);c.fillStyle=colors.ink;box(c,466,350,148,100);},
 DocumentationCard(c){c.strokeStyle=colors.teal;c.lineWidth=5;c.strokeRect(425,285,230,240);for(let i=0;i<4;i++){c.beginPath();c.moveTo(460,335+i*42);c.lineTo(620,335+i*42);c.stroke();}},
 ScreenshotFocus(c){c.strokeStyle=colors.teal;c.lineWidth=4;c.strokeRect(240,280,600,230);c.strokeRect(420,325,240,140);},
 FeatureList(c,p){for(let i=0;i<3;i++){c.fillStyle=i/3<p?colors.teal:colors.line;box(c,320,305+i*65,440,34,12);}},
 ComparisonCards(c,p,scene){c.fillStyle=colors.teal;box(c,245,310,255,160);c.fillStyle=scene?.creative_treatment?colors.white:colors.orange;box(c,580,310,255,160);},
 ArchitectureDiagram(c){c.strokeStyle=colors.teal;c.lineWidth=4;c.beginPath();c.moveTo(320,365);c.lineTo(760,365);c.stroke();for(let x of [260,500,740]){c.fillStyle=colors.panel;box(c,x,310,90,110);}},
 Timeline(c,p){c.fillStyle=colors.line;box(c,200,385,680,6,3);for(let i=0;i<4;i++){c.fillStyle=i/4<p?colors.teal:colors.orange;c.beginPath();c.arc(210+i*220,388,14,0,Math.PI*2);c.fill();}},
 MetricCounter(c,p){c.strokeStyle=colors.line;c.lineWidth=22;c.beginPath();c.arc(540,390,105,0,Math.PI*2);c.stroke();c.strokeStyle=colors.teal;c.beginPath();c.arc(540,390,105,-Math.PI/2,-Math.PI/2+Math.PI*2*p);c.stroke();},
 QuoteCard(c){c.fillStyle=colors.teal;c.font='160px Georgia';c.fillText('“',300,455);c.fillText('”',650,455);},
 ThreeStepProcess(c,p){for(let i=0;i<3;i++){c.fillStyle=i/3<p?colors.teal:colors.line;box(c,220+i*230,330,180,140);}},
 FinalPayoff(c,p){c.fillStyle=colors.teal;box(c,340,325,400,12);box(c,340,425,400*p,12);}
};
export async function loadAssets(spec,resolvePath=p=>p){
 const images={};for(const asset of spec.avatar_assets||[]){if(!asset.source_path)continue;const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('Avatar image could not be decoded'));image.src=resolvePath(asset.source_path);});images[asset.asset_id]=image;}return images;
}
function drawHost(c,spec,scene,frame,checks){
 const host=scene.avatar;if(!host||frame<host.start_frame||frame>=host.end_frame)return false;
 const asset=(spec.avatar_assets||[]).find(a=>a.asset_id===host.asset_id);const b=host.bounds;
 const opacity=Math.min(1,(frame-host.start_frame+1)/8,(host.end_frame-frame)/8);c.save();c.globalAlpha=opacity;c.translate(0,12*(1-opacity));
 c.fillStyle=colors.panel;box(c,b.x,b.y,b.width,b.height);
 const image=globalThis.productionImages?.[host.asset_id];
 if(image){c.save();if(host.masked){c.beginPath();c.roundRect(b.x,b.y,b.width,b.height,28);c.clip();}const crop=asset.crop;const sw=image.width*crop.width,sh=image.height*crop.height;const scale=Math.min(b.width/sw,b.height/sh);c.drawImage(image,image.width*crop.x,image.height*crop.y,sw,sh,b.x+(b.width-sw*scale)/2,b.y+(b.height-sh*scale)/2,sw*scale,sh*scale);c.restore();}
 else{c.strokeStyle=colors.teal;c.setLineDash([10,10]);c.strokeRect(b.x+8,b.y+8,b.width-16,b.height-16);c.setLineDash([]);c.fillStyle=colors.muted;safeText(c,'AVATAR SLOT',b.x+24,b.y+b.height/2,b.width-48,28,40,2,checks);}
 c.restore();checks.push({text:'[avatar bounds]',x:b.x,y:b.y,width:b.width,height:b.height+12*(1-opacity)});return true;
}
export function drawFrame(canvas,spec,frame){
 const c=canvas.getContext('2d');canvas.width=spec.width;canvas.height=spec.height;let checks=[];c.fillStyle=colors.ink;c.fillRect(0,0,1080,1920);
 c.strokeStyle='#142638';c.lineWidth=1;for(let x=0;x<1080;x+=72){c.beginPath();c.moveTo(x,0);c.lineTo(x,1920);c.stroke();}for(let y=0;y<1920;y+=72){c.beginPath();c.moveTo(0,y);c.lineTo(1080,y);c.stroke();}
 let scene=spec.scenes.find(s=>frame>=s.start_frame&&frame<s.end_frame)||spec.scenes.at(-1);let duration=scene.end_frame-scene.start_frame;let p=Math.max(0,Math.min(1,(frame-scene.start_frame)/duration));
 c.fillStyle=colors.teal;safeText(c,'TECH UNCOVERED',104,213,872,28,36,1,checks);c.fillStyle=colors.muted;safeText(c,`${String(spec.scenes.indexOf(scene)+1).padStart(2,'0')} / ${String(spec.scenes.length).padStart(2,'0')}`,780,213,200,28,36,1,checks);
 const hostActive=drawHost(c,spec,scene,frame,checks);
 c.save();c.globalAlpha=hostActive?0:Math.min(1,(frame-scene.start_frame+1)/8,(scene.end_frame-frame)/8);(motifs[scene.scene_type==='AvatarHost'?'DocumentationCard':scene.scene_type]||motifs.ProductCard)(c,p,scene);c.restore();
 // Paging repeats only upstream text; no invented factual labels or numbers.
 const event=(scene.visual_events||[]).filter(e=>e.frame<=frame).at(-1);
 let textBox={x:104,y:590,width:872,height:650};
 if(hostActive){const b=scene.avatar.bounds;if(scene.avatar.position==='center')textBox={x:104,y:990,width:872,height:260};else if(scene.avatar.position==='left')textBox={x:b.x+b.width+24,y:360,width:976-b.x-b.width-24,height:800};else textBox={x:104,y:360,width:b.x-128,height:800};}
 const chunks=[];for(let surface of scene.on_screen_text){let text=surface.text;
  if(text.includes(' • ')){const parts=text.split(' • ');let group=event?.focus?.source_sentence_id===surface.source_sentence_id?event.focus.item_start:0;const heading=parts[0].includes(':')?parts[0].split(':')[0]+': ':'';parts[0]=heading?parts[0].slice(heading.length):parts[0];text=heading+parts.slice(group,group+3).join(' · ');}
  c.font='600 42px Arial';const ls=lines(c,text,textBox.width-72);const maxLines=Math.max(2,Math.floor((textBox.height-100)/64));for(let i=0;i<ls.length;i+=maxLines)chunks.push(ls.slice(i,i+maxLines).join('\n'));
 }
 let chunk=chunks[Math.min(chunks.length-1,Math.floor(p*chunks.length))]||'';
 const treatment=scene.creative_treatment;
 if(treatment){
  const localSeconds=(frame-scene.start_frame)/spec.fps;
  if(treatment.role==='hook'&&frame<treatment.hook_pivot_frame){c.font='600 52px Arial';chunk=lines(c,localSeconds<0.8?'DOCUMENTED':treatment.editorial_heading,textBox.width-72).join('\n');}
  else if(treatment.role==='payoff'){c.font='600 52px Arial';chunk=lines(c,treatment.editorial_heading,textBox.width-72).join('\n');}
  else{c.fillStyle=colors.teal;safeText(c,treatment.editorial_heading,104,263,872,26,32,1,checks);}
 }

 c.fillStyle=colors.panel;box(c,textBox.x,textBox.y,textBox.width,textBox.height);c.fillStyle=colors.white;
 const textLines=chunk.split('\n');for(let i=0;i<textLines.length;i++){c.fillStyle=i===(event?.focus?.phrase_index||0)%textLines.length?colors.teal:colors.white;safeText(c,textLines[i],textBox.x+36,textBox.y+78+i*64,textBox.width-72,42,54,1,checks);}
 const cap=scene.caption_segments.find(s=>frame>=s.start_frame&&frame<s.end_frame);
 if(cap){c.fillStyle='#04101c';box(c,104,1310,872,202);c.fillStyle=colors.white;safeText(c,cap.text,144,1390,792,42,56,2,checks);if(cap.emphasis_words?.length){c.fillStyle=colors.teal;box(c,144,1465,240,5,2);}}
 c.fillStyle=colors.line;box(c,104,1554,872,6,3);c.fillStyle=colors.teal;box(c,104,1554,872*(frame+1)/(spec.duration_target*spec.fps),6,3);
 const b=spec.safe_bounds;return {scene_id:scene.scene_id,frame,bounds:checks,overflow:checks.filter(r=>r.x<b.left||r.x+r.width>b.right||r.y<b.top||r.y+r.height>b.bottom),placeholder:scene.scene_type==='ScreenshotFocus',audio:'silent-preview'};
}
