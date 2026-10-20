import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import MotoroRecords from '../src/components/MotoroRecords';
import '../src/index.css';
function Fixture(){const [loop,setLoop]=useState(1);return <><button onClick={()=>setLoop(2)}>Choose loop 2</button><MotoroRecords key={loop} tag="fixture" loop={loop}/></>;}
createRoot(document.getElementById('root')!).render(<Fixture/>);
