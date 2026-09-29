let token;
async function fetchRead(path){
  for(let attempt=0;;attempt++){
    try{return await fetch(path);}
    catch(error){
      if(!(error instanceof TypeError)||attempt>=2)throw error;
      await new Promise(resolve=>setTimeout(resolve,300*(attempt+1)));
    }
  }
}
async function request(path,method='GET',body){
  if(method!=='GET'&&!token) token=(await (await fetchRead('/api/session')).json()).token;
  // Retry reads only: a lost POST response may already have started a capture.
  const response=method==='GET'?await fetchRead(path):await fetch(path,{method,headers:{'Content-Type':'application/json',...(method!=='GET'?{'X-Hascone-Token':token}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const value=await response.json();
  if(!response.ok){const e=new Error(value.error||value.message||response.statusText);e.status=response.status;e.data=value;throw e;}
  return value;
}
export const api={get:p=>request(p),post:(p,b={})=>request(p,'POST',b),delete:p=>request(p,'DELETE'),url:async p=>p,blobUrl:async p=>{const r=await fetch(p);if(!r.ok)throw new Error(r.statusText);return URL.createObjectURL(await r.blob());}};
