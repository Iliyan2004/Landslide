// ---------- rockfall impact: block mass and energy, collisions with buildings, roads, bridges and facilities, damage, fragmentation, barriers
const rockMass=r=>IMP.rockRho*4/3*Math.PI*r*r*r;                    // kg, sphere of density rockRho
const rockKE=(r,v)=>.5*rockMass(r)*v*v/1000;                       // kJ, translational energy only (rotation is neglected)
// intersection of segment p1-p2 with segment p3-p4: [x, y, t along p1-p2] or null
function segHit(x1,y1,x2,y2,x3,y3,x4,y4){const den=(x2-x1)*(y4-y3)-(y2-y1)*(x4-x3);if(Math.abs(den)<1e-12)return null;const t=((x3-x1)*(y4-y3)-(y3-y1)*(x4-x3))/den,u=((x3-x1)*(y2-y1)-(y3-y1)*(x2-x1))/den;return(t>=0&&t<=1&&u>=0&&u<=1)?[x1+t*(x2-x1),y1+t*(y2-y1),t]:null}
// barrier: R.barrier={x1,y1,x2,y2,cap (kJ),h (m)} in window coordinates; called by stepRocks after each move of a block from (ox, oy)
function barrierCheck(R,b,ox,oy){const B=R.barrier;if(!B||b.stopped)return;const h=segHit(ox,oy,b.x,b.y,B.x1,B.y1,B.x2,B.y2);if(!h)return;
 const gz=sampleZ(R,h[0],h[1]);if((b.z-b.r)-gz>=B.h){B.over=(B.over||0)+1;return}                    // the block's lower edge is above the top of the barrier
 const sp=Math.hypot(b.vx,b.vy,b.vz),ke=rockKE(b.r,sp);
 if(ke<=B.cap){b.stopped=true;b.vx=b.vy=b.vz=0;b.x=h[0];b.y=h[1];b.barrier='stopped';B.stopped=(B.stopped||0)+1;B.absorbed=(B.absorbed||0)+ke}
 else{const f=Math.sqrt((ke-B.cap)/ke);b.vx*=f;b.vy*=f;b.vz*=f;b.barrier='passed';B.passed=(B.passed||0)+1;B.absorbed=(B.absorbed||0)+B.cap}}

// spatial hash of everything a block can hit, in window coordinates (metres from the window centre)
function rockIndex(R){const cs=20,H=new Map(),add=(k,i,x,y,rad)=>{if(Math.abs(x)>R.HALF+30||Math.abs(y)>R.HALF+30)return;const key=Math.floor((x+R.HALF)/cs)+','+Math.floor((y+R.HALF)/cs);let l=H.get(key);if(!l){l=[];H.set(key,l)}l.push([k,i,x,y,rad])};
 if(BP)for(let b=0;b<BP.n;b++){const x=X0+BP.xy[2*b]-R.E0,y=Y1-BP.xy[2*b+1]-R.N0;if(Math.abs(x)<=R.HALF&&Math.abs(y)<=R.HALF)add('b',b,x,y,Math.max(4,Math.sqrt(BP.ar[b]/Math.PI)))}
 INFRA.pois.forEach((p,i)=>add('f',i,X0+p.x-R.E0,Y1-p.y-R.N0,8));
 INFRA.roads.forEach((r,ri)=>{pointsAlong(r.xy,5).forEach(q=>add(r.b?'g':'r',ri,X0+q[0]-R.E0,Y1-q[1]-R.N0,3))});
 return{H,cs}}
function rockQuery(ix,R,x,y,r,fn){const cx=Math.floor((x+R.HALF)/ix.cs),cy=Math.floor((y+R.HALF)/ix.cs);for(let a=-1;a<=1;a++)for(let b=-1;b<=1;b++){const l=ix.H.get((cx+a)+','+(cy+b));if(!l)continue;for(const e of l){if(Math.hypot(x-e[2],y-e[3])<=e[4]+r)fn(e)}}}
// damage state probabilities of a target from the energies of several separate impacts: exceedances combine as 1 - product of (1 - exceedance)
function dsFromHits(kes){const ex=[0,0,0,0];for(let k=0;k<4;k++){let non=1;kes.forEach(e=>{const pm=dsProbs(e,IMP.rockMed,IMP.rockBeta);non*=1-pm.slice(k+1).reduce((a,b)=>a+b,0)});ex[k]=1-non}return[1-ex[0],ex[0]-ex[1],ex[1]-ex[2],ex[2]-ex[3],ex[3]]}

