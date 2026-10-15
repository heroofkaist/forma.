"use client";
import {useState} from 'react';
/** Exact viewport sizes for real routes. No mock API or authentication bypass. */
export function DesignViewport({path,initialWidth=1440}:{path:string;initialWidth?:number}){
  const [width,setWidth]=useState(initialWidth);
  return <main style={{padding:16}}><div style={{display:'flex',alignItems:'center',gap:12,marginBottom:16,flexWrap:'wrap'}}><strong>Проверка адаптивности · локальная разработка</strong>{[1440,768,390].map(w=><button className="button" key={w} aria-pressed={w===width} onClick={()=>setWidth(w)}>{w} px</button>)}</div><div style={{overflow:'auto'}}><iframe title={`Forma · ${width} px`} src={path} width={width} height={900} style={{display:'block',width,height:900,maxWidth:'none',margin:'0 auto',border:'1px solid #bdc9ad',boxSizing:'content-box'}}/></div></main>;
}
