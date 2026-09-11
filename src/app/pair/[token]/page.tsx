import {PairConfirmation} from '@/components/patient';
export default async function Page({params}:{params:Promise<{token:string}>}){return <PairConfirmation token={(await params).token}/>;}
