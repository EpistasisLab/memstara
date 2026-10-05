import KnowledgeFilterUpdate from './KnowledgeFilterUpdate';
import {useEffect, useRef, useState} from 'react';
import {ArrowDown} from 'lucide-react';

export type SimpleStory = {assignment:string;steps: {title:string; ai:string; software:string; result:string}[]};
type Language = 'en'|'ko';
function Exchange({step,index,language,animate,searchExcerpt}:{searchExcerpt?:string;step:SimpleStory['steps'][number];index:number;language:Language;animate:boolean}) {
 const ref=useRef<HTMLElement>(null),[visible,setVisible]=useState(false);
 const t=(en:string,ko:string)=>language==='ko'?ko:en;
 useEffect(()=>{const observer=new IntersectionObserver(entries=>setVisible(entries[0].isIntersecting),{threshold:.15});if(ref.current)observer.observe(ref.current);return()=>observer.disconnect();},[]);
 return <section ref={ref} className={`hyp-simple-step ${animate&&visible?'is-moving':''}`}>
  <h3><span>{index+1}</span>{index===1?t('Search using verified category choices','확인된 분류 선택지로 검색하기'):step.title}</h3>
  {index===1&&<KnowledgeFilterUpdate language={language} excerpt={searchExcerpt}/>}
  {index===1?<details className="hyp-extra hyp-historical-search"><summary>{t('Earlier run: view the recorded search','과거 실행: 당시 검색 설명 보기')}</summary><p>{step.ai}</p><p>{step.software}</p><p>{step.result}</p></details>:<>
  <div className="hyp-simple-exchange"><article><b>{t('AI request','AI의 요청')}</b><p>{step.ai}</p></article><div className="hyp-simple-arrow" aria-hidden="true">→<i/></div><article><b>{t('What the program did','프로그램의 처리')}</b><p>{step.software}</p></article></div>
  <p className="hyp-simple-result">{step.result}</p></>}
  {index<7&&<ArrowDown className="hyp-down" aria-hidden="true"/>}
 </section>;
}
export default function SimpleHypothesisLesson({language,story,loading,animate,paused,reduced,onLanguage,onDetails,onPause,searchExcerpt}:{searchExcerpt?:string;language:Language;story?:SimpleStory;loading:boolean;animate:boolean;paused:boolean;reduced:boolean;onLanguage:(lang:Language)=>void;onDetails:()=>void;onPause:()=>void}){
 const t=(en:string,ko:string)=>language==='ko'?ko:en;
 return <section className="hyp-simple" lang={language}>
  <div className="hyp-topline"><a href="/developer.html?view=agents">{t('← Full pipeline','← 전체 파이프라인')}</a><div className="hyp-language" role="group" aria-label="Language"><button aria-pressed={language==='en'} onClick={()=>onLanguage('en')}>English</button><button aria-pressed={language==='ko'} onClick={()=>onLanguage('ko')}>한국어</button></div></div>
  <header><p className="eyebrow">{t('ONE RECORDED EXAMPLE','실제 실행 하나로 이해하기')}</p><h2>{t('How does a research question get made?','연구 질문은 어떻게 만들어지나요?')}</h2><p>{t('The AI does not produce the finished question at once. It asks the program for information, receives an answer, then writes its next request. Follow that exchange below.','AI가 처음부터 완성된 질문을 내놓는 것은 아닙니다. 프로그램에 정보를 요청하고, 답을 받은 뒤, 다음 요청을 만듭니다. 아래에서 그 주고받는 과정을 따라가 보세요.')}</p><p className="hyp-simple-note">{t('A plain-language retelling of the saved run, not verbatim dialogue. Repeated searches and reads are shortened. The original records and tool-name help are in Detailed view.','저장된 실행을 대화처럼 쉽게 풀어쓴 설명이며 원문 인용은 아닙니다. 반복된 검색·읽기는 줄여 표시했습니다. 원본 기록과 도구 이름 도움말은 상세 보기에서 확인할 수 있습니다.')}</p></header>
  {story&&<p className="hyp-simple-assignment">{story.assignment}</p>}
  <div className="hyp-simple-controls"><button onClick={onDetails}>{t('Detailed view','상세 보기')}</button><button disabled={reduced} onClick={onPause}>{reduced?t('Reduced motion','동작 줄이기 적용'):paused?t('Resume motion','움직임 재개'):t('Pause motion','움직임 멈추기')}</button></div>
  {story?story.steps.map((step,index)=><Exchange searchExcerpt={searchExcerpt} key={index} step={step} index={index} language={language} animate={animate}/>):<p role="status">{loading?t('Loading the saved example…','저장된 예시를 불러오는 중…'):t('The saved example is unavailable. Open Detailed view for the general explanation.','저장된 예시를 불러올 수 없습니다. 일반 설명은 상세 보기에서 확인할 수 있습니다.')}</p>}
 </section>;
}
