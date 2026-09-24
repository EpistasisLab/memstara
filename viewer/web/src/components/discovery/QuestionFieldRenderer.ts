import { pointForId, type Camera } from './geometry';

interface Node { id:number; color:string; active:boolean; arrival:number }
// GPU perspective uses the same camera as DOM labels and pointer hit testing.
const vertex = `
attribute vec3 a_position;
attribute vec4 a_color;
attribute float a_size;
uniform vec2 u_view;
uniform vec3 u_camera;
uniform float u_dpr;
uniform float u_maxPoint;
varying vec4 v_color;
void main() {
  float cy=cos(u_camera.x), sy=sin(u_camera.x), cp=cos(u_camera.y), sp=sin(u_camera.y);
  vec3 p=vec3(a_position.x*cy+a_position.z*sy,a_position.y,a_position.z*cy-a_position.x*sy);
  p=vec3(p.x,p.y*cp-p.z*sp,p.y*sp+p.z*cp);
  float perspective=3.0/(3.0-p.z);
  float radius=min(u_view.x*.34,u_view.y*.37)*u_camera.z;
  vec2 pixel=vec2(u_view.x*.5,u_view.y*.49)+p.xy*radius*perspective;
  gl_Position=vec4(pixel.x/u_view.x*2.0-1.0,1.0-pixel.y/u_view.y*2.0,-p.z*.3,1.0);
  gl_PointSize=min(u_maxPoint,a_size*perspective*u_dpr);
  v_color=vec4(a_color.rgb,a_color.a*clamp(.7+p.z*.2,.2,1.0));
}`;
const fragment = `
precision mediump float;
uniform float u_kind;
varying vec4 v_color;
void main() {
  if(u_kind<.5){gl_FragColor=v_color;return;}
  vec2 uv=(gl_PointCoord-.5)*2.0;
  float r=length(uv);
  if(r>1.0)discard;
  if(u_kind>1.5){
    float alpha=exp(-r*r*7.0)*.65;
    gl_FragColor=vec4(v_color.rgb,alpha*v_color.a);return;
  }
  float halo=exp(-r*4.0)*.4;
  float body=1.0-smoothstep(.28,.34,r);
  vec3 normal=vec3(uv/.34,sqrt(max(0.0,1.0-dot(uv/.34,uv/.34))));
  float light=max(0.0,dot(normal,normalize(vec3(-.5,.65,1.0))));
  float spec=pow(light,18.0)*.65;
  vec3 color=v_color.rgb*(.45+light*.65)+vec3(spec);
  float ring=(1.0-smoothstep(.015,.035,abs(r-.58)))*.2;
  gl_FragColor=vec4(mix(v_color.rgb,color,body),max(halo+ring,body)*v_color.a);
}`;

export class QuestionFieldRenderer {
  private gl:WebGLRenderingContext;
  private program:WebGLProgram;
  private buffer:WebGLBuffer;
  private uniforms:Record<string,WebGLUniformLocation|null>={};
  private attributes:number[];
  private dust:number[]=[];
  private maxPoint:number;
  private canvas:HTMLCanvasElement;
  constructor(canvas:HTMLCanvasElement) {
    this.canvas=canvas;
    const gl=canvas.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:false,powerPreference:'low-power'});
    if(!gl)throw Error('WebGL unavailable');
    this.gl=gl;
    const shaders=[gl.VERTEX_SHADER,gl.FRAGMENT_SHADER].map((type,i)=>{
      const shader=gl.createShader(type)!;gl.shaderSource(shader,i===0?vertex:fragment);gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS)){gl.deleteShader(shader);throw Error('Shader unavailable');}return shader;
    });
    const program=gl.createProgram()!;shaders.forEach(s=>gl.attachShader(program,s));gl.linkProgram(program);
    shaders.forEach(s=>gl.deleteShader(s));
    if(!gl.getProgramParameter(program,gl.LINK_STATUS)){gl.deleteProgram(program);throw Error('Renderer unavailable');}
    this.program=program;this.buffer=gl.createBuffer()!;
    for(const key of ['view','camera','dpr','kind','maxPoint'])this.uniforms[key]=gl.getUniformLocation(program,`u_${key}`);
    this.attributes=['a_position','a_color','a_size'].map(a=>gl.getAttribLocation(program,a));
    this.maxPoint=gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE)[1];
    // Ambient particles are decorative, deterministic, and never selectable questions.
    for(let i=0;i<360;i++){
      const p=pointForId(i+700000), radius=.55+((i*37)%101)/80;
      this.dust.push(p.x*radius,p.y*radius,p.z*radius,.43,.62,.7,.1+(i%4)*.055,1.5+(i%3)*.6);
    }
  }
  draw(camera:Camera,w:number,h:number,nodes:Node[],phase:number,dark:boolean,focused:boolean){
    const gl=this.gl,dpr=Math.min(devicePixelRatio||1,2);
    const width=Math.round(w*dpr),height=Math.round(h*dpr);
    if(this.canvas.width!==width||this.canvas.height!==height){this.canvas.width=width;this.canvas.height=height;}
    gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    gl.useProgram(this.program);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
    gl.uniform2f(this.uniforms.view,w,h);gl.uniform3f(this.uniforms.camera,camera.yaw,camera.pitch,camera.zoom);
    gl.uniform1f(this.uniforms.dpr,dpr);gl.uniform1f(this.uniforms.maxPoint,this.maxPoint);
    gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);
    for(let i=0;i<3;i++){gl.enableVertexAttribArray(this.attributes[i]);gl.vertexAttribPointer(this.attributes[i],[3,4,1][i],gl.FLOAT,false,32,[0,12,28][i]);}
    const paint=(data:number[],kind:number,mode:number)=>{gl.uniform1f(this.uniforms.kind,kind);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.DYNAMIC_DRAW);gl.drawArrays(mode,0,data.length/8);};
    gl.disable(gl.DEPTH_TEST);
    paint(this.dust,2,gl.POINTS);
    // Orbit paths are spatial scaffolding, never inferred scientific relationships.
    for(let orbit=0;orbit<5;orbit++){
      const points:number[]=[],tilt=orbit*.68+.25,radius=1.02+orbit*.07;
      for(let i=0;i<=160;i++){
        const a=i/160*Math.PI*2, x=Math.cos(a)*radius,y=Math.sin(a)*radius;
        const arc=.5+.5*Math.sin(a*2+phase*.2+orbit);
        points.push(x,y*Math.cos(tilt),y*Math.sin(tilt),.46,.62,.75,(dark?.3:.2)*(.25+arc)*(focused?.3:1),1);
      }paint(points,0,gl.LINE_STRIP);
    }
    gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.depthMask(true);
    const particles:number[]=[];
    for(const n of nodes){const p=pointForId(n.id);const rgb=[1,3,5].map(i=>parseInt(n.color.slice(i,i+2),16)/255);
      particles.push(p.x,p.y,p.z,...rgb,(focused&&!n.active?.2:1)*n.arrival,n.active?82:55);
    }
    paint(particles,1,gl.POINTS);gl.disable(gl.DEPTH_TEST);
  }
  dispose(){this.gl.deleteBuffer(this.buffer);this.gl.deleteProgram(this.program);}
}
