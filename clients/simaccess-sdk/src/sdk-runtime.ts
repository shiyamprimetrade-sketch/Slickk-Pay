/** Explicit construction of sandbox-only client resources and security switches. */
import {failure} from "./errors.js";
import {LocalTransport,makeFetchAdapter,type TransportAdapter} from "./transport.js";
import {SessionSnapshotCache} from "./cache.js";
import {InMemorySession,type DeviceClock} from "./session.js";
import {OfflinePolicy} from "./offline.js";
import {RecoveryDesk} from "./recovery.js";
import {TelemetryDesk} from "./telemetry.js";
import {RefreshCoordinator} from "./refresh.js";
import {ConnectionCircuit} from "./connection.js";
import {SafeModeController} from "./safe-mode.js";
import {SyntheticAccessClient} from "./client.js";
export interface LabRuntime {
 readonly client:SyntheticAccessClient;readonly session:InMemorySession;
 readonly cache:SessionSnapshotCache;readonly offline:OfflinePolicy;
 readonly recovery:RecoveryDesk;readonly telemetry:TelemetryDesk;
 readonly refresh:RefreshCoordinator;readonly circuit:ConnectionCircuit;
 readonly safeMode:SafeModeController;
 readonly simulation:true;readonly canPostMoney:false;
 readonly dispose:()=>void;
}
export function createLabRuntime(options:{
 readonly baseURL:string;readonly adapter:TransportAdapter;
 readonly clock?:DeviceClock;readonly nowMs?:()=>number;
}):LabRuntime{
 const now=options.nowMs??(()=>Date.now());
 const session=new InMemorySession(options.clock);
 const cache=new SessionSnapshotCache(now);
 const offline=new OfflinePolicy(now);
 const recovery=new RecoveryDesk(now);
 const telemetry=new TelemetryDesk(now);
 const refresh=new RefreshCoordinator(now);
 const circuit=new ConnectionCircuit(now);
 const safeMode=new SafeModeController(session,cache,offline,now);
 const transport=new LocalTransport(options.baseURL,options.adapter,now);
 transport.observe(event=>telemetry.receiveRequestAudit(event));
 const client=new SyntheticAccessClient({transport,session,cache,nowSeconds:()=>Math.floor(now()/1000)});
 return Object.freeze({client,session,cache,offline,recovery,telemetry,refresh,circuit,
  safeMode,simulation:true,canPostMoney:false,
  dispose:()=>{session.wipe();cache.afterLogout();offline.beforeDeviceSuspend();recovery.wipe();telemetry.clear();}});
}
export function createLocalFetchRuntime(origin:string,fetcher:typeof fetch):LabRuntime{
 return createLabRuntime({baseURL:origin,adapter:makeFetchAdapter(fetcher)});
}
export function denyProductionBootstrap(origin:string):never{
 void origin;
 throw failure("LAB_DISABLED");
}
export function noSdkMayAuthorizeFunds(_runtime:LabRuntime):false{return false;}
