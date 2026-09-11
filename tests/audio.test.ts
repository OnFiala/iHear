import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {encodeWav} from '../src/lib/client/audio';

test('PCM WAV preserves sample rate, length, signed samples and clipping bounds',async()=>{
 const blob=encodeWav(new Float32Array([-2,-.5,0,.5,2]),48000);const v=new DataView(await blob.arrayBuffer());
 assert.equal(blob.type,'audio/wav');assert.equal(v.getUint32(24,true),48000);assert.equal(v.getUint32(40,true),10);assert.equal(v.getInt16(44,true),-32768);assert.equal(v.getInt16(52,true),32767);
});
function harness(sampleRate=100){let Klass:any;const sent:any[]=[];
 const context=vm.createContext({sampleRate,Float32Array,Math,AudioWorkletProcessor:class{port={onmessage:null,postMessage:(data:any)=>sent.push(data)};},registerProcessor:(_name:string,cls:any)=>{Klass=cls;}});
 vm.runInContext(readFileSync('public/pcm-worklet.js','utf8'),context);const instance=new Klass();
 return{instance,sent,feed:(values:number[])=>instance.process([[new Float32Array(values)]],[[new Float32Array(values.length)]]),press:()=>instance.port.onmessage({data:{type:'capture'}})};
}
test('ring buffer takes the most recent five seconds and exactly five after press',()=>{
 const h=harness();h.feed(Array.from({length:800},(_,i)=>i));h.press();h.feed(Array.from({length:500},(_,i)=>800+i));
 const done=h.sent.find(x=>x.type==='complete');assert.ok(done);assert.equal(done.preSeconds,5);assert.equal(done.postSeconds,5);assert.equal(done.samples.length,1000);assert.equal(done.samples[0],300);assert.equal(done.samples[499],799);assert.equal(done.samples[500],800);assert.equal(done.samples[999],1299);
});
test('short prebuffer extends post capture; no synthetic pre-permission audio is inserted',()=>{
 const h=harness();h.feed(Array(120).fill(.2));h.press();h.feed(Array(879).fill(.3));assert.equal(h.sent.filter(x=>x.type==='complete').length,0);h.feed([.3]);
 const done=h.sent.find(x=>x.type==='complete');assert.equal(done.preSeconds,1.2);assert.equal(done.postSeconds,8.8);assert.equal(done.samples.length,1000);
});
test('press before any audio captures ten seconds after press and ignores overlapping presses',()=>{
 const h=harness();h.press();h.press();h.feed(Array(1000).fill(.5));assert.equal(h.sent.filter(x=>x.type==='started').length,1);const done=h.sent.find(x=>x.type==='complete');assert.equal(done.preSeconds,0);assert.equal(done.postSeconds,10);
});
