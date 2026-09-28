let token;
async function request(path,method='GET',body){
  if(method!=='GET'&&!token) token=(await (await fetch('/api/session')).json()).token;
  const response=await fetch(path,{method,headers:{'Content-Type':'application/json',...(method!=='GET'?{'X-Hascone-Token':token}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const value=await response.json();
  if(!response.ok){const e=new Error(value.error||value.message||response.statusText);e.status=response.status;e.data=value;throw e;}
  return value;
}
export const api={get:p=>request(p),post:(p,b={})=>request(p,'POST',b),url:async p=>p,blobUrl:async p=>{const r=await fetch(p);if(!r.ok)throw new Error(r.statusText);return URL.createObjectURL(await r.blob());}};
