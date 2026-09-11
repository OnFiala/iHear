export class ApiError extends Error {constructor(message:string,public status:number){super(message);this.name='ApiError';}}
export async function api<T>(path:string,init?:RequestInit):Promise<T>{
 const response=await fetch(path,{...init,headers:{...(init?.body instanceof FormData?{}:{'Content-Type':'application/json'}),...init?.headers},cache:'no-store'});
 const body=await response.json().catch(()=>({error:'The server returned an unreadable response.'}));
 if(!response.ok)throw new ApiError(body.error||'Something went wrong. Please try again.',response.status);
 return body as T;
}
export function dateLabel(value:string){return new Intl.DateTimeFormat('en',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value.length===10?value+'T12:00:00':value));}
