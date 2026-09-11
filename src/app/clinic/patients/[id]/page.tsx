import {PatientCard} from '@/components/clinic';
export default async function Page({params}:{params:Promise<{id:string}>}){return <PatientCard id={(await params).id}/>;}
