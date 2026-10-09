import React from 'react';
import {createRoot} from 'react-dom/client';
import CostEvidence from '../src/components/CostEvidence';
import '../src/index.css';
createRoot(document.getElementById('root')!).render(<CostEvidence runTag="cost-fixture"/>);
