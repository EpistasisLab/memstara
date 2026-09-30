import { contributionScale } from '../lib/featureImportance';

/** Signed values extend from zero; absolute magnitude is used only for pixel width. */
export default function SignedContributionBar({value, scale}: {value:number; scale:ReturnType<typeof contributionScale>}) {
  return <div className="signed-contribution-track" role="img" aria-label={`Contribution ${value}; zero baseline`} style={{position:'relative',height:8,background:'rgb(var(--line))'}}>
    <span data-contribution-value={value} style={{position:'absolute',height:'100%',left:`${scale.position(Math.min(0,value))}%`,width:`${Math.abs(value)/scale.range*100}%`,background:value<0?'#ad643d':'#769bc8'}}/>
    <span data-zero-baseline title="Zero baseline" style={{position:'absolute',height:'100%',width:2,left:`${Math.min(99.5,Math.max(.5,scale.position(0)))}%`,background:'rgb(var(--ink))'}}/>
  </div>;
}