function impactRock(R,ixIn){const rocks=R.rocks;if(!rocks||!rocks.length)return null;const ix=ixIn||rockIndex(R);
 const o={n:rocks.length,breaks:R.nfrag||0,massT:0,massMaxKg:0,keMax:0,keMaxBlock:-1,stopped:rocks.filter(b=>b.stopped).length,travMax:0,hits:{b:new Map(),f:new Map(),r:new Map(),g:new Map()},roadStops:new Map(),barrier:R.barrier||null};
 rocks.forEach((b,bi)=>{const m=rockMass(b.r);o.massT+=m/1000;if(m>o.massMaxKg)o.massMaxKg=m;if(b.trav>o.travMax)o.travMax=b.trav;
  const T=b.trail,TV=b.tv||[],TR=b.tr||[],cur=new Map();
  for(let t=0;t<T.length;t++){const x=T[t][0],y=T[t][1],v=TV[t]!==undefined?TV[t]:0,r=TR[t]!==undefined?TR[t]:b.r,ke=rockKE(r,v);if(ke>o.keMax){o.keMax=ke;o.keMaxBlock=bi}
   const pts=[[x,y]];if(t+1<T.length){const dx=T[t+1][0]-x,dy=T[t+1][1]-y,L=Math.hypot(dx,dy),m2=Math.floor(L/2);for(let s=1;s<=m2;s++)pts.push([x+dx*s/(m2+1),y+dy*s/(m2+1)])}
   pts.forEach(([px,py])=>rockQuery(ix,R,px,py,r,e=>{const key=e[0]+':'+e[1],c=cur.get(key);if(!c||ke>c[2])cur.set(key,[e[0],e[1],ke])}))}
  cur.forEach(([kind,idx,ke])=>{const mp=o.hits[kind];let h=mp.get(idx);if(!h){h={kes:[],maxKE:0};mp.set(idx,h)}h.kes.push(ke);if(ke>h.maxKE)h.maxKE=ke});
  if(b.r*2>=.8)rockQuery(ix,R,b.x,b.y,b.r,e=>{if(e[0]==='r'||e[0]==='g')o.roadStops.set(e[0]+e[1]+':'+bi,e[1])})});
 const flowDR=R.impact&&R.impact.b?R.impact.b.dr:null;
 const B={hit:o.hits.b.size,modal:[0,0,0,0,0],exp:[0,0,0,0,0],cost:0,extra:0,people:0,pts:[]};
 o.hits.b.forEach((h,bi)=>{const pm=dsFromHits(h.kes),dr=expDR(pm),ds=dsModal(pm),area=BP.ar[bi]*IMP.floors,fd=flowDR?flowDR[bi]:0,cc=coarseCell(BP.xy[2*bi],BP.xy[2*bi+1]);
  B.modal[ds]++;pm.forEach((q,s)=>B.exp[s]+=q);B.cost+=area*IMP.costM2*dr;B.extra+=area*IMP.costM2*((1-(1-dr)*(1-fd))-fd);B.people+=(POP[cc]/POPD)/Math.max(1,BCELL[cc]);B.pts.push([BP.xy[2*bi],BP.xy[2*bi+1],ds,h.maxKE])});
 o.bldg=B;
 o.bridges=[];o.hits.g.forEach((h,ri)=>{const r=INFRA.roads[ri],len=pointsAlong(r.xy,10).reduce((a,q)=>a+q[3],0),pm=dsFromHits(h.kes),prob=pm[3]+pm[4];o.bridges.push({name:r.n||'Unnamed bridge',len,ke:h.maxKE,prob,cost:len*IMP.bridgeCost*prob,ri})});
 const rs=new Set();o.roadStops.forEach(v=>rs.add(v));o.roadsBlocked=rs.size;o.roadClearCost=o.roadStops.size*150000;
 o.roadHits=o.hits.r.size;o.fac=[];o.hits.f.forEach((h,i)=>{const p=INFRA.pois[i],pm=dsFromHits(h.kes);o.fac.push({name:p.n,kind:p.k,ke:h.maxKE,ds:dsModal(pm),n:h.kes.length})});
 o.costExtra=B.extra+o.bridges.reduce((a,b)=>a+b.cost,0)+o.roadClearCost;return o}

// ---------- re-runs of the rock-only replay: without fragmentation, or with a barrier
function rerunRocks(R,mod){if(!RP.make)return null;const R2=RP.make({}),mode=V3.mode;V3.mode='rock';R2.frag=mod.frag!=null?mod.frag:R.frag;if(mod.barrier)R2.barrier=Object.assign({stopped:0,passed:0,over:0,absorbed:0},mod.barrier);
 R2.seed=R.seed;initPhysics(R2);const lim=val('v3tl');let g=0;while(R2.tsim<lim&&g++<400){stepSim(R2,.5);if(R2.tsim>15&&R2.moving===0)break}V3.mode=mode;R2.rockImpact=impactRock(R2);return R2}
const IMPB={mode:false,pts:[],cap:500,h:3,cmp:null,frag:null};
