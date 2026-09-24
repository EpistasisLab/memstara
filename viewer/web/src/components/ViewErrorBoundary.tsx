import {Component, Fragment, type ReactNode} from 'react';

/** Keep an individual view failure from removing execution controls and other views. */
export default class ViewErrorBoundary extends Component<{children:ReactNode; name:string}, {failed:boolean; revision:number}> {
  state={failed:false,revision:0};
  static getDerivedStateFromError(){return {failed:true};}
  render(){
    if(this.state.failed)return <section role="alert" className="view-recovery"><h2>{this.props.name} could not be displayed</h2><p>Your pipelines are not stopped by this display error. Other views remain available.</p><button type="button" onClick={()=>this.setState(s=>({failed:false,revision:s.revision+1}))}>Retry this view</button></section>;
    return <Fragment key={this.state.revision}>{this.props.children}</Fragment>;
  }
}
