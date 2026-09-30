import React,{useRef,useLayoutEffect} from 'react';
import {registerRoot,Composition,useCurrentFrame} from 'remotion';
import {drawFrame,archetypes} from './draw.js';
export const ScenePrimitives=Object.fromEntries(archetypes.map(name=>[name,({spec,frame})=>{const ref=useRef(null);useLayoutEffect(()=>{drawFrame(ref.current,spec,frame);},[spec,frame]);return <canvas ref={ref} width={1080} height={1920}/>;}]));
export const Video=({spec})=>{const frame=useCurrentFrame();const scene=spec.scenes.find(s=>frame>=s.start_frame&&frame<s.end_frame)||spec.scenes.at(-1);const Primitive=ScenePrimitives[scene.scene_type];return <Primitive spec={spec} frame={frame}/>;};
const Root=()=> <Composition id="TechUncovered" component={Video} width={1080} height={1920} fps={30} durationInFrames={1800} calculateMetadata={({props})=>({durationInFrames:Math.round(props.spec.duration_target*30),fps:30,width:1080,height:1920})}/>;
registerRoot(Root);
