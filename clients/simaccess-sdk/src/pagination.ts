/** Strict bounded pagination over sample resources without cursor-derived authority. */
import {failure,invariant} from "./errors.js";
import {integer,text} from "./primitives.js";
export interface PagingRequest{
 readonly page:number;readonly pageSize:number;
 readonly sort:"newest"|"oldest";
}
export interface PagingResult<T>{
 readonly page:number;readonly pageSize:number;
 readonly items:readonly T[];readonly hasMore:boolean;
 readonly total:number;readonly simulation:true;readonly authoritative:false;
}
export function paginate<T>(items:readonly T[],request:PagingRequest):PagingResult<T>{
 const page=integer(request.page,1,10000);
 const pageSize=integer(request.pageSize,1,100);
 if(request.sort!=="newest"&&request.sort!=="oldest")throw failure("INVALID_INPUT");
 const ordered=request.sort==="oldest"?[...items].reverse():[...items];
 const start=(page-1)*pageSize;
 const subset=ordered.slice(start,start+pageSize);
 return Object.freeze({page,pageSize,items:Object.freeze(subset),
  hasMore:start+pageSize<items.length,total:items.length,
  simulation:true,authoritative:false});
}
export function aggregatePages<T>(pages:readonly PagingResult<T>[]):readonly T[]{
 if(pages.length===0)return Object.freeze([]);
 const expected=pages[0]?.page??1;
 if(expected!==1)throw failure("INVALID_INPUT");
 let last=0;
 const all:T[]=[];
 for(const current of pages){
  if(current.page!==last+1||current.simulation!==true||current.authoritative!==false)
   throw failure("UNTRUSTED_RESPONSE");
  all.push(...current.items);last=current.page;
 }
 return Object.freeze(all);
}
export function pageStatus<T>(value:PagingResult<T>,locale:"en"|"bn"):string{
 const span=`${value.items.length}/${value.total}`;
 return locale==="bn"?`নমুনা ফল ${span}`:`Sample records ${span}`;
}
export interface CursorPolicy{
 readonly mayContainAccessToken:false;
 readonly mayAuthorizePosting:false;
 readonly maxLength:64;
}
export const CURSOR_POLICY:CursorPolicy=Object.freeze({mayContainAccessToken:false,
 mayAuthorizePosting:false,maxLength:64});
export function safeCursor(raw:string):string{
 const value=text(raw,1,64);
 if(!/^[a-zA-Z0-9_-]+$/.test(value))throw failure("INVALID_INPUT");
 return value;
}
export function cursorNeverAuthorizesFinancialAction(_cursor:string):false{return false;}
