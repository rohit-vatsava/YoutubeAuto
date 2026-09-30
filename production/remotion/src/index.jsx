import React,{useRef,useLayoutEffect,useEffect,useState} from 'react';
import {registerRoot,Composition,useCurrentFrame,Audio,Sequence,staticFile,delayRender,continueRender,cancelRender} from 'remotion';
import {drawFrame,archetypes,loadAssets} from './draw.js';
export const ScenePrimitives=Object.fromEntries(archetypes.map(name=>[name,({spec,frame,images})=>{const ref=useRef(null);useLayoutEffect(()=>{globalThis.productionImages=images;drawFrame(ref.current,spec,frame);},[spec,frame,images]);return <canvas ref={ref} width={1080} height={1920}/>;}]));
const dbGain=db=>Math.pow(10,db/20);
export const Video=({spec})=>{
 const frame=useCurrentFrame();const [handle]=useState(()=>delayRender('Loading local host assets'));const [images,setImages]=useState({});
 useEffect(()=>{loadAssets(spec,p=>staticFile(p)).then(result=>{setImages(result);continueRender(handle);}).catch(cancelRender);},[spec,handle]);
 const scene=spec.scenes.find(s=>frame>=s.start_frame&&frame<s.end_frame)||spec.scenes.at(-1);const Primitive=ScenePrimitives[scene.scene_type];const mix=spec.audio_mix;
 const musicVolume=f=>{const m=mix.music;const t=f/spec.fps;let gain=dbGain(m.gain_db);if(m.fade_in_seconds)gain*=Math.min(1,t/m.fade_in_seconds);if(m.fade_out_seconds)gain*=Math.min(1,(spec.duration_target-t)/m.fade_out_seconds);if(m.duck_during_narration&&(spec.voice_timing.word_timestamps||[]).some(w=>t>=w.start_seconds&&t<=w.end_seconds))gain*=dbGain(m.ducking_db);return Math.max(0,gain);};
 return <><Primitive spec={spec} frame={frame} images={images}/>
  {mix?.narration.audio_path&&<Audio src={staticFile(mix.narration.audio_path)} volume={dbGain(mix.narration.gain_db)}/>}
  {mix?.music.audio_path&&<Audio src={staticFile(mix.music.audio_path)} volume={musicVolume}/>}
  {(mix?.sound_effects||[]).map((cue,i)=>{const asset=spec.assets.find(a=>a.asset_id===cue.asset_id);return asset?<Sequence key={i} from={Math.round(cue.timestamp_seconds*spec.fps)}><Audio src={staticFile(asset.path)} volume={dbGain(cue.gain_db)}/></Sequence>:null;})}
 </>;
};
const Root=()=> <Composition id="TechUncovered" component={Video} width={1080} height={1920} fps={30} durationInFrames={1800} calculateMetadata={({props})=>({durationInFrames:Math.round(props.spec.duration_target*30),fps:30,width:1080,height:1920})}/>;
registerRoot(Root);
