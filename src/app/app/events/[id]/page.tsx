import {PatientEvent} from '@/components/patient';
export default async function Page({params}:{params:Promise<{id:string}>}){return <PatientEvent id={(await params).id}/>;}
