import React from 'react';
import {AbsoluteFill,Composition,Easing,Img,interpolate,registerRoot,Sequence,staticFile,useCurrentFrame} from 'remotion';
import {Captions} from '../../src/Captions';
import pages from './pages.json';

const amber='#f5b83d', rust='#b8432f', ink='#201f1c', grey='#625e55', ivory='#f3efe5', width=1080;
const font='"PingFang SC","Hiragino Sans GB",sans-serif', serif='"Times New Roman", "Songti SC",serif';
const pos=(x:number,y:number,w?:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width:w});
const ramp=(t:number,a:number,b:number)=>interpolate(t,[a,b],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.31,.02,.2,1)});
const lerp=(a:number,b:number,m:number)=>a+(b-a)*m;
const absolute:React.CSSProperties={position:'absolute',inset:0};
const Pen=({x,y,w,amount,color=rust}:{x:number,y:number,w:number,amount:number,color?:string})=><svg width={w+8} height="18" style={pos(x,y)}><path d={`M3 10 Q ${w*.45} 3 ${w} 7`} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round" pathLength="1" strokeDasharray="1" strokeDashoffset={1-amount}/></svg>;
const Pic=({name,style}:{name:string,style?:React.CSSProperties})=><Img src={staticFile(name+'.png')} style={{display:'block',...style}}/>;
function Sheet({name,native=1075,scale=1,fx=537,fy=380,anchor=480,marks}:{name:string,native?:number,scale?:number,fx?:number,fy?:number,anchor?:number,marks?:React.ReactNode}){
 return <div style={{...absolute,background:'#fff',overflow:'hidden'}}><div style={{...pos(width/2-scale*fx,anchor-scale*fy,native),transform:'scale('+scale+')',transformOrigin:'0 0'}}><Pic name={name} style={{width:'100%'}}/>{marks}</div></div>
}
const noteText:React.CSSProperties={fontSize:32,letterSpacing:1,color:grey};
function Body(){
 const t=(useCurrentFrame()+300)/30;
 let source='Outlier',section='招募页存档',credit='2026.05.18',note='',view:React.ReactNode;
 if(t<12.7667){
  note='招募页脚注 · 费率随项目条件变化';
  view=<Sheet name="outlier_rates_contract" scale={1+.08*ramp(t,10,11.2)} fx={510} fy={125} anchor={170} marks={<Pen x={22} y={94} w={650} amount={ramp(t,10.25,11.25)}/>}/>;
 } else if(t<16.8){
  source='Rest of World';section='Julián Posada 访谈摘录'; credit='2026.11.19';note='受访家庭曾在平台上给汽车和道路图片做标注';
  const m=ramp(t,13,15.5);
  view=<div style={{...absolute,background:ivory,color:ink,padding:'88px 65px'}}>
    <div style={noteText}>《Rest of World》原文节选</div><div style={{height:2,background:'#b6afa1',marginTop:36}}/>
    <div style={{...pos(67,210,950),fontFamily:serif,fontStyle:'italic',fontSize:113,lineHeight:1.13,transform:'translateY('+(-14*m)+'px)'}}>“labeling images<br/>of cars and roads”</div>
    <Pen x={138} y={443-14*m} w={661} amount={ramp(t,14.1,15.1)}/>
    <div style={{...pos(68,651,920),color:grey,fontSize:48}}>给汽车和道路图片贴标签</div>
  </div>;
 } else if(t<25.6667){
  note='同一份招募启事列出的三项专业工作';
  const a=ramp(t,18.18,18.65),b=ramp(t,19.28,19.7),c=ramp(t,20.27,20.72),wide=ramp(t,21.8,23);
  const cam=lerp(1.62,1,wide);
  view=<div style={{...absolute,background:'#fff',color:ink,overflow:'hidden'}}>
   <div style={{...pos(0,0,1080),transformOrigin:'0 0',transform:`translate(${-51*(1-wide)}px,${lerp(128-306*b-310*c,100,wide)}px) scale(${cam})`}}>
   <div style={{...pos(66,72),...noteText}}>工作职责 / 招聘原文节选</div>
   {['design','review','rank'].map((name,i)=>{let y=210+i*239;const active=[a,b,c][i];return <React.Fragment key={name}><div style={{...pos(66,y-56),fontSize:36,color:active?rust:grey,fontWeight:600}}>{['设计病例','审核报告','给答案排序'][i]}</div><Pic name={name} style={pos(66,y,950)}/><Pen x={70} y={y+34} w={[171,215,248][i]} amount={active}/></React.Fragment>})}
   </div>
  </div>;
 } else if(t<30.3667){
  note=t<28.1?'条款原文 · 1099 独立承包合同':'同页脚注 · 初始培训等非核心工作适用较低费率';
  const scroll=ramp(t,27.9,28.59);
  view=<Sheet name="outlier_rates_contract" scale={1.02} fx={526} fy={lerp(1495,235,scroll)} anchor={475} marks={<><Pen x={23} y={1472} w={665} amount={ramp(t,25.85,26.57)}/><Pen x={21} y={340} w={890} amount={ramp(t,28.65,29.5)}/></>}/>;
 } else if(t<32.87){
  section='常见问题';credit='outlier.ai/faq';note='项目时长取决于客户需求';
  view=<div style={{...absolute,background:'#fff',color:ink}}><div style={{...pos(65,165),...noteText}}>平台答复 · 节译</div>
   <Pic name="length" style={pos(60,295,960)}/><div style={{...pos(67,510,950),fontSize:66,fontWeight:650}}>项目能持续多久，<br/>取决于客户的需要。</div>
   <Pen x={67} y={681} w={559} amount={ramp(t,30.9,31.8)}/></div>;
 } else if(t<37.1){
  section='常见问题';credit='outlier.ai/faq';note=t<35.7?'平台答复 · 接单者可自行选择工作时间':'平台答复 · 可以拒绝项目邀请';
  const m=ramp(t,34.85,36.25);
  view=<Sheet name="outlier_faq_schedule" scale={1.02+.045*m} fx={521} fy={175+95*m} marks={<><Pen x={19} y={166} w={289} amount={ramp(t,33.77,34.5)}/><Pen x={22} y={284} w={655} amount={ramp(t,35.72,36.52)}/></>}/>;
 } else if(t<46.9){
  section='报价与工时';credit='按时计费示意';note='实际费率、培训费率和付费工时需要分别核实';
  const t1=ramp(t,37.1,37.68),t2=ramp(t,39.45,40.18),slide=ramp(t,41.55,42.35);
  view=<div style={{...absolute,background:ivory,color:ink,overflow:'hidden'}}>
   <div style={{...pos(0,-124*slide,1080)}}>
    <div style={{...pos(65,75),...noteText}}>招聘页的报价</div>
    <div style={{...pos(65,153,950),height:140,overflow:'hidden',borderBottom:'2px solid #b5aba0'}}><Pic name="price_line" style={{...pos(-7,2,690),mixBlendMode:'multiply'}}/></div>
    <div style={{...pos(67,355),...noteText}}>按小时计算收入</div>
    <div style={{...pos(61,440,980),fontSize:78,fontWeight:700,display:'flex',alignItems:'baseline',gap:26}}><span style={{opacity:t1}}>实际费率</span><span style={{fontFamily:serif,fontWeight:400}}>×</span><span style={{color:rust,opacity:t2}}>付费工时</span></div>
    <Pen x={525} y={539} w={330} amount={t2}/>
    <div style={{...pos(65,649,946),borderTop:'1px solid #b8b0a3',paddingTop:35,fontSize:44,lineHeight:1.7,color:grey}}>
     <span style={{opacity:ramp(t,41.65,42.8)}}>常规任务按什么费率？</span><br/><span style={{opacity:ramp(t,43.9,44.65)}}>培训另算多少？</span><br/><span style={{opacity:ramp(t,45.16,45.82)}}>每月能接到多少小时？</span></div>
   </div></div>;
 } else if(t<49.83){
  section='使用条款';credit='第 12 节';note='原文涉及账户终止后已完成任务的结算';
  const m=ramp(t,47.15,48.35);
  view=<Sheet name="outlier_terms_final" scale={1.02} fx={527} fy={lerp(180,670,m)} marks={<><Pen x={18} y={697} w={915} amount={ramp(t,48.1,48.7)}/><Pen x={18} y={754} w={287} amount={ramp(t,48.6,49.12)}/></>}/>;
 } else {
  section='招募页存档';credit='2026.05.18';note='回看报价 · Up to 表示上限';
  const m=ramp(t,49.83,50.7);
  view=<div style={{...absolute,background:ivory,color:ink}}>
   <div style={{...pos(0,0,1080),height:490,overflow:'hidden',background:'white'}}><div style={{...pos(52-5*m,150-5*m,950+22*m)}}><Pic name="price_line" style={{width:'100%'}}/></div></div>
   <div style={{...pos(63,573),...noteText}}>这行报价里缺的那个数</div>
   <div style={{...pos(62,677,1000),fontSize:77,fontWeight:700,opacity:ramp(t,50.15,50.62)}}>下个月有多少付费工时？</div>
   <Pen x={460} y={784} w={350} amount={ramp(t,51.22,52.06)}/></div>;
 }
 return <AbsoluteFill style={{fontFamily:font,background:'#10110f',color:'#faf8ee'}}>
  <div style={{...pos(62,110),fontSize:35,fontWeight:650}}>{source} <span style={{fontWeight:400,color:'#c2bfae'}}>／ {section}</span></div><div style={{position:'absolute',right:61,top:119,fontSize:30,color:'#b3b0a3'}}>{credit}</div>
  <div style={{...pos(0,213,1080),height:987,overflow:'hidden'}}>{view}</div>
  <div style={{...pos(60,1244,960),display:'flex',alignItems:'center',gap:18,fontSize:35,color:'#ddd9cc'}}><span style={{width:48,height:4,flexShrink:0,background:amber}}/>{note}</div>
  <Sequence from={-300}><Captions pages={pages}/></Sequence><div style={{...pos(0,0,1080),height:8,background:'#222220'}}><div style={{height:8,width:100*t/53.3+'%',background:amber}}/></div>
 </AbsoluteFill>
}
registerRoot(()=> <Composition id="FullBody" component={Body} durationInFrames={1299} fps={30} width={1080} height={1920}/>);
