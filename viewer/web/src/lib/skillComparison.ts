import type {Observation,MetricValue} from './confusionMetrics';

export const metricValue=(value:MetricValue)=>value.value===null?value.infinite?'∞':'Not calculable':value.value.toLocaleString(undefined,{maximumFractionDigits:4});

const palette=['#3b82f6','#10b981','#a78bfa','#f59e0b','#06b6d4','#f472b6','#84cc16','#fb7185'];
const knownColors:Record<string,string>={
 'hiv-no-knowledge':palette[0], 'hiv-okf-whole-graph':palette[1],
 'addiction-psychiatric':palette[2], 'addiction-substance-use':palette[3],
};

/** The same skill keeps its colour when filters or ordering change. */
export function comparisonColor(skill:string):string {
 if(Object.hasOwn(knownColors,skill))return knownColors[skill];
 let hash=0;for(const character of skill)hash=(hash*31+character.charCodeAt(0))|0;
 return palette[(hash>>>0)%palette.length];
}

/** Titles are display metadata; all links and grouping keep the saved IDs. */
export function comparisonLabel(skill:string,titles:Record<string,string>={}):string {
 return skill.split(' + ').map(id=>(Object.hasOwn(titles,id)?titles[id]?.trim():'')||id.replace(/[-_]+/g,' ').replace(/\b(hiv|okf|csv|kb)\b/gi,word=>word.toUpperCase())
  .replace(/\b\w/g,letter=>letter.toUpperCase())).join(' + ');
}

export function labelLines(label:string,maxLength=25):string[] {
 const words=label.split(/\s+/),lines:string[]=[];
 for(const word of words){
  if(lines.length&&lines.at(-1)!.length+word.length+1<=maxLength)lines[lines.length-1]+=' '+word;
  else lines.push(word);
 }
 return lines.length>3?[...lines.slice(0,2),lines[2].slice(0,maxLength-1)+'…']:lines;
}

/** Spread nearby evaluations horizontally, preserving their exact metric values. */
export function swarmOffsets(points:readonly {key:string;value:number}[],y:(value:number)=>number):Map<string,number> {
 const placed:{x:number;y:number}[]=[],offsets=new Map<string,number>(),gap=18;
 for(const point of [...points].sort((a,b)=>a.value-b.value||a.key.localeCompare(b.key))){
  const py=y(point.value);
  for(let lane=0;lane<=points.length*2;lane++){
   const x=lane===0?0:Math.ceil(lane/2)*gap*(lane%2?1:-1);
   if(placed.every(other=>(other.x-x)**2+(other.y-py)**2>=gap**2)){
    placed.push({x,y:py});offsets.set(point.key,x);break;
   }
  }
 }
 return offsets;
}

/** IDs can repeat across execution attempts, so never match just result_id. */
export function resultForObservation<T extends {run_tag?:string;result_id:number}>(results:readonly T[],observation:Observation):T|undefined {
 if(!observation.runTag||observation.resultId===null)return;
 return results.find(result=>result.run_tag===observation.runTag&&result.result_id===observation.resultId);
}
