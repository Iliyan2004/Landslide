#version 300 es
precision highp float;
in vec2 vUv; out vec4 o;
uniform sampler2D uDA, uDB, uVA, uVB, uTF, uBC;
uniform float uMix, uTime, uMaxD, uDry, uVmax, uMode, uFrame, uHasTF, uHasBC, uBCmax, uCell;
uniform vec2 uGrid;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
float vnoise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x), mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ float s=0., a=.5; for(int k=0;k<4;k++){ s+=a*vnoise(p); p=p*2.03+vec2(1.7,9.2); a*=.5; } return s; }
float depthAt(vec2 uv){ float a=texture(uDA,uv).r, b=texture(uDB,uv).r; return mix(a*a,b*b,uMix)*uMaxD; }
vec2 velAt(vec2 uv){ vec2 a=texture(uVA,uv).rg*2.-1., b=texture(uVB,uv).rg*2.-1.; return mix(a,b,uMix)*uVmax; }
vec3 ramp(float t){                       // slow, blue-cyan -> yellow -> orange -> dark red (speed)
  t = clamp(t,0.,1.);
  vec3 c0=vec3(0.16,0.22,0.52), c1=vec3(0.10,0.62,0.72), c2=vec3(0.96,0.86,0.26), c3=vec3(0.96,0.46,0.12), c4=vec3(0.55,0.04,0.10);
  return t<0.25 ? mix(c0,c1,t*4.) : t<0.5 ? mix(c1,c2,(t-.25)*4.) : t<0.75 ? mix(c2,c3,(t-.5)*4.) : mix(c3,c4,(t-.75)*4.);
}
void main(){
  vec2 px = 1.0/uGrid;
  vec2 q = vUv*uGrid;
  // ------------------------------------------------------------ terrain change (static): deposit warm, erosion cool, lit as relief
  if (uMode > 2.5) {
    float bc = (texture(uBC,vUv).r*255.-128.)/127.*uBCmax;
    float a = smoothstep(0.04, 0.30, abs(bc));
    if (a <= 0.002) { o = vec4(0.); return; }
    vec3 dep = mix(vec3(0.94,0.82,0.58), vec3(0.40,0.21,0.07), clamp(bc/uBCmax,0.,1.));
    vec3 ero = mix(vec3(0.72,0.86,0.96), vec3(0.06,0.22,0.55), clamp(-bc/uBCmax,0.,1.));
    vec3 c = bc > 0. ? dep : ero;
    float gx = texture(uBC,vUv-vec2(px.x,0)).r - texture(uBC,vUv+vec2(px.x,0)).r;
    float gy = texture(uBC,vUv-vec2(0,px.y)).r - texture(uBC,vUv+vec2(0,px.y)).r;
    c *= clamp(0.95 + (gx*-0.45 + gy*0.55)*9.0, 0.62, 1.3);
    c *= 0.9 + 0.2*vnoise(q*2.3);
    o = vec4(c*a*0.96, a*0.96); return;
  }
  // ------------------------------------------------------------ scar: where and when the slope failed
  vec4 scar = vec4(0.);
  if (uHasTF > 0.5 && uMode < 1.5) {
    // soft, ragged scar outline: blur the released-so-far mask over the neighbouring cells, then threshold it with a little noise
    vec2 wob = (vec2(fbm(q*0.9), fbm(q*0.9+17.3)) - 0.5) * 0.9 * px;
    float m = 0., ageSum = 0., wsum = 0.;
    for (int j=-1;j<=1;j++) for (int i=-1;i<=1;i++) {
      vec2 o2 = vec2(float(i), float(j))*px*0.9;
      float tfk = texture(uTF, vUv + o2 + wob).r*255.;
      float agek = uFrame - (tfk - 1.0);
      float on = (tfk > 0.5 && agek >= 0.) ? 1. : 0.;
      float w = (i==0 && j==0) ? 2.0 : (i==0 || j==0) ? 1.0 : 0.6;
      m += on*w; wsum += w; ageSum += on*w*agek;
    }
    m /= wsum;
    float cover = smoothstep(0.32, 0.62, m);
    if (cover > 0.002) {
      float age = ageSum/max(m*wsum, 1e-3);
      float flash = exp(-age*0.8);
      float grain = vnoise(q*2.7)*0.6 + vnoise(q*6.1)*0.4;
      vec3 sc = mix(vec3(0.80,0.66,0.50), vec3(0.98,0.30,0.10), flash);       // exposed pale earth, hot red at the moment of failure
      sc *= 0.80 + 0.36*grain;
      float rim = 1.0 - smoothstep(0.55, 0.95, m);                             // darker, rougher rim where the scar ends
      sc *= 1.0 - 0.34*rim;
      float a = cover*(0.66 + 0.32*flash);
      scar = vec4(sc*a, a);
    }
  }
  float d = depthAt(vUv);
  float edge = smoothstep(uDry*0.35, uDry*2.0, d);
  if (edge <= 0.002) {                                                          // beside the flow: only the scar and the contact shadow
    float sd0 = depthAt(vUv + vec2(0.50,0.42)*px*2.4);
    float sa = clamp(sd0*0.9/(uMaxD*0.12+0.3), 0., 1.)*0.38;
    o = vec4(scar.rgb*(1.-sa), scar.a*(1.-sa) + sa); return;
  }
  vec2 v = velAt(vUv);
  float spd = length(v);
  // ------------------------------------------------------------ relief of the moving or settled mass (normal from its own depth field)
  float dl=depthAt(vUv-vec2(px.x,0.)), dr=depthAt(vUv+vec2(px.x,0.)), du=depthAt(vUv-vec2(0.,px.y)), dd=depthAt(vUv+vec2(0.,px.y));
  float EX = 7.0;                                                               // exaggeration so a 1-2 m lobe reads as a mound
  vec3 n = normalize(vec3((dl-dr)/(2.*uCell)*EX, (du-dd)/(2.*uCell)*EX, 1.0));
  vec3 L = normalize(vec3(-0.50, -0.42, 0.76));
  float diff = max(dot(n, L), 0.);
  if (uMode > 1.5) {                                                            // speed: scientific ramp, still lit
    float s = clamp(spd/uVmax, 0., 1.);
    vec3 c = ramp(s) * (0.62 + 0.55*diff);
    float a = edge*0.93; o = vec4(c*a + scar.rgb*(1.-a), a + scar.a*(1.-a)); return;
  }
  // ------------------------------------------------------------ material: mud and gravel, wet and dark while moving, pale and cracked at rest
  vec2 dir = spd > 0.05 ? v/spd : vec2(1.,0.);
  vec2 qa = vec2(dot(q,dir), dot(q,vec2(-dir.y,dir.x)));
  float streak = fbm(vec2(qa.x*0.22 - uTime*min(spd,14.)*0.30, qa.y*1.7));       // stretched along the flow direction
  float grain  = vnoise(q*3.3)*0.55 + vnoise(q*8.1)*0.45;                        // gravel
  float boulder = step(0.82, vnoise(q*1.45+7.1));                                // the odd boulder
  float rest = 1.0 - smoothstep(0.35, 1.6, spd);
  float thin = 1.0 - smoothstep(0.0, 0.30*uMaxD + 0.4, d);
  float crack = smoothstep(0.0, 0.11, abs(fbm(q*0.85+3.3)-0.5)*2.0);
  vec3 wet = vec3(0.20,0.14,0.10), dry = vec3(0.66,0.55,0.42), rock = vec3(0.47,0.46,0.45);
  vec3 base = mix(wet, dry, clamp(rest*0.78 + thin*0.35, 0., 1.));
  base = mix(base, rock, clamp(boulder*0.55 + grain*0.12, 0., 1.));
  base *= 0.80 + 0.40*streak*(1.0-rest) + 0.26*grain;
  base *= mix(1.0, 0.74 + 0.26*crack, rest);
  float hot = smoothstep(2.0, 11.0, spd) * (1.0-rest);                           // very fast front picks up a warm sheen of kicked-up dust
  vec3 col = base*(0.52 + 0.70*diff) + vec3(1.0,0.60,0.25)*hot*0.30;
  // contact shadow on the ground beside the lobe, cast away from the light
  float sd = depthAt(vUv + vec2(0.50,0.42)*px*2.4);
  float shade = clamp(sd*0.9/(uMaxD*0.12+0.3), 0., 1.) * (1.0-edge);
  // rim: thin edge fades into the ground, dust halo where fast
  float rimA = smoothstep(uDry*0.5, uDry*3.5, d);
  float dust = smoothstep(2.5, 9.0, spd) * (1.0-edge)*0.4;
  float alpha = edge * mix(0.62, 0.97, rimA);
  vec3 outc = col*alpha + scar.rgb*(1.-alpha);
  float outa = alpha + scar.a*(1.-alpha);
  outc *= (1.0 - 0.45*shade*(1.0-outa)); outa = max(outa, shade*0.35 + dust);
  o = vec4(outc + vec3(0.8,0.7,0.55)*dust*0.5, outa);
}
