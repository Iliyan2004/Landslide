// ---------- impact assessment of a replay: what the flow (and later the blocks) would damage
// Every fragility threshold, damage ratio and unit cost below is an ASSUMPTION (see the Technical Reference, Part XII). None is calibrated to
// observed damage in Pakistan. Costs are in Pakistani rupees (PKR) and are order-of-magnitude figures for comparing scenarios.
const IMP={rho:1800,floors:1,costM2:35000,dr:[0,.05,.2,.55,1],med:[5,15,40,100],beta:.6,minDepth:.3,dispFrac:[0,0,.5,1,1],hh:6.4,
 roadBlock:.5,roadCost:[6e6,4e6,2e6,.6e6],bridgeCost:4e5,bridgeMed:40,cropHa:2.5e5,
 rockRho:2700,rockMed:[10,40,150,600],rockBeta:.7};   // rock fragility in kJ
const DSNAME=['DS0 none','DS1 slight','DS2 moderate','DS3 extensive','DS4 complete'],DSCOL=['#6e7880','#ffd24a','#ff9a3a','#e04848','#8a1c1c'];
const ROADN=['Highway or primary','Secondary or tertiary','Local road','Track'];
const INFRA=D.infra||{roads:[],pois:[],places:[]};
const BP=D.bpts?(()=>{const a=dec(D.bpts.xy),b=dec(D.bpts.area);return{n:D.bpts.n,xy:new Float32Array(a.buffer.slice(a.byteOffset,a.byteOffset+a.byteLength)),ar:new Uint16Array(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength))}})():null;
const BCELL=(()=>{const c=new Int32Array(NC);if(BP)for(let b=0;b<BP.n;b++){const col=Math.min(D.w-1,Math.max(0,Math.floor(BP.xy[2*b]/D.cell_m))),row=Math.min(D.h-1,Math.max(0,Math.floor(BP.xy[2*b+1]/D.cell_m)));c[row*D.w+col]++}return c})();
function normCdf(z){const t=1/(1+.2316419*Math.abs(z)),d=.3989423*Math.exp(-z*z/2),p=d*t*(.3193815+t*(-.3565638+t*(1.781478+t*(-1.821256+t*1.330274))));return z>0?1-p:p}
// probabilities of damage states DS0..DS4 from an intensity (lognormal fragility, medians in `med` for DS1..DS4)
function dsProbs(im,med,beta){const c=med.map(m=>im<=0?0:normCdf(Math.log(im/m)/beta));return[1-c[0],c[0]-c[1],c[1]-c[2],c[2]-c[3],c[3]]}
const dsModal=pm=>{let k=0;let acc=0;for(let s=4;s>=1;s--){acc+=pm[s];if(acc>=.5){k=s;break}}return k};   // highest state reached with probability at least one half
const flowIM=(h,v)=>IMP.rho*(v*v+.5*9.81*h)/1000;                 // kPa: dynamic pressure plus half the hydrostatic pressure of the depth
const IMF={flow:{im:flowIM,med:IMP.med,beta:IMP.beta,unit:'kPa'},flood:{im:(h,v)=>h+v*v/19.62,med:[.5,1.5,3,5],beta:.5,unit:'m'}};   // hazard model in use: debris flow (pressure) or breach flood (depth plus velocity head)
let HZ=IMF.flow;
const expDR=pm=>pm.reduce((a,p,k)=>a+p*IMP.dr[k],0);
// window cell index for a point given in metres from the page extent corner (x east, y down), or -1 outside the window
function winCell(R,wx,wy){const fi=(X0+wx-(R.E0-R.HALF))/R.DXW,fj=(Y1-wy-(R.N0-R.HALF))/R.DXW;if(fi<0||fj<0||fi>=R.n||fj>=R.n)return -1;return(fj|0)*R.n+(fi|0)}
function coarseCell(wx,wy){const col=Math.min(D.w-1,Math.max(0,Math.floor(wx/D.cell_m))),row=Math.min(D.h-1,Math.max(0,Math.floor(wy/D.cell_m)));return row*D.w+col}

