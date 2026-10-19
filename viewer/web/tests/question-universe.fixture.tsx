import * as Tooltip from '@radix-ui/react-tooltip';
import React from 'react';
import {createRoot} from 'react-dom/client';
import ControlPanel from '../src/panels/ControlPanel';
import DiscoveryPanel from '../src/panels/DiscoveryPanel';
import {useLiveOutputs} from '../src/store/liveOutputs';
import '../src/index.css';
useLiveOutputs.setState({events: [
  {id:'slow',revision:1,stage:'result',question_id:9,result_id:90,run_tag:'fixture',title:'Delayed question',detail:'Fixture',status:'completed'},
  {id:'missing',revision:1,stage:'result',question_id:1,result_id:999,run_tag:'fixture',title:'Missing linked result',detail:'Fixture',status:'completed'},
] as never});
createRoot(document.getElementById('root')!).render(<Tooltip.Provider><ControlPanel/><DiscoveryPanel/></Tooltip.Provider>);
