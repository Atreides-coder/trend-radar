import React from 'react';
import {AbsoluteFill,Composition,Easing,Img,interpolate,registerRoot,staticFile,useCurrentFrame} from 'remotion';
import {Captions} from '../../src/Captions';
import pages from './pages.json';

const amber='#f5b83d', font='"PingFang SC","Hiragino Sans GB",sans-serif';
const motion=(f:number,t:number[],v:number[])=>interpolate(f,t,v,{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.38,.04,.2,1)});
const pin=(left:number,top:number):React.CSSProperties=>({position:'absolute',left,top});
function DocumentCut(){
 const f=useCurrentFrame();
 const price=f>=76&&f<193;
 const back=f>=193;
 const times=price?[76,83,98,132,150,164,192]:back?[193,202,221,278,299]:[0,9,27,45,70,75];
 const scale=motion(f,times,price?[1.68,2.16,2.22,2.22,2.55,2.55,2.56]:back?[1.44,1.16,1.04,1.035,1.035]:[1.03,1.04,1.69,1.75,1.76,1.76]);
 const focusX=motion(f,times,price?[364,285,280,280,277,277,277]:back?[445,504,540,540,540]:[540,540,358,308,308,308]);
 const focusY=motion(f,times,price?[354,358,358,358,357,357,357]:back?[398,427,492,495,495]:[365,370,484,532,534,534]);
 const centerY=price?650:665;
 const line=motion(f,[24,45],[0,1]),dollars=motion(f,[82,100],[0,1]),circle=motion(f,[132,151],[0,1]);
 const src=price?'outlier_price_archive':'source_2_page';
 return <AbsoluteFill style={{fontFamily:font,background:'#10110f',color:'#faf8ee'}}>
   <div style={{...pin(64,110),fontSize:37,fontWeight:600,letterSpacing:1}}>Outlier <span style={{color:'#c2bfae',fontWeight:400}}>／ 招募页存档</span></div>
   <div style={{position:'absolute',right:64,top:120,fontFamily:'Helvetica Neue',fontSize:32,color:'#b3b0a3',fontVariantNumeric:'tabular-nums'}}>2026.05.18</div>
   <div style={{...pin(0,213),width:'100%',height:987,overflow:'hidden',background:price?'#fff':'linear-gradient(90deg,#f5c7c5,#c3e8f3)'}}>
    <div style={{...pin(540-scale*focusX,centerY-213-scale*focusY),transform:'scale('+scale+')',transformOrigin:'top left',width:price?1075:1080}}>
     <Img src={staticFile(src+'.png')} style={{display:'block',width:'100%'}}/>
     {!price&&!back&&<svg width="1080" height="1100" style={pin(0,0)}><path d="M54 561 Q242 564 499 558" pathLength="1" stroke="#c44329" strokeWidth="4" strokeLinecap="round" strokeDasharray="1" strokeDashoffset={1-line} fill="none"/></svg>}
     {price&&<svg width="1075" height="729" style={pin(0,0)}><path d="M257 377 Q340 380 461 374" pathLength="1" stroke="#c44329" strokeWidth="3.7" strokeLinecap="round" strokeDasharray="1" strokeDashoffset={1-dollars} fill="none"/><path d="M224 335 C191 330 153 338 151 356 C148 379 188 385 226 377 C258 370 263 341 226 336 L219 335" pathLength="1" stroke="#c44329" strokeWidth="3" strokeLinecap="round" strokeDasharray="1" strokeDashoffset={1-circle} fill="none"/></svg>}
    </div>
   </div>
   <div style={{...pin(60,1244),display:'flex',alignItems:'center',gap:18,color:'#ddd9cc',fontSize:37}}>
    <div style={{width:50,height:4,background:amber}}/>
    {price?(f<133?'广告原文 · 按小时报价':'Up to，意为「最高」'):back?'心脏科专业人士招募页':'原文节选 · 设计复杂心脏病例'}
   </div>
   <Captions pages={pages}/><div style={{...pin(0,0),height:8,width:'100%',background:'#222220'}}><div style={{height:8,width:100*f/1599+'%',background:amber}}/></div>
 </AbsoluteFill>
}
registerRoot(()=> <Composition id="OriginalPage" component={DocumentCut} durationInFrames={300} fps={30} width={1080} height={1920}/>);