function impactFootprint(R){const n=R.n,F=R.fl,dx2=R.DXW*R.DXW;const h=[],v=[];let cells=0,pc=[0,0,0],hm=0,vm=0,pm=0;
 for(let k=0;k<n*n;k++){if(F.Hmax[k]>=IMP.minDepth){cells++;h.push(F.Hmax[k]);v.push(F.Vmax[k]);if(F.Hmax[k]>hm)hm=F.Hmax[k];if(F.Vmax[k]>vm)vm=F.Vmax[k];const p=HZ.im(F.Hmax[k],F.Vmax[k]);if(p>pm)pm=p;pc[p<5?0:p<30?1:2]++}}
 const q=(a,f)=>{if(!a.length)return 0;const b=[...a].sort((x,y)=>x-y);return b[Math.min(b.length-1,Math.floor(f*(b.length-1)))]};
 return{areaKm2:cells*dx2/1e6,hmax:hm,vmax:vm,pmax:pm,hMed:q(h,.5),hP90:q(h,.9),vMed:q(v,.5),vP90:q(v,.9),pressureKm2:pc.map(c=>c*dx2/1e6)}}

function impactBuildings(R){if(!BP)return null;const n=R.n,F=R.fl,o={dr:new Float32Array(BP.n),costDS:[0,0,0,0,0],inWindow:0,affected:0,ds:[0,0,0,0,0],dsExp:[0,0,0,0,0],cost:0,floorM2:0,people:0,peopleExposed:0,displaced:0,atRisk:0,pts:[]};
 for(let b=0;b<BP.n;b++){const wx=BP.xy[2*b],wy=BP.xy[2*b+1],k=winCell(R,wx,wy);if(k<0)continue;o.inWindow++;const h=F.Hmax[k];
  if(h<IMP.minDepth){o.ds[0]++;o.dsExp[0]++;continue}
  const v=F.Vmax[k],p=HZ.im(h,v),pm=dsProbs(p,HZ.med,HZ.beta),ds=dsModal(pm),cc=coarseCell(wx,wy),ppl=(POP[cc]/POPD)/Math.max(1,BCELL[cc]),area=BP.ar[b]*IMP.floors;
  o.affected++;o.ds[ds]++;pm.forEach((q,s)=>o.dsExp[s]+=q);const dr_=expDR(pm);o.dr[b]=dr_;o.cost+=area*IMP.costM2*dr_;pm.forEach((q,s)=>o.costDS[s]+=area*IMP.costM2*q*IMP.dr[s]);o.floorM2+=area;o.people+=ppl;
  o.displaced+=ppl*pm.reduce((a,q,s)=>a+q*IMP.dispFrac[s],0);if(ds>=3)o.peopleExposed+=ppl;o.atRisk+=ppl*pm[4];
  o.pts.push([wx,wy,ds,p])}
 return o}

function pointsAlong(xy,step){const pts=[];for(let i=0;i+3<xy.length;i+=2){const x1=xy[i],y1=xy[i+1],x2=xy[i+2],y2=xy[i+3],L=Math.hypot(x2-x1,y2-y1),m=Math.max(1,Math.ceil(L/step));for(let s=0;s<m;s++)pts.push([x1+(x2-x1)*s/m,y1+(y2-y1)*s/m,i/2,step*0+L/m])}
 const l=xy.length;pts.push([xy[l-2],xy[l-1],l/2-2,0]);return pts}
