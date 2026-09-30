// Shared deterministic frame drawing for Remotion and the offline browser renderer.
export const archetypes=['HeroReveal','ProductCard','DocumentationCard','ScreenshotFocus','FeatureList','ComparisonCards','ArchitectureDiagram','Timeline','MetricCounter','QuoteCard','ThreeStepProcess','FinalPayoff'];
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
 ComparisonCards(c){c.fillStyle=colors.teal;box(c,245,310,255,160);c.fillStyle=colors.orange;box(c,580,310,255,160);},
 ArchitectureDiagram(c){c.strokeStyle=colors.teal;c.lineWidth=4;c.beginPath();c.moveTo(320,365);c.lineTo(760,365);c.stroke();for(let x of [260,500,740]){c.fillStyle=colors.panel;box(c,x,310,90,110);}},
 Timeline(c,p){c.fillStyle=colors.line;box(c,200,385,680,6,3);for(let i=0;i<4;i++){c.fillStyle=i/4<p?colors.teal:colors.orange;c.beginPath();c.arc(210+i*220,388,14,0,Math.PI*2);c.fill();}},
 MetricCounter(c,p){c.strokeStyle=colors.line;c.lineWidth=22;c.beginPath();c.arc(540,390,105,0,Math.PI*2);c.stroke();c.strokeStyle=colors.teal;c.beginPath();c.arc(540,390,105,-Math.PI/2,-Math.PI/2+Math.PI*2*p);c.stroke();},
 QuoteCard(c){c.fillStyle=colors.teal;c.font='160px Georgia';c.fillText('“',300,455);c.fillText('”',650,455);},
 ThreeStepProcess(c,p){for(let i=0;i<3;i++){c.fillStyle=i/3<p?colors.teal:colors.line;box(c,220+i*230,330,180,140);}},
 FinalPayoff(c,p){c.fillStyle=colors.teal;box(c,340,325,400,12);box(c,340,425,400*p,12);}
};
export function drawFrame(canvas,spec,frame){
 const c=canvas.getContext('2d');canvas.width=spec.width;canvas.height=spec.height;let checks=[];c.fillStyle=colors.ink;c.fillRect(0,0,1080,1920);
 c.strokeStyle='#142638';c.lineWidth=1;for(let x=0;x<1080;x+=72){c.beginPath();c.moveTo(x,0);c.lineTo(x,1920);c.stroke();}for(let y=0;y<1920;y+=72){c.beginPath();c.moveTo(0,y);c.lineTo(1080,y);c.stroke();}
 let scene=spec.scenes.find(s=>frame>=s.start_frame&&frame<s.end_frame)||spec.scenes.at(-1);let duration=scene.end_frame-scene.start_frame;let p=Math.max(0,Math.min(1,(frame-scene.start_frame)/duration));
 c.fillStyle=colors.teal;safeText(c,'TECH UNCOVERED',104,213,872,28,36,1,checks);c.fillStyle=colors.muted;safeText(c,`${String(spec.scenes.indexOf(scene)+1).padStart(2,'0')} / ${String(spec.scenes.length).padStart(2,'0')}`,780,213,200,28,36,1,checks);
 c.save();c.globalAlpha=Math.min(1,(frame-scene.start_frame+1)/8,(scene.end_frame-frame)/8);(motifs[scene.scene_type]||motifs.ProductCard)(c,p);c.restore();
 // Paging repeats only upstream text; no invented factual labels or numbers.
 const chunks=[];for(let surface of scene.on_screen_text){c.font='600 46px Arial';const ls=lines(c,surface.text.replaceAll(' • ','  ·  '),780);for(let i=0;i<ls.length;i+=6)chunks.push(ls.slice(i,i+6).join('\n'));}
 const chunk=chunks[Math.min(chunks.length-1,Math.floor(p*chunks.length))]||'';
 c.fillStyle=colors.panel;box(c,104,590,872,650);c.fillStyle=colors.white;
 const textLines=chunk.split('\n');for(let i=0;i<textLines.length;i++)safeText(c,textLines[i],148,690+i*76,784,46,60,1,checks);
 const cap=scene.caption_segments.find(s=>frame>=s.start_frame&&frame<s.end_frame);
 if(cap){c.fillStyle='#04101c';box(c,104,1310,872,202);c.fillStyle=colors.white;safeText(c,cap.text,144,1390,792,42,56,2,checks);}
 c.fillStyle=colors.line;box(c,104,1554,872,6,3);c.fillStyle=colors.teal;box(c,104,1554,872*(frame+1)/(spec.duration_target*spec.fps),6,3);
 const b=spec.safe_bounds;return {scene_id:scene.scene_id,frame,bounds:checks,overflow:checks.filter(r=>r.x<b.left||r.x+r.width>b.right||r.y<b.top||r.y+r.height>b.bottom),placeholder:scene.scene_type==='ScreenshotFocus',audio:'silent-preview'};
}
