import {csvClassValues} from '../src/components/csvClassValues.ts';
import assert from 'node:assert/strict';
assert.deepEqual({...csvClassValues('\uFEFFa,b,c\r\n"a,b","say ""yes""",0\r\n"line\nbreak",no,1\r\n"a,b",NA,2\r\n')},{a:['a,b','line\nbreak'],b:['say "yes"','no'],c:[]});
assert.deepEqual({...csvClassValues('x,y\n 0,\n1,NA\n0,1')},{x:[],y:['1']});
assert.deepEqual({...csvClassValues('x\n0\n1\n')},{x:['0','1']});
console.log('CSV quoting, exact values, missing values and high-cardinality checks passed');
