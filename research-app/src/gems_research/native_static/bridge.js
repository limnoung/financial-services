"use strict";
(function(){
  // This additive drawer leaves the installed DartLab terminal and routing intact.
  if(window.top!==window.self || document.getElementById("gems-launcher")) return;
  function node(tag,text){var n=document.createElement(tag);if(text)n.textContent=text;return n;}
  function valid(code){return /^[A-Za-z0-9.^_-]{1,20}$/.test(code || "");}
  function context(){
    var route=location.pathname.match(/^\/(terminal|analysis)\/([A-Za-z0-9.^_-]{1,20})(?:\/|$)/),query=new URLSearchParams(location.search),last="";
    try{last=localStorage.getItem("dlTerm.lastSym") || "";}catch(_){}
    var requested=query.get("sym"),chat=query.get("code");
    if(valid(requested))return requested;
    if(route && route[1]==="analysis")return route[2];
    if(location.pathname==="/chat" && valid(chat))return chat;
    if(valid(last))return last;
    return route ? route[2] : "";
  }
  var launcher=node("button","Gems · 재무 검토");launcher.id="gems-launcher";launcher.type="button";launcher.setAttribute("aria-haspopup","dialog");
  var panel=node("dialog");panel.id="gems-drawer";panel.setAttribute("aria-labelledby","gems-drawer-title");
  var head=node("header"),heading=node("div"),title=node("strong","Gems Research");title.id="gems-drawer-title";
  var caption=node("small");heading.append(title,caption);
  var close=node("button","닫기 ✕");close.type="button";close.onclick=function(){panel.close();};head.append(heading,close);
  var bar=node("nav"),buttons={},view="evaluate";
  [["evaluate","매력도 평가"],["review","재무 검토"],["report","보고서"],["history","저장 기록"]].forEach(function(item){
    var b=node("button",item[1]);b.type="button";b.dataset.view=item[0];buttons[item[0]]=b;b.onclick=function(){view=item[0];sendView();};bar.appendChild(b);
  });
  var use=node("button","현재 종목 가져오기");use.type="button";use.className="gems-context";use.onclick=function(){post({type:"gems-select-company",symbol:context()});};bar.appendChild(use);
  var ai=node("a","DartLab AI ↗");ai.target="_blank";ai.rel="noopener";bar.appendChild(ai);
  var frame=node("iframe");frame.title="Gems 매력도 평가와 financial-services 재무 검토";
  function post(data){if(frame.contentWindow)frame.contentWindow.postMessage(data,location.origin);}
  function updateTabs(){Object.keys(buttons).forEach(function(k){buttons[k].classList.toggle("active",k===view);});}
  function sendView(){updateTabs();post({type:"gems-view",view:view});}
  var lastContext="";
  function updateContext(){var code=context();caption.textContent=code?"DartLab 조회 종목: "+code:"DartLab에서 종목을 선택하거나 패널에 직접 입력하세요.";use.disabled=!code;ai.href="/chat?code="+encodeURIComponent(code);if(code!==lastContext){lastContext=code;post({type:"gems-context",symbol:code});}}
  launcher.onclick=function(){
    if(!frame.getAttribute("src"))frame.src="/gems/?embedded=1&symbol="+encodeURIComponent(context());
    updateContext();panel.showModal();sendView();
  };
  panel.addEventListener("close",function(){launcher.focus();});
  window.addEventListener("message",function(event){
    if(event.origin!==location.origin || event.source!==frame.contentWindow)return;
    if(event.data && event.data.type==="gems-view-changed" && Object.hasOwn(buttons,event.data.view)){view=event.data.view;updateTabs();}
    if(event.data && event.data.type==="gems-ready"){sendView();updateContext();}
  });
  panel.append(head,bar,frame);document.body.append(launcher,panel);updateContext();
  // DartLab's terminal updates this documented key when its selection changes.
  setInterval(function(){if(panel.open)updateContext();},750);
})();