function impactRoads(R){const F=R.fl,o={lenKm:[0,0,0,0],blockedKm:[0,0,0,0],cost:0,segs:[],bridges:[],roadsHit:0,blockedEdges:new Set()};
 INFRA.roads.forEach((r,ri)=>{let hit=false,bl=0;const sm=pointsAlong(r.xy,10);let pk=0,hh=0;const inW=[];
  sm.forEach((q,si)=>{const k=winCell(R,q[0],q[1]);if(k<0)return;o.lenKm[r.c]+=q[3]/1000;const h=F.Hmax[k];if(h>=IMP.roadBlock){bl+=q[3];hit=true;inW.push(si);o.blockedEdges.add(ri+':'+q[2])}if(h>=IMP.minDepth){const p=HZ.im(h,F.Vmax[k]);if(p>pk)pk=p;if(h>hh)hh=h}});
  if(hit){o.roadsHit++;o.blockedKm[r.c]+=bl/1000}
  if(r.b&&(hh>=IMP.minDepth)){const len=sm.reduce((a,q)=>a+q[3],0),pr=normCdf(Math.log(Math.max(pk,.01)/(HZ===IMF.flow?IMP.bridgeMed:HZ.med[2]))/HZ.beta);o.bridges.push({ri,name:r.n||'Unnamed bridge',len,p:pk,prob:pr,h:hh,cost:len*IMP.bridgeCost*pr})}
  if(inW.length){const segs=[];let cur=null;inW.forEach(si=>{if(cur&&si===cur[1]+1)cur[1]=si;else{cur=[si,si];segs.push(cur)}});segs.forEach(([a,b])=>{const line=[];for(let s=a;s<=b+1&&s<sm.length;s++)line.push([sm[s][0],sm[s][1]]);if(line.length>1)o.segs.push(line)})}});
 o.cost=o.blockedKm.reduce((a,k,c)=>a+k*IMP.roadCost[c],0)+o.bridges.reduce((a,b)=>a+b.cost,0);return o}

function impactFacilities(R){const F=R.fl,out=[];INFRA.pois.forEach(p=>{const k=winCell(R,p.x,p.y);if(k<0)return;const h=F.Hmax[k];const pr=h>=IMP.minDepth?HZ.im(h,F.Vmax[k]):0,pm=dsProbs(pr,HZ.med,HZ.beta);out.push({kind:p.k,name:p.n,x:p.x,y:p.y,h,p:pr,ds:h>=IMP.minDepth?dsModal(pm):0,pm})});return out}

function impactLand(R){const F=R.fl,n=R.n,dx2=R.DXW*R.DXW,cls={};let crop=0;
 for(let j=0;j<n;j++)for(let i=0;i<n;i++){const k=j*n+i;if(F.Hmax[k]<IMP.minDepth)continue;const E=R.E0-R.HALF+(i+.5)*R.DXW,N=R.N0-R.HALF+(j+.5)*R.DXW,wx=E-X0,wy=Y1-N,cc=coarseCell(wx,wy),lc=LC[cc];cls[lc]=(cls[lc]||0)+dx2/1e6}
 const ha=(cls[4]||0)*100;return{cls,cropHa:ha,cropCost:ha*IMP.cropHa}}

function computeImpact(R){const I={fp:impactFootprint(R),b:impactBuildings(R),r:impactRoads(R),f:impactFacilities(R),land:impactLand(R)};R.impact=I;I.rock=(V3.mode!=='slide'&&R.rocks&&R.rocks.length)?impactRock(R):null;
 I.cost={buildings:I.b?I.b.cost:0,roads:I.r.cost,agri:I.land.cropCost,rock:I.rock?I.rock.costExtra:0};I.cost.total=I.cost.buildings+I.cost.roads+I.cost.agri+I.cost.rock;
 I.people=I.b?{affected:I.b.people,displaced:I.b.displaced,households:I.b.people/IMP.hh,displacedHh:I.b.displaced/IMP.hh,atRisk:I.b.atRisk}:null;return I}

// the same assessment for the breach flood of a landslide dam, using the flood's depth and speed fields and a depth-based fragility
function computeFloodImpact(R){const prev=HZ;HZ=IMF.flood;try{const I={fp:impactFootprint(R),b:impactBuildings(R),r:impactRoads(R),f:impactFacilities(R),land:impactLand(R)};
 I.cost={buildings:I.b?I.b.cost:0,roads:I.r.cost,agri:I.land.cropCost};I.cost.total=I.cost.buildings+I.cost.roads+I.cost.agri;
 I.people=I.b?{affected:I.b.people,displaced:I.b.displaced,households:I.b.people/IMP.hh,displacedHh:I.b.displaced/IMP.hh,atRisk:I.b.atRisk}:null;return I}finally{HZ=prev}}
