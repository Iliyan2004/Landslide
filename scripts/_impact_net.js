// ---------- road network: settlements and their access to hospitals, before and after the blockages
let NET=null;
function netBuild(){const nodes=new Map(),X=[],Y=[],adj=[],SP=[50,40,30,15].map(v=>v/3.6);                  // assumed free speeds by road class, m/s
 const nid=(x,y)=>{const k=Math.round(x/6)+','+Math.round(y/6);let id=nodes.get(k);if(id===undefined){id=X.length;nodes.set(k,id);X.push(x);Y.push(y);adj.push([])}return id};
 INFRA.roads.forEach((r,ri)=>{for(let i=0;i+3<r.xy.length;i+=2){const a=nid(r.xy[i],r.xy[i+1]),b=nid(r.xy[i+2],r.xy[i+3]);if(a===b)continue;const L=Math.hypot(r.xy[i+2]-r.xy[i],r.xy[i+3]-r.xy[i+1]),t=L/SP[r.c],seg=i/2;adj[a].push([b,L,t,ri,seg]);adj[b].push([a,L,t,ri,seg])}});
 const g=new Map();X.forEach((x,i)=>{const k=Math.floor(x/200)+','+Math.floor(Y[i]/200);let l=g.get(k);if(!l){l=[];g.set(k,l)}l.push(i)});
 const snap=(x,y,maxd)=>{let best=-1,bd=maxd;const cx=Math.floor(x/200),cy=Math.floor(y/200),rr=Math.ceil(maxd/200);for(let a=-rr;a<=rr;a++)for(let b=-rr;b<=rr;b++){const l=g.get((cx+a)+','+(cy+b));if(!l)continue;for(const i of l){const d=Math.hypot(X[i]-x,Y[i]-y);if(d<bd){bd=d;best=i}}}return best};
 const hosp=INFRA.pois.filter(p=>p.k==='hospital'),dest=hosp.length?hosp:INFRA.pois.filter(p=>p.k==='clinic');
 const dn=dest.map(p=>snap(p.x,p.y,500)).filter(i=>i>=0);
 const popAround=(x,y)=>{const cc=coarseCell(x,y),col=cc%D.w,row=(cc/D.w)|0;let s=0;for(let a=-1;a<=1;a++)for(let b=-1;b<=1;b++){const c2=col+a,r2=row+b;if(c2>=0&&r2>=0&&c2<D.w&&r2<D.h&&SL[r2*D.w+c2]!==255)s+=POP[r2*D.w+c2]/POPD}return s};
 const sets=INFRA.places.map(p=>({name:p.n,cls:p.c,node:snap(p.x,p.y,500),pop:popAround(p.x,p.y)}));
 return{X,Y,adj,dn,sets,nDest:dest.length,destKind:hosp.length?'hospital':'clinic'}}
function netRun(N,blocked){const n=N.X.length,dist=new Float64Array(n).fill(Infinity),len=new Float64Array(n),heap=[];
 const push=(d,i)=>{heap.push([d,i]);let k=heap.length-1;while(k>0){const p=(k-1)>>1;if(heap[p][0]<=heap[k][0])break;[heap[p],heap[k]]=[heap[k],heap[p]];k=p}};
 const pop=()=>{const top=heap[0],last=heap.pop();if(heap.length){heap[0]=last;let k=0;for(;;){const l=2*k+1,r=l+1;let m=k;if(l<heap.length&&heap[l][0]<heap[m][0])m=l;if(r<heap.length&&heap[r][0]<heap[m][0])m=r;if(m===k)break;[heap[m],heap[k]]=[heap[k],heap[m]];k=m}}return top};
 N.dn.forEach(i=>{dist[i]=0;push(0,i)});
 while(heap.length){const[d,u]=pop();if(d>dist[u])continue;for(const e of N.adj[u]){if(blocked&&blocked.has(e[3]+':'+e[4]))continue;const nd=d+e[2];if(nd<dist[e[0]]){dist[e[0]]=nd;len[e[0]]=len[u]+e[1];push(nd,e[0])}}}
 return{dist,len}}
// bridges that are probably destroyed close every segment of their road
function bridgeBlocks(bridges,set){bridges.forEach(b=>{if(b.prob>=.5){const r=INFRA.roads[b.ri];for(let s=0;s<r.xy.length/2-1;s++)set.add(b.ri+':'+s)}})}
function netAnalysis(sets){if(!NET)NET=netBuild();const N=NET;if(!N.dn.length||!N.sets.length||!N.X.length)return null;if(!N.base)N.base=netRun(N,null);
 const blocked=new Set();sets.forEach(s=>s.forEach(k=>blocked.add(k)));const af=netRun(N,blocked);
 const rows=[];let pb=0,pa=0,popIso=0,popDel=0,n0=0;
 N.sets.forEach(s=>{if(s.node<0)return;const tb=N.base.dist[s.node];if(!isFinite(tb))return;n0++;const ta=af.dist[s.node];if(tb<=1800)pb+=s.pop;if(ta<=1800)pa+=s.pop;
  if(!isFinite(ta)){popIso+=s.pop;rows.push({name:s.name,cls:s.cls,pop:s.pop,tb,ta:Infinity,km:0,status:'isolated'})}
  else if(ta-tb>=120){popDel+=s.pop;rows.push({name:s.name,cls:s.cls,pop:s.pop,tb,ta,km:(af.len[s.node]-N.base.len[s.node])/1000,status:'delayed'})}});
 rows.sort((a,b)=>(a.status==='isolated'?0:1)-(b.status==='isolated'?0:1)||b.pop-a.pop);
 return{rows,nSet:n0,nDest:N.nDest,destKind:N.destKind,isolated:rows.filter(r=>r.status==='isolated').length,delayed:rows.filter(r=>r.status==='delayed').length,popIso,popDel,access30:[pb,pa],blocked:blocked.size}}
