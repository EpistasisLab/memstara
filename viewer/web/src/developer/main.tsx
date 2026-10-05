import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import Atlas from './Atlas';

createRoot(document.getElementById('root')!).render(<StrictMode><Atlas/></StrictMode>);
