export type CapturedAudio={blob:Blob;capture:{sampleRate:number;preSeconds:number;postSeconds:number;trackSettings:MediaTrackSettings;sourceLabel:string;routing:'unknown';interrupted:boolean}};
export function encodeWav(samples:Float32Array,sampleRate:number):Blob{
 const buffer=new ArrayBuffer(44+samples.length*2),v=new DataView(buffer);
 const string=(offset:number,text:string)=>{for(let i=0;i<text.length;i++)v.setUint8(offset+i,text.charCodeAt(i));};
 string(0,'RIFF');v.setUint32(4,buffer.byteLength-8,true);string(8,'WAVE');string(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,sampleRate,true);v.setUint32(28,sampleRate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);string(36,'data');v.setUint32(40,samples.length*2,true);
 for(let i=0;i<samples.length;i++){const x=Math.max(-1,Math.min(1,samples[i]));v.setInt16(44+i*2,x<0?x*32768:x*32767,true);}return new Blob([buffer],{type:'audio/wav'});
}
export class Microphone {
 private context?:AudioContext;private stream?:MediaStream;private node?:AudioWorkletNode;
 private pending?:{resolve:(value:CapturedAudio)=>void;reject:(error:Error)=>void;timer:ReturnType<typeof setTimeout>};
 constructor(private onInterrupted:()=>void){}
 async enable(){
  if(!navigator.mediaDevices?.getUserMedia)throw new Error('A microphone needs a secure HTTPS connection or localhost.');
  this.context=new AudioContext(); await this.context.resume();
  try{
   this.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false,channelCount:1},video:false});
   await this.context.audioWorklet.addModule('/pcm-worklet.js');
   this.node=new AudioWorkletNode(this.context,'pcm-recorder');
   this.context.createMediaStreamSource(this.stream).connect(this.node);this.node.connect(this.context.destination);
   this.stream.getAudioTracks()[0].addEventListener('ended',()=>{this.stop();this.onInterrupted();});
   this.stream.getAudioTracks()[0].addEventListener('mute',()=>{this.stop();this.onInterrupted();});
   this.context.onstatechange=()=>{if(this.context?.state==='suspended'||this.context?.state==='interrupted' as AudioContextState){this.stop();this.onInterrupted();}};
   this.node.port.onmessage=({data})=>{
    if(data.type==='complete'&&this.pending){const pending=this.pending;this.pending=undefined;clearTimeout(pending.timer);const track=this.stream!.getAudioTracks()[0];
     pending.resolve({blob:encodeWav(data.samples,this.context!.sampleRate),capture:{sampleRate:this.context!.sampleRate,preSeconds:data.preSeconds,postSeconds:data.postSeconds,trackSettings:track.getSettings(),sourceLabel:track.label||'Unknown microphone',routing:'unknown',interrupted:false}});
    }
   };
  }catch(e){this.stop();if(e instanceof DOMException){if(e.name==='NotAllowedError')throw new Error('Microphone permission was denied. Allow it in your browser settings, then try again.');if(e.name==='NotFoundError')throw new Error('No microphone was found. Check your device and try again.');}throw e;}
 }
 capture():Promise<CapturedAudio>{
  if(!this.node||this.context?.state!=='running')return Promise.reject(new Error('Enable the microphone before saving a moment.'));
  if(this.pending)return Promise.reject(new Error('A moment is already recording.'));
  return new Promise((resolve,reject)=>{this.pending={resolve,reject,timer:setTimeout(()=>{this.stop();this.onInterrupted();},15000)};this.node!.port.postMessage({type:'capture'});});
 }
 stop(){
  if(this.pending){clearTimeout(this.pending.timer);this.pending.reject(new Error('Recording was interrupted. Keep this screen open and try again.'));this.pending=undefined;}
  const context=this.context;this.context=undefined;if(context){context.onstatechange=null;void context.close().catch(()=>{});}
  this.stream?.getTracks().forEach(t=>t.stop());this.stream=undefined;this.node?.disconnect();this.node=undefined;
 }
}
