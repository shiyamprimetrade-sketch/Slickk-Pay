/** Machine-readable route catalog to keep SDK/API operations aligned. */
export type RouteKind="public_read"|"authenticated_read"|"preview_mutation"|"prohibited";
export interface RouteContract {readonly path:string;readonly method:"GET"|"POST";
 readonly kind:RouteKind;readonly simulation:true;readonly canMoveMoney:false;}
export const ROUTES:readonly RouteContract[]=Object.freeze([
 {path:"/lab/v4/health",method:"GET",kind:"public_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/capabilities",method:"GET",kind:"public_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/contracts",method:"GET",kind:"public_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/session",method:"POST",kind:"preview_mutation",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/me",method:"GET",kind:"authenticated_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/logout",method:"POST",kind:"preview_mutation",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/activity",method:"GET",kind:"authenticated_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/activity/search",method:"GET",kind:"authenticated_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/agents",method:"GET",kind:"authenticated_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/quotes",method:"GET",kind:"authenticated_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/quotes",method:"POST",kind:"preview_mutation",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/requests",method:"GET",kind:"authenticated_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/support",method:"GET",kind:"authenticated_read",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/support",method:"POST",kind:"preview_mutation",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/qr",method:"POST",kind:"preview_mutation",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/qr/inspect",method:"POST",kind:"preview_mutation",simulation:true,canMoveMoney:false},
 {path:"/lab/v4/notifications",method:"GET",kind:"authenticated_read",simulation:true,canMoveMoney:false}
]);
export function routeAllowed(path:string,method:"GET"|"POST"):boolean{
 const template=path.split("?")[0]??"";
 if(ROUTES.some(x=>x.path===template&&x.method===method))return true;
 return /^\/lab\/v4\/(quotes|requests)\/sim_[A-Za-z0-9_.:-]{4,88}(?:\/(?:review|cancel|receipt|cash-checklist|cash-dialogue)(?:\/(?:update|ack|cancel))?)?$/.test(template);
}
export function tableByKind(kind:RouteKind):readonly RouteContract[]{
 return Object.freeze(ROUTES.filter(x=>x.kind===kind));
}
export function neverAllowPaymentRoute(path:string):boolean{
 return !/\/(?:post|settle|cash-handover|disburse|ledger|pay|capture|withdraw|topup)/i.test(path);
}
