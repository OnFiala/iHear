import {writeFile,mkdir} from 'node:fs/promises';
const rate=48000,seconds=12,buffer=Buffer.alloc(44+rate*seconds*2);
buffer.write('RIFF');buffer.writeUInt32LE(buffer.length-8,4);buffer.write('WAVE',8);buffer.write('fmt ',12);buffer.writeUInt32LE(16,16);buffer.writeUInt16LE(1,20);buffer.writeUInt16LE(1,22);buffer.writeUInt32LE(rate,24);buffer.writeUInt32LE(rate*2,28);buffer.writeUInt16LE(2,32);buffer.writeUInt16LE(16,34);buffer.write('data',36);buffer.writeUInt32LE(buffer.length-44,40);
for(let i=0;i<rate*seconds;i++)buffer.writeInt16LE(Math.round(Math.sin(2*Math.PI*1000*i/rate)*8192),44+i*2);
await mkdir('.local/fixtures',{recursive:true});await writeFile('.local/fixtures/tone-1000hz.wav',buffer);console.log('Generated a deterministic 1 kHz -12 dBFS peak synthetic tone. No captured recording is used.');
