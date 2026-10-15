"use strict";
(function(){
  if(window.top!==window.self || document.getElementById("gems-codex-launcher"))return;
  function node(tag,text){var n=document.createElement(tag);if(text)n.textContent=text;return n;}
  var launcher=node("button","AI 연결 점검");launcher.id="gems-codex-launcher";launcher.type="button";launcher.setAttribute("aria-haspopup","dialog");
  var panel=node("dialog");panel.id="gems-codex-dialog";panel.setAttribute("aria-labelledby","gems-codex-title");
  var title=node("h2","Codex 모델 연결");title.id="gems-codex-title";
  var version=node("p","통합 앱 버전 확인 중…"),description=node("p","ChatGPT 로그인에서 사용할 Codex 모델을 확인합니다. 점검은 AI 질문을 전송하지 않습니다.");
  var details=node("p"),label=node("label","연결할 모델"),select=node("select");select.id="gems-codex-model";label.htmlFor=select.id;
  var status=node("p");status.setAttribute("role","status");
  var check=node("button","계정·모델 목록 확인"),apply=node("button","이 모델로 다시 연결"),close=node("button","닫기");
  check.type=apply.type=close.type="button";select.disabled=apply.disabled=true;
  var busy=false,loaded=false;
  function controls(){check.disabled=busy;apply.disabled=busy || !loaded || !select.value;select.disabled=busy || !loaded;}
  async function request(path,body){
    var response=await fetch("/_gems-extension/codex/"+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body || {})}),data=await response.json();
    if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"연결 확인에 실패했습니다.");
    return data;
  }
  select.onchange=controls;
  check.onclick=async function(){
    busy=true;loaded=false;controls();select.replaceChildren();status.textContent="로컬 Codex의 계정과 모델 목록을 확인하고 있습니다…";
    try{
      var info=await request("check");version.textContent="DartLab Research "+info.app_version;
      details.textContent="Codex 설정: "+(info.configured_model || "기본값")+" · 앱 선택: "+(info.saved_model || "자동")+(info.rejected_model?" · 이전 거절 모델: "+info.rejected_model:"");
      var placeholder=node("option","모델을 선택하세요");placeholder.value="";select.append(placeholder);
      info.models.forEach(function(item){var option=node("option",item.label+(item.is_default?" (계정 기본)":""));option.value=item.model;option.disabled=item.model===info.rejected_model;select.append(option);});
      var preferred=info.models.find(function(item){return item.model===info.saved_model && item.model!==info.rejected_model;}) || info.models.find(function(item){return item.is_default && item.model!==info.rejected_model;});
      select.value=preferred?preferred.model:"";loaded=true;
      status.textContent=info.models.length?"모델을 선택하고 다시 연결하세요. 목록 표시는 실제 AI 응답 성공을 보장하지 않습니다.":"모델 목록이 비어 있습니다. Codex CLI에서 /model을 확인하세요.";
    }catch(error){status.textContent=error.message;}finally{busy=false;controls();}
  };
  apply.onclick=async function(){
    busy=true;controls();status.textContent="모델을 다시 확인하고 연결에 적용하고 있습니다…";
    try{
      var result=await request("recover",{model:select.value});
      status.textContent=result.other_error_blocked?"모델은 저장했지만 다른 런타임 오류가 남아 있습니다. Runtime Center에서 오류 원인을 확인하세요.":"모델을 저장했습니다. 창을 닫고 AI 채팅에서 질문을 다시 보내세요. 실제 응답은 아직 확인하지 않았습니다.";
    }catch(error){status.textContent=error.message;}finally{busy=false;controls();}
  };
  launcher.onclick=function(){panel.showModal();};close.onclick=function(){panel.close();};panel.addEventListener("close",function(){launcher.focus();});
  var actions=node("div");actions.className="gems-codex-actions";actions.append(check,apply,close);
  panel.append(title,version,description,details,label,select,status,actions);document.body.append(launcher,panel);
  fetch("/_gems-extension/status",{cache:"no-store"}).then(function(response){return response.json();}).then(function(info){version.textContent="DartLab Research "+info.version;launcher.title="DartLab Research "+info.version;}).catch(function(){version.textContent="통합 앱 버전을 확인하지 못했습니다. 새 실행 창의 주소를 확인하세요.";});
})();
